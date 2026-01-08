"""Testes para IncrementalLearner."""

import pytest
import numpy as np
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

from ml_pipelines.online_learning.incremental_learner import IncrementalLearner
from ml_pipelines.online_learning.config import OnlineLearningConfig


@pytest.fixture
def config():
    """Configuração de teste."""
    return OnlineLearningConfig(
        online_learning_enabled=True,
        incremental_algorithm='sgd',
        mini_batch_size=16,
        learning_rate=0.01,
        regularization_alpha=0.0001
    )


@pytest.fixture
def learner(config):
    """IncrementalLearner para testes."""
    return IncrementalLearner(
        config=config,
        specialist_type='feasibility'
    )


@pytest.fixture
def sample_data():
    """Dados de amostra para treinamento."""
    np.random.seed(42)
    X = np.random.randn(100, 10)
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    return X, y


class TestIncrementalLearnerInitialization:
    """Testes de inicialização."""

    def test_init_sgd(self, config):
        """Testar inicialização com SGD."""
        learner = IncrementalLearner(config, 'feasibility')
        assert learner.specialist_type == 'feasibility'
        assert learner.algorithm == 'sgd'

    def test_init_passive_aggressive(self):
        """Testar inicialização com PassiveAggressive."""
        config = OnlineLearningConfig(incremental_algorithm='passive_aggressive')
        learner = IncrementalLearner(config, 'risk')
        assert learner.algorithm == 'passive_aggressive'

    def test_init_perceptron(self):
        """Testar inicialização com Perceptron."""
        config = OnlineLearningConfig(incremental_algorithm='perceptron')
        learner = IncrementalLearner(config, 'cost')
        assert learner.algorithm == 'perceptron'


class TestPartialFit:
    """Testes de partial_fit."""

    def test_partial_fit_basic(self, learner, sample_data):
        """Testar partial_fit básico."""
        X, y = sample_data
        batch_X = X[:16]
        batch_y = y[:16]

        result = learner.partial_fit(batch_X, batch_y, classes=[0, 1])

        assert result['success'] is True
        assert result['samples_processed'] == 16
        assert 'loss' in result

    def test_partial_fit_updates_counter(self, learner, sample_data):
        """Testar que partial_fit incrementa contador."""
        X, y = sample_data

        initial_updates = learner.updates_count
        learner.partial_fit(X[:16], y[:16], classes=[0, 1])

        assert learner.updates_count == initial_updates + 1

    def test_partial_fit_multiple_batches(self, learner, sample_data):
        """Testar múltiplos batches."""
        X, y = sample_data

        for i in range(5):
            start = i * 16
            end = start + 16
            learner.partial_fit(X[start:end], y[start:end], classes=[0, 1])

        assert learner.updates_count == 5

    def test_partial_fit_with_sample_weight(self, learner, sample_data):
        """Testar partial_fit com pesos."""
        X, y = sample_data
        weights = np.ones(16) * 0.5

        result = learner.partial_fit(
            X[:16], y[:16],
            classes=[0, 1],
            sample_weight=weights
        )

        assert result['success'] is True


class TestPredict:
    """Testes de predição."""

    def test_predict_after_fit(self, learner, sample_data):
        """Testar predição após treinamento."""
        X, y = sample_data

        # Treinar
        learner.partial_fit(X[:80], y[:80], classes=[0, 1])

        # Predizer
        predictions = learner.predict(X[80:])

        assert len(predictions) == 20
        assert all(p in [0, 1] for p in predictions)

    def test_predict_proba(self, learner, sample_data):
        """Testar predict_proba."""
        X, y = sample_data

        learner.partial_fit(X[:80], y[:80], classes=[0, 1])
        probas = learner.predict_proba(X[80:])

        assert probas.shape == (20, 2)
        assert np.allclose(probas.sum(axis=1), 1.0)

    def test_predict_without_training(self, learner, sample_data):
        """Testar predição sem treinamento."""
        X, _ = sample_data

        with pytest.raises(Exception):
            learner.predict(X[:10])


class TestCheckpoint:
    """Testes de checkpoint."""

    def test_save_checkpoint(self, learner, sample_data):
        """Testar salvamento de checkpoint."""
        X, y = sample_data
        learner.partial_fit(X[:32], y[:32], classes=[0, 1])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = learner.save_checkpoint(tmpdir)

            assert os.path.exists(path)
            assert path.endswith('.pkl')

    def test_load_checkpoint(self, learner, sample_data):
        """Testar carregamento de checkpoint."""
        X, y = sample_data
        learner.partial_fit(X[:32], y[:32], classes=[0, 1])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = learner.save_checkpoint(tmpdir)

            # Criar novo learner e carregar
            new_learner = IncrementalLearner(
                learner.config,
                'feasibility'
            )
            new_learner.load_checkpoint(path)

            # Verificar que predições são iguais
            pred1 = learner.predict(X[32:48])
            pred2 = new_learner.predict(X[32:48])

            np.testing.assert_array_equal(pred1, pred2)


class TestConvergenceMetrics:
    """Testes de métricas de convergência."""

    def test_get_convergence_metrics(self, learner, sample_data):
        """Testar obtenção de métricas."""
        X, y = sample_data

        # Treinar alguns batches
        for i in range(5):
            learner.partial_fit(X[i*16:(i+1)*16], y[i*16:(i+1)*16], classes=[0, 1])

        metrics = learner.get_convergence_metrics()

        assert 'average_loss' in metrics
        assert 'loss_history' in metrics
        assert 'updates_count' in metrics
        assert metrics['updates_count'] == 5

    def test_convergence_rate(self, learner, sample_data):
        """Testar cálculo de taxa de convergência."""
        X, y = sample_data

        # Treinar múltiplos batches
        for i in range(10):
            learner.partial_fit(X[i*10:(i+1)*10], y[i*10:(i+1)*10], classes=[0, 1])

        metrics = learner.get_convergence_metrics()

        assert 'convergence_rate' in metrics
        assert isinstance(metrics['convergence_rate'], float)


class TestScaler:
    """Testes do scaler."""

    def test_scaler_initialization(self, learner, sample_data):
        """Testar inicialização do scaler."""
        X, y = sample_data

        learner.partial_fit(X[:32], y[:32], classes=[0, 1])

        assert learner.scaler is not None

    def test_scaler_transforms_data(self, learner, sample_data):
        """Testar que scaler normaliza dados."""
        X, y = sample_data

        learner.partial_fit(X[:32], y[:32], classes=[0, 1])

        # Verificar que scaler está funcionando
        scaled = learner.scaler.transform(X[:10])
        assert scaled.shape == (10, 10)
