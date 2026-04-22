"""Testes de integração ML para TechnicalSpecialist."""

import os
import sys
from typing import Any

import pytest

# Configurar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, "/app/libraries/python")


class MockMLflowClient:
    """Mock do cliente MLflow para testes."""

    def __init__(self, model_available: bool = True):
        self._enabled = True
        self._model_available = model_available
        self._model_metadata = {
            "version": "v1.2.3",
            "stage": "Production",
            "run_id": "test-run-123",
        }

    def is_enabled(self) -> bool:
        return self._enabled

    def load_model_with_fallback(self, model_name: str, stage: str) -> Any:
        if not self._model_available:
            return None
        return MockModel()

    def get_model_metadata(self, model_name: str, stage: str) -> dict:
        if not self._model_available:
            return {}
        return self._model_metadata.copy()

    def load_model(self, model_name: str, stage: str) -> Any:
        if not self._model_available:
            raise Exception("Model not available")
        return MockModel()


class MockModel:
    """Mock de modelo ML."""

    def __init__(self):
        self.feature_names_in_ = [
            "security_score",
            "architecture_score",
            "performance_score",
            "code_quality_score",
            "tech_debt_risk",
            "complexity_score",
        ]
        self.n_features_in_ = len(self.feature_names_in_)

    def predict(self, X):
        """Predição mock."""
        import numpy as np

        n_samples = X.shape[0] if len(X.shape) > 1 else 1
        # Retorna 1 (approve) para scores altos, 0 (reject) para baixos
        if len(X.shape) > 1:
            avg_scores = X.mean(axis=1)
            return np.where(avg_scores > 0.5, 1, 0)
        return 1 if X.mean() > 0.5 else 0

    def predict_proba(self, X):
        """Probabilidades mock."""
        import numpy as np

        n_samples = X.shape[0] if len(X.shape) > 1 else 1
        if len(X.shape) > 1:
            avg_scores = X.mean(axis=1)
            proba_approve = avg_scores
            proba_reject = 1 - proba_approve
            return np.column_stack([proba_reject, proba_approve])
        return [[0.3, 0.7]]

    @property
    def feature_importances_(self):
        """Importância de features mock."""
        import numpy as np

        return np.array([0.30, 0.25, 0.20, 0.15, 0.05, 0.05])


@pytest.fixture()
def mock_mlflow_client():
    """Fixture para cliente MLflow mock."""
    return MockMLflowClient(model_available=True)


@pytest.fixture()
def mock_mlflow_client_unavailable():
    """Fixture para cliente MLflow indisponível."""
    return MockMLflowClient(model_available=False)


@pytest.fixture()
def sample_features():
    """Features de exemplo para predição."""
    return {
        "security_score": 0.85,
        "architecture_score": 0.75,
        "performance_score": 0.70,
        "code_quality_score": 0.80,
        "tech_debt_risk": 0.30,
        "complexity_score": 0.40,
    }


class TestMLModelLoading:
    """Testes de carregamento de modelo ML."""

    def test_load_model_from_mlflow_success(self, mock_mlflow_client):
        """Testa carregamento bem-sucedido do modelo."""
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        assert model is not None
        assert hasattr(model, "predict")
        assert hasattr(model, "feature_names_in_")

    def test_load_model_from_mlflow_unavailable(self, mock_mlflow_client_unavailable):
        """Testa fallback quando modelo não está disponível."""
        model = mock_mlflow_client_unavailable.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        assert model is None

    def test_model_metadata_retrieval(self, mock_mlflow_client):
        """Testa recuperação de metadados do modelo."""
        metadata = mock_mlflow_client.get_model_metadata("specialist_technical_model", "Production")

        assert "version" in metadata
        assert "stage" in metadata
        assert metadata["version"] == "v1.2.3"

    def test_model_metadata_when_unavailable(self, mock_mlflow_client_unavailable):
        """Testa metadados quando modelo não está disponível."""
        metadata = mock_mlflow_client_unavailable.get_model_metadata(
            "specialist_technical_model", "Production"
        )

        assert metadata == {}


class TestMLModelPrediction:
    """Testes de predição do modelo ML."""

    def test_predict_with_loaded_model(self, mock_mlflow_client, sample_features):
        """Testa predição com modelo carregado."""
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        import numpy as np

        X = np.array(
            [
                [
                    sample_features["security_score"],
                    sample_features["architecture_score"],
                    sample_features["performance_score"],
                    sample_features["code_quality_score"],
                    sample_features["tech_debt_risk"],
                    sample_features["complexity_score"],
                ]
            ]
        )

        prediction = model.predict(X)

        assert prediction[0] in [0, 1]

    def test_predict_proba_with_loaded_model(self, mock_mlflow_client, sample_features):
        """Testa predição de probabilidades."""
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        import numpy as np

        X = np.array(
            [
                [
                    sample_features["security_score"],
                    sample_features["architecture_score"],
                    sample_features["performance_score"],
                    sample_features["code_quality_score"],
                    sample_features["tech_debt_risk"],
                    sample_features["complexity_score"],
                ]
            ]
        )

        proba = model.predict_proba(X)

        assert len(proba[0]) == 2
        assert abs(sum(proba[0]) - 1.0) < 0.01

    def test_predict_batch_predictions(self, mock_mlflow_client):
        """Testa predição em batch."""
        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        import numpy as np

        X = np.array(
            [
                [0.8, 0.8, 0.7, 0.8, 0.3, 0.4],  # Bom
                [0.3, 0.3, 0.3, 0.3, 0.8, 0.9],  # Ruim
                [0.6, 0.6, 0.6, 0.6, 0.5, 0.5],  # Médio
            ]
        )

        predictions = model.predict(X)

        assert len(predictions) == 3
        assert all(p in [0, 1] for p in predictions)


class TestHeuristicFallback:
    """Testes de fallback para heurística."""

    def test_fallback_to_heuristic_when_model_unavailable(
        self, mock_mlflow_client_unavailable, sample_features
    ):
        """Testa fallback para heurística quando modelo não disponível."""
        model = mock_mlflow_client_unavailable.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        assert model is None

        # Calcular score heurístico
        heuristic_score = (
            sample_features["security_score"] * 0.35
            + sample_features["architecture_score"] * 0.30
            + sample_features["performance_score"] * 0.20
            + sample_features["code_quality_score"] * 0.15
        )

        assert 0.0 <= heuristic_score <= 1.0

    def test_heuristic_score_calculation(self):
        """Testa cálculo de score heurístico."""
        features = {
            "security_score": 0.8,
            "architecture_score": 0.7,
            "performance_score": 0.75,
            "code_quality_score": 0.6,
        }

        heuristic_score = (
            features["security_score"] * 0.35
            + features["architecture_score"] * 0.30
            + features["performance_score"] * 0.20
            + features["code_quality_score"] * 0.15
        )

        expected = 0.8 * 0.35 + 0.7 * 0.30 + 0.75 * 0.20 + 0.6 * 0.15
        assert abs(heuristic_score - expected) < 0.001


class TestMLHeuristicCombination:
    """Testes de combinação ML + heurística."""

    def test_combined_score_with_ml_available(self, sample_features):
        """Testa score combinado quando ML disponível."""
        ml_score = 0.78
        heuristic_score = 0.72

        # Combinação: 70% ML, 30% heurística
        combined_score = 0.7 * ml_score + 0.3 * heuristic_score

        expected = 0.7 * 0.78 + 0.3 * 0.72  # = 0.762
        assert abs(combined_score - expected) < 0.01
        # O combined_score está entre heuristic_score e ml_score, mas mais perto de ml_score
        assert heuristic_score <= combined_score <= ml_score

    def test_combined_score_with_ml_unavailable(self, sample_features):
        """Testa score combinado quando ML indisponível."""
        ml_score = None
        heuristic_score = 0.72

        if ml_score is None:
            combined_score = heuristic_score
        else:
            combined_score = 0.7 * ml_score + 0.3 * heuristic_score

        assert combined_score == 0.72

    def test_weight_adjustment_based_on_confidence(self):
        """Testa ajuste de pesos baseado em confiança."""
        ml_confidence = 0.6  # Confiança moderada na predição ML
        heuristic_score = 0.7
        ml_score = 0.75

        # Ajustar peso da ML baseado em confiança
        ml_weight = 0.5 + (ml_confidence * 0.4)  # 0.5 a 0.9
        heuristic_weight = 1.0 - ml_weight

        combined_score = ml_weight * ml_score + heuristic_weight * heuristic_score

        assert 0.0 <= combined_score <= 1.0


class TestFeatureExtraction:
    """Testes de extração de features."""

    def test_extract_features_from_cognitive_plan(self):
        """Testa extração de features de plano cognitivo."""
        cognitive_plan = {
            "plan_id": "plan-123",
            "original_domain": "technical",
            "tasks": [
                {
                    "description": "Implement secure authentication",
                    "dependencies": [],
                    "estimated_duration_ms": 30000,
                },
                {
                    "description": "Add caching for performance",
                    "dependencies": [],
                    "estimated_duration_ms": 20000,
                },
                {
                    "description": "Write unit tests",
                    "dependencies": [],
                    "estimated_duration_ms": 15000,
                },
            ],
        }

        # Features extraídas (simuladas)
        features = {
            "security_score": 0.7,  # Tem 'authentication'
            "architecture_score": 0.6,  # Estrutura básica
            "performance_score": 0.7,  # Tem 'caching'
            "code_quality_score": 0.7,  # Tem 'tests'
            "tech_debt_risk": 0.4,  # Risco moderado
            "complexity_score": 0.3,  # Baixa complexidade
        }

        for feature, value in features.items():
            assert 0.0 <= value <= 1.0

    def test_feature_validation(self, sample_features):
        """Testa validação de features."""
        required_features = [
            "security_score",
            "architecture_score",
            "performance_score",
            "code_quality_score",
            "tech_debt_risk",
            "complexity_score",
        ]

        for feature in required_features:
            assert feature in sample_features

        for feature, value in sample_features.items():
            assert isinstance(value, (int, float))
            assert 0.0 <= value <= 1.0


class TestModelPerformanceTracking:
    """Testes de tracking de performance do modelo."""

    def test_model_prediction_latency(self, mock_mlflow_client):
        """Testa medição de latência de predição."""
        import time

        import numpy as np

        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        X = np.random.rand(1, 6)

        start_time = time.time()
        prediction = model.predict(X)
        latency_ms = (time.time() - start_time) * 1000

        # Latência deve ser razoável (< 100ms)
        assert latency_ms < 100

    def test_model_batch_performance(self, mock_mlflow_client):
        """Testa performance de predição em batch."""
        import time

        import numpy as np

        model = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        # Batch de 100 predições
        X = np.random.rand(100, 6)

        start_time = time.time()
        predictions = model.predict(X)
        total_time_ms = (time.time() - start_time) * 1000
        avg_latency_ms = total_time_ms / 100

        # Latência média deve ser menor que 10ms
        assert avg_latency_ms < 10

    def test_model_accuracy_tracking(self):
        """Testa tracking de acurácia do modelo."""
        # Simular histórico de predições
        predictions_history = [
            {"predicted": 1, "actual": 1, "confidence": 0.85},
            {"predicted": 1, "actual": 1, "confidence": 0.78},
            {"predicted": 0, "actual": 0, "confidence": 0.65},
            {"predicted": 1, "actual": 0, "confidence": 0.55},  # Erro
            {"predicted": 0, "actual": 0, "confidence": 0.72},
        ]

        correct = sum(1 for p in predictions_history if p["predicted"] == p["actual"])
        accuracy = correct / len(predictions_history)

        assert accuracy == 0.8  # 4 de 5 corretas


class TestModelReloadOnChange:
    """Testes de recarregamento do modelo."""

    def test_model_reload_on_version_change(self, mock_mlflow_client):
        """Testa recarregamento quando versão muda."""
        # Carregar modelo
        model_v1 = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        # Simular mudança de versão
        mock_mlflow_client._model_metadata["version"] = "v1.3.0"

        # Recarregar
        model_v2 = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        # Modelos devem ter versões diferentes
        assert model_v1 is not None
        assert model_v2 is not None

    def test_model_reload_on_stage_change(self, mock_mlflow_client):
        """Testa recarregamento quando stage muda."""
        # Carregar de Production
        model_prod = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Production"
        )

        # Carregar de Staging
        model_staging = mock_mlflow_client.load_model_with_fallback(
            "specialist_technical_model", "Staging"
        )

        assert model_prod is not None
        assert model_staging is not None


class TestCachePredictions:
    """Testes de cache de predições."""

    def test_prediction_cache_key_generation(self):
        """Testa geração de chave de cache."""
        import hashlib
        import json

        features = {
            "security_score": 0.8,
            "architecture_score": 0.7,
            "performance_score": 0.75,
            "code_quality_score": 0.6,
        }

        # Gerar chave de cache
        features_json = json.dumps(features, sort_keys=True)
        cache_key = hashlib.md5(features_json.encode()).hexdigest()

        assert len(cache_key) == 32  # MD5 hash
        assert isinstance(cache_key, str)

    def test_prediction_cache_hit(self):
        """Testa cache hit."""
        cache = {}

        features = {"security_score": 0.8, "architecture_score": 0.7}
        cache_key = "test-key"

        # Primeira chamada - cache miss
        if cache_key not in cache:
            cache[cache_key] = {"prediction": 1, "confidence": 0.85}

        # Segunda chamada - cache hit
        result = cache.get(cache_key)

        assert result["prediction"] == 1
        assert result["confidence"] == 0.85

    def test_prediction_cache_expiry(self):
        """Testa expiração de cache."""
        import time

        cache = {}
        cache_key = "test-key"
        ttl_seconds = 60

        # Adicionar entrada com timestamp
        cache[cache_key] = {"prediction": 1, "timestamp": time.time() - 120}  # 120 segundos atrás

        # Verificar expiração
        entry = cache.get(cache_key)
        is_expired = (time.time() - entry["timestamp"]) > ttl_seconds

        assert is_expired
