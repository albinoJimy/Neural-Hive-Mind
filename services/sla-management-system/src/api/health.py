"""Health check API para sla-management-system."""

from neural_hive_api.health import HealthRouter, BaseHealthCheck, HealthStatus, CheckResult

# Health router global - será configurado em main.py
_health_router: HealthRouter = None


def get_health_router() -> HealthRouter:
    """Retorna o health router configurado."""
    global _health_router
    if _health_router is None:
        _health_router = HealthRouter("sla-management-system")
    return _health_router


def configure_health_checks(
    postgresql_client=None,
    redis_client=None,
    prometheus_client=None,
    kafka_producer=None,
    alertmanager_client=None,
) -> HealthRouter:
    """Configura os health checks para o sla-management-system."""
    router = get_health_router()

    # Registrar checks apenas se os clientes forem fornecidos
    if postgresql_client:
        router.register_check(PostgreSQLHealthCheck(postgresql_client))

    if redis_client:
        router.register_check(RedisHealthCheck(redis_client))

    if prometheus_client:
        router.register_check(PrometheusHealthCheck(prometheus_client))

    if kafka_producer:
        router.register_check(KafkaHealthCheck(kafka_producer, critical=False))

    if alertmanager_client:
        router.register_check(AlertmanagerHealthCheck(alertmanager_client, critical=False))

    return router


class PostgreSQLHealthCheck(BaseHealthCheck):
    """Health check para PostgreSQL."""

    def __init__(self, client):
        super().__init__("postgresql", critical=True)
        self.client = client

    async def check(self) -> CheckResult:
        """Verifica conexão com PostgreSQL."""
        try:
            # Usa uma query simples para verificar health
            if self.client.pool:
                async with self.client.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.UNHEALTHY, message="No pool")
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.UNHEALTHY, message=str(e))


class RedisHealthCheck(BaseHealthCheck):
    """Health check para Redis."""

    def __init__(self, client):
        super().__init__("redis", critical=True)
        self.client = client

    async def check(self) -> CheckResult:
        """Verifica conexão com Redis."""
        try:
            is_healthy = await self.client.health_check()
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY
            return CheckResult(name=self.name, status=status)
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.UNHEALTHY, message=str(e))


class PrometheusHealthCheck(BaseHealthCheck):
    """Health check para Prometheus."""

    def __init__(self, client):
        super().__init__("prometheus", critical=True)
        self.client = client

    async def check(self) -> CheckResult:
        """Verifica conexão com Prometheus."""
        try:
            is_healthy = await self.client.health_check()
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY
            return CheckResult(name=self.name, status=status)
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.UNHEALTHY, message=str(e))


class KafkaHealthCheck(BaseHealthCheck):
    """Health check para Kafka (opcional)."""

    def __init__(self, client, critical: bool = False):
        super().__init__("kafka", critical=critical)
        self.client = client

    async def check(self) -> CheckResult:
        """Verifica conexão com Kafka."""
        try:
            is_healthy = await self.client.health_check()
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.DEGRADED
            return CheckResult(name=self.name, status=status)
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class AlertmanagerHealthCheck(BaseHealthCheck):
    """Health check para Alertmanager (opcional)."""

    def __init__(self, client, critical: bool = False):
        super().__init__("alertmanager", critical=critical)
        self.client = client

    async def check(self) -> CheckResult:
        """Verifica conexão com Alertmanager."""
        try:
            is_healthy = await self.client.health_check()
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.DEGRADED
            return CheckResult(name=self.name, status=status)
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


# Router para compatibilidade com código existente (será substituído)
router = get_health_router()
