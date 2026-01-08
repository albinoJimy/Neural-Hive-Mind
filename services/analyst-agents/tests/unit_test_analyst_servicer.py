"""Testes unitarios para o AnalystServicer (com mocks)."""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.grpc_service.analyst_servicer import AnalystServicer
from src.proto import analyst_agent_pb2


@pytest.fixture
def mock_mongodb_client():
    """Mock do cliente MongoDB."""
    client = AsyncMock()
    client.client = MagicMock()
    client.client.admin.command = AsyncMock(return_value={'ok': 1})
    client.get_insight_by_id = AsyncMock(return_value=None)
    client.query_insights = AsyncMock(return_value=[])
    client.get_insight_statistics = AsyncMock(return_value={
        'by_type': {},
        'by_priority': {},
        'avg_confidence': 0.0,
        'avg_impact': 0.0,
        'total': 0
    })
    return client


@pytest.fixture
def mock_redis_client():
    """Mock do cliente Redis."""
    client = AsyncMock()
    client.client = MagicMock()
    client.client.ping = AsyncMock(return_value=True)
    client.get_cached_insight = AsyncMock(return_value=None)
    client.cache_insight = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_query_engine():
    """Mock do query engine."""
    engine = AsyncMock()
    engine.get_metric_timeseries = AsyncMock(return_value=[1.0, 2.0, 3.0])
    return engine


@pytest.fixture
def mock_analytics_engine():
    """Mock do analytics engine."""
    engine = MagicMock()
    engine.detect_anomalies = MagicMock(return_value=[])
    engine.calculate_trend = MagicMock(return_value={'slope': 0.5, 'direction': 'up', 'confidence': 0.8})
    engine.calculate_correlation = MagicMock(return_value=0.85)
    return engine


@pytest.fixture
def mock_insight_generator():
    """Mock do gerador de insights."""
    return MagicMock()


@pytest.fixture
def servicer(mock_mongodb_client, mock_redis_client, mock_query_engine, mock_analytics_engine, mock_insight_generator):
    """Cria o servicer com dependencias mockadas."""
    return AnalystServicer(
        mongodb_client=mock_mongodb_client,
        redis_client=mock_redis_client,
        query_engine=mock_query_engine,
        analytics_engine=mock_analytics_engine,
        insight_generator=mock_insight_generator
    )


@pytest.fixture
def mock_grpc_context():
    """Mock do contexto gRPC."""
    context = MagicMock()
    context.invocation_metadata = MagicMock(return_value=[])
    context.set_code = MagicMock()
    context.set_details = MagicMock()
    return context


@pytest.fixture
def sample_insight_dict():
    """Dados de exemplo de um insight."""
    return {
        'insight_id': str(uuid.uuid4()),
        'version': '1.0.0',
        'correlation_id': str(uuid.uuid4()),
        'trace_id': '',
        'span_id': '',
        'insight_type': 'ANOMALY',
        'priority': 'HIGH',
        'title': 'Teste de Anomalia',
        'summary': 'Detectada anomalia de teste',
        'detailed_analysis': 'Analise detalhada do teste',
        'data_sources': ['prometheus', 'mongodb'],
        'metrics': {'value': 95.5, 'threshold': 80.0},
        'confidence_score': 0.92,
        'impact_score': 0.85,
        'recommendations': [
            {'action': 'Escalar recursos', 'priority': 'HIGH', 'estimated_impact': 0.8}
        ],
        'created_at': 1704067200000,
        'hash': 'abc123'
    }


class TestGetInsight:
    """Testes para o metodo GetInsight."""

    @pytest.mark.asyncio
    async def test_get_insight_not_found(self, servicer, mock_grpc_context):
        """Testa busca de insight inexistente."""
        request = analyst_agent_pb2.GetInsightRequest(insight_id='non-existent-id')

        response = await servicer.GetInsight(request, mock_grpc_context)

        assert response.found is False

    @pytest.mark.asyncio
    async def test_get_insight_cache_hit(self, servicer, mock_redis_client, mock_grpc_context, sample_insight_dict):
        """Testa busca de insight com cache hit."""
        mock_redis_client.get_cached_insight.return_value = sample_insight_dict
        request = analyst_agent_pb2.GetInsightRequest(insight_id=sample_insight_dict['insight_id'])

        response = await servicer.GetInsight(request, mock_grpc_context)

        assert response.found is True
        assert response.insight.insight_id == sample_insight_dict['insight_id']
        assert response.insight.insight_type == 'ANOMALY'
        mock_redis_client.get_cached_insight.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_insight_from_mongodb(self, servicer, mock_mongodb_client, mock_redis_client, mock_grpc_context, sample_insight_dict):
        """Testa busca de insight no MongoDB quando nao esta em cache."""
        mock_redis_client.get_cached_insight.return_value = None
        mock_mongodb_client.get_insight_by_id.return_value = sample_insight_dict
        request = analyst_agent_pb2.GetInsightRequest(insight_id=sample_insight_dict['insight_id'])

        response = await servicer.GetInsight(request, mock_grpc_context)

        assert response.found is True
        assert response.insight.insight_id == sample_insight_dict['insight_id']
        mock_mongodb_client.get_insight_by_id.assert_called_once()


class TestQueryInsights:
    """Testes para o metodo QueryInsights."""

    @pytest.mark.asyncio
    async def test_query_insights_empty(self, servicer, mock_grpc_context):
        """Testa consulta sem resultados."""
        request = analyst_agent_pb2.QueryInsightsRequest(
            insight_type='ANOMALY',
            limit=10
        )

        response = await servicer.QueryInsights(request, mock_grpc_context)

        assert response.total_count == 0
        assert len(response.insights) == 0

    @pytest.mark.asyncio
    async def test_query_insights_with_results(self, servicer, mock_mongodb_client, mock_grpc_context, sample_insight_dict):
        """Testa consulta com resultados."""
        mock_mongodb_client.query_insights.return_value = [sample_insight_dict]
        request = analyst_agent_pb2.QueryInsightsRequest(
            insight_type='ANOMALY',
            limit=10
        )

        response = await servicer.QueryInsights(request, mock_grpc_context)

        assert response.total_count == 1
        assert len(response.insights) == 1
        assert response.insights[0].insight_type == 'ANOMALY'

    @pytest.mark.asyncio
    async def test_query_insights_with_time_filter(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa consulta com filtro de tempo."""
        request = analyst_agent_pb2.QueryInsightsRequest(
            start_timestamp=1704067200000,
            end_timestamp=1704153600000,
            limit=10
        )

        await servicer.QueryInsights(request, mock_grpc_context)

        # Verifica que os filtros foram aplicados
        call_args = mock_mongodb_client.query_insights.call_args
        filters = call_args.kwargs.get('filters', call_args[0][0] if call_args[0] else {})
        assert 'created_at' in filters


class TestExecuteAnalysis:
    """Testes para o metodo ExecuteAnalysis."""

    @pytest.mark.asyncio
    async def test_execute_anomaly_detection(self, servicer, mock_grpc_context):
        """Testa execucao de deteccao de anomalias."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type='anomaly_detection',
            parameters={'metric_name': 'cpu_usage', 'threshold': '3.0'}
        )

        response = await servicer.ExecuteAnalysis(request, mock_grpc_context)

        assert response.analysis_id != ''
        assert 'anomaly_count' in response.results
        assert response.confidence > 0

    @pytest.mark.asyncio
    async def test_execute_trend_analysis(self, servicer, mock_grpc_context):
        """Testa execucao de analise de tendencia."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type='trend_analysis',
            parameters={'metric_name': 'memory_usage'}
        )

        response = await servicer.ExecuteAnalysis(request, mock_grpc_context)

        assert response.analysis_id != ''
        assert 'slope' in response.results

    @pytest.mark.asyncio
    async def test_execute_correlation_analysis(self, servicer, mock_grpc_context):
        """Testa execucao de analise de correlacao."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type='correlation',
            parameters={'metric1': 'cpu_usage', 'metric2': 'memory_usage'}
        )

        response = await servicer.ExecuteAnalysis(request, mock_grpc_context)

        assert response.analysis_id != ''
        assert 'correlation' in response.results

    @pytest.mark.asyncio
    async def test_execute_invalid_analysis_type(self, servicer, mock_grpc_context):
        """Testa erro com tipo de analise invalido."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type='invalid_type',
            parameters={}
        )

        response = await servicer.ExecuteAnalysis(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()

    @pytest.mark.asyncio
    async def test_execute_missing_metric_name(self, servicer, mock_grpc_context):
        """Testa erro quando metric_name nao e fornecido."""
        request = analyst_agent_pb2.ExecuteAnalysisRequest(
            analysis_type='anomaly_detection',
            parameters={}
        )

        response = await servicer.ExecuteAnalysis(request, mock_grpc_context)

        mock_grpc_context.set_code.assert_called()


class TestGetStatistics:
    """Testes para o metodo GetStatistics."""

    @pytest.mark.asyncio
    async def test_get_statistics_empty(self, servicer, mock_grpc_context):
        """Testa estatisticas vazias."""
        request = analyst_agent_pb2.GetStatisticsRequest()

        response = await servicer.GetStatistics(request, mock_grpc_context)

        assert response.avg_confidence == 0.0
        assert response.avg_impact == 0.0

    @pytest.mark.asyncio
    async def test_get_statistics_with_data(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa estatisticas com dados."""
        mock_mongodb_client.get_insight_statistics.return_value = {
            'by_type': {'ANOMALY': 10, 'OPERATIONAL': 5},
            'by_priority': {'HIGH': 8, 'MEDIUM': 7},
            'avg_confidence': 0.85,
            'avg_impact': 0.72,
            'total': 15
        }
        request = analyst_agent_pb2.GetStatisticsRequest()

        response = await servicer.GetStatistics(request, mock_grpc_context)

        assert response.avg_confidence == 0.85
        assert response.avg_impact == 0.72
        assert 'ANOMALY' in response.insights_by_type
        assert response.insights_by_type['ANOMALY'] == 10

    @pytest.mark.asyncio
    async def test_get_statistics_with_time_filter(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa estatisticas com filtro de tempo."""
        request = analyst_agent_pb2.GetStatisticsRequest(
            start_timestamp=1704067200000,
            end_timestamp=1704153600000
        )

        await servicer.GetStatistics(request, mock_grpc_context)

        mock_mongodb_client.get_insight_statistics.assert_called_once()


class TestHealthCheck:
    """Testes para o metodo HealthCheck."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, servicer, mock_grpc_context):
        """Testa health check com todos os componentes saudaveis."""
        request = analyst_agent_pb2.HealthCheckRequest()

        response = await servicer.HealthCheck(request, mock_grpc_context)

        assert response.healthy is True
        assert response.status == 'HEALTHY'

    @pytest.mark.asyncio
    async def test_health_check_mongodb_unhealthy(self, servicer, mock_mongodb_client, mock_grpc_context):
        """Testa health check com MongoDB nao saudavel."""
        mock_mongodb_client.client.admin.command.side_effect = Exception('Connection failed')
        request = analyst_agent_pb2.HealthCheckRequest()

        response = await servicer.HealthCheck(request, mock_grpc_context)

        assert response.healthy is False
        assert response.status == 'DEGRADED'

    @pytest.mark.asyncio
    async def test_health_check_redis_unhealthy(self, servicer, mock_redis_client, mock_grpc_context):
        """Testa health check com Redis nao saudavel."""
        mock_redis_client.client.ping.side_effect = Exception('Connection failed')
        request = analyst_agent_pb2.HealthCheckRequest()

        response = await servicer.HealthCheck(request, mock_grpc_context)

        assert response.healthy is False
        assert response.status == 'DEGRADED'


class TestInsightConversion:
    """Testes para conversao de insight para proto."""

    def test_insight_dict_to_proto(self, servicer, sample_insight_dict):
        """Testa conversao de dicionario para proto."""
        proto = servicer._insight_dict_to_proto(sample_insight_dict)

        assert proto.insight_id == sample_insight_dict['insight_id']
        assert proto.insight_type == 'ANOMALY'
        assert proto.priority == 'HIGH'
        assert proto.confidence_score == 0.92
        assert proto.impact_score == 0.85
        assert len(proto.recommendations) == 1
        assert proto.recommendations[0].action == 'Escalar recursos'

    def test_insight_dict_to_proto_empty_recommendations(self, servicer):
        """Testa conversao com lista de recomendacoes vazia."""
        insight_dict = {
            'insight_id': 'test-id',
            'insight_type': 'INFO',
            'priority': 'LOW',
            'title': 'Teste',
            'summary': 'Resumo',
            'recommendations': [],
            'confidence_score': 0.5,
            'impact_score': 0.3
        }

        proto = servicer._insight_dict_to_proto(insight_dict)

        assert len(proto.recommendations) == 0

    def test_insight_dict_to_proto_missing_fields(self, servicer):
        """Testa conversao com campos ausentes."""
        insight_dict = {
            'insight_id': 'test-id'
        }

        proto = servicer._insight_dict_to_proto(insight_dict)

        assert proto.insight_id == 'test-id'
        assert proto.version == '1.0.0'  # valor padrao
        assert proto.priority == 'MEDIUM'  # valor padrao
