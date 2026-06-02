"""
Activity Temporal para Self-Healing e Replay de Workflows.
"""

from typing import Any

import structlog
from temporalio import activity
from temporalio.exceptions import ApplicationError

from src.services.self_healing_service import (
    CorrectionAction,
    CorrectionStrategy,
    FailureType,
    SelfHealingService,
    WorkflowFailure,
)

logger = structlog.get_logger(__name__)

# Serviço de self-healing (singleton)
_self_healing_service: SelfHealingService | None = None


def get_self_healing_service() -> SelfHealingService:
    """Retorna o serviço de self-healing (singleton)."""
    global _self_healing_service
    if _self_healing_service is None:
        _self_healing_service = SelfHealingService()
    return _self_healing_service


@activity.defn
async def analyze_failure(
    workflow_id: str,
    run_id: str,
    error_message: str,
    error_type: str,
    activity_name: str | None = None,
    context: dict | None = None,
) -> dict[str, Any]:
    """
    Analisa uma falha e determina seu tipo.

    Args:
        workflow_id: ID do workflow
        run_id: ID da execução
        error_message: Mensagem de erro
        error_type: Tipo do erro
        activity_name: Nome da activity que falhou
        context: Contexto adicional

    Returns:
        Dict com análise da falha
    """
    logger.info(
        "analyzing_failure_activity",
        workflow_id=workflow_id,
        run_id=run_id,
        activity_name=activity_name,
    )

    service = get_self_healing_service()

    # Criar exceção simulada para análise
    class SimulatedError(Exception):
        pass

    error = SimulatedError(error_message)

    failure = await service.analyze_failure(
        workflow_id=workflow_id,
        run_id=run_id,
        error=error,
        activity_name=activity_name,
        context=context,
    )

    return failure.to_dict()


@activity.defn
async def suggest_correction(
    workflow_id: str,
    run_id: str,
    failure_type: str,
    activity_name: str | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    """
    Sugere uma correção para a falha.

    Args:
        workflow_id: ID do workflow
        run_id: ID da execução
        failure_type: Tipo da falha
        activity_name: Nome da activity
        retry_count: Número de tentativas já realizadas

    Returns:
        Dict com correção sugerida
    """
    logger.info(
        "suggesting_correction_activity",
        workflow_id=workflow_id,
        failure_type=failure_type,
        retry_count=retry_count,
    )

    service = get_self_healing_service()

    # Criar falha simulada
    failure = WorkflowFailure(
        workflow_id=workflow_id,
        run_id=run_id,
        failure_type=FailureType(failure_type),
        activity_name=activity_name,
        error_message="Simulated failure for correction",
    )

    correction = await service.suggest_correction(failure, retry_count)

    return correction.to_dict()


@activity.defn
async def execute_correction(
    workflow_id: str,
    correction_strategy: str,
    correction_parameters: dict | None = None,
    description: str = "",
) -> dict[str, Any]:
    """
    Executa uma ação de correção.

    Args:
        workflow_id: ID do workflow
        correction_strategy: Estratégia de correção
        correction_parameters: Parâmetros da correção
        description: Descrição da correção

    Returns:
        Dict com resultado da execução
    """
    logger.info(
        "executing_correction_activity",
        workflow_id=workflow_id,
        strategy=correction_strategy,
    )

    service = get_self_healing_service()

    correction = CorrectionAction(
        strategy=CorrectionStrategy(correction_strategy),
        description=description,
        parameters=correction_parameters or {},
    )

    result = await service.execute_correction(correction, workflow_id)

    return result


@activity.defn
async def replay_workflow(
    workflow_id: str,
    original_run_id: str,
    corrected_inputs: dict | None = None,
    continue_as_new: bool = False,
) -> dict[str, Any]:
    """
    Re-executa um workflow com inputs corrigidos.

    Args:
        workflow_id: ID do workflow original
        original_run_id: ID da execução original
        corrected_inputs: Inputs corrigidos
        continue_as_new: Se deve continuar como novo workflow

    Returns:
        Dict com ID da nova execução
    """
    logger.info(
        "replay_workflow_activity",
        workflow_id=workflow_id,
        original_run_id=original_run_id,
        continue_as_new=continue_as_new,
    )

    service = get_self_healing_service()

    try:
        new_run_id = await service.replay_workflow(
            workflow_id=workflow_id,
            original_run_id=original_run_id,
            corrected_inputs=corrected_inputs,
            continue_as_new=continue_as_new,
        )

        return {
            "status": "replay_started",
            "new_run_id": new_run_id,
            "workflow_id": workflow_id,
        }

    except Exception as e:
        logger.exception(
            "replay_workflow_failed",
            workflow_id=workflow_id,
            error=str(e),
        )
        raise ApplicationError(
            f"Failed to replay workflow: {str(e)}",
            non_retryable=True,
        )


@activity.defn
async def check_failure_pattern(
    workflow_id: str,
    activity_name: str | None = None,
) -> dict[str, Any]:
    """
    Verifica padrões de falha históricos para ajudar na correção.

    Args:
        workflow_id: ID do workflow
        activity_name: Nome da activity

    Returns:
        Dict com padrões encontrados e sugestões
    """
    logger.info(
        "checking_failure_pattern",
        workflow_id=workflow_id,
        activity_name=activity_name,
    )

    service = get_self_healing_service()

    key = f"{workflow_id}:{activity_name or 'workflow'}"
    failures = service.failure_history.get(key, [])

    # Análise de padrões
    failure_types: dict[str, int] = {}
    for failure in failures:
        ftype = failure.failure_type.value
        failure_types[ftype] = failure_types.get(ftype, 0) + 1

    # Detectar falhas recorrentes
    recurring = [ftype for ftype, count in failure_types.items() if count > 2]

    return {
        "workflow_id": workflow_id,
        "activity_name": activity_name,
        "total_failures": len(failures),
        "failure_types": failure_types,
        "recurring_patterns": recurring,
        "suggestion": _get_pattern_suggestion(recurring, failure_types),
    }


def _get_pattern_suggestion(recurring: list[str], failure_types: dict[str, int]) -> str:
    """Gera sugestão baseada em padrões de falha."""
    if not recurring:
        return "No clear pattern, standard retry recommended"

    if "timeout" in recurring:
        return "Recurring timeouts: Consider increasing timeout or optimizing performance"
    elif "permission_denied" in recurring:
        return "Recurring permission issues: Review RBAC configuration"
    elif "resource_unavailable" in recurring:
        return "Recurring resource issues: Check service health and dependencies"
    elif "validation_error" in recurring:
        return "Recurring validation errors: Review input schemas and constraints"
    else:
        return f"Recurring {recurring[0]}: Investigate root cause"
