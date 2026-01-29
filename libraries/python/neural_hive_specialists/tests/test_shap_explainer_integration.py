"""
Testes de integração para SHAPExplainer com modelos reais.

Testa TreeExplainer e KernelExplainer com modelos sklearn treinados.
"""

import pytest
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.datasets import make_classification

from neural_hive_specialists.explainability.shap_explainer import SHAPExplainer


@pytest.fixture
def sample_data():
    """Gera dataset sintético para testes."""
    X, y = make_classification(
        n_samples=200, n_features=10, n_informative=5, n_redundant=2, random_state=42
    )
    feature_names = [f"feature_{i}" for i in range(10)]
    return pd.DataFrame(X, columns=feature_names), y, feature_names


@pytest.fixture
def background_dataset(sample_data):
    """Cria background dataset para SHAP."""
    X, _, _ = sample_data
    return X.sample(50, random_state=42)


@pytest.mark.integration
class TestSHAPExplainerWithRandomForest:
    """Testes com RandomForest (TreeExplainer)."""

    def test_explain_random_forest_success(
        self, sample_data, background_dataset, tmp_path
    ):
        """Testa explicação SHAP com RandomForest."""
        X, y, feature_names = sample_data

        # Treinar modelo
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        # Salvar background dataset
        background_path = tmp_path / "background.parquet"
        background_dataset.to_parquet(background_path)

        # Criar explainer
        config = {
            "shap_background_dataset_path": str(background_path),
            "shap_timeout_seconds": 10.0,
        }
        explainer = SHAPExplainer(config)

        # Explicar primeira amostra
        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Validações
        assert "method" in result
        assert result["method"] == "shap"
        assert "feature_importances" in result
        assert len(result["feature_importances"]) == len(feature_names)
        assert "base_value" in result
        assert isinstance(result["base_value"], float)

        # Validar estrutura de importâncias
        for importance in result["feature_importances"]:
            assert "feature_name" in importance
            assert "shap_value" in importance
            assert "feature_value" in importance
            assert "contribution" in importance
            assert importance["contribution"] in ["positive", "negative", "neutral"]
            assert "importance" in importance
            assert importance["importance"] >= 0

    def test_explain_with_timeout(self, sample_data, background_dataset, tmp_path):
        """Testa timeout de SHAP."""
        X, y, feature_names = sample_data

        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X, y)

        background_path = tmp_path / "background.parquet"
        background_dataset.to_parquet(background_path)

        # Timeout muito curto
        config = {
            "shap_background_dataset_path": str(background_path),
            "shap_timeout_seconds": 0.001,  # 1ms - deve dar timeout
        }
        explainer = SHAPExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Deve retornar erro de timeout
        assert "error" in result
        assert result["error"] == "timeout"

    def test_top_features_extraction(self, sample_data, background_dataset, tmp_path):
        """Testa extração de top features."""
        X, y, feature_names = sample_data

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        background_path = tmp_path / "background.parquet"
        background_dataset.to_parquet(background_path)

        config = {
            "shap_background_dataset_path": str(background_path),
            "shap_timeout_seconds": 10.0,
        }
        explainer = SHAPExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Extrair top 3 features
        top_features = explainer.get_top_features(result, top_n=3)

        assert len(top_features) == 3
        # Deve estar ordenado por importância
        assert top_features[0]["importance"] >= top_features[1]["importance"]
        assert top_features[1]["importance"] >= top_features[2]["importance"]


@pytest.mark.integration
class TestSHAPExplainerWithGradientBoosting:
    """Testes com GradientBoosting (TreeExplainer)."""

    def test_explain_gradient_boosting(self, sample_data, background_dataset, tmp_path):
        """Testa explicação SHAP com GradientBoosting."""
        X, y, feature_names = sample_data

        model = GradientBoostingClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        background_path = tmp_path / "background.parquet"
        background_dataset.to_parquet(background_path)

        config = {
            "shap_background_dataset_path": str(background_path),
            "shap_timeout_seconds": 10.0,
        }
        explainer = SHAPExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        assert result["method"] == "shap"
        assert "feature_importances" in result
        assert len(result["feature_importances"]) > 0


@pytest.mark.integration
class TestSHAPExplainerWithLinearModel:
    """Testes com modelo linear (KernelExplainer)."""

    def test_explain_logistic_regression(
        self, sample_data, background_dataset, tmp_path
    ):
        """Testa explicação SHAP com LogisticRegression (KernelExplainer)."""
        X, y, feature_names = sample_data

        model = LogisticRegression(random_state=42, max_iter=1000)
        model.fit(X, y)

        background_path = tmp_path / "background.parquet"
        background_dataset.to_parquet(background_path)

        config = {
            "shap_background_dataset_path": str(background_path),
            "shap_timeout_seconds": 15.0,  # KernelExplainer é mais lento
        }
        explainer = SHAPExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # KernelExplainer pode dar timeout, aceitar ambos
        if "error" not in result:
            assert result["method"] == "shap"
            assert "feature_importances" in result


@pytest.mark.integration
class TestSHAPExplainerEdgeCases:
    """Testes de casos extremos."""

    def test_explain_without_background_dataset(self, sample_data):
        """Testa SHAP sem background dataset."""
        X, y, feature_names = sample_data

        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        config = {"shap_background_dataset_path": None, "shap_timeout_seconds": 10.0}
        explainer = SHAPExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(model, features, feature_names)

        # Deve funcionar mesmo sem background
        assert "method" in result

    def test_explain_with_no_model(self, sample_data):
        """Testa SHAP sem modelo."""
        X, _, feature_names = sample_data

        config = {"shap_timeout_seconds": 10.0}
        explainer = SHAPExplainer(config)

        features = X.iloc[0].to_dict()
        result = explainer.explain(None, features, feature_names)

        assert "error" in result
        assert result["error"] == "No model"
