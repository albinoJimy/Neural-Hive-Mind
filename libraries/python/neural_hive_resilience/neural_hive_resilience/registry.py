"""Central registry for resilience policies in Neural Hive-Mind.

Este módulo implementa um registro central para gerenciar políticas de resiliência:
- Circuit breakers
- Retry policies
- Rate limiters
- Timeouts
- Fallbacks
- Bulkheads

Permite configuração centralizada e reutilização de políticas.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

import structlog

from .bulkhead import BulkheadConfig, SemaphoreBulkhead
from .circuit_breaker import MonitoredCircuitBreaker
from .exceptions import (
    PolicyAlreadyExistsError,
    PolicyNotFoundError,
)
from .fallback import FallbackChain, FallbackConfig
from .rate_limiter import (
    ConcurrencyLimiter,
    RateLimiterFactory,
    SlidingWindowLogRateLimiter,
    TokenBucketRateLimiter,
)
from .retry import BackoffStrategy, RetryPolicy


class PolicyType(Enum):
    """Tipos de políticas de resiliência."""

    CIRCUIT_BREAKER = "circuit_breaker"
    RETRY = "retry"
    RATE_LIMITER = "rate_limiter"
    TIMEOUT = "timeout"
    FALLBACK = "fallback"
    BULKHEAD = "bulkhead"


@dataclass
class PolicyMetadata:
    """Metadados de uma política registrada.

    Attributes:
        name: Nome único da política
        type: Tipo da política
        created_at: Timestamp de criação
        last_used: Timestamp do último uso
        usage_count: Número de vezes que foi usada
        description: Descrição da política
        tags: Tags para categorização
        config: Configuração da política (serializável)
    """

    name: str
    type: PolicyType
    created_at: datetime
    last_used: Optional[datetime] = None
    usage_count: int = 0
    description: str = ""
    tags: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


class ResilienceRegistry:
    """Registro central de políticas de resiliência.

    Gerencia políticas de resiliência de forma centralizada, permitindo
    reutilização e configuração consistente entre serviços.

    Example:
        ```python
        registry = ResilienceRegistry(service_name="consensus-engine")

        # Registrar circuit breaker
        registry.register_circuit_breaker(
            name="specialist_calls",
            failure_threshold=5,
            recovery_timeout=60,
        )

        # Registrar retry policy
        registry.register_retry_policy(
            name="default_retry",
            max_attempts=3,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
        )

        # Usar políticas registradas
        cb = registry.get_circuit_breaker("specialist_calls")
        result = await cb.call_async(specialist.analyze, data)
        ```
    """

    def __init__(
        self,
        service_name: str,
        default_policies: bool = True,
    ):
        self.service_name = service_name
        self.logger = structlog.get_logger()
        self._lock = asyncio.Lock()

        # Storage por tipo
        self._circuit_breakers: dict[str, MonitoredCircuitBreaker] = {}
        self._retry_policies: dict[str, RetryPolicy] = {}
        self._rate_limiters: dict[
            str,
            Union[
                TokenBucketRateLimiter,
                SlidingWindowLogRateLimiter,
                ConcurrencyLimiter,
            ],
        ] = {}
        self._timeouts: dict[str, float] = {}
        self._fallbacks: dict[str, FallbackChain] = {}
        self._bulkheads: dict[str, SemaphoreBulkhead] = {}

        # Metadados
        self._metadata: dict[str, PolicyMetadata] = {}

        # Inicializar políticas padrão se solicitado
        if default_policies:
            self._init_default_policies()

    def _init_default_policies(self) -> None:
        """Inicializa políticas de resiliência padrão."""
        # Retry policy padrão
        self.register_retry_policy(
            name="default",
            max_attempts=3,
            base_delay=0.1,
            max_delay=30.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
        )

        # Circuit breaker padrão
        self.register_circuit_breaker(
            name="default",
            failure_threshold=5,
            recovery_timeout=60,
        )

        # Rate limiter padrão (token bucket)
        self.register_rate_limiter_token_bucket(
            name="default",
            capacity=100,
            refill_rate=10,
        )

        # Timeout padrão
        self.register_timeout(
            name="default",
            timeout_seconds=30.0,
        )

    # ==================== Circuit Breaker ====================

    def register_circuit_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Optional[type[Exception]] = None,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> MonitoredCircuitBreaker:
        """Registra um circuit breaker.

        Args:
            name: Nome único do circuit breaker
            failure_threshold: Limite de falhas antes de abrir
            recovery_timeout: Timeout de recuperação em segundos
            expected_exception: Exceção esperada (deprecated)
            description: Descrição da política
            tags: Tags para categorização

        Returns:
            Instância do circuit breaker criado

        Raises:
            PolicyAlreadyExistsError: Se política já existe
        """
        if name in self._circuit_breakers:
            raise PolicyAlreadyExistsError(
                f"Circuit breaker '{name}' já existe",
                policy_name=name,
                policy_type=PolicyType.CIRCUIT_BREAKER.value,
            )

        cb = MonitoredCircuitBreaker(
            service_name=self.service_name,
            circuit_name=name,
            fail_max=failure_threshold,
            reset_timeout=recovery_timeout,
        )

        self._circuit_breakers[name] = cb

        self._metadata[name] = PolicyMetadata(
            name=name,
            type=PolicyType.CIRCUIT_BREAKER,
            created_at=datetime.now(),
            description=description,
            tags=tags or [],
            config={
                "failure_threshold": failure_threshold,
                "recovery_timeout": recovery_timeout,
            },
        )

        self.logger.info(
            "circuit_breaker_registered",
            service=self.service_name,
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        return cb

    def get_circuit_breaker(self, name: str) -> MonitoredCircuitBreaker:
        """Retorna um circuit breaker registrado.

        Args:
            name: Nome do circuit breaker

        Returns:
            Instância do circuit breaker

        Raises:
            PolicyNotFoundError: Se política não existe
        """
        if name not in self._circuit_breakers:
            raise PolicyNotFoundError(
                f"Circuit breaker '{name}' não encontrado",
                policy_name=name,
                policy_type=PolicyType.CIRCUIT_BREAKER.value,
            )

        self._update_usage(name)
        return self._circuit_breakers[name]

    # ==================== Retry Policy ====================

    def register_retry_policy(
        self,
        name: str,
        max_attempts: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 30.0,
        backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
        jitter_enabled: bool = True,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> RetryPolicy:
        """Registra uma política de retry.

        Args:
            name: Nome único da política
            max_attempts: Número máximo de tentativas
            base_delay: Delay base em segundos
            max_delay: Delay máximo em segundos
            backoff_strategy: Estratégia de backoff
            jitter_enabled: Habilita jitter
            description: Descrição da política
            tags: Tags para categorização

        Returns:
            Instância da RetryPolicy criada

        Raises:
            PolicyAlreadyExistsError: Se política já existe
        """
        if name in self._retry_policies:
            raise PolicyAlreadyExistsError(
                f"Retry policy '{name}' já existe",
                policy_name=name,
                policy_type=PolicyType.RETRY.value,
            )

        policy = RetryPolicy(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            backoff_strategy=backoff_strategy,
            jitter_enabled=jitter_enabled,
        )

        self._retry_policies[name] = policy

        self._metadata[name] = PolicyMetadata(
            name=name,
            type=PolicyType.RETRY,
            created_at=datetime.now(),
            description=description,
            tags=tags or [],
            config={
                "max_attempts": max_attempts,
                "base_delay": base_delay,
                "max_delay": max_delay,
                "backoff_strategy": backoff_strategy.value,
            },
        )

        self.logger.info(
            "retry_policy_registered",
            service=self.service_name,
            name=name,
            max_attempts=max_attempts,
            backoff_strategy=backoff_strategy.value,
        )

        return policy

    def get_retry_policy(self, name: str) -> RetryPolicy:
        """Retorna uma política de retry registrada.

        Args:
            name: Nome da política

        Returns:
            Instância da RetryPolicy

        Raises:
            PolicyNotFoundError: Se política não existe
        """
        if name not in self._retry_policies:
            raise PolicyNotFoundError(
                f"Retry policy '{name}' não encontrada",
                policy_name=name,
                policy_type=PolicyType.RETRY.value,
            )

        self._update_usage(name)
        return self._retry_policies[name]

    # ==================== Rate Limiter ====================

    def register_rate_limiter_token_bucket(
        self,
        name: str,
        capacity: int,
        refill_rate: float,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> TokenBucketRateLimiter:
        """Registra um rate limiter do tipo token bucket.

        Args:
            name: Nome único do rate limiter
            capacity: Capacidade do bucket
            refill_rate: Taxa de reabastecimento
            description: Descrição da política
            tags: Tags para categorização

        Returns:
            Instância do TokenBucketRateLimiter criado

        Raises:
            PolicyAlreadyExistsError: Se política já existe
        """
        if name in self._rate_limiters:
            raise PolicyAlreadyExistsError(
                f"Rate limiter '{name}' já existe",
                policy_name=name,
                policy_type=PolicyType.RATE_LIMITER.value,
            )

        factory = RateLimiterFactory(self.service_name)
        limiter = factory.token_bucket(
            capacity=capacity,
            refill_rate=refill_rate,
            name=name,
        )

        self._rate_limiters[name] = limiter

        self._metadata[name] = PolicyMetadata(
            name=name,
            type=PolicyType.RATE_LIMITER,
            created_at=datetime.now(),
            description=description,
            tags=tags or [],
            config={
                "type": "token_bucket",
                "capacity": capacity,
                "refill_rate": refill_rate,
            },
        )

        self.logger.info(
            "rate_limiter_registered",
            service=self.service_name,
            name=name,
            type="token_bucket",
            capacity=capacity,
            refill_rate=refill_rate,
        )

        return limiter

    def register_rate_limiter_sliding_window(
        self,
        name: str,
        limit: int,
        window_seconds: float,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> SlidingWindowLogRateLimiter:
        """Registra um rate limiter do tipo sliding window.

        Args:
            name: Nome único do rate limiter
            limit: Limite de requisições
            window_seconds: Tamanho da janela em segundos
            description: Descrição da política
            tags: Tags para categorização

        Returns:
            Instância do SlidingWindowLogRateLimiter criado

        Raises:
            PolicyAlreadyExistsError: Se política já existe
        """
        if name in self._rate_limiters:
            raise PolicyAlreadyExistsError(
                f"Rate limiter '{name}' já existe",
                policy_name=name,
                policy_type=PolicyType.RATE_LIMITER.value,
            )

        factory = RateLimiterFactory(self.service_name)
        limiter = factory.sliding_window_log(
            limit=limit,
            window_seconds=window_seconds,
            name=name,
        )

        self._rate_limiters[name] = limiter

        self._metadata[name] = PolicyMetadata(
            name=name,
            type=PolicyType.RATE_LIMITER,
            created_at=datetime.now(),
            description=description,
            tags=tags or [],
            config={
                "type": "sliding_window_log",
                "limit": limit,
                "window_seconds": window_seconds,
            },
        )

        self.logger.info(
            "rate_limiter_registered",
            service=self.service_name,
            name=name,
            type="sliding_window_log",
            limit=limit,
            window_seconds=window_seconds,
        )

        return limiter

    def get_rate_limiter(
        self, name: str
    ) -> Union[TokenBucketRateLimiter, SlidingWindowLogRateLimiter, ConcurrencyLimiter]:
        """Retorna um rate limiter registrado.

        Args:
            name: Nome do rate limiter

        Returns:
            Instância do rate limiter

        Raises:
            PolicyNotFoundError: Se política não existe
        """
        if name not in self._rate_limiters:
            raise PolicyNotFoundError(
                f"Rate limiter '{name}' não encontrado",
                policy_name=name,
                policy_type=PolicyType.RATE_LIMITER.value,
            )

        self._update_usage(name)
        return self._rate_limiters[name]

    # ==================== Timeout ====================

    def register_timeout(
        self,
        name: str,
        timeout_seconds: float,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> float:
        """Registra um timeout.

        Args:
            name: Nome único do timeout
            timeout_seconds: Valor do timeout em segundos
            description: Descrição da política
            tags: Tags para categorização

        Returns:
            Valor do timeout registrado

        Raises:
            PolicyAlreadyExistsError: Se política já existe
        """
        if name in self._timeouts:
            raise PolicyAlreadyExistsError(
                f"Timeout '{name}' já existe",
                policy_name=name,
                policy_type=PolicyType.TIMEOUT.value,
            )

        self._timeouts[name] = timeout_seconds

        self._metadata[name] = PolicyMetadata(
            name=name,
            type=PolicyType.TIMEOUT,
            created_at=datetime.now(),
            description=description,
            tags=tags or [],
            config={"timeout_seconds": timeout_seconds},
        )

        self.logger.info(
            "timeout_registered",
            service=self.service_name,
            name=name,
            timeout_seconds=timeout_seconds,
        )

        return timeout_seconds

    def get_timeout(self, name: str) -> float:
        """Retorna um timeout registrado.

        Args:
            name: Nome do timeout

        Returns:
            Valor do timeout em segundos

        Raises:
            PolicyNotFoundError: Se política não existe
        """
        if name not in self._timeouts:
            raise PolicyNotFoundError(
                f"Timeout '{name}' não encontrado",
                policy_name=name,
                policy_type=PolicyType.TIMEOUT.value,
            )

        self._update_usage(name)
        return self._timeouts[name]

    # ==================== Fallback ====================

    def register_fallback_chain(
        self,
        name: str,
        fallbacks: list[FallbackConfig],
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> FallbackChain:
        """Registra uma cadeia de fallback.

        Args:
            name: Nome único da cadeia
            fallbacks: Lista de fallbacks
            description: Descrição da política
            tags: Tags para categorização

        Returns:
            Instância da FallbackChain criada

        Raises:
            PolicyAlreadyExistsError: Se política já existe
        """
        if name in self._fallbacks:
            raise PolicyAlreadyExistsError(
                f"Fallback chain '{name}' já existe",
                policy_name=name,
                policy_type=PolicyType.FALLBACK.value,
            )

        chain = FallbackChain(
            service_name=self.service_name,
            operation_name=name,
            fallbacks=fallbacks,
        )

        self._fallbacks[name] = chain

        self._metadata[name] = PolicyMetadata(
            name=name,
            type=PolicyType.FALLBACK,
            created_at=datetime.now(),
            description=description,
            tags=tags or [],
            config={
                "fallback_count": len(fallbacks),
                "fallback_names": [f.name for f in fallbacks],
            },
        )

        self.logger.info(
            "fallback_chain_registered",
            service=self.service_name,
            name=name,
            fallback_count=len(fallbacks),
        )

        return chain

    def get_fallback_chain(self, name: str) -> FallbackChain:
        """Retorna uma cadeia de fallback registrada.

        Args:
            name: Nome da cadeia

        Returns:
            Instância da FallbackChain

        Raises:
            PolicyNotFoundError: Se política não existe
        """
        if name not in self._fallbacks:
            raise PolicyNotFoundError(
                f"Fallback chain '{name}' não encontrada",
                policy_name=name,
                policy_type=PolicyType.FALLBACK.value,
            )

        self._update_usage(name)
        return self._fallbacks[name]

    # ==================== Bulkhead ====================

    def register_bulkhead(
        self,
        name: str,
        max_concurrent: int = 10,
        max_queue_size: int = 5,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> SemaphoreBulkhead:
        """Registra um bulkhead.

        Args:
            name: Nome único do bulkhead
            max_concurrent: Máximo de operações concorrentes
            max_queue_size: Tamanho máximo da fila
            description: Descrição da política
            tags: Tags para categorização

        Returns:
            Instância do SemaphoreBulkhead criado

        Raises:
            PolicyAlreadyExistsError: Se política já existe
        """
        if name in self._bulkheads:
            raise PolicyAlreadyExistsError(
                f"Bulkhead '{name}' já existe",
                policy_name=name,
                policy_type=PolicyType.BULKHEAD.value,
            )

        config = BulkheadConfig(
            max_concurrent=max_concurrent,
            max_queue_size=max_queue_size,
        )

        bulkhead = SemaphoreBulkhead(
            service_name=self.service_name,
            bulkhead_name=name,
            config=config,
        )

        self._bulkheads[name] = bulkhead

        self._metadata[name] = PolicyMetadata(
            name=name,
            type=PolicyType.BULKHEAD,
            created_at=datetime.now(),
            description=description,
            tags=tags or [],
            config={
                "max_concurrent": max_concurrent,
                "max_queue_size": max_queue_size,
            },
        )

        self.logger.info(
            "bulkhead_registered",
            service=self.service_name,
            name=name,
            max_concurrent=max_concurrent,
            max_queue_size=max_queue_size,
        )

        return bulkhead

    def get_bulkhead(self, name: str) -> SemaphoreBulkhead:
        """Retorna um bulkhead registrado.

        Args:
            name: Nome do bulkhead

        Returns:
            Instância do SemaphoreBulkhead

        Raises:
            PolicyNotFoundError: Se política não existe
        """
        if name not in self._bulkheads:
            raise PolicyNotFoundError(
                f"Bulkhead '{name}' não encontrado",
                policy_name=name,
                policy_type=PolicyType.BULKHEAD.value,
            )

        self._update_usage(name)
        return self._bulkheads[name]

    # ==================== Metadata ====================

    def _update_usage(self, name: str) -> None:
        """Atualiza metadados de uso."""
        if name in self._metadata:
            metadata = self._metadata[name]
            metadata.last_used = datetime.now()
            metadata.usage_count += 1

    def get_metadata(self, name: str) -> Optional[PolicyMetadata]:
        """Retorna metadados de uma política.

        Args:
            name: Nome da política

        Returns:
            PolicyMetadata ou None se não existir
        """
        return self._metadata.get(name)

    def list_policies(
        self,
        policy_type: Optional[PolicyType] = None,
        tag: Optional[str] = None,
    ) -> list[PolicyMetadata]:
        """Lista políticas registradas.

        Args:
            policy_type: Filtrar por tipo (opcional)
            tag: Filtrar por tag (opcional)

        Returns:
            Lista de metadados das políticas
        """
        result = list(self._metadata.values())

        if policy_type:
            result = [m for m in result if m.type == policy_type]

        if tag:
            result = [m for m in result if tag in m.tags]

        return result

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do registro.

        Returns:
            Dicionário com estatísticas
        """
        return {
            "service_name": self.service_name,
            "circuit_breakers": len(self._circuit_breakers),
            "retry_policies": len(self._retry_policies),
            "rate_limiters": len(self._rate_limiters),
            "timeouts": len(self._timeouts),
            "fallbacks": len(self._fallbacks),
            "bulkheads": len(self._bulkheads),
            "total_policies": len(self._metadata),
        }


# Instância global (singleton pattern)
_global_registry: Optional[ResilienceRegistry] = None


def get_global_registry() -> Optional[ResilienceRegistry]:
    """Retorna o registro global de resiliência."""
    return _global_registry


def init_global_registry(
    service_name: str,
    default_policies: bool = True,
) -> ResilienceRegistry:
    """Inicializa o registro global de resiliência.

    Args:
        service_name: Nome do serviço
        default_policies: Incluir políticas padrão

    Returns:
        Instância do ResilienceRegistry
    """
    global _global_registry
    _global_registry = ResilienceRegistry(
        service_name=service_name,
        default_policies=default_policies,
    )
    return _global_registry
