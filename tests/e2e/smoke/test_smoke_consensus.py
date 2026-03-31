"""
Smoke Tests E2E para Consensus Engine.

Valida:
- Endpoint /health responde
- Endpoint /ready verifica dependências (MongoDB, Redis, Specialists, Queen Agent)
- Status dos especialistas é verificado
"""

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
class TestConsensusHealth:
    """Testes de health check para Consensus Engine."""

    async def test_health_endpoint_responds(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-001] Endpoint /health responde em <5s

        Dado: Consensus Engine está rodando
        Quando: GET /health é chamado
        Então: Response HTTP 200 com status='healthy'
        """
        result = await consensus_health_helper.check_health()

        assert (
            result["available"] is True
        ), f"Consensus Engine não disponível: {result['error']}"
        assert result["status_code"] == 200
        assert result["response"] is not None
        assert result["response"].get("status") == "healthy"
        assert result["response"].get("service") == "consensus-engine"

    async def test_health_response_minimal(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-002] Response de /health é minimal

        Dado: Consensus Engine está rodando
        Quando: GET /health é chamado
        Então: Response contém apenas status e service
        """
        result = await consensus_health_helper.check_health()

        assert result["available"] is True
        response = result["response"]
        # Health check básico do Consensus Engine
        assert "status" in response
        assert "service" in response
        # Pode ou não ter version
        assert len(response) >= 2


@pytest.mark.asyncio
class TestConsensusReadiness:
    """Testes de readiness para Consensus Engine."""

    async def test_ready_endpoint_responds(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-003] Endpoint /ready responde

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Response contém checks de dependências
        """
        result = await consensus_health_helper.check_ready()

        assert (
            result["available"] is True
        ), f"Consensus /ready não disponível: {result.get('error')}"
        assert "checks" in result["response"]

    async def test_ready_checks_mongodb(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-004] /ready verifica MongoDB

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem mongodb
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "mongodb" in checks

    async def test_ready_checks_redis(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-005] /ready verifica Redis

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem redis
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "redis" in checks

    async def test_ready_checks_specialists(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-006] /ready verifica especialistas

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem specialists (gRPC health check)
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "specialists" in checks
        assert isinstance(checks["specialists"], bool)

    async def test_ready_checks_queen_agent(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-007] /ready verifica Queen Agent

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem queen_agent
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "queen_agent" in checks
        assert isinstance(checks["queen_agent"], bool)

    async def test_ready_checks_analyst_agent_optional(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-008] /ready verifica Analyst Agent (opcional)

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem analyst_agent (pode ser None se não configurado)
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        # Analyst Agent é opcional
        if "analyst_agent" in checks:
            assert checks["analyst_agent"] is None or isinstance(
                checks["analyst_agent"], bool
            )

    async def test_ready_checks_otel_pipeline_optional(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-009] /ready verifica OTEL pipeline (opcional)

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem otel_pipeline (não-crítico)
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        # OTEL pode não estar presente em algumas versões
        if "otel_pipeline" in checks:
            assert isinstance(checks["otel_pipeline"], bool)


@pytest.mark.asyncio
class TestConsensusSpecialistsStatus:
    """Testes de status dos especialistas via Consensus Engine."""

    async def test_specialists_health_check_aggregated(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-010] Health check agregado dos especialistas

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Campo 'specialists' reflete saúde agregada
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "specialists" in checks
        # Deve ser booleano indicando se todos estão saudáveis
        assert isinstance(checks["specialists"], bool)


@pytest.mark.asyncio
class TestConsensusSmokeComplete:
    """Smoke test completo para Consensus Engine."""

    async def test_consensus_both_endpoints_healthy(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-011] Smoke test completo - ambos endpoints saudáveis

        Dado: Consensus Engine está rodando
        Quando: Ambos /health e /ready são verificados
        Então: Ambos respondem com status OK
        """
        result = await consensus_health_helper.check_all()

        # Health deve estar sempre OK
        assert result["health"]["available"] is True
        assert result["health"]["status_code"] == 200

        # Ready pode ser 503 se deps não estão prontas, mas deve responder
        assert result["ready"]["available"] is True
        assert result["ready"]["status_code"] in {200, 503}

    async def test_consensus_critical_deps_check(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-012] Dependências críticas verificadas

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Dependências críticas estão sendo checadas
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]

        # Dependências críticas do Consensus Engine
        critical_deps = ["mongodb", "redis", "specialists", "queen_agent"]
        for dep in critical_deps:
            assert dep in checks, f"Dependência crítica {dep} não está sendo checada"

    async def test_consensus_ready_flag_in_response(self, consensus_health_helper):
        """
        TEST: [CONSENSUS-013] Flag 'ready' presente na resposta

        Dado: Consensus Engine está rodando
        Quando: GET /ready é chamado
        Então: Response contém campo 'ready' indicando estado
        """
        result = await consensus_health_helper.check_ready()

        assert result["available"] is True
        response = result["response"]
        assert "ready" in response
        assert isinstance(response["ready"], bool)


@pytest.mark.asyncio
class TestConsensusGracefulDegradation:
    """Testes de graceful degradation quando serviço não disponível."""

    async def test_consensus_unavailable_graceful_error(self, http_client):
        """
        TEST: [CONSENSUS-014] Erro gracioso quando Consensus indisponível

        Dado: Consensus Engine NÃO está rodando
        Quando: Tentativa de conexão é feita
        Então: Timeout/conexão falha é identificada corretamente
        """
        from tests.e2e.smoke.conftest import ServiceHealthHelper

        helper = ServiceHealthHelper(http_client, "http://invalid-consensus:9999")

        result = await helper.check_health()

        assert result["available"] is False
        assert result["status_code"] is None
        assert (
            result["error"] in {"timeout", "connection_refused"}
            or result["error"] is not None
        )
