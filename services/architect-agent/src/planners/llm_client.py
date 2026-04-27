"""
Cliente unificado para OpenAI e Anthropic LLMs - Wrapper usando neural_hive_llm.

Este módulo fornece compatibilidade backward com a API existente do architect-agent
enquanto utiliza a biblioteca centralizada neural_hive_llm internamente.

Migration para neural_hive_llm: 2026-04-24
"""

# Re-exportar do wrapper para manter compatibilidade
from .llm_client_wrapper import LLMClient

__all__ = ["LLMClient"]
