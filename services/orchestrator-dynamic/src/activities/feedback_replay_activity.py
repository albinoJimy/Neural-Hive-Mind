"""
Activity Temporal para Feedback-Driven Replay.

Integra com feedback_replay_service para gerenciar workflows
que falharam devido a modelos ML e disparam replay automático.
"""

from datetime import datetime, timezone
from typing import Any

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from src.services.feedback_replay_service import (
    FeedbackReplayService,
    ReplayPriority,
)

logger = structlog.get_logger(__name__)


def _now_iso() -> str:
    """Retorna timestamp atual em ISO format."""
    return datetime.now(timezone.utc).isoformat()


# Serviço de feedback replay (singleton)
_feedback_replay_service: FeedbackReplayService | None = None


def get_feedback_replay_service() -> FeedbackReplayService:
    """Retorna o serviço de feedback replay (singleton)."""
    global _feedback_replay_service
    if _feedback_replay_service is None:
        _feedback_replay_service = FeedbackReplayService()
    return _feedback_replay_service


@activity.defn
async def register_failed_workflow_for_replay(
    workflow_id: str,
    run_id: str,
    failure_reason: str,
    model_version: str,
    plan_id: str | None = None,
    priority: str = "medium",
    estimated_impact: float = 0.0,
    context: dict | None = None,
) -> dict[str, Any]:
    """
    Registra um workflow que falhou devido a modelo ML.

    Args:
        workflow_id: ID do workflow
        run_id: ID da execução
        failure_reason: Razão da falha
        model_version: Versão do modelo quando falhou
        plan_id: ID do plano (opcional)
        priority: Prioridade do replay (critical/high/medium/low)
        estimated_impact: Impacto estimado (0-1)
        context: Contexto adicional

    Returns:
        Dict com status do registro
    """
    logger.info(
        "registering_failed_workflow_for_replay",
        workflow_id=workflow_id,
        run_id=run_id,
        failure_reason=failure_reason,
        model_version=model_version,
    )

    service = get_feedback_replay_service()

    # Converter string para enum
    try:
        priority_enum = ReplayPriority(priority.lower())
    except ValueError:
        priority_enum = ReplayPriority.MEDIUM

    result = await service.register_failed_workflow(
        workflow_id=workflow_id,
        run_id=run_id,
        failure_reason=failure_reason,
        model_version=model_version,
        plan_id=plan_id,
        priority=priority_enum,
        estimated_impact=estimated_impact,
        context=context,
    )

    return result


@activity.defn
async def check_model_improvement(
    old_model_version: str,
    new_model_version: str,
    metrics_old: dict[str, float],
    metrics_new: dict[str, float],
) -> dict[str, Any]:
    """
    Verifica se o novo modelo é significativamente melhor.

    Args:
        old_model_version: Versão do modelo antigo
        new_model_version: Versão do novo modelo
        metrics_old: Métricas do modelo antigo
        metrics_new: Métricas do novo modelo

    Returns:
        Dict com nível de melhoria
    """
    logger.info(
        "checking_model_improvement",
        old_model_version=old_model_version,
        new_model_version=new_model_version,
    )

    service = get_feedback_replay_service()

    improvement = await service.check_model_improvement(
        old_model_version, new_model_version, metrics_old, metrics_new
    )

    return {
        "improvement_level": improvement.value,
        "old_version": old_model_version,
        "new_version": new_model_version,
        "assessed_at": _now_iso(),
    }


@activity.defn
async def on_model_updated_trigger_replay(
    new_model_version: str,
    metrics_old: dict[str, float],
    metrics_new: dict[str, float],
    max_concurrent: int = 10,
) -> dict[str, Any]:
    """
    Callback quando modelo é retreinado. Dispara replay se necessário.

    Args:
        new_model_version: Nova versão do modelo
        metrics_old: Métricas do modelo antigo
        metrics_new: Métricas do novo modelo
        max_concurrent: Máximo de replays simultâneos

    Returns:
        Dict com workflows agendados para replay
    """
    logger.info(
        "on_model_updated_trigger_replay",
        new_model_version=new_model_version,
        pending_replays_count=len(get_feedback_replay_service()._pending_replays),
    )

    service = get_feedback_replay_service()

    result = await service.on_model_updated(
        new_model_version=new_model_version,
        metrics_old=metrics_old,
        metrics_new=metrics_new,
    )

    logger.info(
        "model_replay_trigger_complete",
        status=result.get("status"),
        scheduled_count=result.get("scheduled_count", 0),
    )

    return result


@activity.defn
async def schedule_workflow_replay(
    workflow_id: str,
    original_run_id: str,
    new_model_version: str,
    corrected_inputs: dict | None = None,
) -> dict[str, Any]:
    """
    Agenda um workflow para replay com novo modelo.

    Args:
        workflow_id: ID do workflow original
        original_run_id: ID da execução original
        new_model_version: Versão do novo modelo
        corrected_inputs: Inputs corrigidos (opcional)

    Returns:
        Dict com ID da nova execução
    """
    logger.info(
        "scheduling_workflow_replay",
        workflow_id=workflow_id,
        new_model_version=new_model_version,
    )

    service = get_feedback_replay_service()

    # Buscar pending replay
    pending = service._pending_replays.get(workflow_id)
    if not pending:
        raise ApplicationError(
            f"Workflow {workflow_id} not found in pending replays",
            non_retryable=True,
        )

    # Agendar replay
    result = await service._schedule_replay(pending, new_model_version)

    # Em produção, isso chamaria Temporal para executar o replay
    # Por ora, retornar mock
    result["new_run_id"] = f"{workflow_id}-replay-{new_model_version}"

    return result


@activity.defn
async def record_replay_result(
    workflow_id: str,
    replay_id: str,
    success: bool,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Registra resultado de um replay.

    Args:
        workflow_id: ID do workflow
        replay_id: ID do replay
        success: Se foi bem-sucedido
        result: Resultado do replay

    Returns:
        Dict com status
    """
    logger.info(
        "recording_replay_result",
        workflow_id=workflow_id,
        replay_id=replay_id,
        success=success,
    )

    service = get_feedback_replay_service()

    record_result = await service.record_replay_result(
        workflow_id=workflow_id,
        replay_id=replay_id,
        success=success,
        result=result,
    )

    logger.info(
        "replay_result_recorded",
        workflow_id=workflow_id,
        remaining_attempts=record_result.get("remaining_attempts", 0),
    )

    return record_result


@activity.defn
async def get_pending_replays(
    priority: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Retorna lista de replays pendentes.

    Args:
        priority: Filtrar por prioridade (opcional)
        limit: Limite de resultados

    Returns:
        Dict com lista de replays pendentes
    """
    logger.info(
        "getting_pending_replays",
        priority=priority,
        limit=limit,
    )

    service = get_feedback_replay_service()

    priority_enum = ReplayPriority(priority.lower()) if priority else None

    pending = service.get_pending_replays(priority=priority_enum, limit=limit)

    return {
        "count": len(pending),
        "pending": pending,
        "queried_at": _now_iso(),
    }


@activity.defn
async def get_replay_metrics() -> dict[str, Any]:
    """
    Retorna métricas do serviço de replay.

    Returns:
        Dict com métricas
    """
    service = get_feedback_replay_service()

    metrics = service.get_metrics()

    logger.info(
        "replay_metrics_collected",
        total_pending=metrics.get("queue_size"),
        total_replayed=metrics.get("total_replayed"),
        total_successful=metrics.get("total_successful"),
    )

    return {
        "metrics": metrics,
        "collected_at": _now_iso(),
    }


@activity.defn
async def check_replay_eligibility(
    workflow_id: str,
    run_id: str,
    error_message: str,
    model_version: str,
) -> dict[str, Any]:
    """
    Verifica se um workflow é elegível para replay driven por feedback.

    Args:
        workflow_id: ID do workflow
        run_id: ID da execução
        error_message: Mensagem de erro
        model_version: Versão do modelo

    Returns:
        Dict com elegibilidade
    """
    logger.info(
        "checking_replay_eligibility",
        workflow_id=workflow_id,
        error_message=error_message[:100],
    )

    # Critérios para elegibilidade
    is_model_related = any(
        keyword in error_message.lower()
        for keyword in [
            "model",
            "prediction",
            "classification",
            "confidence",
            "ml_score",
            "approval",
            "quality_score",
        ]
    )

    is_retryable = any(
        keyword in error_message.lower() for keyword in ["timeout", "temporary", "unavailable"]
    )

    has_valid_model = model_version and model_version != "unknown"

    eligible = is_model_related and has_valid_model and not is_retryable

    return {
        "eligible": eligible,
        "reason": {
            "is_model_related": is_model_related,
            "has_valid_model": has_valid_model,
            "not_retryable": not is_retryable,
        },
        "recommended_action": "register_for_replay" if eligible else "standard_retry",
    }
