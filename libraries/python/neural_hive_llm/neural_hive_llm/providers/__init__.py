"""Providers para diferentes provedores LLM.

Este pacote implementa a interface BaseProvider e implementações
específicas para OpenAI, Anthropic e provedores locais (Ollama).
"""

from .base import BaseProvider

# Implementações específicas (lazy import para evitar erros se SDK não instalado)
try:
    from .openai_provider import OpenAIProvider
except ImportError:
    OpenAIProvider = None  # type: ignore

try:
    from .anthropic_provider import AnthropicProvider
except ImportError:
    AnthropicProvider = None  # type: ignore

from .local_provider import LocalProvider

__all__ = [
    "BaseProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "LocalProvider",
]
