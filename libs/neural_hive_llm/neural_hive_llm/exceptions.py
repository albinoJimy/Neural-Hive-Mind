"""
Exceções customizadas para neural_hive_llm.

Hierarquia de exceções para tratamento de erros específicos de LLM.
"""

from typing import Optional


class LLMError(Exception):
    """Classe base para todas as exceções de LLM."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        self.message = message
        self.provider = provider
        self.original_error = original_error
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.provider:
            return f"[{self.provider}] {self.message}"
        return self.message


class LLMTimeoutError(LLMError):
    """Erro quando uma requisição ao LLM excede o timeout."""

    pass


class LLMRateLimitError(LLMError):
    """Erro quando o rate limit do provider é excedido."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[float] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after  # Segundos até retry


class LLMInvalidRequestError(LLMError):
    """Erro para requisições inválidas (parâmetros, prompt, etc)."""

    pass


class LLMProviderError(LLMError):
    """Erro genérico do provider LLM."""

    pass


class LLMCircuitBreakerOpenError(LLMError):
    """Erro quando o circuit breaker está aberto."""

    def __init__(
        self,
        message: str = "Circuit breaker is open",
        recovery_time: Optional[float] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.recovery_time = recovery_time  # Segundos até recuperação


class LLMConfigurationError(LLMError):
    """Erro de configuração (api_key faltando, provider inválido, etc)."""

    pass


class LLMTokenLimitError(LLMError):
    """Erro quando o limite de tokens é excedido."""

    def __init__(
        self,
        message: str = "Token limit exceeded",
        prompt_tokens: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.prompt_tokens = prompt_tokens
        self.limit = limit


class LLMStreamingError(LLMError):
    """Erro durante streaming de resposta."""

    pass
