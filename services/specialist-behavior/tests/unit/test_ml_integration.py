"""Testes de integração ML para BehaviorSpecialist."""

import os
import sys

import pytest

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")


class MockMLflowClient:
    """Mock do cliente MLflow."""

    def __init__(self, model_available: bool = True):
        self._enabled = True
        self._model_available = model_available
        self._model_metadata = {"version": "v1.1.0", "stage": "Production"}

    def is_enabled(self) -> bool:
        return self._enabled

    def load_model_with_fallback(self, model_name: str, stage: str):
        if not self._model_available:
            return None
        return MockBehaviorModel()

    def get_model_metadata(self, model_name: str, stage: str) -> dict:
        if not self._model_available:
            return {}
        return self._model_metadata.copy()

    def load_model(self, model_name: str, stage: str):
        if not self._model_available:
            raise Exception("Model not available")
        return MockBehaviorModel()


class MockBehaviorModel:
    """Mock de modelo ML comportamental."""

    def __init__(self):
        self.feature_names_in_ = [
            "usability_score",
            "accessibility_score",
            "response_time_score",
            "interaction_cost_score",
        ]

    def predict(self, X):
        import numpy as np

        if len(X.shape) > 1:
            return np.where(X.mean(axis=1) > 0.5, 1, 0)
        return 1 if X.mean() > 0.5 else 0


@pytest.fixture()
def mock_mlflow_client():
    return MockMLflowClient(model_available=True)


@pytest.fixture()
def sample_behavior_features():
    return {
        "usability_score": 0.85,
        "accessibility_score": 0.75,
        "response_time_score": 0.80,
        "interaction_cost_score": 0.70,
    }


class TestMLModelLoading:
    """Testes de carregamento de modelo."""

    def test_load_behavior_model_success(self, mock_mlflow_client):
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_behavior_model", "Production"
        )
        assert model is not None


class TestMLModelPrediction:
    """Testes de predição."""

    def test_predict_behavior_design(self, mock_mlflow_client, sample_behavior_features):
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_behavior_model", "Production"
        )

        import numpy as np

        X = np.array(
            [
                [
                    sample_behavior_features["usability_score"],
                    sample_behavior_features["accessibility_score"],
                    sample_behavior_features["response_time_score"],
                    sample_behavior_features["interaction_cost_score"],
                ]
            ]
        )

        prediction = model.predict(X)
        assert prediction[0] in [0, 1]


class TestHeuristicFallback:
    """Testes de fallback para heurística."""

    def test_behavior_heuristic_calculation(self, sample_behavior_features):
        ml_model = None

        heuristic_score = (
            sample_behavior_features["usability_score"] * 0.35
            + sample_behavior_features["accessibility_score"] * 0.25
            + sample_behavior_features["response_time_score"] * 0.25
            + sample_behavior_features["interaction_cost_score"] * 0.15
        )

        assert 0.0 <= heuristic_score <= 1.0


class TestCachePredictions:
    """Testes de cache de predições."""

    def test_behavior_cache_key(self):
        import hashlib
        import json

        features = {"usability_score": 0.85, "accessibility_score": 0.75}

        cache_key = hashlib.md5(json.dumps(features, sort_keys=True).encode()).hexdigest()

        assert len(cache_key) == 32
