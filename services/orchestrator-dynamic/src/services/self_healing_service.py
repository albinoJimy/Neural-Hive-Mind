"""
Self-Healing Service para Temporal Workflows.

Permite detectar falhas, corrigir automaticamente e re-executar workflows.
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from temporalio import workflow
from temporalio.client import Client

from neural_hive_observability import get_tracer

logger = structlog.get_logger(__name__)


class FailureType(str, Enum):
    """Tipo de falha em workflow."""

    ACTIVITY_FAILURE = "activity_failure"
    TIMEOUT = "timeout"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    PERMISSION_DENIED = "permission_denied"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


class CorrectionStrategy(str, Enum):
    """Estratégia de correção."""

    RETRY = "retry"  # Re-tentar com mesmos parâmetros
    PARAMETER_ADJUSTMENT = "parameter_adjustment"  # Ajustar parâmetros
    FALLBACK = "fallback"  # Usar alternativa
    ESCALATION = "escalation"  # Solicitar intervenção humana
    SKIP = "skip"  # Pular etapa não-crítica


class WorkflowFailure:
    """Representa uma falha em workflow."""

    def __init__(
        self,
        workflow_id: str,
        run_id: str,
        failure_type: FailureType,
        activity_name: str | None = None,
        error_message: str = "",
        error_details: dict | None = None,
        timestamp: datetime | None = None,
    ):
        self.workflow_id = workflow_id
        self.run_id = run_id
        self.failure_type = failure_type
        self.activity_name = activity_name
        self.error_message = error_message
        self.error_details = error_details or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict."""
        return {
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "failure_type": self.failure_type.value,
            "activity_name": self.activity_name,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "timestamp": self.timestamp.isoformat(),
        }


class CorrectionAction:
    """Representa uma ação de correção."""

    def __init__(
        self,
        strategy: CorrectionStrategy,
        description: str,
        parameters: dict | None = None,
        requires_approval: bool = False,
    ):
        self.strategy = strategy
        self.description = description
        self.parameters = parameters or {}
        self.requires_approval = requires_approval
        self.executed = False
        self.result: dict | None = None
        self.executed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict."""
        return {
            "strategy": self.strategy.value,
            "description": self.description,
            "parameters": self.parameters,
            "requires_approval": self.requires_approval,
            "executed": self.executed,
            "result": self.result,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class SelfHealingService:
    """
    Serviço para auto-correção e replay de workflows.

    Funcionalidades:
    - Detecção de falhas
    - Análise de causa raiz
    - Sugestão de correções
    - Execução de correções
    - Replay de workflows
    """

    def __init__(
        self,
        temporal_client: Client | None = None,
        enable_auto_correction: bool = True,
        enable_auto_retry: bool = True,
        max_retry_attempts: int = 3,
        retry_backoff_ms: int = 1000,
    ):
        """
        Inicializa o serviço.

        Args:
            temporal_client: Cliente Temporal
            enable_auto_correction: Habilitar correções automáticas
            enable_auto_retry: Habilitar retry automático
            max_retry_attempts: Máximo de tentativas de retry
            retry_backoff_ms: Backoff entre retries em ms
        """
        self.temporal_client = temporal_client
        self.enable_auto_correction = enable_auto_correction
        self.enable_auto_retry = enable_auto_retry
        self.max_retry_attempts = max_retry_attempts
        self.retry_backoff_ms = retry_backoff_ms

        # Histórico de falhas para aprendizado
        self.failure_history: dict[str, list[WorkflowFailure]] = {}

        # Estratégias de correção por tipo de falha
        self.correction_strategies = {
            FailureType.ACTIVITY_FAILURE: self._handle_activity_failure,
            FailureType.TIMEOUT: self._handle_timeout,
            FailureType.RESOURCE_UNAVAILABLE: self._handle_resource_unavailable,
            FailureType.PERMISSION_DENIED: self._handle_permission_denied,
            FailureType.VALIDATION_ERROR: self._handle_validation_error,
            FailureType.UNKNOWN: self._handle_unknown,
        }

    async def analyze_failure(
        self,
        workflow_id: str,
        run_id: str,
        error: Exception,
        activity_name: str | None = None,
        context: dict | None = None,
    ) -> WorkflowFailure:
        """
        Analisa uma falha e determina seu tipo.

        Args:
            workflow_id: ID do workflow
            run_id: ID da execução
            error: Exceção capturada
            activity_name: Nome da activity que falhou
            context: Contexto adicional

        Returns:
            WorkflowFailure com tipo determinado
        """
        error_message = str(error)
        error_type = type(error).__name__

        logger.info(
            "analyzing_failure",
            workflow_id=workflow_id,
            run_id=run_id,
            activity_name=activity_name,
            error_type=error_type,
            error_message=error_message,
        )

        # Determinar tipo de falha baseado na mensagem
        failure_type = self._classify_failure(error_message, error_type)

        failure = WorkflowFailure(
            workflow_id=workflow_id,
            run_id=run_id,
            failure_type=failure_type,
            activity_name=activity_name,
            error_message=error_message,
            error_details={
                "error_type": error_type,
                "context": context or {},
            },
        )

        # Armazenar no histórico
        self._record_failure(failure)

        return failure

    def _classify_failure(self, error_message: str, error_type: str) -> FailureType:
        """Classifica o tipo de falha baseado na mensagem."""
        error_lower = error_message.lower()

        # Timeout
        if "timeout" in error_lower or "timed out" in error_lower:
            return FailureType.TIMEOUT

        # Permissão
        if (
            "permission" in error_lower
            or "unauthorized" in error_lower
            or "forbidden" in error_lower
            or "access denied" in error_lower
        ):
            return FailureType.PERMISSION_DENIED

        # Recurso indisponível
        if (
            "unavailable" in error_lower
            or "not found" in error_lower
            or "connection" in error_lower
            or "refused" in error_lower
        ):
            return FailureType.RESOURCE_UNAVAILABLE

        # Validação
        if (
            "validation" in error_lower
            or "invalid" in error_lower
            or "schema" in error_lower
            or "constraint" in error_lower
        ):
            return FailureType.VALIDATION_ERROR

        # Activity genérica
        if "activity" in error_lower or "task" in error_lower:
            return FailureType.ACTIVITY_FAILURE

        return FailureType.UNKNOWN

    async def suggest_correction(
        self,
        failure: WorkflowFailure,
        retry_count: int = 0,
    ) -> CorrectionAction:
        """
        Sugere uma correção para a falha.

        Args:
            failure: Falha analisada
            retry_count: Número de tentativas já realizadas

        Returns:
            CorrectionAction com estratégia recomendada
        """
        logger.info(
            "suggesting_correction",
            workflow_id=failure.workflow_id,
            failure_type=failure.failure_type.value,
            retry_count=retry_count,
        )

        # Obter handler específico para o tipo de falha
        handler = self.correction_strategies.get(
            failure.failure_type, self._handle_unknown
        )

        correction = await handler(failure, retry_count)

        logger.info(
            "correction_suggested",
            strategy=correction.strategy.value,
            description=correction.description,
            requires_approval=correction.requires_approval,
        )

        return correction

    async def execute_correction(
        self,
        correction: CorrectionAction,
        workflow_id: str,
    ) -> dict[str, Any]:
        """
        Executa uma ação de correção.

        Args:
            correction: Ação de correção
            workflow_id: ID do workflow

        Returns:
            Resultado da execução
        """
        logger.info(
            "executing_correction",
            workflow_id=workflow_id,
            strategy=correction.strategy.value,
        )

        tracer = get_tracer()

        with tracer.start_as_current_span(
            "self_healing.execute_correction",
            attributes={
                "workflow.id": workflow_id,
                "correction.strategy": correction.strategy.value,
            },
        ):
            if correction.strategy == CorrectionStrategy.RETRY:
                result = await self._execute_retry(correction, workflow_id)
            elif correction.strategy == CorrectionStrategy.PARAMETER_ADJUSTMENT:
                result = await self._execute_parameter_adjustment(
                    correction, workflow_id
                )
            elif correction.strategy == CorrectionStrategy.FALLBACK:
                result = await self._execute_fallback(correction, workflow_id)
            elif correction.strategy == CorrectionStrategy.ESCALATION:
                result = await self._execute_escalation(correction, workflow_id)
            elif correction.strategy == CorrectionStrategy.SKIP:
                result = await self._execute_skip(correction, workflow_id)
            else:
                result = {"status": "unknown_strategy"}

        # Marcar como executado
        correction.executed = True
        correction.result = result
        correction.executed_at = datetime.now(timezone.utc)

        return result

    async def replay_workflow(
        self,
        workflow_id: str,
        original_run_id: str,
        corrected_inputs: dict[str, Any] | None = None,
        continue_as_new: bool = False,
    ) -> str:
        """
        Re-executa um workflow com inputs corrigidos.

        Args:
            workflow_id: ID do workflow original
            original_run_id: ID da execução original
            corrected_inputs: Inputs corrigidos
            continue_as_new: Se deve continuar como novo workflow

        Returns:
            ID da nova execução
        """
        logger.info(
            "replaying_workflow",
            workflow_id=workflow_id,
            original_run_id=original_run_id,
            continue_as_new=continue_as_new,
        )

        if not self.temporal_client:
            raise RuntimeError("Temporal client not configured")

        # Obter workflow original
        handle = self.temporal_client.get_workflow_handle(
            workflow_id, run_id=original_run_id
        )

        # Descrever workflow para obter informações
        description = await handle.describe()

        # Construir inputs corrigidos
        original_inputs = description.inputs or {}
        replay_inputs = self._merge_inputs(original_inputs, corrected_inputs or {})

        logger.info(
            "starting_replay",
            original_workflow_type=description.workflow_type.name,
            replay_inputs=replay_inputs,
        )

        # Executar replay
        if continue_as_new:
            # Continuar como novo workflow (para workflows em execução)
            new_handle = await handle.continue_as_new(
                args=[replay_inputs],
            )
            new_run_id = new_handle.id
        else:
            # Iniciar novo workflow (para workflows completados/falhados)
            new_handle = await self.temporal_client.start_workflow(
                description.workflow_type,
                args=[replay_inputs],
                id=f"{workflow_id}-replay-{int(datetime.now(timezone.utc).timestamp())}",
            )
            new_run_id = new_handle.id

        logger.info(
            "replay_started",
            new_run_id=new_run_id,
        )

        return new_run_id

    def _record_failure(self, failure: WorkflowFailure):
        """Registra falha no histórico."""
        key = f"{failure.workflow_id}:{failure.activity_name or 'workflow'}"
        if key not in self.failure_history:
            self.failure_history[key] = []
        self.failure_history[key].append(failure)

    def _merge_inputs(
        self, original: dict[str, Any], corrections: dict[str, Any]
    ) -> dict[str, Any]:
        """Mescla inputs originais com correções."""
        merged = original.copy()
        merged.update(corrections)
        return merged

    # Handlers específicos por tipo de falha

    async def _handle_activity_failure(
        self, failure: WorkflowFailure, retry_count: int
    ) -> CorrectionAction:
        """Handler para falhas de activity."""
        if retry_count < self.max_retry_attempts and self.enable_auto_retry:
            return CorrectionAction(
                strategy=CorrectionStrategy.RETRY,
                description=f"Retry activity {failure.activity_name}",
                parameters={"backoff_ms": self.retry_backoff_ms * (retry_count + 1)},
                requires_approval=False,
            )
        else:
            return CorrectionAction(
                strategy=CorrectionStrategy.ESCALATION,
                description=f"Activity {failure.activity_name} failed after {retry_count} retries",
                requires_approval=True,
            )

    async def _handle_timeout(
        self, failure: WorkflowFailure, retry_count: int
    ) -> CorrectionAction:
        """Handler para timeouts."""
        if retry_count < self.max_retry_attempts:
            return CorrectionAction(
                strategy=CorrectionStrategy.PARAMETER_ADJUSTMENT,
                description="Increase timeout and retry",
                parameters={
                    "timeout_multiplier": 2.0,
                    "backoff_ms": self.retry_backoff_ms * (retry_count + 1),
                },
                requires_approval=False,
            )
        else:
            return CorrectionAction(
                strategy=CorrectionStrategy.ESCALATION,
                description="Task timing out repeatedly, needs investigation",
                requires_approval=True,
            )

    async def _handle_resource_unavailable(
        self, failure: WorkflowFailure, retry_count: int
    ) -> CorrectionAction:
        """Handler para recursos indisponíveis."""
        return CorrectionAction(
            strategy=CorrectionStrategy.RETRY,
            description="Resource temporarily unavailable, will retry",
            parameters={
                "backoff_ms": 5000,  # Backoff maior para recursos
                "max_wait_ms": 60000,
            },
            requires_approval=False,
        )

    async def _handle_permission_denied(
        self, failure: WorkflowFailure, retry_count: int
    ) -> CorrectionAction:
        """Handler para erros de permissão."""
        return CorrectionAction(
            strategy=CorrectionStrategy.ESCALATION,
            description="Permission denied, requires manual intervention",
            requires_approval=True,
        )

    async def _handle_validation_error(
        self, failure: WorkflowFailure, retry_count: int
    ) -> CorrectionAction:
        """Handler para erros de validação."""
        return CorrectionAction(
            strategy=CorrectionStrategy.PARAMETER_ADJUSTMENT,
            description="Validation error, parameters need correction",
            parameters={
                "fix_parameters": True,
                "validation_mode": "strict",
            },
            requires_approval=True,
        )

    async def _handle_unknown(
        self, failure: WorkflowFailure, retry_count: int
    ) -> CorrectionAction:
        """Handler para falhas desconhecidas."""
        if retry_count == 0:
            return CorrectionAction(
                strategy=CorrectionStrategy.RETRY,
                description="Unknown error, attempting retry",
                requires_approval=False,
            )
        else:
            return CorrectionAction(
                strategy=CorrectionStrategy.ESCALATION,
                description="Unknown error persisted, needs investigation",
                requires_approval=True,
            )

    # Executores de estratégia

    async def _execute_retry(
        self, correction: CorrectionAction, workflow_id: str
    ) -> dict[str, Any]:
        """Executa retry."""
        backoff = correction.parameters.get("backoff_ms", self.retry_backoff_ms)
        await asyncio.sleep(backoff / 1000)
        return {"status": "retry_scheduled", "backoff_ms": backoff}

    async def _execute_parameter_adjustment(
        self, correction: CorrectionAction, workflow_id: str
    ) -> dict[str, Any]:
        """Executa ajuste de parâmetros."""
        return {"status": "parameters_adjusted", "changes": correction.parameters}

    async def _execute_fallback(
        self, correction: CorrectionAction, workflow_id: str
    ) -> dict[str, Any]:
        """Executa fallback."""
        return {"status": "fallback_executed", "fallback": correction.parameters}

    async def _execute_escalation(
        self, correction: CorrectionAction, workflow_id: str
    ) -> dict[str, Any]:
        """Executa escalation."""
        # TODO: Implementar sistema de tickets/notifications
        return {
            "status": "escalated",
            "requires_human_intervention": True,
            "description": correction.description,
        }

    async def _execute_skip(
        self, correction: CorrectionAction, workflow_id: str
    ) -> dict[str, Any]:
        """Executa skip."""
        return {"status": "skipped", "reason": "non_critical_task"}
