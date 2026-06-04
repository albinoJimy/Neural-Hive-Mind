"""Cliente gRPC para PII Service.

Implementa T11: gateway-intencoes passa a usar PII Service via gRPC
em vez de implementação local.
"""

import asyncio
import logging
from typing import Any

import grpc

from config.settings import get_settings

# Importar stubs gerados
from src.proto import pii_pb2, pii_pb2_grpc

logger = logging.getLogger(__name__)
settings = get_settings()


class PIIServiceClient:
    """
    Cliente gRPC para o PII Service.

    Implementa chamada ao PII Service (:8021) via gRPC.
    """

    def __init__(self, target: str | None = None):
        """
        Inicializa cliente gRPC.

        Args:
            target: Endereço do PII Service (padrão: localhost:8021)
        """
        self._target = target or settings.pii_service_url or "localhost:9021"
        self._channel: grpc.aio.Channel | None = None
        self._stub: pii_pb2_grpc.PIIServiceStub | None = None
        self._connected = False

        logger.info(f"PIIServiceClient initialized with target: {self._target}")

    async def connect(self):
        """Conecta ao PII Service."""
        if self._connected:
            return

        try:
            self._channel = grpc.aio.insecure_channel(self._target)
            self._stub = pii_pb2_grpc.PIIServiceStub(self._channel)

            # Testar conexão
            await asyncio.wait_for(
                self._stub.HealthCheck(pii_pb2.HealthCheckRequest()), timeout=5.0
            )

            self._connected = True
            logger.info(f"PIIServiceClient connected to {self._target}")

        except asyncio.TimeoutError:
            logger.error(f"PIIServiceClient connection timeout to {self._target}")
            raise
        except Exception as e:
            logger.error(f"PIIServiceClient connection failed: {e}")
            raise

    async def close(self):
        """Fecha conexão com o PII Service."""
        if self._channel:
            await self._channel.close()
            self._connected = False
            logger.info("PIIServiceClient connection closed")

    async def detect(
        self,
        text: str,
        language: str = "pt",
    ) -> list[dict[str, Any]]:
        """
        Detecta PII no texto.

        Args:
            text: Texto para analisar
            language: Idioma do texto

        Returns:
            Lista de PII encontrados
        """
        if not self._connected:
            await self.connect()

        request = pii_pb2.DetectRequest(
            text=text,
            language=language,
        )

        try:
            response = await asyncio.wait_for(
                self._stub.Detect(request),
                timeout=settings.PII_SERVICE_TIMEOUT or 10.0,
            )

            # Converter para lista de dicts
            pii_list = []
            for pii in response.pii_found:
                pii_list.append(
                    {
                        "type": pii.type,
                        "value": pii.value,
                        "start": pii.start,
                        "end": pii.end,
                        "confidence": pii.confidence,
                    }
                )

            logger.debug(f"PII detection found {len(pii_list)} items")

            return pii_list

        except asyncio.TimeoutError:
            logger.error("PII service detect timeout")
            raise
        except grpc.aio.AioRpcError as e:
            logger.error(f"PII service gRPC error: {e.code()}: {e.details()}")
            raise

    async def mask(
        self,
        text: str,
        strategy: str = "MASK_FULL",
        language: str = "pt",
    ) -> str:
        """
        Mascarea PII no texto.

        Args:
            text: Texto para mascarar
            strategy: Estratégia de mascaramento
            language: Idioma do texto

        Returns:
            Texto mascarado
        """
        if not self._connected:
            await self.connect()

        request = pii_pb2.MaskRequest(
            text=text,
            strategy=strategy,
            language=language,
        )

        try:
            response = await asyncio.wait_for(
                self._stub.Mask(request),
                timeout=settings.PII_SERVICE_TIMEOUT or 10.0,
            )

            logger.debug(f"PII masking applied with strategy: {strategy}")

            return response.masked_text

        except asyncio.TimeoutError:
            logger.error("PII service mask timeout")
            raise
        except grpc.aio.AioRpcError as e:
            logger.error(f"PII service gRPC error: {e.code()}: {e.details()}")
            raise

    async def health_check(self) -> bool:
        """Verifica saúde do PII Service."""
        try:
            await self._stub.HealthCheck(pii_pb2.HealthCheckRequest())
            return True
        except Exception as e:
            logger.warning(f"PII service health check failed: {e}")
            return False


# Singleton global
_pii_client: PIIServiceClient | None = None


async def get_pii_client() -> PIIServiceClient:
    """Obtém ou cria o singleton do cliente PII."""
    global _pii_client
    if _pii_client is None:
        _pii_client = PIIServiceClient()
        await _pii_client.connect()
    return _pii_client
