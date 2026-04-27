"""Exceções customizadas para clientes LLM.

Hierarquia de exceções para tratamento de erros específicos
de operações LLM.
"""

from typing import Any, Optional


class LLMError(Exception):
    """Base exception para todos os erros LLM."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        model: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Inicializa erro LLM base.

        Args:
            message: Mensagem de erro
            provider: Nome do provedor
            model: Nome do modelo
            details: Detalhes adicionais do erro
        """
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.details = details or {}

    def __str__(self) -> str:
        base_msg = f"[{self.provider}"
        if self.model:
            base_msg += f":{self.model}"
        base_msg += f"] {super().__str__()}"
        return base_msg


class LLMRateLimitError(LLMError):
    """Erro de rate limit do provedor LLM.

    Levantado quando o provedor recusa a requisição por excesso
    de taxa de requisições.

    Attributes:
        retry_after: Segundos sugeridos antes de retry
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        provider: str = "unknown",
        model: str | None = None,
        retry_after: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, model, details)
        self.retry_after = retry_after

    def __str__(self) -> str:
        msg = super().__str__()
        if self.retry_after:
            msg += f" (retry after {self.retry_after}s)"
        return msg


class LLMTimeoutError(LLMError):
    """Erro de timeout em requisição LLM.

    Levantado quando a requisição excede o tempo limite configurado.
    """

    def __init__(
        self,
        message: str = "Request timeout",
        provider: str = "unknown",
        model: str | None = None,
        timeout_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, model, details)
        self.timeout_seconds = timeout_seconds


class LLMInvalidRequestError(LLMError):
    """Erro de requisição inválida.

    Levantado quando a requisição é malformada ou contém
    parâmetros inválidos.
    """

    def __init__(
        self,
        message: str = "Invalid request",
        provider: str = "unknown",
        model: str | None = None,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, model, details)
        self.field = field


class LLMAuthenticationError(LLMError):
    """Erro de autenticação.

    Levantado quando a credencial API é inválida ou ausente.
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        provider: str = "unknown",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, None, details)


class LLMProviderError(LLMError):
    """Erro genérico do provedor LLM.

    Levantado para erros que não se encaixam nas categorias
    específicas acima.
    """

    def __init__(
        self,
        message: str = "Provider error",
        provider: str = "unknown",
        model: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, model, details)
        self.status_code = status_code

    def __str__(self) -> str:
        msg = super().__str__()
        if self.status_code:
            msg += f" (status: {self.status_code})"
        return msg


class LLMConnectionError(LLMError):
    """Erro de conexão com provedor LLM.

    Levantado quando não é possível estabelecer conexão
    com o endpoint do provedor.
    """

    def __init__(
        self,
        message: str = "Connection error",
        provider: str = "unknown",
        endpoint: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, None, details)
        self.endpoint = endpoint


class LLMResponseParsingError(LLMError):
    """Erro ao processar resposta do provedor.

    Levantado quando a resposta não pode ser parseada
    corretamente.
    """

    def __init__(
        self,
        message: str = "Failed to parse response",
        provider: str = "unknown",
        model: str | None = None,
        raw_response: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, model, details)
        self.raw_response = raw_response


class LLMCircuitBreakerOpenError(LLMError):
    """Erro quando circuit breaker está aberto.

    Levantado quando o circuit breaker detecta muitas falhas
    consecutivas e bloqueia requisições.
    """

    def __init__(
        self,
        message: str = "Circuit breaker is open",
        provider: str = "unknown",
        recovery_timeout: float | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, None, details)
        self.recovery_timeout = recovery_timeout


class LLMConfigurationError(LLMError):
    """Erro de configuração do cliente LLM.

    Levantado quando a configuração fornecida é inválida.
    """

    def __init__(
        self,
        message: str = "Invalid configuration",
        parameter: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, "unknown", None, details)
        self.parameter = parameter


class LLMRetryExhaustedError(LLMError):
    """Erro quando todas as tentativas de retry falharam.

    Levantado após esgotar o número máximo de retries.
    """

    def __init__(
        self,
        message: str = "Retry attempts exhausted",
        provider: str = "unknown",
        model: str | None = None,
        attempts: int = 0,
        last_error: Exception | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, provider, model, details)
        self.attempts = attempts
        self.last_error = last_error

    def __str__(self) -> str:
        msg = super().__str__()
        if self.attempts:
            msg += f" (attempts: {self.attempts})"
        return msg


__all__ = [
    "LLMError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMInvalidRequestError",
    "LLMAuthenticationError",
    "LLMProviderError",
    "LLMConnectionError",
    "LLMResponseParsingError",
    "LLMCircuitBreakerOpenError",
    "LLMConfigurationError",
    "LLMRetryExhaustedError",
]
