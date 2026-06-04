"""
Smoke Tests E2E para Worker Agents.

Valida:
- Endpoint /health responde
- Endpoint /ready verifica dependências
- Serviço de execução está acessível
"""

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
class TestWorkerHealth:
    """Testes de health check para Worker Agents."""

    async def test_health_endpoint_responds(self, worker_health_helper):
        """
        TEST: [WORKER-001] Endpoint /health responde em <5s

        Dado: Worker Agents está rodando
        Quando: GET /health é chamado
        Então: Response HTTP 200 com status='healthy'
        """
        result = await worker_health_helper.check_health()

        # Worker Agents pode não estar disponível em todos ambientes
        if not result["available"]:
            pytest.skip(f"Worker Agents não disponível: {result.get('error')}")

        assert result["status_code"] == 200
        assert result["response"] is not None
        assert result["response"].get("status") == "healthy"

    async def test_health_contains_service_info(self, worker_health_helper):
        """
        TEST: [WORKER-002] Response de /health contém informações do serviço

        Dado: Worker Agents está rodando
        Quando: GET /health é chamado
        Então: Response contém campo 'service' ou equivalente
        """
        result = await worker_health_helper.check_health()

        if not result["available"]:
            pytest.skip(f"Worker Agents não disponível: {result.get('error')}")

        assert "service" in result["response"] or "status" in result["response"]


@pytest.mark.asyncio
class TestWorkerSmokeComplete:
    """Smoke test completo para Worker Agents."""

    async def test_worker_both_endpoints_healthy(self, worker_health_helper):
        """
        TEST: [WORKER-003] Smoke test completo

        Dado: Worker Agents está rodando
        Quando: Ambos /health e /ready são verificados
        Então: Ambos respondem
        """
        result = await worker_health_helper.check_all()

        # Se não disponível, skip teste
        if not result["health"]["available"]:
            pytest.skip("Worker Agents não disponível")

        assert result["health"]["status_code"] == 200
        # Ready pode não existir em worker agents
        if result["ready"]["available"]:
            assert result["ready"]["status_code"] in {200, 503}
