"""
Testes de integração para LIMEExplainer com modelos reais.

Testa LimeTabularExplainer com modelos sklearn treinados.
"""

import pytest
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import make_classification

from neural_hive_specialists.explainability.lime_explainer import LIMEExplainer


@pytest.fixture
def sample_data():
    """Gera dataset sintético para testes."""
    X, y = make_classification(
        n_samples=200, n_features=10, n_informative=5, n_redundant=2, random_state=42
    )
    feature_names = [f"feature_{i}" for i in range(10)]
    return pd.DataFrame(X, columns=feature_names), y, feature_names


@pytest.mark.integration
class TestLIMEExplainerWithRandomForest:
    """Testes com RandomForest."""

    def test_explain_random_forest_success(self, sample_data):
        """Testa explicação LIME com RandomForest."""
        X, y, feature_names = sample_data

        # Treinar modelo
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        # Criar explainer
        config = {"lime_num_samples": 500, "lime_timeout_seconds": 10.0}
        explainer = LIMEExplainer(config)

        # Explicar primeira amostra
        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Validações
        assert "method" in result
        assert result["method"] == "lime"
        assert "feature_importances" in result
        assert len(result["feature_importances"]) > 0
        assert "intercept" in result

        # Validar estrutura de importâncias
        for importance in result["feature_importances"]:
            assert "feature_name" in importance
            assert "lime_weight" in importance
            assert "feature_value" in importance
            assert "contribution" in importance
            assert importance["contribution"] in ["positive", "negative", "neutral"]
            assert "importance" in importance
            assert importance["importance"] >= 0

    def test_explain_with_different_num_samples(self, sample_data):
        """Testa LIME com diferentes números de amostras."""
        X, y, feature_names = sample_data

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        features = X.iloc[0].to_dict()

        # Testar com 100 amostras
        config_100 = {"lime_num_samples": 100, "lime_timeout_seconds": 10.0}
        explainer_100 = LIMEExplainer(config_100)
        result_100 = explainer_100.explain(model, features, feature_names)

        # Testar com 1000 amostras
        config_1000 = {"lime_num_samples": 1000, "lime_timeout_seconds": 10.0}
        explainer_1000 = LIMEExplainer(config_1000)
        result_1000 = explainer_1000.explain(model, features, feature_names)

        # Ambos devem ter sucesso
        assert "error" not in result_100
        assert "error" not in result_1000

        # Mais amostras geralmente = mais features explicadas
        assert len(result_1000["feature_importances"]) >= len(
            result_100["feature_importances"]
        )

    def test_explain_with_timeout(self, sample_data):
        """Testa timeout de LIME."""
        X, y, feature_names = sample_data

        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X, y)

        # Timeout muito curto
        config = {
            "lime_num_samples": 5000,  # Muitas amostras
            "lime_timeout_seconds": 0.001,  # 1ms - deve dar timeout
        }
        explainer = LIMEExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Deve retornar erro de timeout
        assert "error" in result
        assert result["error"] == "timeout"

    def test_top_features_extraction(self, sample_data):
        """Testa extração de top features."""
        X, y, feature_names = sample_data

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        config = {"lime_num_samples": 500, "lime_timeout_seconds": 10.0}
        explainer = LIMEExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Extrair top 3 features
        top_features = explainer.get_top_features(result, top_n=3)

        assert len(top_features) <= 3
        # Deve estar ordenado por importância
        if len(top_features) >= 2:
            assert top_features[0]["importance"] >= top_features[1]["importance"]

    def test_top_features_positive_only(self, sample_data):
        """Testa extração de apenas features positivas."""
        X, y, feature_names = sample_data

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        config = {"lime_num_samples": 500, "lime_timeout_seconds": 10.0}
        explainer = LIMEExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Extrair apenas positivas
        positive_features = explainer.get_top_features(
            result, top_n=5, positive_only=True
        )

        for feature in positive_features:
            assert feature["contribution"] == "positive"


@pytest.mark.integration
class TestLIMEExplainerWithLinearModel:
    """Testes com modelo linear."""

    def test_explain_logistic_regression(self, sample_data):
        """Testa explicação LIME com LogisticRegression."""
        X, y, feature_names = sample_data

        model = LogisticRegression(random_state=42, max_iter=1000)
        model.fit(X, y)

        config = {"lime_num_samples": 500, "lime_timeout_seconds": 10.0}
        explainer = LIMEExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        assert result["method"] == "lime"
        assert "feature_importances" in result
        assert len(result["feature_importances"]) > 0


@pytest.mark.integration
class TestLIMEExplainerEdgeCases:
    """Testes de casos extremos."""

    def test_explain_with_no_model(self, sample_data):
        """Testa LIME sem modelo."""
        X, _, feature_names = sample_data

        config = {"lime_num_samples": 500, "lime_timeout_seconds": 10.0}
        explainer = LIMEExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(None, features, feature_names)

        assert "error" in result
        assert result["error"] == "No model"

    def test_training_data_generation(self, sample_data):
        """Testa geração de training data sintético."""
        X, _, feature_names = sample_data

        config = {"lime_num_samples": 500, "lime_timeout_seconds": 10.0}
        explainer = LIMEExplainer(config)

        features = X.iloc[0].to_dict()
        training_data = explainer._generate_training_data(
            features, feature_names, num_samples=100
        )

        assert training_data.shape == (100, len(feature_names))
        # Valores devem ser perturbações dos originais
        assert not np.allclose(training_data, np.array([list(features.values())] * 100))
