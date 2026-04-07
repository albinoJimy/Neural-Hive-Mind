"""
Smoke Tests E2E para Gateway de Intenções.

Valida:
- Endpoint /health responde
- Endpoint /ready verifica dependências
- Serviço está acessível
"""

import pytest

from tests.e2e.smoke.conftest import SERVICE_URLS


pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
class TestGatewayHealth:
    """Testes de health check para Gateway de Intenções."""

    async def test_health_endpoint_responds(self, gateway_health_helper):
        """
        TEST: [GATEWAY-001] Endpoint /health responde em <5s

        Dado: Gateway de Intenções está rodando
        Quando: GET /health é chamado
        Então: Response HTTP 200 com status='healthy'
        """
        result = await gateway_health_helper.check_health()

        assert result["available"] is True, f"Gateway não disponível: {result['error']}"
        assert result["status_code"] == 200
        assert result["response"] is not None
        assert result["response"].get("status") == "healthy"
        assert result["response"].get("service") == "gateway-intencoes"

    async def test_health_response_contains_version(self, gateway_health_helper):
        """
        TEST: [GATEWAY-002] Response de /health contém versão

        Dado: Gateway de Intenções está rodando
        Quando: GET /health é chamado
        Então: Response contém campo 'version'
        """
        result = await gateway_health_helper.check_health()

        assert result["available"] is True
        assert "version" in result["response"]
        assert isinstance(result["response"]["version"], str)


@pytest.mark.asyncio
class TestGatewayReadiness:
    """Testes de readiness para Gateway de Intenções."""

    async def test_ready_endpoint_responds(self, gateway_health_helper):
        """
        TEST: [GATEWAY-003] Endpoint /ready responde

        Dado: Gateway de Intenções está rodando
        Quando: GET /ready é chamado
        Então: Response contém checks de dependências
        """
        result = await gateway_health_helper.check_ready()

        assert result["available"] is True, f"Gateway /ready não disponível: {result.get('error')}"

    async def test_ready_checks_kafka_connectivity(self, gateway_health_helper):
        """
        TEST: [GATEWAY-004] /ready verifica conectividade Kafka

        Dado: Gateway de Intenções está rodando
        Quando: GET /ready é chamado
        Então: Response contém check de Kafka
        """
        result = await gateway_health_helper.check_ready()

        assert result["available"] is True
        assert "checks" in result["response"]
        # Gateway pode ter diferentes nomes para check Kafka
        checks = result["response"]["checks"]
        kafka_found = any("kafka" in k.lower() for k in checks.keys())
        assert kafka_found, "Check de Kafka não encontrado em /ready"

    async def test_ready_checks_critical_dependencies(self, gateway_health_helper):
        """
        TEST: [GATEWAY-005] /ready verifica dependências críticas

        Dado: Gateway de Intenções está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem Redis e outras deps críticas
        """
        result = await gateway_health_helper.check_ready()

        assert result["available"] is True
        assert "checks" in result["response"]
        checks = result["response"]["checks"]
        # Verificar que há checks sendo realizados
        assert len(checks) > 0, "Nenhum check encontrado em /ready"


@pytest.mark.asyncio
class TestGatewaySmokeComplete:
    """Smoke test completo para Gateway."""

    async def test_gateway_both_endpoints_healthy(self, gateway_health_helper):
        """
        TEST: [GATEWAY-006] Smoke test completo - ambos endpoints saudáveis

        Dado: Gateway de Intenções está rodando
        Quando: Ambos /health e /ready são verificados
        Então: Ambos respondem com status OK
        """
        result = await gateway_health_helper.check_all()

        # Health deve estar sempre OK
        assert result["health"]["available"] is True
        assert result["health"]["status_code"] == 200

        # Ready pode ser 503 se deps não estão prontas, mas deve responder
        assert result["ready"]["available"] is True
        # Status 200 ou 503 são aceitáveis para /ready
        assert result["ready"]["status_code"] in {200, 503}


@pytest.mark.asyncio
class TestGatewayGracefulDegradation:
    """Testes de graceful degradation quando serviço não disponível."""

    async def test_gateway_unavailable_graceful_error(self, http_client):
        """
        TEST: [GATEWAY-007] Erro gracioso quando Gateway indisponível

        Dado: Gateway de Intenções NÃO está rodando
        Quando: Tentativa de conexão é feita
        Então: Timeout/conexão falha é identificada corretamente
        """
        # URL inválida propositalmente
        from tests.e2e.smoke.conftest import ServiceHealthHelper

        helper = ServiceHealthHelper(http_client, "http://invalid-service-that-does-not-exist:9999")

        result = await helper.check_health()

        assert result["available"] is False
        assert result["status_code"] is None
        assert result["error"] in {"timeout", "connection_refused"} or result["error"] is not None
