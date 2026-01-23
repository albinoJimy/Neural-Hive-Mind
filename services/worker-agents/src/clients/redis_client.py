"""
Cliente Redis compartilhado para deduplicação de tickets no Worker Agent.
Inclui circuit breaker para resiliência em caso de falhas de conexão.
"""
import time
from typing import Optional
import redis.asyncio as redis
import structlog

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
        self.state = "CLOSED"

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
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("redis_circuit_breaker_half_open")
                return True
            return False

        return True

    def record_success(self) -> None:
        """Registra uma operação bem-sucedida."""
        if self.state == "HALF_OPEN":
            self.reset()


_redis_client_instance: Optional[redis.Redis] = None
_circuit_breaker: CircuitBreaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)


async def get_redis_client(config) -> Optional[redis.Redis]:
    """
    Retorna instância singleton do cliente Redis.

    Implementa circuit breaker para evitar tentativas repetidas quando Redis está indisponível.

    Args:
        config: Configurações do worker agent

    Returns:
        Cliente Redis inicializado ou None se configuração estiver incompleta ou circuit breaker aberto
    """
    global _redis_client_instance, _circuit_breaker

    if _redis_client_instance is not None:
        return _redis_client_instance

    if not _circuit_breaker.should_allow_request():
        logger.warning(
            "redis_circuit_breaker_open",
            state=_circuit_breaker.state,
            recovery_timeout=_circuit_breaker.recovery_timeout
        )
        return None

    try:
        redis_url = getattr(config, 'redis_url', None)
        redis_host = getattr(config, 'redis_host', 'localhost')
        redis_port = getattr(config, 'redis_port', 6379)
        redis_password = getattr(config, 'redis_password', None)
        redis_ssl = getattr(config, 'redis_ssl_enabled', False)

        if redis_url:
            _redis_client_instance = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=2
            )
        else:
            _redis_client_instance = redis.Redis(
                host=redis_host,
                port=int(redis_port),
                password=redis_password,
                ssl=redis_ssl,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=2
            )

        await _redis_client_instance.ping()
        _circuit_breaker.record_success()

        logger.info(
            "redis_client_initialized",
            host=redis_host,
            port=redis_port,
            ssl=redis_ssl,
            circuit_breaker_state=_circuit_breaker.state
        )

        return _redis_client_instance

    except Exception as e:
        _circuit_breaker.record_failure()
        logger.warning(
            "redis_client_initialization_failed",
            error=str(e),
            circuit_breaker_state=_circuit_breaker.state,
            failure_count=_circuit_breaker.failure_count
        )
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
