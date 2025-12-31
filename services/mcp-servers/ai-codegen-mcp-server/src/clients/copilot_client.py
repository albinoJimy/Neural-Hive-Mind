"""
Cliente HTTP para GitHub Copilot API.

Fornece métodos para geração de código e completions
usando a API do GitHub Copilot.
"""

import asyncio
from typing import Any, Optional

import aiohttp
import structlog

from ..config import get_settings

logger = structlog.get_logger(__name__)


class CopilotClient:
    """Cliente assíncrono para GitHub Copilot API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.github_api_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._copilot_token: Optional[str] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Retorna ou cria sessão HTTP."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.settings.api_timeout)
            headers = {
                "Authorization": f"Bearer {self.settings.github_token}",
                "Accept": "application/json",
                "X-GitHub-Api-Version": "2022-11-28"
            }

            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=headers
            )
        return self._session

    async def close(self) -> None:
        """Fecha a sessão HTTP."""
        if self._session and not self._session.closed:
            await self._session.close()

    def is_available(self) -> bool:
        """Verifica se o cliente está configurado."""
        return bool(self.settings.github_token)

    async def _get_copilot_token(self) -> Optional[str]:
        """Obtém token de acesso do Copilot."""
        if self._copilot_token:
            return self._copilot_token

        session = await self._get_session()

        try:
            async with session.get(
                f"{self.base_url}/copilot_internal/v2/token"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self._copilot_token = data.get("token")
                    return self._copilot_token
                else:
                    logger.warning(
                        "copilot_token_fetch_failed",
                        status=response.status
                    )
                    return None
        except Exception as e:
            logger.error("copilot_token_error", error=str(e))
            return None

    async def _request(
        self,
        endpoint: str,
        data: dict,
        retries: int = 3
    ) -> dict[str, Any]:
        """
        Executa requisição HTTP POST com retry.

        Args:
            endpoint: Endpoint da API
            data: Body da requisição
            retries: Número de tentativas

        Returns:
            Resposta JSON da API
        """
        if not self.is_available():
            return {
                "error": "Copilot not configured",
                "message": "GITHUB_TOKEN não está configurado"
            }

        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            try:
                async with session.post(url, json=data) as response:
                    if response.status == 401:
                        return {
                            "error": "Authentication failed",
                            "message": "Token GitHub inválido ou sem acesso ao Copilot"
                        }

                    if response.status == 403:
                        return {
                            "error": "Access denied",
                            "message": "Sem permissão para acessar o Copilot"
                        }

                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status >= 400:
                        try:
                            error_body = await response.json()
                            message = error_body.get("message", "Unknown error")
                        except Exception:
                            message = await response.text()
                        return {
                            "error": f"HTTP {response.status}",
                            "message": message
                        }

                    return await response.json()

            except asyncio.TimeoutError:
                logger.warning(
                    "copilot_request_timeout",
                    attempt=attempt + 1
                )
                if attempt == retries - 1:
                    return {
                        "error": "Timeout",
                        "message": f"Timeout após {retries} tentativas"
                    }

            except aiohttp.ClientError as e:
                logger.warning(
                    "copilot_request_error",
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt == retries - 1:
                    return {
                        "error": "Connection error",
                        "message": str(e)
                    }
                await asyncio.sleep(2 ** attempt)

        return {"error": "Unknown error"}

    async def generate_completion(
        self,
        prompt: str,
        language: str,
        max_tokens: int = 500
    ) -> dict[str, Any]:
        """
        Gera código usando Copilot.

        Args:
            prompt: Prompt para geração
            language: Linguagem de programação
            max_tokens: Número máximo de tokens

        Returns:
            Código gerado
        """
        # Formatar prompt no estilo que o Copilot espera
        formatted_prompt = f"""# {language}
# {prompt}

"""

        data = {
            "prompt": formatted_prompt,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "top_p": 1.0,
            "n": 1,
            "stop": ["\n\n\n", "# ---"]
        }

        result = await self._request("/copilot_internal/v2/completions", data)

        if "error" in result:
            return result

        choices = result.get("choices", [])
        if not choices:
            return {
                "error": "No completion",
                "message": "Copilot não retornou sugestões"
            }

        return {
            "success": True,
            "code": choices[0].get("text", ""),
            "model": "github-copilot",
            "usage": {
                "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": result.get("usage", {}).get("completion_tokens", 0)
            }
        }

    async def get_suggestions(
        self,
        code: str,
        language: str,
        cursor_position: int
    ) -> dict[str, Any]:
        """
        Obtém sugestões de autocomplete.

        Args:
            code: Código atual
            language: Linguagem de programação
            cursor_position: Posição do cursor

        Returns:
            Lista de sugestões
        """
        # Construir contexto para o Copilot
        before_cursor = code[:cursor_position]
        after_cursor = code[cursor_position:]

        data = {
            "prompt": before_cursor,
            "suffix": after_cursor,
            "max_tokens": 100,
            "temperature": 0.0,
            "n": 3,  # Solicitar múltiplas sugestões
            "stop": ["\n\n", "```"]
        }

        result = await self._request("/copilot_internal/v2/completions", data)

        if "error" in result:
            return result

        choices = result.get("choices", [])
        suggestions = [
            {
                "text": choice.get("text", ""),
                "index": choice.get("index", i)
            }
            for i, choice in enumerate(choices)
            if choice.get("text")
        ]

        return {
            "success": True,
            "suggestions": suggestions,
            "model": "github-copilot"
        }
