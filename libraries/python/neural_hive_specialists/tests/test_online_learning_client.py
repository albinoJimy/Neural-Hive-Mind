"""Testes para OnlineLearningClient."""

import os
import time
import pytest
import numpy as np
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime, timedelta, timezone

from neural_hive_specialists.online_learning_client import (
    OnlineLearningClient,
    OnlineLearningClientError,
)


@pytest.fixture
def client():
    return OnlineLearningClient(
        specialist_type="technical",
        online_learning_enabled=True,
        cache_ttl_seconds=300,
    )


@pytest.mark.unit
class TestOnlineLearningClientError:
    """Testes para OnlineLearningClientError."""

    def test_exception_is_exception(self):
        """Testa que é uma exceção."""
        assert issubclass(OnlineLearningClientError, Exception)

    def test_can_raise_and_catch(self):
        """Testa que pode ser lançada e capturada."""
        with pytest.raises(OnlineLearningClientError):
            raise OnlineLearningClientError("Test error")


@pytest.mark.unit
class TestOnlineLearningClientInit:
    """Testes de inicialização."""

    def test_init_default_params(self):
        """Testa inicialização com parâmetros padrão."""
        client = OnlineLearningClient("technical")

        assert client.specialist_type == "technical"
        assert client.online_learning_enabled is True
        assert client.cache_ttl_seconds == 300
        assert client._cached_model is None
        assert client._cache_timestamp is None

    def test_init_custom_params(self):
        """Testa inicialização com parâmetros customizados."""
        client = OnlineLearningClient(
            specialist_type="business",
            online_learning_enabled=False,
            cache_ttl_seconds=600,
            mongodb_uri="mongodb://remote:27017",
            checkpoint_path="/custom/path",
        )

        assert client.specialist_type == "business"
        assert client.online_learning_enabled is False
        assert client.cache_ttl_seconds == 600
        assert client.mongodb_uri == "mongodb://remote:27017"

    def test_init_with_env_vars(self, monkeypatch):
        """Testa inicialização usando variáveis de ambiente."""
        monkeypatch.setenv("MONGODB_URI", "mongodb://env:27017")
        monkeypatch.setenv("ONLINE_CHECKPOINT_PATH", "/env/checkpoints")

        client = OnlineLearningClient("technical")

        assert client.mongodb_uri == "mongodb://env:27017"
        assert client.checkpoint_path == "/env/checkpoints"

    def test_stats_initialized(self):
        """Testa que estatísticas são inicializadas."""
        client = OnlineLearningClient("technical")

        assert client._prediction_count == 0
        assert client._fallback_count == 0
        assert client._ensemble_count == 0


@pytest.mark.unit
class TestIsCacheValid:
    """Testes para _is_cache_valid."""

    def test_cache_valid_when_fresh(self):
        """Testa cache válido quando timestamp é recente."""
        client = OnlineLearningClient("technical")
        client._cached_model = {"model": "data"}
        client._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=100)

        assert client._is_cache_valid() is True

    def test_cache_invalid_when_expired(self):
        """Testa cache inválido quando timestamp é antigo."""
        client = OnlineLearningClient("technical")
        client._cached_model = {"model": "data"}
        client._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=400)

        assert client._is_cache_valid() is False

    def test_cache_invalid_when_no_model(self):
        """Testa cache inválido quando não há modelo."""
        client = OnlineLearningClient("technical")
        client._cached_model = None

        assert client._is_cache_valid() is False

    def test_cache_invalid_when_no_timestamp(self):
        """Testa cache inválido quando não há timestamp."""
        client = OnlineLearningClient("technical")
        client._cached_model = {"model": "data"}
        client._cache_timestamp = None

        assert client._is_cache_valid() is False


@pytest.mark.unit
class TestLoadOnlineModel:
    """Testes para _load_online_model."""

    def test_disabled_returns_none(self):
        """Testa retorna None quando online learning está desabilitado."""
        client = OnlineLearningClient(
            "technical", online_learning_enabled=False
        )

        result = client._load_online_model()

        assert result is None

    @patch("glob.glob")
    def test_no_checkpoints_found(self, mock_glob):
        """Testa retorna None quando não há checkpoints."""
        client = OnlineLearningClient("technical")
        mock_glob.return_value = []

        result = client._load_online_model()

        assert result is None

    @patch("joblib.load")
    @patch("glob.glob")
    def test_load_checkpoint_success(self, mock_glob, mock_joblib):
        """Testa carregamento bem-sucedido de checkpoint."""
        client = OnlineLearningClient("technical")
        mock_glob.return_value = ["/checkpoints/technical_v1.pkl"]
        mock_joblib.return_value = {
            "model": "model_data",
            "scaler": "scaler_data",
            "model_version": "v1.0",
        }

        result = client._load_online_model()

        assert result is not None
        assert result["model_version"] == "v1.0"


@pytest.mark.unit
class TestGetOnlineModel:
    """Testes para get_online_model."""

    def test_disabled_returns_none(self):
        """Testa retorna None quando desabilitado."""
        client = OnlineLearningClient(
            "technical", online_learning_enabled=False
        )

        result = client.get_online_model()

        assert result is None

    def test_returns_cached_model(self):
        """Testa retorna modelo em cache válido."""
        client = OnlineLearningClient("technical")
        cached_model = {"model": "cached"}
        client._cached_model = cached_model
        client._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=100)

        result = client.get_online_model()

        assert result == cached_model

    def test_forces_reload(self):
        """Testa que force_reload ignora cache."""
        client = OnlineLearningClient("technical")
        old_cached = {"model": "old"}
        client._cached_model = old_cached
        client._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=100)

        with patch.object(client, "_load_online_model", return_value={"model": "new"}):
            result = client.get_online_model(force_reload=True)

        assert result != old_cached
        assert result["model"] == "new"

    def test_circuit_breaker_fallback(self):
        """Testa fallback para cache quando circuit breaker está aberto."""
        import pybreaker

        client = OnlineLearningClient("technical")
        cached_model = {"model": "cached"}
        client._cached_model = cached_model
        client._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=400)

        # Simular circuit breaker aberto
        with patch.object(client, "_load_online_model", side_effect=pybreaker.CircuitBreakerError):
            result = client.get_online_model()

        # Deve retornar cache stale
        assert result == cached_model


@pytest.mark.unit
class TestPredictWithEnsemble:
    """Testes para predict_with_ensemble."""

    @pytest.fixture
    def mock_batch_model(self):
        """Modelo batch mock."""
        model = Mock()
        model.predict_proba.return_value = np.array([[0.3, 0.7], [0.8, 0.2]])
        return model

    def test_predict_with_1d_features(self, client, mock_batch_model):
        """Testa predição com features 1D (reshape automático)."""
        features = np.array([0.5, 0.3, 0.8])

        result = client.predict_with_ensemble(features, mock_batch_model)

        assert result["prediction"] == [1, 0]  #.argmax([0.3, 0.7]) = 1
        assert client._prediction_count == 1

    def test_predict_batch_only_fallback(self, client, mock_batch_model):
        """Testa fallback para batch quando online não disponível."""
        client.online_learning_enabled = False
        features = np.array([[0.5, 0.3, 0.8]])

        result = client.predict_with_ensemble(features, mock_batch_model)

        assert result["model_used"] == "batch"
        assert client._fallback_count == 1

    def test_predict_with_online_model(self, client, mock_batch_model):
        """Testa predição usando ensemble batch + online."""
        features = np.array([[0.5, 0.3, 0.8]])

        # Mock online model
        online_model = {
            "model": Mock(),
            "scaler": Mock(),
        }
        online_model["model"].predict_proba.return_value = np.array([[0.4, 0.6]])
        online_model["scaler"].transform.return_value = features

        with patch.object(client, "get_online_model", return_value=online_model):
            result = client.predict_with_ensemble(features, mock_batch_model)

        assert result["model_used"] == "ensemble"
        assert client._ensemble_count == 1

    def test_predict_custom_weights(self, client, mock_batch_model):
        """Testa predição com pesos customizados."""
        features = np.array([[0.5, 0.3, 0.8]])

        result = client.predict_with_ensemble(
            features, mock_batch_model, batch_weight=0.5, online_weight=0.5
        )

        # Verificar que latência foi calculada
        assert "batch_latency_ms" in result
        assert "total_latency_ms" in result

    def test_predict_batch_error_raises(self, client, mock_batch_model):
        """Testa que erro em batch prediction levanta exceção."""
        mock_batch_model.predict_proba.side_effect = Exception("Batch error")
        features = np.array([[0.5, 0.3, 0.8]])

        with pytest.raises(OnlineLearningClientError):
            client.predict_with_ensemble(features, mock_batch_model)


@pytest.mark.unit
class TestReportPrediction:
    """Testes para report_prediction."""

    @patch("pymongo.MongoClient")
    def test_report_prediction_success(self, mock_mongo_class):
        """Testa report bem-sucedido de predição."""
        mock_client = Mock()
        mock_db = Mock()
        mock_collection = Mock()
        mock_mongo_class.return_value = mock_client
        mock_client.__getitem__ = Mock(return_value=mock_db)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        client = OnlineLearningClient("technical")

        client.report_prediction(
            plan_id="plan-123",
            features=np.array([1, 2, 3]),
            prediction="approve",
            confidence=0.85,
            model_used="ensemble",
        )

        mock_collection.insert_one.assert_called_once()

    @patch("pymongo.MongoClient")
    def test_report_prediction_error_handled(self, mock_mongo_class):
        """Testa que erro ao reportar é tratado sem levantar exceção."""
        mock_mongo_class.side_effect = Exception("DB error")

        client = OnlineLearningClient("technical")

        # Não deve lançar exceção
        client.report_prediction(
            plan_id="plan-123",
            features=np.array([1, 2, 3]),
            prediction="approve",
            confidence=0.85,
            model_used="ensemble",
        )


@pytest.mark.unit
class TestGetStatistics:
    """Testes para get_statistics."""

    def test_statistics_initial(self, client):
        """Testa estatísticas iniciais."""
        stats = client.get_statistics()

        assert stats["specialist_type"] == "technical"
        assert stats["total_predictions"] == 0
        assert stats["ensemble_predictions"] == 0
        assert stats["fallback_predictions"] == 0
        assert stats["ensemble_rate"] == 0.0

    def test_statistics_with_predictions(self, client):
        """Testa estatísticas após predições."""
        client._prediction_count = 10
        client._ensemble_count = 7
        client._fallback_count = 3

        stats = client.get_statistics()

        assert stats["total_predictions"] == 10
        assert stats["ensemble_predictions"] == 7
        assert stats["fallback_predictions"] == 3
        assert stats["ensemble_rate"] == 0.7


@pytest.mark.unit
class TestInvalidateCache:
    """Testes para invalidate_cache."""

    def test_invalidate_cache_clears_model(self):
        """Testa que invalidação limpa o cache."""
        client = OnlineLearningClient("technical")
        client._cached_model = {"model": "data"}
        client._cache_timestamp = datetime.now(timezone.utc)

        client.invalidate_cache()

        assert client._cached_model is None
        assert client._cache_timestamp is None


@pytest.mark.unit
class TestIsOnlineModelAvailable:
    """Testes para is_online_model_available."""

    def test_available_when_disabled(self):
        """Testa retorna False quando desabilitado."""
        client = OnlineLearningClient(
            "technical", online_learning_enabled=False
        )

        assert client.is_online_model_available() is False

    def test_available_when_model_loaded(self):
        """Testa retorna True quando modelo está carregado."""
        client = OnlineLearningClient("technical")
        client._cached_model = {"model": "data"}
        client._cache_timestamp = datetime.now(timezone.utc)

        with patch.object(client, "_is_cache_valid", return_value=True):
            result = client.is_online_model_available()

        assert result is True


@pytest.mark.unit
class TestGetOnlineModelVersion:
    """Testes para get_online_model_version."""

    def test_version_from_loaded_model(self):
        """Testa extração de versão do modelo carregado."""
        client = OnlineLearningClient("technical")
        expected_version = "v2.5"

        with patch.object(client, "get_online_model", return_value={"model_version": expected_version}):
            version = client.get_online_model_version()

        assert version == expected_version

    def test_version_none_when_no_model(self):
        """Testa retorna None quando não há modelo."""
        client = OnlineLearningClient("technical")

        with patch.object(client, "get_online_model", return_value=None):
            version = client.get_online_model_version()

        assert version is None
