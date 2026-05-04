"""Servidor gRPC do NLU Service.

Implementa a interface NLUService definida em nlu.proto:
- Parse: processamento completo
- ClassifyDomain: classificação de domínio
- ExtractEntities: extração de entidades
- CalculateConfidence: cálculo de confiança
- DetectLanguage: detecção de idioma
- HealthCheck: health check

INV-1: NLU Result Compatibility
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

# Importar proto gerados
import nlu_pb2
import nlu_pb2_grpc

from src.models.nlu import (
    CalculateConfidenceResponse,
    Entity,
    EntityType,
    NLUResult,
    ServingStatus,
    UnifiedDomain,
)
from src.services.nlu_pipeline import get_nlu_service

logger = logging.getLogger(__name__)


# Mapeamentos entre modelos internos e protobuf
_DOMAIN_TO_PROTO = {
    UnifiedDomain.BUSINESS: nlu_pb2.UnifiedDomain.BUSINESS,
    UnifiedDomain.TECHNICAL: nlu_pb2.UnifiedDomain.TECHNICAL,
    UnifiedDomain.INFRASTRUCTURE: nlu_pb2.UnifiedDomain.INFRASTRUCTURE,
    UnifiedDomain.SECURITY: nlu_pb2.UnifiedDomain.SECURITY,
}

_PROTO_TO_DOMAIN = {v: k for k, v in _DOMAIN_TO_PROTO.items()}

_ENTITY_TYPE_TO_PROTO = {
    EntityType.UNKNOWN: nlu_pb2.EntityType.ENTITY_UNKNOWN,
    EntityType.PERSON: nlu_pb2.EntityType.PERSON,
    EntityType.ORG: nlu_pb2.EntityType.ORG,
    EntityType.GPE: nlu_pb2.EntityType.GPE,
    EntityType.LOC: nlu_pb2.EntityType.LOC,
    EntityType.DATE: nlu_pb2.EntityType.DATE,
    EntityType.TIME: nlu_pb2.EntityType.TIME,
    EntityType.MONEY: nlu_pb2.EntityType.MONEY,
    EntityType.PERCENT: nlu_pb2.EntityType.PERCENT,
    EntityType.CARDINAL: nlu_pb2.EntityType.CARDINAL,
    EntityType.ORDINAL: nlu_pb2.EntityType.ORDINAL,
    EntityType.QUANTITY: nlu_pb2.EntityType.QUANTITY,
    EntityType.PRODUCT: nlu_pb2.EntityType.PRODUCT,
    EntityType.EVENT: nlu_pb2.EntityType.EVENT,
    EntityType.WORK_OF_ART: nlu_pb2.EntityType.WORK_OF_ART,
    EntityType.LAW: nlu_pb2.EntityType.LAW,
    EntityType.LANGUAGE: nlu_pb2.EntityType.LANGUAGE,
    EntityType.EMAIL: nlu_pb2.EntityType.EMAIL,
    EntityType.PHONE: nlu_pb2.EntityType.PHONE,
    EntityType.URL: nlu_pb2.EntityType.URL,
    EntityType.IP_ADDRESS: nlu_pb2.EntityType.IP_ADDRESS,
}

_PROTO_TO_ENTITY_TYPE = {v: k for k, v in _ENTITY_TYPE_TO_PROTO.items()}


def nlu_result_to_proto(result: NLUResult) -> nlu_pb2.NLUResult:
    """Converter NLUResult interno para protobuf (INV-1)."""
    return nlu_pb2.NLUResult(
        processed_text=result.processed_text,
        domain=_DOMAIN_TO_PROTO.get(result.domain, nlu_pb2.UnifiedDomain.DOMAIN_UNKNOWN),
        classification=result.classification,
        confidence=result.confidence,
        entities=[
            nlu_pb2.Entity(
                type=_ENTITY_TYPE_TO_PROTO.get(
                    e.type, nlu_pb2.EntityType.ENTITY_UNKNOWN
                ),
                value=e.value,
                confidence=e.confidence,
                start=e.start or 0,
                end=e.end or 0,
                label=e.label or "",
                attributes=e.attributes,
            )
            for e in result.entities
        ],
        keywords=result.keywords,
        original_language=result.original_language,
        requires_manual_validation=result.requires_manual_validation,
        confidence_status=result.confidence_status,
        adaptive_threshold=result.adaptive_threshold or 0.0,
        metadata=result.metadata,
    )


def entity_from_proto(entity: nlu_pb2.Entity) -> Entity:
    """Converter Entity protobuf para modelo interno."""
    return Entity(
        type=_PROTO_TO_ENTITY_TYPE.get(entity.type, EntityType.UNKNOWN),
        value=entity.value,
        confidence=entity.confidence,
        start=entity.start if entity.start > 0 else None,
        end=entity.end if entity.end > 0 else None,
        label=entity.label if entity.label else None,
        attributes=dict(entity.attributes) if entity.attributes else {},
    )


class NLUServicer(nlu_pb2_grpc.NLUServiceServicer):
    """Implementação do serviço NLU gRPC."""

    def __init__(self):
        self.nlu_service = None

    async def _ensure_initialized(self):
        """Garantir que o serviço NLU está inicializado."""
        if self.nlu_service is None:
            self.nlu_service = await get_nlu_service()

    async def Parse(self, request: nlu_pb2.ParseRequest, context: Any) -> nlu_pb2.ParseResponse:
        """Processar texto completo e retornar resultado NLU."""
        start_time = time.time()
        await self._ensure_initialized()

        # Extrair contexto
        request_context = dict(request.context) if request.context else {}

        # Processar
        result = await self.nlu_service.parse(
            text=request.text,
            language=request.language,
            context=request_context,
        )

        # Verificar cache
        cached = False
        if self.nlu_service.redis_client and request.enable_cache:
            cache_key = self.nlu_service._get_cache_key(
                request.text, request.language, request_context
            )
            cached = await self.nlu_service._get_cached(cache_key) is not None

        # Criar timestamp
        processed_at = Timestamp()
        processed_at.GetCurrentTime()

        processing_time_ms = int((time.time() - start_time) * 1000)

        return nlu_pb2.ParseResponse(
            result=nlu_result_to_proto(result),
            processing_time_ms=processing_time_ms,
            processed_at=processed_at,
            cached=cached,
        )

    async def ClassifyDomain(
        self, request: nlu_pb2.ClassifyDomainRequest, context: Any
    ) -> nlu_pb2.ClassifyDomainResponse:
        """Classificar domínio do texto."""
        start_time = time.time()
        await self._ensure_initialized()

        request_context = dict(request.context) if request.context else None

        domain, classification, confidence = await self.nlu_service.classify_domain(
            text=request.text,
            language=request.language,
            context=request_context,
        )

        # Gerar reasoning
        reasoning = f"Classificado como {domain.value} com base em palavras-chave e padrões"

        classified_at = Timestamp()
        classified_at.GetCurrentTime()

        processing_time_ms = int((time.time() - start_time) * 1000)

        return nlu_pb2.ClassifyDomainResponse(
            domain=_DOMAIN_TO_PROTO.get(domain, nlu_pb2.UnifiedDomain.DOMAIN_UNKNOWN),
            confidence=confidence,
            reasoning=reasoning,
            processing_time_ms=processing_time_ms,
            classified_at=classified_at,
        )

    async def ExtractEntities(
        self, request: nlu_pb2.ExtractEntitiesRequest, context: Any
    ) -> nlu_pb2.ExtractEntitiesResponse:
        """Extrair entidades nomeadas do texto."""
        start_time = time.time()
        await self._ensure_initialized()

        entities = await self.nlu_service.extract_entities(
            text=request.text,
            language=request.language,
        )

        # Filtrar por tipos se especificado
        if request.entity_types:
            allowed_types = {_PROTO_TO_ENTITY_TYPE.get(t, EntityType.UNKNOWN) for t in request.entity_types}
            entities = [e for e in entities if e.type in allowed_types]

        extracted_at = Timestamp()
        extracted_at.GetCurrentTime()

        processing_time_ms = int((time.time() - start_time) * 1000)

        return nlu_pb2.ExtractEntitiesResponse(
            entities=[
                nlu_pb2.Entity(
                    type=_ENTITY_TYPE_TO_PROTO.get(
                        e.type, nlu_pb2.EntityType.ENTITY_UNKNOWN
                    ),
                    value=e.value,
                    confidence=e.confidence,
                    start=e.start or 0,
                    end=e.end or 0,
                    label=e.label or "",
                    attributes=e.attributes,
                )
                for e in entities
            ],
            processing_time_ms=processing_time_ms,
            extracted_at=extracted_at,
        )

    async def CalculateConfidence(
        self, request: nlu_pb2.CalculateConfidenceRequest, context: Any
    ) -> nlu_pb2.CalculateConfidenceResponse:
        """Calcular confiança do resultado NLU."""
        await self._ensure_initialized()

        # Converter proto para modelo interno
        nlu_result = NLUResult(
            processed_text=request.nlu_result.processed_text,
            domain=_PROTO_TO_DOMAIN.get(
                request.nlu_result.domain, UnifiedDomain.TECHNICAL
            ),
            classification=request.nlu_result.classification,
            confidence=request.nlu_result.confidence,
            entities=[
                entity_from_proto(e) for e in request.nlu_result.entities
            ],
            keywords=list(request.nlu_result.keywords),
            original_language=request.nlu_result.original_language,
            requires_manual_validation=request.nlu_result.requires_manual_validation,
            confidence_status=request.nlu_result.confidence_status,
            adaptive_threshold=request.nlu_result.adaptive_threshold
            if request.nlu_result.HasField("adaptive_threshold")
            else None,
        )

        response = await self.nlu_service.calculate_confidence(nlu_result)

        return nlu_pb2.CalculateConfidenceResponse(
            confidence=response.confidence,
            confidence_status=response.confidence_status,
            adaptive_threshold=response.adaptive_threshold,
            requires_manual_validation=response.requires_manual_validation,
            factor_scores=response.factor_scores,
        )

    async def DetectLanguage(
        self, request: nlu_pb2.DetectLanguageRequest, context: Any
    ) -> nlu_pb2.DetectLanguageResponse:
        """Detectar idioma do texto."""
        await self._ensure_initialized()

        language, confidence, candidates = await self.nlu_service.detect_language(
            text=request.text
        )

        return nlu_pb2.DetectLanguageResponse(
            language=language,
            confidence=confidence,
            candidates=[
                nlu_pb2.LanguageCandidate(language=lang, conf=conf)
                for lang, conf in candidates
            ],
        )

    async def HealthCheck(
        self, request: nlu_pb2.HealthCheckRequest, context: Any
    ) -> nlu_pb2.HealthCheckResponse:
        """Health check do serviço NLU."""
        status = nlu_pb2.HealthCheckResponse.ServingStatus.SERVING
        details = {"model_loaded": "false"}
        version = "0.1.0"

        if self.nlu_service and self.nlu_service.is_ready():
            details["model_loaded"] = "true"
            details["models_count"] = str(len(self.nlu_service.nlp_models))
            details["cache_enabled"] = str(self.nlu_service.settings.nlu_cache_enabled)
            status = nlu_pb2.HealthCheckResponse.ServingStatus.SERVING
        else:
            status = nlu_pb2.HealthCheckResponse.NOT_SERVING

        return nlu_pb2.HealthCheckResponse(
            status=status,
            details=details,
            version=version,
        )


async def serve_grpc(port: int = 8021):
    """Iniciar servidor gRPC."""
    server = grpc.aio.server()
    nlu_pb2_grpc.add_NLUServiceServicer_to_server(NLUServicer(), server)

    server.add_insecure_port(f"[::]:{port}")
    logger.info(f"Servidor gRPC iniciado na porta {port}")

    await server.start()
    await server.wait_for_termination()
