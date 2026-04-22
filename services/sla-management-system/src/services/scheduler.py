"""
Scheduler de workflows Temporal para SLA Management System.

Gerencia schedules de workflows baseados em cron, eventos e triggers manuais.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

import structlog
from temporalio.client import Client

from src.clients.postgresql_client import PostgreSQLClient
from src.models.schedule import (
    Schedule,
    ScheduleExecution,
    SchedulePriority,
    ScheduleStatus,
    ScheduleTrigger,
    ScheduleType,
)

logger = structlog.get_logger(__name__)


class ScheduleManager:
    """Gerenciador de schedules para workflows Temporal."""

    def __init__(
        self,
        postgresql_client: PostgreSQLClient,
        temporal_client: Client,
        temporal_namespace: str = "default",
        temporal_task_queue: str = "sla-tasks",
    ):
        self.postgresql_client = postgresql_client
        self.temporal_client = temporal_client
        self.temporal_namespace = temporal_namespace
        self.temporal_task_queue = temporal_task_queue
        self.logger = logger
        self._running_schedules: dict[str, asyncio.Task] = {}

    async def create_schedule(
        self,
        workflow: str,
        schedule_type: ScheduleType,
        trigger: ScheduleTrigger,
        priority: SchedulePriority = SchedulePriority.MEDIUM,
        metadata: dict[str, Any] = None,
    ) -> str:
        """
        Cria novo schedule.

        Args:
            workflow: Nome do workflow Temporal
            schedule_type: Tipo de schedule (cron, event, manual)
            trigger: Configuração do trigger
            priority: Prioridade do schedule
            metadata: Metadados adicionais

        Returns:
            ID do schedule criado
        """
        schedule_id = str(uuid4())

        # Calcular próxima execução para cron
        next_run_at = None
        if schedule_type == ScheduleType.CRON and trigger.cron_expression:
            next_run_at = self._calculate_next_run(trigger.cron_expression)

        # Persistir no PostgreSQL
        schedule = Schedule(
            schedule_id=schedule_id,
            workflow=workflow,
            schedule_type=schedule_type,
            trigger=trigger,
            priority=priority,
            status=ScheduleStatus.ACTIVE,
            next_run_at=next_run_at,
            metadata=metadata or {},
        )

        await self._save_schedule(schedule)

        # Iniciar task para schedules cron
        if schedule_type == ScheduleType.CRON and schedule.status == ScheduleStatus.ACTIVE:
            await self._start_cron_schedule(schedule)

        self.logger.info(
            "schedule_created",
            schedule_id=schedule_id,
            workflow=workflow,
            type=schedule_type.value,
            priority=priority.value,
        )

        return schedule_id

    async def get_schedule(self, schedule_id: str) -> Optional[Schedule]:
        """
        Retorna schedule por ID.

        Args:
            schedule_id: ID do schedule

        Returns:
            Schedule ou None se não encontrado
        """
        query = """
            SELECT schedule_id, workflow, schedule_type, trigger_data, priority,
                   status, created_at, updated_at, last_run_at, next_run_at,
                   total_runs, failure_count, metadata
            FROM schedules
            WHERE schedule_id = $1
        """
        row = await self.postgresql_client.fetchrow(query, schedule_id)

        if not row:
            return None

        return self._row_to_schedule(row)

    async def list_schedules(
        self,
        workflow_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Schedule]:
        """
        Lista schedules com filtros.

        Args:
            workflow_type: Filtrar por workflow
            status: Filtrar por status
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de schedules
        """
        conditions = []
        params = []
        param_count = 0

        if workflow_type:
            param_count += 1
            conditions.append(f"workflow = ${param_count}")
            params.append(workflow_type)

        if status:
            param_count += 1
            conditions.append(f"status = ${param_count}")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT schedule_id, workflow, schedule_type, trigger_data, priority,
                   status, created_at, updated_at, last_run_at, next_run_at,
                   total_runs, failure_count, metadata
            FROM schedules
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
        """
        params.extend([limit, offset])

        rows = await self.postgresql_client.fetch_all(query, *params)

        return [self._row_to_schedule(row) for row in rows]

    async def trigger_workflow(self, schedule_id: str, manual: bool = False) -> dict[str, Any]:
        """
        Dispara workflow baseado no schedule.

        Args:
            schedule_id: ID do schedule
            manual: Se é um trigger manual

        Returns:
            Dict com schedule_id, workflow_id, triggered_at
        """
        schedule = await self.get_schedule(schedule_id)

        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        if schedule.status != ScheduleStatus.ACTIVE and not manual:
            raise ValueError(f"Schedule {schedule_id} is not active")

        # Iniciar workflow Temporal
        workflow_id = f"{schedule.workflow}-{schedule_id}-{datetime.now(UTC).timestamp()}"

        try:
            handle = await self.temporal_client.start_workflow(
                schedule.workflow,
                id=workflow_id,
                task_queue=self.temporal_task_queue,
                args=schedule.trigger.parameters or {},
            )

            # Atualizar última execução
            await self._update_schedule_last_run(schedule_id, datetime.now(UTC))

            # Registrar execução
            execution = ScheduleExecution(
                schedule_id=schedule_id,
                workflow_id=handle.id,
                started_at=datetime.now(UTC),
                status="running",
            )
            await self._save_execution(execution)

            self.logger.info(
                "workflow_triggered",
                schedule_id=schedule_id,
                workflow_id=handle.id,
                manual=manual,
            )

            return {
                "schedule_id": schedule_id,
                "workflow_id": handle.id,
                "triggered_at": datetime.now(UTC).isoformat(),
                "manual": manual,
            }

        except Exception as e:
            # Atualizar contador de falhas
            await self._increment_failure_count(schedule_id)

            self.logger.error("workflow_trigger_failed", schedule_id=schedule_id, error=str(e))
            raise

    async def pause_schedule(self, schedule_id: str) -> dict[str, Any]:
        """
        Pausa schedule.

        Args:
            schedule_id: ID do schedule

        Returns:
            Status atualizado
        """
        await self._update_schedule_status(schedule_id, ScheduleStatus.PAUSED)

        # Parar task de cron se existir
        if schedule_id in self._running_schedules:
            task = self._running_schedules.pop(schedule_id)
            task.cancel()

        return {"schedule_id": schedule_id, "status": "paused"}

    async def resume_schedule(self, schedule_id: str) -> dict[str, Any]:
        """
        Retoma schedule pausado.

        Args:
            schedule_id: ID do schedule

        Returns:
            Status atualizado
        """
        schedule = await self.get_schedule(schedule_id)

        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        await self._update_schedule_status(schedule_id, ScheduleStatus.ACTIVE)

        # Reiniciar task de cron se aplicável
        if schedule.schedule_type == ScheduleType.CRON:
            await self._start_cron_schedule(schedule)

        return {"schedule_id": schedule_id, "status": "active"}

    async def delete_schedule(self, schedule_id: str) -> dict[str, Any]:
        """
        Deleta schedule.

        Args:
            schedule_id: ID do schedule

        Returns:
            Confirmação
        """
        # Parar task de cron se existir
        if schedule_id in self._running_schedules:
            task = self._running_schedules.pop(schedule_id)
            task.cancel()

        # Deletar do banco
        query = "DELETE FROM schedules WHERE schedule_id = $1"
        await self.postgresql_client.execute(query, schedule_id)

        self.logger.info("schedule_deleted", schedule_id=schedule_id)

        return {"schedule_id": schedule_id, "deleted": True}

    async def _start_cron_schedule(self, schedule: Schedule) -> None:
        """Inicia task assíncrona para schedule cron."""
        if schedule.schedule_id in self._running_schedules:
            return

        async def cron_worker():
            while True:
                try:
                    # Aguardar até próxima execução
                    now = datetime.now(UTC)
                    next_run = schedule.next_run_at

                    if next_run and next_run > now:
                        sleep_seconds = (next_run - now).total_seconds()
                        await asyncio.sleep(sleep_seconds)

                    # Verificar se schedule ainda está ativo
                    current = await self.get_schedule(schedule.schedule_id)
                    if not current or current.status != ScheduleStatus.ACTIVE:
                        break

                    # Disparar workflow
                    await self.trigger_workflow(schedule.schedule_id)

                    # Calcular próxima execução
                    if schedule.trigger.cron_expression:
                        next_run = self._calculate_next_run(schedule.trigger.cron_expression)
                        await self._update_next_run(schedule.schedule_id, next_run)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(
                        "cron_worker_error",
                        schedule_id=schedule.schedule_id,
                        error=str(e),
                    )
                    await asyncio.sleep(60)  # Esperar 1min antes de retry

        task = asyncio.create_task(cron_worker())
        self._running_schedules[schedule.schedule_id] = task

    def _calculate_next_run(self, cron_expression: str) -> datetime:
        """
        Calcula próxima execução baseado em expressão cron.

        Args:
            cron_expression: Expressão cron (5 partes)

        Returns:
            Datetime da próxima execução
        """
        # Implementação simplificada - em produção usar biblioteca como croniter
        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {cron_expression}")

        minute, hour, day, month, dow = parts

        now = datetime.now(UTC)
        next_run = now.replace(second=0, microsecond=0)

        # Lógica simplificada para alguns padrões comuns
        if minute == "*" and hour == "*":
            # A cada minuto
            next_run = next_run + timedelta(minutes=1)
        elif minute == "0" and hour == "*":
            # Hora em hora
            next_run = next_run + timedelta(hours=1)
        elif minute == "0" and hour == "0":
            # Diário à meia-noite
            next_run = next_run + timedelta(days=1)
            next_run = next_run.replace(hour=0, minute=0)
        elif minute == "0" and hour == "2" and dow == "0":
            # Semanal (domingo às 2h)
            days_ahead = 6 - next_run.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_run = next_run + timedelta(days=days_ahead)
            next_run = next_run.replace(hour=2, minute=0)
        else:
            # Default: próxima hora
            next_run = next_run + timedelta(hours=1)

        return next_run

    async def _save_schedule(self, schedule: Schedule) -> None:
        """Salva schedule no banco."""
        query = """
            INSERT INTO schedules (
                schedule_id, workflow, schedule_type, trigger_data, priority,
                status, created_at, updated_at, last_run_at, next_run_at,
                total_runs, failure_count, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (schedule_id) DO UPDATE SET
                workflow = EXCLUDED.workflow,
                trigger_data = EXCLUDED.trigger_data,
                priority = EXCLUDED.priority,
                status = EXCLUDED.status,
                updated_at = EXCLUDED.updated_at,
                last_run_at = EXCLUDED.last_run_at,
                next_run_at = EXCLUDED.next_run_at,
                total_runs = EXCLUDED.total_runs,
                failure_count = EXCLUDED.failure_count,
                metadata = EXCLUDED.metadata
        """
        await self.postgresql_client.execute(
            query,
            schedule.schedule_id,
            schedule.workflow,
            schedule.schedule_type.value,
            schedule.trigger.model_dump_json(),
            schedule.priority.value,
            schedule.status.value,
            schedule.created_at,
            schedule.updated_at,
            schedule.last_run_at,
            schedule.next_run_at,
            schedule.total_runs,
            schedule.failure_count,
            schedule.metadata,
        )

    async def _save_execution(self, execution: ScheduleExecution) -> None:
        """Salva execução no banco."""
        query = """
            INSERT INTO schedule_executions (
                execution_id, schedule_id, workflow_id, started_at,
                completed_at, status, error_message, output
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """
        await self.postgresql_client.execute(
            query,
            execution.execution_id,
            execution.schedule_id,
            execution.workflow_id,
            execution.started_at,
            execution.completed_at,
            execution.status,
            execution.error_message,
            execution.output,
        )

    async def _update_schedule_status(self, schedule_id: str, status: ScheduleStatus) -> None:
        """Atualiza status do schedule."""
        query = """
            UPDATE schedules SET status = $1, updated_at = $2
            WHERE schedule_id = $3
        """
        await self.postgresql_client.execute(query, status.value, datetime.now(UTC), schedule_id)

    async def _update_schedule_last_run(self, schedule_id: str, last_run: datetime) -> None:
        """Atualiza última execução do schedule."""
        query = """
            UPDATE schedules
            SET last_run_at = $1, updated_at = $2, total_runs = total_runs + 1
            WHERE schedule_id = $3
        """
        await self.postgresql_client.execute(query, last_run, datetime.now(UTC), schedule_id)

    async def _update_next_run(self, schedule_id: str, next_run: datetime) -> None:
        """Atualiza próxima execução do schedule."""
        query = """
            UPDATE schedules SET next_run_at = $1, updated_at = $2
            WHERE schedule_id = $3
        """
        await self.postgresql_client.execute(query, next_run, datetime.now(UTC), schedule_id)

    async def _increment_failure_count(self, schedule_id: str) -> None:
        """Incrementa contador de falhas."""
        query = """
            UPDATE schedules
            SET failure_count = failure_count + 1, updated_at = $1
            WHERE schedule_id = $2
        """
        await self.postgresql_client.execute(query, datetime.now(UTC), schedule_id)

    def _row_to_schedule(self, row) -> Schedule:
        """Converte linha do banco para modelo Schedule."""
        from json import loads

        return Schedule(
            schedule_id=row["schedule_id"],
            workflow=row["workflow"],
            schedule_type=ScheduleType(row["schedule_type"]),
            trigger=ScheduleTrigger.model_validate_json(row["trigger_data"]),
            priority=SchedulePriority(row["priority"]),
            status=ScheduleStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_run_at=row["last_run_at"],
            next_run_at=row["next_run_at"],
            total_runs=row["total_runs"],
            failure_count=row["failure_count"],
            metadata=loads(row["metadata"]) if row["metadata"] else {},
        )

    async def list_schedule_executions(
        self, schedule_id: str, limit: int = 50, offset: int = 0
    ) -> list[ScheduleExecution]:
        """
        Lista execuções de um schedule específico.

        Args:
            schedule_id: ID do schedule
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de execuções
        """
        query = """
            SELECT execution_id, schedule_id, workflow_id, started_at,
                   completed_at, status, error_message, output
            FROM schedule_executions
            WHERE schedule_id = $1
            ORDER BY started_at DESC
            LIMIT $2 OFFSET $3
        """
        rows = await self.postgresql_client.fetch_all(query, schedule_id, limit, offset)

        return [
            ScheduleExecution(
                execution_id=row["execution_id"],
                schedule_id=row["schedule_id"],
                workflow_id=row["workflow_id"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                status=row["status"],
                error_message=row["error_message"],
                output=row["output"],
            )
            for row in rows
        ]

    async def shutdown(self) -> None:
        """Para todas as tasks de schedule."""
        for schedule_id, task in self._running_schedules.items():
            task.cancel()
            self.logger.info("schedule_task_stopped", schedule_id=schedule_id)

        self._running_schedules.clear()
