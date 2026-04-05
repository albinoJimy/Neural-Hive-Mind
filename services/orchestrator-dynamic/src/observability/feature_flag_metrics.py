"""
Métricas Prometheus para Feature Flags Dinâmicas.

Este módulo fornece métricas detalhadas para monitoramento de
feature flags, incluindo toggle count, evaluation latency,
cache hit/miss ratio, e rollout percentage.

Métricas:
- feature_flag_enabled_total: Counter para toggles
- feature_flag_evaluation_duration_seconds: Histogram de latência
- feature_flag_cache_hit_miss: Counter para cache hits/misses
- feature_flag_rollout_percentage: Gauge para rollout configurado
"""
from functools import lru_cache

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)


@lru_cache
def get_feature_flag_metrics(
    service_name: str = "orchestrator-dynamic",
    component: str = "feature-flags",
    layer: str = "orchestration",
) -> "FeatureFlagMetrics":
    """
    Retorna instância singleton de FeatureFlagMetrics.

    Args:
        service_name: Nome do serviço
        component: Nome do componente
        layer: Camada da arquitetura

    Returns:
        Instância de FeatureFlagMetrics
    """
    return FeatureFlagMetrics(
        service_name=service_name,
        component=component,
        layer=layer,
    )


class FeatureFlagMetrics:
    """
    Métricas Prometheus para Feature Flags Dinâmicas.

    Coleta métricas sobre:
    - Toggle operations (enable/disable)
    - Evaluation latency
    - Cache performance (hits/misses)
    - Rollout percentage
    - Evaluation results (enabled/disabled)
    """

    def __init__(
        self,
        service_name: str = "orchestrator-dynamic",
        component: str = "feature-flags",
        layer: str = "orchestration",
    ):
        """
        Inicializa métricas Prometheus.

        Args:
            service_name: Nome do serviço
            component: Nome do componente
            layer: Camada da arquitetura
        """
        self.service_name = service_name
        self.component = component
        self.layer = layer

        # -------------------------------------------------------------------------
        # Toggle Count - Counter para operações de toggle
        # -------------------------------------------------------------------------
        self.flag_toggles_total = Counter(
            "feature_flag_toggles_total",
            "Total de operações de toggle em feature flags",
            [
                "flag_name",
                "action",  # enable, disable
                "user",
                "service_name",
                "component",
                "layer",
            ],
        )

        # -------------------------------------------------------------------------
        # Evaluation Latency - Histogram para tempo de avaliação
        # -------------------------------------------------------------------------
        self.evaluation_duration_seconds = Histogram(
            "feature_flag_evaluation_duration_seconds",
            "Duração da avaliação de feature flags em segundos",
            [
                "flag_name",
                "result",  # enabled, disabled, error
                "service_name",
                "component",
                "layer",
            ],
            buckets=[
                0.0005,  # 0.5ms
                0.001,  # 1ms
                0.0025,  # 2.5ms
                0.005,  # 5ms
                0.01,  # 10ms
                0.025,  # 25ms
                0.05,  # 50ms
                0.1,  # 100ms
                0.25,  # 250ms
                0.5,  # 500ms
                1.0,  # 1s
            ],
        )

        # -------------------------------------------------------------------------
        # Cache Performance - Counters para hits e misses
        # -------------------------------------------------------------------------
        self.cache_hits_total = Counter(
            "feature_flag_cache_hits_total",
            "Total de cache hits de feature flags",
            [
                "cache_level",  # local, redis
                "flag_name",
                "service_name",
                "component",
                "layer",
            ],
        )

        self.cache_misses_total = Counter(
            "feature_flag_cache_misses_total",
            "Total de cache misses de feature flags",
            [
                "cache_level",  # local, redis
                "flag_name",
                "service_name",
                "component",
                "layer",
            ],
        )

        # -------------------------------------------------------------------------
        # Evaluation Results - Counter para resultados de avaliação
        # -------------------------------------------------------------------------
        self.evaluations_total = Counter(
            "feature_flag_evaluations_total",
            "Total de avaliações de feature flags",
            [
                "flag_name",
                "result",  # enabled, disabled, error
                "service_name",
                "component",
                "layer",
            ],
        )

        # -------------------------------------------------------------------------
        # Rollout Percentage - Gauge para percentual configurado
        # -------------------------------------------------------------------------
        self.rollout_percentage = Gauge(
            "feature_flag_rollout_percentage",
            "Percentual de rollout configurado para feature flags",
            [
                "flag_name",
                "strategy",  # percentage, gradual, canary
                "service_name",
                "component",
                "layer",
            ],
        )

        # -------------------------------------------------------------------------
        # Active Flags - Gauge para flags ativas
        # -------------------------------------------------------------------------
        self.active_flags = Gauge(
            "feature_flags_active",
            "Número de feature flags ativas",
            [
                "owner",
                "environment",
                "service_name",
                "component",
                "layer",
            ],
        )

        # -------------------------------------------------------------------------
        # OPA Integration - Métricas específicas para integração OPA
        # -------------------------------------------------------------------------
        self.opa_evaluation_duration_seconds = Histogram(
            "feature_flag_opa_evaluation_duration_seconds",
            "Duração da avaliação OPA de feature flags em segundos",
            [
                "policy_path",
                "status",  # success, error, timeout
                "service_name",
                "component",
                "layer",
            ],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )

        self.opa_fallback_total = Counter(
            "feature_flag_opa_fallback_total",
            "Total de fallbacks para valores default (Redis indisponível)",
            [
                "reason",  # redis_unavailable, timeout, error
                "service_name",
                "component",
                "layer",
            ],
        )

        # -------------------------------------------------------------------------
        # Rollout Strategy - Métricas específicas por estratégia
        # -------------------------------------------------------------------------
        self.percentage_rollout_evaluations_total = Counter(
            "feature_flag_percentage_rollout_evaluations_total",
            "Total de avaliações de rollout por porcentagem",
            [
                "flag_name",
                "result",  # included, excluded
                "configured_percentage",
                "service_name",
                "component",
                "layer",
            ],
        )

        self.whitelist_evaluations_total = Counter(
            "feature_flag_whitelist_evaluations_total",
            "Total de avaliações de whitelist",
            [
                "flag_name",
                "result",  # allowed, denied
                "service_name",
                "component",
                "layer",
            ],
        )

    # -------------------------------------------------------------------------
    # Métodos de Registro - Toggle Operations
    # -------------------------------------------------------------------------

    def record_toggle(
        self,
        flag_name: str,
        action: str,
        user: str,
    ) -> None:
        """
        Registra operação de toggle.

        Args:
            flag_name: Nome da flag
            action: Ação (enable/disable)
            user: Usuário que fez a alteração
        """
        self.flag_toggles_total.labels(
            flag_name=flag_name,
            action=action,
            user=user,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

        logger.debug(
            "feature_flag_toggle_recorded",
            flag_name=flag_name,
            action=action,
            user=user,
        )

    # -------------------------------------------------------------------------
    # Métodos de Registro - Evaluation
    # -------------------------------------------------------------------------

    def record_evaluation(
        self,
        flag_name: str,
        result: bool,
        duration_seconds: float,
        error: str | None = None,
    ) -> None:
        """
        Registra avaliação de feature flag.

        Args:
            flag_name: Nome da flag
            result: Resultado da avaliação (True/False)
            duration_seconds: Duração em segundos
            error: Mensagem de erro (se houve erro)
        """
        result_label = "enabled" if result else "disabled"
        if error:
            result_label = "error"

        # Registrar contagem
        self.evaluations_total.labels(
            flag_name=flag_name,
            result=result_label,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

        # Registrar duração
        self.evaluation_duration_seconds.labels(
            flag_name=flag_name,
            result=result_label,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).observe(duration_seconds)

        logger.debug(
            "feature_flag_evaluation_recorded",
            flag_name=flag_name,
            result=result_label,
            duration_seconds=duration_seconds,
        )

    # -------------------------------------------------------------------------
    # Métodos de Registro - Cache Performance
    # -------------------------------------------------------------------------

    def record_cache_hit(
        self,
        cache_level: str,
        flag_name: str,
    ) -> None:
        """
        Registra cache hit.

        Args:
            cache_level: Nível do cache (local, redis)
            flag_name: Nome da flag
        """
        self.cache_hits_total.labels(
            cache_level=cache_level,
            flag_name=flag_name,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

    def record_cache_miss(
        self,
        cache_level: str,
        flag_name: str,
    ) -> None:
        """
        Registra cache miss.

        Args:
            cache_level: Nível do cache (local, redis)
            flag_name: Nome da flag
        """
        self.cache_misses_total.labels(
            cache_level=cache_level,
            flag_name=flag_name,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

    # -------------------------------------------------------------------------
    # Métodos de Registro - Rollout Percentage
    # -------------------------------------------------------------------------

    def set_rollout_percentage(
        self,
        flag_name: str,
        strategy: str,
        percentage: float,
    ) -> None:
        """
        Define percentual de rollout.

        Args:
            flag_name: Nome da flag
            strategy: Estratégia de rollout
            percentage: Percentual configurado (0-100)
        """
        self.rollout_percentage.labels(
            flag_name=flag_name,
            strategy=strategy,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).set(percentage)

    def record_percentage_rollout_evaluation(
        self,
        flag_name: str,
        included: bool,
        configured_percentage: int,
    ) -> None:
        """
        Registra avaliação de rollout por porcentagem.

        Args:
            flag_name: Nome da flag
            included: Se a requisição foi incluída no rollout
            configured_percentage: Percentual configurado
        """
        self.percentage_rollout_evaluations_total.labels(
            flag_name=flag_name,
            result="included" if included else "excluded",
            configured_percentage=str(configured_percentage),
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

    # -------------------------------------------------------------------------
    # Métodos de Registro - Active Flags
    # -------------------------------------------------------------------------

    def set_active_flags(
        self,
        count: int,
        owner: str = "unknown",
        environment: str = "unknown",
    ) -> None:
        """
        Define número de flags ativas.

        Args:
            count: Número de flags ativas
            owner: Owner das flags
            environment: Ambiente
        """
        self.active_flags.labels(
            owner=owner,
            environment=environment,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).set(count)

    # -------------------------------------------------------------------------
    # Métodos de Registro - OPA Integration
    # -------------------------------------------------------------------------

    def record_opa_evaluation(
        self,
        policy_path: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        """
        Registra avaliação OPA.

        Args:
            policy_path: Caminho da política OPA
            status: Status da avaliação (success, error, timeout)
            duration_seconds: Duração em segundos
        """
        self.opa_evaluation_duration_seconds.labels(
            policy_path=policy_path,
            status=status,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).observe(duration_seconds)

    def record_opa_fallback(self, reason: str) -> None:
        """
        Registra fallback para valores default.

        Args:
            reason: Razão do fallback (redis_unavailable, timeout, error)
        """
        self.opa_fallback_total.labels(
            reason=reason,
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

        logger.warning(
            "feature_flag_opa_fallback",
            reason=reason,
        )

    # -------------------------------------------------------------------------
    # Métodos de Registro - Whitelist Evaluation
    # -------------------------------------------------------------------------

    def record_whitelist_evaluation(
        self,
        flag_name: str,
        allowed: bool,
    ) -> None:
        """
        Registra avaliação de whitelist.

        Args:
            flag_name: Nome da flag
            allowed: Se foi permitido pela whitelist
        """
        self.whitelist_evaluations_total.labels(
            flag_name=flag_name,
            result="allowed" if allowed else "denied",
            service_name=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

    # -------------------------------------------------------------------------
    # Utilitários
    # -------------------------------------------------------------------------

    def get_cache_hit_ratio(self, cache_level: str = "all") -> float:
        """
        Calcula razão de cache hit.

        Args:
            cache_level: Nível do cache (local, redis, all)

        Returns:
            Razão de cache hit (0.0 a 1.0)
        """
        # Nota: Prometheus Counter não permite ler valores diretamente.
        # Este método deve ser usado via queries Prometheus.
        # Fórmula: cache_hits / (cache_hits + cache_misses)
        return 0.0


# Instância global singleton
_global_metrics: FeatureFlagMetrics | None = None


def get_metrics() -> FeatureFlagMetrics:
    """
    Retorna instância global de métricas.

    Returns:
        Instância de FeatureFlagMetrics
    """
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = get_feature_flag_metrics()
    return _global_metrics


def reset_metrics() -> None:
    """Reseta instância global de métricas (para testes)."""
    global _global_metrics
    _global_metrics = None
    # Limpar cache do lru_cache
    get_feature_flag_metrics.cache_clear()


__all__ = [
    "FeatureFlagMetrics",
    "get_feature_flag_metrics",
    "get_metrics",
    "reset_metrics",
]
