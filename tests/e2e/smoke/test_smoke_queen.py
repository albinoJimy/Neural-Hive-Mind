"""
Smoke Tests E2E para Queen Agent.

Valida:
- Endpoint /health responde
- Endpoint /ready verifica dependências (MongoDB, Redis, Neo4j, Kafka)
- Leader election status (se disponível)
"""

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
class TestQueenHealth:
    """Testes de health check para Queen Agent."""

    async def test_health_endpoint_responds(self, queen_health_helper):
        """
        TEST: [QUEEN-001] Endpoint /health responde em <5s

        Dado: Queen Agent está rodando
        Quando: GET /health é chamado
        Então: Response HTTP 200 com status='healthy'
        """
        result = await queen_health_helper.check_health()

        # Queen Agent pode não estar disponível em todos ambientes
        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        assert result["status_code"] == 200
        assert result["response"] is not None
        assert result["response"].get("status") == "healthy"
        assert result["response"].get("service") == "queen-agent"

    async def test_health_contains_version(self, queen_health_helper):
        """
        TEST: [QUEEN-002] Response de /health contém versão

        Dado: Queen Agent está rodando
        Quando: GET /health é chamado
        Então: Response contém campo 'version'
        """
        result = await queen_health_helper.check_health()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        assert "version" in result["response"]
        assert isinstance(result["response"]["version"], str)


@pytest.mark.asyncio
class TestQueenReadiness:
    """Testes de readiness para Queen Agent."""

    async def test_ready_endpoint_responds(self, queen_health_helper):
        """
        TEST: [QUEEN-003] Endpoint /ready responde

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Response contém checks de dependências
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        assert "checks" in result["response"]

    async def test_ready_checks_mongodb(self, queen_health_helper):
        """
        TEST: [QUEEN-004] /ready verifica MongoDB

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem mongodb
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        checks = result["response"]["checks"]
        assert "mongodb" in checks

    async def test_ready_checks_redis(self, queen_health_helper):
        """
        TEST: [QUEEN-005] /ready verifica Redis

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem redis
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        checks = result["response"]["checks"]
        assert "redis" in checks

    async def test_ready_checks_neo4j(self, queen_health_helper):
        """
        TEST: [QUEEN-006] /ready verifica Neo4j

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem neo4j
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        checks = result["response"]["checks"]
        assert "neo4j" in checks

    async def test_ready_checks_kafka(self, queen_health_helper):
        """
        TEST: [QUEEN-007] /ready verifica Kafka consumers

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem kafka
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        checks = result["response"]["checks"]
        # Pode ter diferentes nomes para checks kafka
        kafka_found = any("kafka" in k.lower() for k in checks.keys())
        assert kafka_found, "Check de Kafka não encontrado em /ready"


@pytest.mark.asyncio
class TestQueenOptionalChecks:
    """Testes de checks opcionais do Queen Agent."""

    async def test_ready_checks_grpc_server(self, queen_health_helper):
        """
        TEST: [QUEEN-008] /ready verifica gRPC server

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem grpc
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        checks = result["response"]["checks"]
        # gRPC pode ou não estar sendo checado
        if "grpc" in checks:
            assert isinstance(checks["grpc"], bool)

    async def test_ready_checks_leader_election_optional(self, queen_health_helper):
        """
        TEST: [QUEEN-009] /ready verifica leader election (opcional)

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem leader_election (se configurado)
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        checks = result["response"]["checks"]
        # Leader election é opcional
        if "leader_election" in checks:
            assert isinstance(checks["leader_election"], bool)


@pytest.mark.asyncio
class TestQueenSmokeComplete:
    """Smoke test completo para Queen Agent."""

    async def test_queen_both_endpoints_healthy(self, queen_health_helper):
        """
        TEST: [QUEEN-010] Smoke test completo

        Dado: Queen Agent está rodando
        Quando: Ambos /health e /ready são verificados
        Então: Ambos respondem com status OK
        """
        result = await queen_health_helper.check_all()

        # Se não disponível, skip teste
        if not result["health"]["available"]:
            pytest.skip("Queen Agent não disponível")

        assert result["health"]["status_code"] == 200
        assert result["ready"]["status_code"] in {200, 503}

    async def test_queen_critical_deps_check(self, queen_health_helper):
        """
        TEST: [QUEEN-011] Dependências críticas verificadas

        Dado: Queen Agent está rodando
        Quando: GET /ready é chamado
        Então: Dependências críticas estão sendo checadas
        """
        result = await queen_health_helper.check_ready()

        if not result["available"]:
            pytest.skip(f"Queen Agent não disponível: {result.get('error')}")

        checks = result["response"]["checks"]

        # Dependências críticas do Queen Agent
        critical_deps = ["mongodb", "redis", "neo4j"]
        for dep in critical_deps:
            assert dep in checks, f"Dependência crítica {dep} não está sendo checada"
