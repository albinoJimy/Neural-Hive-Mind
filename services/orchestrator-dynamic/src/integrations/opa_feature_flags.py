"""
Cliente OPA para Feature Flags Dinâmicas.

Integra OPA com Feature Flags armazenadas em Redis, permitindo
avaliação de políticas com dados dinâmicos atualizados em tempo real.

Arquitetura:
    Redis (feature_flags:all) --> OPA (data.external) --> Decisão
    Fallback: valores default do feature_flags.rego
"""
import json
from typing import Any, ClassVar

import structlog
from prometheus_client import Counter, Histogram

from src.policies.opa_client import OPAClient

logger = structlog.get_logger(__name__)


# Mock metrics para quando metrics não é fornecido
class _MockMetrics:
    """Mock de métricas para feature flags."""

    def record_flag_evaluation(self, *args, **kwargs):
        pass

    def record_cache_hit(self, *args, **kwargs):
        pass

    def record_cache_miss(self, *args, **kwargs):
        pass

    def record_flag_toggle(self, *args, **kwargs):
        pass


_mock_metrics_instance = _MockMetrics()


class OPAFeatureFlagsMetrics:
    """Métricas Prometheus para Feature Flags OPA."""

    def __init__(
        self,
        service_name: str = "orchestrator-dynamic",
        component: str = "feature-flags",
        layer: str = "opa",
    ):
        self.service_name = service_name
        self.component = component
        self.layer = layer

        # Métricas de avaliação
        self.flag_evaluations_total = Counter(
            "feature_flag_evaluations_total",
            "Total de avaliações de feature flags",
            ["flag_name", "result", "service", "component", "layer"],
        )

        self.flag_evaluation_duration_seconds = Histogram(
            "feature_flag_evaluation_duration_seconds",
            "Duração da avaliação de feature flags",
            ["flag_name", "service", "component", "layer"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
        )

        # Métricas de cache (Redis)
        self.flag_cache_hits_total = Counter(
            "feature_flag_cache_hits_total",
            "Total de cache hits de feature flags",
            ["flag_name", "service", "component", "layer"],
        )

        self.flag_cache_misses_total = Counter(
            "feature_flag_cache_misses_total",
            "Total de cache misses de feature flags",
            ["flag_name", "service", "component", "layer"],
        )

        # Métricas de toggle
        self.flag_toggles_total = Counter(
            "feature_flag_toggles_total",
            "Total de operações de toggle em feature flags",
            ["flag_name", "action", "user", "service", "component", "layer"],
        )

        # Métricas de rollout
        self.flag_rollout_percentage = Counter(
            "feature_flag_rollout_percentage",
            "Percentual de rollout configurado para flags",
            ["flag_name", "strategy", "service", "component", "layer"],
        )

    def record_flag_evaluation(
        self, flag_name: str, result: bool, duration_ms: float
    ) -> None:
        """Registra avaliação de feature flag."""
        self.flag_evaluations_total.labels(
            flag_name=flag_name,
            result="enabled" if result else "disabled",
            service=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

        # Histogram em segundos
        self.flag_evaluation_duration_seconds.labels(
            flag_name=flag_name,
            service=self.service_name,
            component=self.component,
            layer=self.layer,
        ).observe(duration_ms / 1000)

    def record_cache_hit(self, flag_name: str) -> None:
        """Registra cache hit."""
        self.flag_cache_hits_total.labels(
            flag_name=flag_name,
            service=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

    def record_cache_miss(self, flag_name: str) -> None:
        """Registra cache miss."""
        self.flag_cache_misses_total.labels(
            flag_name=flag_name,
            service=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

    def record_flag_toggle(self, flag_name: str, action: str, user: str) -> None:
        """Registra operação de toggle."""
        self.flag_toggles_total.labels(
            flag_name=flag_name,
            action=action,
            user=user,
            service=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc()

    def record_rollout_percentage(
        self, flag_name: str, strategy: str, percentage: int
    ) -> None:
        """Registra percentual de rollout configurado."""
        self.flag_rollout_percentage.labels(
            flag_name=flag_name,
            strategy=strategy,
            service=self.service_name,
            component=self.component,
            layer=self.layer,
        ).inc(percentage)


class OPAFeatureFlagsClient:
    """
    Cliente OPA para Feature Flags Dinâmicas.

    Este cliente integra OPA com Feature Flags armazenadas em Redis,
    permitindo avaliação de políticas com dados dinâmicos atualizados
    em tempo real.

    Features:
    - Avaliação de flags via OPA policy
    - Cache de resultados para performance
    - Fallback para valores default
    - Métricas Prometheus
    - Suporte a rollout strategies
    """

    # Policy path OPA
    POLICY_PATH = "neuralhive.orchestrator.feature_flags"

    # Flags padrão (fallback quando Redis indisponível)
    DEFAULT_FLAGS: ClassVar[dict[str, Any]] = {
        "intelligent_scheduler_enabled": False,
        "burst_capacity_enabled": False,
        "predictive_allocation_enabled": False,
        "auto_scaling_enabled": False,
        "gradual_rollout": False,
        "scheduler_namespaces": ["production", "staging"],
        "burst_threshold": 80,
        "premium_tenants": [],
        "scaling_threshold": 100,
    }

    def __init__(
        self,
        opa_client: OPAClient,
        redis_client: Any | None = None,
        metrics: OPAFeatureFlagsMetrics | None = None,
    ):
        """
        Inicializa cliente OPA Feature Flags.

        Args:
            opa_client: Cliente OPA existente
            redis_client: Cliente Redis async (opcional)
            metrics: Métricas (opcional)
        """
        self.opa_client = opa_client
        self.redis_client = redis_client
        self.metrics = metrics or _MockMetricsInstance()

        # Cache local de flags (TTL curto)
        self._local_cache: dict[str, Any] = {}
        self._local_cache_ttl: float = 5.0  # 5 segundos
        self._local_cache_timestamp: float = 0

    @property
    def _MockMetricsInstance(self):
        """Retorna instância de mock metrics."""
        return _mock_metrics_instance

    async def evaluate_flag(
        self,
        flag_name: str,
        context: dict[str, Any],
        use_cache: bool = True,
    ) -> bool:
        """
        Avalia se uma feature flag está ativa para o contexto dado.

        Args:
            flag_name: Nome da flag (ex: "enable_intelligent_scheduler")
            context: Contexto de avaliação (tenant_id, namespace, risk_band, etc.)
            use_cache: Usar cache local

        Returns:
            True se flag está ativa, False caso contrário
        """
        import time

        start_time = time.time()

        try:
            # 1. Tentar obter flags do Redis (via OPA data.external)
            flags = await self._get_flags_from_redis(use_cache=use_cache)

            # 2. Preparar input OPA
            opa_input = {
                "flag_name": flag_name,
                "flags": flags,
                "context": context,
            }

            # 3. Avaliar política OPA
            result = await self.opa_client.evaluate_policy(
                self.POLICY_PATH,
                {"input": opa_input},
            )

            # 4. Extrair resultado
            enabled = self._extract_flag_result(result, flag_name)

            # 5. Registrar métricas
            duration_ms = (time.time() - start_time) * 1000
            if isinstance(self.metrics, OPAFeatureFlagsMetrics):
                self.metrics.record_flag_evaluation(flag_name, enabled, duration_ms)

            logger.debug(
                "feature_flag_evaluated",
                flag_name=flag_name,
                enabled=enabled,
                duration_ms=duration_ms,
            )

            return enabled

        except Exception as e:
            logger.error(
                "feature_flag_evaluation_failed",
                flag_name=flag_name,
                error=str(e),
            )
            # Fallback para valor default
            return self.DEFAULT_FLAGS.get(
                f"{flag_name}_enabled",
                False,
            )

    async def evaluate_multiple_flags(
        self,
        flag_names: list[str],
        context: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Avalia múltiplas flags de uma vez.

        Args:
            flag_names: Lista de nomes de flags
            context: Contexto de avaliação

        Returns:
            Dict com {flag_name: enabled}
        """
        results = {}
        for flag_name in flag_names:
            results[flag_name] = await self.evaluate_flag(flag_name, context)
        return results

    async def get_all_flags(self, use_cache: bool = True) -> dict[str, Any]:
        """
        Obtém todas as flags do Redis ou valores default.

        Args:
            use_cache: Usar cache local

        Returns:
            Dict com todas as flags
        """
        return await self._get_flags_from_redis(use_cache=use_cache)

    async def _get_flags_from_redis(self, use_cache: bool = True) -> dict[str, Any]:
        """
        Obtém flags do Redis ou usa fallback.

        Args:
            use_cache: Usar cache local

        Returns:
            Dict com flags
        """
        import time

        # Verificar cache local
        if use_cache:
            cache_age = time.time() - self._local_cache_timestamp
            if cache_age < self._local_cache_ttl and self._local_cache:
                logger.debug("using_local_cache", cache_age=cache_age)
                return self._local_cache

        # Tentar obter do Redis
        if self.redis_client:
            try:
                flags_data = await self.redis_client.get("feature_flags:all")
                if flags_data:
                    flags = json.loads(flags_data)

                    # Atualizar cache local
                    self._local_cache = flags
                    self._local_cache_timestamp = time.time()

                    if isinstance(self.metrics, OPAFeatureFlagsMetrics):
                        for flag_name in flags.keys():
                            self.metrics.record_cache_hit(flag_name)

                    logger.debug("redis_flags_loaded", flag_count=len(flags))
                    return flags
                if isinstance(self.metrics, OPAFeatureFlagsMetrics):
                    for flag_name in self.DEFAULT_FLAGS.keys():
                        self.metrics.record_cache_miss(flag_name)
            except Exception as e:
                logger.warning("redis_flags_fetch_failed", error=str(e))

        # Fallback para valores default
        logger.info("using_default_flags")
        return self.DEFAULT_FLAGS.copy()

    def _extract_flag_result(self, opa_result: dict[str, Any], flag_name: str) -> bool:
        """
        Extrai resultado da avaliação OPA.

        Args:
            opa_result: Resultado da avaliação OPA
            flag_name: Nome da flag

        Returns:
            True se flag está ativa
        """
        try:
            # Result pode estar aninhado em 'result'
            if "result" in opa_result:
                result_data = opa_result["result"]
            else:
                result_data = opa_result

            # Verificar se flag está em result
            if isinstance(result_data, dict):
                # Formato: {"enable_intelligent_scheduler": true, ...}
                opa_flag_name = self._to_opa_flag_name(flag_name)
                return bool(result_data.get(opa_flag_name, False))

            return False

        except Exception as e:
            logger.warning(
                "flag_result_extraction_failed",
                flag_name=flag_name,
                error=str(e),
            )
            return False

    def _to_opa_flag_name(self, flag_name: str) -> str:
        """
        Converte nome da flag para formato OPA.

        Args:
            flag_name: Nome da flag (ex: "intelligent_scheduler")

        Returns:
            Nome no formato OPA (ex: "enable_intelligent_scheduler")
        """
        if flag_name.startswith("enable_"):
            return flag_name
        return f"enable_{flag_name}"

    async def toggle_flag(
        self,
        flag_name: str,
        enabled: bool,
        user: str = "system",
    ) -> dict[str, Any]:
        """
        Alterna estado de uma feature flag.

        Args:
            flag_name: Nome da flag
            enabled: Novo estado
            user: Usuário fazendo a alteração

        Returns:
            Dict com flag atualizada
        """
        import time

        start_time = time.time()

        try:
            # 1. Obter flags atuais
            flags = await self._get_flags_from_redis(use_cache=False)

            # 2. Atualizar flag
            opa_flag_name = self._to_opa_flag_name(flag_name)
            flags[opa_flag_name] = enabled

            # 3. Persistir no Redis
            if self.redis_client:
                flags_json = json.dumps(flags)
                await self.redis_client.set(
                    "feature_flags:all",
                    flags_json,
                    ex=60,  # TTL de 60 segundos
                )

            # 4. Invalidar cache local
            self._local_cache = {}
            self._local_cache_timestamp = 0

            # 5. Invalidar cache OPA
            self.opa_client.clear_cache()

            # 6. Registrar métricas
            duration_ms = (time.time() - start_time) * 1000
            if isinstance(self.metrics, OPAFeatureFlagsMetrics):
                self.metrics.record_flag_toggle(
                    flag_name,
                    "enable" if enabled else "disable",
                    user,
                )

            logger.info(
                "feature_flag_toggled",
                flag_name=flag_name,
                enabled=enabled,
                user=user,
                duration_ms=duration_ms,
            )

            return {flag_name: enabled}

        except Exception as e:
            logger.error(
                "feature_flag_toggle_failed",
                flag_name=flag_name,
                error=str(e),
            )
            raise

    async def update_flag_config(
        self,
        flag_name: str,
        config: dict[str, Any],
        user: str = "system",
    ) -> dict[str, Any]:
        """
        Atualiza configuração de uma feature flag.

        Args:
            flag_name: Nome da flag
            config: Configuração a atualizar
            user: Usuário fazendo a alteração

        Returns:
            Dict com flag atualizada
        """
        try:
            # 1. Obter flags atuais
            flags = await self._get_flags_from_redis(use_cache=False)

            # 2. Atualizar configuração
            for key, value in config.items():
                flags[key] = value

            # 3. Persistir no Redis
            if self.redis_client:
                flags_json = json.dumps(flags)
                await self.redis_client.set(
                    "feature_flags:all",
                    flags_json,
                    ex=60,  # TTL de 60 segundos
                )

            # 4. Invalidar caches
            self._local_cache = {}
            self._local_cache_timestamp = 0
            self.opa_client.clear_cache()

            logger.info(
                "feature_flag_config_updated",
                flag_name=flag_name,
                config_keys=list(config.keys()),
                user=user,
            )

            return config

        except Exception as e:
            logger.error(
                "feature_flag_config_update_failed",
                flag_name=flag_name,
                error=str(e),
            )
            raise

    async def get_flag_status(self, flag_name: str) -> dict[str, Any]:
        """
        Obtém status atual de uma flag específica.

        Args:
            flag_name: Nome da flag

        Returns:
            Dict com status da flag
        """
        flags = await self._get_flags_from_redis()
        opa_flag_name = self._to_opa_flag_name(flag_name)

        return {
            "name": flag_name,
            "enabled": flags.get(opa_flag_name, False),
            "config": {
                k: v
                for k, v in flags.items()
                if k.startswith(flag_name) or k == opa_flag_name
            },
        }

    async def health_check(self) -> dict[str, Any]:
        """
        Verifica saúde da integração OPA Feature Flags.

        Returns:
            Dict com status dos componentes
        """
        checks = {
            "opa": await self._check_opa_health(),
            "redis": await self._check_redis_health() if self.redis_client else False,
        }

        # Local cache é opcional, não afixa saúde
        return {
            "healthy": all(checks.values()),
            "checks": checks,
            "local_cache": bool(self._local_cache),
        }

    async def _check_opa_health(self) -> bool:
        """Verifica saúde do OPA."""
        try:
            return await self.opa_client.health_check()
        except Exception:
            return False

    async def _check_redis_health(self) -> bool:
        """Verifica saúde do Redis."""
        if not self.redis_client:
            return False
        try:
            await self.redis_client.ping()
            return True
        except Exception:
            return False


# Singleton de mock metrics
_MockMetricsInstance = _MockMetrics()
