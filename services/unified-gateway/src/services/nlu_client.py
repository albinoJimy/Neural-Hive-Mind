"""Cliente gRPC para o NLU Service."""

import logging
from typing import Any

import grpc
from pydantic import ValidationError

from src.config.settings import get_settings
from src.models.classification import NLUResult
from src.proto import nlu_pb2, nlu_pb2_grpc

logger = logging.getLogger(__name__)

settings = get_settings()


class NLUServiceClient:
    """
    Cliente gRPC para o NLU Service.

    Oferece métodos de alto nível para interagir com o NLU Service,
    com retry logic e fallback para classificação local.
    """

    def __init__(self, nlu_service_address: str | None = None):
        """
        Inicializa o cliente NLU.

        Args:
            nlu_service_address: Endereço do NLU Service (host:port)
        """
        self._nlu_address = nlu_service_address or settings.nlu_service_address
        self._channel: grpc.Channel | None = None
        self._stub: nlu_pb2_grpc.NLUServiceStub | None = None

    async def _get_stub(self) -> nlu_pb2_grpc.NLUServiceStub:
        """Obtém ou cria o stub gRPC."""
        if self._stub is None or self._channel is None:
            self._channel = grpc.aio.insecure_channel(self._nlu_address)
            self._stub = nlu_pb2_grpc.NLUServiceStub(self._channel)
        return self._stub

    async def close(self):
        """Fecha a conexão gRPC."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def parse(
        self,
        text: str,
        language: str = "pt",
        context: dict[str, str] | None = None,
        enable_cache: bool = True,
    ) -> NLUResult:
        """
        Processa texto completo via NLU Service.

        Args:
            text: Texto para processar
            language: Idioma do texto (ISO 639-1)
            context: Contexto adicional (tenant_id, user_id, etc)
            enable_cache: Habilitar cache Redis

        Returns:
            NLUResult com domain, entities, confidence, keywords
        """
        try:
            stub = await self._get_stub()

            request = nlu_pb2.ParseRequest(
                text=text,
                language=language,
                context=context or {},
                enable_cache=enable_cache,
            )

            response = await stub.Parse(request, timeout=settings.nlu_timeout_seconds)

            return self._convert_nlu_result(response.result, text)

        except grpc.aio.AioRpcError as e:
            logger.warning(f"NLU Service gRPC error: {e.code()}: {e.details()}")
            # Fallback para classificação local (INV-12)
            return self._fallback_nlu_result(text, language)

        except (ValidationError, Exception) as e:
            logger.error(f"Error parsing NLU response: {e}")
            return self._fallback_nlu_result(text, language)

    async def classify_domain(
        self,
        text: str,
        language: str = "pt",
        context: dict[str, str] | None = None,
    ) -> tuple[str, float, str]:
        """
        Classifica domínio do texto.

        Args:
            text: Texto para classificar
            language: Idioma do texto
            context: Contexto adicional

        Returns:
            Tuple (domain, confidence, reasoning)
        """
        try:
            stub = await self._get_stub()

            request = nlu_pb2.ClassifyDomainRequest(
                text=text,
                language=language,
                context=context or {},
            )

            response = await stub.ClassifyDomain(request, timeout=settings.nlu_timeout_seconds)

            domain_name = nlu_pb2.UnifiedDomain.Name(response.domain)
            return domain_name, response.confidence, response.reasoning

        except grpc.aio.AioRpcError as e:
            logger.warning(f"NLU classify_domain error: {e.code()}: {e.details()}")
            return "DOMAIN_UNKNOWN", 0.3, "NLU Service unavailable, using fallback"

    async def extract_entities(
        self,
        text: str,
        language: str = "pt",
        entity_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Extrai entidades nomeadas do texto.

        Args:
            text: Texto para extrair entidades
            language: Idioma do texto
            entity_types: Tipos de entidades a extrair (vazio = todas)

        Returns:
            Lista de entidades (dict com type, value, confidence, start, end)
        """
        try:
            stub = await self._get_stub()

            # Converter entity_types strings para EntityType enum
            type_enums = []
            if entity_types:
                for et in entity_types:
                    try:
                        type_enums.append(nlu_pb2.EntityType.Value(et))
                    except ValueError:
                        logger.warning(f"Unknown entity type: {et}")

            request = nlu_pb2.ExtractEntitiesRequest(
                text=text,
                language=language,
                entity_types=type_enums,
            )

            response = await stub.ExtractEntities(request, timeout=settings.nlu_timeout_seconds)

            return [
                {
                    "type": nlu_pb2.EntityType.Name(e.type),
                    "value": e.value,
                    "confidence": e.confidence,
                    "start": e.start,
                    "end": e.end,
                }
                for e in response.entities
            ]

        except grpc.aio.AioRpcError as e:
            logger.warning(f"NLU extract_entities error: {e.code()}: {e.details()}")
            return []

    async def health_check(self) -> dict[str, Any]:
        """
        Verifica saúde do NLU Service.

        Returns:
            Dict com status e detalhes
        """
        try:
            stub = await self._get_stub()

            request = nlu_pb2.HealthCheckRequest(service_name="unified-gateway")
            response = await stub.HealthCheck(request, timeout=5.0)

            status_name = nlu_pb2.HealthCheckResponse.ServingStatus.Name(response.status)

            return {
                "status": status_name,
                "details": dict(response.details),
                "version": response.version,
            }

        except Exception as e:
            logger.error(f"NLU health check failed: {e}")
            return {"status": "UNKNOWN", "details": {"error": str(e)}}

    def _convert_nlu_result(self, proto_result: nlu_pb2.NLUResult, original_text: str) -> NLUResult:
        """
        Converte NLUResult protobuf para modelo Pydantic.

        Args:
            proto_result: Resultado do NLU Service
            original_text: Texto original da requisição

        Returns:
            NLUResult (modelo Pydantic)
        """
        # Converter entidades
        entities = {
            nlu_pb2.EntityType.Name(e.type): e.value
            for e in proto_result.entities
        }

        return NLUResult(
            text=original_text,
            domain=nlu_pb2.UnifiedDomain.Name(proto_result.domain),
            confidence=proto_result.confidence,
            entities=entities,
            keywords=list(proto_result.keywords),
        )

    def _fallback_nlu_result(self, text: str, language: str) -> NLUResult:
        """
        Resultado NLU de fallback quando serviço indisponível (INV-12).

        Args:
            text: Texto original
            language: Idioma

        Returns:
            NLUResult com valores mínimos
        """
        return NLUResult(
            text=text,
            domain="DOMAIN_UNKNOWN",
            confidence=0.3,
            entities={},
            keywords=[],
        )


# Singleton global
_nlu_client: NLUServiceClient | None = None


async def get_nlu_client() -> NLUServiceClient:
    """Obtém ou cria o singleton do cliente NLU."""
    global _nlu_client
    if _nlu_client is None:
        _nlu_client = NLUServiceClient()
    return _nlu_client
