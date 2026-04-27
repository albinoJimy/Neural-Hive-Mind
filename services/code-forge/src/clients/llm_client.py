"""
LLM client for code generation - Wrapper usando neural_hive_llm.

Este módulo fornece compatibilidade backward com a API existente do code-forge
enquanto utiliza a biblioteca centralizada neural_hive_llm internamente.

Migration para neural_hive_llm: 2026-04-24
"""

# Re-exportar do wrapper para manter compatibilidade
from .llm_client_wrapper import LLMClient, LLMProvider

__all__ = ["LLMClient", "LLMProvider"]
