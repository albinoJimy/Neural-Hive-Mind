"""Flow Router para proxy de requests para gateways específicos."""

import logging
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.models.classification import ClassificationDecision, FlowType

logger = logging.getLogger(__name__)


class FlowGatewayConfig(BaseModel):
    """Configuração de um gateway de fluxo."""

    name: str
    http_url: str
    grpc_address: str | None = None
    timeout: float = 30.0
    health_check_path: str = "/health"
    health_check_interval: int = 60  # seconds

    model_config = {"extra": "ignore"}


class RouteTarget(BaseModel):
    """Alvo de roteamento."""

    flow_type: FlowType
    gateway_config: FlowGatewayConfig


class RoutingResult(BaseModel):
    """Resultado do roteamento."""

    flow_type: FlowType
    target_url: str
    method: str
    status: str = "pending"
    error: str | None = None
    processing_time_ms: int = 0


class FlowRouter:
    """
    Roteador de fluxo para gateways específicos.

    Responsável por:
    1. Receber decisão de classificação (FlowType)
    2. Selecionar gateway apropriado
    3. Fazer proxy da requisição
    4. Retornar resposta do gateway downstream

    Mapeamento FlowType → Gateway:
    - A-F (Cognitive Pipeline) → gateway-intencoes:8000
    - G (Code Generation) → requirements-engineering:8010
    - H (Migration) → doc-ingestion:8018
    """

    # Configurações dos gateways (carregadas do settings)
    GATEWAY_CONFIGS: dict[FlowType, FlowGatewayConfig] = {}

    def __init__(self):
        """Inicializa o Flow Router."""
        self._http_client: httpx.AsyncClient | None = None
        self._health_status: dict[FlowType, bool] = {}
        self._load_gateway_configs()

    def _load_gateway_configs(self):
        """Carrega configurações dos gateways do settings."""
        settings = get_settings()
        self.GATEWAY_CONFIGS = {
            FlowType.AF: FlowGatewayConfig(
                name="gateway-intencoes",
                http_url=settings.FLOW_AF_GATEWAY,
                timeout=settings.FLOW_ROUTER_TIMEOUT,
            ),
            FlowType.G: FlowGatewayConfig(
                name="requirements-engineering",
                http_url=settings.FLOW_G_GATEWAY,
                timeout=settings.FLOW_ROUTER_TIMEOUT,
            ),
            FlowType.H: FlowGatewayConfig(
                name="doc-ingestion",
                http_url=settings.FLOW_H_GATEWAY,
                timeout=settings.FLOW_ROUTER_TIMEOUT,
            ),
        }

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Obtém ou cria cliente HTTP."""
        if self._http_client is None or self._http_client.is_closed:
            settings = get_settings()
            timeout = httpx.Timeout(settings.FLOW_ROUTER_TIMEOUT, connect=10.0)
            self._http_client = httpx.AsyncClient(timeout=timeout)
        return self._http_client

    async def close(self):
        """Fecha recursos."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def route(
        self,
        decision: ClassificationDecision,
        request_method: str,
        request_path: str,
        request_headers: dict[str, str],
        request_body: bytes | None = None,
        request_query: str | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """
        Roteia request para o gateway apropriado.

        Args:
            decision: Decisão de classificação com FlowType
            request_method: Método HTTP (GET, POST, etc)
            request_path: Caminho da requisição
            request_headers: Cabeçalhos HTTP
            request_body: Corpo da requisição
            request_query: Query string

        Returns:
            Tuple (status_code, headers, body)

        Raises:
            ValueError: Se FlowType não suportado
            RuntimeError: Se todos os gateways estiverem down
        """
        import time

        start_time = time.time()

        # Obter configuração do gateway para o flow type
        gateway_config = self.GATEWAY_CONFIGS.get(decision.flow_type)
        if gateway_config is None:
            raise ValueError(f"Unsupported flow type: {decision.flow_type}")

        # Verificar saúde do gateway (graceful degradation)
        if not await self._is_gateway_healthy(decision.flow_type):
            logger.warning(f"Gateway {decision.flow_type} unhealthy, attempting request anyway")

        # Construir URL alvo
        target_url = self._build_target_url(gateway_config.http_url, request_path, request_query)

        try:
            # Fazer proxy da requisição
            response = await self._proxy_request(
                target_url=target_url,
                method=request_method,
                headers=request_headers,
                body=request_body,
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            return response["status_code"], response["headers"], response["body"]

        except httpx.TimeoutException:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Timeout routing to {target_url}")
            raise

        except httpx.HTTPError as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"HTTP error routing to {target_url}: {e}")
            raise

    async def route_with_fallback(
        self,
        decision: ClassificationDecision,
        request_method: str,
        request_path: str,
        request_headers: dict[str, str],
        request_body: bytes | None = None,
        request_query: str | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """
        Roteia com fallback para flow alternativo se primário falhar.

        Args:
            decision: Decisão de classificação (pode conter alternativa)
            ... (mesmos parâmetros que route())

        Returns:
            Tuple (status_code, headers, body)

        Implementa graceful degradation: se gateway primário falhar,
        tenta gateway alternativo (se disponível).
        """
        try:
            return await self.route(
                decision=decision,
                request_method=request_method,
                request_path=request_path,
                request_headers=request_headers,
                request_body=request_body,
                request_query=request_query,
            )

        except (httpx.HTTPError, ValueError) as e:
            # Tentar flow alternativo se disponível
            if decision.alternative and decision.alternative != decision.flow_type:
                logger.info(f"Primary flow {decision.flow_type} failed, trying alternative {decision.alternative}")

                alternative_decision = ClassificationDecision(
                    flow_type=decision.alternative,
                    confidence=decision.confidence * 0.8,  # Reduz confiança do alternativa
                    reasoning=f"Fallback from {decision.flow_type}: {str(e)}",
                    alternative=None,
                )

                try:
                    return await self.route(
                        decision=alternative_decision,
                        request_method=request_method,
                        request_path=request_path,
                        request_headers=request_headers,
                        request_body=request_body,
                        request_query=request_query,
                    )

                except Exception as fallback_error:
                    logger.error(f"Alternative flow {decision.alternative} also failed: {fallback_error}")
                    raise

            raise

    def _build_target_url(
        self, base_url: str, path: str, query: str | None = None
    ) -> str:
        """Constrói URL alvo."""
        # Remover trailing slash do base_url
        base = base_url.rstrip("/")

        # Adicionar path
        target = f"{base}{path}"

        # Adicionar query se presente
        if query:
            target = f"{target}?{query}"

        return target

    async def _proxy_request(
        self,
        target_url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> dict[str, Any]:
        """Faz proxy da requisição HTTP."""

        # Filtrar headers que não devem ser passados
        proxy_headers = self._filter_headers(headers)

        client = await self._get_http_client()

        response = await client.request(
            method=method,
            url=target_url,
            headers=proxy_headers,
            content=body,
        )

        # Construir resposta
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.content,
        }

    def _filter_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Filtra headers para proxy."""
        # Headers que não devem ser passados
        filtered_out = {
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "keep-alive",
        }

        return {
            k: v
            for k, v in headers.items()
            if k.lower() not in filtered_out
        }

    async def _is_gateway_healthy(self, flow_type: FlowType) -> bool:
        """Verifica saúde do gateway (cache simples)."""
        # Para MVP, assume sempre saudável
        # Em produção, implementar health check real com cache
        return True

    async def health_check_all(self) -> dict[FlowType, dict[str, Any]]:
        """Verifica saúde de todos os gateways."""
        results = {}

        for flow_type, config in self.GATEWAY_CONFIGS.items():
            try:
                health_url = f"{config.http_url.rstrip('/')}{config.health_check_path}"
                client = await self._get_http_client()

                response = await client.get(health_url, timeout=5.0)

                results[flow_type] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "status_code": response.status_code,
                    "url": health_url,
                }

                self._health_status[flow_type] = response.status_code == 200

            except Exception as e:
                results[flow_type] = {
                    "status": "error",
                    "error": str(e),
                    "url": f"{config.http_url}{config.health_check_path}",
                }

                self._health_status[flow_type] = False

        return results


# Singleton global
_flow_router: FlowRouter | None = None


def get_flow_router() -> FlowRouter:
    """Obtém ou cria o singleton do Flow Router."""
    global _flow_router
    if _flow_router is None:
        _flow_router = FlowRouter()
    return _flow_router
