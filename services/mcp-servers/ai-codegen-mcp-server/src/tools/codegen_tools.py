"""
Ferramentas MCP para geração de código via IA.

Fornece ferramentas unificadas para:
- Geração de código (GitHub Copilot ou OpenAI)
- Autocomplete de código
- Explicação de código
"""

import time
from typing import Any, Literal

import structlog
from fastmcp import FastMCP

from ..clients import OpenAIClient, CopilotClient
from ..config import get_settings

logger = structlog.get_logger(__name__)

# Clientes singleton
_openai_client: OpenAIClient | None = None
_copilot_client: CopilotClient | None = None


def get_openai_client() -> OpenAIClient:
    """Retorna cliente OpenAI singleton."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client


def get_copilot_client() -> CopilotClient:
    """Retorna cliente Copilot singleton."""
    global _copilot_client
    if _copilot_client is None:
        _copilot_client = CopilotClient()
    return _copilot_client


def select_provider(
    requested: str
) -> tuple[Literal["openai", "copilot"], Any]:
    """
    Seleciona provider baseado em disponibilidade.

    Args:
        requested: Provider solicitado (auto, openai, copilot)

    Returns:
        Tupla com nome do provider e cliente
    """
    settings = get_settings()
    openai = get_openai_client()
    copilot = get_copilot_client()

    if requested == "openai":
        return ("openai", openai)
    elif requested == "copilot":
        return ("copilot", copilot)
    else:  # auto
        # Priorizar baseado em configuração e disponibilidade
        if settings.default_provider == "copilot" and copilot.is_available():
            return ("copilot", copilot)
        elif settings.default_provider == "openai" and openai.is_available():
            return ("openai", openai)
        elif openai.is_available():
            return ("openai", openai)
        elif copilot.is_available():
            return ("copilot", copilot)
        else:
            return ("openai", openai)  # Retornar OpenAI para erro apropriado


def register_codegen_tools(mcp: FastMCP) -> None:
    """Registra ferramentas de geração de código no servidor MCP."""

    @mcp.tool()
    async def generate_code(
        prompt: str,
        language: str,
        provider: str = "auto",
        max_tokens: int = 500
    ) -> dict[str, Any]:
        """
        Gera código a partir de descrição em linguagem natural.

        Args:
            prompt: Descrição do código desejado
            language: Linguagem de programação (python, javascript, go, etc)
            provider: Provider a usar (auto, openai, copilot)
            max_tokens: Número máximo de tokens na resposta

        Returns:
            Código gerado com metadata do provider usado
        """
        start_time = time.time()

        provider_name, client = select_provider(provider)

        logger.info(
            "generating_code",
            provider=provider_name,
            language=language,
            prompt_length=len(prompt)
        )

        if provider_name == "openai":
            result = await client.generate_code(prompt, language, max_tokens)
        else:
            result = await client.generate_completion(prompt, language, max_tokens)

        duration = time.time() - start_time

        if "error" in result:
            return {
                "success": False,
                "provider": provider_name,
                "error": result.get("error"),
                "message": result.get("message"),
                "duration_seconds": duration
            }

        return {
            "success": True,
            "provider": provider_name,
            "language": language,
            "code": result.get("code", ""),
            "model": result.get("model"),
            "usage": result.get("usage", {}),
            "duration_seconds": duration
        }

    @mcp.tool()
    async def complete_code(
        code: str,
        language: str,
        cursor_position: int,
        provider: str = "auto"
    ) -> dict[str, Any]:
        """
        Completa código parcial na posição do cursor.

        Args:
            code: Código parcial
            language: Linguagem de programação
            cursor_position: Posição do cursor no código (índice)
            provider: Provider a usar (auto, openai, copilot)

        Returns:
            Sugestões de completion
        """
        start_time = time.time()

        provider_name, client = select_provider(provider)

        logger.info(
            "completing_code",
            provider=provider_name,
            language=language,
            code_length=len(code),
            cursor_position=cursor_position
        )

        if provider_name == "openai":
            result = await client.complete_code(
                code, language, cursor_position
            )
            if result.get("success"):
                completions = [{"text": result.get("completion", ""), "index": 0}]
            else:
                completions = []
        else:
            result = await client.get_suggestions(
                code, language, cursor_position
            )
            completions = result.get("suggestions", [])

        duration = time.time() - start_time

        if "error" in result:
            return {
                "success": False,
                "provider": provider_name,
                "error": result.get("error"),
                "message": result.get("message"),
                "duration_seconds": duration
            }

        return {
            "success": True,
            "provider": provider_name,
            "language": language,
            "completions": completions,
            "model": result.get("model"),
            "duration_seconds": duration
        }

    @mcp.tool()
    async def explain_code(
        code: str,
        language: str
    ) -> dict[str, Any]:
        """
        Gera explicação detalhada para um trecho de código.

        Args:
            code: Código a ser explicado
            language: Linguagem de programação

        Returns:
            Explicação em linguagem natural
        """
        start_time = time.time()

        # Explicação usa apenas OpenAI (melhor para texto explicativo)
        client = get_openai_client()

        if not client.is_available():
            return {
                "success": False,
                "error": "OpenAI not configured",
                "message": "Explicação de código requer OpenAI configurado"
            }

        logger.info(
            "explaining_code",
            language=language,
            code_length=len(code)
        )

        result = await client.explain_code(code, language)
        duration = time.time() - start_time

        if "error" in result:
            return {
                "success": False,
                "error": result.get("error"),
                "message": result.get("message"),
                "duration_seconds": duration
            }

        return {
            "success": True,
            "provider": "openai",
            "language": language,
            "explanation": result.get("explanation", ""),
            "model": result.get("model"),
            "usage": result.get("usage", {}),
            "duration_seconds": duration
        }
