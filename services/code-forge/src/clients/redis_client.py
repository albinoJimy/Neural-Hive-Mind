"""
Cliente Redis para cache de templates e state de pipelines.

Fornece interface assíncrona ao Redis para cache de alta performance.
Suporta modo standalone e cluster.
"""

import time
from typing import Optional, Any, Dict, Union, TYPE_CHECKING
from urllib.parse import urlparse
import json
import structlog
from redis.asyncio import Redis, RedisCluster
from redis.asyncio.cluster import ClusterNode
from redis.exceptions import RedisError, RedisClusterException

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class RedisClient:
    """Cliente Redis assíncrono para operações de cache e state."""

    def __init__(
        self,
        url: str,
        cluster_enabled: bool = False,
        ssl_enabled: bool = False,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        """
        Inicializa o cliente Redis.

        Args:
            url: URL de conexão Redis (redis://host:port ou redis://:password@host:port)
            cluster_enabled: Se True, usa RedisCluster
            ssl_enabled: Se True, habilita SSL/TLS
            metrics: Instância de CodeForgeMetrics para instrumentação
        """
        self.url = url
        self.cluster_enabled = cluster_enabled
        self.ssl_enabled = ssl_enabled
        self.client: Optional[Union[Redis, RedisCluster]] = None
        self.metrics = metrics

    async def start(self):
        """Inicia conexão com Redis (standalone ou cluster)."""
        parsed = urlparse(self.url)
        host = parsed.hostname or 'localhost'
        port = parsed.port or 6379
        password = parsed.password

        if self.cluster_enabled:
            await self._start_cluster(host, port, password)
        else:
            await self._start_standalone(host, port, password)

    async def _start_standalone(self, host: str, port: int, password: Optional[str]):
        """Inicia conexão standalone."""
        try:
            self.client = Redis(
                host=host,
                port=port,
                password=password,
                ssl=self.ssl_enabled,
                decode_responses=True
            )

            await self.client.ping()

            logger.info(
                'redis_client_started',
                mode='standalone',
                host=host,
                port=port,
                ssl=self.ssl_enabled
            )

        except RedisError as e:
            logger.error('redis_connection_failed', error=str(e))
            raise

    async def _start_cluster(self, host: str, port: int, password: Optional[str]):
        """Inicia conexão em modo cluster."""
        try:
            startup_nodes = [ClusterNode(host=host, port=port)]

            self.client = RedisCluster(
                startup_nodes=startup_nodes,
                password=password,
                ssl=self.ssl_enabled,
                decode_responses=True
            )

            await self.client.ping()

            logger.info(
                'redis_client_started',
                mode='cluster',
                host=host,
                port=port,
                ssl=self.ssl_enabled
            )

        except RedisClusterException as e:
            logger.warning(
                'redis_cluster_failed_fallback_standalone',
                error=str(e)
            )
            # Fallback para standalone
            self.cluster_enabled = False
            await self._start_standalone(host, port, password)

    async def stop(self):
        """Fecha conexão com Redis."""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info('redis_client_stopped')

    async def cache_template(self, template_id: str, template: Any, ttl: int = 3600):
        """
        Cacheia template.

        Args:
            template_id: ID do template
            template: Objeto template a cachear
            ttl: Time to live em segundos (padrão: 1 hora)
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        start_time = time.perf_counter()
        try:
            key = f'template:{template_id}'
            value = json.dumps(template, default=str)
            await self.client.setex(key, ttl, value)

            logger.debug('template_cached', template_id=template_id, ttl=ttl)

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.redis_operations_total.labels(operation='cache_template', status='success').inc()
                self.metrics.redis_operation_duration_seconds.labels(operation='cache_template').observe(duration)

        except (RedisError, TypeError, ValueError) as e:
            if self.metrics:
                self.metrics.redis_operations_total.labels(operation='cache_template', status='failure').inc()
            logger.error('cache_template_failed', template_id=template_id, error=str(e))
            raise

    async def get_cached_template(self, template_id: str) -> Optional[Any]:
        """
        Recupera template do cache.

        Args:
            template_id: ID do template

        Returns:
            Template cacheado ou None se não encontrado
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        start_time = time.perf_counter()
        try:
            key = f'template:{template_id}'
            value = await self.client.get(key)

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.redis_operations_total.labels(operation='get_template', status='success').inc()
                self.metrics.redis_operation_duration_seconds.labels(operation='get_template').observe(duration)

            if value:
                logger.debug('template_cache_hit', template_id=template_id)
                if self.metrics:
                    self.metrics.redis_cache_hits_total.inc()
                return json.loads(value)

            logger.debug('template_cache_miss', template_id=template_id)
            if self.metrics:
                self.metrics.redis_cache_misses_total.inc()
            return None

        except RedisError as e:
            if self.metrics:
                self.metrics.redis_operations_total.labels(operation='get_template', status='failure').inc()
            logger.warning('get_cached_template_failed', template_id=template_id, error=str(e))
            return None
        except json.JSONDecodeError as e:
            logger.warning('template_json_decode_error', template_id=template_id, error=str(e))
            return None

    async def invalidate_template(self, template_id: str) -> bool:
        """
        Invalida template do cache.

        Args:
            template_id: ID do template

        Returns:
            True se removido com sucesso
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            key = f'template:{template_id}'
            deleted = await self.client.delete(key)
            logger.debug('template_invalidated', template_id=template_id, deleted=deleted > 0)
            return deleted > 0

        except RedisError as e:
            logger.warning('invalidate_template_failed', template_id=template_id, error=str(e))
            return False

    async def set_pipeline_state(self, pipeline_id: str, state: Dict[str, Any], ttl: int = 86400):
        """
        Salva estado de pipeline.

        Args:
            pipeline_id: ID do pipeline
            state: Dicionário com estado do pipeline
            ttl: Time to live em segundos (padrão: 24 horas)
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        start_time = time.perf_counter()
        try:
            key = f'pipeline:{pipeline_id}'
            # Converte valores para strings para compatibilidade com hset
            string_state = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in state.items()}

            await self.client.hset(key, mapping=string_state)
            await self.client.expire(key, ttl)

            logger.debug('pipeline_state_saved', pipeline_id=pipeline_id)

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.redis_operations_total.labels(operation='set_state', status='success').inc()
                self.metrics.redis_operation_duration_seconds.labels(operation='set_state').observe(duration)

        except RedisError as e:
            if self.metrics:
                self.metrics.redis_operations_total.labels(operation='set_state', status='failure').inc()
            logger.error('set_pipeline_state_failed', pipeline_id=pipeline_id, error=str(e))
            raise

    async def get_pipeline_state(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """
        Recupera estado de pipeline.

        Args:
            pipeline_id: ID do pipeline

        Returns:
            Estado do pipeline ou None se não encontrado
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            key = f'pipeline:{pipeline_id}'
            state = await self.client.hgetall(key)

            if state:
                # Tenta converter valores JSON de volta para objetos
                result = {}
                for k, v in state.items():
                    try:
                        result[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        result[k] = v

                logger.debug('pipeline_state_found', pipeline_id=pipeline_id)
                return result

            logger.debug('pipeline_state_not_found', pipeline_id=pipeline_id)
            return None

        except RedisError as e:
            logger.warning('get_pipeline_state_failed', pipeline_id=pipeline_id, error=str(e))
            return None

    async def update_pipeline_state(self, pipeline_id: str, updates: Dict[str, Any]):
        """
        Atualiza campos específicos do estado de pipeline.

        Args:
            pipeline_id: ID do pipeline
            updates: Campos a atualizar
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            key = f'pipeline:{pipeline_id}'
            string_updates = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in updates.items()}

            await self.client.hset(key, mapping=string_updates)
            logger.debug('pipeline_state_updated', pipeline_id=pipeline_id, fields=list(updates.keys()))

        except RedisError as e:
            logger.error('update_pipeline_state_failed', pipeline_id=pipeline_id, error=str(e))
            raise

    async def delete_pipeline_state(self, pipeline_id: str) -> bool:
        """
        Remove estado de pipeline.

        Args:
            pipeline_id: ID do pipeline

        Returns:
            True se removido com sucesso
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            key = f'pipeline:{pipeline_id}'
            deleted = await self.client.delete(key)
            logger.debug('pipeline_state_deleted', pipeline_id=pipeline_id, deleted=deleted > 0)
            return deleted > 0

        except RedisError as e:
            logger.warning('delete_pipeline_state_failed', pipeline_id=pipeline_id, error=str(e))
            return False

    async def acquire_lock(self, resource_id: str, timeout: int = 30, owner: Optional[str] = None) -> bool:
        """
        Adquire lock distribuído para concorrência.

        Args:
            resource_id: ID do recurso a bloquear
            timeout: Tempo máximo de lock em segundos
            owner: Identificador do owner do lock (opcional)

        Returns:
            True se lock adquirido com sucesso
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        start_time = time.perf_counter()
        try:
            key = f'lock:{resource_id}'
            value = owner or '1'

            # SETNX com expiração atômica
            acquired = await self.client.set(key, value, nx=True, ex=timeout)

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.redis_operations_total.labels(operation='acquire_lock', status='success').inc()
                self.metrics.redis_operation_duration_seconds.labels(operation='acquire_lock').observe(duration)

            if acquired:
                logger.debug('lock_acquired', resource_id=resource_id, timeout=timeout)
                return True

            logger.debug('lock_not_acquired', resource_id=resource_id)
            return False

        except RedisError as e:
            if self.metrics:
                self.metrics.redis_operations_total.labels(operation='acquire_lock', status='failure').inc()
            logger.warning('acquire_lock_failed', resource_id=resource_id, error=str(e))
            return False

    async def release_lock(self, resource_id: str, owner: Optional[str] = None) -> bool:
        """
        Libera lock distribuído.

        Args:
            resource_id: ID do recurso a desbloquear
            owner: Identificador do owner do lock (verifica ownership se fornecido)

        Returns:
            True se lock liberado com sucesso
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            key = f'lock:{resource_id}'

            # Se owner fornecido, verifica ownership antes de deletar
            if owner:
                current_owner = await self.client.get(key)
                if current_owner != owner:
                    logger.warning('lock_release_denied_wrong_owner', resource_id=resource_id)
                    return False

            deleted = await self.client.delete(key)
            released = deleted > 0

            if released:
                logger.debug('lock_released', resource_id=resource_id)
            else:
                logger.debug('lock_not_found', resource_id=resource_id)

            return released

        except RedisError as e:
            logger.warning('release_lock_failed', resource_id=resource_id, error=str(e))
            return False

    async def extend_lock(self, resource_id: str, timeout: int = 30, owner: Optional[str] = None) -> bool:
        """
        Estende tempo de um lock existente.

        Args:
            resource_id: ID do recurso
            timeout: Novo tempo de expiração em segundos
            owner: Verificar ownership antes de estender

        Returns:
            True se lock estendido com sucesso
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            key = f'lock:{resource_id}'

            # Verifica ownership se fornecido
            if owner:
                current_owner = await self.client.get(key)
                if current_owner != owner:
                    logger.warning('lock_extend_denied_wrong_owner', resource_id=resource_id)
                    return False

            extended = await self.client.expire(key, timeout)

            if extended:
                logger.debug('lock_extended', resource_id=resource_id, timeout=timeout)
            else:
                logger.debug('lock_extend_failed_not_found', resource_id=resource_id)

            return bool(extended)

        except RedisError as e:
            logger.warning('extend_lock_failed', resource_id=resource_id, error=str(e))
            return False

    async def set_value(self, key: str, value: str, ttl: Optional[int] = None):
        """
        Armazena valor genérico.

        Args:
            key: Chave
            value: Valor
            ttl: Time to live opcional
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)

            logger.debug('value_stored', key=key, ttl=ttl)

        except RedisError as e:
            logger.error('set_value_failed', key=key, error=str(e))
            raise

    async def get_value(self, key: str) -> Optional[str]:
        """
        Recupera valor genérico.

        Args:
            key: Chave

        Returns:
            Valor ou None
        """
        if not self.client:
            raise RuntimeError('Redis client not started')

        try:
            value = await self.client.get(key)
            if value:
                logger.debug('value_found', key=key)
            return value

        except RedisError as e:
            logger.warning('get_value_failed', key=key, error=str(e))
            return None

    async def health_check(self) -> bool:
        """
        Verifica saúde da conexão.

        Returns:
            True se conexão está saudável
        """
        if not self.client:
            return False

        start_time = time.perf_counter()
        try:
            await self.client.ping()
            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.redis_operations_total.labels(operation='health_check', status='success').inc()
                self.metrics.redis_operation_duration_seconds.labels(operation='health_check').observe(duration)
            return True
        except Exception as e:
            if self.metrics:
                self.metrics.redis_operations_total.labels(operation='health_check', status='failure').inc()
            logger.warning('redis_health_check_failed', error=str(e))
            return False
