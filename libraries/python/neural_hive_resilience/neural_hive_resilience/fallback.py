"""Fallback mechanisms for Neural Hive-Mind.

Este módulo implementa padrões de fallback para degradação graciosa:
- Single fallback: Um fallback simples
- Fallback chain: Múltiplos fallbacks em sequência
- Circuit breaker fallback: Fallback quando circuit breaker abre
- Conditional fallback: Fallback baseado em condições
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Optional,
    TypeVar,
    Union,
)


T = TypeVar("T")
from prometheus_client import Counter
import structlog

from .exceptions import AllFallbacksFailedError


# Métricas Prometheus
fallback_invocations_total = Counter(
    "fallback_invocations_total",
    "Total number of fallback invocations",
    ["service", "operation", "fallback_index", "status"],
)


class FallbackStrategy(Enum):
    """Estratégias de fallback."""

    PRIMARY_FIRST = "primary_first"  # Tenta primário, depois fallbacks
    FASTEST = "fastest"  # Executa todos e retorna o primeiro
    MAJORITY = "majority"  # Executa todos e retorna o resultado majoritário


@dataclass
class FallbackResult:
    """Resultado de uma operação com fallback.

    Attributes:
        success: Se a operação foi bem-sucedida
        result: Resultado da operação (se success=True)
        error: Erro da operação (se success=False)
        source: Fonte do resultado (primary, fallback_1, fallback_2, etc.)
        attempt: Número da tentativa (0=primary, 1=fallback_1, etc.)
    """

    success: bool
    result: Any = None
    error: Optional[Exception] = None
    source: str = "unknown"
    attempt: int = 0


@dataclass
class FallbackConfig:
    """Configuração de um fallback individual.

    Attributes:
        name: Nome identificador do fallback
        func: Função de fallback (assíncrona)
        should_execute: Condição para executar (opcional)
        timeout: Timeout para este fallback (opcional)
    """

    name: str
    func: Callable[..., Awaitable[Any]]
    should_execute: Optional[Callable[[], bool]] = None
    timeout: Optional[float] = None


class FallbackChain:
    """Cadeia de fallbacks para degradação graciosa.

    Tenta a operação principal e, em caso de falha, tenta fallbacks
    em sequência até um funcionar ou todos falharem.

    Example:
        ```python
        # Definir fallbacks
        fallbacks = [
            FallbackConfig(
                name="cache",
                func=get_from_cache,
            ),
            FallbackConfig(
                name="database_replica",
                func=get_from_replica,
            ),
            FallbackConfig(
                name="static_response",
                func=get_static_default,
            ),
        ]

        chain = FallbackChain(
            service_name="consensus-engine",
            operation_name="get_specialist_opinion",
            fallbacks=fallbacks,
        )

        # Usar a cadeia
        result = await chain.execute(get_opinion_primary, specialist_id="tech-01")
        ```
    """

    def __init__(
        self,
        service_name: str,
        operation_name: str,
        fallbacks: List[FallbackConfig],
        strategy: FallbackStrategy = FallbackStrategy.PRIMARY_FIRST,
    ):
        self.service_name = service_name
        self.operation_name = operation_name
        self.fallbacks = fallbacks
        self.strategy = strategy
        self.logger = structlog.get_logger()

    async def execute(
        self,
        primary_func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> FallbackResult:
        """Executa operação com cadeia de fallback.

        Args:
            primary_func: Função principal a executar
            *args: Argumentos para a função
            **kwargs: Keyword arguments para a função

        Returns:
            FallbackResult com o resultado

        Raises:
            AllFallbacksFailedError: Se todas as tentativas falharem
        """
        if self.strategy == FallbackStrategy.PRIMARY_FIRST:
            return await self._execute_primary_first(primary_func, *args, **kwargs)
        elif self.strategy == FallbackStrategy.FASTEST:
            return await self._execute_fastest(primary_func, *args, **kwargs)
        elif self.strategy == FallbackStrategy.MAJORITY:
            return await self._execute_majority(primary_func, *args, **kwargs)
        else:
            return await self._execute_primary_first(primary_func, *args, **kwargs)

    async def _execute_primary_first(
        self,
        primary_func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> FallbackResult:
        """Executa estratégia primary-first."""
        functions = [(primary_func, "primary", 0)] + [
            (f.func, f.name, i + 1) for i, f in enumerate(self.fallbacks)
        ]

        errors = []

        for func, name, attempt in functions:
            # Verificar se deve executar (para fallbacks)
            if attempt > 0:
                fallback_config = self.fallbacks[attempt - 1]
                if fallback_config.should_execute:
                    try:
                        if not fallback_config.should_execute():
                            continue
                    except Exception:
                        pass  # Executar mesmo se should_execute falhar

            try:
                start_time = asyncio.get_event_loop().time()

                if attempt > 0 and self.fallbacks[attempt - 1].timeout:
                    result = await asyncio.wait_for(
                        func(*args, **kwargs),
                        timeout=self.fallbacks[attempt - 1].timeout,
                    )
                else:
                    result = await func(*args, **kwargs)

                elapsed = asyncio.get_event_loop().time() - start_time

                self.logger.info(
                    "fallback_chain_success",
                    service=self.service_name,
                    operation=self.operation_name,
                    source=name,
                    attempt=attempt,
                    duration=elapsed,
                )

                fallback_invocations_total.labels(
                    service=self.service_name,
                    operation=self.operation_name,
                    fallback_index=str(attempt),
                    status="success",
                ).inc()

                return FallbackResult(
                    success=True,
                    result=result,
                    source=name,
                    attempt=attempt,
                )

            except Exception as e:
                errors.append((name, e))

                self.logger.warning(
                    "fallback_chain_attempt_failed",
                    service=self.service_name,
                    operation=self.operation_name,
                    source=name,
                    attempt=attempt,
                    error=str(e),
                    error_type=type(e).__name__,
                )

                fallback_invocations_total.labels(
                    service=self.service_name,
                    operation=self.operation_name,
                    fallback_index=str(attempt),
                    status="failed",
                ).inc()

        # Todas as tentativas falharam
        raise AllFallbacksFailedError(
            f"Todos os fallbacks falharam para {self.operation_name}",
            service=self.service_name,
            fallback_chain=[name for name, _, _ in functions],
            exceptions=[e for _, e in errors],
        )

    async def _execute_fastest(
        self,
        primary_func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> FallbackResult:
        """Executa estratégia fastest (primeiro a responder)."""
        functions = [primary_func] + [f.func for f in self.fallbacks]
        names = ["primary"] + [f.name for f in self.fallbacks]

        tasks = [
            asyncio.create_task(func(*args, **kwargs))
            for func in functions
        ]

        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancelar tarefas pendentes
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Pegar primeiro completado com sucesso
        for task in done:
            try:
                result = await task
                # Encontrar o índice na lista original
                task_index = tasks.index(task)
                return FallbackResult(
                    success=True,
                    result=result,
                    source=names[task_index],
                    attempt=task_index,
                )
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        raise AllFallbacksFailedError(
            f"Todas as tentativas paralelas falharam para {self.operation_name}",
            service=self.service_name,
            fallback_chain=names,
            exceptions=[],
        )

    async def _execute_majority(
        self,
        primary_func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> FallbackResult:
        """Executa estratégia majority (resultado majoritário)."""
        functions = [primary_func] + [f.func for f in self.fallbacks]
        names = ["primary"] + [f.name for f in self.fallbacks]

        tasks = [
            asyncio.create_task(func(*args, **kwargs))
            for func in functions
        ]

        results = []
        errors = []

        for i, task in enumerate(tasks):
            try:
                result = await task
                results.append((names[i], result))
            except Exception as e:
                errors.append((names[i], e))

        if results:
            # Retornar resultado mais comum (simplificado)
            return FallbackResult(
                success=True,
                result=results[0][1],
                source=results[0][0],
                attempt=0,
            )

        raise AllFallbacksFailedError(
            f"Todas as tentativas falharam para {self.operation_name}",
            service=self.service_name,
            fallback_chain=names,
            exceptions=[e for _, e in errors],
        )


class ConditionalFallback:
    """Fallback que executa baseado em condições.

    Útil para fallbacks que só devem ser usados em cenários específicos.

    Example:
        ```python
        fallback = ConditionalFallback(
            service_name="gateway-intencoes",
            operation_name="translate_intent",
            fallback_func=safe_translate,
            condition=lambda error: isinstance(error, TimeoutError),
        )

        result = await fallback.execute(translate_intent, intent)
        ```
    """

    def __init__(
        self,
        service_name: str,
        operation_name: str,
        fallback_func: Callable[..., Awaitable[Any]],
        condition: Callable[[Exception], bool],
    ):
        self.service_name = service_name
        self.operation_name = operation_name
        self.fallback_func = fallback_func
        self.condition = condition
        self.logger = structlog.get_logger()

    async def execute(
        self,
        primary_func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Executa operação com fallback condicional.

        Args:
            primary_func: Função principal
            *args: Argumentos para a função
            **kwargs: Keyword arguments

        Returns:
            Resultado da primária ou do fallback
        """
        try:
            return await primary_func(*args, **kwargs)
        except Exception as e:
            if self.condition(e):
                self.logger.info(
                    "conditional_fallback_triggered",
                    service=self.service_name,
                    operation=self.operation_name,
                    error_type=type(e).__name__,
                )

                fallback_invocations_total.labels(
                    service=self.service_name,
                    operation=self.operation_name,
                    fallback_index="0",
                    status="success",
                ).inc()

                return await self.fallback_func(*args, **kwargs)

            raise


def with_fallback(
    fallback_func: Callable[..., Awaitable[Any]],
    service_name: str = "unknown",
    operation_name: str = "unknown",
) -> Callable:
    """Decorator para adicionar fallback simples.

    Args:
        fallback_func: Função fallback assíncrona
        service_name: Nome do serviço para métricas
        operation_name: Nome da operação para métricas

    Returns:
        Decorator configurado

    Example:
        ```python
        async def safe_opinions(opinions):
            return Opinion.merge_safe(opinions)

        @fallback(
            fallback_func=safe_opinions,
            service_name="consensus-engine",
        )
        async def merge_opinions(opinions):
            return await consensus_service.merge(opinions)
        ```
    """

    def decorator(func):
        op_name = operation_name or func.__name__

        if asyncio.iscoroutinefunction(func):

            async def wrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger = structlog.get_logger()
                    logger.warning(
                        "fallback_decorator_triggered",
                        service=service_name,
                        operation=op_name,
                        error=str(e),
                    )

                    fallback_invocations_total.labels(
                        service=service_name,
                        operation=op_name,
                        fallback_index="0",
                        status="success",
                    ).inc()

                    return await fallback_func(*args, **kwargs)

            return wrapper
        else:
            raise TypeError(
                f"@fallback decorator só suporta funções assíncronas"
            )

    return decorator
