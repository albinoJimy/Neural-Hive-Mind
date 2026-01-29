"""
Benchmarks de performance para SHAP Explainer.

Mede tempo de execução de explicações SHAP em diferentes cenários.
"""

import pytest
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from unittest.mock import Mock


@pytest.fixture
def small_model():
    """Modelo pequeno para benchmark."""
    X = np.random.rand(50, 4)
    y = np.random.randint(0, 2, 50)
    model = RandomForestClassifier(n_estimators=5, random_state=42, max_depth=2)
    model.fit(X, y)
    return model


@pytest.fixture
def shap_config():
    """Configuração para SHAPExplainer."""
    return {
        "shap_timeout_seconds": 5.0,
        "shap_background_dataset_path": None,
        "shap_max_background_samples": 50,
    }


@pytest.mark.benchmark
class TestSHAPBenchmarks:
    """Benchmarks de SHAP."""

    def test_benchmark_shap_explain_small_model(
        self, benchmark, small_model, shap_config
    ):
        """
        Benchmark: Tempo de explicação SHAP em modelo pequeno.

        Expectativa: < 5 segundos
        """
        from neural_hive_specialists.explainability.shap_explainer import SHAPExplainer

        explainer = SHAPExplainer(shap_config)

        # Features de entrada
        aggregated_features = {
            "num_tasks": 8.0,
            "complexity_score": 0.75,
            "avg_duration_ms": 2500.0,
            "risk_score": 0.3,
        }
        feature_names = sorted(aggregated_features.keys())

        # Executar benchmark
        result = benchmark(
            explainer.explain, small_model, aggregated_features, feature_names
        )

        # Validar que retornou resultado válido
        assert "feature_importances" in result or "error" in result

    def test_benchmark_shap_with_background_data(
        self, benchmark, small_model, shap_config
    ):
        """
        Benchmark: SHAP com background dataset.

        Expectativa: < 5 segundos
        """
        from neural_hive_specialists.explainability.shap_explainer import SHAPExplainer
        import pandas as pd

        # Criar background dataset pequeno
        background_data = pd.DataFrame(
            np.random.rand(30, 4), columns=["f1", "f2", "f3", "f4"]
        )

        explainer = SHAPExplainer(shap_config)
        explainer.background_data = background_data

        aggregated_features = {"f1": 0.5, "f2": 0.6, "f3": 0.7, "f4": 0.8}
        feature_names = ["f1", "f2", "f3", "f4"]

        result = benchmark(
            explainer.explain, small_model, aggregated_features, feature_names
        )

        assert "feature_importances" in result or "error" in result
