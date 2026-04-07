"""
Smoke Tests E2E para Orchestrator Dynamic.

Valida:
- Endpoint /health responde
- Endpoint /ready verifica dependências (Temporal, MongoDB, Redis)
- Conectividade básica com serviços downstream
"""

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
class TestOrchestratorHealth:
    """Testes de health check para Orchestrator Dynamic."""

    async def test_health_endpoint_responds(self, orchestrator_health_helper):
        """
        TEST: [ORCH-001] Endpoint /health responde em <5s

        Dado: Orchestrator Dynamic está rodando
        Quando: GET /health é chamado
        Então: Response HTTP 200 com status='healthy'
        """
        result = await orchestrator_health_helper.check_health()

        # Orchestrator pode não estar disponível em todos ambientes
        if not result["available"]:
            pytest.skip(f"Orchestrator não disponível: {result.get('error')}")

        assert result["status_code"] == 200
        assert result["response"] is not None
        assert result["response"].get("status") == "healthy"

    async def test_health_contains_service_name(self, orchestrator_health_helper):
        """
        TEST: [ORCH-002] Response de /health contém nome do serviço

        Dado: Orchestrator Dynamic está rodando
        Quando: GET /health é chamado
        Então: Response contém campo 'service'
        """
        result = await orchestrator_health_helper.check_health()

        if not result["available"]:
            pytest.skip(f"Orchestrator não disponível: {result.get('error')}")

        assert "service" in result["response"]
        assert "orchestrator" in result["response"]["service"].lower()


@pytest.mark.asyncio
class TestOrchestratorReadiness:
    """Testes de readiness para Orchestrator Dynamic."""

    async def test_ready_endpoint_responds(self, orchestrator_health_helper):
        """
        TEST: [ORCH-003] Endpoint /ready responde

        Dado: Orchestrator Dynamic está rodando
        Quando: GET /ready é chamado
        Então: Response contém checks de dependências
        """
        result = await orchestrator_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Orchestrator não disponível: {result.get('error')}")

        assert "checks" in result["response"]

    async def test_ready_checks_temporal(self, orchestrator_health_helper):
        """
        TEST: [ORCH-004] /ready verifica Temporal

        Dado: Orchestrator Dynamic está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem Temporal
        """
        result = await orchestrator_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Orchestrator não disponível: {result.get('error')}")

        checks = result["response"]["checks"]
        # Pode ter diferentes nomes para check temporal
        temporal_found = any(
            "temporal" in k.lower() or "workflow" in k.lower() for k in checks.keys()
        )
        assert temporal_found, "Check de Temporal não encontrado em /ready"


@pytest.mark.asyncio
class TestOrchestratorSmokeComplete:
    """Smoke test completo para Orchestrator."""

    async def test_orchestrator_both_endpoints_healthy(self, orchestrator_health_helper):
        """
        TEST: [ORCH-005] Smoke test completo

        Dado: Orchestrator Dynamic está rodando
        Quando: Ambos /health e /ready são verificados
        Então: Ambos respondem
        """
        result = await orchestrator_health_helper.check_all()

        # Se não disponível, skip teste
        if not result["health"]["available"]:
            pytest.skip(f"Orchestrator não disponível")

        assert result["health"]["status_code"] == 200
        assert result["ready"]["status_code"] in {200, 503}
