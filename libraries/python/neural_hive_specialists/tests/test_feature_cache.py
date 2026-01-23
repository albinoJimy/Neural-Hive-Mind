"""
Testes unitários para FeatureCache.

Testa caching distribuído de features extraídas para otimização de performance.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock


class TestFeatureCache:
    """Testes da classe FeatureCache."""

    @pytest.fixture
    def mock_redis(self):
        """Mock do Redis Cluster."""
        with patch('neural_hive_specialists.feature_cache.RedisCluster') as mock:
            mock_instance = MagicMock()
            mock_instance.ping.return_value = True
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def feature_cache(self, mock_redis):
        """Cria FeatureCache com Redis mockado."""
        from neural_hive_specialists.feature_cache import FeatureCache
        return FeatureCache(
            redis_cluster_nodes='localhost:6379',
            redis_password=None,
            redis_ssl_enabled=False,
            cache_ttl_seconds=3600,
            specialist_type='business'
        )

    def test_cache_init_success(self, mock_redis):
        """Testa inicialização bem-sucedida do cache."""
        from neural_hive_specialists.feature_cache import FeatureCache
        cache = FeatureCache(
            redis_cluster_nodes='localhost:6379',
            specialist_type='business'
        )
        assert cache.is_connected()
        assert cache.specialist_type == 'business'
        assert cache.cache_ttl_seconds == 3600

    def test_cache_init_connection_failure(self):
        """Testa inicialização com falha de conexão."""
        with patch('neural_hive_specialists.feature_cache.RedisCluster') as mock:
            from redis.exceptions import RedisError
            mock.side_effect = RedisError("Connection failed")

            from neural_hive_specialists.feature_cache import FeatureCache
            cache = FeatureCache(
                redis_cluster_nodes='localhost:6379',
                specialist_type='business'
            )
            assert not cache.is_connected()

    def test_cache_hit(self, feature_cache, mock_redis):
        """Testa cache hit - features encontradas no cache."""
        cached_data = {
            'aggregated_features': {'feature1': 0.5, 'feature2': 0.8},
            'metadata_features': {'num_tasks': 5}
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        result = feature_cache.get('test-hash-123')

        assert result is not None
        assert 'aggregated_features' in result
        assert result['aggregated_features']['feature1'] == 0.5
        mock_redis.get.assert_called_once()

    def test_cache_miss(self, feature_cache, mock_redis):
        """Testa cache miss - features não encontradas."""
        mock_redis.get.return_value = None

        result = feature_cache.get('test-hash-456')

        assert result is None
        mock_redis.get.assert_called_once()

    def test_cache_set_success(self, feature_cache, mock_redis):
        """Testa armazenamento bem-sucedido no cache."""
        features = {
            'aggregated_features': {'feature1': 0.5},
            'metadata_features': {'num_tasks': 5},
            'ontology_features': {'domain_id': 'BUSINESS'}
        }

        result = feature_cache.set('test-hash-789', features)

        assert result is True
        mock_redis.setex.assert_called_once()
        # Verificar que TTL foi passado
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 3600  # TTL

    def test_cache_set_serialization_error(self, feature_cache, mock_redis):
        """Testa falha de serialização ao armazenar."""
        from redis.exceptions import RedisError

        # Simular erro do Redis ao tentar setar
        mock_redis.setex.side_effect = RedisError("Connection lost")

        features = {
            'aggregated_features': {'feature1': 0.5}
        }

        result = feature_cache.set('test-hash-bad', features)

        # Deve retornar False em caso de erro de Redis
        assert result is False

    def test_cache_delete(self, feature_cache, mock_redis):
        """Testa remoção de features do cache."""
        mock_redis.delete.return_value = 1

        result = feature_cache.delete('test-hash-delete')

        assert result is True
        mock_redis.delete.assert_called_once()

    def test_cache_key_generation(self, feature_cache):
        """Testa geração de chave de cache."""
        key = feature_cache._generate_cache_key('abc123')
        assert key == 'features:business:abc123'

    def test_cache_ontology_serialization(self, feature_cache):
        """Testa serialização de features de ontologia com enums."""
        # Criar mock de enum
        class MockEnum:
            value = 'BUSINESS_DOMAIN'

        ontology_features = {
            'domain_id': 'BD001',
            'unified_domain': MockEnum(),
            'risk_weight': 0.5
        }

        serialized = feature_cache._serialize_ontology_features(ontology_features)

        assert serialized['domain_id'] == 'BD001'
        assert serialized['unified_domain'] == 'BUSINESS_DOMAIN'
        assert serialized['risk_weight'] == 0.5

    def test_cache_not_connected(self):
        """Testa operações quando cache não está conectado."""
        with patch('neural_hive_specialists.feature_cache.RedisCluster') as mock:
            from redis.exceptions import RedisError
            mock.side_effect = RedisError("Connection failed")

            from neural_hive_specialists.feature_cache import FeatureCache
            cache = FeatureCache(
                redis_cluster_nodes='localhost:6379',
                specialist_type='business'
            )

            # Operações devem retornar None/False graciosamente
            assert cache.get('any-hash') is None
            assert cache.set('any-hash', {}) is False
            assert cache.delete('any-hash') is False


class TestFeatureCacheIntegration:
    """Testes de integração para FeatureCache (requer Redis)."""

    @pytest.mark.skip(reason="Requer Redis cluster rodando")
    def test_real_redis_connection(self):
        """Testa conexão real com Redis."""
        from neural_hive_specialists.feature_cache import FeatureCache
        cache = FeatureCache(
            redis_cluster_nodes='localhost:6379',
            specialist_type='test'
        )

        if cache.is_connected():
            # Testar ciclo completo
            test_features = {'aggregated_features': {'test': 1.0}}
            cache.set('test-key', test_features)
            result = cache.get('test-key')
            assert result is not None
            cache.delete('test-key')
