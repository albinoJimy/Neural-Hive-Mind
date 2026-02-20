"""
Application Bootstrapper - Neural Hive-Mind Gateway

Organiza a inicialização da aplicação em fases bem definidas,
eliminando a complexidade de múltiplos try/except e stubs.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from contextlib import AsyncExitStack

import structlog

logger = structlog.get_logger()


@dataclass
class ApplicationContext:
    """Contexto da aplicação com todos os componentes inicializados."""

    redis_client: Any = None
    oauth2_validator: Any = None
    rate_limiter: Any = None
    asr_pipeline: Any = None
    nlu_pipeline: Any = None
    kafka_producer: Any = None
    health_manager: Any = None
    initialized: bool = False
    errors: List[str] = field(default_factory=list)


class InitializationPhase:
    """Fase de inicialização com retry e fallback controlado."""

    def __init__(self, name: str, required: bool = True, max_retries: int = 3):
        self.name = name
        self.required = required
        self.max_retries = max_retries
        self.initialized = False
        self.error: Optional[str] = None

    async def execute(self, context: ApplicationContext) -> bool:
        """Executa a fase de inicialização."""
        raise NotImplementedError


class InfrastructurePhase(InitializationPhase):
    """Fase 1: Infraestrutura base (Redis, OAuth2, Rate Limiter)."""

    def __init__(self, settings):
        super().__init__("infrastructure", required=True)
        self.settings = settings

    async def execute(self, context: ApplicationContext) -> bool:
        from cache.redis_client import get_redis_client, close_redis_client
        from security.oauth2_validator import (
            get_oauth2_validator,
            close_oauth2_validator,
        )
        from middleware.rate_limiter import RateLimiter, set_rate_limiter

        try:
            # Redis
            logger.info("phase_infrastructure_redis_start")
            context.redis_client = await get_redis_client()
            logger.info("phase_infrastructure_redis_complete")

            # OAuth2
            logger.info("phase_infrastructure_oauth2_start")
            context.oauth2_validator = await get_oauth2_validator()
            logger.info("phase_infrastructure_oauth2_complete")

            # Rate Limiter
            logger.info("phase_infrastructure_rate_limiter_start")
            context.rate_limiter = RateLimiter(
                redis_client=context.redis_client,
                enabled=self.settings.rate_limit_enabled,
                default_limit=self.settings.rate_limit_requests_per_minute,
                burst_size=self.settings.rate_limit_burst_size,
                fail_open=self.settings.rate_limit_fail_open,
            )

            # Carregar configurações de override
            await self._load_rate_limit_overrides(context.rate_limiter)
            set_rate_limiter(context.rate_limiter)

            logger.info(
                "phase_infrastructure_rate_limiter_complete",
                enabled=self.settings.rate_limit_enabled,
                default_limit=self.settings.rate_limit_requests_per_minute,
            )

            return True

        except Exception as e:
            error_msg = f"Infrastructure phase failed: {str(e)}"
            logger.error("phase_infrastructure_failed", error=str(e), exc_info=True)
            context.errors.append(error_msg)
            return False

    async def _load_rate_limit_overrides(self, rate_limiter):
        """Carrega configurações de rate limit por tenant/user."""
        try:
            tenant_overrides = json.loads(self.settings.rate_limit_tenant_overrides)
            for tenant_id, limit in tenant_overrides.items():
                rate_limiter.set_tenant_limit(tenant_id, limit)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug("rate_limit_tenant_overrides_parse_skipped", error=str(e))

        try:
            user_overrides = json.loads(self.settings.rate_limit_user_overrides)
            for user_id, limit in user_overrides.items():
                rate_limiter.set_user_limit(user_id, limit)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug("rate_limit_user_overrides_parse_skipped", error=str(e))


class ProcessingPhase(InitializationPhase):
    """Fase 2: Pipelines de processamento (ASR, NLU)."""

    def __init__(self, settings):
        super().__init__("processing", required=True)
        self.settings = settings

    async def execute(self, context: ApplicationContext) -> bool:
        from pipelines.asr_pipeline import ASRPipeline
        from pipelines.nlu_pipeline import NLUPipeline

        try:
            # ASR Pipeline
            logger.info("phase_processing_asr_start")
            context.asr_pipeline = ASRPipeline(
                model_name=self.settings.asr_model_name, device=self.settings.asr_device
            )
            await context.asr_pipeline.initialize()
            logger.info("phase_processing_asr_complete")

            # NLU Pipeline
            logger.info("phase_processing_nlu_start")
            context.nlu_pipeline = NLUPipeline(
                language_model=self.settings.nlu_language_model,
                confidence_threshold=self.settings.nlu_confidence_threshold,
            )
            await context.nlu_pipeline.initialize()
            logger.info("phase_processing_nlu_complete")

            return True

        except Exception as e:
            error_msg = f"Processing phase failed: {str(e)}"
            logger.error("phase_processing_failed", error=str(e), exc_info=True)
            context.errors.append(error_msg)
            return False


class ObservabilityPhase(InitializationPhase):
    """Fase 3: Observabilidade (OpenTelemetry)."""

    def __init__(self, settings):
        super().__init__("observability", required=False)
        self.settings = settings

    async def execute(self, context: ApplicationContext) -> bool:
        if not self.settings.otel_enabled:
            logger.info("phase_observability_disabled")
            return True  # Não é erro, apenas desabilitado

        try:
            from neural_hive_observability import init_observability

            logger.info("phase_observability_start")
            init_observability(
                service_name="gateway-intencoes",
                service_version="1.0.7",
                neural_hive_component="gateway",
                neural_hive_layer="experiencia",
                neural_hive_domain="captura-intencoes",
                environment=self.settings.environment,
                otel_endpoint=self.settings.otel_endpoint,
                prometheus_port=self.settings.prometheus_port,
            )
            logger.info(
                "phase_observability_complete",
                service_name="gateway-intencoes",
                otel_endpoint=self.settings.otel_endpoint,
            )
            return True

        except ImportError as e:
            logger.warning(
                "phase_observability_library_missing",
                error=str(e),
                message="OpenTelemetry library not available - running without observability",
            )
            return True  # Fallback aceitável

        except Exception as e:
            logger.error("phase_observability_failed", error=str(e), exc_info=True)
            context.errors.append(f"Observability phase failed: {str(e)}")
            return not self.required  # Se não é obrigatório, continua


class MessagingPhase(InitializationPhase):
    """Fase 4: Mensageria (Kafka Producer)."""

    def __init__(self, settings):
        super().__init__("messaging", required=True)
        self.settings = settings

    async def execute(self, context: ApplicationContext) -> bool:
        from kafka.producer import KafkaIntentProducer

        try:
            logger.info("phase_messaging_kafka_start")
            context.kafka_producer = KafkaIntentProducer(
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                schema_registry_url=self.settings.schema_registry_url,
            )
            await context.kafka_producer.initialize()
            logger.info("phase_messaging_kafka_complete")
            return True

        except Exception as e:
            error_msg = f"Messaging phase failed: {str(e)}"
            logger.error("phase_messaging_failed", error=str(e), exc_info=True)
            context.errors.append(error_msg)
            return False


class HealthChecksPhase(InitializationPhase):
    """Fase 5: Health Checks."""

    def __init__(self, settings):
        super().__init__("health_checks", required=False)
        self.settings = settings

    async def execute(self, context: ApplicationContext) -> bool:
        try:
            logger.info("phase_health_checks_start")

            # Detectar versão da biblioteca de observabilidade
            try:
                from neural_hive_observability.health import HealthManager
                from neural_hive_observability.config import ObservabilityConfig
                from neural_hive_observability.health_checks.otel import (
                    OTELPipelineHealthCheck,
                )
                from neural_hive_observability.health import (
                    RedisHealthCheck,
                    CustomHealthCheck,
                )

                # Criar config
                obs_config = ObservabilityConfig(
                    service_name="gateway-intencoes",
                    service_version="1.0.7",
                    neural_hive_component="gateway",
                    neural_hive_layer="experiencia",
                    environment=self.settings.environment,
                )
                context.health_manager = HealthManager(obs_config)

                # Registrar checks
                self._register_checks(
                    context,
                    RedisHealthCheck,
                    CustomHealthCheck,
                    OTELPipelineHealthCheck,
                )

            except ImportError:
                # Fallback para stub simples
                logger.warning("health_checks_using_stub")
                context.health_manager = HealthManagerStub()

            logger.info("phase_health_checks_complete")
            return True

        except Exception as e:
            logger.error("phase_health_checks_failed", error=str(e))
            context.errors.append(f"Health checks phase failed: {str(e)}")
            return not self.required

    def _register_checks(
        self, context, RedisHealthCheck, CustomHealthCheck, OTELPipelineHealthCheck
    ):
        """Registra todos os health checks."""
        if context.redis_client:
            context.health_manager.register_check(
                RedisHealthCheck("redis", context.redis_client.ping)
            )

        if context.asr_pipeline:
            context.health_manager.register_check(
                CustomHealthCheck(
                    "asr_pipeline",
                    lambda: context.asr_pipeline.is_ready()
                    if context.asr_pipeline
                    else False,
                    "ASR Pipeline",
                )
            )

        if context.nlu_pipeline:
            context.health_manager.register_check(
                CustomHealthCheck(
                    "nlu_pipeline",
                    lambda: context.nlu_pipeline.is_ready()
                    if context.nlu_pipeline
                    else False,
                    "NLU Pipeline",
                )
            )

        if context.kafka_producer:
            context.health_manager.register_check(
                CustomHealthCheck(
                    "kafka_producer",
                    lambda: context.kafka_producer.is_ready()
                    if context.kafka_producer
                    else False,
                    "Kafka Producer",
                )
            )

        if context.oauth2_validator:
            context.health_manager.register_check(
                CustomHealthCheck("oauth2_validator", lambda: True, "OAuth2 Validator")
            )

        if self.settings.otel_enabled:
            try:
                otel_health_check = OTELPipelineHealthCheck(
                    otel_endpoint=self.settings.otel_endpoint,
                    service_name="gateway-intencoes",
                    name="otel_pipeline",
                    timeout_seconds=5.0,
                    verify_trace_export=True,
                )
                context.health_manager.register_check(otel_health_check)
                logger.info("health_check_otel_pipeline_registered")
            except Exception as e:
                logger.warning("health_check_otel_pipeline_failed", error=str(e))


class HealthManagerStub:
    """Stub simples para HealthManager quando biblioteca não está disponível."""

    def __init__(self):
        self.checks = []

    def register_check(self, check):
        self.checks.append(check)

    async def check_all(self):
        return {"status": "healthy", "checks": {}}

    def get_overall_status(self):
        return "healthy"


class ApplicationBootstrapper:
    """
    Bootstrapper principal que orquestra a inicialização em fases.

    Usage:
        bootstrapper = ApplicationBootstrapper(settings)
        context = await bootstrapper.bootstrap()

        if context.initialized:
            app = create_app(context)
        else:
            raise RuntimeError(f"Failed to initialize: {context.errors}")
    """

    def __init__(self, settings):
        self.settings = settings
        self.phases: List[InitializationPhase] = []
        self.exit_stack = AsyncExitStack()

        # Configurar fases
        self._setup_phases()

    def _setup_phases(self):
        """Configura a ordem das fases de inicialização."""
        self.phases = [
            InfrastructurePhase(self.settings),
            ProcessingPhase(self.settings),
            ObservabilityPhase(self.settings),
            MessagingPhase(self.settings),
            HealthChecksPhase(self.settings),
        ]

    async def bootstrap(self) -> ApplicationContext:
        """
        Executa todas as fases de inicialização.

        Returns:
            ApplicationContext com todos os componentes ou erros.
        """
        logger.info("bootstrap_start", total_phases=len(self.phases))

        context = ApplicationContext()

        for i, phase in enumerate(self.phases, 1):
            logger.info(
                "bootstrap_phase_start",
                phase=phase.name,
                phase_number=i,
                total_phases=len(self.phases),
                required=phase.required,
            )

            success = await phase.execute(context)

            if success:
                logger.info("bootstrap_phase_complete", phase=phase.name)
            else:
                logger.error(
                    "bootstrap_phase_failed",
                    phase=phase.name,
                    required=phase.required,
                    error=phase.error,
                )

                if phase.required:
                    logger.error("bootstrap_aborted", failed_phase=phase.name)
                    return context

        context.initialized = True
        logger.info("bootstrap_complete", phases_completed=len(self.phases))

        return context

    async def shutdown(self, context: ApplicationContext):
        """Realiza cleanup de todos os componentes."""
        logger.info("shutdown_start")

        if context.kafka_producer:
            try:
                await context.kafka_producer.close()
                logger.info("shutdown_kafka_complete")
            except Exception as e:
                logger.error("shutdown_kafka_error", error=str(e))

        if context.asr_pipeline:
            try:
                await context.asr_pipeline.close()
                logger.info("shutdown_asr_complete")
            except Exception as e:
                logger.error("shutdown_asr_error", error=str(e))

        if context.nlu_pipeline:
            try:
                await context.nlu_pipeline.close()
                logger.info("shutdown_nlu_complete")
            except Exception as e:
                logger.error("shutdown_nlu_error", error=str(e))

        if context.redis_client:
            try:
                from cache.redis_client import close_redis_client

                await close_redis_client()
                logger.info("shutdown_redis_complete")
            except Exception as e:
                logger.error("shutdown_redis_error", error=str(e))

        if context.oauth2_validator:
            try:
                from security.oauth2_validator import close_oauth2_validator

                await close_oauth2_validator()
                logger.info("shutdown_oauth2_complete")
            except Exception as e:
                logger.error("shutdown_oauth2_error", error=str(e))

        if context.rate_limiter:
            try:
                from middleware.rate_limiter import close_rate_limiter

                close_rate_limiter()
                logger.info("shutdown_rate_limiter_complete")
            except Exception as e:
                logger.error("shutdown_rate_limiter_error", error=str(e))

        logger.info("shutdown_complete")


# Função helper para uso direto
async def bootstrap_application(settings) -> ApplicationContext:
    """Helper function para inicializar a aplicação."""
    bootstrapper = ApplicationBootstrapper(settings)
    return await bootstrapper.bootstrap()
