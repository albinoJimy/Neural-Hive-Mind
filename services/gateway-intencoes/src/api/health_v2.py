"""Health check configuration para gateway-intencoes usando neural_hive_api."""

from neural_hive_api.health import HealthRouter, BaseHealthCheck, HealthStatus, CheckResult


# Health router global
_health_router: HealthRouter = None


def get_health_router() -> HealthRouter:
    """Retorna o health router configurado."""
    global _health_router
    if _health_router is None:
        _health_router = HealthRouter("gateway-intencoes")
    return _health_router


def configure_health_checks(
    redis_client=None,
    kafka_producer=None,
) -> HealthRouter:
    """Configura os health checks para o gateway-intencoes."""
    router = get_health_router()

    # Registrar checks apenas se os clientes forem fornecidos
    if redis_client:
        router.register_check(RedisHealthCheck(redis_client))

    if kafka_producer:
        router.register_check(KafkaHealthCheck(kafka_producer))

    return router


class RedisHealthCheck(BaseHealthCheck):
    """Health check para Redis."""

    def __init__(self, client):
        super().__init__("redis", critical=True)
        self.client = client

    async def check(self) -> CheckResult:
        """Verifica conexão com Redis."""
        try:
            if hasattr(self.client, 'pool'):
                # Verifica pool de conexões
                await self.client.ping()
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message="No pool")
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class KafkaHealthCheck(BaseHealthCheck):
    """Health check para Kafka producer."""

    def __init__(self, producer):
        super().__init__("kafka", critical=True)
        self.producer = producer

    async def check(self) -> CheckResult:
        """Verifica conexão com Kafka."""
        try:
            # Kafka producer health check
            if hasattr(self.producer, 'check_connection'):
                is_healthy = await self.producer.check_connection()
                status = HealthStatus.HEALTHY if is_healthy else HealthStatus.DEGRADED
                return CheckResult(name=self.name, status=status)
            return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


# Exportar router para compatibilidade
router = get_health_router()
