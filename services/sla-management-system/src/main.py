"""
Entry point principal do SLA Management System.
"""

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from .api import alerts, budgets, policies, slos, webhooks
from .clients.alertmanager_client import AlertmanagerClient
from .clients.kafka_producer import KafkaProducerClient
from .clients.pagerduty_client import PagerDutyClient
from .clients.postgresql_client import PostgreSQLClient
from .clients.prometheus_client import PrometheusClient
from .clients.redis_client import RedisClient
from .clients.slack_client import SlackClient
from .config.settings import get_settings
from .consumers.sla_alert_consumer import SLAAlertConsumer
from .services.alert_dispatcher import AlertDispatcher
from .services.alert_engine import AlertEngine
from .services.budget_calculator import BudgetCalculator
from .services.policy_enforcer import PolicyEnforcer
from .services.slo_manager import SLOManager

# Configurar logging estruturado
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# Settings globais
settings = get_settings()

# Clientes globais
prometheus_client: PrometheusClient = None
postgresql_client: PostgreSQLClient = None
redis_client: RedisClient = None
kafka_producer: KafkaProducerClient = None
alertmanager_client: AlertmanagerClient = None
slack_client: SlackClient = None
pagerduty_client: PagerDutyClient = None

# Serviços globais
budget_calculator: BudgetCalculator = None
policy_enforcer: PolicyEnforcer = None
slo_manager: SLOManager = None
alert_engine: AlertEngine = None
alert_dispatcher: AlertDispatcher = None
sla_alert_consumer: SLAAlertConsumer = None

# Background task handles
periodic_calculation_task: asyncio.Task = None
alert_monitoring_task: asyncio.Task = None
sla_alert_consumer_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia lifecycle da aplicação."""
    # Startup
    logger.info(
        "sla_management_system_starting",
        service=settings.service_name,
        version=settings.version,
        environment=settings.environment,
    )

    global prometheus_client, postgresql_client, redis_client
    global kafka_producer, alertmanager_client
    global slack_client, pagerduty_client
    global budget_calculator, policy_enforcer, slo_manager
    global alert_engine, alert_dispatcher, sla_alert_consumer
    global periodic_calculation_task, alert_monitoring_task, sla_alert_consumer_task

    try:
        # Inicializar clientes
        prometheus_client = PrometheusClient(settings.prometheus)
        await prometheus_client.connect()

        postgresql_client = PostgreSQLClient(settings.postgresql)
        await postgresql_client.connect()

        redis_client = RedisClient(settings.redis)
        await redis_client.connect()

        # Kafka é opcional - continua sem ele se não conectar
        kafka_producer = KafkaProducerClient(settings.kafka)
        try:
            if settings.kafka.enabled:
                await kafka_producer.start()
                logger.info("kafka_producer_connected")
        except Exception as e:
            logger.warning("kafka_connection_failed_continuing_without", error=str(e))
            kafka_producer = None

        alertmanager_client = AlertmanagerClient(settings.alertmanager)
        try:
            await alertmanager_client.connect()
        except Exception as e:
            logger.warning("alertmanager_connection_failed", error=str(e))

        # Inicializar clientes de notificação (opcional)
        slack_client = None
        if settings.slack.webhook_url:
            slack_client = SlackClient(webhook_url=settings.slack.webhook_url)
            await slack_client.connect()
            logger.info("slack_client_connected")

        pagerduty_client = None
        if settings.pagerduty.routing_key:
            pagerduty_client = PagerDutyClient(
                routing_key=settings.pagerduty.routing_key,
                api_url=settings.pagerduty.api_url,
            )
            await pagerduty_client.connect()
            logger.info("pagerduty_client_connected")

        # Inicializar serviços
        budget_calculator = BudgetCalculator(
            prometheus_client, postgresql_client, redis_client, kafka_producer, settings.calculator
        )

        policy_enforcer = PolicyEnforcer(
            postgresql_client, redis_client, kafka_producer, settings.policy
        )

        slo_manager = SLOManager(postgresql_client, prometheus_client)

        # Inicializar AlertDispatcher e AlertEngine (usa clientes diretamente)
        alert_dispatcher = AlertDispatcher(
            slack_webhook_url=settings.slack.webhook_url,
            pagerduty_routing_key=settings.pagerduty.routing_key,
        )
        await alert_dispatcher.connect()

        alert_engine = AlertEngine(
            postgresql_client=postgresql_client,
            redis_client=redis_client,
            alert_dispatcher=alert_dispatcher,
            check_interval_seconds=settings.calculator.calculation_interval_seconds,
        )
        await alert_engine.start()

        # Inicializar SLAAlertConsumer se habilitado
        if settings.sla_alert_consumer.enable_sla_alert_consumer:
            if slack_client and pagerduty_client:
                sla_alert_consumer = SLAAlertConsumer(
                    bootstrap_servers=settings.kafka.bootstrap_servers,
                    topics=settings.sla_alert_consumer.sla_alerts_topics,
                    slack_client=slack_client,
                    pagerduty_client=pagerduty_client,
                    group_id=settings.sla_alert_consumer.consumer_group_id,
                    auto_offset_reset=settings.sla_alert_consumer.auto_offset_reset,
                )
                await sla_alert_consumer.start()
                sla_alert_consumer_task = asyncio.create_task(sla_alert_consumer.consume())
                logger.info("sla_alert_consumer_started")
            else:
                logger.warning(
                    "sla_alert_consumer_not_started",
                    reason="slack_client or pagerduty_client not configured",
                )

        # Iniciar background task de cálculo periódico
        periodic_calculation_task = asyncio.create_task(
            budget_calculator.run_periodic_calculation()
        )

        logger.info("sla_management_system_started")

        yield

    finally:
        # Shutdown
        logger.info("sla_management_system_shutting_down")

        # Parar SLAAlertConsumer
        if sla_alert_consumer_task:
            sla_alert_consumer_task.cancel()
            try:
                await sla_alert_consumer_task
            except asyncio.CancelledError:
                pass

        if sla_alert_consumer:
            await sla_alert_consumer.stop()

        # Parar background tasks
        if periodic_calculation_task:
            budget_calculator.stop_periodic_calculation()
            periodic_calculation_task.cancel()
            try:
                await periodic_calculation_task
            except asyncio.CancelledError:
                pass

        # Parar AlertEngine
        if alert_engine:
            await alert_engine.stop()

        # Fechar AlertDispatcher
        if alert_dispatcher:
            await alert_dispatcher.disconnect()

        # Fechar clientes de notificação
        if slack_client:
            await slack_client.disconnect()

        if pagerduty_client:
            await pagerduty_client.disconnect()

        # Fechar clientes
        if kafka_producer:
            await kafka_producer.stop()

        if redis_client:
            await redis_client.disconnect()

        if postgresql_client:
            await postgresql_client.disconnect()

        if prometheus_client:
            await prometheus_client.disconnect()

        if alertmanager_client:
            await alertmanager_client.disconnect()

        logger.info("sla_management_system_stopped")


# Criar aplicação FastAPI
app = FastAPI(
    title="SLA Management System",
    description="Gerenciamento de SLOs, error budgets e enforcement de políticas",
    version=settings.version,
    lifespan=lifespan,
)

# CORS - usa configuração segura por ambiente via neural_hive_security
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


# Dependency overrides para injetar serviços nos routers
def override_slo_manager():
    return slo_manager


def override_budget_calculator():
    return budget_calculator


def override_policy_enforcer():
    return policy_enforcer


def override_postgresql_client():
    return postgresql_client


def override_prometheus_client():
    return prometheus_client


def override_alert_engine():
    return alert_engine


app.dependency_overrides[slos.get_slo_manager] = override_slo_manager
app.dependency_overrides[budgets.get_budget_calculator] = override_budget_calculator
app.dependency_overrides[budgets.get_postgresql_client] = override_postgresql_client
app.dependency_overrides[budgets.get_prometheus_client] = override_prometheus_client
app.dependency_overrides[budgets.get_redis_client] = lambda: redis_client
app.dependency_overrides[policies.get_policy_enforcer] = override_policy_enforcer
app.dependency_overrides[policies.get_postgresql_client] = override_postgresql_client
app.dependency_overrides[webhooks.get_slo_manager] = override_slo_manager
app.dependency_overrides[webhooks.get_budget_calculator] = override_budget_calculator
app.dependency_overrides[webhooks.get_policy_enforcer] = override_policy_enforcer
app.dependency_overrides[webhooks.get_postgresql_client] = override_postgresql_client
app.dependency_overrides[alerts.get_alert_engine] = override_alert_engine
app.dependency_overrides[alerts.get_postgresql_client] = override_postgresql_client


# Registrar routers
app.include_router(slos.router)
app.include_router(budgets.router)
app.include_router(policies.router)
app.include_router(webhooks.router)

# Configurar router de alerts com injeção de dependências
alerts.set_alert_engine(alert_engine)
alerts.set_postgresql_client(postgresql_client)
app.include_router(alerts.router)


# Health checks
@app.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness probe."""
    checks = {}

    # Verificar PostgreSQL
    try:
        # Simples query para verificar conectividade
        await postgresql_client.list_slos()
        checks["postgresql"] = "ok"
    except Exception as e:
        checks["postgresql"] = f"error: {e!s}"

    # Verificar Redis
    try:
        redis_ok = await redis_client.health_check()
        checks["redis"] = "ok" if redis_ok else "error"
    except Exception as e:
        checks["redis"] = f"error: {e!s}"

    # Verificar Prometheus
    try:
        prom_ok = await prometheus_client.health_check()
        checks["prometheus"] = "ok" if prom_ok else "error"
    except Exception as e:
        checks["prometheus"] = f"error: {e!s}"

    # Verificar Kafka (opcional)
    if kafka_producer:
        try:
            kafka_ok = await kafka_producer.health_check()
            checks["kafka"] = "ok" if kafka_ok else "error"
        except Exception as e:
            checks["kafka"] = f"error: {e!s}"
    else:
        checks["kafka"] = "disabled"

    # Determinar status geral (considera "disabled" como OK)
    all_ok = all(v in ("ok", "disabled") for v in checks.values())

    return {"status": "ready" if all_ok else "not ready", "checks": checks}


# Métricas Prometheus
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
