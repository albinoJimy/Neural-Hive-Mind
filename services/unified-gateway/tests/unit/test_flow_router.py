"""Testes para o Flow Router."""

import pytest
from unittest.mock import AsyncMock, Mock

import httpx

from src.config.settings import Settings
from src.models.classification import ClassificationDecision, FlowType
from src.services.flow_router import FlowGatewayConfig, FlowRouter, get_flow_router


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings para testes."""

    class TestSettings(Settings):
        FLOW_AF_GATEWAY: str = "http://af-gateway:8000"
        FLOW_G_GATEWAY: str = "http://g-gateway:8010"
        FLOW_H_GATEWAY: str = "http://h-gateway:8018"
        FLOW_ROUTER_TIMEOUT: int = 30

    def mock_get_settings():
        return TestSettings()

    monkeypatch.setattr("src.services.flow_router.get_settings", mock_get_settings)
    return TestSettings()


@pytest.fixture
def flow_router(mock_settings):
    """Fixture para Flow Router."""
    router = FlowRouter()
    yield router
    # Cleanup - criar event loop para async close
    import asyncio

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(router.close())
    finally:
        loop.close()


@pytest.mark.asyncio
class TestFlowRouter:
    """Testes do Flow Router."""

    async def test_gateway_configs_loaded(self, flow_router):
        """Testar que configurações dos gateways foram carregadas."""
        assert FlowType.AF in flow_router.GATEWAY_CONFIGS
        assert FlowType.G in flow_router.GATEWAY_CONFIGS
        assert FlowType.H in flow_router.GATEWAY_CONFIGS

        af_config = flow_router.GATEWAY_CONFIGS[FlowType.AF]
        assert af_config.name == "gateway-intencoes"
        assert "af-gateway" in af_config.http_url

    async def test_route_flow_af(self, flow_router):
        """Testar roteamento para Flow A-F."""
        decision = ClassificationDecision(
            flow_type=FlowType.AF,
            confidence=0.8,
            reasoning="Teste",
        )

        # Mock HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "ok"}'

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response
        mock_client.is_closed = False

        flow_router._http_client = mock_client

        # Executar roteamento
        status, headers, body = await flow_router.route(
            decision=decision,
            request_method="POST",
            request_path="/api/v1/process",
            request_headers={"authorization": "Bearer token"},
            request_body=b'{"text": "teste"}',
        )

        # Verificar resultado
        assert status == 200
        assert headers["content-type"] == "application/json"
        assert body == b'{"result": "ok"}'

    async def test_route_flow_g(self, flow_router):
        """Testar roteamento para Flow G."""
        decision = ClassificationDecision(
            flow_type=FlowType.G,
            confidence=0.85,
            reasoning="Teste G",
        )

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.headers = {}
        mock_response.content = b'{"code": "generated"}'

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response
        mock_client.is_closed = False

        flow_router._http_client = mock_client

        status, headers, body = await flow_router.route(
            decision=decision,
            request_method="POST",
            request_path="/generate",
            request_headers={},
            request_body=b'{"prompt": "create app"}',
        )

        assert status == 201
        assert body == b'{"code": "generated"}'

    async def test_route_flow_h(self, flow_router):
        """Testar roteamento para Flow H."""
        decision = ClassificationDecision(
            flow_type=FlowType.H,
            confidence=0.9,
            reasoning="Teste H",
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.content = b'{"migration": "done"}'

        mock_client = AsyncMock()
        mock_client.request.return_value = mock_response
        mock_client.is_closed = False

        flow_router._http_client = mock_client

        status, headers, body = await flow_router.route(
            decision=decision,
            request_method="POST",
            request_path="/migrate",
            request_headers={},
            request_body=b'{"source": "legacy"}',
        )

        assert status == 200
        assert body == b'{"migration": "done"}'

    async def test_route_unsupported_flow_type(self, flow_router):
        """Testar erro para flow type não suportado."""
        # Criar decisão com flow type inválido
        decision = ClassificationDecision(
            flow_type=FlowType.AF,  # Vamos modificar internamente
            confidence=0.5,
            reasoning="Teste",
        )

        # Remover AF do config para forçar erro
        original_configs = flow_router.GATEWAY_CONFIGS
        flow_router.GATEWAY_CONFIGS = {}

        with pytest.raises(ValueError, match="Unsupported flow type"):
            await flow_router.route(
                decision=decision,
                request_method="GET",
                request_path="/test",
                request_headers={},
            )

        # Restaurar configs
        flow_router.GATEWAY_CONFIGS = original_configs


@pytest.mark.asyncio
class TestFlowRouterWithFallback:
    """Testes do Flow Router com fallback."""

    async def test_fallback_to_alternative_on_error(self, flow_router):
        """Testar fallback para flow alternativo."""
        decision = ClassificationDecision(
            flow_type=FlowType.AF,
            confidence=0.8,
            reasoning="Teste",
            alternative=FlowType.G,
        )

        # Mock HTTP client que falha no primeiro request
        mock_client = AsyncMock()
        mock_client.is_closed = False

        # Primeira chamada falha
        call_count = [0]

        async def mock_request(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx.TimeoutException("Timeout")
            else:
                # Segunda chamada (alternativa) sucesso
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.headers = {}
                mock_response.content = b'{"fallback": "success"}'
                return mock_response

        mock_client.request = mock_request
        flow_router._http_client = mock_client

        # Executar com fallback
        status, headers, body = await flow_router.route_with_fallback(
            decision=decision,
            request_method="POST",
            request_path="/test",
            request_headers={},
        )

        # Verificar que fallback foi usado
        assert call_count[0] == 2  # Primário + alternativo
        assert status == 200
        assert body == b'{"fallback": "success"}'

    async def test_fallback_exhausted_raises_error(self, flow_router):
        """Testar erro quando ambos primário e alternativo falham."""
        decision = ClassificationDecision(
            flow_type=FlowType.AF,
            confidence=0.8,
            reasoning="Teste",
            alternative=FlowType.G,
        )

        # Mock HTTP client que sempre falha
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request.side_effect = httpx.TimeoutException("Timeout")
        flow_router._http_client = mock_client

        # Executar com fallback - deve levantar exceção
        with pytest.raises(httpx.TimeoutException):
            await flow_router.route_with_fallback(
                decision=decision,
                request_method="POST",
                request_path="/test",
                request_headers={},
            )

    async def test_no_alternative_raises_on_error(self, flow_router):
        """Testar erro quando não há alternativa e primário falha."""
        decision = ClassificationDecision(
            flow_type=FlowType.AF,
            confidence=0.8,
            reasoning="Teste",
            alternative=None,  # Sem alternativa
        )

        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.request.side_effect = httpx.TimeoutException("Timeout")
        flow_router._http_client = mock_client

        with pytest.raises(httpx.TimeoutException):
            await flow_router.route_with_fallback(
                decision=decision,
                request_method="POST",
                request_path="/test",
                request_headers={},
            )


class TestFlowRouterHelperMethods:
    """Testes de métodos auxiliares do Flow Router."""

    def test_filter_headers(self, flow_router):
        """Testar filtro de headers."""
        headers = {
            "host": "localhost:7999",
            "content-type": "application/json",
            "content-length": "100",
            "authorization": "Bearer token",
            "user-agent": "test",
        }

        filtered = flow_router._filter_headers(headers)

        # Headers filtrados não devem estar presentes
        assert "host" not in filtered
        assert "content-length" not in filtered

        # Outros headers devem estar presentes
        assert "content-type" in filtered
        assert "authorization" in filtered
        assert "user-agent" in filtered

    def test_build_target_url(self, flow_router):
        """Testar construção de URL alvo."""
        # Sem query
        url = flow_router._build_target_url("http://gateway:8000", "/api/test")
        assert url == "http://gateway:8000/api/test"

        # Com query
        url = flow_router._build_target_url("http://gateway:8000/", "/api/test", "param=value")
        assert url == "http://gateway:8000/api/test?param=value"

        # Base com trailing slash
        url = flow_router._build_target_url("http://gateway:8000/", "/api/test")
        assert url == "http://gateway:8000/api/test"


@pytest.mark.asyncio
class TestFlowRouterHealthCheck:
    """Testes de health check do Flow Router."""

    async def test_health_check_all(self, flow_router):
        """Testar health check de todos os gateways."""
        # Mock HTTP client
        mock_response = Mock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.is_closed = False
        flow_router._http_client = mock_client

        # Executar health check
        results = await flow_router.health_check_all()

        # Verificar resultados
        assert len(results) == 3  # AF, G, H
        assert FlowType.AF in results
        assert FlowType.G in results
        assert FlowType.H in results

        # Todos devem retornar status healthy
        for flow_type, result in results.items():
            assert result["status"] == "healthy"
            assert result["status_code"] == 200
            assert "url" in result

    async def test_health_check_with_failure(self, flow_router):
        """Testar health check com gateway falhando."""
        mock_client = AsyncMock()
        mock_client.is_closed = False

        # AF retorna erro
        async def mock_get(url, **kwargs):
            if "af-gateway" in url:
                raise httpx.ConnectError("Connection refused")
            else:
                mock_response = Mock()
                mock_response.status_code = 200
                return mock_response

        mock_client.get = mock_get
        flow_router._http_client = mock_client

        results = await flow_router.health_check_all()

        # AF deve ter erro
        assert results[FlowType.AF]["status"] == "error"
        assert "error" in results[FlowType.AF]

        # G e H devem estar healthy
        assert results[FlowType.G]["status"] == "healthy"
        assert results[FlowType.H]["status"] == "healthy"


class TestFlowRouterSingleton:
    """Testes do singleton do Flow Router."""

    def test_get_flow_router_returns_same_instance(self, flow_router):
        """Testar que singleton retorna mesma instância."""
        router1 = get_flow_router()
        router2 = get_flow_router()

        assert router1 is router2


class TestFlowGatewayConfig:
    """Testes do modelo de configuração."""

    def test_flow_gateway_config_creation(self):
        """Testar criação de FlowGatewayConfig."""
        config = FlowGatewayConfig(
            name="test-gateway",
            http_url="http://test:8000",
            grpc_address="test:8001",
            timeout=30.0,
        )

        assert config.name == "test-gateway"
        assert config.http_url == "http://test:8000"
        assert config.grpc_address == "test:8001"
        assert config.timeout == 30.0
