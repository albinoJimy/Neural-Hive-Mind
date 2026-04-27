"""Circuit breaker integrado com neural_hive_resilience para clientes LLM.

Implementa circuit breaker para proteção contra falhas cascata em chamadas
a provedores LLM externos.
"""

from typing import Final, Optional

import structlog
from pybreaker import CircuitBreakerError

from neural_hive_resilience import MonitoredCircuitBreaker

logger = structlog.get_logger()


class LLMCircuitBreakerOpenError(CircuitBreakerError):
    """Exceção levantada quando o circuit breaker está aberto.

    Isso indica que o provedor LLM está experimentando muitas falhas
    e as requisições estão sendo bloqueadas preventivamente.
    """

    def __init__(
        self,
        message: str = "Circuit breaker is open - blocking LLM requests",
        provider: str = "unknown",
        recovery_timeout: float | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.recovery_timeout = recovery_timeout


class LLMCircuitBreaker:
    """Circuit breaker especializado para chamadas LLM.

    Integra com MonitoredCircuitBreaker de neural_hive_resilience,
    adicionando contexto específico para operações LLM.

    Attributes:
        provider: Nome do provedor LLM (openai, anthropic, local)
        failure_threshold: Número de falhas consecutivas para abrir o circuito
        recovery_timeout: Tempo em segundos antes de tentar recuperação
        service_name: Nome do serviço para métricas
    """

    # Configurações padrão por provedor
    DEFAULT_THRESHOLDS: Final[dict[str, dict[str, int | float]]] = {
        "openai": {"failure_threshold": 5, "recovery_timeout": 60},
        "anthropic": {"failure_threshold": 5, "recovery_timeout": 60},
        "local": {"failure_threshold": 10, "recovery_timeout": 30},  # Mais tolerante
    }

    def __init__(
        self,
        provider: str,
        failure_threshold: int | None = None,
        recovery_timeout: float | None = None,
        service_name: str = "neural_hive_llm",
    ):
        """Inicializa circuit breaker para LLM.

        Args:
            provider: Nome do provedor (openai, anthropic, local)
            failure_threshold: Falhas consecutivas para abrir (usa padrão se None)
            recovery_timeout: Timeout de recuperação em segundos (usa padrão se None)
            service_name: Nome do serviço para métricas
        """
        self.provider = provider
        self.service_name = service_name

        # Obter configurações padrão se não fornecidas
        defaults = self.DEFAULT_THRESHOLDS.get(provider, {})
        self.failure_threshold = failure_threshold or defaults.get("failure_threshold", 5)
        self.recovery_timeout = recovery_timeout or defaults.get("recovery_timeout", 60)

        # Criar circuit breaker monitorado
        # pybreaker usa fail_max para limite de falhas
        self._circuit = MonitoredCircuitBreaker(
            service_name=service_name,
            circuit_name=f"llm_{provider}",
            recovery_timeout=int(self.recovery_timeout),
            fail_max=self.failure_threshold,
        )

        self.logger = structlog.get_logger().bind(
            provider=provider,
            service=service_name,
        )

        logger.info(
            "llm_circuit_breaker_initialized",
            provider=provider,
            failure_threshold=self.failure_threshold,
            recovery_timeout=self.recovery_timeout,
        )

    async def call(self, func, *args, **kwargs):
        """Executa função com proteção do circuit breaker.

        Args:
            func: Função assíncrona a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            LLMCircuitBreakerOpenError: Se circuito está aberto
        """
        try:
            return await self._circuit.call_async(func, *args, **kwargs)
        except CircuitBreakerError as e:
            self.logger.warning(
                "llm_circuit_breaker_open",
                recovery_timeout=self.recovery_timeout,
            )
            raise LLMCircuitBreakerOpenError(
                message=f"Circuit breaker open for provider '{self.provider}'",
                provider=self.provider,
                recovery_timeout=self.recovery_timeout,
            ) from e

    def call_sync(self, func, *args, **kwargs):
        """Executa função síncrona com proteção do circuit breaker.

        Args:
            func: Função síncrona a executar
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            LLMCircuitBreakerOpenError: Se circuito está aberto
        """
        try:
            return self._circuit.call(func, *args, **kwargs)
        except CircuitBreakerError as e:
            self.logger.warning(
                "llm_circuit_breaker_open",
                recovery_timeout=self.recovery_timeout,
            )
            raise LLMCircuitBreakerOpenError(
                message=f"Circuit breaker open for provider '{self.provider}'",
                provider=self.provider,
                recovery_timeout=self.recovery_timeout,
            ) from e

    @property
    def state(self) -> str:
        """Retorna estado atual do circuit breaker.

        Returns:
            'closed', 'open', ou 'half_open'
        """
        # pybreaker retorna string diretamente
        current_state = self._circuit.current_state
        # Mapear para valores padronizados
        if current_state == "closed":
            return "closed"
        elif current_state == "open":
            return "open"
        elif current_state == "half-open":
            return "half_open"
        return str(current_state)

    @property
    def failure_count(self) -> int:
        """Retorna número de falhas consecutivas atuais."""
        return self._circuit.fail_counter

    @property
    def is_open(self) -> bool:
        """Verifica se circuito está aberto."""
        return self.state == "open"

    def reset(self):
        """Reseta circuit breaker para estado fechado (uso manual)."""
        self._circuit._state = self._circuit._closed_state
        self.logger.info("llm_circuit_breaker_reset")

    def __repr__(self) -> str:
        return (
            f"LLMCircuitBreaker(provider={self.provider}, "
            f"state={self.state}, failures={self.failure_count})"
        )


def create_llm_circuit_breaker(
    provider: str,
    failure_threshold: int | None = None,
    recovery_timeout: float | None = None,
    service_name: str = "neural_hive_llm",
) -> LLMCircuitBreaker:
    """Factory function para criar circuit breaker LLM.

    Args:
        provider: Nome do provedor
        failure_threshold: Falhas consecutivas para abrir
        recovery_timeout: Timeout de recuperação
        service_name: Nome do serviço

    Returns:
        Instância de LLMCircuitBreaker configurada

    Example:
        ```python
        cb = create_llm_circuit_breaker("openai")
        try:
            result = await cb.call(lambda: openai_client.generate(...))
        except LLMCircuitBreakerOpenError:
            # Fallback para outro provedor
            result = await fallback_client.generate(...)
        ```
    """
    return LLMCircuitBreaker(
        provider=provider,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        service_name=service_name,
    )


__all__ = [
    "LLMCircuitBreakerOpenError",
    "LLMCircuitBreaker",
    "create_llm_circuit_breaker",
]
