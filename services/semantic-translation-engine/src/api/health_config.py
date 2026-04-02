"""Health check configuration para semantic-translation-engine usando neural_hive_api."""

from neural_hive_api.health import HealthRouter, BaseHealthCheck, HealthStatus, CheckResult


# Health router global
_health_router: HealthRouter = None
_state: dict = None


def get_health_router() -> HealthRouter:
    """Retorna o health router configurado."""
    global _health_router
    if _health_router is None:
        _health_router = HealthRouter("semantic-translation-engine")
    return _health_router


def set_state(state: dict) -> None:
    """Define o state global para acesso aos clientes."""
    global _state
    _state = state


def configure_health_checks(state: dict) -> HealthRouter:
    """Configura os health checks para o semantic-translation-engine."""
    router = get_health_router()

    # Redis check
    if "redis" in state and state["redis"]:
        router.register_check(RedisHealthCheck(state["redis"]))

    # MongoDB check
    if "mongodb" in state and state["mongodb"]:
        router.register_check(MongoDBHealthCheck(state["mongodb"]))

    # Neo4j check
    if "neo4j" in state and state["neo4j"]:
        router.register_check(Neo4jHealthCheck(state["neo4j"]))

    # Kafka producer check
    if "producer" in state and state["producer"]:
        router.register_check(KafkaProducerHealthCheck(state["producer"]))

    # Kafka consumer check (critical for readiness)
    if "consumer" in state and state["consumer"]:
        router.register_check(KafkaConsumerHealthCheck(state["consumer"]))

    # Approval response consumer (non-critical, optional)
    if "approval_response_consumer" in state and state["approval_response_consumer"]:
        router.register_check(
            ApprovalResponseConsumerHealthCheck(state["approval_response_consumer"], critical=False)
        )

    return router


class RedisHealthCheck(BaseHealthCheck):
    """Health check para Redis."""

    def __init__(self, redis_client):
        super().__init__("redis", critical=True)
        self.redis_client = redis_client

    async def check(self) -> CheckResult:
        """Verifica conexão com Redis."""
        try:
            if hasattr(self.redis_client, 'client'):
                await self.redis_client.client.ping()
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message="No client")
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class MongoDBHealthCheck(BaseHealthCheck):
    """Health check para MongoDB."""

    def __init__(self, mongodb_client):
        super().__init__("mongodb", critical=True)
        self.mongodb_client = mongodb_client

    async def check(self) -> CheckResult:
        """Verifica conexão com MongoDB."""
        try:
            if hasattr(self.mongodb_client, 'client'):
                await self.mongodb_client.client.admin.command("ping")
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message="No client")
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class Neo4jHealthCheck(BaseHealthCheck):
    """Health check para Neo4j."""

    def __init__(self, neo4j_client):
        super().__init__("neo4j", critical=True)
        self.neo4j_client = neo4j_client

    async def check(self) -> CheckResult:
        """Verifica conexão com Neo4j."""
        try:
            if hasattr(self.neo4j_client, 'driver'):
                await self.neo4j_client.driver.verify_connectivity()
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message="No driver")
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class KafkaProducerHealthCheck(BaseHealthCheck):
    """Health check para Kafka producer."""

    def __init__(self, producer):
        super().__init__("kafka_producer", critical=True)
        self.producer = producer

    async def check(self) -> CheckResult:
        """Verifica conexão com Kafka producer."""
        try:
            if hasattr(self.producer, 'producer'):
                self.producer.producer.list_topics(timeout=2)
                return CheckResult(name=self.name, status=HealthStatus.HEALTHY)
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message="No producer")
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class KafkaConsumerHealthCheck(BaseHealthCheck):
    """Health check para Kafka consumer."""

    def __init__(self, consumer):
        super().__init__("kafka_consumer", critical=True)
        self.consumer = consumer

    async def check(self) -> CheckResult:
        """Verifica estado do Kafka consumer."""
        try:
            is_healthy, reason = self.consumer.is_healthy(max_poll_age_seconds=60.0)
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.DEGRADED
            return CheckResult(name=self.name, status=status, message=reason if not is_healthy else None)
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


class ApprovalResponseConsumerHealthCheck(BaseHealthCheck):
    """Health check para Approval Response Consumer (opcional)."""

    def __init__(self, consumer, critical: bool = False):
        super().__init__("approval_response_consumer", critical=critical)
        self.consumer = consumer

    async def check(self) -> CheckResult:
        """Verifica estado do Approval Response Consumer."""
        try:
            is_healthy, reason = self.consumer.is_healthy(max_poll_age_seconds=60.0)
            status = HealthStatus.HEALTHY if is_healthy else HealthStatus.DEGRADED
            return CheckResult(name=self.name, status=status, message=reason if not is_healthy else None)
        except Exception as e:
            return CheckResult(name=self.name, status=HealthStatus.DEGRADED, message=str(e))


# Exportar router para compatibilidade
router = get_health_router()
