"""
Configuracao de retries para compensacao de Saga.

Implementa backoff exponencial com jitter para evitar
thundering herd quando multiplas sagas compensam simultaneamente.
"""

import random

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Erros que nao devem ser retentados (falhas permanentes)
NON_RETRYABLE_ERRORS: set[str] = {
    "validation_error",
    "schema_error",
    "permission_denied",
    "not_found",
    "authentication_error",
    "quota_exceeded",
    "invalid_input",
}


class SagaRetryConfig(BaseModel):
    """
    Configuracao de retry para operacoes de Saga.

    Attributes:
        max_attempts: Numero maximo de tentativas (1-10)
        initial_delay_ms: Atraso inicial em milissegundos
        max_delay_ms: Atraso maximo em milissegundos (cap)
        multiplier: Multiplicador para backoff exponencial
        jitter: Aplicar jitter para evitar thundering herd
        jitter_factor: Fator de jitter (0.0 a 1.0)
    """

    max_attempts: int = Field(
        default=3, ge=1, le=10, description="Numero maximo de tentativas (1-10)"
    )
    initial_delay_ms: int = Field(
        default=1000, ge=100, le=60000, description="Atraso inicial em milissegundos"
    )
    max_delay_ms: int = Field(
        default=30000, ge=1000, le=300000, description="Atraso maximo em milissegundos"
    )
    multiplier: float = Field(
        default=2.0, ge=1.0, le=10.0, description="Multiplicador para backoff exponencial"
    )
    jitter: bool = Field(default=True, description="Aplicar jitter para evitar thundering herd")
    jitter_factor: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Fator de jitter (0.0 = sem jitter, 1.0 = maximo jitter)",
    )
    non_retryable_errors: set[str] = Field(
        default_factory=NON_RETRYABLE_ERRORS.copy,
        description="Conjunto de erros que nao devem ser retentados",
    )

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("max_delay_ms")
    @classmethod
    def max_delay_must_be_gte_initial(cls, v: int, info) -> int:
        """Valida que max_delay >= initial_delay."""
        if "initial_delay_ms" in info.data and v < info.data["initial_delay_ms"]:
            raise ValueError("max_delay_ms deve ser maior ou igual a initial_delay_ms")
        return v

    def get_delay(self, attempt: int) -> int:
        """
        Calcula o delay para uma tentativa especifica.

        Usa backoff exponencial: delay = initial_delay * multiplier^(attempt-1)
        Com jitter opcional para evitar sincronizacao de retries.

        Args:
            attempt: Numero da tentativa (1-indexed)

        Returns:
            Delay em milissegundos

        Examples:
            >>> config = SagaRetryConfig()
            >>> config.get_delay(1)  # Primeira tentativa: 1000ms
            1000
            >>> config.get_delay(2)  # Segunda: 2000ms
            2000
            >>> config.get_delay(3)  # Terceira: 4000ms
            4000
        """
        if attempt < 1:
            return 0

        # Calcular backoff exponencial
        delay = self.initial_delay_ms * (self.multiplier ** (attempt - 1))

        # Aplicar cap
        delay = min(delay, self.max_delay_ms)

        # Aplicar jitter se habilitado
        if self.jitter and self.jitter_factor > 0:
            jitter_range = delay * self.jitter_factor
            jitter = random.uniform(-jitter_range, jitter_range)
            delay = int(max(0, delay + jitter))

        return int(delay)

    def should_retry(self, attempt: int, error: str | None = None) -> bool:
        """
        Determina se uma operacao deve ser retentada.

        Args:
            attempt: Numero da tentativa atual (1-indexed)
            error: Mensagem de erro (opcional) para verificar se e retryable

        Returns:
            True se deve retentar, False caso contrario

        Examples:
            >>> config = SagaRetryConfig(max_attempts=3)
            >>> config.should_retry(1, 'temporary_failure')
            True
            >>> config.should_retry(3, 'temporary_failure')
            False  # Excedeu max_attempts
            >>> config.should_retry(1, 'validation_error')
            False  # Erro non-retryable
        """
        # Verificar se excedeu maximo de tentativas
        if attempt > self.max_attempts:
            return False

        # Se erro fornecido, verificar se e non-retryable
        if error:
            error_lower = error.lower()
            for non_retryable in self.non_retryable_errors:
                if non_retryable in error_lower:
                    return False

        return True

    def get_total_timeout_ms(self) -> int:
        """
        Calcula o timeout total considerando todos os retries.

        Soma os delays de todas as tentativas possiveis.
        Util para configurar timeouts de operacoes.

        Returns:
            Timeout total em milissegundos
        """
        total = 0
        for attempt in range(1, self.max_attempts + 1):
            total += self.get_delay(attempt)
        return total

    def with_overrides(
        self,
        max_attempts: int | None = None,
        initial_delay_ms: int | None = None,
        max_delay_ms: int | None = None,
        multiplier: float | None = None,
        jitter: bool | None = None,
    ) -> "SagaRetryConfig":
        """
        Cria uma nova configuracao com overrides selecionados.

        Args:
            **kwargs: Parametros para sobrescrever

        Returns:
            Nova instancia de SagaRetryConfig com overrides aplicados
        """
        current_dict = self.model_dump()
        overrides = {
            k: v
            for k, v in {
                "max_attempts": max_attempts,
                "initial_delay_ms": initial_delay_ms,
                "max_delay_ms": max_delay_ms,
                "multiplier": multiplier,
                "jitter": jitter,
            }.items()
            if v is not None
        }
        current_dict.update(overrides)
        return SagaRetryConfig(**current_dict)
