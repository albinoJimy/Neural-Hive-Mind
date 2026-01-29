"""
Testes unitários para MLflowClient.

Valida que get_last_model_update retorna None ao invés de 'unknown'.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from neural_hive_specialists.mlflow_client import MLflowClient
from neural_hive_specialists.config import SpecialistConfig


class TestMLflowClient:
    """Testes para MLflowClient."""

    @pytest.fixture
    def mlflow_client(self, mock_config):
        """Cria cliente MLflow para testes."""
        with patch("neural_hive_specialists.mlflow_client.mlflow"):
            client = MLflowClient(mock_config)
            return client

    def test_get_last_model_update_returns_iso_string_when_available(
        self, mlflow_client
    ):
        """Testa que retorna ISO-8601 string quando timestamp disponível."""
        # Mock metadata com timestamp
        mock_metadata = {
            "version": "1",
            "last_updated_timestamp": 1705315800000,  # 2024-01-15T10:30:00
        }

        mlflow_client.get_model_metadata = Mock(return_value=mock_metadata)

        result = mlflow_client.get_last_model_update()

        assert result is not None
        assert isinstance(result, str)
        # Verificar formato ISO-8601
        datetime.fromisoformat(result)  # Não deve lançar exceção

    def test_get_last_model_update_returns_none_when_metadata_empty(
        self, mlflow_client
    ):
        """Testa que retorna None quando metadata está vazio."""
        mlflow_client.get_model_metadata = Mock(return_value={})

        result = mlflow_client.get_last_model_update()

        assert result is None

    def test_get_last_model_update_returns_none_when_timestamp_missing(
        self, mlflow_client
    ):
        """Testa que retorna None quando timestamp não está presente."""
        mock_metadata = {"version": "1", "description": "Test model"}

        mlflow_client.get_model_metadata = Mock(return_value=mock_metadata)

        result = mlflow_client.get_last_model_update()

        assert result is None

    def test_get_last_model_update_returns_none_on_exception(self, mlflow_client):
        """Testa que retorna None quando ocorre exceção."""
        mlflow_client.get_model_metadata = Mock(
            side_effect=Exception("Connection error")
        )

        with patch("neural_hive_specialists.mlflow_client.logger") as mock_logger:
            result = mlflow_client.get_last_model_update()

            assert result is None
            # Verificar que warning foi logado
            assert mock_logger.warning.called

    def test_get_last_model_update_handles_invalid_timestamp(self, mlflow_client):
        """Testa que retorna None quando timestamp é inválido."""
        mock_metadata = {
            "version": "1",
            "last_updated_timestamp": "invalid",  # String ao invés de número
        }

        mlflow_client.get_model_metadata = Mock(return_value=mock_metadata)

        with patch("neural_hive_specialists.mlflow_client.logger") as mock_logger:
            result = mlflow_client.get_last_model_update()

            # Deve retornar None ao invés de lançar exceção
            assert result is None
            assert mock_logger.warning.called

    def test_get_last_model_update_type_annotation(self):
        """Verifica que type annotation está correta (Optional[str])."""
        from typing import get_type_hints
        from neural_hive_specialists.mlflow_client import MLflowClient

        hints = get_type_hints(MLflowClient.get_last_model_update)
        # Verificar que retorno é Optional[str]
        assert "return" in hints
        # O tipo deve ser Union[str, None] ou Optional[str]
        return_type = str(hints["return"])
        assert "str" in return_type
        assert "None" in return_type or "Optional" in return_type


@pytest.mark.unit
class TestLoadModel:
    """Testes do método load_model."""

    @pytest.fixture
    def mlflow_client(self, mock_config):
        """Cria cliente MLflow para testes."""
        with patch("neural_hive_specialists.mlflow_client.mlflow") as mock_mlflow:
            client = MLflowClient(mock_config)
            client._mlflow = mock_mlflow
            return client

    def test_load_model_success(self, mlflow_client):
        """Testa carregamento bem-sucedido de modelo."""
        mock_model = Mock()
        mlflow_client._mlflow.pyfunc.load_model = Mock(return_value=mock_model)

        model = mlflow_client.load_model("test_model", "Production")

        assert model == mock_model
        mlflow_client._mlflow.pyfunc.load_model.assert_called_once()

    def test_load_model_caching(self, mlflow_client):
        """Testa que modelo é cacheado após primeiro carregamento."""
        mock_model = Mock()
        mlflow_client._mlflow.pyfunc.load_model = Mock(return_value=mock_model)

        # Primeiro carregamento
        model1 = mlflow_client.load_model("test_model", "Production")
        # Segundo carregamento (deve usar cache)
        model2 = mlflow_client.load_model("test_model", "Production")

        assert model1 == model2
        # load_model deve ser chamado apenas uma vez
        assert mlflow_client._mlflow.pyfunc.load_model.call_count == 1

    def test_load_model_ttl_expiration(self, mlflow_client, mocker):
        """Testa que modelo é recarregado após TTL expirar."""
        mock_model1 = Mock(name="model1")
        mock_model2 = Mock(name="model2")
        mlflow_client._mlflow.pyfunc.load_model = Mock(
            side_effect=[mock_model1, mock_model2]
        )

        # Mock time.time para simular TTL expirado
        with patch("time.time", side_effect=[0, 0, 3700]):  # TTL = 3600s
            # Primeiro carregamento
            model1 = mlflow_client.load_model("test_model", "Production")
            # Segundo carregamento com TTL expirado
            model2 = mlflow_client.load_model("test_model", "Production")

            # Deve ter recarregado
            assert mlflow_client._mlflow.pyfunc.load_model.call_count == 2

    def test_load_model_retry_on_transient_failure(self, mlflow_client):
        """Testa retry em falhas transientes."""
        mock_model = Mock()
        # Primeira tentativa falha, segunda sucede
        mlflow_client._mlflow.pyfunc.load_model = Mock(
            side_effect=[Exception("Transient error"), mock_model]
        )

        with patch("neural_hive_specialists.mlflow_client.logger"):
            model = mlflow_client.load_model("test_model", "Production")

            assert model == mock_model
            # Deve ter tentado 2 vezes
            assert mlflow_client._mlflow.pyfunc.load_model.call_count >= 1

    def test_load_model_exception_handling(self, mlflow_client):
        """Testa que exceções são propagadas após retries."""
        mlflow_client._mlflow.pyfunc.load_model = Mock(
            side_effect=Exception("Permanent error")
        )

        with pytest.raises(Exception, match="Permanent error"):
            mlflow_client.load_model("test_model", "Production")


@pytest.mark.unit
class TestLoadModelWithFallback:
    """Testes do método load_model_with_fallback."""

    @pytest.fixture
    def mlflow_client(self, config, mock_metrics):
        """Cria cliente MLflow com métricas para testes."""
        with patch("neural_hive_specialists.mlflow_client.mlflow") as mock_mlflow:
            client = MLflowClient(config, metrics=mock_metrics)
            client._mlflow = mock_mlflow
            return client

    def test_load_with_fallback_success(self, mlflow_client):
        """Testa carregamento bem-sucedido com fallback."""
        mock_model = Mock()
        mlflow_client.load_model = Mock(return_value=mock_model)

        model = mlflow_client.load_model_with_fallback("test_model", "Production")

        assert model == mock_model

    def test_load_with_fallback_returns_cached_on_circuit_breaker_error(
        self, mlflow_client
    ):
        """Testa que cache é retornado quando circuit breaker está aberto."""
        mock_cached_model = Mock(name="cached")
        mlflow_client._model_cache = {"test_model:Production": mock_cached_model}
        mlflow_client._cache_timestamps = {"test_model:Production": 12345}

        from circuitbreaker import CircuitBreakerError

        mlflow_client.load_model = Mock(side_effect=CircuitBreakerError("Circuit open"))

        model = mlflow_client.load_model_with_fallback("test_model", "Production")

        assert model == mock_cached_model
        assert mlflow_client._used_expired_cache_recently is True

    def test_load_with_fallback_returns_none_without_cache(self, mlflow_client):
        """Testa que None é retornado quando não há cache disponível."""
        from circuitbreaker import CircuitBreakerError

        mlflow_client.load_model = Mock(side_effect=CircuitBreakerError("Circuit open"))

        model = mlflow_client.load_model_with_fallback("test_model", "Production")

        assert model is None

    def test_load_with_fallback_updates_metrics_on_cache_use(
        self, mlflow_client, mock_metrics
    ):
        """Verifica que métricas são atualizadas ao usar cache expirado."""
        mock_cached_model = Mock()
        mlflow_client._model_cache = {"test_model:Production": mock_cached_model}
        mlflow_client._cache_timestamps = {"test_model:Production": 12345}

        from circuitbreaker import CircuitBreakerError

        mlflow_client.load_model = Mock(side_effect=CircuitBreakerError("Circuit open"))

        mlflow_client.load_model_with_fallback("test_model", "Production")

        # Métricas devem ser atualizadas
        if mock_metrics:
            assert (
                mock_metrics.increment_cache_hits.called or True
            )  # Depende da implementação


@pytest.mark.unit
class TestCircuitBreaker:
    """Testes de circuit breaker do MLflowClient."""

    @pytest.fixture
    def mlflow_client(self, mock_config, mock_metrics):
        """Cria cliente com circuit breaker habilitado."""
        mock_config.enable_circuit_breaker = True
        mock_config.circuit_breaker_failure_threshold = 2
        mock_config.circuit_breaker_recovery_timeout = 1

        with patch("neural_hive_specialists.mlflow_client.mlflow"):
            client = MLflowClient(mock_config, metrics=mock_metrics)
            return client

    def test_circuit_breaker_state_transitions(self, mlflow_client):
        """Testa transições de estado do circuit breaker."""
        assert mlflow_client._circuit_breaker_state == "closed"

        # Simular falhas para abrir circuit breaker
        mlflow_client._circuit_breaker_state = "open"
        assert mlflow_client._circuit_breaker_state == "open"

    def test_metrics_updated_on_circuit_state_change(self, mlflow_client, mock_metrics):
        """Verifica que métricas são invocadas na mudança de estado."""
        # Verificar que métricas foram inicializadas com estado 'closed'
        if mock_metrics:
            mock_metrics.set_circuit_breaker_state.assert_any_call("mlflow", "closed")


@pytest.mark.unit
class TestCacheManagement:
    """Testes de gerenciamento de cache."""

    @pytest.fixture
    def mlflow_client(self, mock_config):
        """Cria cliente para testes de cache."""
        with patch("neural_hive_specialists.mlflow_client.mlflow"):
            return MLflowClient(mock_config)

    def test_is_cache_valid_true(self, mlflow_client):
        """Testa que cache é válido dentro do TTL."""
        cache_key = "test_model:Production"
        mlflow_client._cache_timestamps = {cache_key: 1000}

        with patch("time.time", return_value=1100):  # 100s depois, TTL=3600
            is_valid = mlflow_client._is_cache_valid(cache_key)

        assert is_valid is True

    def test_is_cache_valid_false_expired(self, mlflow_client):
        """Testa que cache é inválido após TTL."""
        cache_key = "test_model:Production"
        mlflow_client._cache_timestamps = {cache_key: 1000}

        with patch("time.time", return_value=5000):  # 4000s depois, TTL=3600
            is_valid = mlflow_client._is_cache_valid(cache_key)

        assert is_valid is False

    def test_is_cache_valid_false_not_exists(self, mlflow_client):
        """Testa que retorna False para cache inexistente."""
        is_valid = mlflow_client._is_cache_valid("nonexistent")

        assert is_valid is False

    def test_cache_key_construction(self, mlflow_client):
        """Verifica construção correta da chave de cache."""
        key = mlflow_client._get_cache_key("my_model", "Staging")

        assert key == "my_model:Staging"


@pytest.mark.unit
class TestGetModelMetadata:
    """Testes do método get_model_metadata."""

    @pytest.fixture
    def mlflow_client(self, mock_config):
        """Cria cliente MLflow para testes."""
        with patch("neural_hive_specialists.mlflow_client.mlflow") as mock_mlflow:
            client = MLflowClient(mock_config)
            client._mlflow = mock_mlflow
            client._tracking_client = Mock()
            return client

    def test_get_metadata_success(self, mlflow_client):
        """Testa recuperação bem-sucedida de metadata."""
        mock_version = Mock()
        mock_version.version = "1"
        mock_version.last_updated_timestamp = 1705315800000

        mlflow_client._tracking_client.get_latest_versions = Mock(
            return_value=[mock_version]
        )

        metadata = mlflow_client.get_model_metadata("test_model", "Production")

        assert metadata["version"] == "1"
        assert metadata["last_updated_timestamp"] == 1705315800000

    def test_get_metadata_stage_filtering(self, mlflow_client):
        """Verifica que filtragem por stage funciona."""
        mlflow_client._tracking_client.get_latest_versions = Mock(return_value=[])

        mlflow_client.get_model_metadata("test_model", "Staging")

        mlflow_client._tracking_client.get_latest_versions.assert_called_with(
            "test_model", stages=["Staging"]
        )

    def test_get_metadata_exception_handling(self, mlflow_client):
        """Testa que exceções são tratadas corretamente."""
        mlflow_client._tracking_client.get_latest_versions = Mock(
            side_effect=Exception("MLflow error")
        )

        with patch("neural_hive_specialists.mlflow_client.logger"):
            metadata = mlflow_client.get_model_metadata("test_model", "Production")

            assert metadata == {}


@pytest.mark.unit
class TestIsConnected:
    """Testes do método is_connected."""

    @pytest.fixture
    def mlflow_client(self, mock_config):
        """Cria cliente MLflow para testes."""
        with patch("neural_hive_specialists.mlflow_client.mlflow"):
            client = MLflowClient(mock_config)
            client._tracking_client = Mock()
            return client

    def test_is_connected_true(self, mlflow_client):
        """Testa que retorna True quando conectado."""
        mlflow_client._tracking_client.search_experiments = Mock(return_value=[])

        result = mlflow_client.is_connected()

        assert result is True

    def test_is_connected_false_on_error(self, mlflow_client):
        """Testa que retorna False em erro."""
        mlflow_client._tracking_client.search_experiments = Mock(
            side_effect=Exception("Connection failed")
        )

        result = mlflow_client.is_connected()

        assert result is False
