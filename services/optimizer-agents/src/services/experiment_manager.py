import uuid
from datetime import datetime
from typing import Dict, List, Optional

import structlog

from src.config.settings import get_settings
from src.models.experiment_request import ComparisonOperator, ExperimentRequest, ExperimentType, RandomizationStrategy
from src.models.optimization_hypothesis import OptimizationHypothesis
from src.experimentation.ab_testing_engine import ABTestingEngine
from src.experimentation.guardrails import GuardrailMonitor
from src.experimentation.sample_size_calculator import SampleSizeCalculator
from src.experimentation.randomization import RandomizationStrategyType

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

        # Inicializar ABTestingEngine para A/B tests
        self.ab_testing_engine = ABTestingEngine(
            settings=self.settings,
            mongodb_client=mongodb_client,
            redis_client=redis_client,
        )

        # Inicializar GuardrailMonitor para verificacao automatica de guardrails
        self.guardrail_monitor = GuardrailMonitor(
            mongodb_client=mongodb_client,
            redis_client=redis_client,
            min_sample_size=self.settings.ab_test_min_sample_size if hasattr(self.settings, 'ab_test_min_sample_size') else 100,
        )

        # Inicializar SampleSizeCalculator para calculo de tamanho de amostra
        self.sample_calculator = SampleSizeCalculator()

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

            # Converter hipótese para ExperimentRequest (com calculo de sample_size via SampleSizeCalculator)
            experiment_request = self._hypothesis_to_experiment_request(hypothesis)

            # Validar se sample_size calculado e suficiente
            sample_size_validation = self._validate_calculated_sample_size(experiment_request)
            if not sample_size_validation["is_valid"]:
                logger.error(
                    "insufficient_sample_size",
                    experiment_id=experiment_request.experiment_id,
                    required=sample_size_validation["required"],
                    reason=sample_size_validation["reason"],
                )
                if self.redis_client:
                    await self.redis_client.unlock_component(hypothesis.target_component)
                return None

            # Validar guardrails e success criteria
            if not experiment_request.validate_guardrails():
                logger.error("invalid_guardrails", experiment_id=experiment_request.experiment_id)
                if self.redis_client:
                    await self.redis_client.unlock_component(hypothesis.target_component)
                return None

            # Solicitar aprovação de compliance se necessário
            if experiment_request.ethical_approval_required:
                logger.info("ethical_approval_required", experiment_id=experiment_request.experiment_id)
                experiment_request.approved_by_compliance = False  # Pendente

            # Para A/B tests, criar o teste via ABTestingEngine
            if experiment_request.experiment_type == ExperimentType.A_B_TEST:
                ab_test_config = await self._create_ab_test_from_request(experiment_request, hypothesis)
                logger.info(
                    "ab_test_created_via_engine",
                    experiment_id=experiment_request.experiment_id,
                    ab_test_id=ab_test_config.experiment_id,
                    minimum_sample_size=ab_test_config.minimum_sample_size,
                )

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
                sample_size=experiment_request.sample_size,
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

        Verifica guardrails continuamente via GuardrailMonitor e aborta se violados.

        Args:
            experiment_id: ID do experimento

        Returns:
            Dict com status do experimento incluindo:
                - elapsed_time: tempo decorrido em segundos
                - performance_degradation: percentual de degradação (0.0 a 1.0)
                - status: status atual do workflow
                - sample_progress: progresso em relacao ao tamanho de amostra calculado
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

            # Obter metricas coletadas para verificacao de guardrails
            control_metrics = {}
            treatment_metrics = {}
            current_sample_size = 0

            if self.redis_client:
                # Coletar metricas do Redis para grupos control e treatment
                control_metrics = await self._get_experiment_metrics(experiment_id, "control")
                treatment_metrics = await self._get_experiment_metrics(experiment_id, "treatment")

                # Calcular tamanho atual da amostra
                control_size = await self._get_group_size(experiment_id, "control")
                treatment_size = await self._get_group_size(experiment_id, "treatment")
                current_sample_size = min(control_size, treatment_size)

            # Converter guardrails para formato esperado pelo GuardrailMonitor
            guardrails_config = experiment.guardrails if hasattr(experiment, 'guardrails') else []

            # Verificar guardrails via GuardrailMonitor
            guardrail_result = await self.guardrail_monitor.should_abort(
                experiment_id=experiment_id,
                guardrails_config=guardrails_config,
                control_metrics=control_metrics,
                treatment_metrics=treatment_metrics,
                current_sample_size=current_sample_size,
            )

            guardrails_ok = not guardrail_result["should_abort"]

            # Calcular degradacao de performance baseada nas violacoes de guardrails
            performance_degradation = 0.0
            if guardrail_result.get("violations"):
                # Usar a maior degradacao encontrada
                for violation in guardrail_result["violations"]:
                    degradation_str = violation.get("degradation", "0%")
                    degradation_val = float(degradation_str.rstrip('%')) / 100
                    performance_degradation = max(performance_degradation, degradation_val)

            # Abortar automaticamente se guardrails indicarem abort
            if guardrail_result["should_abort"]:
                logger.warning(
                    "guardrails_violated_aborting",
                    experiment_id=experiment_id,
                    reason=guardrail_result["reason"],
                )
                await self.abort_experiment(experiment_id, guardrail_result["reason"])

            # Calcular progresso em relacao ao tamanho de amostra requerido
            required_sample_size = experiment.sample_size if hasattr(experiment, 'sample_size') else 1000
            sample_progress = {
                "current": current_sample_size,
                "required": required_sample_size,
                "percentage": min((current_sample_size / required_sample_size) * 100, 100) if required_sample_size > 0 else 0,
                "is_sufficient": current_sample_size >= required_sample_size,
            }

            return {
                "elapsed_time": elapsed_time,
                "performance_degradation": performance_degradation,
                "status": workflow_status,
                "guardrails_ok": guardrails_ok,
                "guardrail_details": guardrail_result,
                "sample_progress": sample_progress,
            }

        except Exception as e:
            logger.error("experiment_monitoring_failed", experiment_id=experiment_id, error=str(e))
            return None

    async def analyze_experiment_results(self, experiment_id: str) -> Optional[Dict]:
        """
        Analisar resultados de experimento concluído.

        Delega a analise para ABTestingEngine.analyze_results() para A/B tests,
        que fornece analise estatistica completa incluindo testes frequentistas
        e Bayesianos.

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

            experiment = ExperimentRequest.from_avro_dict(experiment_doc)

            # Para A/B tests, delegar analise para ABTestingEngine
            experiment_type = experiment_doc.get("experiment_type", "")
            if experiment_type == "A_B_TEST" or (hasattr(experiment, 'experiment_type') and experiment.experiment_type == ExperimentType.A_B_TEST):
                ab_results = await self.ab_testing_engine.analyze_results(experiment_id)

                # Converter ABTestResults para formato de dicionario
                analysis = {
                    "success": ab_results.statistical_recommendation == "APPLY",
                    "improvement_percentage": self._calculate_improvement_from_ab_results(ab_results),
                    "confidence": ab_results.confidence_level,
                    "recommendation": ab_results.statistical_recommendation,
                    "primary_metrics_analysis": ab_results.primary_metrics_analysis,
                    "secondary_metrics_analysis": ab_results.secondary_metrics_analysis,
                    "bayesian_analysis": ab_results.bayesian_analysis,
                    "guardrails_status": ab_results.guardrails_status,
                    "control_size": ab_results.control_size,
                    "treatment_size": ab_results.treatment_size,
                    "early_stopped": ab_results.early_stopped,
                    "early_stop_reason": ab_results.early_stop_reason,
                }

                logger.info(
                    "ab_test_results_analyzed_via_engine",
                    experiment_id=experiment_id,
                    recommendation=ab_results.statistical_recommendation,
                    confidence=ab_results.confidence_level,
                    control_size=ab_results.control_size,
                    treatment_size=ab_results.treatment_size,
                )

                return analysis

            # Fallback para outros tipos de experimento (nao A/B test)
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
            success_criteria_met = self._check_success_criteria(experiment, experimental_metrics)

            # Calcular significância estatística (simplificado)
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
        """
        Converter hipótese para ExperimentRequest.

        Utiliza SampleSizeCalculator para definir sample_size com base em
        baseline/MDE/power/alpha ao inves de valor constante.
        """
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

        # Calcular sample_size via SampleSizeCalculator com base nas metricas da hipotese
        sample_size = self._calculate_required_sample_size(hypothesis)

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
            sample_size=sample_size,
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

    def _calculate_required_sample_size(self, hypothesis: OptimizationHypothesis) -> int:
        """
        Calcular tamanho de amostra necessario via SampleSizeCalculator.

        Usa baseline/MDE/power/alpha para determinar sample_size estatisticamente
        valido ao inves de valor constante.

        Args:
            hypothesis: Hipotese com metricas baseline e targets

        Returns:
            sample_size calculado por grupo
        """
        # Parametros padroes de teste estatistico
        alpha = getattr(self.settings, 'ab_test_default_alpha', 0.05)
        power = getattr(self.settings, 'ab_test_default_power', 0.80)
        default_mde_percentage = 0.05  # 5% MDE padrao

        max_sample_size = 0

        # Calcular sample_size para cada metrica primaria
        for metric_name, target_value in hypothesis.target_metrics.items():
            baseline_value = hypothesis.baseline_metrics.get(metric_name, 0.0)

            if baseline_value == 0:
                continue

            # Calcular MDE baseado na diferenca entre target e baseline
            mde_absolute = abs(target_value - baseline_value)
            if mde_absolute == 0:
                mde_absolute = baseline_value * default_mde_percentage

            try:
                # Determinar se metrica e binaria (taxa entre 0 e 1) ou continua
                is_binary = self._is_binary_metric(metric_name, baseline_value)

                if is_binary:
                    # Metrica binaria (ex: error_rate, conversion_rate)
                    result = self.sample_calculator.calculate_for_binary(
                        baseline_rate=baseline_value,
                        mde=mde_absolute,
                        alpha=alpha,
                        power=power,
                    )
                else:
                    # Metrica continua (ex: latency, throughput)
                    # Estimar std_dev como 30% do baseline (heuristica comum)
                    std_dev = baseline_value * 0.3 if baseline_value > 0 else 1.0
                    result = self.sample_calculator.calculate_for_continuous(
                        baseline_mean=baseline_value,
                        mde=mde_absolute,
                        std_dev=std_dev,
                        alpha=alpha,
                        power=power,
                    )

                max_sample_size = max(max_sample_size, result.sample_size_per_group)

                logger.debug(
                    "sample_size_calculated_for_metric",
                    metric_name=metric_name,
                    baseline=baseline_value,
                    mde=mde_absolute,
                    sample_size=result.sample_size_per_group,
                )

            except Exception as e:
                logger.warning(
                    "sample_size_calculation_failed",
                    metric_name=metric_name,
                    error=str(e),
                )

        # Garantir minimo de 100 amostras por grupo
        min_sample_size = getattr(self.settings, 'ab_test_min_sample_size', 100)
        return max(max_sample_size, min_sample_size)

    def _is_binary_metric(self, metric_name: str, value: float) -> bool:
        """
        Determinar se metrica e binaria baseado no nome ou valor.

        Args:
            metric_name: Nome da metrica
            value: Valor baseline da metrica

        Returns:
            True se metrica for binaria, False caso contrario
        """
        # Sufixos que indicam metricas binarias
        binary_suffixes = ['_rate', '_ratio', '_percentage', '_pct', '_conversion']
        binary_prefixes = ['error_', 'success_', 'failure_', 'conversion_']

        metric_lower = metric_name.lower()

        # Verificar por nome
        for suffix in binary_suffixes:
            if metric_lower.endswith(suffix):
                return True

        for prefix in binary_prefixes:
            if metric_lower.startswith(prefix):
                return True

        # Verificar por valor (taxas tipicamente entre 0 e 1)
        if 0 < value < 1:
            return True

        return False

    def _validate_calculated_sample_size(self, experiment_request: ExperimentRequest) -> Dict:
        """
        Validar se sample_size calculado atende aos requisitos minimos.

        Args:
            experiment_request: Request do experimento com sample_size

        Returns:
            Dict com is_valid, required e reason
        """
        min_sample_size = getattr(self.settings, 'ab_test_min_sample_size', 100)
        sample_size = experiment_request.sample_size

        if sample_size < min_sample_size:
            return {
                "is_valid": False,
                "required": min_sample_size,
                "current": sample_size,
                "reason": f"sample_size {sample_size} e menor que minimo requerido {min_sample_size}",
            }

        return {
            "is_valid": True,
            "required": sample_size,
            "current": sample_size,
            "reason": "sample_size atende aos requisitos",
        }

    async def _create_ab_test_from_request(
        self,
        experiment_request: ExperimentRequest,
        hypothesis: OptimizationHypothesis,
    ):
        """
        Criar A/B test via ABTestingEngine a partir de ExperimentRequest.

        Args:
            experiment_request: Request do experimento
            hypothesis: Hipotese original

        Returns:
            ABTestConfig criado
        """
        # Extrair metricas primarias dos success criteria
        primary_metrics = [
            criterion["metric_name"]
            for criterion in experiment_request.success_criteria
            if isinstance(criterion, dict)
        ]

        # Se success_criteria for lista de objetos SuccessCriterion
        if not primary_metrics and experiment_request.success_criteria:
            primary_metrics = [
                getattr(criterion, 'metric_name', '')
                for criterion in experiment_request.success_criteria
                if hasattr(criterion, 'metric_name')
            ]

        # Extrair guardrails
        guardrails_config = []
        if hasattr(experiment_request, 'guardrails'):
            for guardrail in experiment_request.guardrails:
                if isinstance(guardrail, dict):
                    guardrails_config.append(guardrail)
                elif hasattr(guardrail, 'metric_name'):
                    guardrails_config.append({
                        "metric_name": guardrail.metric_name,
                        "max_degradation_percentage": getattr(guardrail, 'max_degradation_percentage', 0.05),
                        "abort_threshold": getattr(guardrail, 'abort_threshold', 0.10),
                    })

        # Mapear estrategia de randomizacao
        strategy = RandomizationStrategyType.RANDOM
        if hasattr(experiment_request, 'randomization_strategy'):
            strategy_map = {
                RandomizationStrategy.RANDOM: RandomizationStrategyType.RANDOM,
                RandomizationStrategy.STRATIFIED: RandomizationStrategyType.STRATIFIED,
                RandomizationStrategy.BLOCK: RandomizationStrategyType.BLOCK,
            }
            strategy = strategy_map.get(
                experiment_request.randomization_strategy,
                RandomizationStrategyType.RANDOM,
            )

        # Criar A/B test via engine
        ab_config = await self.ab_testing_engine.create_ab_test(
            name=f"experiment-{experiment_request.experiment_id}",
            hypothesis=experiment_request.hypothesis,
            primary_metrics=primary_metrics if primary_metrics else ["default_metric"],
            traffic_split=0.5,  # 50/50 entre control e treatment
            randomization_strategy=strategy,
            secondary_metrics=[],
            guardrails=guardrails_config,
            minimum_sample_size=experiment_request.sample_size,
            maximum_duration_seconds=experiment_request.duration_seconds,
            early_stopping_enabled=True,
            bayesian_analysis_enabled=True,
            created_by=experiment_request.created_by,
            metadata={
                "original_experiment_id": experiment_request.experiment_id,
                "hypothesis_id": hypothesis.hypothesis_id,
                "target_component": hypothesis.target_component,
            },
        )

        return ab_config

    async def _get_experiment_metrics(self, experiment_id: str, group: str) -> Dict[str, List[float]]:
        """
        Obter metricas coletadas para um grupo do experimento.

        Args:
            experiment_id: ID do experimento
            group: Grupo ("control" ou "treatment")

        Returns:
            Dict com metricas e seus valores coletados
        """
        if not self.redis_client:
            return {}

        metrics = {}

        try:
            # Buscar todas as chaves de metricas para este grupo
            pattern = f"ab_test:{experiment_id}:metrics:{group}:*"
            keys = await self.redis_client.keys(pattern)

            for key in keys:
                # Extrair nome da metrica da chave
                parts = key.split(":")
                if len(parts) >= 5:
                    metric_name = parts[4]

                    # Obter valores
                    values = await self.redis_client.lrange(key, 0, -1)
                    metrics[metric_name] = [float(v) for v in values]

        except Exception as e:
            logger.warning("failed_to_get_experiment_metrics", error=str(e))

        return metrics

    async def _get_group_size(self, experiment_id: str, group: str) -> int:
        """
        Obter tamanho do grupo de um experimento.

        Args:
            experiment_id: ID do experimento
            group: Grupo ("control" ou "treatment")

        Returns:
            Tamanho do grupo
        """
        if not self.redis_client:
            return 0

        try:
            key = f"ab_test:{experiment_id}:group_size:{group}"
            value = await self.redis_client.get(key)
            return int(value) if value else 0
        except Exception:
            return 0

    def _calculate_improvement_from_ab_results(self, ab_results) -> float:
        """
        Calcular percentual de melhoria medio dos resultados de A/B test.

        Args:
            ab_results: ABTestResults do ABTestingEngine

        Returns:
            Percentual de melhoria medio
        """
        if not ab_results.primary_metrics_analysis:
            return 0.0

        improvements = []
        for analysis in ab_results.primary_metrics_analysis:
            control_mean = analysis.get("control_mean", 0)
            treatment_mean = analysis.get("treatment_mean", 0)

            if control_mean != 0:
                improvement = ((treatment_mean - control_mean) / abs(control_mean)) * 100
                improvements.append(improvement)

        return sum(improvements) / len(improvements) if improvements else 0.0
