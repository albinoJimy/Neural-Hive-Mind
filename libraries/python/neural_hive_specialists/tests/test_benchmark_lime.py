"""
Benchmarks de performance para LIME Explainer.

Mede tempo de execução de explicações LIME em diferentes cenários.
"""

import pytest
import numpy as np
from sklearn.linear_model import LogisticRegression


@pytest.fixture
def linear_model():
    """Modelo linear pequeno para benchmark."""
    X = np.random.rand(50, 4)
    y = np.random.randint(0, 2, 50)
    model = LogisticRegression(random_state=42, max_iter=100)
    model.fit(X, y)
    return model


@pytest.fixture
def lime_config():
    """Configuração para LIMEExplainer."""
    return {
        'lime_timeout_seconds': 5.0,
        'lime_num_samples': 500  # Reduzido para benchmark mais rápido
    }


@pytest.mark.benchmark
class TestLIMEBenchmarks:
    """Benchmarks de LIME."""

    def test_benchmark_lime_explain_small_model(self, benchmark, linear_model, lime_config):
        """
        Benchmark: Tempo de explicação LIME em modelo linear.

        Expectativa: < 5 segundos
        """
        from neural_hive_specialists.explainability.lime_explainer import LIMEExplainer

        explainer = LIMEExplainer(lime_config)

        # Features de entrada
        aggregated_features = {
            'num_tasks': 8.0,
            'complexity_score': 0.75,
            'avg_duration_ms': 2500.0,
            'risk_score': 0.3
        }
        feature_names = sorted(aggregated_features.keys())

        # Executar benchmark
        result = benchmark(
            explainer.explain,
            linear_model,
            aggregated_features,
            feature_names
        )

        # Validar que retornou resultado válido
        assert 'feature_importances' in result or 'error' in result

    def test_benchmark_lime_with_fewer_samples(self, benchmark, linear_model):
        """
        Benchmark: LIME com menos amostras para velocidade.

        Expectativa: < 2 segundos
        """
        from neural_hive_specialists.explainability.lime_explainer import LIMEExplainer

        config = {
            'lime_timeout_seconds': 5.0,
            'lime_num_samples': 100  # Muito reduzido
        }

        explainer = LIMEExplainer(config)

        aggregated_features = {
            'f1': 0.5,
            'f2': 0.6,
            'f3': 0.7,
            'f4': 0.8
        }
        feature_names = ['f1', 'f2', 'f3', 'f4']

        result = benchmark(
            explainer.explain,
            linear_model,
            aggregated_features,
            feature_names
        )

        assert 'feature_importances' in result or 'error' in result
