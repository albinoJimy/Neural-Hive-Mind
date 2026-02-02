"""
Metricas Prometheus para Approval Service

Define metricas customizadas para observabilidade do servico de aprovacoes.
"""

import asyncio
import structlog
from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger()


# Counters
approval_requests_received_total = Counter(
    'approval_requests_received_total',
    'Total de requests de aprovacao recebidos',
    ['risk_band', 'is_destructive']
)

approvals_total = Counter(
    'approvals_total',
    'Total de decisoes de aprovacao',
    ['decision', 'risk_band']
)

approval_api_requests_total = Counter(
    'approval_api_requests_total',
    'Total de requests na API',
    ['endpoint', 'status']
)

# Gauges
approval_requests_pending_gauge = Gauge(
    'approval_requests_pending',
    'Numero de requests de aprovacao pendentes',
    ['risk_band']
)

approval_requests_max_pending_age_seconds = Gauge(
    'approval_requests_max_pending_age_seconds',
    'Idade maxima (em segundos) dos requests pendentes',
    ['risk_band']
)

# Republication Metrics
approval_republish_total = Counter(
    'approval_republish_total',
    'Total de republicacoes de planos aprovados',
    ['outcome', 'force']  # outcome: 'success', 'failure'; force: 'true', 'false'
)

approval_republish_failures_total = Counter(
    'approval_republish_failures_total',
    'Total de falhas em republicacao de planos',
    ['failure_reason']  # failure_reason: 'not_found', 'not_approved', 'no_cognitive_plan', 'kafka_error'
)

approval_republish_duration_seconds = Histogram(
    'approval_republish_duration_seconds',
    'Duracao da operacao de republicacao',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Histograms
approval_processing_duration_seconds = Histogram(
    'approval_processing_duration_seconds',
    'Tempo para processar decisao de aprovacao',
    ['decision'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

approval_time_to_decision_seconds = Histogram(
    'approval_time_to_decision_seconds',
    'Tempo desde o request ate a decisao',
    ['decision', 'risk_band'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]
)


class NeuralHiveMetrics:
    """Wrapper para metricas do Approval Service"""

    def __init__(self, mongodb_client=None):
        """
        Inicializa metricas

        Args:
            mongodb_client: Cliente MongoDB para queries de gauge
        """
        self._mongodb_client = mongodb_client

    def set_mongodb_client(self, client):
        """Define cliente MongoDB para queries de gauge"""
        self._mongodb_client = client

    def increment_approval_requests_received(
        self,
        risk_band: str,
        is_destructive: bool
    ):
        """
        Incrementa contador de requests recebidos

        Args:
            risk_band: Banda de risco (low/medium/high/critical)
            is_destructive: Se contem operacoes destrutivas
        """
        # Normaliza risk_band para string
        if hasattr(risk_band, 'value'):
            risk_band = risk_band.value

        approval_requests_received_total.labels(
            risk_band=risk_band,
            is_destructive=str(is_destructive).lower()
        ).inc()

    def increment_approvals_total(
        self,
        decision: str,
        risk_band: str
    ):
        """
        Incrementa contador de decisoes

        Args:
            decision: Decisao (approved/rejected)
            risk_band: Banda de risco
        """
        # Normaliza risk_band para string
        if hasattr(risk_band, 'value'):
            risk_band = risk_band.value

        approvals_total.labels(
            decision=decision,
            risk_band=risk_band
        ).inc()

    def increment_api_requests(
        self,
        endpoint: str,
        status: str
    ):
        """
        Incrementa contador de requests na API

        Args:
            endpoint: Nome do endpoint
            status: Status code HTTP
        """
        approval_api_requests_total.labels(
            endpoint=endpoint,
            status=status
        ).inc()

    def observe_processing_duration(
        self,
        duration: float,
        decision: str
    ):
        """
        Observa duracao do processamento da decisao

        Args:
            duration: Duracao em segundos
            decision: Decisao (approved/rejected)
        """
        approval_processing_duration_seconds.labels(
            decision=decision
        ).observe(duration)

    def observe_time_to_decision(
        self,
        time_seconds: float,
        decision: str,
        risk_band: str
    ):
        """
        Observa tempo desde request ate decisao

        Args:
            time_seconds: Tempo em segundos
            decision: Decisao (approved/rejected)
            risk_band: Banda de risco
        """
        # Normaliza risk_band para string
        if hasattr(risk_band, 'value'):
            risk_band = risk_band.value

        approval_time_to_decision_seconds.labels(
            decision=decision,
            risk_band=risk_band
        ).observe(time_seconds)

    def increment_republish_total(self, outcome: str, force: bool):
        """
        Incrementa contador de republicacoes

        Args:
            outcome: Resultado (success/failure)
            force: Se foi republicacao forcada
        """
        approval_republish_total.labels(
            outcome=outcome,
            force=str(force).lower()
        ).inc()

    def increment_republish_failures(self, failure_reason: str):
        """
        Incrementa contador de falhas de republicacao

        Args:
            failure_reason: Motivo da falha (not_found, not_approved, no_cognitive_plan, kafka_error)
        """
        approval_republish_failures_total.labels(
            failure_reason=failure_reason
        ).inc()

    def observe_republish_duration(self, duration: float):
        """
        Observa duracao da operacao de republicacao

        Args:
            duration: Duracao em segundos
        """
        approval_republish_duration_seconds.observe(duration)

    def update_pending_gauge(self):
        """
        Atualiza gauge de requests pendentes e idade maxima

        Executa query async no MongoDB de forma fire-and-forget.
        """
        if not self._mongodb_client:
            logger.debug('MongoDB client nao disponivel para gauge update')
            return

        async def _do_update():
            from datetime import datetime, timezone
            try:
                # Usa agregacao para contar pendentes por risk_band
                pipeline = [
                    {'$match': {'status': 'pending'}},
                    {'$group': {'_id': '$risk_band', 'count': {'$sum': 1}}}
                ]
                results = await self._mongodb_client.collection.aggregate(pipeline).to_list(length=10)

                # Define risk bands conhecidas
                known_bands = ['low', 'medium', 'high', 'critical']

                # Zera todas as labels primeiro
                for band in known_bands:
                    approval_requests_pending_gauge.labels(risk_band=band).set(0)
                    approval_requests_max_pending_age_seconds.labels(risk_band=band).set(0)

                # Atualiza com valores reais
                for item in results:
                    risk_band = item['_id']
                    count = item['count']
                    approval_requests_pending_gauge.labels(risk_band=risk_band).set(count)

                # Calcula idade maxima por risk_band
                age_pipeline = [
                    {'$match': {'status': 'pending'}},
                    {'$group': {
                        '_id': '$risk_band',
                        'oldest_requested_at': {'$min': '$requested_at'}
                    }}
                ]
                age_results = await self._mongodb_client.collection.aggregate(age_pipeline).to_list(length=10)

                now = datetime.now(timezone.utc)
                for item in age_results:
                    risk_band = item['_id']
                    oldest = item.get('oldest_requested_at')
                    if oldest:
                        # Calcula idade em segundos
                        if oldest.tzinfo is None:
                            oldest = oldest.replace(tzinfo=timezone.utc)
                        age_seconds = (now - oldest).total_seconds()
                        approval_requests_max_pending_age_seconds.labels(
                            risk_band=risk_band
                        ).set(age_seconds)

                logger.debug(
                    'Gauge de pendentes atualizado',
                    counts={item['_id']: item['count'] for item in results}
                )
            except Exception as e:
                logger.warning(
                    'Falha ao atualizar gauge de pendentes',
                    error=str(e)
                )

        # Executa de forma fire-and-forget
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do_update())
        except RuntimeError:
            # Nao ha event loop rodando - ignora
            logger.debug('Event loop nao disponivel para gauge update')


def register_metrics():
    """Registra todas as metricas customizadas"""
    # Metricas sao auto-registradas com prometheus_client
    pass
