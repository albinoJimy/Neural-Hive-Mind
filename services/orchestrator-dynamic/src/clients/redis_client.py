"""
Cliente Redis compartilhado para cache de SLA budgets e deduplicação de alertas.
Inclui circuit breaker para resiliência em caso de falhas de conexão.
"""
import time
from typing import Optional
import redis.asyncio as redis
import structlog

from src.config.settings import OrchestratorSettings
from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError

logger = structlog.get_logger(__name__)


_redis_client_instance: Optional[redis.Redis] = None
_circuit_breaker: Optional[MonitoredCircuitBreaker] = None
_circuit_breaker_enabled: bool = True


async def get_redis_client(config: Optional[OrchestratorSettings] = None) -> Optional[redis.Redis]:
    """
    Retorna instância singleton do cliente Redis.

    Implementa circuit breaker para evitar tentativas repetidas quando Redis está indisponível.
    Circuit breaker é desabilitado via REDIS_CIRCUIT_BREAKER_ENABLED=false.

    Args:
        config: Configurações do orchestrator (opcional, usa get_settings() se não fornecido)

    Returns:
        Cliente Redis inicializado ou None se configuração estiver incompleta ou circuit breaker aberto
    """
    global _redis_client_instance, _circuit_breaker, _circuit_breaker_enabled

    if _redis_client_instance is not None:
        return _redis_client_instance

    if config is None:
        from src.config.settings import get_settings
        config = get_settings()

    # Verificar se circuit breaker está habilitado
    _circuit_breaker_enabled = getattr(config, 'REDIS_CIRCUIT_BREAKER_ENABLED', True)

    # Inicializar circuit breaker apenas se habilitado
    if _circuit_breaker_enabled and _circuit_breaker is None:
        _circuit_breaker = MonitoredCircuitBreaker(
            service_name=config.service_name,
            circuit_name='redis_client',
            fail_max=getattr(config, 'REDIS_CIRCUIT_BREAKER_FAIL_MAX', 5),
            timeout_duration=getattr(config, 'REDIS_CIRCUIT_BREAKER_TIMEOUT', 60),
            recovery_timeout=getattr(config, 'REDIS_CIRCUIT_BREAKER_RECOVERY_TIMEOUT', 60)
        )
        logger.info(
            'Redis circuit breaker inicializado',
            fail_max=_circuit_breaker.fail_max,
            timeout=_circuit_breaker.recovery_timeout
        )
    elif not _circuit_breaker_enabled:
        logger.info('Redis circuit breaker desabilitado via configuração')

    try:
        # Parsear nodes do cluster Redis
        cluster_nodes = config.redis_cluster_nodes
        if not cluster_nodes:
            logger.warning('redis_cluster_nodes_not_configured')
            return None

        # Formato esperado: "host1:port1,host2:port2" ou "host:port"
        nodes = cluster_nodes.split(',')
        if not nodes:
            logger.warning('redis_cluster_nodes_empty')
            return None

        # Usar primeiro node para conexão standalone
        first_node = nodes[0].strip()
        host, port = first_node.split(':')

        # Criar cliente Redis
        async def _create_and_ping():
            client = redis.Redis(
                host=host,
                port=int(port),
                password=config.redis_password,
                ssl=config.redis_ssl_enabled,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=2
            )
            await client.ping()
            return client

        # Usar circuit breaker apenas se habilitado
        if _circuit_breaker_enabled and _circuit_breaker is not None:
            _redis_client_instance = await _circuit_breaker.call_async(_create_and_ping)
        else:
            _redis_client_instance = await _create_and_ping()

        logger.info(
            'redis_client_initialized',
            host=host,
            port=port,
            ssl=config.redis_ssl_enabled,
            circuit_breaker_enabled=_circuit_breaker_enabled
        )

        return _redis_client_instance

    except CircuitBreakerError:
        logger.warning(
            'redis_client_circuit_breaker_open',
            recovery_timeout=_circuit_breaker.recovery_timeout if _circuit_breaker else 0
        )
        _redis_client_instance = None
        return None

    except Exception as e:
        logger.warning(
            'redis_client_initialization_failed',
            error=str(e)
        )
        # Fail-open: retornar None e permitir operação sem Redis
        _redis_client_instance = None
        return None


async def close_redis_client():
    """Fecha conexão Redis gracefully."""
    global _redis_client_instance

    if _redis_client_instance:
        try:
            await _redis_client_instance.aclose()
            logger.info("redis_client_closed")
        except Exception as e:
            logger.warning("redis_client_close_error", error=str(e))
        finally:
            _redis_client_instance = None


def get_circuit_breaker_state() -> dict:
    """
    Retorna o estado atual do circuit breaker.

    Returns:
        Dict com estado e informações do circuit breaker
    """
    global _circuit_breaker, _circuit_breaker_enabled

    if not _circuit_breaker_enabled:
        return {
            'state': 'DISABLED',
            'failure_count': 0,
            'failure_threshold': 0,
            'recovery_timeout': 0,
            'enabled': False
        }

    if _circuit_breaker is None:
        return {
            'state': 'not_initialized',
            'failure_count': 0,
            'failure_threshold': 0,
            'recovery_timeout': 0,
            'enabled': _circuit_breaker_enabled
        }

    # MonitoredCircuitBreaker usa pybreaker internamente
    state_map = {
        'closed': 'CLOSED',
        'open': 'OPEN',
        'half-open': 'HALF_OPEN'
    }

    return {
        'state': state_map.get(str(_circuit_breaker.current_state).lower(), 'UNKNOWN'),
        'failure_count': _circuit_breaker.fail_counter,
        'failure_threshold': _circuit_breaker.fail_max,
        'recovery_timeout': _circuit_breaker.recovery_timeout,
        'enabled': True
    }


# =============================================================================
# Métricas de Cache
# =============================================================================

class CacheMetrics:
    """
    Métricas de cache para telemetria em tempo real.

    Rastreia hits, misses e calcula hit ratio para exposição via /redis/stats.
    """

    def __init__(self):
        self.total_hits = 0
        self.total_misses = 0
        self.recent_latencies: list[float] = []  # Últimas N latências em ms
        self._max_latency_samples = 100

    def record_hit(self, latency_ms: float = 0.0) -> None:
        """Registra um cache hit."""
        self.total_hits += 1
        self._record_latency(latency_ms)

    def record_miss(self, latency_ms: float = 0.0) -> None:
        """Registra um cache miss."""
        self.total_misses += 1
        self._record_latency(latency_ms)

    def _record_latency(self, latency_ms: float) -> None:
        """Registra latência da operação."""
        if latency_ms > 0:
            self.recent_latencies.append(latency_ms)
            # Manter apenas as últimas N amostras
            if len(self.recent_latencies) > self._max_latency_samples:
                self.recent_latencies = self.recent_latencies[-self._max_latency_samples:]

    @property
    def hit_ratio(self) -> float:
        """Calcula hit ratio (0.0-1.0)."""
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Calcula latência média em ms."""
        if not self.recent_latencies:
            return 0.0
        return sum(self.recent_latencies) / len(self.recent_latencies)

    def get_stats(self) -> dict:
        """Retorna estatísticas de cache."""
        return {
            "total_hits": self.total_hits,
            "total_misses": self.total_misses,
            "hit_ratio": round(self.hit_ratio, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "total_operations": self.total_hits + self.total_misses
        }


_cache_metrics: CacheMetrics = CacheMetrics()


def get_cache_metrics() -> dict:
    """
    Retorna métricas de cache em tempo real.

    Returns:
        Dict com total_hits, total_misses, hit_ratio, avg_latency_ms
    """
    global _cache_metrics
    return _cache_metrics.get_stats()


# =============================================================================
# Wrapper Methods com Circuit Breaker
# =============================================================================

async def redis_get_safe(key: str) -> Optional[str]:
    """
    Wrapper seguro para operação GET do Redis com circuit breaker opcional.

    Verifica circuit breaker antes da operação (se habilitado), registra sucesso/falha,
    e atualiza métricas de cache.

    Args:
        key: Chave a buscar no Redis

    Returns:
        Valor da chave ou None se circuit breaker aberto ou erro
    """
    global _redis_client_instance, _circuit_breaker, _cache_metrics, _circuit_breaker_enabled

    if _redis_client_instance is None:
        _cache_metrics.record_miss()
        return None

    start_time = time.time()

    try:
        async def _do_get():
            return await _redis_client_instance.get(key)

        # Usar circuit breaker apenas se habilitado
        if _circuit_breaker_enabled and _circuit_breaker is not None:
            value = await _circuit_breaker.call_async(_do_get)
        else:
            value = await _do_get()

        latency_ms = (time.time() - start_time) * 1000

        if value is not None:
            _cache_metrics.record_hit(latency_ms)
        else:
            _cache_metrics.record_miss(latency_ms)

        return value

    except CircuitBreakerError:
        latency_ms = (time.time() - start_time) * 1000
        _cache_metrics.record_miss(latency_ms)

        logger.debug(
            'redis_get_blocked_circuit_open',
            key=key
        )
        return None

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        _cache_metrics.record_miss(latency_ms)

        logger.warning(
            'redis_get_safe_error',
            key=key,
            error=str(e)
        )
        return None


async def redis_setex_safe(key: str, ttl_seconds: int, value: str) -> bool:
    """
    Wrapper seguro para operação SETEX do Redis com circuit breaker opcional.

    Verifica circuit breaker antes da operação (se habilitado) e registra sucesso/falha.

    Args:
        key: Chave a definir
        ttl_seconds: TTL em segundos
        value: Valor a armazenar

    Returns:
        True se operação bem-sucedida, False caso contrário
    """
    global _redis_client_instance, _circuit_breaker, _circuit_breaker_enabled

    if _redis_client_instance is None:
        return False

    try:
        async def _do_setex():
            return await _redis_client_instance.setex(key, ttl_seconds, value)

        # Usar circuit breaker apenas se habilitado
        if _circuit_breaker_enabled and _circuit_breaker is not None:
            await _circuit_breaker.call_async(_do_setex)
        else:
            await _do_setex()
        return True

    except CircuitBreakerError:
        logger.debug(
            'redis_setex_blocked_circuit_open',
            key=key
        )
        return False

    except Exception as e:
        logger.warning(
            'redis_setex_safe_error',
            key=key,
            error=str(e)
        )
        return False


async def redis_ping_safe() -> bool:
    """
    Wrapper seguro para operação PING do Redis com circuit breaker opcional.

    Verifica circuit breaker antes da operação (se habilitado) e registra sucesso/falha.

    Returns:
        True se Redis respondeu ao ping, False caso contrário
    """
    global _redis_client_instance, _circuit_breaker, _circuit_breaker_enabled

    if _redis_client_instance is None:
        return False

    try:
        async def _do_ping():
            return await _redis_client_instance.ping()

        # Usar circuit breaker apenas se habilitado
        if _circuit_breaker_enabled and _circuit_breaker is not None:
            await _circuit_breaker.call_async(_do_ping)
        else:
            await _do_ping()
        return True

    except CircuitBreakerError:
        logger.debug('redis_ping_blocked_circuit_open')
        return False

    except Exception as e:
        logger.warning(
            'redis_ping_safe_error',
            error=str(e)
        )
        return False
