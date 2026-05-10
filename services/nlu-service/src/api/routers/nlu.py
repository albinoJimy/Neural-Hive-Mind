"""API REST do NLU Service.

Endpoints (paths conforme spec 2026-05-01-unified-gateway-architecture, TICKET-008):
- POST /parse - Processamento completo
- POST /classify-domain - Classificação de domínio
- POST /extract-entities - Extração de entidades
- POST /calculate-confidence - Cálculo de confiança
- POST /language - Detecção de idioma
- GET /health - Health check (INV-10)
"""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from src.models.nlu import (
    CalculateConfidenceRequest,
    CalculateConfidenceResponse,
    ClassifyDomainRequest,
    ClassifyDomainResponse,
    DetectLanguageRequest,
    DetectLanguageResponse,
    ExtractEntitiesRequest,
    ExtractEntitiesResponse,
    HealthCheckResponse,
    ParseRequest,
    ParseResponse,
    ServingStatus,
)
from src.services.nlu_pipeline import get_nlu_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/nlu", tags=["NLU"])

# Global service reference
_nlu_service = None


async def _get_service():
    """Obter instância do serviço NLU."""
    global _nlu_service
    if _nlu_service is None:
        _nlu_service = await get_nlu_service()
    return _nlu_service


@router.post("/parse", response_model=ParseResponse)
async def parse_text(request: ParseRequest) -> ParseResponse:
    """
    Processar texto completo e retornar resultado NLU.

    INV-1: Retorna NLUResult com domain, entities, confidence, keywords
    """
    service = await _get_service()

    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NLU Service not ready",
        )

    try:
        start_time = time.time()

        # Verificar cache
        cached = False
        if request.enable_cache and service.redis_client:
            cache_key = service._get_cache_key(request.text, request.language, request.context)
            cached_result = await service._get_cached(cache_key)
            if cached_result:
                cached = True
                result = cached_result
            else:
                result = await service.parse(
                    text=request.text,
                    language=request.language,
                    context=request.context,
                )
        else:
            result = await service.parse(
                text=request.text,
                language=request.language,
                context=request.context,
            )

        processing_time_ms = int((time.time() - start_time) * 1000)

        return ParseResponse(
            result=result,
            processing_time_ms=processing_time_ms,
            processed_at=datetime.now(timezone.utc),
            cached=cached,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Erro no processamento NLU: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )


@router.post("/classify-domain", response_model=ClassifyDomainResponse)
async def classify_domain(request: ClassifyDomainRequest) -> ClassifyDomainResponse:
    """Classificar domínio do texto."""
    service = await _get_service()

    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NLU Service not ready",
        )

    try:
        start_time = time.time()

        domain, classification, confidence = await service.classify_domain(
            text=request.text,
            language=request.language,
            context=request.context,
        )

        # Gerar reasoning
        reasoning = f"Classificado como {domain.value} com base em análise de palavras-chave e padrões"

        processing_time_ms = int((time.time() - start_time) * 1000)

        return ClassifyDomainResponse(
            domain=domain,
            confidence=confidence,
            reasoning=reasoning,
            processing_time_ms=processing_time_ms,
            classified_at=datetime.now(timezone.utc),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Erro na classificação de domínio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )


@router.post("/extract-entities", response_model=ExtractEntitiesResponse)
async def extract_entities(request: ExtractEntitiesRequest) -> ExtractEntitiesResponse:
    """Extrair entidades nomeadas do texto."""
    service = await _get_service()

    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NLU Service not ready",
        )

    try:
        start_time = time.time()

        entities = await service.extract_entities(
            text=request.text,
            language=request.language,
        )

        # Filtrar por tipos se especificado
        if request.entity_types:
            allowed_types = set(request.entity_types)
            entities = [e for e in entities if e.type in allowed_types]

        processing_time_ms = int((time.time() - start_time) * 1000)

        return ExtractEntitiesResponse(
            entities=entities,
            processing_time_ms=processing_time_ms,
            extracted_at=datetime.now(timezone.utc),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Erro na extração de entidades: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )


@router.post("/calculate-confidence", response_model=CalculateConfidenceResponse)
async def calculate_confidence(request: CalculateConfidenceRequest) -> CalculateConfidenceResponse:
    """Calcular métricas de confiança detalhadas."""
    service = await _get_service()

    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NLU Service not ready",
        )

    try:
        return await service.calculate_confidence(request.nlu_result)

    except Exception as e:
        logger.exception(f"Erro no cálculo de confiança: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )


@router.post("/language", response_model=DetectLanguageResponse)
async def detect_language(request: DetectLanguageRequest) -> DetectLanguageResponse:
    """Detectar idioma do texto."""
    service = await _get_service()

    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NLU Service not ready",
        )

    try:
        language, confidence, candidates = await service.detect_language(request.text)

        return DetectLanguageResponse(
            language=language,
            confidence=confidence,
            candidates=[
                {"language": lang, "confidence": conf} for lang, conf in candidates
            ],
        )

    except Exception as e:
        logger.exception(f"Erro na detecção de idioma: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal processing error",
        )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """
    Health check do serviço NLU.

    INV-10: Retorna {status, version} JSON
    """
    service = await _get_service() if _nlu_service else None

    is_ready = service.is_ready() if service else False

    return HealthCheckResponse(
        status=ServingStatus.SERVING if is_ready else ServingStatus.NOT_SERVING,
        details={
            "model_loaded": "true" if is_ready else "false",
            "models_count": str(len(service.nlp_models)) if is_ready else "0",
            "cache_enabled": str(service.settings.nlu_cache_enabled) if service else "false",
        },
        version="0.1.0",
    )
