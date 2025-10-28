"""Prometheus metrics for Scout Agents"""
from prometheus_client import Counter, Histogram, Gauge
from typing import Dict

# Lifecycle metrics
scout_startup_total = Counter(
    'scout_agent_startup_total',
    'Total number of Scout Agent startups'
)

scout_registered_total = Counter(
    'scout_agent_registered_total',
    'Total number of Service Registry registrations'
)

scout_heartbeat_total = Counter(
    'scout_agent_heartbeat_total',
    'Total number of heartbeats sent',
    ['status']
)

scout_deregistered_total = Counter(
    'scout_agent_deregistered_total',
    'Total number of deregistrations'
)

# Detection metrics
events_consumed_total = Counter(
    'scout_agent_events_consumed_total',
    'Total events consumed',
    ['source']
)

signals_detected_total = Counter(
    'scout_agent_signals_detected_total',
    'Total signals detected',
    ['signal_type', 'domain']
)

signals_published_total = Counter(
    'scout_agent_signals_published_total',
    'Total signals published to Kafka',
    ['signal_type', 'domain', 'channel']
)

signals_discarded_total = Counter(
    'scout_agent_signals_discarded_total',
    'Total signals discarded',
    ['reason']
)

detection_duration_seconds = Histogram(
    'scout_agent_detection_duration_seconds',
    'Time spent detecting signals',
    ['signal_type'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Scoring metrics
curiosity_score = Histogram(
    'scout_agent_curiosity_score',
    'Distribution of curiosity scores',
    ['domain'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

confidence_score = Histogram(
    'scout_agent_confidence_score',
    'Distribution of confidence scores',
    ['domain'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

relevance_score = Histogram(
    'scout_agent_relevance_score',
    'Distribution of relevance scores',
    ['domain'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

risk_score = Histogram(
    'scout_agent_risk_score',
    'Distribution of risk scores',
    ['domain'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

# Pheromone metrics
pheromones_published_total = Counter(
    'scout_agent_pheromones_published_total',
    'Total pheromones published',
    ['pheromone_type', 'domain']
)

pheromone_publish_duration_seconds = Histogram(
    'scout_agent_pheromone_publish_duration_seconds',
    'Time spent publishing pheromones',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25]
)

# Integration metrics
kafka_publish_total = Counter(
    'scout_agent_kafka_publish_total',
    'Total Kafka publish attempts',
    ['topic', 'status']
)

kafka_publish_errors_total = Counter(
    'scout_agent_kafka_publish_errors_total',
    'Total Kafka publish errors',
    ['topic', 'error_type']
)

memory_layer_requests_total = Counter(
    'scout_agent_memory_layer_requests_total',
    'Total Memory Layer API requests',
    ['operation', 'status']
)

service_registry_requests_total = Counter(
    'scout_agent_service_registry_requests_total',
    'Total Service Registry requests',
    ['operation', 'status']
)

# Performance metrics
active_detections = Gauge(
    'scout_agent_active_detections',
    'Number of detections currently in progress'
)

queue_size = Gauge(
    'scout_agent_queue_size',
    'Size of internal signal queue'
)

rate_limit_exceeded_total = Counter(
    'scout_agent_rate_limit_exceeded_total',
    'Total times rate limit was exceeded'
)


class ScoutMetrics:
    """Wrapper class for Scout Agent metrics"""

    @staticmethod
    def record_startup():
        """Record agent startup"""
        scout_startup_total.inc()

    @staticmethod
    def record_registration():
        """Record Service Registry registration"""
        scout_registered_total.inc()

    @staticmethod
    def record_heartbeat(success: bool):
        """Record heartbeat attempt"""
        status = 'success' if success else 'failure'
        scout_heartbeat_total.labels(status=status).inc()

    @staticmethod
    def record_deregistration():
        """Record deregistration"""
        scout_deregistered_total.inc()

    @staticmethod
    def record_event_consumed(source: str):
        """Record event consumption"""
        events_consumed_total.labels(source=source).inc()

    @staticmethod
    def record_signal_detected(signal_type: str, domain: str):
        """Record signal detection"""
        signals_detected_total.labels(
            signal_type=signal_type,
            domain=domain
        ).inc()

    @staticmethod
    def record_signal_published(signal_type: str, domain: str, channel: str):
        """Record signal publication"""
        signals_published_total.labels(
            signal_type=signal_type,
            domain=domain,
            channel=channel
        ).inc()

    @staticmethod
    def record_signal_discarded(reason: str):
        """Record signal discard"""
        signals_discarded_total.labels(reason=reason).inc()

    @staticmethod
    def record_detection_duration(signal_type: str, duration: float):
        """Record detection duration"""
        detection_duration_seconds.labels(signal_type=signal_type).observe(duration)

    @staticmethod
    def record_curiosity_score(domain: str, score: float):
        """Record curiosity score"""
        curiosity_score.labels(domain=domain).observe(score)

    @staticmethod
    def record_confidence_score(domain: str, score: float):
        """Record confidence score"""
        confidence_score.labels(domain=domain).observe(score)

    @staticmethod
    def record_relevance_score(domain: str, score: float):
        """Record relevance score"""
        relevance_score.labels(domain=domain).observe(score)

    @staticmethod
    def record_risk_score(domain: str, score: float):
        """Record risk score"""
        risk_score.labels(domain=domain).observe(score)

    @staticmethod
    def record_pheromone_published(pheromone_type: str, domain: str):
        """Record pheromone publication"""
        pheromones_published_total.labels(
            pheromone_type=pheromone_type,
            domain=domain
        ).inc()

    @staticmethod
    def record_pheromone_duration(duration: float):
        """Record pheromone publish duration"""
        pheromone_publish_duration_seconds.observe(duration)

    @staticmethod
    def record_kafka_publish(topic: str, success: bool):
        """Record Kafka publish attempt"""
        status = 'success' if success else 'failure'
        kafka_publish_total.labels(topic=topic, status=status).inc()

    @staticmethod
    def record_kafka_error(topic: str, error_type: str):
        """Record Kafka publish error"""
        kafka_publish_errors_total.labels(
            topic=topic,
            error_type=error_type
        ).inc()

    @staticmethod
    def record_memory_layer_request(operation: str, success: bool):
        """Record Memory Layer API request"""
        status = 'success' if success else 'failure'
        memory_layer_requests_total.labels(
            operation=operation,
            status=status
        ).inc()

    @staticmethod
    def record_service_registry_request(operation: str, success: bool):
        """Record Service Registry request"""
        status = 'success' if success else 'failure'
        service_registry_requests_total.labels(
            operation=operation,
            status=status
        ).inc()

    @staticmethod
    def set_active_detections(count: int):
        """Set active detections count"""
        active_detections.set(count)

    @staticmethod
    def set_queue_size(size: int):
        """Set queue size"""
        queue_size.set(size)

    @staticmethod
    def record_rate_limit_exceeded():
        """Record rate limit exceeded"""
        rate_limit_exceeded_total.inc()
