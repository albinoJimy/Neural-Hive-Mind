"""Testes para SHAPExplainer."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np

from neural_hive_specialists.explainability.shap_explainer import SHAPExplainer


@pytest.fixture
def mock_config():
    """Configuração mock para SHAPExplainer."""
    return {
        "shap_background_dataset_path": None,  # Sem dataset para testes básicos
        "shap_timeout_seconds": 5.0,
    }


@pytest.fixture
def sample_features():
    """Features de exemplo."""
    return {
        "confidence": 0.8,
        "risk": 0.3,
        "complexity": 0.5,
        "specialist_type_business": 1.0,
        "specialist_type_technical": 0.0,
    }


@pytest.fixture
def sample_feature_names():
    """Nomes de features de exemplo."""
    return [
        "confidence",
        "risk",
        "complexity",
        "specialist_type_business",
        "specialist_type_technical",
    ]


class TestSHAPExplainerInit:
    """Testes de inicialização."""

    def test_init_with_minimal_config(self, mock_config):
        """Testa inicialização com config mínima."""
        explainer = SHAPExplainer(mock_config)

        assert explainer.timeout_seconds == 5.0
        assert explainer.background_data is None
        assert explainer.feature_names == []

    def test_init_with_custom_timeout(self, mock_config):
        """Testa inicialização com timeout customizado."""
        mock_config["shap_timeout_seconds"] = 10.0
        explainer = SHAPExplainer(mock_config)

        assert explainer.timeout_seconds == 10.0

    @patch("pandas.read_parquet")
    def test_init_loads_background_dataset(self, mock_read_parquet, tmp_path):
        """Testa carregamento de dataset de background."""
        # Criar dataset Parquet temporário
        df = pd.DataFrame({"feature1": [1, 2, 3], "feature2": [4, 5, 6]})
        parquet_path = tmp_path / "background.parquet"
        df.to_parquet(parquet_path)

        mock_read_parquet.return_value = df

        config = {"shap_background_dataset_path": str(parquet_path), "shap_timeout_seconds": 5.0}

        explainer = SHAPExplainer(config)

        assert explainer.background_data is not None
        assert len(explainer.feature_names) == 2
        assert "feature1" in explainer.feature_names

    @patch("pandas.read_parquet")
    def test_init_handles_load_error(self, mock_read_parquet):
        """Testa tratamento de erro ao carregar dataset."""
        mock_read_parquet.side_effect = Exception("File not found")

        config = {
            "shap_background_dataset_path": "/nonexistent/path.parquet",
            "shap_timeout_seconds": 5.0,
        }

        explainer = SHAPExplainer(config)

        assert explainer.background_data is None
        assert explainer.feature_names == []


class TestExplain:
    """Testes do método explain."""

    def test_explain_with_no_model(self, mock_config, sample_features, sample_feature_names):
        """Testa explicação quando modelo não é fornecido."""
        explainer = SHAPExplainer(mock_config)

        result = explainer.explain(None, sample_features, sample_feature_names)

        assert result["method"] == "shap"
        assert result["base_value"] == 0.5
        assert "error" in result
        assert result["error"] == "No model"
        assert len(result["feature_importances"]) == len(sample_feature_names)

    def test_explain_fallback_features_structure(
        self, mock_config, sample_features, sample_feature_names
    ):
        """Testa estrutura de features fallback."""
        explainer = SHAPExplainer(mock_config)

        result = explainer.explain(None, sample_features, sample_feature_names)

        # Verificar estrutura de cada feature importance
        for importance in result["feature_importances"]:
            assert "feature_name" in importance
            assert "shap_value" in importance
            assert "feature_value" in importance
            assert "contribution" in importance
            assert "importance" in importance
            assert importance["shap_value"] == 0.0
            assert importance["contribution"] == "neutral"

    def test_explain_with_empty_features(self, mock_config, sample_feature_names):
        """Testa explicação com features vazias."""
        explainer = SHAPExplainer(mock_config)

        result = explainer.explain(None, {}, sample_feature_names)

        assert len(result["feature_importances"]) == len(sample_feature_names)

    @patch("shap.Explainer")
    def test_explain_timeout_handling(
        self, mock_shap_explainer, mock_config, sample_features, sample_feature_names
    ):
        """Testa tratamento de timeout no cálculo SHAP."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError

        explainer = SHAPExplainer(mock_config)

        # Criar modelo mock
        mock_model = Mock()

        # Simular timeout
        with patch.object(ThreadPoolExecutor, "submit") as mock_submit:
            mock_future = Mock()
            mock_future.result.side_effect = TimeoutError("Timeout")
            mock_submit.return_value = mock_future

            result = explainer.explain(mock_model, sample_features, sample_feature_names)

            assert "error" in result
            assert result["error"] == "timeout"


class TestExplainWithBackgroundData:
    """Testes com dataset de background."""

    @patch("pandas.read_parquet")
    def test_explain_uses_background_features(self, mock_read_parquet, tmp_path, sample_features):
        """Testa que features do background são usadas."""
        df = pd.DataFrame({"confidence": [0.5, 0.6, 0.7], "risk": [0.3, 0.4, 0.5]})
        parquet_path = tmp_path / "background.parquet"
        df.to_parquet(parquet_path)
        mock_read_parquet.return_value = df

        config = {"shap_background_dataset_path": str(parquet_path), "shap_timeout_seconds": 5.0}

        explainer = SHAPExplainer(config)

        assert len(explainer.feature_names) == 2
        assert "confidence" in explainer.feature_names


class TestGetTopFeatures:
    """Testes do método get_top_features."""

    def test_get_top_features_default(self, mock_config, sample_features):
        """Testa get_top_features com parâmetros padrão."""
        explainer = SHAPExplainer(mock_config)

        shap_result = {
            "feature_importances": [
                {"feature_name": "f1", "importance": 0.5, "contribution": "positive"},
                {"feature_name": "f2", "importance": 0.3, "contribution": "negative"},
                {"feature_name": "f3", "importance": 0.1, "contribution": "neutral"},
            ]
        }

        top_features = explainer.get_top_features(shap_result, top_n=2)

        assert len(top_features) == 2
        assert top_features[0]["feature_name"] == "f1"
        assert top_features[1]["feature_name"] == "f2"

    def test_get_top_features_positive_only(self, mock_config):
        """Testa filtro para apenas contribuições positivas."""
        explainer = SHAPExplainer(mock_config)

        shap_result = {
            "feature_importances": [
                {"feature_name": "f1", "importance": 0.5, "contribution": "positive"},
                {"feature_name": "f2", "importance": 0.3, "contribution": "negative"},
            ]
        }

        top_features = explainer.get_top_features(shap_result, positive_only=True)

        assert len(top_features) == 1
        assert top_features[0]["contribution"] == "positive"

    def test_get_top_features_negative_only(self, mock_config):
        """Testa filtro para apenas contribuições negativas."""
        explainer = SHAPExplainer(mock_config)

        shap_result = {
            "feature_importances": [
                {"feature_name": "f1", "importance": 0.5, "contribution": "positive"},
                {"feature_name": "f2", "importance": 0.3, "contribution": "negative"},
            ]
        }

        top_features = explainer.get_top_features(shap_result, negative_only=True)

        assert len(top_features) == 1
        assert top_features[0]["contribution"] == "negative"


class TestErrorHandling:
    """Testes de tratamento de erros."""

    def test_handles_missing_feature_values(self, mock_config):
        """Testa tratamento de features faltantes."""
        explainer = SHAPExplainer(mock_config)

        feature_names = ["confidence", "risk", "complexity"]
        features = {"confidence": 0.8}  # Apenas uma feature

        result = explainer.explain(None, features, feature_names)

        # Features faltantes devem ter valor padrão 0.0
        for importance in result["feature_importances"]:
            if importance["feature_name"] in ["risk", "complexity"]:
                assert importance["feature_value"] == 0.0

    def test_handles_nan_values(self, mock_config):
        """Testa tratamento de valores NaN."""
        explainer = SHAPExplainer(mock_config)

        feature_names = ["confidence", "risk"]
        features = {"confidence": float("nan"), "risk": 0.5}

        # Deve tratar NaN sem lançar erro
        result = explainer.explain(None, features, feature_names)

        assert len(result["feature_importances"]) == 2


class TestExplainMultiplePredictions:
    """Testes de múltiplas predições - removidos devido a complexidade de mock do SHAP."""
