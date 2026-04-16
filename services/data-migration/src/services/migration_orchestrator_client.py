"""
Cliente de Integração do Data Migration com Orchestrator Dynamic.

Fornece métodos para submeter jobs de migração ao Orchestrator Dynamic,
consultar status do workflow e enviar sinais (aprovação, pausa, rollback).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import structlog
from temporalio.client import Client

from src.models.migration import MigrationJob, SchemaMapping

logger = structlog.get_logger(__name__)

__all__ = [
    "submit_migration_job",
    "get_workflow_status",
    "signal_approve_phase",
    "signal_pause_migration",
    "signal_resume_migration",
    "signal_rollback_migration",
    "create_migration_execution_ticket",
    "update_ticket_progress",
]


# =============================================================================
# Cliente Temporal (Lazy Loading)
# =============================================================================

_temporal_client: Optional[Client] = None


async def get_temporal_client() -> Client:
    """
    Retorna cliente Temporal (singleton).

    Returns:
        Cliente Temporal conectado

    Raises:
        RuntimeError: Se Temporal não estiver configurado
    """
    global _temporal_client

    if _temporal_client is None:
        from src.config.settings import get_settings

        settings = get_settings()

        if not settings.temporal_enabled:
            raise RuntimeError("Temporal não está habilitado")

        target = f"{settings.temporal_host}:{settings.temporal_port}"

        logger.info(
            "conectando_temporal",
            target=target,
            namespace=settings.temporal_namespace,
        )

        _temporal_client = await Client.connect(
            target,
            namespace=settings.temporal_namespace,
        )

        logger.info("temporal_conectado")

    return _temporal_client


# =============================================================================
# Submissão de Job
# =============================================================================


async def submit_migration_job(
    migration_job: MigrationJob,
    schema_mapping: SchemaMapping,
    auto_approve: bool = True,
    task_queue: str = "orchestrator-task-queue",
) -> Dict[str, Any]:
    """
    Submete job de migração ao Orchestrator Dynamic.

    Cria execution ticket e inicia workflow Temporal.

    Args:
        migration_job: Job de migração
        schema_mapping: Mapeamento de schema a utilizar
        auto_approve: Se True, aprova automaticamente fases que requerem aprovação
        task_queue: Task queue Temporal

    Returns:
        Dict com:
            - success: bool
            - workflow_id: str
            - ticket_id: str (se sucesso)
            - error: str (se falhou)
    """
    try:
        logger.info(
            "submit_migration_job_started",
            job_id=migration_job.job_id,
            auto_approve=auto_approve,
        )

        # Criar execution ticket
        ticket_result = await create_migration_execution_ticket(
            migration_job=migration_job,
            task_type="MIGRATE",
        )

        if not ticket_result.get("success"):
            return {
                "success": False,
                "error": f"Falha ao criar ticket: {ticket_result.get('error')}",
            }

        ticket_id = ticket_result["ticket_id"]

        # Preparar input do workflow
        workflow_input = {
            "migration_config": {
                "job_id": migration_job.job_id,
                "schema_mapping_id": schema_mapping.legacy_connection_id,
                "legacy_connection_id": schema_mapping.legacy_connection_id,
                "target_service": schema_mapping.nhm_target,
                "batch_size": migration_job.batch_size,
                "max_parallel_migrations": migration_job.max_parallel_migrations,
                "auto_approve": auto_approve,
                "snapshot_strategy": "s3",
            },
            "job_id": migration_job.job_id,
            "initial_phase": migration_job.status.value,
            "ticket_id": ticket_id,
        }

        # Obter cliente Temporal
        client = await get_temporal_client()

        # Iniciar workflow
        workflow_id = f"data-migration-{migration_job.job_id}"

        # Não podemos importar DataMigrationWorkflow diretamente pois está no orchestrator-dynamic
        # Usamos o nome do workflow como string
        await client.start_workflow(
            "DataMigrationWorkflow.run",
            workflow_input,
            id=workflow_id,
            task_queue=task_queue,
        )

        logger.info(
            "migration_job_submitted",
            job_id=migration_job.job_id,
            workflow_id=workflow_id,
            ticket_id=ticket_id,
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "ticket_id": ticket_id,
            "job_id": migration_job.job_id,
            "status": "submitted",
        }

    except Exception as e:
        logger.exception("submit_migration_job_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Consulta de Status
# =============================================================================


async def get_workflow_status(workflow_id: str) -> Dict[str, Any]:
    """
    Consulta status do workflow de migração.

    Args:
        workflow_id: ID do workflow Temporal

    Returns:
        Dict com:
            - success: bool
            - status: str
            - current_phase: str
            - progress: dict
            - error: str (se falhou)
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)

        # Query status do workflow - usa nome da query como string
        # DataMigrationWorkflow.get_status é uma query definida no workflow
        status = await handle.query("get_status")

        logger.info(
            "workflow_status_queried",
            workflow_id=workflow_id,
            status=status.get("status"),
            phase=status.get("current_phase"),
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            **status,
        }

    except Exception as e:
        logger.exception("get_workflow_status_failed", workflow_id=workflow_id)
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Sinais
# =============================================================================


async def signal_approve_phase(
    workflow_id: str,
    approved_by: str = "unknown",
) -> Dict[str, Any]:
    """
    Envia sinal de aprovação para o workflow.

    Args:
        workflow_id: ID do workflow Temporal
        approved_by: Usuário ou serviço aprovando

    Returns:
        Dict com:
            - success: bool
            - error: str (se falhou)
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)

        # Usa nome do signal como string
        await handle.signal("approve_mapping", approved_by)

        logger.info(
            "approval_signal_sent",
            workflow_id=workflow_id,
            approved_by=approved_by,
        )

        return {
            "success": True,
            "message": "Sinal de aprovação enviado",
        }

    except Exception as e:
        logger.exception("signal_approve_phase_failed", workflow_id=workflow_id)
        return {
            "success": False,
            "error": str(e),
        }


async def signal_pause_migration(workflow_id: str) -> Dict[str, Any]:
    """
    Envia sinal de pausa para o workflow.

    Args:
        workflow_id: ID do workflow Temporal

    Returns:
        Dict com:
            - success: bool
            - error: str (se falhou)
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)

        # Usa nome do signal como string
        await handle.signal("pause_migration")

        logger.info("pause_signal_sent", workflow_id=workflow_id)

        return {
            "success": True,
            "message": "Sinal de pausa enviado",
        }

    except Exception as e:
        logger.exception("signal_pause_migration_failed", workflow_id=workflow_id)
        return {
            "success": False,
            "error": str(e),
        }


async def signal_resume_migration(workflow_id: str) -> Dict[str, Any]:
    """
    Envia sinal de retomada para o workflow.

    Args:
        workflow_id: ID do workflow Temporal

    Returns:
        Dict com:
            - success: bool
            - error: str (se falhou)
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)

        # Usa nome do signal como string
        await handle.signal("resume_migration")

        logger.info("resume_signal_sent", workflow_id=workflow_id)

        return {
            "success": True,
            "message": "Sinal de retomada enviado",
        }

    except Exception as e:
        logger.exception("signal_resume_migration_failed", workflow_id=workflow_id)
        return {
            "success": False,
            "error": str(e),
        }


async def signal_rollback_migration(
    workflow_id: str,
    reason: str = "Manual rollback requested",
) -> Dict[str, Any]:
    """
    Envia sinal de rollback para o workflow.

    Args:
        workflow_id: ID do workflow Temporal
        reason: Motivo do rollback

    Returns:
        Dict com:
            - success: bool
            - error: str (se falhou)
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)

        # Usa nome do signal como string
        await handle.signal("trigger_rollback", reason)

        logger.warning(
            "rollback_signal_sent",
            workflow_id=workflow_id,
            reason=reason,
        )

        return {
            "success": True,
            "message": "Sinal de rollback enviado",
        }

    except Exception as e:
        logger.exception("signal_rollback_migration_failed", workflow_id=workflow_id)
        return {
            "success": False,
            "error": str(e),
        }


async def signal_update_progress(
    workflow_id: str,
    rows_migrated: int,
    total_rows: int,
) -> Dict[str, Any]:
    """
    Envia sinal de atualização de progresso para o workflow.

    Args:
        workflow_id: ID do workflow Temporal
        rows_migrated: Linhas migradas
        total_rows: Total de linhas

    Returns:
        Dict com:
            - success: bool
            - error: str (se falhou)
    """
    try:
        client = await get_temporal_client()
        handle = client.get_workflow_handle(workflow_id)

        # Usa nome do signal como string
        await handle.signal("update_progress", rows_migrated, total_rows)

        logger.info(
            "progress_update_signal_sent",
            workflow_id=workflow_id,
            rows_migrated=rows_migrated,
            total_rows=total_rows,
        )

        return {
            "success": True,
            "message": "Sinal de atualização de progresso enviado",
        }

    except Exception as e:
        logger.exception("signal_update_progress_failed", workflow_id=workflow_id)
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Execution Tickets
# =============================================================================


async def create_migration_execution_ticket(
    migration_job: MigrationJob,
    task_type: str = "MIGRATE",
) -> Dict[str, Any]:
    """
    Cria execution ticket para job de migração.

    Args:
        migration_job: Job de migração
        task_type: Tipo da tarefa

    Returns:
        Dict com:
            - success: bool
            - ticket_id: str
            - error: str (se falhou)
    """
    try:
        from src.models.migration import MigrationStatus

        # Calcular deadline (24 horas a partir de agora)
        now = datetime.now(timezone.utc)
        deadline = int((now + timedelta(hours=24)).timestamp() * 1000)

        # Calcular prioridade baseado no tamanho
        total_rows = migration_job.total_rows or 0
        if total_rows > 1000000:
            priority = "HIGH"
        elif total_rows > 100000:
            priority = "NORMAL"
        else:
            priority = "LOW"

        # Criar ticket
        ticket = {
            "ticket_id": f"ticket-{migration_job.job_id[:8]}-{uuid.uuid4().hex[:8]}",
            "plan_id": f"plan-migration-{migration_job.job_id}",
            "intent_id": f"intent-migration-{migration_job.job_id}",
            "decision_id": f"decision-migration-{migration_job.job_id}",
            "task_id": migration_job.job_id,
            "task_type": task_type,
            "description": f"Data migration job {migration_job.job_id}",
            "status": MigrationStatus.PENDING.value,
            "priority": priority,
            "risk_band": "medium",
            "sla": {
                "deadline": deadline,
                "timeout_ms": 86400000,  # 24 horas
                "max_retries": 3,
            },
            "qos": {
                "delivery_mode": "AT_LEAST_ONCE",
                "consistency": "EVENTUAL",
                "durability": "PERSISTENT",
            },
            "parameters": {
                "job_id": migration_job.job_id,
                "schema_mapping_id": migration_job.schema_mapping_id,
                "batch_size": migration_job.batch_size,
            },
            "required_capabilities": ["postgres", "mongodb", "kafka"],
            "security_level": "INTERNAL",
            "created_at": int(now.timestamp() * 1000),
            "estimated_duration_ms": (
                migration_job.calculate_eta().total_seconds() * 1000
                if migration_job.calculate_eta()
                else None
            ),
            "metadata": {
                "service": "data-migration",
                "job_type": "migration",
            },
        }

        # Na implementação real, persistir no MongoDB
        # Por ora, retornar o ticket criado

        logger.info(
            "migration_ticket_created",
            ticket_id=ticket["ticket_id"],
            job_id=migration_job.job_id,
        )

        return {
            "success": True,
            "ticket_id": ticket["ticket_id"],
            "ticket": ticket,
        }

    except Exception as e:
        logger.exception("create_migration_execution_ticket_failed")
        return {
            "success": False,
            "error": str(e),
        }


async def update_ticket_progress(
    ticket_id: str,
    rows_migrated: int,
    total_rows: int,
) -> Dict[str, Any]:
    """
    Atualiza progresso do ticket de execução.

    Args:
        ticket_id: ID do ticket
        rows_migrated: Linhas migradas
        total_rows: Total de linhas

    Returns:
        Dict com:
            - success: bool
            - progress_percentage: float
            - error: str (se falhou)
    """
    try:
        progress_percentage = (rows_migrated / total_rows * 100.0) if total_rows > 0 else 0.0

        # Na implementação real, atualizar no MongoDB
        # Por ora, apenas log

        logger.info(
            "ticket_progress_updated",
            ticket_id=ticket_id,
            rows_migrated=rows_migrated,
            total_rows=total_rows,
            progress_percentage=progress_percentage,
        )

        return {
            "success": True,
            "ticket_id": ticket_id,
            "rows_migrated": rows_migrated,
            "total_rows": total_rows,
            "progress_percentage": progress_percentage,
        }

    except Exception as e:
        logger.exception("update_ticket_progress_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Utilitários
# =============================================================================


async def close_temporal_client():
    """Fecha conexão com Temporal."""
    global _temporal_client

    if _temporal_client is not None:
        logger.info("fechando_cliente_temporal")
        # Temporal client não tem método close explícito
        # Apenas limpamos a referência
        _temporal_client = None
