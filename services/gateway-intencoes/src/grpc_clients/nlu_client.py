"""Cliente gRPC para NLU Service.

Implementa T11: gateway-intencoes passa a usar NLU Service via gRPC
em vez de implementação local (1.303 LOC removidos).
"""

import asyncio
import logging
from typing import Any

import grpc
from google.protobuf import empty_pb2

from config.settings import get_settings

# Importar stubs gerados
from src.proto import nlu_pb2, nlu_pb2_grpc

logger = logging.getLogger(__name__)
settings = get_settings()


class NLUServiceClient:
    """
    Cliente gRPC para o NLU Service.

    Implementa chamada ao NLU Service (:8020) via gRPC.
    """

    def __init__(self, target: str | None = None):
        """
        Inicializa cliente gRPC.

        Args:
            target: Endereço do NLU Service (padrão: localhost:8020)
        """
        self._target = target or settings.NLU_SERVICE_URL or "localhost:8020"
        self._channel: grpc.aio.Channel | None = None
        self._stub: nlu_pb2_grpc.NLUServiceStub | None = None
        self._connected = False

        logger.info(f"NLUServiceClient initialized with target: {self._target}")

    async def connect(self):
        """Conecta ao NLU Service."""
        if self._connected:
            return

        try:
            self._channel = grpc.aio.insecure_channel(self._target)
            self._stub = nlu_pb2_grpc.NLUServiceStub(self._channel)

            # Testar conexão
            await asyncio.wait_for(self._stub.HealthCheck(empty_pb2.Empty()), timeout=5.0)

            self._connected = True
            logger.info(f"NLUServiceClient connected to {self._target}")

        except asyncio.TimeoutError:
            logger.error(f"NLUServiceClient connection timeout to {self._target}")
            raise
        except Exception as e:
            logger.error(f"NLUServiceClient connection failed: {e}")
            raise

    async def close(self):
        """Fecha conexão com o NLU Service."""
        if self._channel:
            await self._channel.close()
            self._connected = False
            logger.info("NLUServiceClient connection closed")

    async def parse(
        self,
        text: str,
        language: str = "pt",
        context: dict[str, Any] | None = None,
        enable_cache: bool = True,
    ) -> nlu_pb2.NLUResult:
        """
        Processa texto via NLU Service.

        Args:
            text: Texto para processar
            language: Idioma do texto (pt, en, es)
            context: Contexto adicional
            enable_cache: Habilitar cache

        Returns:
            NLUResult do NLU Service
        """
        if not self._connected:
            await self.connect()

        # Construir request
        request = nlu_pb2.ParseRequest(
            text=text,
            language=language,
            enable_cache=enable_cache,
        )

        # Adicionar contexto se fornecido
        if context:
            for key, value in context.items():
                request.context[key] = str(value)

        try:
            # Chamar NLU Service
            response = await asyncio.wait_for(
                self._stub.Parse(request),
                timeout=settings.NLU_SERVICE_TIMEOUT or 10.0,
            )

            logger.debug(
                "NLU service call successful",
                domain=response.domain,
                confidence=response.confidence,
                keywords_count=len(response.keywords),
            )

            return response

        except asyncio.TimeoutError:
            logger.error("NLU service call timeout")
            raise
        except grpc.aio.AioRpcError as e:
            logger.error(f"NLU service gRPC error: {e.code()}: {e.details()}")
            raise

    async def health_check(self) -> bool:
        """Verifica saúde do NLU Service."""
        try:
            await self._stub.HealthCheck(empty_pb2.Empty())
            return True
        except Exception as e:
            logger.warning(f"NLU service health check failed: {e}")
            return False


# Singleton global
_nlu_client: NLUServiceClient | None = None


async def get_nlu_client() -> NLUServiceClient:
    """Obtém ou cria o singleton do cliente NLU."""
    global _nlu_client
    if _nlu_client is None:
        _nlu_client = NLUServiceClient()
        await _nlu_client.connect()
    return _nlu_client
