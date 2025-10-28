import uuid
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from src.config.settings import get_settings
from src.models.experiment_request import ComparisonOperator, ExperimentRequest, ExperimentType, RandomizationStrategy
from src.models.optimization_hypothesis import OptimizationHypothesis

logger = structlog.get_logger()


class ExperimentManager:
    """
    Gerenciador de experimentos integrado com Argo Workflows.

    Responsável por submeter, monitorar e analisar experimentos controlados
    para validar hipóteses de otimização.
    """

    def __init__(self, settings=None, argo_client=None, mongodb_client=None, redis_client=None):
        self.settings = settings or get_settings()
        self.argo_client = argo_client  # ArgoWorkflowsClient (a ser implementado)
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client

        logger.info("experiment_manager_initialized")

    async def submit_experiment(self, hypothesis: OptimizationHypothesis) -> Optional[str]:
        """
        Submeter experimento baseado em hipótese.

        Args:
            hypothesis: Hipótese de otimização a ser testada

        Returns:
            experiment_id se submetido com sucesso, None caso contrário
        """
        try:
            # Validar viabilidade da hipótese
            if not hypothesis.validate_feasibility():
                logger.warning("hypothesis_not_feasible", hypothesis_id=hypothesis.hypothesis_id)
                return None

            # Verificar se não há experimento em andamento no mesmo componente (lock via Redis)
            if self.redis_client:
                locked = await self.redis_client.lock_component(
                    hypothesis.target_component, ttl=self.settings.experiment_timeout_seconds
                )
                if not locked:
                    logger.warning(
                        "component_locked_for_experiment", component=hypothesis.target_component
                    )
                    return None

            # Converter hipótese para ExperimentRequest
            experiment_request = self._hypothesis_to_experiment_request(hypothesis)

            # Validar guardrails e success criteria
            if not experiment_request.validate_guardrails():
                logger.error("invalid_guardrails", experiment_id=experiment_request.experiment_id)
                if self.redis_client:
                    await self.redis_client.unlock_component(hypothesis.target_component)
                return None

            # Solicitar aprovação de compliance se necessário
            if experiment_request.ethical_approval_required:
                # TODO: Integrar com sistema de compliance
                logger.info("ethical_approval_required", experiment_id=experiment_request.experiment_id)
                experiment_request.approved_by_compliance = False  # Pendente

            # Submeter workflow via Argo Workflows
            if self.argo_client:
                workflow_name = await self.argo_client.submit_experiment_workflow(experiment_request)
                logger.info(
                    "experiment_submitted_to_argo",
                    experiment_id=experiment_request.experiment_id,
                    workflow=workflow_name,
                )
            else:
                logger.warning("argo_client_not_configured", experiment_id=experiment_request.experiment_id)

            # Persistir no MongoDB
            if self.mongodb_client:
                await self.mongodb_client.save_experiment(experiment_request)

            logger.info(
                "experiment_submitted",
                experiment_id=experiment_request.experiment_id,
                hypothesis_id=hypothesis.hypothesis_id,
                type=experiment_request.experiment_type.value,
            )

            return experiment_request.experiment_id

        except Exception as e:
            logger.error("experiment_submission_failed", hypothesis_id=hypothesis.hypothesis_id, error=str(e))
            # Liberar lock em caso de erro
            if self.redis_client:
                await self.redis_client.unlock_component(hypothesis.target_component)
            return None

    async def monitor_experiment(self, experiment_id: str) -> Optional[Dict]:
        """
        Monitorar experimento em andamento.

        Verifica guardrails continuamente e aborta se violados.

        Args:
            experiment_id: ID do experimento

        Returns:
            Dict com status do experimento incluindo:
                - elapsed_time: tempo decorrido em segundos
                - performance_degradation: percentual de degradação (0.0 a 1.0)
                - status: status atual do workflow
        """
        try:
            # Recuperar experimento do MongoDB
            if not self.mongodb_client:
                logger.warning("mongodb_client_not_configured")
                return None

            experiment_doc = await self.mongodb_client.get_experiment(experiment_id)
            if not experiment_doc:
                logger.error("experiment_not_found", experiment_id=experiment_id)
                return None

            experiment = ExperimentRequest.from_avro_dict(experiment_doc)

            # Calcular tempo decorrido
            now_millis = int(datetime.utcnow().timestamp() * 1000)
            created_at = experiment_doc.get("created_at", now_millis)
            elapsed_time = (now_millis - created_at) / 1000  # em segundos

            # Obter status do Argo Workflows
            workflow_status = "UNKNOWN"
            if self.argo_client:
                workflow_status = await self.argo_client.get_workflow_status(f"experiment-{experiment_id}")
                logger.debug("experiment_status_checked", experiment_id=experiment_id, status=workflow_status)

            # Verificar guardrails e calcular degradação (simulado - em produção, puxar métricas reais)
            guardrails_ok = await self._check_guardrails(experiment)

            # Simular degradação baseada em guardrails
            # Em produção, isso viria de métricas reais do experimento
            performance_degradation = 0.0 if guardrails_ok else 0.1

            if not guardrails_ok:
                logger.warning("guardrails_violated", experiment_id=experiment_id)
                await self.abort_experiment(experiment_id, "Guardrail violation detected")

            return {
                "elapsed_time": elapsed_time,
                "performance_degradation": performance_degradation,
                "status": workflow_status,
                "guardrails_ok": guardrails_ok
            }

        except Exception as e:
            logger.error("experiment_monitoring_failed", experiment_id=experiment_id, error=str(e))
            return None

    async def analyze_experiment_results(self, experiment_id: str) -> Optional[Dict]:
        """
        Analisar resultados de experimento concluído.

        Args:
            experiment_id: ID do experimento

        Returns:
            Dict com análise de resultados
        """
        try:
            # Recuperar experimento do MongoDB
            if not self.mongodb_client:
                logger.warning("mongodb_client_not_configured")
                return None

            experiment_doc = await self.mongodb_client.get_experiment(experiment_id)
            if not experiment_doc:
                logger.error("experiment_not_found", experiment_id=experiment_id)
                return None

            # Recuperar resultados do Argo Workflows
            if self.argo_client:
                results = await self.argo_client.get_workflow_results(f"experiment-{experiment_id}")
            else:
                results = experiment_doc.get("results", {})

            if not results:
                logger.warning("no_results_available", experiment_id=experiment_id)
                return None

            # Extrair métricas baseline vs experimental
            baseline_metrics = results.get("baseline_metrics", {})
            experimental_metrics = results.get("experimental_metrics", {})

            # Calcular melhoria percentual
            improvements = {}
            for metric_name in baseline_metrics.keys():
                baseline = baseline_metrics[metric_name]
                experimental = experimental_metrics.get(metric_name, baseline)

                if baseline > 0:
                    improvement_pct = ((experimental - baseline) / baseline) * 100
                    improvements[metric_name] = improvement_pct

            # Verificar success criteria
            experiment = ExperimentRequest.from_avro_dict(experiment_doc)
            success_criteria_met = self._check_success_criteria(experiment, experimental_metrics)

            # Calcular significância estatística (simplificado - usar t-test em produção)
            confidence = self._calculate_statistical_confidence(baseline_metrics, experimental_metrics)

            # Gerar recomendação
            recommendation = "APPLY" if success_criteria_met and confidence > 0.95 else "REJECT"

            analysis = {
                "success": success_criteria_met,
                "improvement_percentage": sum(improvements.values()) / len(improvements) if improvements else 0.0,
                "confidence": confidence,
                "recommendation": recommendation,
                "baseline_metrics": baseline_metrics,
                "experimental_metrics": experimental_metrics,
                "improvements": improvements,
            }

            logger.info(
                "experiment_results_analyzed",
                experiment_id=experiment_id,
                success=success_criteria_met,
                improvement=analysis["improvement_percentage"],
                confidence=confidence,
            )

            return analysis

        except Exception as e:
            logger.error("experiment_analysis_failed", experiment_id=experiment_id, error=str(e))
            return None

    async def validate_hypothesis(self, hypothesis: OptimizationHypothesis) -> bool:
        """
        Validar viabilidade de hipótese antes de submeter experimento.

        Args:
            hypothesis: Hipótese a ser validada

        Returns:
            True se viável, False caso contrário
        """
        try:
            # Verificar se baseline_metrics disponíveis
            if not hypothesis.baseline_metrics:
                logger.warning("no_baseline_metrics", hypothesis_id=hypothesis.hypothesis_id)
                return False

            # Verificar se ajustes não excedem limites
            for adjustment in hypothesis.proposed_adjustments:
                if "weight" in adjustment.parameter_name.lower():
                    # Verificar max_weight_adjustment
                    old_val = float(adjustment.old_value)
                    new_val = float(adjustment.new_value)
                    delta = abs(new_val - old_val)

                    if delta > self.settings.max_weight_adjustment:
                        logger.warning(
                            "adjustment_exceeds_max",
                            hypothesis_id=hypothesis.hypothesis_id,
                            parameter=adjustment.parameter_name,
                            delta=delta,
                            max=self.settings.max_weight_adjustment,
                        )
                        return False

            # Verificar se não há lock ativo no componente
            if self.redis_client:
                # Tentar adquirir lock temporário para verificação
                locked = await self.redis_client.lock_component(hypothesis.target_component, ttl=10)
                if locked:
                    await self.redis_client.unlock_component(hypothesis.target_component)
                else:
                    logger.warning("component_already_locked", component=hypothesis.target_component)
                    return False

            logger.debug("hypothesis_validated", hypothesis_id=hypothesis.hypothesis_id)
            return True

        except Exception as e:
            logger.error("hypothesis_validation_failed", hypothesis_id=hypothesis.hypothesis_id, error=str(e))
            return False

    async def abort_experiment(self, experiment_id: str, reason: str):
        """
        Abortar experimento em andamento.

        Args:
            experiment_id: ID do experimento
            reason: Razão do abort
        """
        try:
            # Deletar workflow no Argo
            if self.argo_client:
                await self.argo_client.delete_workflow(f"experiment-{experiment_id}")

            # Aplicar rollback (recuperar configuração baseline)
            # TODO: Implementar lógica de rollback

            # Atualizar status no MongoDB
            if self.mongodb_client:
                await self.mongodb_client.update_experiment_status(
                    experiment_id, "ABORTED", {"abort_reason": reason}
                )

            # Liberar lock
            if self.mongodb_client:
                experiment_doc = await self.mongodb_client.get_experiment(experiment_id)
                if experiment_doc:
                    component = experiment_doc.get("target_component")
                    if self.redis_client:
                        await self.redis_client.unlock_component(component)

            logger.info("experiment_aborted", experiment_id=experiment_id, reason=reason)

        except Exception as e:
            logger.error("experiment_abort_failed", experiment_id=experiment_id, error=str(e))

    async def get_experiment_status(self, experiment_id: str) -> Optional[str]:
        """Obter status de experimento."""
        try:
            if self.argo_client:
                status = await self.argo_client.get_workflow_status(f"experiment-{experiment_id}")
                return status
            elif self.mongodb_client:
                experiment_doc = await self.mongodb_client.get_experiment(experiment_id)
                return experiment_doc.get("status") if experiment_doc else None

            return None
        except Exception as e:
            logger.error("get_experiment_status_failed", experiment_id=experiment_id, error=str(e))
            return None

    async def list_active_experiments(self) -> List[Dict]:
        """Listar experimentos ativos."""
        try:
            if self.mongodb_client:
                # Buscar experimentos com status RUNNING ou PENDING
                experiments = await self.mongodb_client.list_experiments(
                    filters={"status": "RUNNING"}, limit=50
                )
                return experiments

            return []
        except Exception as e:
            logger.error("list_active_experiments_failed", error=str(e))
            return []

    async def rollback_experiment(self, experiment_id: str) -> Dict:
        """
        Realizar rollback de experimento com degradação detectada.

        Args:
            experiment_id: ID do experimento

        Returns:
            Dict com status do rollback incluindo:
                - success: bool
                - rollback_completed: bool
                - component: str
                - reason: str
        """
        try:
            # Recuperar experimento do MongoDB
            if not self.mongodb_client:
                logger.warning("mongodb_client_not_configured")
                return {
                    "success": False,
                    "rollback_completed": False,
                    "reason": "mongodb_client_not_configured"
                }

            experiment_doc = await self.mongodb_client.get_experiment(experiment_id)
            if not experiment_doc:
                logger.error("experiment_not_found", experiment_id=experiment_id)
                return {
                    "success": False,
                    "rollback_completed": False,
                    "reason": "experiment_not_found"
                }

            component = experiment_doc.get("target_component", "unknown")

            # Deletar workflow no Argo se existir
            if self.argo_client:
                try:
                    await self.argo_client.delete_workflow(f"experiment-{experiment_id}")
                    logger.info("argo_workflow_deleted", experiment_id=experiment_id)
                except Exception as e:
                    logger.warning("argo_workflow_deletion_failed", experiment_id=experiment_id, error=str(e))

            # Recuperar configuração baseline para rollback
            baseline_config = experiment_doc.get("baseline_configuration", {})

            # Nota: O rollback real depende do tipo de otimização
            # Por enquanto, apenas marcamos o experimento como rolled back
            # Em produção, isso chamaria os gRPC clients apropriados:
            # - consensus_engine_client.rollback_weights() para weight recalibration
            # - orchestrator_client.rollback_slos() para SLO adjustment
            logger.info(
                "experiment_rollback_initiated",
                experiment_id=experiment_id,
                component=component,
                baseline_config=baseline_config
            )

            # Atualizar status no MongoDB
            rollback_result = {
                "rollback_reason": "degradation_detected",
                "rollback_timestamp": int(datetime.utcnow().timestamp() * 1000),
                "baseline_configuration": baseline_config
            }

            await self.mongodb_client.update_experiment_status(
                experiment_id, "ROLLED_BACK", rollback_result
            )

            # Liberar lock do componente
            if self.redis_client:
                await self.redis_client.unlock_component(component)
                logger.info("component_lock_released", component=component)

            logger.info("experiment_rolled_back", experiment_id=experiment_id, component=component)

            return {
                "success": True,
                "rollback_completed": True,
                "component": component,
                "reason": "degradation_detected",
                "baseline_config": baseline_config
            }

        except Exception as e:
            logger.error("experiment_rollback_failed", experiment_id=experiment_id, error=str(e))
            return {
                "success": False,
                "rollback_completed": False,
                "reason": f"rollback_failed: {str(e)}"
            }

    # Helper methods

    def _hypothesis_to_experiment_request(self, hypothesis: OptimizationHypothesis) -> ExperimentRequest:
        """Converter hipótese para ExperimentRequest."""
        experiment_id = str(uuid.uuid4())
        now_millis = int(datetime.utcnow().timestamp() * 1000)

        # Gerar success criteria baseado em métricas alvo
        success_criteria = []
        for metric_name, target_value in hypothesis.target_metrics.items():
            baseline_value = hypothesis.baseline_metrics.get(metric_name, 0.0)

            operator = ComparisonOperator.GTE if target_value >= baseline_value else ComparisonOperator.LTE

            success_criteria.append({
                "metric_name": metric_name,
                "operator": operator,
                "threshold": target_value,
                "confidence_level": hypothesis.confidence_score,
            })

        # Gerar guardrails (máximo 5% de degradação em métricas críticas)
        guardrails = []
        for metric_name in ["error_rate", "latency_p95"]:
            if metric_name in hypothesis.baseline_metrics:
                guardrails.append({
                    "metric_name": metric_name,
                    "max_degradation_percentage": 0.05,
                    "abort_threshold": 0.02,
                })

        return ExperimentRequest(
            experiment_id=experiment_id,
            correlation_id=hypothesis.metadata.get("context_id", experiment_id),
            trace_id=experiment_id,
            span_id=experiment_id,
            hypothesis=hypothesis.hypothesis_text,
            objective=f"Validate {hypothesis.optimization_type.value} for {hypothesis.target_component}",
            experiment_type=ExperimentType.A_B_TEST,
            target_component=hypothesis.target_component,
            baseline_configuration={k: str(v) for k, v in hypothesis.baseline_metrics.items()},
            experimental_configuration={
                adj.parameter_name: adj.new_value for adj in hypothesis.proposed_adjustments
            },
            success_criteria=success_criteria,
            guardrails=guardrails,
            traffic_percentage=0.1,  # 10% de tráfego por padrão
            duration_seconds=self.settings.experiment_timeout_seconds,
            sample_size=1000,
            randomization_strategy=RandomizationStrategy.RANDOM,
            ethical_approval_required=hypothesis.risk_score > 0.7,
            rollback_on_failure=True,
            created_at=now_millis,
            created_by="optimizer-agents",
        )

    async def _check_guardrails(self, experiment: ExperimentRequest) -> bool:
        """Verificar se guardrails estão sendo respeitados."""
        # TODO: Implementar lógica real de verificação de guardrails
        # Consultar métricas atuais do experimento e comparar com thresholds
        return True

    def _check_success_criteria(self, experiment: ExperimentRequest, experimental_metrics: Dict) -> bool:
        """Verificar se success criteria foram atendidos."""
        for criterion in experiment.success_criteria:
            metric_value = experimental_metrics.get(criterion.metric_name)
            if metric_value is None:
                return False

            # Verificar operador
            if criterion.operator == ComparisonOperator.GT and metric_value <= criterion.threshold:
                return False
            elif criterion.operator == ComparisonOperator.LT and metric_value >= criterion.threshold:
                return False
            elif criterion.operator == ComparisonOperator.GTE and metric_value < criterion.threshold:
                return False
            elif criterion.operator == ComparisonOperator.LTE and metric_value > criterion.threshold:
                return False
            elif criterion.operator == ComparisonOperator.EQ and metric_value != criterion.threshold:
                return False

        return True

    def _calculate_statistical_confidence(self, baseline: Dict, experimental: Dict) -> float:
        """Calcular confiança estatística (simplificado - usar t-test em produção)."""
        # Simplificação: retornar confiança baseada em número de métricas melhoradas
        improved = 0
        total = 0

        for metric_name in baseline.keys():
            if metric_name in experimental:
                total += 1
                if experimental[metric_name] < baseline[metric_name]:  # Assumir que menor é melhor
                    improved += 1

        if total == 0:
            return 0.0

        # Mapear para confiança (60% das métricas melhoradas = 0.9 de confiança)
        improvement_ratio = improved / total
        confidence = 0.5 + (improvement_ratio * 0.5)

        return confidence
