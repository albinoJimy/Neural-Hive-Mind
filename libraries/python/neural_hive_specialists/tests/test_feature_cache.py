"""Testes para FeatureCache."""

import json
import pytest
from unittest.mock import patch, MagicMock
from redis.exceptions import RedisError

from neural_hive_specialists.feature_cache import FeatureCache


@pytest.fixture
def mock_redis():
    """Mock de RedisCluster."""
    with patch("neural_hive_specialists.feature_cache.RedisCluster") as mock:
        redis_instance = MagicMock()
        mock.return_value = redis_instance
        redis_instance.ping.return_value = True
        redis_instance.get.return_value = None
        redis_instance.setex.return_value = True
        redis_instance.delete.return_value = 1
        redis_instance.scan.return_value = (0, [])
        yield redis_instance


@pytest.fixture
def feature_cache(mock_redis):
    """FeatureCache para testes."""
    return FeatureCache(
        redis_cluster_nodes="localhost:6379",
        redis_password=None,
        cache_ttl_seconds=3600,
        specialist_type="technical",
    )


@pytest.mark.unit
class TestFeatureCacheInit:
    """Testes de inicialização."""

    @patch("neural_hive_specialists.feature_cache.RedisCluster")
    def test_init_success(self, mock_redis_class):
        """Testa inicialização bem-sucedida."""
        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        cache = FeatureCache(
            redis_cluster_nodes="localhost:6379",
            specialist_type="technical",
        )

        assert cache.specialist_type == "technical"
        assert cache.cache_ttl_seconds == 3600
        assert cache._connected is True

    @patch("neural_hive_specialists.feature_cache.RedisCluster")
    def test_init_with_custom_ttl(self, mock_redis_class):
        """Testa inicialização com TTL customizado."""
        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        cache = FeatureCache(
            redis_cluster_nodes="localhost:6379",
            cache_ttl_seconds=7200,
            specialist_type="technical",
        )

        assert cache.cache_ttl_seconds == 7200

    @patch("neural_hive_specialists.feature_cache.RedisCluster")
    def test_init_multiple_nodes(self, mock_redis_class):
        """Testa inicialização com múltiplos nodes."""
        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        cache = FeatureCache(
            redis_cluster_nodes="localhost:6379,localhost:6380,localhost:6381",
            specialist_type="business",
        )

        assert cache._connected is True

    @patch("neural_hive_specialists.feature_cache.RedisCluster")
    def test_init_redis_connection_fails(self, mock_redis_class):
        """Testa falha de conexão com Redis."""
        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.side_effect = RedisError("Connection refused")

        cache = FeatureCache(
            redis_cluster_nodes="localhost:6379",
            specialist_type="technical",
        )

        assert cache._connected is False
        assert cache.redis is None


@pytest.mark.unit
class TestGenerateCacheKey:
    """Testes para _generate_cache_key."""

    def test_generate_cache_key(self, feature_cache):
        """Testa geração de chave de cache."""
        key = feature_cache._generate_cache_key("plan123")

        assert key == "features:technical:plan123"

    @patch("neural_hive_specialists.feature_cache.RedisCluster")
    def test_generate_cache_key_different_specialist(self, mock_redis_class):
        """Testa chave para diferente especialista."""
        mock_redis_instance = MagicMock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        cache = FeatureCache(
            redis_cluster_nodes="localhost:6379",
            specialist_type="business",
        )
        key = cache._generate_cache_key("plan123")

        assert key == "features:business:plan123"


@pytest.mark.unit
class TestGet:
    """Testes para get."""

    def test_get_cache_miss(self, feature_cache, mock_redis):
        """Testa cache miss."""
        mock_redis.get.return_value = None

        result = feature_cache.get("plan123")

        assert result is None

    def test_get_cache_hit(self, feature_cache, mock_redis):
        """Testa cache hit."""
        features = {
            "metadata_features": {"complexity": 0.5},
            "aggregated_features": {"total_tasks": 5},
        }
        mock_redis.get.return_value = json.dumps(features)

        result = feature_cache.get("plan123")

        assert result["metadata_features"]["complexity"] == 0.5
        assert result["aggregated_features"]["total_tasks"] == 5

    def test_get_not_connected(self, feature_cache, mock_redis):
        """Testa get quando não conectado."""
        feature_cache._connected = False
        feature_cache.redis = None

        result = feature_cache.get("plan123")

        assert result is None

    def test_get_redis_error(self, feature_cache, mock_redis):
        """Testa get com erro do Redis."""
        mock_redis.get.side_effect = RedisError("Connection error")

        result = feature_cache.get("plan123")

        assert result is None

    def test_get_json_decode_error(self, feature_cache, mock_redis):
        """Testa get com JSON inválido."""
        mock_redis.get.return_value = "invalid json"

        result = feature_cache.get("plan123")

        assert result is None


@pytest.mark.unit
class TestSet:
    """Testes para set."""

    def test_set_success(self, feature_cache, mock_redis):
        """Testa armazenamento bem-sucedido."""
        features = {
            "metadata_features": {"complexity": 0.5},
            "ontology_features": {},
            "graph_features": {},
            "aggregated_features": {"total_tasks": 5},
        }

        result = feature_cache.set("plan123", features)

        assert result is True
        mock_redis.setex.assert_called_once()

    def test_set_not_connected(self, feature_cache, mock_redis):
        """Testa set quando não conectado."""
        feature_cache._connected = False
        feature_cache.redis = None

        result = feature_cache.set("plan123", {})

        assert result is False

    def test_set_redis_error(self, feature_cache, mock_redis):
        """Testa set com erro do Redis."""
        mock_redis.setex.side_effect = RedisError("Connection error")

        result = feature_cache.set("plan123", {})

        assert result is False

    def test_set_serializes_ontology_features(self, feature_cache, mock_redis):
        """Testa serialização de features de ontologia."""
        from enum import Enum

        class TestEnum(Enum):
            VALUE = 1

        features = {
            "metadata_features": {},
            "ontology_features": {"enum_key": TestEnum.VALUE},
            "graph_features": {},
            "aggregated_features": {},
        }

        result = feature_cache.set("plan123", features)

        assert result is True


@pytest.mark.unit
class TestIsConnected:
    """Testes para is_connected."""

    def test_is_connected_true(self, feature_cache, mock_redis):
        """Testa que está conectado."""
        mock_redis.ping.return_value = True

        result = feature_cache.is_connected()

        assert result is True

    def test_is_connected_false_when_not_flagged(self, feature_cache):
        """Testa que não está conectado quando flag é False."""
        feature_cache._connected = False

        result = feature_cache.is_connected()

        assert result is False

    def test_is_connected_false_on_ping_error(self, feature_cache, mock_redis):
        """Testa que não está conectado quando ping falha."""
        mock_redis.ping.side_effect = RedisError("Connection error")

        result = feature_cache.is_connected()

        assert result is False
        assert feature_cache._connected is False


@pytest.mark.unit
class TestDelete:
    """Testes para delete."""

    def test_delete_success(self, feature_cache, mock_redis):
        """Testa deleção bem-sucedida."""
        mock_redis.delete.return_value = 1

        result = feature_cache.delete("plan123")

        assert result is True

    def test_delete_key_not_found(self, feature_cache, mock_redis):
        """Testa deleção quando chave não existe."""
        mock_redis.delete.return_value = 0

        result = feature_cache.delete("plan123")

        assert result is False

    def test_delete_not_connected(self, feature_cache):
        """Testa delete quando não conectado."""
        feature_cache._connected = False
        feature_cache.redis = None

        result = feature_cache.delete("plan123")

        assert result is False

    def test_delete_redis_error(self, feature_cache, mock_redis):
        """Testa delete com erro do Redis."""
        mock_redis.delete.side_effect = RedisError("Connection error")

        result = feature_cache.delete("plan123")

        assert result is False


@pytest.mark.unit
class TestClearAll:
    """Testes para clear_all."""

    def test_clear_all_empty(self, feature_cache, mock_redis):
        """Testa limpar cache vazio."""
        mock_redis.scan.return_value = (0, [])

        result = feature_cache.clear_all()

        assert result == 0

    def test_clear_all_with_keys(self, feature_cache, mock_redis):
        """Testa limpar cache com chaves."""
        mock_redis.scan.side_effect = [
            (0, ["features:technical:plan1", "features:technical:plan2"]),
            (0, []),
        ]
        mock_redis.delete.return_value = 2

        result = feature_cache.clear_all()

        assert result == 2

    def test_clear_all_not_connected(self, feature_cache):
        """Testa clear_all quando não conectado."""
        feature_cache._connected = False
        feature_cache.redis = None

        result = feature_cache.clear_all()

        assert result == 0

    def test_clear_all_redis_error(self, feature_cache, mock_redis):
        """Testa clear_all com erro do Redis."""
        mock_redis.scan.side_effect = RedisError("Connection error")

        result = feature_cache.clear_all()

        assert result == 0


@pytest.mark.unit
class TestSerializeOntologyFeatures:
    """Testes para _serialize_ontology_features."""

    def test_serialize_empty_features(self, feature_cache):
        """Testa serialização de features vazias."""
        result = feature_cache._serialize_ontology_features({})

        assert result == {}

    def test_serialize_enum_value(self, feature_cache):
        """Testa serialização de Enum."""
        from enum import Enum

        class TestEnum(Enum):
            VALUE = 1

        features = {"enum_key": TestEnum.VALUE}
        result = feature_cache._serialize_ontology_features(features)

        assert result["enum_key"] == 1

    def test_serialize_object_with_dict(self, feature_cache):
        """Testa serialização de objeto com __dict__."""

        class TestClass:
            def __init__(self):
                self.data = "test_data"

        features = {"obj_key": TestClass()}
        result = feature_cache._serialize_ontology_features(features)

        # O objeto tem um atributo 'data', não 'value', então não é tratado como Enum
        # e como tem __dict__, é convertido para string
        assert isinstance(result["obj_key"], str)
        assert "TestClass" in result["obj_key"]

    def test_serialize_primitive_value(self, feature_cache):
        """Testa serialização de valor primitivo."""
        features = {"int_key": 42, "str_key": "value", "float_key": 3.14}
        result = feature_cache._serialize_ontology_features(features)

        assert result["int_key"] == 42
        assert result["str_key"] == "value"
        assert result["float_key"] == 3.14
