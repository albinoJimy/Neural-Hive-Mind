"""
neural_hive_llm - Biblioteca centralizada de LLM clients para Neural Hive Mind.

Esta biblioteca fornece uma abstração unificada para múltiplos provedores LLM
(OpenAI, Anthropic, Local/Ollama), eliminando código duplicado entre serviços.

Example:
    >>> from neural_hive_llm import LLMClient, LLMProvider
    >>> client = LLMClient(provider=LLMProvider.OPENAI, api_key="sk-...")
    >>> await client.start()
    >>> response = await client.generate("Explique microserviços")
    >>> print(response.text)
"""

__version__ = "0.1.0"
__author__ = "Neural Hive Mind Team"
__all__ = [
    # Client principal
    "LLMClient",
    "create_client",
    # Enums
    "LLMProvider",
    "LLMModel",
    # Models
    "LLMResponse",
    "LLMRequest",
    "LLMStreamChunk",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingVector",
    "TokenUsage",
    # Config
    "LLMSettings",
    "get_llm_settings",
    # Exceptions
    "LLMError",
    "LLMTimeoutError",
    "LLMRateLimitError",
    "LLMInvalidRequestError",
    "LLMProviderError",
    "LLMCircuitBreakerOpenError",
    "LLMConfigurationError",
    # Registry System
    "ModelRegistry",
    "ModelMetadata",
    "ModelCapabilities",
    "ModelPricing",
    "TaskType",
    "Priority",
    "get_registry",
    "PerformanceTracker",
    "RequestMetric",
    "get_tracker",
    "IntelligentSelector",
    "SelectionContext",
    "SelectionResult",
    "SelectionCriteria",
    "SelectionWeights",
    "get_selector",
]

# Imports públicos principais
from neural_hive_llm.client import LLMClient, create_client
from neural_hive_llm.config import LLMSettings, get_llm_settings
from neural_hive_llm.exceptions import (
    LLMCircuitBreakerOpenError,
    LLMConfigurationError,
    LLMError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from neural_hive_llm.models import (
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingVector,
    LLMModel,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)
from neural_hive_llm.registry import (
    IntelligentSelector,
    ModelCapabilities,
    ModelMetadata,
    ModelPricing,
    ModelRegistry,
    PerformanceTracker,
    Priority,
    RequestMetric,
    SelectionContext,
    SelectionCriteria,
    SelectionResult,
    SelectionWeights,
    TaskType,
    get_registry,
    get_selector,
    get_tracker,
)
