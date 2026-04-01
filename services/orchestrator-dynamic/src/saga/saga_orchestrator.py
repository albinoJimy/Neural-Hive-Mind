"""
Orchestrator de Saga para coordenacao de transaccoes distribuidas.

Implementa a logica de coordenacao de Sagas com execucao sequencial
de steps e compensacao automatica em caso de falha.
"""
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from .saga_event_store import SagaEventStore, SagaEventType
from .saga_repository import SagaRepository
from .saga_state import SagaConcurrentModificationError, SagaState, SagaStatus, SagaStep, StepStatus

logger = structlog.get_logger()


class SagaOrchestrator:
    """
    Coordenador de Saga para transaccoes distribuidas.

    Gerencia o ciclo de vida de Sagas, incluindo criacao, execucao,
    tratamento de falhas e compensacao automatica.
    """

    def __init__(self, repository: SagaRepository, event_store: SagaEventStore):
        """
        Inicializa o orchestrator.

        Args:
            repository: Repository para persistencia de estado
            event_store: Event store para eventos de Saga
        """
        self._repository = repository
        self._event_store = event_store

    async def create_saga(
        self,
        workflow_id: str,
        plan_id: str,
        intent_id: str,
        steps: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> SagaState:
        """
        Cria uma nova Saga com steps definidos.

        Args:
            workflow_id: ID do workflow Temporal
            plan_id: ID do Cognitive Plan
            intent_id: ID da intencao original
            steps: Lista de definicoes de steps
            metadata: Metadados adicionais

        Returns:
            Nova instancia de SagaState criada
        """
        saga_id = str(uuid4())
        now = int(datetime.now(UTC).timestamp() * 1000)

        # Converter definicoes de steps para objetos SagaStep
        saga_steps = []
        for step_def in steps:
            step = SagaStep(
                step_id=str(uuid4()),
                name=step_def.get("name", "unnamed_step"),
                action=step_def.get("action", ""),
                compensation_action=step_def.get("compensation_action", ""),
                parameters=step_def.get("parameters", {}),
                compensation_parameters=step_def.get("compensation_parameters", {}),
                max_retries=step_def.get("max_retries", 3),
                created_at=now,
            )
            saga_steps.append(step)

        # Criar ordem de compensacao (ordem reversa)
        compensation_order = [step.step_id for step in reversed(saga_steps)]

        saga = SagaState(
            saga_id=saga_id,
            workflow_id=workflow_id,
            plan_id=plan_id,
            intent_id=intent_id,
            status=SagaStatus.PENDING,
            steps=saga_steps,
            compensation_order=compensation_order,
            created_at=now,
            current_step_index=0,
            metadata=metadata or {},
        )

        # Persistir saga
        await self._repository.save(saga)

        # Registrar evento de criacao
        await self._event_store.record_event_raw(
            saga_id=saga_id,
            event_type=SagaEventType.saga_created,
            data={
                "workflow_id": workflow_id,
                "plan_id": plan_id,
                "intent_id": intent_id,
                "steps_count": len(saga_steps),
            },
        )

        logger.info(
            "saga_created",
            saga_id=saga_id,
            workflow_id=workflow_id,
            plan_id=plan_id,
            steps_count=len(saga_steps),
        )

        return saga

    async def start_saga(self, saga_id: str) -> SagaState | None:
        """
        Inicia a execucao de uma Saga.

        Marca a Saga como STARTED e inicia o primeiro step.

        Args:
            saga_id: ID da Saga

        Returns:
            Estado atualizado da Saga ou None se nao encontrada
        """
        saga = await self._repository.find_by_id(saga_id)
        if not saga:
            logger.warning("saga_not_found", saga_id=saga_id)
            return None

        if saga.status != SagaStatus.PENDING:
            logger.warning("saga_already_started", saga_id=saga_id, current_status=str(saga.status))
            return saga

        # Atualizar status
        saga.status = SagaStatus.STARTED
        saga.started_at = int(datetime.now(UTC).timestamp() * 1000)

        await self._repository.save(saga)

        # Registrar evento
        await self._event_store.record_event_raw(
            saga_id=saga_id, event_type=SagaEventType.saga_started
        )

        logger.info("saga_started", saga_id=saga_id, steps_count=len(saga.steps))

        return saga

    async def complete_step(
        self, saga_id: str, step_id: str, result: dict[str, Any] | None = None
    ) -> SagaState | None:
        """
        Marca um step como completado e avanca para o proximo.

        Args:
            saga_id: ID da Saga
            step_id: ID do step completado
            result: Resultado da execucao do step

        Returns:
            Estado atualizado da Saga ou None se erro
        """
        saga = await self._repository.find_by_id(saga_id)
        if not saga:
            logger.warning("saga_not_found", saga_id=saga_id)
            return None

        # Encontrar o step
        step = None
        step_index = -1
        for i, s in enumerate(saga.steps):
            if s.step_id == step_id:
                step = s
                step_index = i
                break

        if not step:
            logger.warning("step_not_found_in_saga", saga_id=saga_id, step_id=step_id)
            return None

        # Marcar step como completado
        step.mark_completed(result)

        # Registrar evento do step
        await self._event_store.record_event_raw(
            saga_id=saga_id,
            event_type=SagaEventType.saga_step_completed,
            data={"step_id": step_id, "step_name": step.name, "step_index": step_index},
        )

        # Avancar para proximo step
        next_index = step_index + 1
        if next_index < len(saga.steps):
            # Ainda ha steps a executar
            saga.status = SagaStatus.IN_PROGRESS
            saga.current_step_index = next_index

            logger.info(
                "saga_step_completed_next_pending",
                saga_id=saga_id,
                step_id=step_id,
                next_step_index=next_index,
            )
        else:
            # Todos os steps foram completados
            saga.status = SagaStatus.COMPLETED
            saga.completed_at = int(datetime.now(UTC).timestamp() * 1000)

            await self._event_store.record_event_raw(
                saga_id=saga_id,
                event_type=SagaEventType.saga_completed,
                data={"steps_completed": len(saga.steps)},
            )

            logger.info(
                "saga_completed_all_steps", saga_id=saga_id, steps_completed=len(saga.steps)
            )

        await self._repository.save(saga)
        return saga

    async def fail_step(
        self, saga_id: str, step_id: str, error: str, trigger_compensation: bool = True
    ) -> SagaState | None:
        """
        Marca um step como falhado e inicia compensacao.

        Args:
            saga_id: ID da Saga
            step_id: ID do step que falhou
            error: Mensagem de erro
            trigger_compensation: Se True, inicia compensacao automatica

        Returns:
            Estado atualizado da Saga ou None se erro
        """
        saga = await self._repository.find_by_id(saga_id)
        if not saga:
            logger.warning("saga_not_found", saga_id=saga_id)
            return None

        # Encontrar o step
        step = None
        for s in saga.steps:
            if s.step_id == step_id:
                step = s
                break

        if not step:
            logger.warning("step_not_found_in_saga", saga_id=saga_id, step_id=step_id)
            return None

        # Marcar step como falhado
        step.mark_failed(error)

        # Registrar evento de falha
        await self._event_store.record_event_raw(
            saga_id=saga_id,
            event_type=SagaEventType.saga_step_failed,
            data={"step_id": step_id, "step_name": step.name, "error": error},
        )

        logger.info("saga_step_failed", saga_id=saga_id, step_id=step_id, error=error)

        # Verificar se pode compensar
        if trigger_compensation:
            completed_steps = saga.get_completed_steps()
            if completed_steps:
                # Iniciar compensacao
                saga.status = SagaStatus.COMPENSATING
                saga.error = error

                await self._event_store.record_event_raw(
                    saga_id=saga_id,
                    event_type=SagaEventType.saga_compensating,
                    data={"trigger_step_id": step_id, "steps_to_compensate": len(completed_steps)},
                )

                logger.info(
                    "saga_compensation_started",
                    saga_id=saga_id,
                    steps_to_compensate=len(completed_steps),
                )
            else:
                # Sem steps para compensar - falha direta
                saga.status = SagaStatus.FAILED
                saga.failed_at = int(datetime.now(UTC).timestamp() * 1000)
                saga.error = error

                await self._event_store.record_event_raw(
                    saga_id=saga_id, event_type=SagaEventType.saga_failed, data={"error": error}
                )

                logger.info("saga_failed_no_compensation", saga_id=saga_id, error=error)

        await self._repository.save(saga)
        return saga

    async def compensate_step(
        self, saga_id: str, step_id: str, compensation_result: dict[str, Any] | None = None
    ) -> SagaState | None:
        """
        Marca um step como compensado.

        Args:
            saga_id: ID da Saga
            step_id: ID do step compensado
            compensation_result: Resultado da compensacao

        Returns:
            Estado atualizado da Saga ou None se erro
        """
        saga = await self._repository.find_by_id(saga_id)
        if not saga:
            logger.warning("saga_not_found", saga_id=saga_id)
            return None

        # Encontrar o step
        step = None
        for s in saga.steps:
            if s.step_id == step_id:
                step = s
                break

        if not step:
            logger.warning("step_not_found_in_saga", saga_id=saga_id, step_id=step_id)
            return None

        # Marcar step como compensado
        step.mark_compensated(compensation_result)

        # Registrar evento
        await self._event_store.record_event_raw(
            saga_id=saga_id,
            event_type=SagaEventType.saga_step_compensated,
            data={"step_id": step_id, "step_name": step.name},
        )

        logger.info("saga_step_compensated", saga_id=saga_id, step_id=step_id)

        # Verificar se todos os steps completados foram compensados
        completed_steps = saga.get_completed_steps()
        compensated_steps = [s for s in saga.steps if s.status == StepStatus.COMPENSATED]

        # Steps completados que ainda nao foram compensados
        pending_compensation = [s for s in completed_steps if s.status != StepStatus.COMPENSATED]

        if not pending_compensation:
            # Todos os steps foram compensados
            saga.status = SagaStatus.COMPENSATED
            saga.compensated_at = int(datetime.now(UTC).timestamp() * 1000)

            await self._event_store.record_event_raw(
                saga_id=saga_id,
                event_type=SagaEventType.saga_compensated,
                data={"steps_compensated": len(compensated_steps)},
            )

            logger.info(
                "saga_compensation_completed",
                saga_id=saga_id,
                steps_compensated=len(compensated_steps),
            )

        await self._repository.save(saga)
        return saga

    async def get_saga_state(self, saga_id: str) -> SagaState | None:
        """
        Retorna o estado atual de uma Saga.

        Args:
            saga_id: ID da Saga

        Returns:
            Estado da Saga ou None se nao encontrada
        """
        return await self._repository.find_by_id(saga_id)

    async def get_current_step(self, saga_id: str) -> SagaStep | None:
        """
        Retorna o step atual sendo executado.

        Args:
            saga_id: ID da Saga

        Returns:
            Step atual ou None
        """
        saga = await self._repository.find_by_id(saga_id)
        if not saga:
            return None
        return saga.get_current_step()

    async def get_compensation_order(self, saga_id: str) -> list[SagaStep]:
        """
        Retorna a ordem de compensacao para uma Saga.

        Args:
            saga_id: ID da Saga

        Returns:
            Lista de steps na ordem de compensacao
        """
        saga = await self._repository.find_by_id(saga_id)
        if not saga:
            return []
        return saga.get_compensation_order()

    async def retry_saga(self, saga_id: str) -> SagaState | None:
        """
        Prepara uma Saga falhada para nova tentativa.

        Args:
            saga_id: ID da Saga

        Returns:
            Estado resetado da Saga ou None

        Raises:
            SagaConcurrentModificationError: Se a Saga foi modificada
                por outro processo desde a leitura
        """
        saga = await self._repository.find_by_id(saga_id)
        if not saga:
            logger.warning("saga_not_found", saga_id=saga_id)
            return None

        if not saga.can_retry():
            logger.warning(
                "saga_cannot_retry_max_reached",
                saga_id=saga_id,
                retry_count=saga.retry_count,
                max_retries=saga.max_retries,
            )
            return None

        # Incrementar contador e resetar
        saga.increment_retry()
        saga.reset_for_retry()

        try:
            await self._repository.save(saga)
        except SagaConcurrentModificationError:
            logger.warning(
                "saga_retry_failed_concurrent_modification",
                saga_id=saga_id,
                retry_count=saga.retry_count,
            )
            raise

        logger.info("saga_reset_for_retry", saga_id=saga_id, retry_count=saga.retry_count)

        return saga
