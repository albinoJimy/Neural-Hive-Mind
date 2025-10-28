from typing import Dict, List, Optional

import structlog

from src.clients.mongodb_client import MongoDBClient
from src.clients.orchestrator_grpc_client import OrchestratorGrpcClient
from src.clients.redis_client import RedisClient
from src.config.settings import get_settings
from src.models.optimization_event import (
    Adjustment,
    ApprovalStatus,
    CausalAnalysis,
    OptimizationEvent,
    OptimizationType,
    RollbackPlan,
)
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.producers.optimization_producer import OptimizationProducer

logger = structlog.get_logger()


class SLOAdjuster:
    """
    Serviço responsável por ajuste de SLOs no Orchestrator Dynamic.

    Aplica ajustes de SLO baseados em hipóteses validadas e feedback do RL.
    """

    def __init__(
        self,
        settings=None,
        orchestrator_client: Optional[OrchestratorGrpcClient] = None,
        mongodb_client: Optional[MongoDBClient] = None,
        redis_client: Optional[RedisClient] = None,
        optimization_producer: Optional[OptimizationProducer] = None,
        metrics=None,
    ):
        self.settings = settings or get_settings()
        self.orchestrator_client = orchestrator_client
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.optimization_producer = optimization_producer
        self.metrics = metrics

    async def apply_slo_adjustment(self, hypothesis: OptimizationHypothesis) -> Optional[OptimizationEvent]:
        """
        Aplicar ajuste de SLO baseado em hipótese.

        Args:
            hypothesis: Hipótese de otimização validada

        Returns:
            Evento de otimização aplicado (ou None se falhou)
        """
        try:
            # Validar tipo de otimização
            if hypothesis.optimization_type != OptimizationType.SLO_ADJUSTMENT:
                logger.warning(
                    "invalid_optimization_type",
                    hypothesis_id=hypothesis.hypothesis_id,
                    expected="SLO_ADJUSTMENT",
                    actual=hypothesis.optimization_type.value,
                )
                return None

            # Obter SLOs atuais
            current_slos = await self.orchestrator_client.get_current_slos(service=hypothesis.target_component)

            if not current_slos:
                logger.error("failed_to_get_current_slos", hypothesis_id=hypothesis.hypothesis_id)
                return None

            # Verificar error budget
            error_budget = await self.orchestrator_client.get_error_budget(service=hypothesis.target_component)

            if error_budget and error_budget.get("remaining_budget_percentage", 0) < 0.2:
                logger.warning(
                    "insufficient_error_budget",
                    hypothesis_id=hypothesis.hypothesis_id,
                    remaining_budget=error_budget.get("remaining_budget_percentage"),
                )
                return None

            # Calcular SLOs propostos
            proposed_slos = self._calculate_proposed_slos(
                current_slos=current_slos.get(hypothesis.target_component, {}),
                adjustments=hypothesis.proposed_adjustments,
            )

            # Validar ajuste
            is_valid = await self.orchestrator_client.validate_slo_adjustment({hypothesis.target_component: proposed_slos})

            if not is_valid:
                logger.warning(
                    "slo_adjustment_validation_failed",
                    hypothesis_id=hypothesis.hypothesis_id,
                    proposed_slos=proposed_slos,
                )
                return None

            # Adquirir lock
            lock_acquired = await self.redis_client.lock_component(hypothesis.target_component)

            if not lock_acquired:
                logger.warning("failed_to_acquire_lock", component=hypothesis.target_component)
                return None

            try:
                # Aplicar ajuste
                success = await self.orchestrator_client.update_slos(
                    slo_updates={hypothesis.target_component: proposed_slos},
                    justification=hypothesis.rationale,
                    optimization_id=hypothesis.hypothesis_id,
                )

                if not success:
                    logger.error("failed_to_update_slos", hypothesis_id=hypothesis.hypothesis_id)
                    return None

                # Criar evento de otimização
                optimization_event = self._create_optimization_event(
                    hypothesis=hypothesis,
                    baseline_slos=current_slos.get(hypothesis.target_component, {}),
                    optimized_slos=proposed_slos,
                )

                # Persistir
                await self.mongodb_client.save_optimization(optimization_event.model_dump())

                # Publicar evento
                await self.optimization_producer.publish_optimization(optimization_event)

                logger.info(
                    "slo_adjustment_applied",
                    optimization_id=optimization_event.optimization_id,
                    service=hypothesis.target_component,
                    slos_before=current_slos.get(hypothesis.target_component),
                    slos_after=proposed_slos,
                )

                if self.metrics:
                    self.metrics.increment_counter("slo_adjustments_applied_total")

                return optimization_event

            finally:
                # Liberar lock
                await self.redis_client.unlock_component(hypothesis.target_component)

        except Exception as e:
            logger.error("slo_adjustment_failed", hypothesis_id=hypothesis.hypothesis_id, error=str(e))
            return None

    def _calculate_proposed_slos(self, current_slos: Dict, adjustments: List[Dict]) -> Dict:
        """
        Calcular SLOs propostos baseado em ajustes.

        Args:
            current_slos: SLOs atuais
            adjustments: Lista de ajustes

        Returns:
            SLOs propostos
        """
        proposed = current_slos.copy()

        for adjustment in adjustments:
            parameter = adjustment.get("parameter")
            new_value = adjustment.get("new_value")

            if parameter in ["target_latency_ms", "target_availability", "target_error_rate"]:
                # Aplicar ajuste com limites de segurança
                if parameter == "target_latency_ms":
                    # Latência: ±30% máximo
                    current = proposed.get(parameter, 1000)
                    max_change = current * 0.3
                    delta = new_value - current
                    clamped_delta = max(-max_change, min(max_change, delta))
                    proposed[parameter] = max(100, current + clamped_delta)

                elif parameter == "target_availability":
                    # Availability: mínimo 0.95, máximo 0.9999
                    proposed[parameter] = max(0.95, min(0.9999, new_value))

                elif parameter == "target_error_rate":
                    # Error rate: mínimo 0.001, máximo 0.10
                    proposed[parameter] = max(0.001, min(0.10, new_value))

        return proposed

    def _create_optimization_event(
        self,
        hypothesis: OptimizationHypothesis,
        baseline_slos: Dict,
        optimized_slos: Dict,
    ) -> OptimizationEvent:
        """
        Criar evento de otimização.

        Args:
            hypothesis: Hipótese original
            baseline_slos: SLOs baseline
            optimized_slos: SLOs otimizados

        Returns:
            Evento de otimização
        """
        # Calcular improvement
        improvement = hypothesis.expected_improvement

        # Criar adjustments
        adjustments = []
        for param in ["target_latency_ms", "target_availability", "target_error_rate"]:
            old_value = baseline_slos.get(param, 0)
            new_value = optimized_slos.get(param, 0)

            if old_value != new_value:
                adjustments.append(
                    Adjustment(
                        parameter=param,
                        previous_value=old_value,
                        new_value=new_value,
                        justification=f"Ajuste baseado em RL Q-value: {hypothesis.rationale}",
                    )
                )

        # Criar causal analysis
        causal_analysis = CausalAnalysis(
            root_cause=f"Degradação de SLO em {hypothesis.target_component}",
            contributing_factors=[f"Métricas baseline: {hypothesis.baseline_metrics}"],
            confidence_score=hypothesis.confidence,
        )

        # Criar rollback plan
        rollback_plan = RollbackPlan(
            rollback_strategy="REVERT_SLOS",
            rollback_steps=[
                f"1. Reverter SLOs para: {baseline_slos}",
                "2. Validar compliance recovery",
                "3. Notificar Queen Agent",
            ],
            validation_criteria=["slo_compliance >= 0.99", "error_rate < 0.01"],
        )

        # Criar evento
        optimization_event = OptimizationEvent(
            optimization_id=hypothesis.hypothesis_id,
            optimization_type=OptimizationType.SLO_ADJUSTMENT,
            target_component=hypothesis.target_component,
            experiment_id=hypothesis.hypothesis_id,
            baseline_metrics=hypothesis.baseline_metrics,
            optimized_metrics={},
            improvement_percentage=improvement,
            causal_analysis=causal_analysis,
            adjustments=adjustments,
            approval_status=ApprovalStatus.APPROVED,
            rollback_plan=rollback_plan,
        )

        return optimization_event

    async def rollback_slo_adjustment(self, optimization_id: str) -> bool:
        """
        Reverter ajuste de SLO.

        Args:
            optimization_id: ID da otimização a reverter

        Returns:
            True se bem-sucedido
        """
        try:
            success = await self.orchestrator_client.rollback_slos(optimization_id)

            if success:
                logger.info("slo_adjustment_rolled_back", optimization_id=optimization_id)

                if self.metrics:
                    self.metrics.increment_counter("slo_adjustments_rolled_back_total")

            return success

        except Exception as e:
            logger.error("slo_adjustment_rollback_failed", optimization_id=optimization_id, error=str(e))
            return False
