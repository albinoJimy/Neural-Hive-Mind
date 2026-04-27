"""Biblioteca Neural Hive-Mind para clientes LLM.

Fornece interface unificada para múltiplos provedores LLM (OpenAI, Anthropic,
Ollama/local) com retry automático, circuit breaker e observabilidade.

Example:
    ```python
    from neural_hive_llm import LLMClient, LLMProvider

    # Inicializar cliente
    client = LLMClient(provider=LLMProvider.OPENAI, api_key="sk-...")
    await client.start()

    # Gerar texto
    response = await client.generate(
        prompt="Explique microserviços",
        system_prompt="Você é um arquiteto sênior",
        temperature=0.7,
    )

    print(response.text)
    print(response.total_tokens)
    print(response.estimated_cost_usd)

    await client.stop()
    ```
"""

__version__ = "1.0.0"

# Cliente principal
from .client import LLMClient

# Configurações
from .settings import LLMSettings, get_llm_settings, reset_llm_settings

# Modelos
from .models import (
    LLMConfig,
    LLMMessage,
    LLMOperationType,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
)

# Exceções
from .exceptions import (
    LLMAuthenticationError,
    LLMCircuitBreakerOpenError,
    LLMConfigurationError,
    LLMConnectionError,
    LLMError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMRetryExhaustedError,
    LLMTimeoutError,
)

# Resiliência
from .circuit_breaker import LLMCircuitBreaker, LLMCircuitBreakerOpenError as CBError, create_llm_circuit_breaker
from .resilience import LLMRateLimitError as ResilienceRateLimitError, LLMRetryPolicy, llm_retry

# Observabilidade e métricas
from .observability import LLMTracer, OperationType, get_llm_tracer
from .token_counter import ModelPricing, ModelProvider, TokenCounter, get_token_counter

__all__ = [
    # Version
    "__version__",
    # Cliente
    "LLMClient",
    # Configurações
    "LLMSettings",
    "get_llm_settings",
    "reset_llm_settings",
    # Modelos
    "LLMProvider",
    "LLMOperationType",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamChunk",
    "LLMMessage",
    "LLMConfig",
    # Exceções
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
    # Resiliência
    "LLMRetryPolicy",
    "llm_retry",
    "LLMCircuitBreaker",
    "create_llm_circuit_breaker",
    # Observabilidade
    "LLMTracer",
    "OperationType",
    "get_llm_tracer",
    "TokenCounter",
    "get_token_counter",
    "ModelPricing",
    "ModelProvider",
]

# Importar conditional para evitar erros se dependências não instaladas
try:
    from .providers import BaseProvider, OpenAIProvider, AnthropicProvider, LocalProvider

    __all__.extend(
        [
            "BaseProvider",
            "OpenAIProvider",
            "AnthropicProvider",
            "LocalProvider",
        ]
    )
except ImportError:
    pass
