"""Router principal do Unified Gateway.

Implementa o endpoint POST /api/v1/nhm/request que orquestra:
1. Context Builder → extrai tenant_id, session_id, user_id
2. Intent Classifier → classifica para FlowType (A-F, G, H)
3. Flow Router → proxy para gateway específico
4. Response Processor → formatação unificada + eventos Kafka

Este é o endpoint principal especificado na US-001 do spec.
"""

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.middleware import get_auth_context_optional
from src.models.classification import ClassificationDecision, FlowType
from src.services.context_builder import ContextBuilder, get_context_builder
from src.services.flow_router import FlowRouter, get_flow_router
from src.services.nlu_client import get_intent_classifier
from src.services.resilience import ResilienceNLUService, get_resilience_nlu
from src.services.response_processor import ResponseProcessor, get_response_processor
from src.api.routers.status import save_request_status

logger = structlog.get_logger(__name__)

request_router = APIRouter()


class NHMRequest(BaseModel):
    """Request para o Unified Gateway."""

    input: str = Field(
        ...,
        description="Input de texto para processamento",
        min_length=1,
        max_length=10000,
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Contexto adicional (opcional)",
    )
    language: str | None = Field(
        default="pt",
        description="Idioma do input (pt, en, es)",
    )
    flow_type: FlowType | None = Field(
        default=None,
        description="Flow type explícito (opcional - para debugging/testing)",
    )
    model_config = {"extra": "allow"}


class NHMRequestResponse(BaseModel):
    """Response padrão do Unified Gateway."""

    request_id: str
    flow_type: str
    status: str
    processing_time_ms: int
    data: dict[str, Any] | None = None
    error: str | None = None
    gateway_used: str | None = None
    trace_id: str | None = None
    fallback_used: bool = False


class ClassificationInfo(BaseModel):
    """Informações sobre a classificação."""

    flow_type: str
    confidence: float
    reasoning: str
    alternative: str | None = None


class DetailedResponse(NHMRequestResponse):
    """Response detalhada com informações de classificação."""

    classification: ClassificationInfo | None = None
    nlu_result: dict[str, Any] | None = None


@request_router.post("/api/v1/nhm/request", response_model=NHMRequestResponse)
async def nhm_request(
    request: Request,
    body: NHMRequest,
    auth_context=Depends(get_auth_context_optional),
    context_builder: ContextBuilder = Depends(get_context_builder),
    flow_router: FlowRouter = Depends(get_flow_router),
    response_processor: ResponseProcessor = Depends(get_response_processor),
    resilience_nlu: ResilienceNLUService = Depends(get_resilience_nlu),
) -> NHMRequestResponse:
    """
    Endpoint principal do Unified Gateway.

    Implementa US-001: Cliente Simplificado.
    Recebe requests de qualquer tipo (A-F, G, H) e roteia automaticamente.

    Fluxo:
    1. Context Builder → extrai tenant_id, session_id, user_id do JWT
    2. Intent Classifier → classifica usando NLU Service + heurísticas
    3. Flow Router → proxy HTTP para gateway específico
    4. Response Processor → formatação unificada + eventos Kafka

    Args:
        request: Request FastAPI
        body: NHMRequest com input e contexto
        auth_context: Contexto de autenticação (extraído pelo JWTAuthMiddleware)
        context_builder: Builder de contexto (injetado)
        flow_router: Router de fluxo (injetado)
        response_processor: Processor de resposta (injetado)
        nlu_client: Cliente NLU Service (injetado)

    Returns:
        NHMRequestResponse com resultado processado
    """
    start_time = time.time()

    # 1. Context Builder - construir RequestContext
    request_context = await context_builder.build(
        request=request,
        input_data={"input": body.input, "context": body.context},
    )

    request_id = request_context.request_id
    tenant_id = request_context.tenant.tenant_id if request_context.tenant else None
    user_id = request_context.actor.actor_id if request_context.actor else None

    logger.info(
        "processing_nhm_request",
        request_id=request_id,
        tenant_id=tenant_id,
        user_id=user_id,
        input_length=len(body.input),
    )

    # Status Tracking - marcar como processing
    await save_request_status(
        request_id=request_id,
        status_value="processing",
        flow_type=None,
    )

    # 2. Intent Classifier - classificar intenção
    intent_classifier = get_intent_classifier()

    # Se flow_type especificado, usar diretamente
    if body.flow_type:
        classification_decision = ClassificationDecision(
            flow_type=body.flow_type,
            confidence=1.0,
            reasoning="Flow type explícito fornecido",
            alternative=None,
        )
        logger.info(
            "using_explicit_flow_type",
            request_id=request_id,
            flow_type=body.flow_type.value,
        )
    else:
        # Classificar usando NLU Service + heurísticas
        classification_decision = await intent_classifier.classify(
            text=body.input,
            language=body.language or "pt",
            context=body.context or {},
        )

        logger.info(
            "classified_intent",
            request_id=request_id,
            flow_type=classification_decision.flow_type.value,
            confidence=classification_decision.confidence,
            reasoning=classification_decision.reasoning,
        )

    # 3. Flow Router - rotear para gateway específico
    try:
        # Extrair headers da request original
        request_headers = dict(request.headers)

        # Adicionar headers de contexto (INV-7)
        if tenant_id:
            request_headers["X-Tenant-ID"] = tenant_id
        if user_id:
            request_headers["X-User-ID"] = user_id
        if request_context.session.session_id:
            request_headers["X-Session-ID"] = request_context.session.session_id

        # Fazer proxy para gateway downstream
        status_code, response_headers, response_body = await flow_router.route_with_fallback(
            decision=classification_decision,
            request_method="POST",
            request_path="/api/v1/process",  # Endpoint padrão dos gateways
            request_headers=request_headers,
            request_body=body.input.encode("utf-8"),
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "gateway_response",
            request_id=request_id,
            status_code=status_code,
            processing_time_ms=processing_time_ms,
        )

        # 4. Response Processor - formatar e publicar evento
        gateway_used = flow_router.GATEWAY_CONFIGS.get(classification_decision.flow_type)
        gateway_name = gateway_used.name if gateway_used else None

        unified_response, event_published = await response_processor.process_and_publish(
            request_id=request_id,
            flow_type=classification_decision.flow_type,
            status_code=status_code,
            body=response_body,
            headers=response_headers,
            processing_time_ms=processing_time_ms,
            tenant_id=tenant_id,
            user_id=user_id,
            gateway_used=gateway_name,
            fallback_used=False,  # TODO: detectar se fallback foi usado
        )

        logger.info(
            "request_completed",
            request_id=request_id,
            status=unified_response.status,
            event_published=event_published,
        )

        # Status Tracking - marcar como completed
        await save_request_status(
            request_id=request_id,
            status_value="completed",
            flow_type=unified_response.flow_type,
            processing_time_ms=processing_time_ms,
            gateway_used=gateway_name,
            data=unified_response.data,
        )

        return NHMRequestResponse(
            request_id=request_id,
            flow_type=unified_response.flow_type,
            status=unified_response.status.value,
            processing_time_ms=unified_response.processing_time_ms,
            data=unified_response.data,
            error=unified_response.error,
            gateway_used=unified_response.gateway_used,
            trace_id=unified_response.trace_id,
            fallback_used=unified_response.fallback_used,
        )

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.exception(
            "request_failed",
            request_id=request_id,
            error=str(e),
            processing_time_ms=processing_time_ms,
        )

        # Status Tracking - marcar como failed
        await save_request_status(
            request_id=request_id,
            status_value="failed",
            flow_type=classification_decision.flow_type.value
            if hasattr(classification_decision, "flow_type")
            else None,
            processing_time_ms=processing_time_ms,
            error=str(e),
        )

        # Response Processor - formatar erro
        error_response = await response_processor.format_response(
            request_id=request_id,
            flow_type=classification_decision.flow_type,
            status_code=500,
            body=None,
            headers={},
            processing_time_ms=processing_time_ms,
            gateway_used=None,
        )

        # Publicar evento de falha
        await response_processor.publish_event(
            request_id=request_id,
            flow_type=classification_decision.flow_type,
            status=error_response.status,
            processing_time_ms=processing_time_ms,
            tenant_id=tenant_id,
            user_id=user_id,
            error_message=str(e),
        )

        return NHMRequestResponse(
            request_id=request_id,
            flow_type=classification_decision.flow_type.value,
            status="error",
            processing_time_ms=processing_time_ms,
            error=str(e),
            trace_id=None,
        )


@request_router.post("/api/v1/nhm/request/detailed", response_model=DetailedResponse)
async def nhm_request_detailed(
    request: Request,
    body: NHMRequest,
    auth_context=Depends(get_auth_context_optional),
    context_builder: ContextBuilder = Depends(get_context_builder),
    flow_router: FlowRouter = Depends(get_flow_router),
    response_processor: ResponseProcessor = Depends(get_response_processor),
    resilience_nlu: ResilienceNLUService = Depends(get_resilience_nlu),
) -> DetailedResponse:
    """
    Endpoint detalhado com informações de classificação.

    Inclui informações de debug sobre a classificação e NLU.
    """
    start_time = time.time()

    # 1. Context Builder
    request_context = await context_builder.build(
        request=request,
        input_data={"input": body.input, "context": body.context},
    )

    request_id = request_context.request_id
    tenant_id = request_context.tenant.tenant_id if request_context.tenant else None
    user_id = request_context.actor.actor_id if request_context.actor else None

    # 2. Intent Classifier
    intent_classifier = get_intent_classifier()
    classification_decision = await intent_classifier.classify(
        text=body.input,
        language=body.language or "pt",
        context=body.context or {},
    )

    # Obter NLU result (se disponível) via ResilienceNLUService
    nlu_result_dict = None
    try:
        nlu_result = await resilience_nlu.parse(
            text=body.input,
            language=body.language or "pt",
            context=body.context or {},
            enable_cache=True,
        )
        nlu_result_dict = nlu_result.model_dump()
    except Exception as e:
        logger.warning(f"Failed to get NLU result for detailed response: {e}")

    # 3. Flow Router
    try:
        request_headers = dict(request.headers)
        if tenant_id:
            request_headers["X-Tenant-ID"] = tenant_id
        if user_id:
            request_headers["X-User-ID"] = user_id

        status_code, response_headers, response_body = await flow_router.route_with_fallback(
            decision=classification_decision,
            request_method="POST",
            request_path="/api/v1/process",
            request_headers=request_headers,
            request_body=body.input.encode("utf-8"),
        )

        processing_time_ms = int((time.time() - start_time) * 1000)

        gateway_used = flow_router.GATEWAY_CONFIGS.get(classification_decision.flow_type)
        gateway_name = gateway_used.name if gateway_used else None

        unified_response, _ = await response_processor.process_and_publish(
            request_id=request_id,
            flow_type=classification_decision.flow_type,
            status_code=status_code,
            body=response_body,
            headers=response_headers,
            processing_time_ms=processing_time_ms,
            tenant_id=tenant_id,
            user_id=user_id,
            gateway_used=gateway_name,
        )

        return DetailedResponse(
            request_id=request_id,
            flow_type=unified_response.flow_type,
            status=unified_response.status.value,
            processing_time_ms=unified_response.processing_time_ms,
            data=unified_response.data,
            error=unified_response.error,
            gateway_used=unified_response.gateway_used,
            trace_id=unified_response.trace_id,
            fallback_used=unified_response.fallback_used,
            classification=ClassificationInfo(
                flow_type=classification_decision.flow_type.value,
                confidence=classification_decision.confidence,
                reasoning=classification_decision.reasoning,
                alternative=classification_decision.alternative.value
                if classification_decision.alternative
                else None,
            ),
            nlu_result=nlu_result_dict,
        )

    except Exception as e:
        processing_time_ms = int((time.time() - start_time) * 1000)
        logger.exception("detailed_request_failed", request_id=request_id)

        return DetailedResponse(
            request_id=request_id,
            flow_type=classification_decision.flow_type.value,
            status="error",
            processing_time_ms=processing_time_ms,
            error=str(e),
            classification=ClassificationInfo(
                flow_type=classification_decision.flow_type.value,
                confidence=classification_decision.confidence,
                reasoning=classification_decision.reasoning,
            ),
            nlu_result=nlu_result_dict,
        )


@request_router.get("/api/v1/nhm/capabilities")
async def get_capabilities() -> dict[str, Any]:
    """Retorna as capacidades do Unified Gateway."""
    return {
        "service": "unified-gateway",
        "version": "1.0.0",
        "flows": {
            "A-F": {
                "name": "Cognitive Pipeline",
                "description": "Fluxos de dashboard, relatórios e análise de dados",
                "gateway": "gateway-intencoes:8000",
            },
            "G": {
                "name": "Code Generation",
                "description": "Fluxos de geração de código e criação de apps",
                "gateway": "requirements-engineering:8010",
            },
            "H": {
                "name": "Migration",
                "description": "Fluxos de migração e modernização de legado",
                "gateway": "doc-ingestion:8018",
            },
        },
        "classification": {
            "nlu_service": "nlu-service:8021",
            "domains": ["BUSINESS", "TECHNICAL", "INFRASTRUCTURE", "SECURITY"],
            "fallback": "keyword-based",
        },
        "endpoints": {
            "main": "/api/v1/nhm/request",
            "detailed": "/api/v1/nhm/request/detailed",
            "capabilities": "/api/v1/nhm/capabilities",
        },
    }
