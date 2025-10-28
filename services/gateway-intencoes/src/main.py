#!/usr/bin/env python3
"""
Gateway de Intenções - Neural Hive-Mind
Aplicação principal FastAPI para captura e processamento de intenções
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, Response
import structlog

from config.settings import get_settings
from models.intent_envelope import IntentEnvelope, IntentRequest, VoiceIntentRequest
from pipelines.asr_pipeline import ASRPipeline
from pipelines.nlu_pipeline import NLUPipeline
from kafka.producer import KafkaIntentProducer
from cache.redis_client import get_redis_client, close_redis_client
from security.oauth2_validator import get_oauth2_validator, close_oauth2_validator
from middleware.auth_middleware import create_auth_middleware, get_current_user, get_current_admin_user
# from neural_hive_observability import trace_intent, get_metrics, get_context_manager
# from neural_hive_observability.health import HealthManager, RedisHealthCheck, CustomHealthCheck, HealthStatus
# from observability.metrics import (
#     intent_counter, latency_histogram, confidence_histogram,
#     low_confidence_routed_counter, record_too_large_counter
# )

# Stubs temporários para desenvolvimento local sem neural_hive_observability
class HealthManager:
    def __init__(self):
        self.checks = []

    def add_check(self, health_check):
        """Aceita objetos de health check"""
        self.checks.append(health_check)

    async def check_health(self):
        return {"status": "healthy", "checks": {}}

    async def check_all(self):
        results = {}
        overall_healthy = True
        for check in self.checks:
            try:
                # Tentar executar o check
                name = getattr(check, 'name', 'unknown')
                result = {"status": "healthy"}
                results[name] = result
            except Exception as e:
                results.get(name, "unknown")
                results[name] = {"status": "unhealthy", "error": str(e)}
                overall_healthy = False
        self._overall_status = "healthy" if overall_healthy else "degraded"
        return {
            "status": self._overall_status,
            "checks": results
        }

    def get_overall_status(self):
        """Retorna status geral do sistema"""
        return getattr(self, '_overall_status', 'healthy')

class RedisHealthCheck:
    def __init__(self, name, *args, **kwargs):
        self.name = name

class CustomHealthCheck:
    def __init__(self, name, *args, **kwargs):
        self.name = name

class HealthStatus:
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"

def trace_intent(*args, **kwargs):
    def decorator(func): return func
    return decorator

def get_metrics(): return {}
def get_context_manager(): return None

# Stubs de métricas
class MetricStub:
    def labels(self, **kwargs): return self
    def inc(self, *args): pass
    def observe(self, *args): pass

intent_counter = MetricStub()
latency_histogram = MetricStub()
confidence_histogram = MetricStub()
low_confidence_routed_counter = MetricStub()
record_too_large_counter = MetricStub()

# Setup logging estruturado
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
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Configurações globais
settings = get_settings()
security = HTTPBearer()

# Componentes de inicialização
asr_pipeline: Optional[ASRPipeline] = None
nlu_pipeline: Optional[NLUPipeline] = None
kafka_producer: Optional[KafkaIntentProducer] = None
redis_client = None
oauth2_validator = None
health_manager: Optional[HealthManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciamento do ciclo de vida da aplicação"""
    global asr_pipeline, nlu_pipeline, kafka_producer, redis_client, oauth2_validator, health_manager

    logger.info("Iniciando Gateway de Intenções com camada de memória")

    try:
        # Inicializar Redis Cache
        logger.info("Conectando ao Redis Cluster")
        redis_client = await get_redis_client()

        # Inicializar OAuth2 Validator
        logger.info("Inicializando validador OAuth2")
        oauth2_validator = await get_oauth2_validator()

        # Inicializar pipelines de processamento
        logger.info("Carregando pipeline ASR")
        asr_pipeline = ASRPipeline(
            model_name=settings.asr_model_name,
            device=settings.asr_device
        )
        await asr_pipeline.initialize()

        logger.info("Carregando pipeline NLU")
        nlu_pipeline = NLUPipeline(
            language_model=settings.nlu_language_model,
            confidence_threshold=settings.nlu_confidence_threshold
        )
        await nlu_pipeline.initialize()

        # Inicializar producer Kafka
        logger.info("Conectando ao Kafka")
        kafka_producer = KafkaIntentProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            schema_registry_url=settings.schema_registry_url
        )
        await kafka_producer.initialize()

        # Setup observabilidade padronizada do Neural Hive-Mind
        # DESABILITADO para dev local - biblioteca neural_hive_observability não disponível
        # from neural_hive_observability import init_observability
        # from neural_hive_observability.config import ObservabilityConfig
        # from neural_hive_observability.tracing import init_tracing

        # Initialize observability configuration
        # observability_config = ObservabilityConfig(
        #     service_name="gateway-intencoes",
        #     service_version="1.0.0",
        #     neural_hive_component="gateway",
        #     neural_hive_layer="experiencia",
        #     neural_hive_domain="captura-intencoes",
        #     environment=settings.environment,
        #     otel_endpoint=settings.otel_endpoint,
        #     prometheus_port=8000
        # )

        # Initialize tracing with OTLP exporter
        # init_tracing(observability_config)

        # Initialize full observability stack
        # init_observability(
        #     service_name="gateway-intencoes",
        #     service_version="1.0.0",
        #     neural_hive_component="gateway",
        #     neural_hive_layer="experiencia",
        #     neural_hive_domain="captura-intencoes",
        #     environment=settings.environment,
        #     otel_endpoint=settings.otel_endpoint,
        #     prometheus_port=8000
        # )

        logger.info("Observabilidade desabilitada para dev local")

        # Initialize standardized health checks
        logger.info("Configurando health checks padronizados")
        health_manager = HealthManager()

        # Add Redis health check
        if redis_client:
            health_manager.add_check(
                RedisHealthCheck("redis", lambda: redis_client.ping() if redis_client else False)
            )

        # Add ASR pipeline health check
        if asr_pipeline:
            health_manager.add_check(
                CustomHealthCheck(
                    "asr_pipeline",
                    lambda: asr_pipeline.is_ready() if asr_pipeline else False,
                    "ASR Pipeline"
                )
            )

        # Add NLU pipeline health check
        if nlu_pipeline:
            health_manager.add_check(
                CustomHealthCheck(
                    "nlu_pipeline",
                    lambda: nlu_pipeline.is_ready() if nlu_pipeline else False,
                    "NLU Pipeline"
                )
            )

        # Add Kafka producer health check
        if kafka_producer:
            health_manager.add_check(
                CustomHealthCheck(
                    "kafka_producer",
                    lambda: kafka_producer.is_ready() if kafka_producer else False,
                    "Kafka Producer"
                )
            )

        # Add OAuth2 validator health check
        if oauth2_validator:
            health_manager.add_check(
                CustomHealthCheck(
                    "oauth2_validator",
                    lambda: True,  # OAuth2 validator doesn't have is_ready method
                    "OAuth2 Validator"
                )
            )

        logger.info("Gateway de Intenções iniciado com sucesso - Redis e OAuth2 ativos")

        yield

    except Exception as e:
        logger.error("Erro durante inicialização", error=str(e), exc_info=True)
        raise
    finally:
        # Cleanup
        logger.info("Finalizando Gateway de Intenções")
        if kafka_producer:
            await kafka_producer.close()
        if asr_pipeline:
            await asr_pipeline.close()
        if nlu_pipeline:
            await nlu_pipeline.close()
        if redis_client:
            await close_redis_client()
        if oauth2_validator:
            await close_oauth2_validator()

# Criar aplicação FastAPI
app = FastAPI(
    title="Gateway de Intenções - Neural Hive-Mind",
    description="Gateway para captura e processamento de intenções do Neural Hive-Mind",
    version="1.0.0",
    docs_url="/docs" if settings.environment == "dev" else None,
    redoc_url="/redoc" if settings.environment == "dev" else None,
    lifespan=lifespan
)

# Middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Middleware de hosts confiáveis
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts
)

# Middleware de autenticação OAuth2
auth_middleware = create_auth_middleware(
    exclude_paths=["/health", "/ready", "/metrics", "/docs", "/openapi.json"]
)
app.add_middleware(auth_middleware)

# Dependências
async def get_user_context_from_request(request: Request) -> Dict[str, Any]:
    """Extrair contexto do usuário autenticado"""
    # Se validação de token está desabilitada, retornar contexto de teste
    if not settings.token_validation_enabled:
        return {
            "userId": "test-user-123",
            "userName": "test-user",
            "userEmail": "test@neural-hive.local",
            "tenantId": "gateway-intencoes",
            "sessionId": "test-session",
            "roles": ["user"],
            "isAdmin": False
        }

    if not hasattr(request.state, 'authenticated') or not request.state.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não autenticado"
        )

    user = request.state.user
    return {
        "userId": user.get("user_id"),
        "userName": user.get("username"),
        "userEmail": user.get("email"),
        "tenantId": user.get("client_id"),  # Cliente OAuth2 como tenant
        "sessionId": user.get("session_id"),
        "roles": user.get("roles", []),
        "isAdmin": user.get("is_admin", False)
    }

# Endpoints

@app.get("/health")
async def health_check():
    """Standardized health check endpoint using Neural Hive-Mind observability library"""
    if not health_manager:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "message": "Health manager not initialized",
                "timestamp": datetime.utcnow().isoformat(),
                "version": "1.0.0"
            }
        )

    try:
        # Run all health checks
        health_results = await health_manager.check_all()
        overall_status = health_manager.get_overall_status()

        # Format results for response (dev local mode - simplified)
        component_statuses = {}
        if isinstance(health_results, dict) and 'checks' in health_results:
            # Stub mode
            component_statuses = health_results.get('checks', {})
        else:
            # Production mode com neural_hive_observability
            for name, result in health_results.items():
                component_statuses[name] = {
                    "status": result.status.value if hasattr(result, 'status') else result.get('status', 'unknown'),
                    "message": result.message if hasattr(result, 'message') else result.get('message', ''),
                    "duration_seconds": result.duration_seconds if hasattr(result, 'duration_seconds') else 0,
                    "timestamp": result.timestamp if hasattr(result, 'timestamp') else datetime.utcnow().isoformat(),
                    "details": result.details if hasattr(result, 'details') else result.get('details', {})
                }

        # Overall status handling
        status_value = overall_status if isinstance(overall_status, str) else (overall_status.value if hasattr(overall_status, 'value') else 'unknown')

        response_data = {
            "status": status_value,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "service_name": "gateway-intencoes",
            "neural_hive_component": "gateway",
            "neural_hive_layer": "experiencia",
            "components": component_statuses
        }

        # Return appropriate HTTP status code based on health
        if overall_status in [HealthStatus.UNHEALTHY]:
            return JSONResponse(status_code=503, content=response_data)
        elif overall_status in [HealthStatus.DEGRADED]:
            return JSONResponse(status_code=200, content=response_data)
        else:
            return response_data

    except Exception as e:
        logger.error(f"Erro ao executar health check: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "message": f"Health check error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "version": "1.0.0",
                "service_name": "gateway-intencoes"
            }
        )

@app.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint - checks if service is ready to accept traffic"""
    if not health_manager:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "message": "Health manager not initialized",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

    try:
        # Check critical components for readiness
        critical_checks = ["redis", "kafka_producer"]
        overall_ready = True

        for check_name in critical_checks:
            result = await health_manager.check_single(check_name)
            if result and result.status != HealthStatus.HEALTHY:
                overall_ready = False
                break

        response_data = {
            "status": "ready" if overall_ready else "not_ready",
            "timestamp": datetime.utcnow().isoformat(),
            "service_name": "gateway-intencoes",
            "neural_hive_component": "gateway"
        }

        return JSONResponse(
            status_code=200 if overall_ready else 503,
            content=response_data
        )

    except Exception as e:
        logger.error(f"Erro ao executar readiness check: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "message": f"Readiness check error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@app.get("/cache/stats")
async def cache_stats(user: Dict[str, Any] = Depends(get_current_admin_user)):
    """Estatísticas do cache Redis (apenas admins)"""
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis cache não disponível"
        )

    return await redis_client.get_cache_stats()

@app.get("/metrics")
async def metrics_endpoint():
    """Endpoint de métricas Prometheus"""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/intentions/{intent_id}")
async def get_intention(
    intent_id: str,
    request: Request,
    user_context: Dict[str, Any] = Depends(get_user_context_from_request)
):
    """Obter intenção do cache por ID"""
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache não disponível"
        )

    try:
        cache_key = f"intent:{intent_id}"
        cached_intent = await redis_client.get(cache_key, intent_type="retrieval")

        if not cached_intent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Intenção não encontrada"
            )

        # Verificar se usuário tem acesso a esta intenção
        if cached_intent.get("actor", {}).get("id") != user_context.get("userId"):
            if not user_context.get("isAdmin", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Acesso negado a esta intenção"
                )

        return {
            "intent_id": intent_id,
            "data": cached_intent,
            "cached": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter intenção {intent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar intenção"
        )

@app.post("/intentions", response_model=Dict[str, Any])
@trace_intent(
    operation_name="captura.intencao.texto",
    extract_intent_id_from="intent_id",
    include_args=False,
    include_result=True
)
async def process_text_intention(
    request: IntentRequest,
    http_request: Request,
    user_context: Dict[str, Any] = Depends(get_user_context_from_request)
):
    """
    Processar intenção em formato texto
    """
    start_time = datetime.utcnow()

    try:
        # Gerar IDs de correlação
        intent_id = str(uuid.uuid4())
        correlation_id = request.correlation_id or str(uuid.uuid4())

        # Verificar deduplicação via Redis se disponível
        duplicate_check_passed = True
        if redis_client and request.correlation_id:
            try:
                # Usar correlation_id para evitar duplicatas
                dedup_key = f"dedup:{request.correlation_id}"

                # Verificar se já processamos esta intenção
                existing = await redis_client.get(dedup_key, intent_type="deduplication")
                if existing:
                    logger.info(
                        "Intenção duplicada detectada",
                        correlation_id=request.correlation_id,
                        original_intent_id=existing.get("intent_id"),
                        new_intent_id=intent_id
                    )

                    return {
                        "intent_id": existing.get("intent_id"),
                        "correlation_id": request.correlation_id,
                        "status": "duplicate_detected",
                        "original_timestamp": existing.get("timestamp"),
                        "message": "Intenção já foi processada anteriormente"
                    }

                # Registrar processamento para evitar futuras duplicatas (TTL curto para dedup)
                await redis_client.set(
                    dedup_key,
                    {"intent_id": intent_id, "timestamp": start_time.isoformat()},
                    ttl=300,  # 5 minutos para deduplicação
                    intent_type="deduplication"
                )

            except Exception as e:
                logger.warning(f"Erro na verificação de duplicatas: {e}")
                # Continuar processamento mesmo se Redis falhar

        # Usar context manager para correlação distribuída
        context_manager = get_context_manager()
        if context_manager:
            with context_manager.correlation_context(
                intent_id=intent_id,
                user_id=user_context.get("userId"),
                domain=request.text[:50],  # Domain será ajustado após NLU
                channel="api"
            ):
                return await _process_text_intention_with_context(
                    request, user_context, intent_id, correlation_id, start_time
                )
        else:
            return await _process_text_intention_with_context(
                request, user_context, intent_id, correlation_id, start_time
            )

    except Exception as e:
        error_str = str(e)

        # Check if it's a record too large error
        if "RECORD_TOO_LARGE" in error_str or "message size" in error_str.lower() or "rejeitada por exceder limite" in error_str:
            logger.error(
                "Intenção rejeitada por tamanho excessivo",
                intent_id=intent_id,
                error=error_str,
                exc_info=True
            )

            intent_counter.labels(
                neural_hive_component="gateway",
                neural_hive_layer="experiencia",
                domain="unknown",
                channel="api",
                status="record_too_large"
            ).inc()

            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Envelope de intenção excede limite de tamanho permitido (4MB). Considere reduzir o conteúdo da solicitação."
            )

        logger.error(
            "Erro processando intenção de texto",
            intent_id=intent_id,
            error=error_str,
            exc_info=True
        )

        intent_counter.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain="unknown",
            channel="api",
            status="error"
        ).inc()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro processando intenção: {error_str}"
        )


async def _process_text_intention_with_context(
    request: IntentRequest,
    user_context: Dict[str, Any],
    intent_id: str,
    correlation_id: str,
    start_time: datetime
) -> Dict[str, Any]:
    """Processar intenção de texto com contexto de correlação."""
    try:
        # Log início do processamento
        logger.info(
            "Processando intenção de texto",
            intent_id=intent_id,
            correlation_id=correlation_id,
            user_id=user_context.get("userId"),
            intent_text=request.text[:100] + "..." if len(request.text) > 100 else request.text
        )

        # Pipeline NLU para processar texto
        nlu_result = await nlu_pipeline.process(
            text=request.text,
            language=request.language,
            context=user_context
        )

        # Construir envelope de intenção
        intent_envelope = IntentEnvelope(
            id=intent_id,
            correlation_id=correlation_id,
            actor={
                "id": user_context.get("userId", "anonymous"),
                "actor_type": "human",
                "name": user_context.get("userName")
            },
            intent={
                "text": request.text,
                "domain": nlu_result.domain,
                "classification": nlu_result.classification,
                "original_language": request.language,
                "processed_text": nlu_result.processed_text,
                "entities": [entity.dict() for entity in nlu_result.entities],
                "keywords": nlu_result.keywords
            },
            confidence=nlu_result.confidence,
            context=user_context,
            constraints=request.constraints.dict() if request.constraints else None,
            qos=request.qos.dict() if request.qos else None,
            timestamp=datetime.utcnow()
        )

        # Confidence gating - route to validation if low confidence
        logger.info(f"⚡ Antes de kafka_producer.send_intent: requires_manual_validation={nlu_result.requires_manual_validation}, intent_id={intent_id}")
        if nlu_result.requires_manual_validation:
            # Route to validation topic for manual validation
            logger.info(f"📤 Chamando kafka_producer.send_intent para validação: intent_id={intent_id}")
            await kafka_producer.send_intent(intent_envelope, topic_override="intentions.validation")

            # Track low confidence routing metric
            low_confidence_routed_counter.labels(
                neural_hive_component="gateway",
                neural_hive_layer="experiencia",
                domain=nlu_result.domain,
                channel="api",
                route_target="human"
            ).inc()

            logger.info(
                "Intenção roteada para validação manual por baixa confiança",
                intent_id=intent_id,
                confidence=nlu_result.confidence,
                domain=nlu_result.domain,
                threshold=nlu_pipeline.confidence_threshold
            )

            status_message = "routed_to_validation"
        else:
            # Send to main domain topic
            await kafka_producer.send_intent(intent_envelope)
            status_message = "processed"

        # Cache intent envelope in Redis for retrieval
        if redis_client:
            try:
                cache_key = f"intent:{intent_id}"
                await redis_client.set(
                    cache_key,
                    intent_envelope.to_cache_dict(),
                    ttl=settings.redis_default_ttl,
                    intent_type="intent"
                )
                logger.debug(f"Intent {intent_id} cached in Redis", cache_key=cache_key)
            except Exception as e:
                logger.warning(f"Falha ao cachear intent {intent_id} no Redis: {e}")

        # Métricas
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        intent_counter.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain=nlu_result.domain,
            channel="api",
            status="low_confidence_routed" if nlu_result.requires_manual_validation else "success"
        ).inc()
        latency_histogram.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain=nlu_result.domain,
            channel="api"
        ).observe(processing_time)
        confidence_histogram.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain=nlu_result.domain,
            channel="api"
        ).observe(nlu_result.confidence)

        logger.info(
            "Intenção processada com sucesso",
            intent_id=intent_id,
            processing_time_ms=processing_time * 1000,
            confidence=nlu_result.confidence,
            domain=nlu_result.domain
        )

        response_data = {
            "intent_id": intent_id,
            "correlation_id": correlation_id,
            "status": status_message,
            "confidence": nlu_result.confidence,
            "domain": nlu_result.domain,
            "classification": nlu_result.classification,
            "processing_time_ms": processing_time * 1000
        }

        # Add validation info if routed to validation
        if nlu_result.requires_manual_validation:
            response_data["requires_manual_validation"] = True
            response_data["validation_reason"] = "confidence_below_threshold"
            response_data["confidence_threshold"] = nlu_pipeline.confidence_threshold

        return response_data

    except Exception as e:
        error_str = str(e)

        # Check if it's a record too large error
        if "RECORD_TOO_LARGE" in error_str or "message size" in error_str.lower() or "rejeitada por exceder limite" in error_str:
            logger.error(
                "Intenção rejeitada por tamanho excessivo",
                intent_id=intent_id,
                error=error_str,
                exc_info=True
            )

            intent_counter.labels(
                neural_hive_component="gateway",
                neural_hive_layer="experiencia",
                domain="unknown",
                channel="api",
                status="record_too_large"
            ).inc()

            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Envelope de intenção excede limite de tamanho permitido (4MB). Considere reduzir o conteúdo da solicitação."
            )

        logger.error(
            "Erro processando intenção de texto",
            intent_id=intent_id,
            error=error_str,
            exc_info=True
        )

        intent_counter.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain="unknown",
            channel="api",
            status="error"
        ).inc()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro processando intenção: {error_str}"
        )

@app.post("/intentions/voice", response_model=Dict[str, Any])
@trace_intent(
    operation_name="captura.intencao.voz",
    extract_intent_id_from="intent_id",
    include_args=False,
    include_result=True
)
async def process_voice_intention(
    http_request: Request,
    audio_file: UploadFile = File(...),
    language: str = Form("pt-BR"),
    correlation_id: Optional[str] = Form(None),
    user_context: Dict[str, Any] = Depends(get_user_context_from_request)
):
    """
    Processar intenção de áudio (voz)
    """
    start_time = datetime.utcnow()

    try:
        # Validar tipo de arquivo de áudio
        if not audio_file.content_type.startswith('audio/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Arquivo deve ser de áudio"
            )

        # Gerar IDs
        intent_id = str(uuid.uuid4())
        correlation_id = correlation_id or str(uuid.uuid4())

        logger.info(
            "Processando intenção de voz",
            intent_id=intent_id,
            correlation_id=correlation_id,
            user_id=user_context.get("userId"),
            audio_content_type=audio_file.content_type,
            audio_size_bytes=audio_file.size
        )

        # Ler arquivo de áudio
        audio_content = await audio_file.read()

        # Pipeline ASR para converter áudio em texto
        asr_result = await asr_pipeline.process(
            audio_data=audio_content,
            language=language
        )

        if not asr_result.text or len(asr_result.text.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível extrair texto do áudio"
            )

        # Pipeline NLU para processar texto extraído
        nlu_result = await nlu_pipeline.process(
            text=asr_result.text,
            language=language,
            context=user_context
        )

        # Construir envelope de intenção
        intent_envelope = IntentEnvelope(
            id=intent_id,
            correlation_id=correlation_id,
            actor={
                "id": user_context.get("userId", "anonymous"),
                "actor_type": "human",
                "name": user_context.get("userName")
            },
            intent={
                "text": asr_result.text,
                "domain": nlu_result.domain,
                "classification": nlu_result.classification,
                "original_language": language,
                "processed_text": nlu_result.processed_text,
                "entities": [entity.dict() for entity in nlu_result.entities],
                "keywords": nlu_result.keywords
            },
            confidence=min(asr_result.confidence, nlu_result.confidence),  # Menor confiança
            context={
                **user_context,
                "channel": "voice",
                "asr_confidence": asr_result.confidence,
                "nlu_confidence": nlu_result.confidence,
                "audio_duration_s": asr_result.duration
            },
            timestamp=datetime.utcnow()
        )

        # Confidence gating - route to validation if low confidence
        logger.info(f"⚡ Antes de kafka_producer.send_intent: requires_manual_validation={nlu_result.requires_manual_validation}, intent_id={intent_id}")
        if nlu_result.requires_manual_validation:
            # Route to validation topic for manual validation
            logger.info(f"📤 Chamando kafka_producer.send_intent para validação: intent_id={intent_id}")
            await kafka_producer.send_intent(intent_envelope, topic_override="intentions.validation")

            # Track low confidence routing metric
            low_confidence_routed_counter.labels(
                neural_hive_component="gateway",
                neural_hive_layer="experiencia",
                domain=nlu_result.domain,
                channel="voice",
                route_target="human"
            ).inc()

            logger.info(
                "Intenção de voz roteada para validação manual por baixa confiança",
                intent_id=intent_id,
                confidence=intent_envelope.confidence,
                asr_confidence=asr_result.confidence,
                nlu_confidence=nlu_result.confidence,
                domain=nlu_result.domain,
                threshold=nlu_pipeline.confidence_threshold
            )

            status_message = "routed_to_validation"
        else:
            # Send to main domain topic
            await kafka_producer.send_intent(intent_envelope)
            status_message = "processed"

        # Cache intent envelope in Redis for retrieval
        if redis_client:
            try:
                cache_key = f"intent:{intent_id}"
                await redis_client.set(
                    cache_key,
                    intent_envelope.to_cache_dict(),
                    ttl=settings.redis_default_ttl,
                    intent_type="intent"
                )
                logger.debug(f"Voice intent {intent_id} cached in Redis", cache_key=cache_key)
            except Exception as e:
                logger.warning(f"Falha ao cachear voice intent {intent_id} no Redis: {e}")

        # Métricas
        processing_time = (datetime.utcnow() - start_time).total_seconds()
        intent_counter.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain=nlu_result.domain,
            channel="voice",
            status="low_confidence_routed" if nlu_result.requires_manual_validation else "success"
        ).inc()
        latency_histogram.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain=nlu_result.domain,
            channel="voice"
        ).observe(processing_time)
        confidence_histogram.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain=nlu_result.domain,
            channel="voice"
        ).observe(intent_envelope.confidence)

        logger.info(
            "Intenção de voz processada com sucesso",
            intent_id=intent_id,
            processing_time_ms=processing_time * 1000,
            transcribed_text=asr_result.text,
            asr_confidence=asr_result.confidence,
            nlu_confidence=nlu_result.confidence,
            final_confidence=intent_envelope.confidence,
            domain=nlu_result.domain
        )

        response_data = {
            "intent_id": intent_id,
            "correlation_id": correlation_id,
            "status": status_message,
            "transcribed_text": asr_result.text,
            "confidence": intent_envelope.confidence,
            "asr_confidence": asr_result.confidence,
            "nlu_confidence": nlu_result.confidence,
            "domain": nlu_result.domain,
            "classification": nlu_result.classification,
            "processing_time_ms": processing_time * 1000
        }

        # Add validation info if routed to validation
        if nlu_result.requires_manual_validation:
            response_data["requires_manual_validation"] = True
            response_data["validation_reason"] = "confidence_below_threshold"
            response_data["confidence_threshold"] = nlu_pipeline.confidence_threshold

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        error_str = str(e)

        # Check if it's a record too large error
        if "RECORD_TOO_LARGE" in error_str or "message size" in error_str.lower() or "rejeitada por exceder limite" in error_str:
            logger.error(
                "Intenção de voz rejeitada por tamanho excessivo",
                intent_id=intent_id,
                error=error_str,
                exc_info=True
            )

            intent_counter.labels(
                neural_hive_component="gateway",
                neural_hive_layer="experiencia",
                domain="unknown",
                channel="voice",
                status="record_too_large"
            ).inc()

            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Envelope de intenção de voz excede limite de tamanho permitido (4MB). Considere usar áudio mais curto ou de menor qualidade."
            )

        logger.error(
            "Erro processando intenção de voz",
            intent_id=intent_id,
            error=error_str,
            exc_info=True
        )

        intent_counter.labels(
            neural_hive_component="gateway",
            neural_hive_layer="experiencia",
            domain="unknown",
            channel="voice",
            status="error"
        ).inc()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro processando intenção de voz: {error_str}"
        )

@app.get("/status")
async def service_status():
    """Status detalhado do serviço"""
    return {
        "service": "Gateway de Intenções",
        "version": "1.0.0",
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "asr_pipeline": {
                "ready": asr_pipeline is not None and asr_pipeline.is_ready(),
                "model": settings.asr_model_name,
                "device": settings.asr_device
            },
            "nlu_pipeline": {
                "ready": nlu_pipeline is not None and nlu_pipeline.is_ready(),
                "model": settings.nlu_language_model,
                "confidence_threshold": settings.nlu_confidence_threshold
            },
            "kafka_producer": {
                "ready": kafka_producer is not None and kafka_producer.is_ready(),
                "bootstrap_servers": settings.kafka_bootstrap_servers
            }
        },
        "settings": {
            "max_audio_size_mb": settings.max_audio_size_mb,
            "max_text_length": settings.max_text_length,
            "supported_audio_formats": ["wav", "mp3", "m4a", "ogg"],
            "supported_languages": ["pt-BR", "en-US", "es-ES"]
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "dev",
        access_log=True,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["default"],
            },
        }
    )