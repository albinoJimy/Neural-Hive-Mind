"""
FeatureStore: Persistência e cache de features extraídas.

Usa MongoDB para persistência e Redis para cache em memória,
permitindo recuperação rápida de features para inferência e análise.
"""

import json
import time
from typing import Dict, Any, Optional
import structlog
from pymongo import MongoClient
from redis.cluster import RedisCluster

logger = structlog.get_logger(__name__)


class NumpyEncoder(json.JSONEncoder):
    """Encoder JSON que suporta arrays NumPy."""

    def default(self, obj):
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return super().default(obj)


class FeatureStore:
    """
    Armazena e recupera features extraídas de planos cognitivos.

    Usa MongoDB para persistência durável e Redis para cache rápido.
    """

    def __init__(
        self,
        mongodb_uri: str,
        mongodb_database: str,
        redis_cluster_nodes: str,
        redis_password: Optional[str] = None,
        redis_ssl_enabled: bool = False,
        cache_ttl_seconds: int = 3600
    ):
        """
        Inicializa Feature Store.

        Args:
            mongodb_uri: URI de conexão MongoDB
            mongodb_database: Nome do database MongoDB
            redis_cluster_nodes: Nodes do cluster Redis (formato: host1:port1,host2:port2)
            redis_password: Senha do Redis (opcional)
            redis_ssl_enabled: Habilitar SSL para Redis
            cache_ttl_seconds: TTL para cache Redis
        """
        self.cache_ttl_seconds = cache_ttl_seconds

        # Inicializar MongoDB
        try:
            self.mongo_client = MongoClient(mongodb_uri)
            self.db = self.mongo_client[mongodb_database]
            self.features_collection = self.db['plan_features']

            # Criar índice em plan_id para busca rápida
            self.features_collection.create_index('plan_id', unique=True)

            logger.info("MongoDB feature store initialized", database=mongodb_database)
        except Exception as e:
            logger.error("Failed to initialize MongoDB for feature store", error=str(e))
            raise

        # Inicializar Redis
        try:
            nodes = []
            for node in redis_cluster_nodes.split(','):
                host, port = node.strip().split(':')
                nodes.append({'host': host, 'port': int(port)})

            self.redis_client = RedisCluster(
                startup_nodes=nodes,
                password=redis_password,
                ssl=redis_ssl_enabled,
                decode_responses=True
            )

            # Testar conexão
            self.redis_client.ping()

            logger.info("Redis feature cache initialized", nodes=len(nodes))
        except Exception as e:
            logger.warning("Failed to initialize Redis for feature cache", error=str(e))
            self.redis_client = None

    def save_features(self, plan_id: str, features: Dict[str, Any]) -> bool:
        """
        Salva features de um plano.

        Args:
            plan_id: ID do plano cognitivo
            features: Features extraídas (dicionário com arrays, listas, etc.)

        Returns:
            True se salvou com sucesso
        """
        try:
            # Serializar features para JSON (usando NumpyEncoder)
            features_json = json.dumps(features, cls=NumpyEncoder)

            # Salvar no MongoDB
            document = {
                'plan_id': plan_id,
                'features': features_json,
                'timestamp': time.time()
            }

            self.features_collection.replace_one(
                {'plan_id': plan_id},
                document,
                upsert=True
            )

            logger.debug("Features saved to MongoDB", plan_id=plan_id)

            # Salvar no Redis (cache)
            if self.redis_client:
                cache_key = f"features:{plan_id}"
                self.redis_client.setex(
                    cache_key,
                    self.cache_ttl_seconds,
                    features_json
                )
                logger.debug("Features cached in Redis", plan_id=plan_id)

            return True

        except Exception as e:
            logger.error("Failed to save features", plan_id=plan_id, error=str(e))
            return False

    def get_features(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera features de um plano.

        Tenta primeiro do cache Redis, depois do MongoDB.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            Dicionário de features ou None se não encontrado
        """
        # Tentar cache Redis primeiro
        if self.redis_client:
            try:
                cache_key = f"features:{plan_id}"
                cached = self.redis_client.get(cache_key)

                if cached:
                    logger.debug("Features retrieved from Redis cache", plan_id=plan_id)
                    return json.loads(cached)

            except Exception as e:
                logger.warning("Failed to retrieve from Redis cache", plan_id=plan_id, error=str(e))

        # Fallback para MongoDB
        try:
            document = self.features_collection.find_one({'plan_id': plan_id})

            if document:
                features = json.loads(document['features'])
                logger.debug("Features retrieved from MongoDB", plan_id=plan_id)

                # Re-popular cache Redis
                if self.redis_client:
                    try:
                        cache_key = f"features:{plan_id}"
                        self.redis_client.setex(
                            cache_key,
                            self.cache_ttl_seconds,
                            document['features']
                        )
                    except:
                        pass

                return features

            logger.debug("Features not found", plan_id=plan_id)
            return None

        except Exception as e:
            logger.error("Failed to retrieve features from MongoDB", plan_id=plan_id, error=str(e))
            return None

    def delete_features(self, plan_id: str) -> bool:
        """
        Remove features de um plano.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            True se removeu com sucesso
        """
        try:
            # Remover do MongoDB
            self.features_collection.delete_one({'plan_id': plan_id})

            # Remover do Redis
            if self.redis_client:
                cache_key = f"features:{plan_id}"
                self.redis_client.delete(cache_key)

            logger.debug("Features deleted", plan_id=plan_id)
            return True

        except Exception as e:
            logger.error("Failed to delete features", plan_id=plan_id, error=str(e))
            return False

    def close(self):
        """Fecha conexões."""
        try:
            if self.mongo_client:
                self.mongo_client.close()
            if self.redis_client:
                self.redis_client.close()
            logger.info("Feature store connections closed")
        except Exception as e:
            logger.warning("Error closing feature store", error=str(e))
