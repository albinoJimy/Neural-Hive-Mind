"""
Workflow Temporal para Cutover Orchestrator.

Implementa o fluxo de migração gradual do sistema legado para o novo:
- Shadow Mode (paralelo sem produção)
- Canary Deployment (5% → 25% → 50% → 100%)
- Rollback automático em caso de falha

Este workflow gerencia o ciclo de vida completo do cutover.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.models.workflow import CutoverPhase


@workflow.defn
class CutoverWorkflow:
    """
    Workflow de Cutover para migração gradual de sistemas.

    Gerencia o processo de cutover em múltiplas fases com rollback automático.
    """

    def __init__(self):
        self._status = "initializing"
        self._current_phase = CutoverPhase.SHADOW_MODE
        self._cutover_id: str | None = None
        self._config: dict | None = None
        self._metrics_history: list = []
        self._rollback_triggered = False
        self._pause_requested = False

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Executa o workflow de cutover.

        Args:
            input_data: Dicionário contendo:
                - cutover_config: Configuração do CutoverConfig
                - cutover_id: ID existente (opcional, para retomada)
                - initial_phase: Fase inicial (opcional)

        Returns:
            Dicionário com resultado do cutover
        """
        config_data = input_data.get("cutover_config", {})
        self._cutover_id = input_data.get("cutover_id")
        initial_phase = input_data.get("initial_phase", CutoverPhase.SHADOW_MODE)

        workflow_id = workflow.info().workflow_id

        workflow.logger.info(
            f"Iniciando workflow de cutover: workflow_id={workflow_id}, "
            f"initial_phase={initial_phase}"
        )

        try:
            # === Fase 1: Shadow Mode ===
            self._status = "shadow_mode"
            self._current_phase = CutoverPhase.SHADOW_MODE

            shadow_result = await self._execute_shadow_mode(
                config_data,
                input_data.get("cutover_id"),
            )

            if not shadow_result["success"]:
                # Shadow mode falhou - abortar cutover
                return {
                    "workflow_id": workflow_id,
                    "cutover_id": self._cutover_id,
                    "status": "failed",
                    "phase": "shadow_mode",
                    "error": shadow_result.get("error"),
                }

            workflow.logger.info("Shadow mode concluído com sucesso")

            # === Fase 2: Canary Deployment ===
            canary_stages = config_data.get("canary_stages", [5, 25, 50, 100])

            for traffic_percentage in canary_stages:
                # Verificar se foi pausado
                if self._pause_requested:
                    return await self._handle_pause(workflow_id)

                # Verificar se rollback foi acionado
                if self._rollback_triggered:
                    return await self._handle_rollback(workflow_id, "canary")

                phase_name = f"canary_{traffic_percentage}"
                self._status = phase_name

                # Mapear percentual para fase
                if traffic_percentage == 5:
                    self._current_phase = CutoverPhase.CANARY_5
                elif traffic_percentage == 25:
                    self._current_phase = CutoverPhase.CANARY_25
                elif traffic_percentage == 50:
                    self._current_phase = CutoverPhase.CANARY_50
                elif traffic_percentage == 100:
                    self._current_phase = CutoverPhase.FULL_CUTOVER

                canary_result = await self._execute_canary_stage(
                    config_data,
                    traffic_percentage,
                    self._cutover_id,
                )

                if not canary_result["success"]:
                    # Canary falhou - verificar se deve fazer rollback
                    if canary_result.get("should_rollback"):
                        return await self._handle_rollback(
                            workflow_id, phase_name, canary_result.get("error")
                        )
                    # Senão, pausar para intervenção manual
                    return await self._handle_pause(workflow_id, canary_result.get("error"))

                workflow.logger.info(f"Canary stage {traffic_percentage}% concluído com sucesso")

            # === Fase 3: Full Cutover ===
            self._status = "full_cutover"
            self._current_phase = CutoverPhase.FULL_CUTOVER

            full_result = await self._execute_full_cutover(
                config_data,
                self._cutover_id,
            )

            if not full_result["success"]:
                # Full cutover falhou
                return await self._handle_rollback(
                    workflow_id, "full_cutover", full_result.get("error")
                )

            # === Fase 4: Stabilization ===
            self._status = "stabilization"

            stabilization_result = await self._execute_stabilization(
                config_data,
                self._cutover_id,
            )

            # Workflow concluído
            self._status = "completed"

            return {
                "workflow_id": workflow_id,
                "cutover_id": self._cutover_id,
                "status": "success",
                "final_phase": "completed",
                "shadow_duration_hours": shadow_result.get("duration_hours"),
                "canary_stages_completed": len(canary_stages),
                "stabilization_days": stabilization_result.get("days"),
                "metrics_collected": len(self._metrics_history),
            }

        except Exception as e:
            self._status = "failed"
            workflow.logger.error(f"Erro no workflow de cutover: {e}", exc_info=True)
            raise

    async def _execute_shadow_mode(self, config: dict, cutover_id: str | None) -> dict[str, Any]:
        """
        Executa fase de Shadow Mode.

        No shadow mode, o novo sistema executa em paralelo com o legado
        sem receber tráfego de produção. Útil para validar comportamento.

        Args:
            config: Configuração do cutover
            cutover_id: ID do cutover

        Returns:
            Dict com resultado da fase
        """
        from src.activities.cutover import (
            finalize_shadow_mode,
            initialize_shadow_mode,
            validate_shadow_metrics,
        )

        shadow_duration_hours = config.get("shadow_duration_hours", 168)

        workflow.logger.info(f"Iniciando Shadow Mode: duration={shadow_duration_hours}h")

        # Inicializar shadow mode
        init_result = await workflow.execute_activity(
            initialize_shadow_mode,
            args=[config, cutover_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        if not init_result.get("success"):
            return {
                "success": False,
                "error": init_result.get("error", "Falha ao inicializar shadow mode"),
            }

        self._cutover_id = init_result.get("cutover_id")

        # Validar métricas periodicamente
        # Em produção, isso seria um loop com timer
        validation_result = await workflow.execute_activity(
            validate_shadow_metrics,
            args=[self._cutover_id, config],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        if not validation_result.get("valid"):
            return {
                "success": False,
                "error": validation_result.get("error", "Métricas shadow inválidas"),
            }

        # Finalizar shadow mode
        finalize_result = await workflow.execute_activity(
            finalize_shadow_mode,
            args=[self._cutover_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return {
            "success": True,
            "duration_hours": shadow_duration_hours,
            "metrics_summary": validation_result.get("metrics_summary", {}),
        }

    async def _execute_canary_stage(
        self, config: dict, traffic_percentage: int, cutover_id: str
    ) -> dict[str, Any]:
        """
        Executa um estágio de Canary.

        Args:
            config: Configuração do cutover
            traffic_percentage: Percentual de tráfego para este estágio
            cutover_id: ID do cutover

        Returns:
            Dict com resultado do estágio
        """
        from src.activities.cutover import (
            configure_canary_traffic,
            monitor_canary_metrics,
            validate_canary_stage,
        )

        canary_min_hours = config.get("canary_min_hours", 24)

        workflow.logger.info(
            f"Iniciando Canary {traffic_percentage}%: min_duration={canary_min_hours}h"
        )

        # Configurar tráfego canary
        config_result = await workflow.execute_activity(
            configure_canary_traffic,
            args=[cutover_id, traffic_percentage, config],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        if not config_result.get("success"):
            return {
                "success": False,
                "error": config_result.get("error", "Falha ao configurar tráfego"),
                "should_rollback": False,
            }

        # Monitorar métricas
        monitor_result = await workflow.execute_activity(
            monitor_canary_metrics,
            args=[cutover_id, traffic_percentage, config],
            start_to_close_timeout=timedelta(hours=canary_min_hours),
            retry_policy=RetryPolicy(
                maximum_attempts=1, non_retryable_error_types=["MetricThresholdExceeded"]
            ),
        )

        if not monitor_result.get("success"):
            should_rollback = monitor_result.get("should_rollback", False)
            return {
                "success": False,
                "error": monitor_result.get("error", "Métricas canary fora dos limites"),
                "should_rollback": should_rollback,
            }

        # Validar estágio
        validation_result = await workflow.execute_activity(
            validate_canary_stage,
            args=[cutover_id, traffic_percentage],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        if not validation_result.get("valid"):
            return {
                "success": False,
                "error": validation_result.get("error", "Validação canary falhou"),
                "should_rollback": False,
            }

        return {
            "success": True,
            "traffic_percentage": traffic_percentage,
            "duration_hours": canary_min_hours,
            "metrics_summary": monitor_result.get("metrics_summary", {}),
        }

    async def _execute_full_cutover(self, config: dict, cutover_id: str) -> dict[str, Any]:
        """
        Executa Full Cutover (100% do tráfego no novo sistema).

        Args:
            config: Configuração do cutover
            cutover_id: ID do cutover

        Returns:
            Dict com resultado
        """
        from src.activities.cutover import (
            configure_full_cutover,
            verify_full_cutover,
        )

        workflow.logger.info("Iniciando Full Cutover (100% tráfego)")

        # Configurar tráfego total
        config_result = await workflow.execute_activity(
            configure_full_cutover,
            args=[cutover_id, config],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        if not config_result.get("success"):
            return {
                "success": False,
                "error": config_result.get("error", "Falha ao configurar full cutover"),
            }

        # Verificar se sistema está estável
        verify_result = await workflow.execute_activity(
            verify_full_cutover,
            args=[cutover_id],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        if not verify_result.get("stable"):
            return {
                "success": False,
                "error": verify_result.get("error", "Sistema instável após full cutover"),
            }

        return {
            "success": True,
            "stable": True,
            "metrics_summary": verify_result.get("metrics_summary", {}),
        }

    async def _execute_stabilization(self, config: dict, cutover_id: str) -> dict[str, Any]:
        """
        Executa período de estabilização (7 dias).

        Args:
            config: Configuração do cutover
            cutover_id: ID do cutover

        Returns:
            Dict com resultado
        """
        from src.activities.cutover import monitor_stabilization

        stabilization_days = 7

        workflow.logger.info(f"Iniciando estabilização: duration={stabilization_days} dias")

        # Monitorar estabilização
        result = await workflow.execute_activity(
            monitor_stabilization,
            args=[cutover_id, stabilization_days, config],
            start_to_close_timeout=timedelta(days=stabilization_days),
            retry_policy=RetryPolicy(
                maximum_attempts=1, non_retryable_error_types=["StabilizationFailed"]
            ),
        )

        if not result.get("success"):
            return {
                "success": False,
                "error": result.get("error", "Estabilização falhou"),
            }

        return {
            "success": True,
            "days": stabilization_days,
            "final_state": "completed",
        }

    async def _handle_rollback(
        self, workflow_id: str, phase: str, error: str | None = None
    ) -> dict[str, Any]:
        """
        Trata rollback do cutover.

        Args:
            workflow_id: ID do workflow
            phase: Fase onde ocorreu o erro
            error: Erro que causou o rollback

        Returns:
            Dict com resultado do rollback
        """
        from src.activities.cutover import execute_rollback

        self._rollback_triggered = True
        self._status = "rolling_back"

        workflow.logger.error(f"Rollback acionado: phase={phase}, error={error}")

        rollback_result = await workflow.execute_activity(
            execute_rollback,
            args=[self._cutover_id, phase, error],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return {
            "workflow_id": workflow_id,
            "cutover_id": self._cutover_id,
            "status": "rolled_back",
            "phase": phase,
            "error": error,
            "rollback_successful": rollback_result.get("success", False),
        }

    async def _handle_pause(self, workflow_id: str, reason: str | None = None) -> dict[str, Any]:
        """
        Trata pausa do cutover.

        Args:
            workflow_id: ID do workflow
            reason: Motivo da pausa

        Returns:
            Dict com estado pausado
        """
        self._pause_requested = True
        self._status = "paused"

        workflow.logger.warning(f"Cutover pausado: reason={reason}")

        return {
            "workflow_id": workflow_id,
            "cutover_id": self._cutover_id,
            "status": "paused",
            "phase": self._current_phase.value,
            "reason": reason,
        }

    @workflow.signal
    async def pause_cutover(self):
        """Signal para pausar o cutover."""
        workflow.logger.info("Sinal de pausa recebido")
        self._pause_requested = True

    @workflow.signal
    async def trigger_rollback(self, reason: str = "manual"):
        """Signal para acionar rollback manual."""
        workflow.logger.warning(f"Sinal de rollback recebido: reason={reason}")
        self._rollback_triggered = True

    @workflow.signal
    async def promote_phase(self):
        """Signal para promoção manual de fase."""
        workflow.logger.info("Sinal de promoção recebido")
        # A promoção real será tratada no próximo checkpoint do loop

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """Query para consultar status atual."""
        return {
            "status": self._status,
            "current_phase": self._current_phase.value,
            "cutover_id": self._cutover_id,
            "rollback_triggered": self._rollback_triggered,
            "pause_requested": self._pause_requested,
        }

    @workflow.query
    def get_metrics_summary(self) -> dict[str, Any]:
        """Query para consultar resumo de métricas."""
        return {
            "metrics_collected": len(self._metrics_history),
            "current_phase": self._current_phase.value,
        }
