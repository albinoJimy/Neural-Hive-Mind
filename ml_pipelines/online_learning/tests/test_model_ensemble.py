"""Testes para ModelEnsemble."""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock
from datetime import datetime

from ml_pipelines.online_learning.model_ensemble import ModelEnsemble
from ml_pipelines.online_learning.config import OnlineLearningConfig


@pytest.fixture
def config():
    """Configuração de teste."""
    return OnlineLearningConfig(
        ensemble_strategy="weighted_average",
        batch_model_weight=0.7,
        online_model_weight=0.3,
    )


@pytest.fixture
def mock_batch_model():
    """Mock do modelo batch."""
    model = Mock()
    model.predict_proba = Mock(
        return_value=np.array([[0.2, 0.8], [0.9, 0.1], [0.4, 0.6]])
    )
    model.predict = Mock(return_value=np.array([1, 0, 1]))
    return model


@pytest.fixture
def mock_online_learner():
    """Mock do learner online (IncrementalLearner)."""
    learner = Mock()
    learner.predict_proba = Mock(
        return_value=np.array([[0.3, 0.7], [0.8, 0.2], [0.5, 0.5]])
    )
    learner.is_fitted = True
    learner.model_version = "v1.0"
    return learner


@pytest.fixture
def ensemble(config, mock_batch_model, mock_online_learner):
    """ModelEnsemble para testes."""
    return ModelEnsemble(
        config=config,
        specialist_type="test_specialist",
        batch_model=mock_batch_model,
        online_learner=mock_online_learner,
    )


class TestModelEnsembleInitialization:
    """Testes de inicialização."""

    def test_init_weighted_average(self, config, mock_batch_model, mock_online_learner):
        """Testar inicialização com weighted_average."""
        ensemble = ModelEnsemble(
            config=config,
            specialist_type="test_specialist",
            batch_model=mock_batch_model,
            online_learner=mock_online_learner,
        )

        assert ensemble.config.ensemble_strategy == "weighted_average"
        metrics = ensemble.get_contribution_metrics()
        assert metrics["batch_weight"] == 0.7
        assert metrics["online_weight"] == 0.3

    def test_init_dynamic_routing(self, mock_batch_model, mock_online_learner):
        """Testar inicialização com dynamic_routing."""
        config = OnlineLearningConfig(ensemble_strategy="dynamic_routing")
        ensemble = ModelEnsemble(
            config=config,
            specialist_type="test_specialist",
            batch_model=mock_batch_model,
            online_learner=mock_online_learner,
        )

        assert ensemble.config.ensemble_strategy == "dynamic_routing"

    def test_init_stacking(self, mock_batch_model, mock_online_learner):
        """Testar inicialização com stacking."""
        config = OnlineLearningConfig(ensemble_strategy="stacking")
        ensemble = ModelEnsemble(
            config=config,
            specialist_type="test_specialist",
            batch_model=mock_batch_model,
            online_learner=mock_online_learner,
        )

        assert ensemble.config.ensemble_strategy == "stacking"


class TestPredictProba:
    """Testes de predict_proba."""

    def test_predict_proba_weighted_average(self, ensemble):
        """Testar predict_proba com weighted_average."""
        X = np.random.randn(3, 5)

        probas = ensemble.predict_proba(X)

        assert probas.shape == (3, 2)
        # Verificar que probabilidades somam 1
        np.testing.assert_array_almost_equal(probas.sum(axis=1), np.ones(3))

    def test_predict_proba_combines_models(
        self, ensemble, mock_batch_model, mock_online_learner
    ):
        """Testar que probabilidades são combinadas corretamente."""
        X = np.random.randn(3, 5)

        probas = ensemble.predict_proba(X)

        # Calcular manualmente: 0.7 * batch + 0.3 * online
        batch_proba = mock_batch_model.predict_proba.return_value
        online_proba = mock_online_learner.predict_proba.return_value
        expected = 0.7 * batch_proba + 0.3 * online_proba
        expected = expected / expected.sum(axis=1, keepdims=True)

        np.testing.assert_array_almost_equal(probas, expected)

    def test_predict_proba_batch_only(self, config, mock_batch_model):
        """Testar predict_proba apenas com modelo batch."""
        ensemble = ModelEnsemble(
            config=config,
            specialist_type="test_specialist",
            batch_model=mock_batch_model,
            online_learner=None,
        )
        X = np.random.randn(3, 5)

        probas = ensemble.predict_proba(X)

        np.testing.assert_array_equal(
            probas, mock_batch_model.predict_proba.return_value
        )


class TestPredict:
    """Testes de predict."""

    def test_predict_returns_class(self, ensemble):
        """Testar que predict retorna classe."""
        X = np.random.randn(3, 5)

        predictions = ensemble.predict(X)

        assert len(predictions) == 3
        assert all(p in [0, 1] for p in predictions)

    def test_predict_uses_argmax(self, ensemble):
        """Testar que predict usa argmax das probabilidades."""
        X = np.random.randn(3, 5)

        probas = ensemble.predict_proba(X)
        predictions = ensemble.predict(X)

        expected = np.argmax(probas, axis=1)
        np.testing.assert_array_equal(predictions, expected)


class TestUpdateWeights:
    """Testes de atualização de pesos."""

    def test_update_weights_valid(self, ensemble):
        """Testar atualização de pesos válida."""
        ensemble.update_weights(
            batch_accuracy=0.6, online_accuracy=0.4, smoothing_factor=1.0
        )

        metrics = ensemble.get_contribution_metrics()
        assert metrics["batch_weight"] == 0.6
        assert metrics["online_weight"] == 0.4

    def test_update_weights_normalizes(self, ensemble):
        """Testar que pesos são normalizados."""
        ensemble.update_weights(
            batch_accuracy=0.75, online_accuracy=0.25, smoothing_factor=1.0
        )

        metrics = ensemble.get_contribution_metrics()
        # 0.75 / (0.75 + 0.25) = 0.75
        assert abs(metrics["batch_weight"] - 0.75) < 0.01
        assert abs(metrics["online_weight"] - 0.25) < 0.01

    def test_update_weights_invalid(self, ensemble):
        """Testar atualização com accuracy zero."""
        # Não deve lançar erro, apenas não atualizar se total for zero
        ensemble.update_weights(
            batch_accuracy=0.0, online_accuracy=0.0, smoothing_factor=0.1
        )
        # Peso deve permanecer o mesmo
        metrics = ensemble.get_contribution_metrics()
        assert metrics["batch_weight"] == 0.7
        assert metrics["online_weight"] == 0.3


class TestContributionMetrics:
    """Testes de métricas de contribuição."""

    def test_get_contribution_metrics(self, ensemble):
        """Testar obtenção de métricas."""
        X = np.random.randn(10, 5)

        # Fazer algumas predições com diferentes inputs para evitar cache
        for i in range(5):
            ensemble.predict_proba(X + i)  # Diferente input para cada chamada

        metrics = ensemble.get_contribution_metrics()

        assert "batch_weight" in metrics
        assert "online_weight" in metrics
        assert "total_predictions" in metrics
        assert metrics["total_predictions"] == 5

    def test_contribution_metrics_empty(self, ensemble):
        """Testar métricas sem predições."""
        metrics = ensemble.get_contribution_metrics()

        assert metrics["total_predictions"] == 0


class TestDynamicRouting:
    """Testes de dynamic routing."""

    def test_dynamic_routing_high_confidence(
        self, mock_batch_model, mock_online_learner
    ):
        """Testar routing com alta confiança."""
        config = OnlineLearningConfig(ensemble_strategy="dynamic_routing")
        ensemble = ModelEnsemble(
            config=config,
            specialist_type="test_specialist",
            batch_model=mock_batch_model,
            online_learner=mock_online_learner,
        )

        # Configurar alta confiança no batch
        mock_batch_model.predict_proba.return_value = np.array(
            [
                [0.05, 0.95],  # Alta confiança
            ]
        )
        mock_online_learner.predict_proba.return_value = np.array(
            [
                [0.4, 0.6],  # Baixa confiança
            ]
        )

        X = np.random.randn(1, 5)
        probas = ensemble.predict_proba(X)

        # Deve dar mais peso ao batch por ter maior confiança
        assert probas.shape == (1, 2)


class TestCache:
    """Testes de cache."""

    def test_cache_predictions(self, ensemble):
        """Testar cache de predições."""
        X = np.random.randn(3, 5)

        # Primeira chamada
        probas1 = ensemble.predict_proba(X)

        # Segunda chamada com mesmos dados
        probas2 = ensemble.predict_proba(X)

        np.testing.assert_array_equal(probas1, probas2)

    def test_cache_invalidation(self, ensemble):
        """Testar invalidação de cache após clear_cache."""
        X = np.random.randn(3, 5)

        probas1 = ensemble.predict_proba(X)
        ensemble.clear_cache()
        probas2 = ensemble.predict_proba(X)

        # Resultados devem ser iguais mas cache foi limpo
        np.testing.assert_array_equal(probas1, probas2)
