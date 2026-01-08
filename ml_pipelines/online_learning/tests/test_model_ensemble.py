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
        ensemble_strategy='weighted_average',
        batch_model_weight=0.7,
        online_model_weight=0.3
    )


@pytest.fixture
def mock_batch_model():
    """Mock do modelo batch."""
    model = Mock()
    model.predict_proba = Mock(return_value=np.array([
        [0.2, 0.8],
        [0.9, 0.1],
        [0.4, 0.6]
    ]))
    model.predict = Mock(return_value=np.array([1, 0, 1]))
    return model


@pytest.fixture
def mock_online_model():
    """Mock do modelo online."""
    model = Mock()
    model.predict_proba = Mock(return_value=np.array([
        [0.3, 0.7],
        [0.8, 0.2],
        [0.5, 0.5]
    ]))
    model.predict = Mock(return_value=np.array([1, 0, 0]))
    return model


@pytest.fixture
def ensemble(config, mock_batch_model, mock_online_model):
    """ModelEnsemble para testes."""
    return ModelEnsemble(
        config=config,
        batch_model=mock_batch_model,
        online_model=mock_online_model
    )


class TestModelEnsembleInitialization:
    """Testes de inicialização."""

    def test_init_weighted_average(self, config, mock_batch_model, mock_online_model):
        """Testar inicialização com weighted_average."""
        ensemble = ModelEnsemble(config, mock_batch_model, mock_online_model)

        assert ensemble.strategy == 'weighted_average'
        assert ensemble.batch_weight == 0.7
        assert ensemble.online_weight == 0.3

    def test_init_dynamic_routing(self, mock_batch_model, mock_online_model):
        """Testar inicialização com dynamic_routing."""
        config = OnlineLearningConfig(ensemble_strategy='dynamic_routing')
        ensemble = ModelEnsemble(config, mock_batch_model, mock_online_model)

        assert ensemble.strategy == 'dynamic_routing'

    def test_init_stacking(self, mock_batch_model, mock_online_model):
        """Testar inicialização com stacking."""
        config = OnlineLearningConfig(ensemble_strategy='stacking')
        ensemble = ModelEnsemble(config, mock_batch_model, mock_online_model)

        assert ensemble.strategy == 'stacking'


class TestPredictProba:
    """Testes de predict_proba."""

    def test_predict_proba_weighted_average(self, ensemble):
        """Testar predict_proba com weighted_average."""
        X = np.random.randn(3, 5)

        probas = ensemble.predict_proba(X)

        assert probas.shape == (3, 2)
        # Verificar que probabilidades somam 1
        np.testing.assert_array_almost_equal(
            probas.sum(axis=1),
            np.ones(3)
        )

    def test_predict_proba_combines_models(self, ensemble, mock_batch_model, mock_online_model):
        """Testar que probabilidades são combinadas corretamente."""
        X = np.random.randn(3, 5)

        probas = ensemble.predict_proba(X)

        # Calcular manualmente: 0.7 * batch + 0.3 * online
        batch_proba = mock_batch_model.predict_proba.return_value
        online_proba = mock_online_model.predict_proba.return_value
        expected = 0.7 * batch_proba + 0.3 * online_proba
        expected = expected / expected.sum(axis=1, keepdims=True)

        np.testing.assert_array_almost_equal(probas, expected)

    def test_predict_proba_batch_only(self, config, mock_batch_model):
        """Testar predict_proba apenas com modelo batch."""
        ensemble = ModelEnsemble(config, mock_batch_model, online_model=None)
        X = np.random.randn(3, 5)

        probas = ensemble.predict_proba(X)

        np.testing.assert_array_equal(
            probas,
            mock_batch_model.predict_proba.return_value
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
        ensemble.update_weights(batch_weight=0.6, online_weight=0.4)

        assert ensemble.batch_weight == 0.6
        assert ensemble.online_weight == 0.4

    def test_update_weights_normalizes(self, ensemble):
        """Testar que pesos são normalizados."""
        ensemble.update_weights(batch_weight=3.0, online_weight=2.0)

        assert ensemble.batch_weight == 0.6
        assert ensemble.online_weight == 0.4

    def test_update_weights_invalid(self, ensemble):
        """Testar atualização com pesos inválidos."""
        with pytest.raises(ValueError):
            ensemble.update_weights(batch_weight=-0.1, online_weight=1.1)


class TestContributionMetrics:
    """Testes de métricas de contribuição."""

    def test_get_contribution_metrics(self, ensemble):
        """Testar obtenção de métricas."""
        X = np.random.randn(10, 5)

        # Fazer algumas predições
        for _ in range(5):
            ensemble.predict_proba(X)

        metrics = ensemble.get_contribution_metrics()

        assert 'batch_weight' in metrics
        assert 'online_weight' in metrics
        assert 'prediction_count' in metrics
        assert metrics['prediction_count'] == 5

    def test_contribution_metrics_empty(self, ensemble):
        """Testar métricas sem predições."""
        metrics = ensemble.get_contribution_metrics()

        assert metrics['prediction_count'] == 0


class TestDynamicRouting:
    """Testes de dynamic routing."""

    def test_dynamic_routing_high_confidence(self, mock_batch_model, mock_online_model):
        """Testar routing com alta confiança."""
        config = OnlineLearningConfig(ensemble_strategy='dynamic_routing')
        ensemble = ModelEnsemble(config, mock_batch_model, mock_online_model)

        # Configurar alta confiança no batch
        mock_batch_model.predict_proba.return_value = np.array([
            [0.05, 0.95],  # Alta confiança
        ])
        mock_online_model.predict_proba.return_value = np.array([
            [0.4, 0.6],  # Baixa confiança
        ])

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
        """Testar invalidação de cache após update_weights."""
        X = np.random.randn(3, 5)

        probas1 = ensemble.predict_proba(X)
        ensemble.update_weights(0.5, 0.5)
        probas2 = ensemble.predict_proba(X)

        # Resultados devem ser diferentes após mudar pesos
        assert not np.array_equal(probas1, probas2)
