import asyncio
import signal
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog
from neural_hive_observability import init_observability

from src.config.settings import get_settings
from src.api import health

# Configurar logger estruturado
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia lifecycle da aplicação"""
    # Startup
    logger.info("guard_agent.startup", service=settings.service_name, version=settings.service_version)

    try:
        init_observability(
            service_name=settings.service_name,
            service_version=settings.service_version,
            neural_hive_component="guard-agents",
            neural_hive_layer="resilience",
            environment=settings.environment,
            otel_endpoint=settings.otel_exporter_otlp_endpoint,
            prometheus_port=9090,
            log_level=settings.log_level,
            enable_kafka=True,
            enable_grpc=False
        )
    except Exception as e:
        logger.warning(
            "observability_init_failed",
            error=str(e),
            otel_endpoint=settings.otel_exporter_otlp_endpoint,
            prometheus_port=9090
        )

    # Importar clientes
    from src.clients.service_registry_client import ServiceRegistryClient
    from src.clients.mongodb_client import MongoDBClient
    from src.clients.redis_client import RedisClient
    from src.clients.kafka_consumer import KafkaConsumerClient
    from src.clients.kubernetes_client import KubernetesClient
    from src.clients.self_healing_client import SelfHealingClient
    from src.clients.opa_client import OPAClient
    from src.clients.istio_client import IstioClient
    from src.clients.prometheus_client import PrometheusClient
    from src.producers.remediation_producer import RemediationProducer
    from src.services.message_handler import MessageHandler

    # Inicializar Service Registry
    logger.info("guard_agent.initializing_service_registry")
    service_registry = ServiceRegistryClient(
        host=settings.service_registry_host,
        port=settings.service_registry_port,
        agent_type="GUARD",
        capabilities=settings.capabilities,
        metadata={
            "version": settings.service_version,
            "environment": settings.environment,
            "namespace": settings.kubernetes_namespace
        },
        heartbeat_interval=settings.heartbeat_interval_seconds
    )
    await service_registry.connect()
    agent_id = await service_registry.register()
    await service_registry.start_heartbeat()
    app.state.service_registry = service_registry

    # Inicializar MongoDB
    logger.info("guard_agent.initializing_mongodb")
    mongodb = MongoDBClient(uri=settings.mongodb_uri, database=settings.mongodb_database)
    await mongodb.connect(
        incidents_coll=settings.mongodb_incidents_collection,
        remediation_coll=settings.mongodb_remediation_collection
    )
    app.state.mongodb = mongodb

    # Inicializar Redis
    logger.info("guard_agent.initializing_redis")
    redis_client = RedisClient(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password
    )
    await redis_client.connect()
    app.state.redis = redis_client

    # Inicializar Kubernetes
    logger.info("guard_agent.initializing_kubernetes")
    k8s_client = KubernetesClient(
        in_cluster=settings.kubernetes_in_cluster,
        namespace=settings.kubernetes_namespace
    )
    await k8s_client.connect()
    app.state.k8s = k8s_client

    # Inicializar Kafka Producer para remediações
    logger.info("guard_agent.initializing_kafka_producer")
    remediation_producer = RemediationProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.kafka_remediation_topic
    )
    await remediation_producer.connect()
    app.state.remediation_producer = remediation_producer

    # Inicializar Self-Healing Client
    logger.info("guard_agent.initializing_self_healing_client")
    self_healing_client = SelfHealingClient(
        base_url=settings.self_healing_engine_url,
        timeout=30.0
    )
    await self_healing_client.connect()
    app.state.self_healing_client = self_healing_client

    # Inicializar OPA Client (opcional - graceful degradation)
    opa_client = None
    if settings.opa_enforcement_enabled:
        logger.info("guard_agent.initializing_opa_client")
        opa_client = OPAClient(
            base_url=settings.opa_url,
            timeout=settings.opa_timeout_seconds
        )
        try:
            await opa_client.connect()
            logger.info("guard_agent.opa_client_ready")
        except Exception as e:
            logger.warning("guard_agent.opa_client_failed", error=str(e))
            opa_client = None
    app.state.opa_client = opa_client

    # Inicializar Vault Client (opcional - graceful degradation)
    vault_client = None
    if settings.vault_enabled:
        logger.info("guard_agent.initializing_vault_client")
        from src.clients.vault_client import GuardVaultClient
        vault_client = GuardVaultClient(config=settings)
        try:
            await vault_client.initialize()
            logger.info("guard_agent.vault_client_ready")
        except Exception as e:
            logger.warning("guard_agent.vault_client_failed", error=str(e))
            if not settings.vault_fail_open:
                raise
            vault_client = None
    app.state.vault_client = vault_client

    # Inicializar Trivy Client (opcional - graceful degradation)
    trivy_client = None
    if settings.trivy_enabled:
        logger.info("guard_agent.initializing_trivy_client")
        from src.clients.trivy_client import TrivyClient
        trivy_client = TrivyClient(
            base_url=settings.trivy_url,
            timeout=settings.trivy_timeout_seconds
        )
        try:
            await trivy_client.connect()
            logger.info("guard_agent.trivy_client_ready")
        except Exception as e:
            logger.warning("guard_agent.trivy_client_failed", error=str(e))
            trivy_client = None
    app.state.trivy_client = trivy_client

    # Inicializar Istio Client (opcional - graceful degradation)
    istio_client = None
    if settings.istio_enforcement_enabled:
        logger.info("guard_agent.initializing_istio_client")
        istio_client = IstioClient(
            k8s_client=k8s_client,
            namespace=settings.kubernetes_namespace
        )
        try:
            await istio_client.connect()
            logger.info("guard_agent.istio_client_ready")
        except Exception as e:
            logger.warning("guard_agent.istio_client_failed", error=str(e))
            istio_client = None
    app.state.istio_client = istio_client

    # Inicializar Prometheus Client (opcional - graceful degradation)
    prometheus_client = None
    logger.info("guard_agent.initializing_prometheus_client")
    prometheus_client = PrometheusClient(
        base_url=settings.prometheus_url,
        timeout=settings.prometheus_query_timeout_seconds
    )
    try:
        await prometheus_client.connect()
        logger.info("guard_agent.prometheus_client_ready")
    except Exception as e:
        logger.warning("guard_agent.prometheus_client_failed", error=str(e))
        prometheus_client = None
    app.state.prometheus_client = prometheus_client

    # Inicializar Security Validator
    logger.info("guard_agent.initializing_security_validator")
    from src.services.security_validator import SecurityValidator
    security_validator = SecurityValidator(
        opa_client=opa_client,
        k8s_client=k8s_client,
        vault_client=vault_client,
        trivy_client=trivy_client,
        redis_client=redis_client,
        mongodb_client=mongodb,
        settings=settings
    )
    app.state.security_validator = security_validator

    # Inicializar Guardrail Enforcer
    logger.info("guard_agent.initializing_guardrail_enforcer")
    from src.services.guardrail_enforcer import GuardrailEnforcer
    guardrail_enforcer = GuardrailEnforcer(
        opa_client=opa_client,
        mongodb_client=mongodb,
        redis_client=redis_client,
        mode=settings.guardrails_mode
    )
    app.state.guardrail_enforcer = guardrail_enforcer

    # Inicializar Validation Producer
    logger.info("guard_agent.initializing_validation_producer")
    from src.producers.validation_producer import ValidationProducer
    validation_producer = ValidationProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.kafka_validations_topic
    )
    await validation_producer.connect()
    app.state.validation_producer = validation_producer

    # Inicializar Message Handler com todos os componentes
    logger.info("guard_agent.initializing_message_handler")
    message_handler = MessageHandler(
        mongodb_client=mongodb,
        redis_client=redis_client,
        k8s_client=k8s_client,
        kafka_producer=remediation_producer,
        self_healing_client=self_healing_client,
        opa_client=app.state.opa_client,
        istio_client=app.state.istio_client,
        prometheus_client=app.state.prometheus_client
    )
    app.state.message_handler = message_handler

    # Inicializar Kafka Consumers
    logger.info("guard_agent.initializing_kafka_consumers")

    # Consumer para security incidents
    security_consumer = KafkaConsumerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        topics=[settings.kafka_incidents_topic],
        auto_offset_reset=settings.kafka_auto_offset_reset,
        enable_auto_commit=settings.kafka_enable_auto_commit
    )
    await security_consumer.connect()
    security_consumer.set_message_handler(message_handler.handle_security_incident)
    await security_consumer.start_consuming()
    app.state.security_consumer = security_consumer

    # Consumer para orchestration incidents
    orchestration_consumer = KafkaConsumerClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        topics=[settings.kafka_orchestration_incidents_topic],
        auto_offset_reset=settings.kafka_auto_offset_reset,
        enable_auto_commit=settings.kafka_enable_auto_commit
    )
    await orchestration_consumer.connect()
    orchestration_consumer.set_message_handler(message_handler.handle_orchestration_incident)
    await orchestration_consumer.start_consuming()
    app.state.orchestration_consumer = orchestration_consumer

    # Consumer para ticket validation
    logger.info("guard_agent.initializing_ticket_consumer")
    from src.consumers.ticket_consumer import TicketConsumer
    ticket_consumer = TicketConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{settings.kafka_consumer_group}-ticket-validator",
        security_validator=security_validator,
        guardrail_enforcer=guardrail_enforcer,
        validation_producer=validation_producer,
        tickets_topic=settings.kafka_tickets_topic,
        tickets_validated_topic=settings.kafka_tickets_validated_topic,
        tickets_rejected_topic=settings.kafka_tickets_rejected_topic,
        tickets_pending_approval_topic=settings.kafka_tickets_pending_approval_topic
    )
    await ticket_consumer.connect()
    await ticket_consumer.start_consuming()
    app.state.ticket_consumer = ticket_consumer

    logger.info(
        "guard_agent.startup_complete",
        agent_id=agent_id,
        capabilities=settings.capabilities
    )

    yield

    # Shutdown
    logger.info("guard_agent.shutdown", service=settings.service_name)

    # Parar consumers
    logger.info("guard_agent.stopping_kafka_consumers")
    await app.state.security_consumer.stop()
    await app.state.orchestration_consumer.stop()

    # Parar ticket consumer
    if hasattr(app.state, 'ticket_consumer'):
        logger.info("guard_agent.stopping_ticket_consumer")
        await app.state.ticket_consumer.stop()

    # Fechar producers
    logger.info("guard_agent.closing_kafka_producers")
    await app.state.remediation_producer.close()

    if hasattr(app.state, 'validation_producer'):
        await app.state.validation_producer.close()

    # Fechar clientes
    logger.info("guard_agent.closing_clients")
    await app.state.self_healing_client.close()

    if app.state.opa_client:
        await app.state.opa_client.close()

    if app.state.prometheus_client:
        await app.state.prometheus_client.close()

    if hasattr(app.state, 'vault_client') and app.state.vault_client:
        await app.state.vault_client.close()

    if hasattr(app.state, 'trivy_client') and app.state.trivy_client:
        await app.state.trivy_client.close()

    # Desregistrar do Service Registry
    logger.info("guard_agent.closing_service_registry")
    await app.state.service_registry.close()

    # Fechar conexões
    logger.info("guard_agent.closing_connections")
    await app.state.mongodb.close()
    await app.state.redis.close()

    logger.info("guard_agent.shutdown_complete")


# Criar aplicação FastAPI
app = FastAPI(
    title="Guard Agents",
    description="Neural Hive-Mind Guard Agents - Threat Detection and Policy Enforcement",
    version=settings.service_version,
    lifespan=lifespan
)

# Incluir routers
app.include_router(health.router, tags=["health"])

# Incluir router de validação
from src.api import validation
app.include_router(validation.router, prefix="/api/v1", tags=["validation"])

# TODO: Incluir routers adicionais
# app.include_router(incidents.router, prefix="/api/v1", tags=["incidents"])
# app.include_router(enforcement.router, prefix="/api/v1", tags=["enforcement"])
# app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])


# Signal handling para graceful shutdown
def handle_shutdown(signum, frame):
    logger.info("guard_agent.signal_received", signal=signum)
    # Graceful shutdown será tratado pelo lifespan


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        log_level=settings.log_level.lower(),
        access_log=True
    )
