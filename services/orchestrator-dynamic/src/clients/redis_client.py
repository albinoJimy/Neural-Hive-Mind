"""
Cliente Redis compartilhado para cache de SLA budgets e deduplicação de alertas.
Inclui circuit breaker para resiliência em caso de falhas de conexão.
"""
import time
from typing import Optional
from functools import lru_cache
import redis.asyncio as redis
import structlog

from src.config.settings import OrchestratorSettings

logger = structlog.get_logger(__name__)


class CircuitBreaker:
    """
    Circuit breaker para operações Redis.

    Previne cascading failures abrindo o circuito após múltiplas falhas consecutivas.
    Transições de estado: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Inicializa o circuit breaker.

        Args:
            failure_threshold: Número de falhas consecutivas para abrir o circuito
            recovery_timeout: Tempo em segundos antes de tentar recuperação
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def record_failure(self) -> None:
        """Registra uma falha e potencialmente abre o circuito."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                "redis_circuit_breaker_opened",
                failure_count=self.failure_count,
                threshold=self.failure_threshold
            )

    def reset(self) -> None:
        """Reseta o circuit breaker para estado CLOSED."""
        previous_state = self.state
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
        if previous_state != "CLOSED":
            logger.info(
                "redis_circuit_breaker_reset",
                previous_state=previous_state
            )

    def should_allow_request(self) -> bool:
        """
        Verifica se uma requisição deve ser permitida.

        Returns:
            True se a requisição pode prosseguir, False se deve ser bloqueada
        """
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            # Verificar se recovery timeout expirou
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("redis_circuit_breaker_half_open")
                return True
            return False

        # HALF_OPEN - permitir uma requisição de teste
        return True

    def record_success(self) -> None:
        """Registra uma operação bem-sucedida."""
        if self.state == "HALF_OPEN":
            self.reset()


_redis_client_instance: Optional[redis.Redis] = None
_circuit_breaker: CircuitBreaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)


async def get_redis_client(config: Optional[OrchestratorSettings] = None) -> Optional[redis.Redis]:
    """
    Retorna instância singleton do cliente Redis.

    Implementa circuit breaker para evitar tentativas repetidas quando Redis está indisponível.

    Args:
        config: Configurações do orchestrator (opcional, usa get_settings() se não fornecido)

    Returns:
        Cliente Redis inicializado ou None se configuração estiver incompleta ou circuit breaker aberto
    """
    global _redis_client_instance, _circuit_breaker

    if _redis_client_instance is not None:
        return _redis_client_instance

    # Verificar circuit breaker antes de tentar conexão
    if not _circuit_breaker.should_allow_request():
        logger.warning(
            "redis_circuit_breaker_open",
            state=_circuit_breaker.state,
            recovery_timeout=_circuit_breaker.recovery_timeout
        )
        return None

    if config is None:
        from src.config.settings import get_settings
        config = get_settings()

    try:
        # Parsear nodes do cluster Redis
        cluster_nodes = config.redis_cluster_nodes
        if not cluster_nodes:
            logger.warning("redis_cluster_nodes_not_configured")
            return None

        # Formato esperado: "host1:port1,host2:port2" ou "host:port"
        nodes = cluster_nodes.split(',')
        if not nodes:
            logger.warning("redis_cluster_nodes_empty")
            return None

        # Usar primeiro node para conexão standalone
        # (Em produção com cluster real, usar RedisCluster)
        first_node = nodes[0].strip()
        host, port = first_node.split(':')

        # Criar cliente Redis
        _redis_client_instance = redis.Redis(
            host=host,
            port=int(port),
            password=config.redis_password,
            ssl=config.redis_ssl_enabled,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=2
        )

        # Testar conexão
        await _redis_client_instance.ping()

        # Conexão bem-sucedida - registrar sucesso no circuit breaker
        _circuit_breaker.record_success()

        logger.info(
            "redis_client_initialized",
            host=host,
            port=port,
            ssl=config.redis_ssl_enabled,
            circuit_breaker_state=_circuit_breaker.state
        )

        return _redis_client_instance

    except Exception as e:
        # Registrar falha no circuit breaker
        _circuit_breaker.record_failure()

        logger.warning(
            "redis_client_initialization_failed",
            error=str(e),
            circuit_breaker_state=_circuit_breaker.state,
            failure_count=_circuit_breaker.failure_count
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
        Dict com estado, contagem de falhas e tempo da última falha
    """
    global _circuit_breaker
    return {
        "state": _circuit_breaker.state,
        "failure_count": _circuit_breaker.failure_count,
        "failure_threshold": _circuit_breaker.failure_threshold,
        "recovery_timeout": _circuit_breaker.recovery_timeout,
        "last_failure_time": _circuit_breaker.last_failure_time
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
    Wrapper seguro para operação GET do Redis com circuit breaker.

    Verifica circuit breaker antes da operação, registra sucesso/falha,
    e atualiza métricas de cache.

    Args:
        key: Chave a buscar no Redis

    Returns:
        Valor da chave ou None se circuit breaker aberto ou erro
    """
    global _redis_client_instance, _circuit_breaker, _cache_metrics

    if _redis_client_instance is None:
        _cache_metrics.record_miss()
        return None

    # Verificar circuit breaker
    if not _circuit_breaker.should_allow_request():
        logger.debug(
            "redis_get_blocked_circuit_open",
            key=key,
            circuit_state=_circuit_breaker.state
        )
        _cache_metrics.record_miss()
        return None

    start_time = time.time()
    try:
        value = await _redis_client_instance.get(key)
        latency_ms = (time.time() - start_time) * 1000

        # Operação bem-sucedida - registrar sucesso
        _circuit_breaker.record_success()

        if value is not None:
            _cache_metrics.record_hit(latency_ms)
        else:
            _cache_metrics.record_miss(latency_ms)

        return value

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        _circuit_breaker.record_failure()
        _cache_metrics.record_miss(latency_ms)

        logger.warning(
            "redis_get_safe_error",
            key=key,
            error=str(e),
            circuit_state=_circuit_breaker.state
        )
        return None


async def redis_setex_safe(key: str, ttl_seconds: int, value: str) -> bool:
    """
    Wrapper seguro para operação SETEX do Redis com circuit breaker.

    Verifica circuit breaker antes da operação e registra sucesso/falha.

    Args:
        key: Chave a definir
        ttl_seconds: TTL em segundos
        value: Valor a armazenar

    Returns:
        True se operação bem-sucedida, False caso contrário
    """
    global _redis_client_instance, _circuit_breaker

    if _redis_client_instance is None:
        return False

    # Verificar circuit breaker
    if not _circuit_breaker.should_allow_request():
        logger.debug(
            "redis_setex_blocked_circuit_open",
            key=key,
            circuit_state=_circuit_breaker.state
        )
        return False

    try:
        await _redis_client_instance.setex(key, ttl_seconds, value)

        # Operação bem-sucedida - registrar sucesso
        _circuit_breaker.record_success()

        return True

    except Exception as e:
        _circuit_breaker.record_failure()

        logger.warning(
            "redis_setex_safe_error",
            key=key,
            error=str(e),
            circuit_state=_circuit_breaker.state
        )
        return False


async def redis_ping_safe() -> bool:
    """
    Wrapper seguro para operação PING do Redis com circuit breaker.

    Verifica circuit breaker antes da operação e registra sucesso/falha.

    Returns:
        True se Redis respondeu ao ping, False caso contrário
    """
    global _redis_client_instance, _circuit_breaker

    if _redis_client_instance is None:
        return False

    # Verificar circuit breaker
    if not _circuit_breaker.should_allow_request():
        logger.debug(
            "redis_ping_blocked_circuit_open",
            circuit_state=_circuit_breaker.state
        )
        return False

    try:
        await _redis_client_instance.ping()

        # Operação bem-sucedida - registrar sucesso
        _circuit_breaker.record_success()

        return True

    except Exception as e:
        _circuit_breaker.record_failure()

        logger.warning(
            "redis_ping_safe_error",
            error=str(e),
            circuit_state=_circuit_breaker.state
        )
        return False
