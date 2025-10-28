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


def setup_metrics():
    """Configurar métricas Prometheus."""
    import structlog
    logger = structlog.get_logger()
    logger.info("prometheus_metrics_configured")
