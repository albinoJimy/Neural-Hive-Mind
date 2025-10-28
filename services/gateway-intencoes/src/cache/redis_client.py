"""
Cliente Redis Cluster para Neural Hive-Mind
Implementa cache distribuído com TTL, circuit breaker e observabilidade
"""

import asyncio
import json
import logging
import ssl
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster, ClusterNode
from redis.exceptions import ConnectionError, TimeoutError, RedisError, RedisClusterException
from opentelemetry import trace
from prometheus_client import Counter, Histogram, Gauge

from config.settings import get_settings


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Métricas Prometheus
redis_operations_total = Counter(
    'redis_operations_total',
    'Total de operações Redis',
    ['operation', 'status', 'intent_type']
)

redis_operation_duration = Histogram(
    'redis_operation_duration_seconds',
    'Duração das operações Redis',
    ['operation'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

redis_hit_ratio = Gauge(
    'redis_hit_ratio',
    'Taxa de acerto do cache Redis'
)

redis_connections = Gauge(
    'redis_connections_active',
    'Conexões Redis ativas'
)

redis_memory_usage = Gauge(
    'redis_memory_usage_bytes',
    'Uso de memória Redis'
)

redis_ssl_connections = Counter(
    'redis_ssl_connections_total',
    'Total de conexões SSL ao Redis',
    ['status']
)

redis_cluster_topology_changes = Counter(
    'redis_cluster_topology_changes_total',
    'Mudanças na topologia do cluster Redis'
)


class CircuitBreakerError(Exception):
    """Erro quando circuit breaker está aberto"""
    pass


class CircuitBreaker:
    """Circuit breaker simples para Redis operations"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if (asyncio.get_event_loop().time() - self.last_failure_time) > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info("Circuit breaker mudou para HALF_OPEN")
                else:
                    raise CircuitBreakerError("Circuit breaker is OPEN")

            try:
                result = await func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.reset()
                return result
            except Exception as e:
                self.record_failure()
                raise e

        return wrapper

    def record_failure(self):
        """Registrar falha e potencialmente abrir circuit breaker"""
        self.failure_count += 1
        self.last_failure_time = asyncio.get_event_loop().time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker ABERTO após {self.failure_count} falhas")

    def reset(self):
        """Reset circuit breaker para estado CLOSED"""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
        logger.info("Circuit breaker RESETADO para CLOSED")


class RedisClient:
    """Cliente Redis Cluster com recursos avançados para Neural Hive-Mind"""

    def __init__(self):
        self.settings = get_settings()
        self.redis: Optional[Union[RedisCluster, Redis]] = None
        self.is_cluster_mode = False  # Track if we're using cluster or standalone
        self.circuit_breaker = CircuitBreaker()
        self.hit_count = 0
        self.miss_count = 0

    async def initialize(self):
        """Inicializar conexão com Redis (cluster ou standalone)"""
        try:
            # Parse nodes
            nodes = []
            for node in self.settings.redis_cluster_nodes.split(","):
                host, port = node.strip().split(":")
                nodes.append({"host": host, "port": int(port)})

            # Determinar se devemos usar cluster mode
            # 1. Se temos múltiplos nodes, tentar cluster
            # 2. Se variável de ambiente REDIS_MODE=standalone, usar standalone
            redis_mode = self.settings.redis_mode if hasattr(self.settings, 'redis_mode') else None
            force_standalone = redis_mode == "standalone"
            use_cluster_mode = len(nodes) > 1 and not force_standalone

            # Configurar SSL se necessário
            ssl_context = None
            ssl_kwargs = {}

            if self.settings.redis_ssl_enabled:
                ssl_context = ssl.create_default_context()

                # Configurar verificação de certificado
                if self.settings.redis_ssl_cert_reqs == "none":
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                elif self.settings.redis_ssl_cert_reqs == "optional":
                    ssl_context.verify_mode = ssl.CERT_OPTIONAL
                else:  # required
                    ssl_context.verify_mode = ssl.CERT_REQUIRED

                # Carregar CA certificates
                if self.settings.redis_ssl_ca_certs:
                    ssl_context.load_verify_locations(cafile=self.settings.redis_ssl_ca_certs)

                # Carregar certificado cliente se fornecido
                if self.settings.redis_ssl_certfile and self.settings.redis_ssl_keyfile:
                    ssl_context.load_cert_chain(
                        certfile=self.settings.redis_ssl_certfile,
                        keyfile=self.settings.redis_ssl_keyfile
                    )

                ssl_kwargs = {
                    "ssl": True,
                    "ssl_ca_certs": self.settings.redis_ssl_ca_certs,
                    "ssl_certfile": self.settings.redis_ssl_certfile,
                    "ssl_keyfile": self.settings.redis_ssl_keyfile,
                    "ssl_cert_reqs": getattr(ssl, f"CERT_{self.settings.redis_ssl_cert_reqs.upper()}")
                }

                logger.info(f"SSL habilitado para Redis. Cert reqs: {self.settings.redis_ssl_cert_reqs}")

            # Suporte a username/password (Redis 6+)
            auth_kwargs = {}
            if self.settings.redis_password:
                auth_kwargs["password"] = self.settings.redis_password

            # Tentar conectar em cluster mode primeiro se múltiplos nodes
            if use_cluster_mode:
                try:
                    logger.info(f"Tentando conectar em Redis Cluster mode com {len(nodes)} nodes...")
                    cluster_nodes = [ClusterNode(host=n["host"], port=n["port"]) for n in nodes]

                    self.redis = RedisCluster(
                        startup_nodes=cluster_nodes,
                        **auth_kwargs,
                        **ssl_kwargs,
                        socket_timeout=self.settings.redis_timeout / 1000,
                        socket_connect_timeout=5.0,
                        decode_responses=True,
                        health_check_interval=30,
                    )

                    # Testar conexão e verificar se cluster está habilitado
                    await self.redis.ping()
                    cluster_info = await self.redis.cluster_info()

                    self.is_cluster_mode = True
                    logger.info(f"✅ Conectado ao Redis Cluster com sucesso. Nodes: {len(nodes)}, SSL: {self.settings.redis_ssl_enabled}")
                    logger.info(f"Cluster info: {cluster_info}")

                except RedisClusterException as e:
                    if "Cluster mode is not enabled" in str(e):
                        logger.warning(f"Redis Cluster mode não habilitado no servidor: {e}")
                        logger.info("Tentando conectar em modo standalone...")
                        use_cluster_mode = False
                    else:
                        raise

            # Usar standalone mode
            if not use_cluster_mode:
                logger.info(f"Conectando em Redis standalone mode...")
                first_node = nodes[0]

                self.redis = Redis(
                    host=first_node["host"],
                    port=first_node["port"],
                    **auth_kwargs,
                    **ssl_kwargs,
                    socket_timeout=self.settings.redis_timeout / 1000,
                    socket_connect_timeout=5.0,
                    decode_responses=True,
                    health_check_interval=30,
                )

                # Testar conexão
                await self.redis.ping()
                self.is_cluster_mode = False
                logger.info(f"✅ Conectado ao Redis standalone com sucesso. Host: {first_node['host']}:{first_node['port']}, SSL: {self.settings.redis_ssl_enabled}")

            # Atualizar métricas
            redis_connections.set(self.settings.redis_connection_pool_max_connections)

            # Rastrear conexões SSL
            if self.settings.redis_ssl_enabled:
                redis_ssl_connections.labels(status="success").inc()
            else:
                redis_ssl_connections.labels(status="plaintext").inc()

        except Exception as e:
            logger.error(f"Erro ao conectar ao Redis: {e}")
            raise

    async def close(self):
        """Fechar conexões Redis"""
        if self.redis:
            await self.redis.close()
            logger.info("Conexões Redis Cluster fechadas")

    async def health_check(self) -> Dict[str, Any]:
        """Verificar saúde do Redis (cluster ou standalone)"""
        try:
            start_time = asyncio.get_event_loop().time()

            if self.is_cluster_mode:
                # Ping all nodes in cluster
                ping_results = {}
                cluster_nodes = await self.redis.cluster_nodes()

                for node_id, node_info in cluster_nodes.items():
                    try:
                        node_client = self.redis.get_node(node_id)
                        await node_client.ping()
                        ping_results[node_id] = {
                            "status": "healthy",
                            "host": node_info.get("host"),
                            "port": node_info.get("port"),
                            "role": node_info.get("role")
                        }
                    except Exception as e:
                        ping_results[node_id] = {
                            "status": "unhealthy",
                            "error": str(e),
                            "host": node_info.get("host"),
                            "port": node_info.get("port"),
                            "role": node_info.get("role")
                        }

                duration = asyncio.get_event_loop().time() - start_time
                healthy_nodes = sum(1 for result in ping_results.values() if result["status"] == "healthy")
                total_nodes = len(ping_results)

                return {
                    "status": "healthy" if healthy_nodes == total_nodes else "degraded",
                    "mode": "cluster",
                    "healthy_nodes": healthy_nodes,
                    "total_nodes": total_nodes,
                    "nodes": ping_results,
                    "check_duration_seconds": duration,
                    "ssl_enabled": self.settings.redis_ssl_enabled,
                    "circuit_breaker_state": self.circuit_breaker.state
                }
            else:
                # Standalone mode - simple ping
                await self.redis.ping()
                duration = asyncio.get_event_loop().time() - start_time

                return {
                    "status": "healthy",
                    "mode": "standalone",
                    "check_duration_seconds": duration,
                    "ssl_enabled": self.settings.redis_ssl_enabled,
                    "circuit_breaker_state": self.circuit_breaker.state
                }

        except Exception as e:
            logger.error(f"Erro no health check do Redis: {e}")
            return {
                "status": "unhealthy",
                "mode": "cluster" if self.is_cluster_mode else "standalone",
                "error": str(e),
                "circuit_breaker_state": self.circuit_breaker.state
            }

    async def get_cluster_topology(self) -> Dict[str, Any]:
        """Obter topologia do Redis (cluster ou standalone)"""
        try:
            if not self.is_cluster_mode:
                # Standalone mode - return simple info
                info = await self.redis.info()
                return {
                    "mode": "standalone",
                    "redis_version": info.get("redis_version", "unknown"),
                    "uptime_seconds": info.get("uptime_in_seconds", 0),
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "ssl_enabled": self.settings.redis_ssl_enabled
                }

            # Cluster mode
            cluster_info = await self.redis.cluster_info()
            cluster_nodes = await self.redis.cluster_nodes()

            masters = []
            slaves = []

            for node_id, node_info in cluster_nodes.items():
                node_data = {
                    "node_id": node_id,
                    "host": node_info.get("host"),
                    "port": node_info.get("port"),
                    "slots": node_info.get("slots", []),
                    "flags": node_info.get("flags", [])
                }

                if "master" in node_info.get("flags", []):
                    masters.append(node_data)
                else:
                    slaves.append(node_data)

            return {
                "mode": "cluster",
                "cluster_state": cluster_info.get("cluster_state", "unknown"),
                "cluster_size": len(cluster_nodes),
                "master_nodes": len(masters),
                "slave_nodes": len(slaves),
                "masters": masters,
                "slaves": slaves,
                "total_slots": 16384,
                "ssl_enabled": self.settings.redis_ssl_enabled
            }

        except Exception as e:
            logger.error(f"Erro ao obter topologia: {e}")
            return {
                "mode": "cluster" if self.is_cluster_mode else "standalone",
                "error": str(e),
                "cluster_state": "unknown" if self.is_cluster_mode else None
            }

    async def pipeline_with_retry(self, operations: List[Dict[str, Any]], max_retries: int = 3) -> List[Any]:
        """Pipeline com retry automático em caso de falha de rede"""
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                return await self.pipeline_operations(operations)
            except (ConnectionError, TimeoutError, RedisClusterException) as e:
                retry_count += 1
                last_error = e

                if retry_count < max_retries:
                    wait_time = 2 ** retry_count  # Exponential backoff
                    logger.warning(f"Pipeline falhou (tentativa {retry_count}/{max_retries}), aguardando {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Pipeline falhou após {max_retries} tentativas: {e}")
                    raise last_error

        raise last_error

    async def _with_circuit_breaker(self, operation_name: str, operation_func):
        """Wrapper para aplicar circuit breaker em operações"""
        if self.circuit_breaker.state == "OPEN":
            current_time = asyncio.get_event_loop().time()
            if (current_time - self.circuit_breaker.last_failure_time) > self.circuit_breaker.recovery_timeout:
                self.circuit_breaker.state = "HALF_OPEN"
                logger.info("Circuit breaker mudou para HALF_OPEN")
            else:
                raise CircuitBreakerError(f"Circuit breaker is OPEN for operation: {operation_name}")

        try:
            result = await operation_func()
            if self.circuit_breaker.state == "HALF_OPEN":
                self.circuit_breaker.reset()
            return result
        except Exception as e:
            self.circuit_breaker.record_failure()
            raise e

    async def get(self, key: str, intent_type: str = "unknown") -> Optional[Any]:
        """Obter valor do cache com deserialização automática"""
        start_time = asyncio.get_event_loop().time()

        async def _get_operation():
            with tracer.start_as_current_span("redis_get", attributes={"key": key}):
                return await self.redis.get(key)

        try:
            value = await self._with_circuit_breaker("get", _get_operation)

            duration = asyncio.get_event_loop().time() - start_time
            redis_operation_duration.labels(operation="get").observe(duration)

            if value:
                self.hit_count += 1
                redis_operations_total.labels(
                    operation="get", status="hit", intent_type=intent_type
                ).inc()

                # Deserializar JSON
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            else:
                self.miss_count += 1
                redis_operations_total.labels(
                    operation="get", status="miss", intent_type=intent_type
                ).inc()
                return None

        except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
            duration = asyncio.get_event_loop().time() - start_time
            redis_operation_duration.labels(operation="get").observe(duration)
            redis_operations_total.labels(
                operation="get", status="error", intent_type=intent_type
            ).inc()
            logger.error(f"Erro ao obter chave {key}: {e}")
            return None
        finally:
            self._update_hit_ratio()

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        intent_type: str = "unknown"
    ) -> bool:
        """Definir valor no cache com serialização automática"""
        start_time = asyncio.get_event_loop().time()

        # Serializar para JSON se necessário
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        elif not isinstance(value, str):
            value = str(value)

        # Usar TTL padrão se não especificado
        if ttl is None:
            ttl = self.settings.redis_default_ttl

        async def _set_operation():
            with tracer.start_as_current_span("redis_set", attributes={"key": key}):
                return await self.redis.setex(key, ttl, value)

        try:
            result = await self._with_circuit_breaker("set", _set_operation)

            duration = asyncio.get_event_loop().time() - start_time
            redis_operation_duration.labels(operation="set").observe(duration)
            redis_operations_total.labels(
                operation="set", status="success", intent_type=intent_type
            ).inc()

            return result

        except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
            duration = asyncio.get_event_loop().time() - start_time
            redis_operation_duration.labels(operation="set").observe(duration)
            redis_operations_total.labels(
                operation="set", status="error", intent_type=intent_type
            ).inc()
            logger.error(f"Erro ao definir chave {key}: {e}")
            return False

    async def delete(self, key: str, intent_type: str = "unknown") -> bool:
        """Deletar chave do cache"""
        start_time = asyncio.get_event_loop().time()

        async def _delete_operation():
            with tracer.start_as_current_span("redis_delete", attributes={"key": key}):
                return await self.redis.delete(key)

        try:
            result = await self._with_circuit_breaker("delete", _delete_operation)

            duration = asyncio.get_event_loop().time() - start_time
            redis_operation_duration.labels(operation="delete").observe(duration)
            redis_operations_total.labels(
                operation="delete", status="success", intent_type=intent_type
            ).inc()

            return bool(result)

        except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
            duration = asyncio.get_event_loop().time() - start_time
            redis_operation_duration.labels(operation="delete").observe(duration)
            redis_operations_total.labels(
                operation="delete", status="error", intent_type=intent_type
            ).inc()
            logger.error(f"Erro ao deletar chave {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Verificar se chave existe"""
        async def _exists_operation():
            with tracer.start_as_current_span("redis_exists", attributes={"key": key}):
                return await self.redis.exists(key)

        try:
            result = await self._with_circuit_breaker("exists", _exists_operation)
            return bool(result)
        except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
            logger.error(f"Erro ao verificar existência da chave {key}: {e}")
            return False

    def _extract_key(self, args: tuple, kwargs: dict) -> Optional[str]:
        """
        Extract the key from operation arguments.

        Args:
            args: Positional arguments for the operation
            kwargs: Keyword arguments for the operation

        Returns:
            The key if found, None for keyless operations
        """
        # Most Redis commands have the key as the first argument
        if args and isinstance(args[0], str):
            return args[0]
        # Check kwargs for 'key' or 'name' parameters
        elif 'key' in kwargs:
            return kwargs['key']
        elif 'name' in kwargs:
            return kwargs['name']
        return None

    async def pipeline_operations(self, operations: List[Dict[str, Any]]) -> List[Any]:
        """
        Execute multiple operations in pipeline, respecting Redis Cluster constraints.

        In Redis Cluster mode, all keys in a pipeline must belong to the same hash slot.
        This method automatically groups operations by slot and executes them in separate
        pipelines if needed, preserving the original order of results.

        Args:
            operations: List of operation dictionaries with 'method', 'args', and 'kwargs'

        Returns:
            List of results in the same order as input operations

        Raises:
            CircuitBreakerError: If circuit breaker is open

        Example:
            operations = [
                {"method": "get", "args": ["key1"]},
                {"method": "set", "args": ["key2", "value"], "kwargs": {"ex": 60}},
                {"method": "delete", "args": ["key3"]}
            ]
            results = await client.pipeline_operations(operations)
        """
        start_time = asyncio.get_event_loop().time()

        # In standalone mode, all operations can be in same pipeline
        if not self.is_cluster_mode:
            logger.debug(f"Standalone mode: All {len(operations)} operations in single pipeline")

            async def _single_pipeline():
                with tracer.start_as_current_span("redis_pipeline_standalone",
                                                 attributes={"ops_count": len(operations)}):
                    pipe = self.redis.pipeline()

                    for op in operations:
                        method = getattr(pipe, op["method"])
                        method(*op.get("args", []), **op.get("kwargs", {}))

                    return await pipe.execute()

            try:
                results = await self._with_circuit_breaker("pipeline", _single_pipeline)

                duration = asyncio.get_event_loop().time() - start_time
                redis_operation_duration.labels(operation="pipeline").observe(duration)
                redis_operations_total.labels(
                    operation="pipeline", status="success", intent_type="batch"
                ).inc()

                return results

            except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
                duration = asyncio.get_event_loop().time() - start_time
                redis_operation_duration.labels(operation="pipeline").observe(duration)
                redis_operations_total.labels(
                    operation="pipeline", status="error", intent_type="batch"
                ).inc()
                logger.error(f"Pipeline error (standalone): {e}")
                return []

        # Cluster mode - Group operations by hash slot
        slot_groups = {}
        operation_indices = []  # Track original indices for result ordering
        keyless_ops = []
        keyless_indices = []

        for idx, op in enumerate(operations):
            args = op.get("args", [])
            kwargs = op.get("kwargs", {})
            key = self._extract_key(args, kwargs)

            if key is None:
                # Handle keyless operations (like PING)
                keyless_ops.append(op)
                keyless_indices.append(idx)
            else:
                # Calculate hash slot for the key
                try:
                    slot = self.redis.keyslot(key)
                except Exception as e:
                    logger.warning(f"Could not calculate slot for key '{key}': {e}")
                    slot = -1  # Use a special slot for problematic keys

                if slot not in slot_groups:
                    slot_groups[slot] = {"operations": [], "indices": []}

                slot_groups[slot]["operations"].append(op)
                slot_groups[slot]["indices"].append(idx)

        # Check if all operations are in the same slot (fast path)
        if len(slot_groups) == 1 and len(keyless_ops) == 0:
            slot = list(slot_groups.keys())[0]
            logger.debug(f"Fast path: All {len(operations)} operations in same slot {slot}")

            async def _single_pipeline():
                with tracer.start_as_current_span("redis_pipeline_single_slot",
                                                 attributes={"slot": slot, "ops_count": len(operations)}):
                    pipe = self.redis.pipeline()

                    for op in operations:
                        method = getattr(pipe, op["method"])
                        method(*op.get("args", []), **op.get("kwargs", {}))

                    return await pipe.execute()

            try:
                results = await self._with_circuit_breaker("pipeline", _single_pipeline)

                duration = asyncio.get_event_loop().time() - start_time
                redis_operation_duration.labels(operation="pipeline").observe(duration)
                redis_operations_total.labels(
                    operation="pipeline", status="success", intent_type="batch"
                ).inc()

                return results

            except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
                duration = asyncio.get_event_loop().time() - start_time
                redis_operation_duration.labels(operation="pipeline").observe(duration)
                redis_operations_total.labels(
                    operation="pipeline", status="error", intent_type="batch"
                ).inc()
                logger.error(f"Pipeline error (single slot): {e}")
                return []

        # Multi-slot path: execute separate pipelines per slot
        logger.info(f"Multi-slot pipeline: {len(slot_groups)} slots, {len(keyless_ops)} keyless ops")

        # Initialize results array with None values
        results = [None] * len(operations)

        # Execute pipelines for each slot
        for slot, group_data in slot_groups.items():
            group_ops = group_data["operations"]
            group_indices = group_data["indices"]

            logger.debug(f"Executing pipeline for slot {slot} with {len(group_ops)} operations")

            async def _slot_pipeline():
                with tracer.start_as_current_span("redis_pipeline_slot",
                                                 attributes={"slot": slot, "ops_count": len(group_ops)}):
                    pipe = self.redis.pipeline()

                    for op in group_ops:
                        method = getattr(pipe, op["method"])
                        method(*op.get("args", []), **op.get("kwargs", {}))

                    return await pipe.execute()

            try:
                slot_results = await self._with_circuit_breaker(f"pipeline_slot_{slot}", _slot_pipeline)

                # Place results in correct positions
                for idx, result in zip(group_indices, slot_results):
                    results[idx] = result

                redis_operations_total.labels(
                    operation="pipeline_slot", status="success", intent_type="batch"
                ).inc()

            except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
                logger.error(f"Pipeline error for slot {slot}: {e}")
                redis_operations_total.labels(
                    operation="pipeline_slot", status="error", intent_type="batch"
                ).inc()
                # Keep None values for failed operations

        # Execute keyless operations if any
        if keyless_ops:
            logger.debug(f"Executing {len(keyless_ops)} keyless operations")

            async def _keyless_pipeline():
                with tracer.start_as_current_span("redis_pipeline_keyless",
                                                 attributes={"ops_count": len(keyless_ops)}):
                    pipe = self.redis.pipeline()

                    for op in keyless_ops:
                        method = getattr(pipe, op["method"])
                        method(*op.get("args", []), **op.get("kwargs", {}))

                    return await pipe.execute()

            try:
                keyless_results = await self._with_circuit_breaker("pipeline_keyless", _keyless_pipeline)

                # Place results in correct positions
                for idx, result in zip(keyless_indices, keyless_results):
                    results[idx] = result

            except (ConnectionError, TimeoutError, RedisError, RedisClusterException) as e:
                logger.error(f"Pipeline error for keyless operations: {e}")

        # Log final metrics
        duration = asyncio.get_event_loop().time() - start_time
        redis_operation_duration.labels(operation="pipeline").observe(duration)

        # Emit structured log for monitoring
        logger.info(
            "Pipeline execution completed",
            extra={
                "total_ops": len(operations),
                "slot_count": len(slot_groups),
                "keyless_count": len(keyless_ops),
                "duration_seconds": duration,
                "slots": list(slot_groups.keys())
            }
        )

        return results

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Obter estatísticas do cache"""
        try:
            stats = {
                "hit_ratio": self.hit_count / max(self.hit_count + self.miss_count, 1),
                "hits": self.hit_count,
                "misses": self.miss_count,
                "circuit_breaker_state": self.circuit_breaker.state,
                "connected": True,
                "mode": "cluster" if self.is_cluster_mode else "standalone"
            }

            if self.is_cluster_mode:
                # Obter informações de cada node do cluster
                stats["cluster_nodes"] = []
                cluster_info = await self.redis.cluster_info()
                for node_id, node_info in cluster_info.items():
                    stats["cluster_nodes"].append({
                        "node_id": node_id,
                        "role": node_info.get("role"),
                        "slots": node_info.get("slots", [])
                    })
            else:
                # Standalone mode - get simple server info
                info = await self.redis.info()
                stats["server_info"] = {
                    "redis_version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "unknown")
                }

            return stats
        except Exception as e:
            logger.error(f"Erro ao obter estatísticas: {e}")
            return {
                "hit_ratio": 0,
                "hits": self.hit_count,
                "misses": self.miss_count,
                "circuit_breaker_state": self.circuit_breaker.state,
                "connected": False,
                "mode": "cluster" if self.is_cluster_mode else "standalone",
                "error": str(e)
            }

    def _update_hit_ratio(self):
        """Atualizar métrica de hit ratio"""
        total_operations = self.hit_count + self.miss_count
        if total_operations > 0:
            ratio = self.hit_count / total_operations
            redis_hit_ratio.set(ratio)

    @asynccontextmanager
    async def acquire_lock(self, lock_key: str, timeout: int = 10, wait_timeout: int = 5):
        """Context manager para locks distribuídos"""
        lock_acquired = False
        try:
            # Tentar adquirir lock
            lock_acquired = await self.redis.set(
                lock_key, "locked", nx=True, ex=timeout
            )

            if not lock_acquired:
                # Aguardar release do lock
                for _ in range(wait_timeout):
                    await asyncio.sleep(1)
                    lock_acquired = await self.redis.set(
                        lock_key, "locked", nx=True, ex=timeout
                    )
                    if lock_acquired:
                        break

            if not lock_acquired:
                raise TimeoutError(f"Não foi possível adquirir lock {lock_key}")

            yield

        finally:
            if lock_acquired:
                await self.redis.delete(lock_key)


# Cliente global singleton
_redis_client: Optional[RedisClient] = None


async def get_redis_client() -> RedisClient:
    """Obter cliente Redis singleton"""
    global _redis_client

    if _redis_client is None:
        _redis_client = RedisClient()
        await _redis_client.initialize()

    return _redis_client


async def close_redis_client():
    """Fechar cliente Redis global"""
    global _redis_client

    if _redis_client:
        await _redis_client.close()
        _redis_client = None