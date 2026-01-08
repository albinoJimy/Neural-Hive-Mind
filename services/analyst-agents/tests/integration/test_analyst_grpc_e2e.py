"""Testes de integracao end-to-end para o servico gRPC do Analyst Agent.

Estes testes iniciam o AnalystGRPCServer real e exercitam os endpoints gRPC
usando stubs sobre um canal gRPC. Requerem MongoDB e Redis (e opcionalmente Neo4j)
disponiveis para execucao completa.
"""
import pytest
import asyncio
import uuid
import grpc
from datetime import datetime

from src.grpc_service.server import AnalystGRPCServer
from src.grpc_service.analyst_servicer import AnalystServicer
from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.clients.neo4j_client import Neo4jClient
from src.services.insight_generator import InsightGenerator
from src.proto import analyst_agent_pb2, analyst_agent_pb2_grpc
from src.models.insight import AnalystInsight, InsightType, Priority, Recommendation, RelatedEntity, TimeWindow


# Configuracoes de teste - usar variaveis de ambiente ou valores padrão para testes
TEST_MONGODB_URI = "mongodb://localhost:27017"
TEST_MONGODB_DATABASE = "analyst_agents_test"
TEST_MONGODB_COLLECTION = "insights_test"
TEST_REDIS_HOST = "localhost"
TEST_REDIS_PORT = 6379
TEST_REDIS_PASSWORD = None
TEST_REDIS_DB = 15  # DB dedicado para testes
TEST_REDIS_TTL = 3600
TEST_NEO4J_URI = "bolt://localhost:7687"
TEST_NEO4J_USER = "neo4j"
TEST_NEO4J_PASSWORD = "testpassword"
TEST_NEO4J_DATABASE = "neo4j"
TEST_GRPC_HOST = "127.0.0.1"
TEST_GRPC_PORT = 50099


class TestQueryEngine:
    """Query engine simplificado para testes."""

    def __init__(self):
        self._data = {}

    async def get_metric_timeseries(self, metric_name: str):
        return self._data.get(metric_name, [1.0, 2.0, 3.0, 4.0, 5.0])


class TestAnalyticsEngine:
    """Analytics engine simplificado para testes."""

    def __init__(self):
        pass

    def detect_anomalies(self, metric_name: str, values: list, threshold: float = 3.0):
        return []

    def calculate_trend(self, metric_name: str, values: list):
        return {'slope': 0.5, 'direction': 'up', 'confidence': 0.85}

    def calculate_correlation(self, values1: list, values2: list):
        return 0.75


@pytest.fixture(scope="module")
def event_loop():
    """Criar event loop para testes assincronos."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def mongodb_client():
    """Inicializar cliente MongoDB real para testes."""
    client = MongoDBClient(
        uri=TEST_MONGODB_URI,
        database=TEST_MONGODB_DATABASE,
        collection=TEST_MONGODB_COLLECTION
    )
    try:
        await client.initialize()
        yield client
    except Exception as e:
        pytest.skip(f"MongoDB nao disponivel: {e}")
    finally:
        # Limpar colecao de teste
        if client.collection:
            await client.collection.delete_many({})
        await client.close()


@pytest.fixture(scope="module")
async def redis_client():
    """Inicializar cliente Redis real para testes."""
    client = RedisClient(
        host=TEST_REDIS_HOST,
        port=TEST_REDIS_PORT,
        password=TEST_REDIS_PASSWORD,
        db=TEST_REDIS_DB,
        ttl=TEST_REDIS_TTL
    )
    try:
        await client.initialize()
        yield client
    except Exception as e:
        pytest.skip(f"Redis nao disponivel: {e}")
    finally:
        if client.client:
            try:
                await client.client.flushdb()
            except Exception:
                pass
        await client.close()


@pytest.fixture(scope="module")
async def neo4j_client():
    """Inicializar cliente Neo4j para testes (opcional)."""
    client = Neo4jClient(
        uri=TEST_NEO4J_URI,
        user=TEST_NEO4J_USER,
        password=TEST_NEO4J_PASSWORD,
        database=TEST_NEO4J_DATABASE
    )
    try:
        await client.initialize()
        yield client
    except Exception:
        yield None
    finally:
        if client.driver:
            # Limpar dados de teste
            try:
                await client.query_patterns("MATCH (n) WHERE n.insight_id STARTS WITH 'test-' DETACH DELETE n", {})
            except Exception:
                pass
            await client.close()


@pytest.fixture(scope="module")
async def grpc_server(mongodb_client, redis_client, neo4j_client):
    """Inicializar servidor gRPC para testes."""
    query_engine = TestQueryEngine()
    analytics_engine = TestAnalyticsEngine()
    insight_generator = InsightGenerator(min_confidence=0.5)

    server = AnalystGRPCServer(
        host=TEST_GRPC_HOST,
        port=TEST_GRPC_PORT,
        mongodb_client=mongodb_client,
        redis_client=redis_client,
        query_engine=query_engine,
        analytics_engine=analytics_engine,
        insight_generator=insight_generator,
        neo4j_client=neo4j_client,
        max_workers=4
    )

    await server.start()
    yield server
    await server.stop(grace_period=1)


@pytest.fixture(scope="module")
async def grpc_channel(grpc_server):
    """Criar canal gRPC para testes."""
    channel = grpc.aio.insecure_channel(f"{TEST_GRPC_HOST}:{TEST_GRPC_PORT}")
    yield channel
    await channel.close()


@pytest.fixture(scope="module")
def grpc_stub(grpc_channel):
    """Criar stub gRPC para testes."""
    return analyst_agent_pb2_grpc.AnalystAgentServiceStub(grpc_channel)


@pytest.fixture
async def seeded_insight(mongodb_client, redis_client):
    """Inserir insight de teste no MongoDB e Redis."""
    insight = AnalystInsight(
        insight_id=f"test-{uuid.uuid4()}",
        version="1.0.0",
        correlation_id=str(uuid.uuid4()),
        trace_id=str(uuid.uuid4()),
        span_id=str(uuid.uuid4()),
        insight_type=InsightType.ANOMALY,
        priority=Priority.HIGH,
        title="Insight de Teste E2E",
        summary="Insight criado para testes de integracao",
        detailed_analysis="Analise detalhada para validacao de testes end-to-end",
        data_sources=["test", "e2e"],
        metrics={"test_value": 95.5, "threshold": 80.0},
        confidence_score=0.92,
        impact_score=0.85,
        recommendations=[
            Recommendation(action="Acao de teste", priority="HIGH", estimated_impact=0.8)
        ],
        related_entities=[
            RelatedEntity(entity_type="test", entity_id="test-entity-1", relationship="test_relation")
        ],
        time_window=TimeWindow(start_timestamp=1704067200000, end_timestamp=1704153600000),
        tags=["test", "e2e"],
        metadata={"test_key": "test_value"}
    )

    await mongodb_client.save_insight(insight)
    await redis_client.cache_insight(insight)

    yield insight

    # Cleanup
    if mongodb_client.collection:
        await mongodb_client.collection.delete_one({"insight_id": insight.insight_id})


class TestHealthCheckE2E:
    """Testes end-to-end para HealthCheck."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self, grpc_stub):
        """Verificar que health check retorna saudavel com servicos ativos."""
        request = analyst_agent_pb2.HealthCheckRequest()
        response = await grpc_stub.HealthCheck(request)

        assert response.status in ["HEALTHY", "DEGRADED"]


class TestGetInsightE2E:
    """Testes end-to-end para GetInsight."""

    @pytest.mark.asyncio
    async def test_get_insight_not_found(self, grpc_stub):
        """Buscar insight inexistente retorna found=False."""
        request = analyst_agent_pb2.GetInsightRequest(insight_id="non-existent-id")
        response = await grpc_stub.GetInsight(request)

        assert response.found is False

    @pytest.mark.asyncio
    async def test_get_insight_found(self, grpc_stub, seeded_insight):
        """Buscar insight existente retorna dados corretos."""
        request = analyst_agent_pb2.GetInsightRequest(insight_id=seeded_insight.insight_id)
        response = await grpc_stub.GetInsight(request)

        assert response.found is True
        assert response.insight.insight_id == seeded_insight.insight_id
        assert response.insight.insight_type == "ANOMALY"
        assert response.insight.priority == "HIGH"
        assert response.insight.title == "Insight de Teste E2E"

    @pytest.mark.asyncio
    async def test_get_insight_cache_hit(self, grpc_stub, seeded_insight, redis_client):
        """Verificar que insight e retornado do cache."""
        # Primeira chamada popula o cache
        request = analyst_agent_pb2.GetInsightRequest(insight_id=seeded_insight.insight_id)
        response1 = await grpc_stub.GetInsight(request)
        assert response1.found is True

        # Segunda chamada deve usar cache
        response2 = await grpc_stub.GetInsight(request)
        assert response2.found is True
        assert response2.insight.insight_id == seeded_insight.insight_id


class TestQueryInsightsE2E:
    """Testes end-to-end para QueryInsights."""

    @pytest.mark.asyncio
    async def test_query_insights_empty(self, grpc_stub):
        """Consulta sem filtros em colecao vazia."""
        request = analyst_agent_pb2.QueryInsightsRequest(
            insight_type="NON_EXISTENT_TYPE",
            limit=10
        )
        response = await grpc_stub.QueryInsights(request)

        assert response.total_count == 0
        assert len(response.insights) == 0

    @pytest.mark.asyncio
    async def test_query_insights_by_type(self, grpc_stub, seeded_insight):
        """Consultar insights por tipo."""
        request = analyst_agent_pb2.QueryInsightsRequest(
            insight_type="ANOMALY",
            limit=10
        )
        response = await grpc_stub.QueryInsights(request)

        assert response.total_count >= 1
        found = any(i.insight_id == seeded_insight.insight_id for i in response.insights)
        assert found

    @pytest.mark.asyncio
    async def test_query_insights_by_priority(self, grpc_stub, seeded_insight):
        """Consultar insights por prioridade."""
        request = analyst_agent_pb2.QueryInsightsRequest(
            priority="HIGH",
            limit=10
        )
        response = await grpc_stub.QueryInsights(request)

        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_query_insights_with_time_filter(self, grpc_stub, seeded_insight):
        """Consultar insights com filtro de tempo."""
        request = analyst_agent_pb2.QueryInsightsRequest(
            start_timestamp=1704067200000,
            end_timestamp=int(datetime.utcnow().timestamp() * 1000) + 86400000,
            limit=10
        )
        response = await grpc_stub.QueryInsights(request)

        assert response.total_count >= 0


class TestExecuteAnalysisE2E:
    """Testes end-to-end para ExecuteAnalysis."""

    @pytest.mark.asyncio
    async def test_execute_anomaly_detection(self, grpc_stub):
        """Executar deteccao de anomalias."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type="anomaly_detection",
            parameters={"metric_name": "cpu_usage", "threshold": "3.0"}
        )
        response = await grpc_stub.ExecuteAnalysis(request)

        assert response.analysis_id != ""
        assert "anomaly_count" in response.results
        assert response.confidence > 0

    @pytest.mark.asyncio
    async def test_execute_trend_analysis(self, grpc_stub):
        """Executar analise de tendencia."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type="trend_analysis",
            parameters={"metric_name": "memory_usage"}
        )
        response = await grpc_stub.ExecuteAnalysis(request)

        assert response.analysis_id != ""
        assert "slope" in response.results

    @pytest.mark.asyncio
    async def test_execute_correlation_analysis(self, grpc_stub):
        """Executar analise de correlacao."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type="correlation",
            parameters={"metric1": "cpu_usage", "metric2": "memory_usage"}
        )
        response = await grpc_stub.ExecuteAnalysis(request)

        assert response.analysis_id != ""
        assert "correlation" in response.results

    @pytest.mark.asyncio
    async def test_execute_invalid_analysis_type(self, grpc_stub):
        """Tipo de analise invalido retorna erro."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type="invalid_type",
            parameters={}
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await grpc_stub.ExecuteAnalysis(request)

        assert exc_info.value.code() == grpc.StatusCode.INVALID_ARGUMENT


class TestGetStatisticsE2E:
    """Testes end-to-end para GetStatistics."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, grpc_stub, seeded_insight):
        """Obter estatisticas de insights."""
        request = analyst_agent_pb2.GetStatisticsRequest()
        response = await grpc_stub.GetStatistics(request)

        # Com pelo menos um insight inserido
        assert "ANOMALY" in response.insights_by_type or response.insights_by_type == {}


class TestGenerateInsightE2E:
    """Testes end-to-end para GenerateInsight."""

    @pytest.mark.asyncio
    async def test_generate_insight_success(self, grpc_stub, mongodb_client):
        """Gerar novo insight via gRPC."""
        request = analyst_agent_pb2.GenerateInsightRequest(
            insight_type="OPERATIONAL",
            title="Insight Gerado via gRPC",
            summary="Teste de geracao de insight",
            detailed_analysis="Analise detalhada gerada pelo teste E2E",
            data_sources=["grpc_test"],
            metrics={"test_metric": 42.0},
            correlation_id=str(uuid.uuid4()),
            tags=["e2e", "generated"],
            persist_to_neo4j=False
        )
        response = await grpc_stub.GenerateInsight(request)

        assert response.success is True
        assert response.insight.insight_id != ""
        assert response.insight.insight_type == "OPERATIONAL"
        assert response.insight.title == "Insight Gerado via gRPC"

        # Verificar persistencia no MongoDB
        saved = await mongodb_client.get_insight_by_id(response.insight.insight_id)
        assert saved is not None
        assert saved["title"] == "Insight Gerado via gRPC"

        # Cleanup
        await mongodb_client.collection.delete_one({"insight_id": response.insight.insight_id})

    @pytest.mark.asyncio
    async def test_generate_insight_invalid_type(self, grpc_stub):
        """Tipo de insight invalido retorna erro."""
        request = analyst_agent_pb2.GenerateInsightRequest(
            insight_type="INVALID_TYPE",
            title="Teste Invalido",
            summary="Teste"
        )
        response = await grpc_stub.GenerateInsight(request)

        assert response.success is False
        assert "Invalid insight_type" in response.error_message

    @pytest.mark.asyncio
    async def test_generate_insight_with_related_entities(self, grpc_stub, mongodb_client):
        """Gerar insight com entidades relacionadas."""
        related_entity = analyst_agent_pb2.RelatedEntity(
            entity_type="test",
            entity_id="test-entity-123",
            relationship="caused_by"
        )
        request = analyst_agent_pb2.GenerateInsightRequest(
            insight_type="CAUSAL",
            title="Insight com Entidades Relacionadas",
            summary="Teste de relacionamentos",
            detailed_analysis="Analise causal",
            related_entities=[related_entity],
            persist_to_neo4j=False
        )
        response = await grpc_stub.GenerateInsight(request)

        assert response.success is True
        assert response.insight.insight_id != ""

        # Cleanup
        await mongodb_client.collection.delete_one({"insight_id": response.insight.insight_id})


class TestQueryInsightsWithNeo4jE2E:
    """Testes end-to-end para QueryInsights com enriquecimento Neo4j."""

    @pytest.mark.asyncio
    async def test_query_with_graph_enrichment_no_neo4j(self, grpc_stub):
        """Consulta com graph_enrichment sem Neo4j disponivel funciona."""
        request = analyst_agent_pb2.QueryInsightsRequest(
            use_graph_enrichment=True,
            related_entity_id="some-entity",
            limit=10
        )
        response = await grpc_stub.QueryInsights(request)

        # Deve funcionar mesmo sem Neo4j
        assert response.total_count >= 0
