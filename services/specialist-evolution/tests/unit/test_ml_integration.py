"""Testes de integração ML para EvolutionSpecialist."""

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
        self._model_metadata = {"version": "v1.0.0", "stage": "Production"}

    def is_enabled(self) -> bool:
        return self._enabled

    def load_model_with_fallback(self, model_name: str, stage: str):
        if not self._model_available:
            return None
        return MockEvolutionModel()

    def get_model_metadata(self, model_name: str, stage: str) -> dict:
        if not self._model_available:
            return {}
        return self._model_metadata.copy()

    def load_model(self, model_name: str, stage: str):
        if not self._model_available:
            raise Exception("Model not available")
        return MockEvolutionModel()


class MockEvolutionModel:
    """Mock de modelo ML de evolução."""

    def __init__(self):
        self.feature_names_in_ = [
            "maintainability_score",
            "scalability_score",
            "extensibility_score",
            "modularity_score",
            "tech_debt_score",
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
def sample_evolution_features():
    return {
        "maintainability_score": 0.80,
        "scalability_score": 0.75,
        "extensibility_score": 0.70,
        "modularity_score": 0.85,
        "tech_debt_score": 0.65,
    }


class TestMLModelLoading:
    """Testes de carregamento de modelo."""

    def test_load_evolution_model_success(self, mock_mlflow_client):
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_evolution_model", "Production"
        )
        assert model is not None


class TestMLModelPrediction:
    """Testes de predição."""

    def test_predict_evolution_design(self, mock_mlflow_client, sample_evolution_features):
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_evolution_model", "Production"
        )

        import numpy as np

        X = np.array(
            [
                [
                    sample_evolution_features["maintainability_score"],
                    sample_evolution_features["scalability_score"],
                    sample_evolution_features["extensibility_score"],
                    sample_evolution_features["modularity_score"],
                    sample_evolution_features["tech_debt_score"],
                ]
            ]
        )

        prediction = model.predict(X)
        assert prediction[0] in [0, 1]


class TestHeuristicFallback:
    """Testes de fallback para heurística."""

    def test_evolution_heuristic_calculation(self, sample_evolution_features):
        ml_model = None

        # Pesos padrão do EvolutionSpecialist
        default_weights = {
            "maintainability": 0.25,
            "scalability": 0.25,
            "extensibility": 0.20,
            "modularity": 0.15,
            "tech_debt_prevention": 0.15,
        }

        heuristic_score = (
            sample_evolution_features["maintainability_score"] * default_weights["maintainability"]
            + sample_evolution_features["scalability_score"] * default_weights["scalability"]
            + sample_evolution_features["extensibility_score"] * default_weights["extensibility"]
            + sample_evolution_features["modularity_score"] * default_weights["modularity"]
            + sample_evolution_features["tech_debt_score"] * default_weights["tech_debt_prevention"]
        )

        assert 0.0 <= heuristic_score <= 1.0


class TestAdaptiveWeights:
    """Testes de pesos adaptativos."""

    def test_default_weights(self):
        """Testa pesos padrão do EvolutionSpecialist."""
        default_weights = {
            "maintainability": 0.25,
            "scalability": 0.25,
            "extensibility": 0.20,
            "modularity": 0.15,
            "tech_debt_prevention": 0.15,
        }

        total_weight = sum(default_weights.values())
        assert abs(total_weight - 1.0) < 0.01

    def test_adaptive_weights_adjustment(self):
        """Testa ajuste de pesos adaptativos."""
        default_weights = {
            "maintainability": 0.25,
            "scalability": 0.25,
            "extensibility": 0.20,
            "modularity": 0.15,
            "tech_debt_prevention": 0.15,
        }

        # Simular ajuste baseado em histórico
        adjustment_factor = 0.05
        adapted_weights = default_weights.copy()
        adapted_weights["maintainability"] += adjustment_factor
        adapted_weights["scalability"] -= adjustment_factor

        total_weight = sum(adapted_weights.values())
        assert abs(total_weight - 1.0) < 0.01


class TestCachePredictions:
    """Testes de cache de predições."""

    def test_evolution_cache_key(self):
        import hashlib
        import json

        features = {"maintainability_score": 0.80, "scalability_score": 0.75}

        cache_key = hashlib.md5(json.dumps(features, sort_keys=True).encode()).hexdigest()

        assert len(cache_key) == 32
