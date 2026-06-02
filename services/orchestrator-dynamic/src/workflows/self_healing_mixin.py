"""
Mixin para adicionar capacidades de Self-Healing a Workflows.

Este mixin pode ser usado em qualquer workflow Temporal para adicionar
capacidades automáticas de recuperação de falhas.
"""

from datetime import timedelta
from typing import Any, Callable

from temporalio import workflow
from temporalio.common import RetryPolicy

from src.activities.self_healing_activity import (
    check_failure_pattern,
    execute_correction,
    replay_workflow,
    suggest_correction,
)


class SelfHealingMixin:
    """
    Mixin para adicionar self-healing a workflows.

    Uso:
        class MeuWorkflow(SelfHealingMixin):
            @workflow.run
            async def run(self, input_data):
                # Usar execute_with_self_healing para activities críticas
                result = await self.execute_with_self_healing(
                    activity=minha_activity,
                    args=[arg1, arg2],
                    activity_name="minha_activity",
                    max_retries=3,
                )
    """

    def __init__(self):
        self._retry_counts: dict[str, int] = {}
        self._correction_history: list[dict[str, Any]] = []

    async def execute_with_self_healing(
        self,
        activity: Callable,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        activity_name: str | None = None,
        max_retries: int = 3,
        enable_correction: bool = True,
        timeout_ms: int | None = None,
    ) -> Any:
        """
        Executa uma activity com capacidades de self-healing.

        Args:
            activity: Activity Temporal
            args: Argumentos posicionais
            kwargs: Argumentos nomeados
            activity_name: Nome da activity (para logging)
            max_retries: Máximo de tentativas
            enable_correction: Habilitar correções automáticas
            timeout_ms: Timeout em milissegundos

        Returns:
            Resultado da activity

        Raises:
            ApplicationError: Se todas as tentativas falharem
        """
        if activity_name is None:
            activity_name = activity.__name__

        args = args or []
        kwargs = kwargs or {}
        retry_count = self._retry_counts.get(activity_name, 0)

        workflow.logger.info(
            "executing_with_self_healing",
            activity=activity_name,
            retry_count=retry_count,
            max_retries=max_retries,
        )

        while retry_count <= max_retries:
            try:
                # Configurar retry policy do Temporal
                retry_policy = RetryPolicy(
                    maximum_attempts=1,  # Nós controlamos retries manualmente
                    initial_interval=timedelta(seconds=1),
                )

                # Executar activity
                result = await workflow.execute_activity(
                    activity,
                    args=args,
                    kwargs=kwargs,
                    start_to_close_timeout=timedelta(milliseconds=timeout_ms)
                    if timeout_ms
                    else None,
                    retry_policy=retry_policy,
                )

                # Sucesso! Resetar contador
                self._retry_counts[activity_name] = 0
                return result

            except Exception as e:
                retry_count += 1
                self._retry_counts[activity_name] = retry_count

                workflow.logger.warning(
                    "activity_failed",
                    activity=activity_name,
                    attempt=retry_count,
                    error=str(e),
                )

                # Verificar se devemos tentar correção
                if enable_correction and retry_count <= max_retries:
                    correction = await self._attempt_correction(
                        activity_name=activity_name,
                        error=str(e),
                        error_type=type(e).__name__,
                        retry_count=retry_count,
                    )

                    # Aplicar correção se sugerida
                    if correction and correction.get("strategy") in [
                        "parameter_adjustment",
                        "retry",
                    ]:
                        await self._apply_correction(correction)

                        # Se for retry, tentar novamente
                        if correction.get("strategy") == "retry":
                            continue

                # Se chegou aqui, esgotou tentativas
                if retry_count > max_retries:
                    # Verificar padrões de falha
                    pattern = await self._check_failure_patterns(activity_name)

                    workflow.logger.error(
                        "activity_failed_after_retries",
                        activity=activity_name,
                        attempts=retry_count,
                        pattern=pattern,
                    )

                    raise workflow.ApplicationError(
                        f"Activity {activity_name} failed after {retry_count} attempts",
                        non_retryable=True,
                    )

    async def _attempt_correction(
        self,
        activity_name: str,
        error: str,
        error_type: str,
        retry_count: int,
    ) -> dict[str, Any] | None:
        """
        Tenta encontrar uma correção para a falha.

        Args:
            activity_name: Nome da activity
            error: Mensagem de erro
            error_type: Tipo do erro
            retry_count: Número de tentativas

        Returns:
            Dict com correção sugerida ou None
        """
        workflow_info = workflow.info()
        workflow_id = workflow_info.workflow_id
        run_id = workflow_info.run_id

        try:
            # Analisar falha
            # (Isso poderia ser uma activity separada)
            failure_type = self._classify_error(error, error_type)

            # Sugerir correção
            correction = await workflow.execute_activity(
                suggest_correction,
                args=[
                    workflow_id,
                    run_id,
                    failure_type,
                    activity_name,
                    retry_count,
                ],
                start_to_close_timeout=timedelta(seconds=10),
            )

            workflow.logger.info(
                "correction_suggested",
                activity=activity_name,
                strategy=correction.get("strategy"),
                description=correction.get("description"),
            )

            return correction

        except Exception as e:
            workflow.logger.warning(
                "correction_suggestion_failed",
                activity=activity_name,
                error=str(e),
            )
            return None

    async def _apply_correction(self, correction: dict[str, Any]):
        """
        Aplica uma correção sugerida.

        Args:
            correction: Dict com correção
        """
        workflow_info = workflow.info()
        workflow_id = workflow_info.workflow_id

        try:
            await workflow.execute_activity(
                execute_correction,
                args=[
                    workflow_id,
                    correction.get("strategy"),
                    correction.get("parameters"),
                    correction.get("description", ""),
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Registrar no histórico
            self._correction_history.append(
                {
                    "timestamp": workflow.now().isoformat(),
                    "correction": correction,
                }
            )

        except Exception as e:
            workflow.logger.warning(
                "correction_execution_failed",
                error=str(e),
            )

    async def _check_failure_patterns(self, activity_name: str) -> dict[str, Any]:
        """
        Verifica padrões de falha históricos.

        Args:
            activity_name: Nome da activity

        Returns:
            Dict com padrões encontrados
        """
        workflow_info = workflow.info()
        workflow_id = workflow_info.workflow_id

        try:
            pattern = await workflow.execute_activity(
                check_failure_pattern,
                args=[workflow_id, activity_name],
                start_to_close_timeout=timedelta(seconds=10),
            )
            return pattern
        except Exception:
            return {"error": "Could not check patterns"}

    def _classify_error(self, error_message: str, error_type: str) -> str:
        """Classifica o tipo de erro."""
        error_lower = error_message.lower()

        if "timeout" in error_lower:
            return "timeout"
        elif "permission" in error_lower or "unauthorized" in error_lower:
            return "permission_denied"
        elif "validation" in error_lower or "invalid" in error_lower:
            return "validation_error"
        elif "unavailable" in error_lower or "not found" in error_lower:
            return "resource_unavailable"
        else:
            return "activity_failure"

    async def request_replay(
        self,
        corrected_inputs: dict[str, Any] | None = None,
        continue_as_new: bool = False,
    ) -> str:
        """
        Solicita replay do workflow atual.

        Args:
            corrected_inputs: Inputs corrigidos
            continue_as_new: Se deve continuar como novo

        Returns:
            ID da nova execução
        """
        workflow_info = workflow.info()
        workflow_id = workflow_info.workflow_id
        run_id = workflow_info.run_id

        workflow.logger.info(
            "requesting_replay",
            workflow_id=workflow_id,
            run_id=run_id,
            continue_as_new=continue_as_new,
        )

        result = await workflow.execute_activity(
            replay_workflow,
            args=[workflow_id, run_id, corrected_inputs, continue_as_new],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return result.get("new_run_id")
