"""Métricas Prometheus para Execution Ticket Service."""
from prometheus_client import Counter, Histogram, Gauge, Info


class TicketServiceMetrics:
    """Métricas customizadas do serviço."""

    def __init__(self, service_name: str = 'execution-ticket-service'):
        """Inicializa métricas."""

        # Service Info
        self.service_info = Info('service', 'Service information')
        self.service_info.info({'name': service_name, 'version': '1.0.0'})

        # Tickets
        self.tickets_consumed_total = Counter(
            'tickets_consumed_total',
            'Total de tickets consumidos do Kafka'
        )
        self.tickets_persisted_total = Counter(
            'tickets_persisted_total',
            'Total de tickets persistidos (PostgreSQL + MongoDB)'
        )
        self.tickets_processing_errors_total = Counter(
            'tickets_processing_errors_total',
            'Total de erros ao processar tickets'
        )
        self.ticket_processing_duration_seconds = Histogram(
            'ticket_processing_duration_seconds',
            'Duração do processamento de tickets'
        )
        self.tickets_by_status = Gauge(
            'tickets_by_status',
            'Tickets ativos por status',
            ['status']
        )

        # API
        self.api_requests_total = Counter(
            'api_requests_total',
            'Total de requests REST API',
            ['method', 'endpoint', 'status_code']
        )
        self.api_request_duration_seconds = Histogram(
            'api_request_duration_seconds',
            'Latência de requests API'
        )
        self.api_errors_total = Counter(
            'api_errors_total',
            'Total de erros na API',
            ['endpoint']
        )

        # Webhooks
        self.webhooks_enqueued_total = Counter(
            'webhooks_enqueued_total',
            'Total de webhooks enfileirados'
        )
        self.webhooks_sent_total = Counter(
            'webhooks_sent_total',
            'Total de webhooks enviados com sucesso'
        )
        self.webhooks_failed_total = Counter(
            'webhooks_failed_total',
            'Total de webhooks falhados'
        )
        self.webhook_duration_seconds = Histogram(
            'webhook_duration_seconds',
            'Duração de envio de webhook'
        )
        self.webhook_queue_size = Gauge(
            'webhook_queue_size',
            'Tamanho atual da fila de webhooks'
        )

        # JWT
        self.jwt_tokens_generated_total = Counter(
            'jwt_tokens_generated_total',
            'Total de tokens JWT gerados'
        )

        # Database
        self.postgres_queries_total = Counter(
            'postgres_queries_total',
            'Total de queries PostgreSQL',
            ['operation']
        )
        self.postgres_query_duration_seconds = Histogram(
            'postgres_query_duration_seconds',
            'Duração de queries PostgreSQL'
        )
        self.mongodb_operations_total = Counter(
            'mongodb_operations_total',
            'Total de operações MongoDB',
            ['operation']
        )

        # Kafka
        self.kafka_messages_consumed_total = Counter(
            'kafka_messages_consumed_total',
            'Total de mensagens consumidas'
        )
        self.kafka_consumer_lag = Gauge(
            'kafka_consumer_lag',
            'Lag do consumer Kafka'
        )
