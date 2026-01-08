"""Configurações compartilhadas para testes de online learning."""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock

from ml_pipelines.online_learning.config import OnlineLearningConfig


@pytest.fixture(scope="session")
def default_config():
    """Configuração padrão para testes."""
    return OnlineLearningConfig(
        online_learning_enabled=True,
        incremental_algorithm='sgd',
        mini_batch_size=32,
        learning_rate=0.01,
        regularization_alpha=0.0001,
        shadow_accuracy_threshold=0.02,
        shadow_max_latency_ratio=1.5,
        shadow_max_kl_divergence=0.1,
        shadow_min_samples=50,
        rollback_enabled=True,
        rollback_f1_drop_threshold=0.05,
        rollback_accuracy_drop_threshold=0.03,
        rollback_latency_increase_threshold=1.5,
        max_versions_to_keep=10,
        rollout_stages=[0.1, 0.5, 1.0],
        rollout_stage_duration_minutes=60,
        ensemble_strategy='weighted_average',
        batch_model_weight=0.7,
        online_model_weight=0.3
    )


@pytest.fixture
def mock_mongodb_client():
    """Mock do cliente MongoDB."""
    client = MagicMock()
    db = MagicMock()
    collection = MagicMock()

    client.__getitem__ = Mock(return_value=db)
    db.__getitem__ = Mock(return_value=collection)

    collection.find = Mock(return_value=[])
    collection.find_one = Mock(return_value=None)
    collection.insert_one = Mock(return_value=Mock(inserted_id='test_id'))
    collection.update_one = Mock(return_value=Mock(modified_count=1))
    collection.delete_one = Mock(return_value=Mock(deleted_count=1))

    return client


@pytest.fixture
def mock_mlflow_client():
    """Mock do cliente MLflow."""
    client = MagicMock()

    # Mock de busca de modelos
    client.search_model_versions = Mock(return_value=[])
    client.get_model_version = Mock(return_value=None)
    client.transition_model_version_stage = Mock()
    client.create_model_version = Mock(return_value=Mock(version='1'))

    return client


@pytest.fixture
def sample_features():
    """Features de amostra para testes."""
    np.random.seed(42)
    return np.random.randn(100, 10)


@pytest.fixture
def sample_labels():
    """Labels de amostra para testes."""
    np.random.seed(42)
    return np.random.randint(0, 2, 100)


@pytest.fixture
def sample_batch_model():
    """Modelo batch simulado."""
    model = Mock()

    def predict_proba(X):
        np.random.seed(42)
        n_samples = X.shape[0]
        probs = np.random.uniform(0.3, 0.7, (n_samples, 2))
        probs = probs / probs.sum(axis=1, keepdims=True)
        return probs

    def predict(X):
        probs = predict_proba(X)
        return np.argmax(probs, axis=1)

    model.predict_proba = predict_proba
    model.predict = predict

    return model


@pytest.fixture
def sample_online_model():
    """Modelo online simulado."""
    model = Mock()

    def predict_proba(X):
        np.random.seed(43)  # Seed diferente
        n_samples = X.shape[0]
        probs = np.random.uniform(0.3, 0.7, (n_samples, 2))
        probs = probs / probs.sum(axis=1, keepdims=True)
        return probs

    def predict(X):
        probs = predict_proba(X)
        return np.argmax(probs, axis=1)

    model.predict_proba = predict_proba
    model.predict = predict

    return model


@pytest.fixture(autouse=True)
def reset_prometheus_metrics():
    """Resetar métricas Prometheus entre testes."""
    # Prometheus metrics são singletons, então precisamos
    # ter cuidado com estado entre testes
    yield
    # Cleanup após cada teste se necessário


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Diretório temporário para checkpoints."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    return str(checkpoint_dir)
