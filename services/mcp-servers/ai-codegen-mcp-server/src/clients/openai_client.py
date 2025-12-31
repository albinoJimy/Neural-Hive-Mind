"""
Cliente HTTP para OpenAI API.

Fornece métodos para geração de código e chat completions
usando a API da OpenAI.
"""

import asyncio
from typing import Any, Optional

import aiohttp
import structlog

from ..config import get_settings

logger = structlog.get_logger(__name__)


class OpenAIClient:
    """Cliente assíncrono para OpenAI API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.openai_api_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Retorna ou cria sessão HTTP."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.settings.api_timeout)
            headers = {
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json"
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
        return bool(self.settings.openai_api_key)

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
                "error": "OpenAI not configured",
                "message": "OPENAI_API_KEY não está configurado"
            }

        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            try:
                async with session.post(url, json=data) as response:
                    if response.status == 401:
                        return {
                            "error": "Authentication failed",
                            "message": "API key OpenAI inválida"
                        }

                    if response.status == 429:
                        # Rate limit - aguardar e tentar novamente
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(
                            "openai_rate_limited",
                            retry_after=retry_after
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status >= 400:
                        error_body = await response.json()
                        return {
                            "error": f"HTTP {response.status}",
                            "message": error_body.get("error", {}).get("message", "Unknown error")
                        }

                    return await response.json()

            except asyncio.TimeoutError:
                logger.warning(
                    "openai_request_timeout",
                    attempt=attempt + 1,
                    endpoint=endpoint
                )
                if attempt == retries - 1:
                    return {
                        "error": "Timeout",
                        "message": f"Timeout após {retries} tentativas"
                    }

            except aiohttp.ClientError as e:
                logger.warning(
                    "openai_request_error",
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

    async def generate_code(
        self,
        prompt: str,
        language: str,
        max_tokens: int = 500
    ) -> dict[str, Any]:
        """
        Gera código a partir de uma descrição.

        Args:
            prompt: Descrição do código desejado
            language: Linguagem de programação
            max_tokens: Número máximo de tokens na resposta

        Returns:
            Código gerado
        """
        system_prompt = f"""Você é um assistente especialista em programação.
Gere código limpo, bem comentado e funcional na linguagem {language}.
Responda APENAS com o código, sem explicações adicionais."""

        data = {
            "model": self.settings.openai_code_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2
        }

        result = await self._request("/chat/completions", data)

        if "error" in result:
            return result

        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})

        return {
            "success": True,
            "code": message.get("content", ""),
            "model": result.get("model"),
            "usage": result.get("usage", {})
        }

    async def complete_code(
        self,
        code: str,
        language: str,
        cursor_position: int,
        max_tokens: int = 200
    ) -> dict[str, Any]:
        """
        Completa código parcial.

        Args:
            code: Código parcial
            language: Linguagem de programação
            cursor_position: Posição do cursor
            max_tokens: Número máximo de tokens

        Returns:
            Sugestão de completion
        """
        # Dividir código na posição do cursor
        before_cursor = code[:cursor_position]
        after_cursor = code[cursor_position:]

        system_prompt = f"""Você é um assistente de autocomplete de código {language}.
Complete o código abaixo de forma natural e idiomática.
Responda APENAS com o código que deve ser inserido na posição do cursor."""

        user_prompt = f"""Código antes do cursor:
```{language}
{before_cursor}
```

Código depois do cursor:
```{language}
{after_cursor}
```

Complete o código na posição do cursor:"""

        data = {
            "model": self.settings.openai_code_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.1
        }

        result = await self._request("/chat/completions", data)

        if "error" in result:
            return result

        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})

        return {
            "success": True,
            "completion": message.get("content", ""),
            "model": result.get("model"),
            "usage": result.get("usage", {})
        }

    async def explain_code(
        self,
        code: str,
        language: str
    ) -> dict[str, Any]:
        """
        Gera explicação para um trecho de código.

        Args:
            code: Código a explicar
            language: Linguagem de programação

        Returns:
            Explicação do código
        """
        system_prompt = """Você é um professor de programação experiente.
Explique o código de forma clara e didática, incluindo:
- O que o código faz
- Como funciona
- Conceitos importantes utilizados"""

        user_prompt = f"""Explique o seguinte código {language}:

```{language}
{code}
```"""

        data = {
            "model": self.settings.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 1000,
            "temperature": 0.3
        }

        result = await self._request("/chat/completions", data)

        if "error" in result:
            return result

        choice = result.get("choices", [{}])[0]
        message = choice.get("message", {})

        return {
            "success": True,
            "explanation": message.get("content", ""),
            "model": result.get("model"),
            "usage": result.get("usage", {})
        }
