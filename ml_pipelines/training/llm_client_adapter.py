"""
LLM Client Adapter para geração de datasets.

Adaptado de services/code-forge/src/clients/llm_client.py
Focado em geração de JSON estruturado para cognitive plans e specialist opinions.
"""

import asyncio
import json
import re
from enum import Enum
from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger()


class LLMProvider(Enum):
    """
    Providers de LLM suportados.

    OpenAI-compatible providers (usam mesma API):
    - OPENAI: ChatGPT/GPT-4 (api.openai.com)
    - DEEPSEEK: DeepSeek Chat/Coder (api.deepseek.com)
    - GROQ: Llama, Mixtral via Groq (api.groq.com)
    - TOGETHER: Together AI (api.together.xyz)
    - AZURE_OPENAI: Azure OpenAI Service
    - OPENROUTER: OpenRouter (openrouter.ai) - acesso a múltiplos modelos

    Outros providers:
    - ANTHROPIC: Claude (api.anthropic.com)
    - LOCAL: Ollama local
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"  # Ollama
    DEEPSEEK = "deepseek"  # DeepSeek API (OpenAI-compatible)
    GROQ = "groq"  # Groq API (OpenAI-compatible, muito rápido)
    TOGETHER = "together"  # Together AI (OpenAI-compatible)
    OPENROUTER = "openrouter"  # OpenRouter (acesso a múltiplos modelos)
    AZURE_OPENAI = "azure_openai"  # Azure OpenAI Service


class LLMClientAdapter:
    """Cliente LLM para geração de datasets com retry logic e JSON parsing."""

    def __init__(
        self,
        provider: LLMProvider,
        api_key: Optional[str] = None,
        model_name: str = "llama2",
        endpoint_url: Optional[str] = None,
        temperature: float = 0.7,
    ):
        """
        Inicializa LLM client.

        Args:
            provider: Provider do LLM (openai, anthropic, local)
            api_key: API key para OpenAI/Anthropic (não necessário para local)
            model_name: Nome do modelo (gpt-4, claude-3-opus, llama2, etc.)
            endpoint_url: URL base customizada (default baseado no provider)
            temperature: Temperature para sampling (0.0-1.0, default 0.7)
        """
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.base_url = endpoint_url or self._get_default_base_url(provider)
        self.client: Optional[httpx.AsyncClient] = None

        # Validar configuração
        cloud_providers = (
            LLMProvider.OPENAI, LLMProvider.ANTHROPIC, LLMProvider.DEEPSEEK,
            LLMProvider.GROQ, LLMProvider.TOGETHER, LLMProvider.OPENROUTER,
            LLMProvider.AZURE_OPENAI
        )
        if provider in cloud_providers and not api_key:
            logger.warning(
                "llm_api_key_missing",
                provider=provider.value,
                message="API key não fornecida, geração pode falhar",
            )

    def _get_default_base_url(self, provider: LLMProvider) -> str:
        """Retorna base URL padrão por provider."""
        base_urls = {
            LLMProvider.OPENAI: "https://api.openai.com/v1",
            LLMProvider.ANTHROPIC: "https://api.anthropic.com/v1",
            LLMProvider.LOCAL: "http://ollama:11434/api",
            LLMProvider.DEEPSEEK: "https://api.deepseek.com/v1",
            LLMProvider.GROQ: "https://api.groq.com/openai/v1",
            LLMProvider.TOGETHER: "https://api.together.xyz/v1",
            LLMProvider.OPENROUTER: "https://openrouter.ai/api/v1",
            LLMProvider.AZURE_OPENAI: "",  # Requer endpoint_url customizado
        }
        return base_urls[provider]

    async def start(self):
        """Inicializa cliente HTTP com base_url e headers configurados."""
        headers = {}

        # Configurar headers de autenticação para providers de nuvem
        if self.api_key and self.provider != LLMProvider.LOCAL:
            # Providers OpenAI-compatible (usam Bearer token)
            openai_compatible = (
                LLMProvider.OPENAI, LLMProvider.DEEPSEEK, LLMProvider.GROQ,
                LLMProvider.TOGETHER, LLMProvider.AZURE_OPENAI
            )
            if self.provider in openai_compatible:
                headers["Authorization"] = f"Bearer {self.api_key}"
            elif self.provider == LLMProvider.OPENROUTER:
                headers["Authorization"] = f"Bearer {self.api_key}"
                headers["HTTP-Referer"] = "https://neural-hive-mind.local"  # Requerido pelo OpenRouter
                headers["X-Title"] = "Neural Hive Mind Dataset Generator"
            elif self.provider == LLMProvider.ANTHROPIC:
                headers["x-api-key"] = self.api_key
                headers["anthropic-version"] = "2023-06-01"

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=120.0
        )
        logger.info("llm_client_started", provider=self.provider.value, model=self.model_name, base_url=self.base_url)

    async def stop(self):
        """Fecha cliente HTTP."""
        if self.client:
            await self.client.aclose()
            logger.info("llm_client_stopped")

    async def generate_json(self, prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Gera JSON válido usando LLM com retry logic.

        Args:
            prompt: Prompt para geração
            max_retries: Número máximo de tentativas

        Returns:
            Dict com JSON parseado

        Raises:
            Exception: Se falhar após max_retries
        """
        for attempt in range(max_retries):
            try:
                # Chamar LLM baseado no provider
                # Providers OpenAI-compatible
                openai_compatible = (
                    LLMProvider.OPENAI, LLMProvider.DEEPSEEK, LLMProvider.GROQ,
                    LLMProvider.TOGETHER, LLMProvider.OPENROUTER, LLMProvider.AZURE_OPENAI
                )
                if self.provider in openai_compatible:
                    response_text = await self._call_openai(prompt, self.temperature)
                elif self.provider == LLMProvider.ANTHROPIC:
                    response_text = await self._call_anthropic(prompt, self.temperature)
                elif self.provider == LLMProvider.LOCAL:
                    response_text = await self._call_ollama(prompt, self.temperature)
                else:
                    raise ValueError(f"Provider não suportado: {self.provider}")

                # Extrair e validar JSON
                json_data = self._extract_json_from_response(response_text)

                logger.debug(
                    "json_generated_successfully",
                    provider=self.provider.value,
                    attempt=attempt + 1,
                )

                return json_data

            except json.JSONDecodeError as e:
                logger.warning(
                    "json_decode_error",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                )

                if attempt < max_retries - 1:
                    # Exponential backoff
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    raise Exception(f"Falha ao gerar JSON válido após {max_retries} tentativas")

            except Exception as e:
                logger.error("llm_generation_error", attempt=attempt + 1, error=str(e))
                raise

        raise Exception("Erro inesperado na geração de JSON")

    async def _call_openai(self, prompt: str, temperature: float) -> str:
        """Chama OpenAI API."""
        if not self.client:
            raise RuntimeError("Cliente não inicializado. Chame start() primeiro.")

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()

        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def _call_anthropic(self, prompt: str, temperature: float) -> str:
        """Chama Anthropic API."""
        if not self.client:
            raise RuntimeError("Cliente não inicializado. Chame start() primeiro.")

        payload = {
            "model": self.model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }

        response = await self.client.post("/messages", json=payload)
        response.raise_for_status()

        data = response.json()
        return data["content"][0]["text"]

    async def _call_ollama(self, prompt: str, temperature: float) -> str:
        """Chama Ollama local API."""
        if not self.client:
            raise RuntimeError("Cliente não inicializado. Chame start() primeiro.")

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }

        response = await self.client.post("/generate", json=payload)
        response.raise_for_status()

        data = response.json()
        return data["response"]

    def _extract_json_from_response(self, response_text: str) -> Dict[str, Any]:
        """
        Extrai JSON de resposta do LLM.

        Remove markdown code blocks e comentários.

        Args:
            response_text: Texto de resposta do LLM

        Returns:
            Dict com JSON parseado

        Raises:
            json.JSONDecodeError: Se JSON for inválido
        """
        # Remover markdown code blocks
        response_text = re.sub(r"```json\s*", "", response_text)
        response_text = re.sub(r"```\s*", "", response_text)

        # Remover comentários de linha única
        response_text = re.sub(r"//.*", "", response_text)

        # Remover comentários de múltiplas linhas
        response_text = re.sub(r"/\*.*?\*/", "", response_text, flags=re.DOTALL)

        # Trim whitespace
        response_text = response_text.strip()

        # Validar e parsear JSON
        json_data = json.loads(response_text)

        if not isinstance(json_data, dict):
            raise json.JSONDecodeError(
                "Resposta não é um objeto JSON", response_text, 0
            )

        return json_data
