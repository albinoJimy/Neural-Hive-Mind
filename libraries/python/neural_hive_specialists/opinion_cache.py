"""
OpinionCache: Cache distribuído Redis para pareceres de especialistas.

Usa RedisCluster para cache de alta disponibilidade com TTL configurável,
permitindo recuperação rápida de pareceres para planos idênticos.
"""

import json
import hashlib
import time
from typing import Dict, Any, Optional
import structlog
from redis.cluster import RedisCluster
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

logger = structlog.get_logger(__name__)


class OpinionCache:
    """
    Cache distribuído para pareceres de especialistas.

    Usa RedisCluster para armazenar pareceres com TTL, permitindo
    que planos idênticos sejam avaliados instantaneamente.
    """

    def __init__(
        self,
        redis_cluster_nodes: str,
        redis_password: Optional[str] = None,
        redis_ssl_enabled: bool = False,
        cache_ttl_seconds: int = 3600,
        key_prefix: str = "opinion:",
        specialist_type: str = "unknown",
    ):
        """
        Inicializa OpinionCache.

        Args:
            redis_cluster_nodes: Nodes do cluster Redis (formato: host1:port1,host2:port2)
            redis_password: Senha do Redis (opcional)
            redis_ssl_enabled: Habilitar SSL para Redis
            cache_ttl_seconds: TTL padrão para cache (default 3600 = 1h)
            key_prefix: Prefixo para chaves Redis (default "opinion:")
            specialist_type: Tipo do especialista (para logging)
        """
        self.cache_ttl_seconds = cache_ttl_seconds
        self.key_prefix = key_prefix
        self.specialist_type = specialist_type
        self.redis_client = None
        self._connected = False

        # Inicializar RedisCluster
        try:
            nodes = []
            for node in redis_cluster_nodes.split(","):
                host, port = node.strip().split(":")
                nodes.append({"host": host, "port": int(port)})

            self.redis_client = RedisCluster(
                startup_nodes=nodes,
                password=redis_password,
                ssl=redis_ssl_enabled,
                decode_responses=True,
                skip_full_coverage_check=True,  # Para ambientes de desenvolvimento
            )

            # Testar conexão
            self.redis_client.ping()
            self._connected = True

            logger.info(
                "Opinion cache initialized",
                specialist_type=specialist_type,
                nodes=len(nodes),
                ttl_seconds=cache_ttl_seconds,
            )
        except Exception as e:
            logger.warning(
                "Failed to initialize opinion cache - continuing without cache",
                specialist_type=specialist_type,
                error=str(e),
            )
            self.redis_client = None
            self._connected = False

    def generate_cache_key(
        self,
        plan_bytes: bytes,
        specialist_type: str,
        specialist_version: str,
        tenant_id: Optional[str] = None,
    ) -> str:
        """
        Gera chave de cache determinística baseada no plano, versão e tenant.

        Usa SHA-256 completo do plano + tipo + versão + tenant para garantir que:
        - Planos idênticos geram mesma chave
        - Versões diferentes de especialistas geram chaves diferentes
        - Tenants diferentes geram chaves diferentes (isolamento)
        - Chaves são únicas e uniformemente distribuídas
        - Risco mínimo de colisão (SHA-256 completo)

        Args:
            plan_bytes: Plano cognitivo serializado (bytes)
            specialist_type: Tipo do especialista (technical, business, etc.)
            specialist_version: Versão do especialista (semver)
            tenant_id: ID do tenant (opcional, default 'default')

        Returns:
            Chave de cache no formato: {prefix}{tenant_id}:{specialist_type}:{version}:{hash}
        """
        # Usar tenant padrão se não fornecido
        tenant = tenant_id or "default"

        # Calcular hash SHA-256 completo do plano (64 caracteres hexadecimais)
        plan_hash = hashlib.sha256(plan_bytes).hexdigest()

        # Construir chave com prefixo, tenant, tipo, versão e hash
        cache_key = f"{self.key_prefix}{tenant}:{specialist_type}:{specialist_version}:{plan_hash}"

        logger.debug(
            "Cache key generated",
            tenant_id=tenant,
            specialist_type=specialist_type,
            version=specialist_version,
            plan_hash=plan_hash[:16],  # Log apenas primeiros 16 chars
            cache_key_prefix=cache_key[:50],  # Log apenas prefixo
        )

        return cache_key

    def get_cached_opinion(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Recupera parecer do cache.

        Args:
            cache_key: Chave de cache gerada por generate_cache_key()

        Returns:
            Dicionário com parecer ou None se não encontrado/erro
        """
        if not self._connected or not self.redis_client:
            return None

        try:
            start_time = time.time()
            cached_json = self.redis_client.get(cache_key)
            duration = time.time() - start_time

            if cached_json:
                opinion = json.loads(cached_json)
                logger.debug(
                    "Cache hit", cache_key=cache_key, duration_ms=int(duration * 1000)
                )
                return opinion
            else:
                logger.debug(
                    "Cache miss", cache_key=cache_key, duration_ms=int(duration * 1000)
                )
                return None

        except (RedisError, RedisConnectionError) as e:
            logger.warning(
                "Redis error during cache get", cache_key=cache_key, error=str(e)
            )
            return None
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to decode cached opinion", cache_key=cache_key, error=str(e)
            )
            # Invalidar cache corrompido
            self.invalidate_cache(cache_key)
            return None
        except Exception as e:
            logger.error(
                "Unexpected error during cache get",
                cache_key=cache_key,
                error=str(e),
                exc_info=True,
            )
            return None

    def set_cached_opinion(
        self, cache_key: str, opinion: Dict[str, Any], ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Salva parecer no cache com TTL.

        Args:
            cache_key: Chave de cache
            opinion: Parecer a ser cacheado
            ttl_seconds: TTL customizado (usa default se None)

        Returns:
            True se salvou com sucesso, False caso contrário
        """
        if not self._connected or not self.redis_client:
            return False

        try:
            start_time = time.time()
            ttl = ttl_seconds or self.cache_ttl_seconds

            # Serializar parecer
            opinion_json = json.dumps(opinion, default=str)

            # Salvar com TTL
            self.redis_client.setex(cache_key, ttl, opinion_json)

            duration = time.time() - start_time

            logger.debug(
                "Opinion cached",
                cache_key=cache_key,
                ttl_seconds=ttl,
                size_bytes=len(opinion_json),
                duration_ms=int(duration * 1000),
            )

            return True

        except (RedisError, RedisConnectionError) as e:
            logger.warning(
                "Redis error during cache set", cache_key=cache_key, error=str(e)
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error during cache set",
                cache_key=cache_key,
                error=str(e),
                exc_info=True,
            )
            return False

    def invalidate_cache(self, cache_key: str) -> bool:
        """
        Invalida (remove) entrada do cache.

        Args:
            cache_key: Chave de cache a ser removida

        Returns:
            True se removeu com sucesso, False caso contrário
        """
        if not self._connected or not self.redis_client:
            return False

        try:
            deleted = self.redis_client.delete(cache_key)
            logger.debug("Cache invalidated", cache_key=cache_key, deleted=deleted > 0)
            return deleted > 0
        except Exception as e:
            logger.warning(
                "Failed to invalidate cache", cache_key=cache_key, error=str(e)
            )
            return False

    def is_connected(self) -> bool:
        """
        Verifica se cache está conectado e operacional.

        Returns:
            True se conectado, False caso contrário
        """
        if not self._connected or not self.redis_client:
            return False

        try:
            self.redis_client.ping()
            return True
        except Exception:
            self._connected = False
            return False

    def close(self):
        """Fecha conexão Redis."""
        try:
            if self.redis_client:
                self.redis_client.close()
                self._connected = False
                logger.info(
                    "Opinion cache connection closed",
                    specialist_type=self.specialist_type,
                )
        except Exception as e:
            logger.warning(
                "Error closing opinion cache",
                specialist_type=self.specialist_type,
                error=str(e),
            )
