"""
Politica de retry para operacoes de Saga.

Executor que aplica configuracao de retry com backoff exponencial
a operacoes assincronas, com metricas e logging.
"""
import asyncio
from datetime import datetime, timezone
from typing import TypeVar, Callable, Optional, Any, Dict
from functools import wraps

import structlog

from .retry_config import SagaRetryConfig

logger = structlog.get_logger()
T = TypeVar('T')


class RetryError(Exception):
    """Excecao lancada quando todas as tentativas de retry falham."""

    def __init__(
        self,
        message: str,
        last_error: Optional[Exception] = None,
        attempt: int = 0,
        total_attempts: int = 0
    ):
        super().__init__(message)
        self.last_error = last_error
        self.attempt = attempt
        self.total_attempts = total_attempts


class RetryPolicy:
    """
    Politica de retry para operacoes de Saga.

    Aplica configuracao de retry a funcoes assincronas,
    com backoff exponencial, jitter e tratamento de erros.
    """

    def __init__(self, config: Optional[SagaRetryConfig] = None):
        """
        Inicializa politica de retry.

        Args:
            config: Configuracao de retry (default: SagaRetryConfig())
        """
        self.config = config or SagaRetryConfig()

    async def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        operation_name: str = 'operation',
        **kwargs: Any
    ) -> T:
        """
        Executa funcao com retry e backoff exponencial.

        Args:
            func: Funcao assincrona a executar
            *args: Argumentos posicionais para a funcao
            operation_name: Nome da operacao para logging
            **kwargs: Argumentos nomeados para a funcao

        Returns:
            Resultado da funcao executada

        Raises:
            RetryError: Se todas as tentativas falharem

        Examples:
            >>> policy = RetryPolicy()
            >>> result = await policy.execute(
            ...     some_async_function,
            ...     arg1, arg2,
            ...     operation_name='create_ticket'
            ... )
        """
        started_at = datetime.now(timezone.utc)
        last_error: Optional[Exception] = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                logger.info(
                    f'retry.execute_start operation={operation_name} '
                    f'attempt={attempt}/{self.config.max_attempts}'
                )

                # Executar funcao
                result = await func(*args, **kwargs)

                # Sucesso
                elapsed_ms = int(
                    (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
                )
                logger.info(
                    f'retry.execute_success operation={operation_name} '
                    f'attempt={attempt} elapsed_ms={elapsed_ms}'
                )
                return result

            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                error_msg = str(e)

                logger.warning(
                    f'retry.execute_failed operation={operation_name} '
                    f'attempt={attempt}/{self.config.max_attempts} '
                    f'error={error_type} error_msg={error_msg}'
                )

                # Verificar se deve retentar
                should_retry = self.config.should_retry(
                    attempt=attempt,
                    error=error_msg
                )

                if not should_retry:
                    logger.error(
                        f'retry.non_retryable operation={operation_name} '
                        f'attempt={attempt} error={error_type}'
                    )
                    raise RetryError(
                        f'Operacao {operation_name} falhou com erro non-retryable: {error_msg}',
                        last_error=e,
                        attempt=attempt,
                        total_attempts=self.config.max_attempts
                    ) from e

                # Se houver mais tentativas, calcular delay e aguardar
                if attempt < self.config.max_attempts:
                    delay_ms = self.config.get_delay(attempt + 1)
                    logger.info(
                        f'retry.scheduling_next operation={operation_name} '
                        f'next_attempt={attempt + 1} delay_ms={delay_ms}'
                    )
                    await asyncio.sleep(delay_ms / 1000)

        # Todas as tentativas falharam
        elapsed_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )
        logger.error(
            f'retry.all_attempts_failed operation={operation_name} '
            f'total_attempts={self.config.max_attempts} elapsed_ms={elapsed_ms}'
        )

        raise RetryError(
            f'Operacao {operation_name} falhou apos {self.config.max_attempts} tentativas',
            last_error=last_error,
            attempt=self.config.max_attempts,
            total_attempts=self.config.max_attempts
        )

    def get_retry_count(self, started_at: datetime) -> int:
        """
        Estima o numero de tentativas baseado no tempo decorrido.

        Util para inferir retries em operacoes em andamento.

        Args:
            started_at: Timestamp de inicio da operacao

        Returns:
            Numero estimado de tentativas ja realizadas

        Examples:
            >>> policy = RetryPolicy()
            >>> started = datetime.now(timezone.utc)
            >>> # Apos 2 segundos...
            >>> policy.get_retry_count(started)
            1
        """
        elapsed_ms = int(
            (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
        )

        # Tentar encontrar o numero de tentativas baseado no delay acumulado
        accumulated = 0
        for attempt in range(1, self.config.max_attempts + 1):
            accumulated += self.config.get_delay(attempt)
            if accumulated > elapsed_ms:
                return attempt

        return self.config.max_attempts

    def decorator(self, operation_name: Optional[str] = None):
        """
        Decorator para aplicar retry a funcoes assincronas.

        Args:
            operation_name: Nome da operacao (default: nome da funcao)

        Returns:
            Decorator function

        Examples:
            >>> policy = RetryPolicy()
            >>> @policy.decorator(operation_name='delete_artifacts')
            ... async def delete_artifacts(artifact_id: str):
            ...     # Implementacao com retry automatico
            ...     pass
        """

        def decorator_wrapper(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T:
                name = operation_name or func.__name__
                return await self.execute(
                    func, *args, operation_name=name, **kwargs
                )

            return wrapper

        return decorator_wrapper


class NoRetryPolicy:
    """
    Politica sem retry para operacoes criticas ou idempotentes.

    Usada quando retry pode causar efeitos colaterais indesejados
    ou quando a operacao deve falhar rapido em caso de erro.
    """

    async def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        operation_name: str = 'operation',
        **kwargs: Any
    ) -> T:
        """
        Executa funcao sem retry.

        Args:
            func: Funcao assincrona a executar
            *args: Argumentos posicionais
            operation_name: Nome da operacao para logging
            **kwargs: Argumentos nomeados

        Returns:
            Resultado da funcao

        Raises:
            Exception: Excecao original da funcao
        """
        logger.debug(
            f'no_retry.execute operation={operation_name}'
        )
        return await func(*args, **kwargs)


def create_retry_policy(
    max_attempts: int = 3,
    initial_delay_ms: int = 1000,
    max_delay_ms: int = 30000,
    multiplier: float = 2.0,
    jitter: bool = True
) -> RetryPolicy:
    """
    Factory para criar RetryPolicy com configuracao customizada.

    Args:
        max_attempts: Numero maximo de tentativas
        initial_delay_ms: Atraso inicial em ms
        max_delay_ms: Atraso maximo em ms
        multiplier: Multiplicador exponencial
        jitter: Aplicar jitter

    Returns:
        Nova instancia de RetryPolicy
    """
    config = SagaRetryConfig(
        max_attempts=max_attempts,
        initial_delay_ms=initial_delay_ms,
        max_delay_ms=max_delay_ms,
        multiplier=multiplier,
        jitter=jitter
    )
    return RetryPolicy(config=config)
