from typing import Dict, Optional

from prometheus_client import Counter, Gauge, Histogram


class OptimizerMetrics:
    """Prometheus metrics for Optimizer Agents."""

    def __init__(self, service_name: str = "optimizer-agents", component: str = "optimizer", layer: str = "estrategica"):
        self.service_name = service_name
        self.component = component
        self.layer = layer

        # Counters
        self.hypotheses_generated_total = Counter(
            "optimizer_hypotheses_generated_total",
            "Total number of hypotheses generated",
            ["optimization_type"],
        )

        self.experiments_submitted_total = Counter(
            "optimizer_experiments_submitted_total", "Total experiments submitted", ["experiment_type"]
        )

        self.experiments_successful_total = Counter(
            "optimizer_experiments_successful_total", "Successful experiments", ["experiment_type"]
        )

        self.experiments_failed_total = Counter(
            "optimizer_experiments_failed_total", "Failed experiments", ["experiment_type"]
        )

        self.experiments_aborted_total = Counter(
            "optimizer_experiments_aborted_total", "Aborted experiments", ["experiment_type"]
        )

        self.optimizations_applied_total = Counter(
            "optimizer_optimizations_applied_total",
            "Total optimizations applied",
            ["optimization_type", "component"],
        )

        self.optimizations_rolled_back_total = Counter(
            "optimizer_optimizations_rolled_back_total",
            "Total rollbacks",
            ["optimization_type", "component"],
        )

        self.weight_adjustments_total = Counter(
            "optimizer_weight_adjustments_total", "Total weight adjustments", ["component"]
        )

        self.slo_adjustments_total = Counter(
            "optimizer_slo_adjustments_total", "Total SLO adjustments", ["service"]
        )

        self.insights_consumed_total = Counter(
            "optimizer_insights_consumed_total", "Total insights consumed from Kafka"
        )

        self.telemetry_consumed_total = Counter(
            "optimizer_telemetry_consumed_total", "Total telemetry consumed from Kafka"
        )

        self.causal_analyses_requested_total = Counter(
            "optimizer_causal_analyses_requested_total", "Total causal analyses requested"
        )

        # Gauges
        self.experiments_active = Gauge("optimizer_experiments_active", "Active experiments")

        self.optimization_success_rate = Gauge(
            "optimizer_optimization_success_rate", "Success rate of optimizations (0.0-1.0)"
        )

        self.average_improvement_percentage = Gauge(
            "optimizer_average_improvement_percentage", "Average improvement percentage"
        )

        self.q_table_size = Gauge("optimizer_q_table_size", "Size of Q-table for RL")

        self.epsilon_value = Gauge("optimizer_epsilon_value", "Current epsilon value for exploration")

        # Histograms
        self.experiment_duration_seconds = Histogram(
            "optimizer_experiment_duration_seconds",
            "Duration of experiments in seconds",
            buckets=(60, 300, 600, 1800, 3600),
        )

        self.optimization_processing_duration_seconds = Histogram(
            "optimizer_optimization_processing_duration_seconds",
            "Processing duration for optimizations",
            buckets=(0.1, 0.5, 1, 5, 10),
        )

        self.hypothesis_generation_duration_seconds = Histogram(
            "optimizer_hypothesis_generation_duration_seconds",
            "Duration of hypothesis generation",
            buckets=(0.1, 0.5, 1, 2, 5),
        )

        self.weight_adjustment_magnitude = Histogram(
            "optimizer_weight_adjustment_magnitude",
            "Magnitude of weight adjustments",
            buckets=(0.01, 0.05, 0.1, 0.2),
        )

        self.slo_adjustment_percentage = Histogram(
            "optimizer_slo_adjustment_percentage", "Percentage of SLO adjustments", buckets=(0.01, 0.05, 0.1, 0.2)
        )

        # ML Subsystem Metrics
        # Counters para ML
        self.load_predictions_total = Counter(
            "optimizer_load_predictions_total", "Total load predictions generated", ["horizon", "status"]
        )

        self.scheduling_optimizations_applied_total = Counter(
            "optimizer_scheduling_optimizations_applied_total", "Total scheduling optimizations applied", ["action"]
        )

        self.ml_model_loads_total = Counter(
            "optimizer_ml_model_loads_total", "Total ML model loads", ["model_name", "status"]
        )

        self.ml_training_runs_total = Counter(
            "optimizer_ml_training_runs_total", "Total ML training runs", ["model_type", "status"]
        )

        self.ml_cache_hits_total = Counter(
            "optimizer_ml_cache_hits_total", "Total ML cache hits", ["cache_name"]
        )

        self.ml_cache_misses_total = Counter(
            "optimizer_ml_cache_misses_total", "Total ML cache misses", ["cache_name"]
        )

        # Gauges para ML
        self.load_forecast_accuracy_mape = Gauge(
            "optimizer_load_forecast_accuracy_mape", "Load forecast MAPE (Mean Absolute Percentage Error)"
        )

        self.scheduling_policy_average_reward = Gauge(
            "optimizer_scheduling_policy_average_reward", "Average reward of scheduling policy"
        )

        self.ml_model_age_seconds = Gauge(
            "optimizer_ml_model_age_seconds", "Age of currently loaded ML model in seconds", ["model_name"]
        )

        # Histograms para ML
        self.ml_model_load_duration_seconds = Histogram(
            "optimizer_ml_model_load_duration_seconds",
            "Duration of ML model loading in seconds",
            buckets=(0.1, 0.5, 1, 5, 10, 30),
        )

        self.ml_prediction_duration_seconds = Histogram(
            "optimizer_ml_prediction_duration_seconds",
            "Duration of ML predictions in seconds",
            buckets=(0.01, 0.05, 0.1, 0.5, 1, 5),
        )

        self.ml_training_duration_seconds = Histogram(
            "optimizer_ml_training_duration_seconds",
            "Duration of ML training in seconds",
            buckets=(60, 300, 600, 1800, 3600, 7200),
        )

        self.scheduling_optimization_duration_seconds = Histogram(
            "optimizer_scheduling_optimization_duration_seconds",
            "Duration of scheduling optimization in seconds",
            buckets=(0.01, 0.05, 0.1, 0.5, 1),
        )

        # Métricas para Consensus Optimization (extensões gRPC)
        self.consensus_weight_updates_total = Counter(
            "optimizer_consensus_weight_updates_total",
            "Total de atualizações de peso aplicadas via gRPC",
            ["specialist_type", "status"],
        )

        self.consensus_weight_rollbacks_total = Counter(
            "optimizer_consensus_weight_rollbacks_total",
            "Total de rollbacks de peso",
            ["optimization_id"],
        )

        self.consensus_weight_validations_total = Counter(
            "optimizer_consensus_weight_validations_total",
            "Total de validações de peso",
            ["result"],
        )

        # Métricas para Orchestrator Optimization (extensões gRPC)
        self.orchestrator_slo_updates_total = Counter(
            "optimizer_orchestrator_slo_updates_total",
            "Total de atualizações de SLO aplicadas via gRPC",
            ["service", "status"],
        )

        self.orchestrator_slo_rollbacks_total = Counter(
            "optimizer_orchestrator_slo_rollbacks_total",
            "Total de rollbacks de SLO",
            ["optimization_id"],
        )

        self.orchestrator_slo_validations_total = Counter(
            "optimizer_orchestrator_slo_validations_total",
            "Total de validações de SLO",
            ["result"],
        )

        self.orchestrator_error_budget_queries_total = Counter(
            "optimizer_orchestrator_error_budget_queries_total",
            "Total de consultas de error budget",
            ["service"],
        )

        # Métricas RL para extensões
        self.rl_q_value_updates_total = Counter(
            "optimizer_rl_q_value_updates_total",
            "Total de atualizações de Q-value no RL",
            ["action"],
        )

        # Histogram para recompensas RL
        self.rl_reward_distribution = Histogram(
            "optimizer_rl_reward_distribution",
            "Distribuição de recompensas RL",
            buckets=(-1.0, -0.5, 0.0, 0.5, 1.0, 2.0),
        )

        # Gauges para estado atual das extensões
        self.consensus_active_weights_count = Gauge(
            "optimizer_consensus_active_weights_count",
            "Número de especialistas com pesos ativos",
        )

        self.orchestrator_active_slos_count = Gauge(
            "optimizer_orchestrator_active_slos_count",
            "Número de serviços com SLOs ativos",
        )

        # Metricas A/B Testing
        self.ab_test_assignments_total = Counter(
            "neural_hive_ab_test_assignments_total",
            "Total de atribuicoes a grupos em testes A/B",
            ["experiment_id", "group"],
        )

        self.ab_test_sample_size = Gauge(
            "neural_hive_ab_test_sample_size",
            "Tamanho atual da amostra por grupo",
            ["experiment_id", "group"],
        )

        self.ab_test_statistical_significance = Gauge(
            "neural_hive_ab_test_statistical_significance",
            "P-value do teste estatistico",
            ["experiment_id", "metric_name"],
        )

        self.ab_test_effect_size = Gauge(
            "neural_hive_ab_test_effect_size",
            "Effect size (Cohen's d)",
            ["experiment_id", "metric_name"],
        )

        self.ab_test_guardrail_violations_total = Counter(
            "neural_hive_ab_test_guardrail_violations_total",
            "Total de violacoes de guardrails",
            ["experiment_id", "metric_name"],
        )

        self.ab_test_early_stops_total = Counter(
            "neural_hive_ab_test_early_stops_total",
            "Total de paradas antecipadas",
            ["experiment_id", "reason"],
        )

        self.ab_test_probability_of_superiority = Gauge(
            "neural_hive_ab_test_probability_of_superiority",
            "Probabilidade de superioridade do treatment (Bayesiano)",
            ["experiment_id", "metric_name"],
        )

        self.ab_test_expected_lift = Gauge(
            "neural_hive_ab_test_expected_lift",
            "Lift esperado do treatment vs control",
            ["experiment_id", "metric_name"],
        )

        self.ab_test_duration_seconds = Histogram(
            "neural_hive_ab_test_duration_seconds",
            "Duracao de testes A/B em segundos",
            buckets=(3600, 86400, 172800, 604800, 1209600),
        )

        self.ab_test_analysis_duration_seconds = Histogram(
            "neural_hive_ab_test_analysis_duration_seconds",
            "Duracao da analise estatistica em segundos",
            buckets=(0.1, 0.5, 1.0, 5.0, 10.0),
        )

    def increment_counter(self, metric_name: str, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric."""
        counter = getattr(self, metric_name, None)
        if counter:
            if labels:
                counter.labels(**labels).inc()
            else:
                counter.inc()

    def set_gauge(self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge metric."""
        gauge = getattr(self, metric_name, None)
        if gauge:
            if labels:
                gauge.labels(**labels).set(value)
            else:
                gauge.set(value)

    def observe_histogram(self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Observe a histogram metric."""
        histogram = getattr(self, metric_name, None)
        if histogram:
            if labels:
                histogram.labels(**labels).observe(value)
            else:
                histogram.observe(value)

    def record_hypothesis_generated(self, optimization_type: str):
        """Record hypothesis generation."""
        self.hypotheses_generated_total.labels(optimization_type=optimization_type).inc()

    def record_experiment_submitted(self, experiment_type: str):
        """Record experiment submission."""
        self.experiments_submitted_total.labels(experiment_type=experiment_type).inc()

    def record_optimization_applied(self, optimization_type: str, component: str, improvement: float):
        """Record optimization application."""
        self.optimizations_applied_total.labels(optimization_type=optimization_type, component=component).inc()
        self.average_improvement_percentage.set(improvement)

    def record_rollback(self, optimization_type: str, component: str):
        """Record rollback."""
        self.optimizations_rolled_back_total.labels(optimization_type=optimization_type, component=component).inc()

    def record_ml_model_load(self, model_name: str, status: str, duration: float):
        """Record ML model load event."""
        self.ml_model_loads_total.labels(model_name=model_name, status=status).inc()
        self.ml_model_load_duration_seconds.observe(duration)

    def record_load_prediction(self, horizon: int, status: str, duration: float, accuracy: Optional[float]):
        """Record load prediction event."""
        self.load_predictions_total.labels(horizon=str(horizon), status=status).inc()
        self.ml_prediction_duration_seconds.observe(duration)
        if accuracy is not None:
            self.load_forecast_accuracy_mape.set(accuracy)

    def increment_cache_hit(self, cache_name: str):
        """Record cache hit."""
        self.ml_cache_hits_total.labels(cache_name=cache_name).inc()

    def increment_cache_miss(self, cache_name: str):
        """Record cache miss."""
        self.ml_cache_misses_total.labels(cache_name=cache_name).inc()

    def record_ml_training(self, model_type: str, duration: float, metrics: Dict):
        """Record ML training run."""
        status = "success" if metrics else "failed"
        self.ml_training_runs_total.labels(model_type=model_type, status=status).inc()
        self.ml_training_duration_seconds.observe(duration)

    def record_scheduling_optimization(self, action: str, duration: float, reward: float):
        """Record scheduling optimization action."""
        self.scheduling_optimizations_applied_total.labels(action=action).inc()
        self.scheduling_optimization_duration_seconds.observe(duration)
        # Update average reward (simplified - actual implementation may use exponential moving average)
        self.scheduling_policy_average_reward.set(reward)

    def record_policy_update(self, reward: float, new_q: float):
        """Record policy update in Q-learning."""
        # Track policy quality through average reward
        self.scheduling_policy_average_reward.set(reward)


def setup_metrics():
    """Configurar métricas Prometheus."""
    import structlog
    logger = structlog.get_logger()
    logger.info("prometheus_metrics_configured")
