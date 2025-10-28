from typing import Dict, List, Optional

import structlog

from src.clients.consensus_engine_grpc_client import ConsensusEngineGrpcClient
from src.clients.mongodb_client import MongoDBClient
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


class WeightRecalibrator:
    """
    Serviço responsável por recalibração de pesos dos especialistas no Consensus Engine.

    Aplica ajustes de peso baseados em hipóteses validadas e feedback do RL.
    """

    def __init__(
        self,
        settings=None,
        consensus_client: Optional[ConsensusEngineGrpcClient] = None,
        mongodb_client: Optional[MongoDBClient] = None,
        redis_client: Optional[RedisClient] = None,
        optimization_producer: Optional[OptimizationProducer] = None,
        metrics=None,
    ):
        self.settings = settings or get_settings()
        self.consensus_client = consensus_client
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.optimization_producer = optimization_producer
        self.metrics = metrics

    async def apply_weight_recalibration(self, hypothesis: OptimizationHypothesis) -> Optional[OptimizationEvent]:
        """
        Aplicar recalibração de pesos baseada em hipótese.

        Args:
            hypothesis: Hipótese de otimização validada

        Returns:
            Evento de otimização aplicado (ou None se falhou)
        """
        try:
            # Validar tipo de otimização
            if hypothesis.optimization_type != OptimizationType.WEIGHT_RECALIBRATION:
                logger.warning(
                    "invalid_optimization_type",
                    hypothesis_id=hypothesis.hypothesis_id,
                    expected="WEIGHT_RECALIBRATION",
                    actual=hypothesis.optimization_type.value,
                )
                return None

            # Obter pesos atuais
            current_weights = await self.consensus_client.get_current_weights()

            if not current_weights:
                logger.error("failed_to_get_current_weights", hypothesis_id=hypothesis.hypothesis_id)
                return None

            # Calcular novos pesos
            proposed_weights = self._calculate_proposed_weights(
                current_weights=current_weights,
                adjustments=hypothesis.proposed_adjustments,
            )

            # Validar ajuste
            is_valid = await self.consensus_client.validate_weight_adjustment(proposed_weights)

            if not is_valid:
                logger.warning(
                    "weight_adjustment_validation_failed",
                    hypothesis_id=hypothesis.hypothesis_id,
                    proposed_weights=proposed_weights,
                )
                return None

            # Adquirir lock
            lock_acquired = await self.redis_client.lock_component("consensus-engine")

            if not lock_acquired:
                logger.warning("failed_to_acquire_lock", component="consensus-engine")
                return None

            try:
                # Aplicar ajuste
                success = await self.consensus_client.update_weights(
                    weights=proposed_weights,
                    justification=hypothesis.rationale,
                    optimization_id=hypothesis.hypothesis_id,
                )

                if not success:
                    logger.error("failed_to_update_weights", hypothesis_id=hypothesis.hypothesis_id)
                    return None

                # Criar evento de otimização
                optimization_event = self._create_optimization_event(
                    hypothesis=hypothesis,
                    baseline_weights=current_weights,
                    optimized_weights=proposed_weights,
                )

                # Persistir
                await self.mongodb_client.save_optimization(optimization_event.model_dump())

                # Publicar evento
                await self.optimization_producer.publish_optimization(optimization_event)

                logger.info(
                    "weight_recalibration_applied",
                    optimization_id=optimization_event.optimization_id,
                    weights_before=current_weights,
                    weights_after=proposed_weights,
                )

                if self.metrics:
                    self.metrics.increment_counter("weight_recalibrations_applied_total")

                return optimization_event

            finally:
                # Liberar lock
                await self.redis_client.unlock_component("consensus-engine")

        except Exception as e:
            logger.error("weight_recalibration_failed", hypothesis_id=hypothesis.hypothesis_id, error=str(e))
            return None

    def _calculate_proposed_weights(self, current_weights: Dict[str, float], adjustments: List[Dict]) -> Dict[str, float]:
        """
        Calcular pesos propostos baseado em ajustes.

        Args:
            current_weights: Pesos atuais
            adjustments: Lista de ajustes

        Returns:
            Pesos propostos
        """
        proposed = current_weights.copy()

        for adjustment in adjustments:
            specialist = adjustment.get("parameter")
            delta = adjustment.get("new_value", 0.0)

            if specialist in proposed:
                # Aplicar delta limitado
                max_delta = self.settings.max_weight_adjustment
                clamped_delta = max(-max_delta, min(max_delta, delta))

                proposed[specialist] = max(0.0, min(1.0, proposed[specialist] + clamped_delta))

        # Normalizar para somar 1.0
        total = sum(proposed.values())
        if total > 0:
            proposed = {k: v / total for k, v in proposed.items()}

        return proposed

    def _create_optimization_event(
        self,
        hypothesis: OptimizationHypothesis,
        baseline_weights: Dict[str, float],
        optimized_weights: Dict[str, float],
    ) -> OptimizationEvent:
        """
        Criar evento de otimização.

        Args:
            hypothesis: Hipótese original
            baseline_weights: Pesos baseline
            optimized_weights: Pesos otimizados

        Returns:
            Evento de otimização
        """
        # Calcular improvement (divergence reduction esperada)
        improvement = hypothesis.expected_improvement

        # Criar adjustments
        adjustments = []
        for specialist, new_weight in optimized_weights.items():
            old_weight = baseline_weights.get(specialist, 0.0)
            if abs(new_weight - old_weight) > 0.01:
                adjustments.append(
                    Adjustment(
                        parameter=specialist,
                        previous_value=old_weight,
                        new_value=new_weight,
                        justification=f"Ajuste baseado em RL Q-value: {hypothesis.rationale}",
                    )
                )

        # Criar causal analysis
        causal_analysis = CausalAnalysis(
            root_cause=f"Divergência de consenso em {hypothesis.target_component}",
            contributing_factors=[f"Specialist accuracy: {hypothesis.baseline_metrics}"],
            confidence_score=hypothesis.confidence,
        )

        # Criar rollback plan
        rollback_plan = RollbackPlan(
            rollback_strategy="REVERT_WEIGHTS",
            rollback_steps=[
                f"1. Reverter pesos para: {baseline_weights}",
                "2. Validar consenso recovery",
                "3. Notificar Queen Agent",
            ],
            validation_criteria=["divergence < 0.05", "confidence > 0.80"],
        )

        # Criar evento
        optimization_event = OptimizationEvent(
            optimization_id=hypothesis.hypothesis_id,
            optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
            target_component=hypothesis.target_component,
            experiment_id=hypothesis.hypothesis_id,  # Usar mesmo ID
            baseline_metrics=hypothesis.baseline_metrics,
            optimized_metrics={},  # Será preenchido após observação
            improvement_percentage=improvement,
            causal_analysis=causal_analysis,
            adjustments=adjustments,
            approval_status=ApprovalStatus.APPROVED,
            rollback_plan=rollback_plan,
        )

        return optimization_event

    async def rollback_weight_recalibration(self, optimization_id: str) -> bool:
        """
        Reverter recalibração de pesos.

        Args:
            optimization_id: ID da otimização a reverter

        Returns:
            True se bem-sucedido
        """
        try:
            success = await self.consensus_client.rollback_weights(optimization_id)

            if success:
                logger.info("weight_recalibration_rolled_back", optimization_id=optimization_id)

                if self.metrics:
                    self.metrics.increment_counter("weight_recalibrations_rolled_back_total")

            return success

        except Exception as e:
            logger.error("weight_recalibration_rollback_failed", optimization_id=optimization_id, error=str(e))
            return False
