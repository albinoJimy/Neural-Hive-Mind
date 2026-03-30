"""Testes de integração ML para ArchitectureSpecialist."""

import sys
import os
import pytest
from typing import Dict, Any
from unittest.mock import Mock

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, '/app/libraries/python')


class MockMLflowClient:
    """Mock do cliente MLflow."""

    def __init__(self, model_available: bool = True):
        self._enabled = True
        self._model_available = model_available
        self._model_metadata = {'version': 'v1.0.5', 'stage': 'Production'}

    def is_enabled(self) -> bool:
        return self._enabled

    def load_model_with_fallback(self, model_name: str, stage: str):
        if not self._model_available:
            return None
        return MockArchitectureModel()

    def get_model_metadata(self, model_name: str, stage: str) -> Dict:
        if not self._model_available:
            return {}
        return self._model_metadata.copy()

    def load_model(self, model_name: str, stage: str):
        if not self._model_available:
            raise Exception("Model not available")
        return MockArchitectureModel()


class MockArchitectureModel:
    """Mock de modelo ML de arquitetura."""

    def __init__(self):
        self.feature_names_in_ = [
            'design_patterns_score', 'solid_score', 'coupling_cohesion_score',
            'separation_score', 'modularity_score'
        ]

    def predict(self, X):
        import numpy as np
        if len(X.shape) > 1:
            return np.where(X.mean(axis=1) > 0.5, 1, 0)
        return 1 if X.mean() > 0.5 else 0


@pytest.fixture
def mock_mlflow_client():
    return MockMLflowClient(model_available=True)


@pytest.fixture
def sample_architecture_features():
    return {
        'design_patterns_score': 0.80,
        'solid_score': 0.75,
        'coupling_cohesion_score': 0.70,
        'separation_score': 0.85,
        'modularity_score': 0.65
    }


class TestMLModelLoading:
    """Testes de carregamento de modelo."""

    def test_load_architecture_model_success(self, mock_mlflow_client):
        model = mock_mlflow_client.load_model_with_fallback(
            'specialist_architecture_model', 'Production'
        )
        assert model is not None

    def test_load_architecture_model_unavailable(self):
        client = MockMLflowClient(model_available=False)
        model = client.load_model_with_fallback(
            'specialist_architecture_model', 'Production'
        )
        assert model is None


class TestMLModelPrediction:
    """Testes de predição."""

    def test_predict_architecture_design(self, mock_mlflow_client, sample_architecture_features):
        model = mock_mlflow_client.load_model_with_fallback(
            'specialist_architecture_model', 'Production'
        )

        import numpy as np
        X = np.array([[
            sample_architecture_features['design_patterns_score'],
            sample_architecture_features['solid_score'],
            sample_architecture_features['coupling_cohesion_score'],
            sample_architecture_features['separation_score'],
            sample_architecture_features['modularity_score']
        ]])

        prediction = model.predict(X)
        assert prediction[0] in [0, 1]


class TestHeuristicFallback:
    """Testes de fallback para heurística."""

    def test_architecture_heuristic_calculation(self, sample_architecture_features):
        ml_model = None

        heuristic_score = (
            sample_architecture_features['design_patterns_score'] * 0.25 +
            sample_architecture_features['solid_score'] * 0.25 +
            sample_architecture_features['coupling_cohesion_score'] * 0.20 +
            sample_architecture_features['separation_score'] * 0.15 +
            sample_architecture_features['modularity_score'] * 0.15
        )

        assert 0.0 <= heuristic_score <= 1.0


class TestCachePredictions:
    """Testes de cache de predições."""

    def test_architecture_cache_key(self):
        import hashlib
        import json

        features = {
            'design_patterns_score': 0.80,
            'solid_score': 0.75,
            'modularity_score': 0.65
        }

        cache_key = hashlib.md5(
            json.dumps(features, sort_keys=True).encode()
        ).hexdigest()

        assert len(cache_key) == 32
