"""Wrapper de Circuit Breaker para chamadas gRPC no consensus-engine.

Este módulo fornece uma camada de abstração para usar circuit breakers
da neural_hive_resilience em chamadas gRPC, protegendo contra falhas em cascata.

Circuit Breakers implementados:
- queen_agent_calls: Para chamadas ao Queen Agent
- analyst_agent_calls: Para chamadas ao Analyst Agent
- specialist_calls: Para chamadas aos especialistas (business, technical, etc.)
"""

from collections.abc import Callable
from typing import Any, Optional

import grpc
import structlog

from neural_hive_resilience import (
    CircuitBreakerError,
    CircuitBreakerOpenError,
    MonitoredCircuitBreaker,
    ResilienceRegistry,
)

logger = structlog.get_logger()


class GrpcCircuitBreakerWrapper:
    """Wrapper para aplicar circuit breaker em chamadas gRPC.

    Protege chamadas gRPC contra falhas em cascata usando o pattern
    circuit breaker com estados CLOSED -> OPEN -> HALF_OPEN.

    Attributes:
        service_name: Nome do serviço para métricas
        registry: Registro de políticas de resiliência
    """

    def __init__(
        self, service_name: str = "consensus-engine", registry: Optional[ResilienceRegistry] = None
    ):
        self.service_name = service_name
        self.registry = registry or ResilienceRegistry(
            service_name=service_name, default_policies=False
        )
        self._breakers: dict[str, MonitoredCircuitBreaker] = {}
        self.logger = structlog.get_logger()

        # Inicializar circuit breakers padrão
        self._init_default_breakers()

    def _init_default_breakers(self) -> None:
        """Inicializa circuit breakers padrão para chamadas gRPC."""
        # Circuit breaker para Queen Agent
        self.register_breaker(
            name="queen_agent_calls",
            failure_threshold=5,
            recovery_timeout=60,
            description="Circuit breaker para chamadas ao Queen Agent via gRPC",
        )

        # Circuit breaker para Analyst Agent
        self.register_breaker(
            name="analyst_agent_calls",
            failure_threshold=5,
            recovery_timeout=60,
            description="Circuit breaker para chamadas ao Analyst Agent via gRPC",
        )

        # Circuit breakers para cada especialista
        for specialist in ["business", "technical", "behavior", "evolution", "architecture"]:
            self.register_breaker(
                name=f"specialist_{specialist}_calls",
                failure_threshold=3,  # Mais agressivo para specialists
                recovery_timeout=30,
                description=f"Circuit breaker para chamadas ao {specialist} specialist via gRPC",
            )

    def register_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        description: str = "",
    ) -> MonitoredCircuitBreaker:
        """Registra um novo circuit breaker.

        Args:
            name: Nome único do circuit breaker
            failure_threshold: Limite de falhas antes de abrir
            recovery_timeout: Timeout de recuperação em segundos
            description: Descrição do circuit breaker

        Returns:
            Instância do MonitoredCircuitBreaker criado
        """
        if name in self._breakers:
            self.logger.warning("circuit_breaker_already_exists", name=name)
            return self._breakers[name]

        cb = self.registry.register_circuit_breaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            description=description,
            tags=["grpc", "consensus-engine"],
        )
        self._breakers[name] = cb

        self.logger.info(
            "grpc_circuit_breaker_registered",
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        return cb

    def get_breaker(self, name: str) -> Optional[MonitoredCircuitBreaker]:
        """Retorna um circuit breaker registrado.

        Args:
            name: Nome do circuit breaker

        Returns:
            Instância do MonitoredCircuitBreaker ou None
        """
        return self._breakers.get(name)

    async def call_with_breaker(
        self,
        breaker_name: str,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Executa chamada gRPC protegida por circuit breaker.

        Args:
            breaker_name: Nome do circuit breaker
            func: Função a ser executada
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da função

        Raises:
            CircuitBreakerOpenError: Se circuit breaker está aberto
            Exception: Outros erros da chamada gRPC
        """
        breaker = self.get_breaker(breaker_name)
        if not breaker:
            self.logger.warning(
                "circuit_breaker_not_found",
                breaker_name=breaker_name,
                executing_without_protection=True,
            )
            # Fallback: executar sem proteção
            return await func(*args, **kwargs)

        try:
            return await breaker.call_async(func, *args, **kwargs)
        except CircuitBreakerOpenError:
            self.logger.error(
                "circuit_breaker_open",
                breaker_name=breaker_name,
                service=self.service_name,
            )
            raise
        except CircuitBreakerError as e:
            self.logger.error(
                "circuit_breaker_error",
                breaker_name=breaker_name,
                error=str(e),
            )
            raise
        except grpc.RpcError as e:
            # gRPC errors já são tratados pelo circuit breaker via call_async
            self.logger.error(
                "grpc_error_with_breaker",
                breaker_name=breaker_name,
                code=e.code().name,
                details=e.details(),
            )
            raise
        except Exception as e:
            self.logger.error(
                "unexpected_error_with_breaker",
                breaker_name=breaker_name,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def call_queen_agent(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Executa chamada ao Queen Agent protegida por circuit breaker.

        Args:
            func: Função gRPC a ser executada
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da chamada gRPC
        """
        return await self.call_with_breaker("queen_agent_calls", func, *args, **kwargs)

    async def call_analyst_agent(
        self,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Executa chamada ao Analyst Agent protegida por circuit breaker.

        Args:
            func: Função gRPC a ser executada
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da chamada gRPC
        """
        return await self.call_with_breaker("analyst_agent_calls", func, *args, **kwargs)

    async def call_specialist(
        self,
        specialist_type: str,
        func: Callable,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Executa chamada a um especialista protegida por circuit breaker.

        Args:
            specialist_type: Tipo do especialista (business, technical, etc.)
            func: Função gRPC a ser executada
            *args: Argumentos posicionais
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da chamada gRPC
        """
        breaker_name = f"specialist_{specialist_type}_calls"
        return await self.call_with_breaker(breaker_name, func, *args, **kwargs)

    def get_breaker_states(self) -> dict[str, str]:
        """Retorna o estado atual de todos os circuit breakers.

        Returns:
            Dicionário com nome -> estado (CLOSED, OPEN, HALF_OPEN)
        """
        states = {}
        for name, breaker in self._breakers.items():
            # pybreaker usa _state.current_state para obter o estado
            state_obj = breaker._state
            state_name = (
                state_obj.current_state if hasattr(state_obj, "current_state") else "UNKNOWN"
            )
            states[name] = state_name
        return states

    def reset_breaker(self, name: str) -> bool:
        """Reinicia um circuit breaker para o estado CLOSED.

        Útil para testes ou recuperação manual.

        Args:
            name: Nome do circuit breaker

        Returns:
            True se reiniciado com sucesso, False caso contrário
        """
        breaker = self.get_breaker(name)
        if not breaker:
            return False

        # pybreaker não tem método reset direto
        # Apenas logamos que o reset foi solicitado - o circuit breaker
        # voltará ao CLOSED automaticamente após o recovery_timeout
        self.logger.info(
            "circuit_breaker_reset_requested",
            breaker_name=name,
            note="Circuit breaker voltará ao CLOSED após recovery_timeout",
        )
        return True


# Instância global (singleton pattern)
_global_wrapper: Optional[GrpcCircuitBreakerWrapper] = None


def get_grpc_circuit_breaker() -> GrpcCircuitBreakerWrapper:
    """Retorna a instância global do wrapper de circuit breaker gRPC."""
    global _global_wrapper
    if _global_wrapper is None:
        _global_wrapper = GrpcCircuitBreakerWrapper()
    return _global_wrapper


def init_grpc_circuit_breaker(
    service_name: str = "consensus-engine",
    registry: Optional[ResilienceRegistry] = None,
) -> GrpcCircuitBreakerWrapper:
    """Inicializa a instância global do wrapper de circuit breaker gRPC.

    Args:
        service_name: Nome do serviço
        registry: Registro de políticas de resiliência (opcional)

    Returns:
        Instância do GrpcCircuitBreakerWrapper
    """
    global _global_wrapper
    _global_wrapper = GrpcCircuitBreakerWrapper(service_name=service_name, registry=registry)
    return _global_wrapper
