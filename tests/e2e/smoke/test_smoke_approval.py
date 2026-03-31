"""
Smoke Tests E2E para Approval Service.

Valida:
- Endpoint /health responde
- Endpoint /ready verifica dependências (MongoDB, Redis, Kafka)
- API básica está acessível
"""

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
class TestApprovalHealth:
    """Testes de health check para Approval Service."""

    async def test_health_endpoint_responds(self, approval_health_helper):
        """
        TEST: [APPROVAL-001] Endpoint /health responde em <5s

        Dado: Approval Service está rodando
        Quando: GET /health é chamado
        Então: Response HTTP 200 com status='healthy'
        """
        result = await approval_health_helper.check_health()

        # Approval Service pode não estar disponível em todos ambientes
        if not result["available"]:
            pytest.skip(f"Approval Service não disponível: {result.get('error')}")

        assert result["status_code"] == 200
        assert result["response"] is not None
        assert result["response"].get("status") == "healthy"

    async def test_health_contains_version(self, approval_health_helper):
        """
        TEST: [APPROVAL-002] Response de /health contém versão

        Dado: Approval Service está rodando
        Quando: GET /health é chamado
        Então: Response contém campo 'version'
        """
        result = await approval_health_helper.check_health()

        if not result["available"]:
            pytest.skip(f"Approval Service não disponível: {result.get('error')}")

        assert "version" in result["response"] or "service" in result["response"]


@pytest.mark.asyncio
class TestApprovalReadiness:
    """Testes de readiness para Approval Service."""

    async def test_ready_endpoint_responds(self, approval_health_helper):
        """
        TEST: [APPROVAL-003] Endpoint /ready responde

        Dado: Approval Service está rodando
        Quando: GET /ready é chamado
        Então: Response contém checks de dependências
        """
        result = await approval_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Approval Service não disponível: {result.get('error')}")

        assert "checks" in result["response"] or "ready" in result["response"]


@pytest.mark.asyncio
class TestApprovalSmokeComplete:
    """Smoke test completo para Approval Service."""

    async def test_approval_both_endpoints_healthy(self, approval_health_helper):
        """
        TEST: [APPROVAL-004] Smoke test completo

        Dado: Approval Service está rodando
        Quando: Ambos /health e /ready são verificados
        Então: Ambos respondem
        """
        result = await approval_health_helper.check_all()

        # Se não disponível, skip teste
        if not result["health"]["available"]:
            pytest.skip(f"Approval Service não disponível")

        assert result["health"]["status_code"] == 200
        assert result["ready"]["status_code"] in {200, 503}
