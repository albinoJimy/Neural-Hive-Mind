"""
Testes para ABTestingSpecialist.

Testa carregamento de modelos A/B, seleção determinística de variante,
coleta de métricas e análise estatística.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from neural_hive_specialists.ab_testing_specialist import ABTestingSpecialist
from neural_hive_specialists.config import SpecialistConfig


@pytest.fixture
def ab_test_config():
    """Configuração para A/B testing specialist."""
    return SpecialistConfig(
        specialist_type="technical",
        service_name="test-ab-specialist",
        mlflow_tracking_uri="http://localhost:5000",
        mlflow_experiment_name="test-ab",
        mlflow_model_name="technical-model",
        mongodb_uri="mongodb://localhost:27017",
        redis_cluster_nodes="localhost:6379",
        neo4j_uri="bolt://localhost:7687",
        neo4j_password="test",
        enable_ab_testing=True,
        ab_test_model_a_name="model-baseline",
        ab_test_model_a_stage="Production",
        ab_test_model_b_name="model-challenger",
        ab_test_model_b_stage="Staging",
        ab_test_traffic_split=0.5,
        ab_test_hash_seed="test-seed-123",
        ab_test_minimum_sample_size=30,
    )


@pytest.fixture
def mock_mlflow_client():
    """Mock do MLflowClient."""
    with patch(
        "neural_hive_specialists.ab_testing_specialist.MLflowClient"
    ) as mock_client:
        client_instance = MagicMock()

        # Mock load_model para retornar modelos mock
        def mock_load_model(name, stage):
            model = MagicMock()
            model.predict = Mock(return_value=np.array([[0.7, 0.3]]))
            return model

        client_instance.load_model = Mock(side_effect=mock_load_model)

        # Mock get_model_metadata
        def mock_get_metadata(name, stage):
            version = "1" if name == "model-baseline" else "2"
            run_id = "run-baseline" if name == "model-baseline" else "run-challenger"
            return {"version": version, "run_id": run_id}

        client_instance.get_model_metadata = Mock(side_effect=mock_get_metadata)

        mock_client.return_value = client_instance
        yield client_instance


@pytest.fixture
def ab_testing_specialist(ab_test_config, mock_mlflow_client):
    """Instância de ABTestingSpecialist configurada."""
    with patch("neural_hive_specialists.base_specialist.LedgerWriter"), patch(
        "neural_hive_specialists.base_specialist.RedisCache"
    ), patch("neural_hive_specialists.base_specialist.FeatureStore"):
        specialist = ABTestingSpecialist(config=ab_test_config)
        specialist.mlflow_client = mock_mlflow_client

        # Mock dos modelos carregados
        specialist.model_a = MagicMock()
        specialist.model_b = MagicMock()

        specialist.model_a_metadata = {
            "name": "model-baseline",
            "stage": "Production",
            "version": "1",
            "run_id": "run-baseline",
        }

        specialist.model_b_metadata = {
            "name": "model-challenger",
            "stage": "Staging",
            "version": "2",
            "run_id": "run-challenger",
        }

        # Mock metrics
        specialist.metrics = MagicMock()
        specialist.metrics.ab_test_variant_usage_total = MagicMock()
        specialist.metrics.ab_test_variant_consensus_agreement = MagicMock()
        specialist.metrics.ab_test_variant_confidence_score = MagicMock()
        specialist.metrics.ab_test_variant_processing_time_seconds = MagicMock()
        specialist.metrics.ab_test_variant_recommendation_distribution = MagicMock()

        yield specialist


class TestABTestingSpecialistLoading:
    """Testes de carregamento de modelos A/B."""

    def test_load_both_models(self, ab_testing_specialist, mock_mlflow_client):
        """Testa carregamento de ambos os modelos A e B."""
        assert ab_testing_specialist.model_a is not None
        assert ab_testing_specialist.model_b is not None

    def test_model_metadata_loaded(self, ab_testing_specialist):
        """Testa que metadados foram carregados para ambos modelos."""
        assert ab_testing_specialist.model_a_metadata == {
            "name": "model-baseline",
            "stage": "Production",
            "version": "1",
            "run_id": "run-baseline",
        }

        assert ab_testing_specialist.model_b_metadata == {
            "name": "model-challenger",
            "stage": "Staging",
            "version": "2",
            "run_id": "run-challenger",
        }

    def test_fallback_to_single_model_when_model_b_fails(
        self, ab_test_config, mock_mlflow_client
    ):
        """Testa fallback para modelo único quando modelo B falha."""

        # Fazer modelo B falhar
        def failing_load_model(name, stage):
            if name == "model-challenger":
                raise Exception("Model B load failed")
            model = MagicMock()
            return model

        mock_mlflow_client.load_model = Mock(side_effect=failing_load_model)

        with patch("neural_hive_specialists.base_specialist.LedgerWriter"), patch(
            "neural_hive_specialists.base_specialist.RedisCache"
        ), patch("neural_hive_specialists.base_specialist.FeatureStore"):
            specialist = ABTestingSpecialist(config=ab_test_config)
            specialist.mlflow_client = mock_mlflow_client

            # Simular carregamento
            result = specialist._load_model()

            # Deve retornar modelo A
            assert result is not None


class TestVariantSelection:
    """Testes de seleção determinística de variante."""

    def test_deterministic_hash_selection(self, ab_testing_specialist):
        """Testa que hash é determinístico para mesmo plan_id."""
        plan_id = "test-plan-123"
        intent_id = "test-intent-456"

        # Executar seleção múltiplas vezes
        variant1, _ = ab_testing_specialist._select_model_for_request(
            plan_id, intent_id
        )
        variant2, _ = ab_testing_specialist._select_model_for_request(
            plan_id, intent_id
        )
        variant3, _ = ab_testing_specialist._select_model_for_request(
            plan_id, intent_id
        )

        # Deve retornar sempre a mesma variante
        assert variant1 == variant2 == variant3

    def test_different_plan_ids_different_variants(self, ab_testing_specialist):
        """Testa que diferentes plan_ids podem ter variantes diferentes."""
        # Com múltiplos plan_ids, devemos ter ao menos algumas diferenças
        variants = []
        for i in range(100):
            plan_id = f"test-plan-{i}"
            variant, _ = ab_testing_specialist._select_model_for_request(plan_id, "")
            variants.append(variant)

        # Deve ter ambas as variantes
        assert "model_a" in variants
        assert "model_b" in variants

    def test_traffic_split_distribution(self, ab_testing_specialist):
        """Testa que distribuição de tráfego respeita traffic_split."""
        # Com tráfego 50/50, distribuição deve ser aproximadamente igual
        variants = []
        for i in range(1000):
            plan_id = f"test-plan-{i}"
            variant, _ = ab_testing_specialist._select_model_for_request(plan_id, "")
            variants.append(variant)

        model_a_count = variants.count("model_a")
        model_b_count = variants.count("model_b")

        # Com 1000 amostras e split 0.5, esperamos ~500 cada
        # Permitir margem de erro de 10%
        assert 400 < model_a_count < 600
        assert 400 < model_b_count < 600

    def test_hash_value_normalized(self, ab_testing_specialist):
        """Testa que hash value está normalizado entre 0.0 e 1.0."""
        for i in range(100):
            plan_id = f"test-plan-{i}"
            hash_value = ab_testing_specialist._calculate_hash_value(plan_id, "")

            assert 0.0 <= hash_value <= 1.0

    def test_fallback_to_model_a_when_model_b_missing(self, ab_testing_specialist):
        """Testa fallback para modelo A quando modelo B não está disponível."""
        # Remover modelo B
        ab_testing_specialist.model_b = None

        variant, model = ab_testing_specialist._select_model_for_request(
            "test-plan", ""
        )

        assert variant == "model_a"
        assert model == ab_testing_specialist.model_a


class TestABTestingPrediction:
    """Testes de predição com A/B testing."""

    def test_prediction_includes_variant_metadata(self, ab_testing_specialist):
        """Testa que predição inclui metadados de variante."""
        # Mock super()._predict_with_model
        with patch.object(
            ABTestingSpecialist.__bases__[0], "_predict_with_model"
        ) as mock_predict:
            mock_predict.return_value = {
                "confidence_score": 0.8,
                "risk_score": 0.2,
                "recommendation": "approve",
            }

            cognitive_plan = {
                "plan_id": "test-plan-123",
                "intent_id": "test-intent-456",
                "description": "Test plan",
            }

            result = ab_testing_specialist._predict_with_model(cognitive_plan)

            # Verificar metadados
            assert result is not None
            assert "metadata" in result
            assert "ab_test_variant" in result["metadata"]
            assert result["metadata"]["ab_test_variant"] in ["model_a", "model_b"]
            assert "ab_test_model_name" in result["metadata"]
            assert "ab_test_model_version" in result["metadata"]
            assert "ab_test_model_run_id" in result["metadata"]
            assert "ab_test_traffic_split" in result["metadata"]
            assert "ab_test_hash_value" in result["metadata"]

    def test_metrics_published_after_prediction(self, ab_testing_specialist):
        """Testa que métricas são publicadas após predição."""
        with patch.object(
            ABTestingSpecialist.__bases__[0], "_predict_with_model"
        ) as mock_predict:
            mock_predict.return_value = {
                "confidence_score": 0.8,
                "risk_score": 0.2,
                "recommendation": "approve",
            }

            cognitive_plan = {"plan_id": "test-plan-123", "description": "Test plan"}

            ab_testing_specialist._predict_with_model(cognitive_plan)

            # Verificar chamadas de métricas
            ab_testing_specialist.metrics.observe_ab_test_variant_processing_time.assert_called()
            ab_testing_specialist.metrics.increment_ab_test_variant_usage.assert_called()
            ab_testing_specialist.metrics.observe_ab_test_variant_confidence.assert_called()
            ab_testing_specialist.metrics.observe_ab_test_variant_risk.assert_called()
            ab_testing_specialist.metrics.increment_ab_test_recommendation.assert_called()

    def test_fallback_on_prediction_failure(self, ab_testing_specialist):
        """Testa fallback quando predição falha."""
        # Mock para falhar na primeira tentativa (modelo B) e suceder no fallback (modelo A)
        call_count = [0]

        def mock_predict_with_failure(cognitive_plan):
            call_count[0] += 1
            if call_count[0] == 1:
                # Primeira chamada falha
                return None
            else:
                # Segunda chamada (fallback) sucede
                return {"confidence_score": 0.7, "recommendation": "approve"}

        with patch.object(
            ABTestingSpecialist.__bases__[0],
            "_predict_with_model",
            side_effect=mock_predict_with_failure,
        ):
            # Forçar seleção de modelo B
            ab_testing_specialist._select_model_for_request = Mock(
                return_value=("model_b", ab_testing_specialist.model_b)
            )

            cognitive_plan = {
                "plan_id": "test-plan-fallback",
                "description": "Test plan",
            }

            result = ab_testing_specialist._predict_with_model(cognitive_plan)

            # Deve ter tentado fallback
            assert result is not None


class TestABTestStatistics:
    """Testes de estatísticas de A/B testing."""

    def test_statistics_collection(self, ab_testing_specialist):
        """Testa coleta de estatísticas de ambas variantes."""

        # Mock dos metrics counters
        def mock_label_value(specialist_type, variant, *args):
            mock_val = MagicMock()
            if variant == "model_a":
                mock_val._value.get.return_value = 50
            else:
                mock_val._value.get.return_value = 45
            return mock_val

        ab_testing_specialist.metrics.ab_test_variant_usage_total.labels = Mock(
            side_effect=mock_label_value
        )

        # Mock histograms para confidence e latency
        def mock_histogram(specialist_type, variant):
            mock_hist = MagicMock()
            mock_hist._sum.get.return_value = 40.0 if variant == "model_a" else 36.0
            mock_hist._count.get.return_value = 50 if variant == "model_a" else 45
            return mock_hist

        ab_testing_specialist.metrics.ab_test_variant_confidence_score.labels = Mock(
            side_effect=mock_histogram
        )
        ab_testing_specialist.metrics.ab_test_variant_processing_time_seconds.labels = (
            Mock(side_effect=mock_histogram)
        )

        # Mock agreement
        def mock_agreement(specialist_type, variant):
            mock_val = MagicMock()
            mock_val._value.get.return_value = 0.85 if variant == "model_a" else 0.82
            return mock_val

        ab_testing_specialist.metrics.ab_test_variant_consensus_agreement.labels = Mock(
            side_effect=mock_agreement
        )

        # Mock recommendation distribution
        def mock_recommendation(specialist_type, variant, recommendation):
            mock_val = MagicMock()
            if recommendation == "approve":
                mock_val._value.get.return_value = 40 if variant == "model_a" else 35
            else:
                mock_val._value.get.return_value = 10 if variant == "model_a" else 10
            return mock_val

        ab_testing_specialist.metrics.ab_test_variant_recommendation_distribution.labels = Mock(
            side_effect=mock_recommendation
        )

        stats = ab_testing_specialist.get_ab_test_statistics()

        # Verificar estrutura
        assert "model_a" in stats
        assert "model_b" in stats
        assert "statistical_significance" in stats
        assert "recommendation" in stats

        # Verificar dados de model_a
        assert stats["model_a"]["sample_size"] == 50
        assert stats["model_a"]["avg_confidence"] == 0.8  # 40/50

        # Verificar dados de model_b
        assert stats["model_b"]["sample_size"] == 45
        assert stats["model_b"]["avg_confidence"] == 0.8  # 36/45

    def test_statistical_significance_with_sufficient_samples(
        self, ab_testing_specialist
    ):
        """Testa cálculo de significância estatística com amostras suficientes."""

        # Mock para amostras suficientes (>30 cada)
        def mock_label_value(specialist_type, variant, *args):
            mock_val = MagicMock()
            mock_val._value.get.return_value = 100  # >30
            return mock_val

        ab_testing_specialist.metrics.ab_test_variant_usage_total.labels = Mock(
            side_effect=mock_label_value
        )

        # Mock histograms
        def mock_histogram(specialist_type, variant):
            mock_hist = MagicMock()
            mock_hist._sum.get.return_value = 80.0 if variant == "model_a" else 90.0
            mock_hist._count.get.return_value = 100
            return mock_hist

        ab_testing_specialist.metrics.ab_test_variant_confidence_score.labels = Mock(
            side_effect=mock_histogram
        )
        ab_testing_specialist.metrics.ab_test_variant_processing_time_seconds.labels = (
            Mock(side_effect=mock_histogram)
        )

        # Mock agreement
        def mock_agreement(specialist_type, variant):
            mock_val = MagicMock()
            mock_val._value.get.return_value = 0.85
            return mock_val

        ab_testing_specialist.metrics.ab_test_variant_consensus_agreement.labels = Mock(
            side_effect=mock_agreement
        )

        # Mock recommendation distribution
        def mock_recommendation(specialist_type, variant, recommendation):
            mock_val = MagicMock()
            if recommendation == "approve":
                mock_val._value.get.return_value = 80 if variant == "model_a" else 90
            else:
                mock_val._value.get.return_value = 20 if variant == "model_a" else 10
            return mock_val

        ab_testing_specialist.metrics.ab_test_variant_recommendation_distribution.labels = Mock(
            side_effect=mock_recommendation
        )

        stats = ab_testing_specialist.get_ab_test_statistics()

        # Verificar significância calculada
        assert "p_value" in stats["statistical_significance"]
        assert "is_significant" in stats["statistical_significance"]

    def test_insufficient_samples_recommendation(self, ab_testing_specialist):
        """Testa recomendação quando amostras insuficientes."""

        # Mock para amostras insuficientes (<30)
        def mock_label_value(specialist_type, variant, *args):
            mock_val = MagicMock()
            mock_val._value.get.return_value = 10  # <30
            return mock_val

        ab_testing_specialist.metrics.ab_test_variant_usage_total.labels = Mock(
            side_effect=mock_label_value
        )

        # Mock outros metrics
        ab_testing_specialist.metrics.ab_test_variant_confidence_score.labels = Mock(
            return_value=MagicMock(
                _sum=MagicMock(get=Mock(return_value=8.0)),
                _count=MagicMock(get=Mock(return_value=10)),
            )
        )
        ab_testing_specialist.metrics.ab_test_variant_processing_time_seconds.labels = (
            Mock(
                return_value=MagicMock(
                    _sum=MagicMock(get=Mock(return_value=5.0)),
                    _count=MagicMock(get=Mock(return_value=10)),
                )
            )
        )
        ab_testing_specialist.metrics.ab_test_variant_consensus_agreement.labels = Mock(
            return_value=MagicMock(_value=MagicMock(get=Mock(return_value=0.8)))
        )
        ab_testing_specialist.metrics.ab_test_variant_recommendation_distribution.labels = Mock(
            return_value=MagicMock(_value=MagicMock(get=Mock(return_value=5)))
        )

        stats = ab_testing_specialist.get_ab_test_statistics()

        # Deve recomendar continuar testando
        assert "insufficient_data" in stats["recommendation"]


class TestABTestingErrorHandling:
    """Testes de tratamento de erros."""

    def test_missing_plan_id_generates_temporary_id(self, ab_testing_specialist):
        """Testa que plan_id temporário é gerado quando faltando."""
        with patch.object(
            ABTestingSpecialist.__bases__[0], "_predict_with_model"
        ) as mock_predict:
            mock_predict.return_value = {
                "confidence_score": 0.8,
                "recommendation": "approve",
            }

            # Plano sem plan_id
            cognitive_plan = {"description": "Test plan without ID"}

            result = ab_testing_specialist._predict_with_model(cognitive_plan)

            # Deve funcionar sem erros
            assert result is not None

    def test_error_handling_in_statistics_collection(self, ab_testing_specialist):
        """Testa tratamento de erro na coleta de estatísticas."""
        # Fazer métricas falharem
        ab_testing_specialist.metrics.ab_test_variant_usage_total.labels = Mock(
            side_effect=Exception("Metrics error")
        )

        stats = ab_testing_specialist.get_ab_test_statistics()

        # Deve retornar estrutura de erro
        assert "error" in stats or stats["model_a"]["sample_size"] == 0


@pytest.mark.integration
class TestABTestingIntegration:
    """Testes de integração end-to-end."""

    def test_full_ab_testing_flow(self, ab_testing_specialist):
        """Testa fluxo completo de A/B testing."""
        with patch.object(
            ABTestingSpecialist.__bases__[0], "_predict_with_model"
        ) as mock_predict:
            mock_predict.return_value = {
                "confidence_score": 0.85,
                "risk_score": 0.15,
                "recommendation": "approve",
                "reasoning_factors": [],
            }

            cognitive_plan = {
                "plan_id": "integration-test-plan",
                "intent_id": "integration-test-intent",
                "description": "Integration test plan",
                "complexity_score": 0.5,
            }

            result = ab_testing_specialist._predict_with_model(cognitive_plan)

            # Verificar resultado completo
            assert result is not None
            assert "confidence_score" in result
            assert "metadata" in result
            assert "ab_test_variant" in result["metadata"]
            assert "ab_test_model_version" in result["metadata"]
            assert "ab_test_model_run_id" in result["metadata"]

            # Verificar que variante é consistente
            variant = result["metadata"]["ab_test_variant"]
            assert variant in ["model_a", "model_b"]

            # Executar novamente com mesmo plan_id
            result2 = ab_testing_specialist._predict_with_model(cognitive_plan)

            # Deve ter a mesma variante (determinístico)
            assert result2["metadata"]["ab_test_variant"] == variant
