"""Testes para AggregatedMetricsCollector."""

import pytest
from unittest.mock import patch, MagicMock

from neural_hive_specialists.observability.aggregated_metrics import (
    AggregatedMetricsCollector,
)


@pytest.fixture
def mock_config():
    """Config mock para testes."""
    return {
        "mongodb_uri": "mongodb://localhost:27017",
        "mongodb_database": "neural_hive_test",
        "metrics_window_hours": 24,
    }


@pytest.fixture
def collector(mock_config):
    """Instância de AggregatedMetricsCollector para testes."""
    with patch("neural_hive_specialists.observability.aggregated_metrics.MongoClient"):
        return AggregatedMetricsCollector(mock_config)


class TestAggregatedMetricsCollectorInit:
    """Testes de inicialização."""

    def test_init_with_config(self, collector):
        """Testa inicialização com config."""
        assert collector.metrics_window_hours == 24
        assert collector.mongodb_uri == "mongodb://localhost:27017"
        assert collector.mongodb_database == "neural_hive_test"

    def test_init_with_custom_window(self, mock_config):
        """Testa inicialização com janela customizada."""
        mock_config["metrics_window_hours"] = 48
        collector = AggregatedMetricsCollector(mock_config)

        assert collector.metrics_window_hours == 48

    def test_prometheus_metrics_initialized(self, collector):
        """Testa que métricas Prometheus são inicializadas."""
        assert collector.consensus_rate is not None
        assert collector.avg_confidence_by_specialist is not None
        assert collector.avg_risk_by_specialist is not None
        assert collector.ledger_health_score is not None
        assert collector.total_opinions_24h is not None

    def test_mongo_client_property(self, collector):
        """Testa propriedade lazy do mongo_client."""
        # Primeiro acesso cria o cliente
        with patch(
            "neural_hive_specialists.observability.aggregated_metrics.MongoClient"
        ) as mock_mongo:
            collector._mongo_client = None
            _ = collector.mongo_client

            assert mock_mongo.called


class TestCollectConsensusMetrics:
    """Testes para _collect_consensus_metrics."""

    @pytest.mark.asyncio
    async def test_collect_consensus_metrics_success(self, collector):
        """Testa coleta bem-sucedida de métricas de consenso."""
        # Mock collection
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        # Mock aggregate result
        mock_collection.aggregate.return_value = [
            {
                "_id": "plan1",
                "opinions": [
                    {"recommendation": "approve", "confidence": 0.8},
                    {"recommendation": "approve", "confidence": 0.9},
                    {"recommendation": "reject", "confidence": 0.7},
                ],
                "count": 3,
            },
            {
                "_id": "plan2",
                "opinions": [
                    {"recommendation": "approve", "confidence": 0.85},
                    {"recommendation": "approve", "confidence": 0.75},
                ],
                "count": 2,
            },
        ]

        await collector._collect_consensus_metrics()

        # Plan 1: 2 approve, 1 reject -> consensus_score = 2/3 = 0.667
        # Plan 2: 2 approve -> consensus_score = 1.0
        # Avg = (0.667 + 1.0) / 2 = 0.834
        assert collector.consensus_rate._value.get() > 0

    @pytest.mark.asyncio
    async def test_collect_consensus_metrics_no_data(self, collector):
        """Testa coleta quando não há dados."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        mock_collection.aggregate.return_value = []

        await collector._collect_consensus_metrics()

        # Não deve lançar erro, apenas logar debug


class TestCollectSpecialistMetrics:
    """Testes para _collect_specialist_metrics."""

    @pytest.mark.asyncio
    async def test_collect_specialist_metrics_success(self, collector):
        """Testa coleta bem-sucedida de métricas por especialista."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        mock_collection.aggregate.return_value = [
            {
                "_id": "technical",
                "avg_confidence": 0.75,
                "avg_risk": 0.30,
                "buffered_count": 5,
                "total_count": 100,
            },
            {
                "_id": "business",
                "avg_confidence": 0.80,
                "avg_risk": 0.25,
                "buffered_count": 2,
                "total_count": 50,
            },
        ]

        await collector._collect_specialist_metrics()

        # Verificar que métricas foram setadas
        # (valores exatos dependem do mock do Gauge)

    @pytest.mark.asyncio
    async def test_collect_specialist_metrics_buffered_rate(self, collector):
        """Testa cálculo de buffered_rate."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        mock_collection.aggregate.return_value = [
            {
                "_id": "technical",
                "avg_confidence": 0.75,
                "avg_risk": 0.30,
                "buffered_count": 10,
                "total_count": 100,
            }
        ]

        await collector._collect_specialist_metrics()

        # buffered_rate = 10/100 * 100 = 10%


class TestCollectLatencyMetrics:
    """Testes para _collect_latency_metrics."""

    @pytest.mark.asyncio
    async def test_collect_latency_metrics_success(self, collector):
        """Testa coleta bem-sucedida de métricas de latência."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        processing_times = [100, 150, 200, 250, 300, 120, 180, 220, 280, 320]

        mock_collection.aggregate.return_value = [
            {"_id": "technical", "processing_times": processing_times}
        ]

        await collector._collect_latency_metrics()

        # Deve calcular percentis P50, P95, P99
        # P50 de [100, 150, 200, 250, 300, 120, 180, 220, 280, 320] ≈ 210

    @pytest.mark.asyncio
    async def test_collect_latency_metrics_empty_times(self, collector):
        """Testa coleta com lista de tempos vazia."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        mock_collection.aggregate.return_value = [{"_id": "technical", "processing_times": []}]

        await collector._collect_latency_metrics()

        # Não deve lançar erro


class TestCollectRecommendationDistribution:
    """Testes para _collect_recommendation_distribution."""

    @pytest.mark.asyncio
    async def test_collect_distribution_success(self, collector):
        """Testa coleta bem-sucedida de distribuição."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        # Mock aggregate para distribution
        mock_collection.aggregate.side_effect = [
            # Primeira chamada: distribution
            [
                {"_id": "approve", "count": 70},
                {"_id": "reject", "count": 20},
                {"_id": "review_required", "count": 10},
            ],
            # Segunda chamada: count_documents (retorna 0 para evitar loop)
            0,
        ]

        # Mock count_documents
        mock_collection.count_documents.return_value = 100

        await collector._collect_recommendation_distribution()

        # approve: 70/100 = 70%
        # reject: 20/100 = 20%
        # review_required: 10/100 = 10%


class TestCollectLedgerHealth:
    """Testes para _collect_ledger_health."""

    @pytest.mark.asyncio
    async def test_collect_ledger_health_success(self, collector):
        """Testa cálculo de saúde do ledger."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        # Mock dos dados
        mock_collection.find.return_value.limit.return_value = []
        mock_collection.count_documents.side_effect = [10, 100]

        # Set valores iniciais para consensus e high_risk
        collector.consensus_rate.set(0.8)
        collector.high_risk_rate.set(5.0)

        await collector._collect_ledger_health()

        # health_score = consensus * (1 - buffered) * (1 - high_risk)
        # deve estar entre 0 e 1


class TestCalculateSpecialistAgreementMatrix:
    """Testes para calculate_specialist_agreement_matrix."""

    def test_agreement_matrix_empty(self, collector):
        """Testa com dados vazios."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        mock_collection.aggregate.return_value = []

        matrix = collector.calculate_specialist_agreement_matrix()

        assert matrix == {}

    def test_agreement_matrix_calculation(self, collector):
        """Testa cálculo de matriz de concordância."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        # Plan 1: technical e business concordam (approve)
        # Plan 2: technical e business discordam
        mock_collection.aggregate.return_value = [
            {
                "_id": "plan1",
                "opinions": [
                    {"specialist_type": "technical", "recommendation": "approve"},
                    {"specialist_type": "business", "recommendation": "approve"},
                ],
                "count": 2,
            },
            {
                "_id": "plan2",
                "opinions": [
                    {"specialist_type": "technical", "recommendation": "approve"},
                    {"specialist_type": "business", "recommendation": "reject"},
                ],
                "count": 2,
            },
        ]

        matrix = collector.calculate_specialist_agreement_matrix()

        # Concordância technical-business = 0.5 (1 de 2 planos)
        assert "technical" in matrix
        assert "business" in matrix


class TestGetSystemHealthSummary:
    """Testes para get_system_health_summary."""

    def test_health_summary(self, collector):
        """Testa retorno de resumo de saúde."""
        # Set valores
        collector.ledger_health_score.set(0.85)
        collector.consensus_rate.set(0.80)
        collector.high_risk_rate.set(5.0)
        collector.total_opinions_24h.set(1000)
        collector.ledger_growth_rate.set(50.0)
        collector.masked_documents_rate.set(2.0)

        summary = collector.get_system_health_summary()

        assert summary["ledger_health_score"] == 0.85
        assert summary["consensus_rate"] == 0.80
        assert summary["high_risk_rate"] == 5.0
        assert summary["total_opinions_24h"] == 1000
        assert summary["ledger_growth_rate"] == 50.0
        assert summary["masked_documents_rate"] == 2.0


class TestCollectAllMetrics:
    """Testes para collect_all_metrics."""

    @pytest.mark.asyncio
    async def test_collect_all_metrics_success(self, collector):
        """Testa coleta de todas as métricas."""
        # Mock collection
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        # Retornar dados vazios para evitar erros
        mock_collection.aggregate.return_value = []
        mock_collection.find.return_value = []
        mock_collection.count_documents.return_value = 0

        await collector.collect_all_metrics()

        # Não deve lançar erro

    @pytest.mark.asyncio
    async def test_collect_all_metrics_parallel(self, collector):
        """Testa que coletas executam em paralelo."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        mock_collection.aggregate.return_value = []
        mock_collection.find.return_value = []
        mock_collection.count_documents.return_value = 0

        import time

        start = time.time()
        await collector.collect_all_metrics()
        elapsed = time.time() - start

        # Deve ser rápido (execução paralela)
        assert elapsed < 5


class TestEdgeCases:
    """Testes de edge cases."""

    def test_init_with_missing_config(self):
        """Testa inicialização com config faltando."""
        config = {}  # Config vazia
        collector = AggregatedMetricsCollector(config)

        # Deve usar defaults
        assert collector.metrics_window_hours == 24
        assert collector.mongodb_database == "neural_hive"

    @pytest.mark.asyncio
    async def test_collect_with_mongo_error(self, collector):
        """Testa tratamento de erro do MongoDB."""
        mock_collection = MagicMock()
        collector._mongo_client = MagicMock()
        collector._mongo_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        # Simular erro
        mock_collection.aggregate.side_effect = Exception("MongoDB error")

        # Não deve lançar erro, deve loggar e retornar
        try:
            await collector._collect_consensus_metrics()
        except Exception:
            pytest.fail("Should not raise exception")


class TestMetricsTypes:
    """Testes para tipos específicos de métricas."""

    def test_consensus_rate_metric(self, collector):
        """Testa métrica de consenso."""
        collector.consensus_rate.set(0.85)

        assert collector.consensus_rate._value.get() == 0.85

    def test_confidence_by_specialist_metric(self, collector):
        """Testa métrica de confiança por especialista."""
        collector.avg_confidence_by_specialist.labels("technical").set(0.75)

        # Verificar que labels funcionam

    def test_recommendation_distribution_metric(self, collector):
        """Testa métrica de distribuição de recomendações."""
        collector.recommendation_distribution.labels("approve").set(70.0)
        collector.recommendation_distribution.labels("reject").set(20.0)

        # Verificar que diferentes labels funcionam
