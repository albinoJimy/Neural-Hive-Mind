"""
FeatureCache: Cache Redis para features extraídas de planos cognitivos.

Reduz latência de feature extraction de ~3s para ~50ms através de
caching distribuído das features extraídas.
"""

import json
import hashlib
import structlog
from typing import Dict, Any, Optional
from redis import RedisCluster
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)


class FeatureCache:
    """Cache distribuído para features extraídas."""

    def __init__(
        self,
        redis_cluster_nodes: str,
        redis_password: Optional[str] = None,
        redis_ssl_enabled: bool = False,
        cache_ttl_seconds: int = 3600,  # 1 hora
        specialist_type: str = "unknown"
    ):
        """
        Inicializa FeatureCache.

        Args:
            redis_cluster_nodes: Nodes do cluster Redis (formato: "host1:port1,host2:port2")
            redis_password: Senha do Redis (opcional)
            redis_ssl_enabled: Se SSL está habilitado
            cache_ttl_seconds: TTL do cache (default: 1h)
            specialist_type: Tipo do especialista
        """
        self.specialist_type = specialist_type
        self.cache_ttl_seconds = cache_ttl_seconds
        self._connected = False

        try:
            # Configurar Redis Cluster
            nodes = [
                {'host': node.split(':')[0], 'port': int(node.split(':')[1])}
                for node in redis_cluster_nodes.split(',')
            ]

            self.redis = RedisCluster(
                startup_nodes=nodes,
                password=redis_password,
                ssl=redis_ssl_enabled,
                decode_responses=True,
                skip_full_coverage_check=True
            )

            # Testar conexão
            self.redis.ping()
            self._connected = True

            logger.info(
                "FeatureCache initialized",
                specialist_type=specialist_type,
                ttl_seconds=cache_ttl_seconds,
                num_nodes=len(nodes)
            )
        except RedisError as e:
            logger.warning(
                "FeatureCache failed to connect to Redis",
                error=str(e),
                specialist_type=specialist_type
            )
            self.redis = None
            self._connected = False

    def _generate_cache_key(self, plan_hash: str) -> str:
        """Gera chave de cache para features."""
        return f"features:{self.specialist_type}:{plan_hash}"

    def get(self, plan_hash: str) -> Optional[Dict[str, Any]]:
        """
        Busca features no cache.

        Args:
            plan_hash: Hash do plano cognitivo

        Returns:
            Features ou None se não encontrado
        """
        if not self._connected or self.redis is None:
            return None

        cache_key = self._generate_cache_key(plan_hash)

        try:
            cached_data = self.redis.get(cache_key)
            if cached_data:
                features = json.loads(cached_data)
                logger.debug(
                    "feature_cache_hit",
                    plan_hash=plan_hash[:16] + "...",
                    num_features=len(features.get('aggregated_features', {}))
                )
                return features
            else:
                logger.debug("feature_cache_miss", plan_hash=plan_hash[:16] + "...")
                return None
        except RedisError as e:
            logger.warning(
                "feature_cache_get_error",
                plan_hash=plan_hash[:16] + "...",
                error=str(e)
            )
            return None
        except json.JSONDecodeError as e:
            logger.warning(
                "feature_cache_decode_error",
                plan_hash=plan_hash[:16] + "...",
                error=str(e)
            )
            return None

    def set(self, plan_hash: str, features: Dict[str, Any]) -> bool:
        """
        Armazena features no cache.

        Args:
            plan_hash: Hash do plano cognitivo
            features: Features extraídas

        Returns:
            True se sucesso, False caso contrário
        """
        if not self._connected or self.redis is None:
            return False

        cache_key = self._generate_cache_key(plan_hash)

        try:
            # Serializar features (excluir arrays numpy grandes)
            cacheable_features = {
                'metadata_features': features.get('metadata_features', {}),
                'ontology_features': self._serialize_ontology_features(
                    features.get('ontology_features', {})
                ),
                'graph_features': features.get('graph_features', {}),
                'aggregated_features': features.get('aggregated_features', {}),
                # Não cachear embeddings (muito grandes e variam)
            }

            self.redis.setex(
                cache_key,
                self.cache_ttl_seconds,
                json.dumps(cacheable_features)
            )

            logger.debug(
                "feature_cache_set",
                plan_hash=plan_hash[:16] + "...",
                ttl_seconds=self.cache_ttl_seconds
            )
            return True
        except RedisError as e:
            logger.warning(
                "feature_cache_set_error",
                plan_hash=plan_hash[:16] + "...",
                error=str(e)
            )
            return False
        except (TypeError, ValueError) as e:
            logger.warning(
                "feature_cache_serialization_error",
                plan_hash=plan_hash[:16] + "...",
                error=str(e)
            )
            return False

    def _serialize_ontology_features(self, ontology_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serializa features de ontologia, convertendo objetos não-serializáveis.

        Args:
            ontology_features: Features de ontologia

        Returns:
            Features serializáveis
        """
        serialized = {}
        for key, value in ontology_features.items():
            if hasattr(value, 'value'):  # Enum
                serialized[key] = value.value
            elif hasattr(value, '__dict__'):  # Objeto
                serialized[key] = str(value)
            else:
                serialized[key] = value
        return serialized

    def is_connected(self) -> bool:
        """Verifica se Redis está conectado."""
        if not self._connected or self.redis is None:
            return False
        try:
            self.redis.ping()
            return True
        except RedisError:
            self._connected = False
            return False

    def delete(self, plan_hash: str) -> bool:
        """
        Remove features do cache.

        Args:
            plan_hash: Hash do plano cognitivo

        Returns:
            True se removido, False caso contrário
        """
        if not self._connected or self.redis is None:
            return False

        cache_key = self._generate_cache_key(plan_hash)

        try:
            result = self.redis.delete(cache_key)
            return result > 0
        except RedisError as e:
            logger.warning(
                "feature_cache_delete_error",
                plan_hash=plan_hash[:16] + "...",
                error=str(e)
            )
            return False

    def clear_all(self) -> int:
        """
        Limpa todas as features do cache para este especialista.

        Returns:
            Número de chaves removidas
        """
        if not self._connected or self.redis is None:
            return 0

        pattern = f"features:{self.specialist_type}:*"
        count = 0

        try:
            # Scan e delete em batches
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    count += self.redis.delete(*keys)
                if cursor == 0:
                    break

            logger.info(
                "feature_cache_cleared",
                specialist_type=self.specialist_type,
                keys_removed=count
            )
            return count
        except RedisError as e:
            logger.warning(
                "feature_cache_clear_error",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            return count
