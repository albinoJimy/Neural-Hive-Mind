"""
Métricas Prometheus para Rate Limiting no Orchestrator Dynamic.

Este módulo define as métricas expostas para monitoramento do rate limiting
hierárquico baseado em Token Bucket.
"""
from functools import lru_cache

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger()


class RateLimitMetrics:
    """Métricas Prometheus para Rate Limiting."""

    def __init__(
        self,
        service_name: str = "orchestrator-dynamic",
    ):
        """
        Inicializa métricas Prometheus para rate limiting.

        Args:
            service_name: Nome do serviço para label
        """
        self.service_name = service_name

        # Counter: Total de requests processadas pelo rate limiter
        # Labels: service, tenant_id, endpoint, status (allowed/throttled)
        self.rate_limit_requests_total = Counter(
            "rate_limit_requests_total",
            "Total de requests processadas pelo rate limiter",
            ["service", "tenant_id", "endpoint", "status"],
        )

        # Histogram: Tempo de espera para aquisição de tokens
        # Labels: service, tenant_id
        # Buckets: de 1ms até 1 segundo para capturar latências típicas
        self.rate_limit_wait_duration_seconds = Histogram(
            "rate_limit_wait_duration_seconds",
            "Tempo de espera para aquisição de tokens",
            ["service", "tenant_id"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )

        # Gauge: Tokens restantes no bucket
        # Labels: service, tenant_id, user_id, endpoint
        self.rate_limit_tokens_remaining = Gauge(
            "rate_limit_tokens_remaining",
            "Tokens restantes no bucket",
            ["service", "tenant_id", "user_id", "endpoint"],
        )

        # Counter: Total de requests throttled
        # Labels: service, tenant_id, reason (capacity_exceeded, tier_limit, burst_exceeded)
        self.rate_limit_throttle_total = Counter(
            "rate_limit_throttle_total",
            "Total de requests throttled",
            ["service", "tenant_id", "reason"],
        )

    def record_request(
        self,
        service: str,
        tenant_id: str,
        endpoint: str,
        status: str,
    ) -> None:
        """
        Registra uma request processada pelo rate limiter.

        Args:
            service: Nome do serviço
            tenant_id: ID do tenant
            endpoint: Caminho do endpoint
            status: 'allowed' ou 'throttled'
        """
        self.rate_limit_requests_total.labels(
            service=service,
            tenant_id=tenant_id,
            endpoint=endpoint,
            status=status,
        ).inc()

    def record_wait_duration(
        self,
        service: str,
        tenant_id: str,
        duration_seconds: float,
    ) -> None:
        """
        Registra o tempo de espera para aquisição de tokens.

        Args:
            service: Nome do serviço
            tenant_id: ID do tenant
            duration_seconds: Tempo de espera em segundos
        """
        self.rate_limit_wait_duration_seconds.labels(
            service=service,
            tenant_id=tenant_id,
        ).observe(duration_seconds)

    def set_tokens_remaining(
        self,
        service: str,
        tenant_id: str,
        user_id: str,
        endpoint: str,
        tokens: float,
    ) -> None:
        """
        Atualiza o gauge de tokens restantes.

        Args:
            service: Nome do serviço
            tenant_id: ID do tenant
            user_id: ID do usuário
            endpoint: Caminho do endpoint
            tokens: Quantidade de tokens restantes
        """
        self.rate_limit_tokens_remaining.labels(
            service=service,
            tenant_id=tenant_id,
            user_id=user_id,
            endpoint=endpoint,
        ).set(tokens)

    def record_throttle(
        self,
        service: str,
        tenant_id: str,
        reason: str,
    ) -> None:
        """
        Registra uma request throttled.

        Args:
            service: Nome do serviço
            tenant_id: ID do tenant
            reason: Razão do throttle (capacity_exceeded, tier_limit, burst_exceeded, etc)
        """
        self.rate_limit_throttle_total.labels(
            service=service,
            tenant_id=tenant_id,
            reason=reason,
        ).inc()


@lru_cache
def get_rate_limit_metrics() -> RateLimitMetrics:
    """
    Retorna instância singleton das métricas de rate limiting.

    Returns:
        Instância de RateLimitMetrics
    """
    return RateLimitMetrics()
