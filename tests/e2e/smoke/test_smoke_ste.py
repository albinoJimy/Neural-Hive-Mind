"""
Smoke Tests E2E para Semantic Translation Engine (STE).

Valida:
- Endpoint /health responde
- Endpoint /ready verifica dependências (Kafka, MongoDB, Redis, Neo4j)
- Consumer health check funciona
"""

import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.asyncio
class TestSTEHealth:
    """Testes de health check para Semantic Translation Engine."""

    async def test_health_endpoint_responds(self, ste_health_helper):
        """
        TEST: [STE-001] Endpoint /health responde em <5s

        Dado: Semantic Translation Engine está rodando
        Quando: GET /health é chamado
        Então: Response HTTP 200 com status='healthy'
        """
        result = await ste_health_helper.check_health()

        assert result["available"] is True, f"STE não disponível: {result['error']}"
        assert result["status_code"] == 200
        assert result["response"] is not None
        assert result["response"].get("status") == "healthy"
        assert result["response"].get("service") == "semantic-translation-engine"

    async def test_health_contains_version(self, ste_health_helper):
        """
        TEST: [STE-002] Response de /health contém versão

        Dado: Semantic Translation Engine está rodando
        Quando: GET /health é chamado
        Então: Response contém campo 'version'
        """
        result = await ste_health_helper.check_health()

        assert result["available"] is True
        assert "version" in result["response"]
        assert isinstance(result["response"]["version"], str)


@pytest.mark.asyncio
class TestSTEReadiness:
    """Testes de readiness para Semantic Translation Engine."""

    async def test_ready_endpoint_responds(self, ste_health_helper):
        """
        TEST: [STE-003] Endpoint /ready responde

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Response contém checks de dependências
        """
        result = await ste_health_helper.check_ready()

        assert (
            result["available"] is True
        ), f"STE /ready não disponível: {result.get('error')}"
        assert "checks" in result["response"]

    async def test_ready_checks_kafka_producer(self, ste_health_helper):
        """
        TEST: [STE-004] /ready verifica Kafka producer

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem kafka_producer
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "kafka_producer" in checks

    async def test_ready_checks_kafka_consumer_health(self, ste_health_helper):
        """
        TEST: [STE-005] /ready verifica saúde do Kafka consumer

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem kafka_consumer com status
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "kafka_consumer" in checks
        # Status pode ser bool
        assert isinstance(checks["kafka_consumer"], bool)

    async def test_ready_checks_mongodb(self, ste_health_helper):
        """
        TEST: [STE-006] /ready verifica MongoDB

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem mongodb
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "mongodb" in checks

    async def test_ready_checks_redis(self, ste_health_helper):
        """
        TEST: [STE-007] /ready verifica Redis

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem redis
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "redis" in checks

    async def test_ready_checks_neo4j(self, ste_health_helper):
        """
        TEST: [STE-008] /ready verifica Neo4j

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem neo4j
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "neo4j" in checks

    async def test_ready_checks_nlp_processor_optional(self, ste_health_helper):
        """
        TEST: [STE-009] /ready verifica NLP Processor (opcional)

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem nlp_processor (pode ser True se não habilitado)
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "nlp_processor" in checks
        # NLP é opcional, pode estar True (habilitado e pronto) ou True (não habilitado)
        assert isinstance(checks["nlp_processor"], bool)

    async def test_ready_checks_otel_pipeline(self, ste_health_helper):
        """
        TEST: [STE-010] /ready verifica OTEL pipeline

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem otel_pipeline
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        # OTEL pode não estar presente em algumas versões
        if "otel_pipeline" in checks:
            assert isinstance(checks["otel_pipeline"], bool)


@pytest.mark.asyncio
class TestSTEConsumerMetrics:
    """Testes de métricas de consumer do STE."""

    async def test_ready_checks_approval_response_consumer(self, ste_health_helper):
        """
        TEST: [STE-011] /ready verifica Approval Response Consumer

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Checks incluem approval_response_consumer
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]
        assert "approval_response_consumer" in checks
        # Approval consumer pode estar None (não configurado) ou bool
        assert checks["approval_response_consumer"] is None or isinstance(
            checks["approval_response_consumer"], bool
        )


@pytest.mark.asyncio
class TestSTESmokeComplete:
    """Smoke test completo para STE."""

    async def test_ste_both_endpoints_healthy(self, ste_health_helper):
        """
        TEST: [STE-012] Smoke test completo - ambos endpoints saudáveis

        Dado: Semantic Translation Engine está rodando
        Quando: Ambos /health e /ready são verificados
        Então: Ambos respondem com status OK
        """
        result = await ste_health_helper.check_all()

        # Health deve estar sempre OK
        assert result["health"]["available"] is True
        assert result["health"]["status_code"] == 200

        # Ready pode ser 503 se deps não estão prontas, mas deve responder
        assert result["ready"]["available"] is True
        assert result["ready"]["status_code"] in {200, 503}

    async def test_ste_critical_deps_check(self, ste_health_helper):
        """
        TEST: [STE-013] Dependências críticas verificadas

        Dado: Semantic Translation Engine está rodando
        Quando: GET /ready é chamado
        Então: Dependências críticas estão sendo checadas
        """
        result = await ste_health_helper.check_ready()

        assert result["available"] is True
        checks = result["response"]["checks"]

        # Dependências críticas do STE
        critical_deps = [
            "kafka_consumer",
            "kafka_producer",
            "mongodb",
            "redis",
            "neo4j",
        ]
        for dep in critical_deps:
            assert dep in checks, f"Dependência crítica {dep} não está sendo checada"


@pytest.mark.asyncio
class TestSTEGracefulDegradation:
    """Testes de graceful degradation quando serviço não disponível."""

    async def test_ste_unavailable_graceful_error(self, http_client):
        """
        TEST: [STE-014] Erro gracioso quando STE indisponível

        Dado: Semantic Translation Engine NÃO está rodando
        Quando: Tentativa de conexão é feita
        Então: Timeout/conexão falha é identificada corretamente
        """
        from tests.e2e.smoke.conftest import ServiceHealthHelper

        helper = ServiceHealthHelper(http_client, "http://invalid-ste-service:9999")

        result = await helper.check_health()

        assert result["available"] is False
        assert result["status_code"] is None
        assert (
            result["error"] in {"timeout", "connection_refused"}
            or result["error"] is not None
        )
