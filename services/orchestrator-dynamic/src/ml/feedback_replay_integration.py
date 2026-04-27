"""
Integração entre Model Promotion e Feedback-Driven Replay.

Quando um modelo ML é promovido com melhor performance, este módulo
dispara automaticamente o replay de workflows que falharam devido ao
modelo antigo.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from temporalio.client import Client

from src.activities.feedback_replay_activity import get_feedback_replay_service
from src.services.feedback_replay_service import FeedbackReplayService

logger = logging.getLogger(__name__)


class FeedbackReplayIntegration:
    """
    Gerencia integração entre model promotion e feedback replay.

    Responsável por:
    - Detectar quando modelo é promovido com sucesso
    - Comparar métricas antes/depois
    - Disparar replay automático se melhoria for significativa
    """

    def __init__(
        self,
        temporal_client: Optional[Client] = None,
        improvement_threshold_pct: float = 10.0,
        enabled: bool = True,
    ):
        """
        Inicializa a integração.

        Args:
            temporal_client: Cliente Temporal para executar workflows
            improvement_threshold_pct: Percentual mínimo de melhoria para disparar replay
            enabled: Se False, integração é desabilitada
        """
        self.temporal_client = temporal_client
        self.improvement_threshold_pct = improvement_threshold_pct
        self.enabled = enabled

        self.feedback_replay_service: Optional[FeedbackReplayService] = None

    async def initialize(self) -> None:
        """Inicializa serviço de feedback replay."""
        if not self.enabled:
            logger.info("feedback_replay_integration_disabled")
            return

        self.feedback_replay_service = get_feedback_replay_service()
        logger.info(
            "feedback_replay_integration_initialized",
            threshold_pct=self.improvement_threshold_pct,
        )

    async def on_model_promoted(
        self,
        model_name: str,
        old_version: str,
        new_version: str,
        old_metrics: dict[str, float],
        new_metrics: dict[str, float],
        promote_initiated_by: str = "system",
    ) -> dict[str, Any]:
        """
        Callback quando modelo é promovido com sucesso.

        Compara métricas e dispara replay se melhoria for significativa.

        Args:
            model_name: Nome do modelo (ex: "approval-predictor")
            old_version: Versão do modelo anterior
            new_version: Nova versão promovida
            old_metrics: Métricas do modelo anterior
            new_metrics: Métricas do novo modelo
            promote_initiated_by: Quem iniciou a promoção

        Returns:
            Dict com resultado da integração
        """
        if not self.enabled or not self.feedback_replay_service:
            return {
                "status": "skipped",
                "reason": "integration_disabled_or_not_initialized",
            }

        logger.info(
            "model_promoted_triggering_replay_check",
            model_name=model_name,
            old_version=old_version,
            new_version=new_version,
        )

        # Comparar métricas
        improvement = await self.feedback_replay_service.check_model_improvement(
            old_model_version=old_version,
            new_model_version=new_version,
            metrics_old=old_metrics,
            metrics_new=new_metrics,
        )

        logger.info(
            "model_improvement_assessed",
            model_name=model_name,
            improvement=improvement.value,
            threshold=self.improvement_threshold_pct,
        )

        # Disparar replay se melhoria for suficiente
        if improvement.value in ["significant", "moderate"]:
            replay_result = await self.feedback_replay_service.on_model_updated(
                new_model_version=new_version,
                metrics_old=old_metrics,
                metrics_new=new_metrics,
            )

            logger.info(
                "feedback_replay_triggered",
                model_name=model_name,
                new_version=new_version,
                scheduled_count=replay_result.get("scheduled_count", 0),
            )

            return {
                "status": "replay_triggered",
                "improvement": improvement.value,
                "replay_result": replay_result,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
                "triggered_by": promote_initiated_by,
            }

        return {
            "status": "no_replay",
            "reason": f"Improvement not sufficient: {improvement.value}",
            "improvement": improvement.value,
            "threshold_required": "moderate_or_significant",
        }

    async def register_workflow_failure(
        self,
        workflow_id: str,
        run_id: str,
        failure_reason: str,
        model_version: str,
        plan_id: Optional[str] = None,
        priority: str = "medium",
        estimated_impact: float = 0.0,
        context: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Registra workflow que falhou devido a modelo ML.

        Chamado por workflows quando detectam erro relacionado a modelo.

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
        if not self.enabled or not self.feedback_replay_service:
            return {
                "status": "skipped",
                "reason": "integration_disabled_or_not_initialized",
            }

        from src.services.feedback_replay_service import ReplayPriority

        try:
            priority_enum = ReplayPriority(priority.lower())
        except ValueError:
            priority_enum = ReplayPriority.MEDIUM

        result = await self.feedback_replay_service.register_failed_workflow(
            workflow_id=workflow_id,
            run_id=run_id,
            failure_reason=failure_reason,
            model_version=model_version,
            plan_id=plan_id,
            priority=priority_enum,
            estimated_impact=estimated_impact,
            context=context,
        )

        logger.info(
            "workflow_failure_registered",
            workflow_id=workflow_id,
            model_version=model_version,
            priority=priority,
        )

        return result

    async def get_replay_metrics(self) -> dict[str, Any]:
        """Retorna métricas do sistema de replay."""
        if not self.feedback_replay_service:
            return {"status": "not_initialized"}

        return self.feedback_replay_service.get_metrics()

    async def close(self) -> None:
        """Limpa recursos."""
        self.feedback_replay_service = None
        logger.info("feedback_replay_integration_closed")


# Singleton para uso no ModelPromotionManager
_integration_instance: Optional[FeedbackReplayIntegration] = None


def get_feedback_replay_integration() -> FeedbackReplayIntegration:
    """Retorna instância singleton da integração."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = FeedbackReplayIntegration()
    return _integration_instance
