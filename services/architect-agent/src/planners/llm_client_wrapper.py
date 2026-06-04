"""
Wrapper LLM Client para architect-agent usando neural_hive_llm.

Mantém compatibilidade com a API existente do architect-agent enquanto usa
a biblioteca centralizada neural_hive_llm internamente.
"""

import structlog

from neural_hive_llm import LLMClient as NeuralHiveLLMClient, LLMProvider, LLMResponse
from src.config.settings import get_settings

logger = structlog.get_logger()


class LLMClient:
    """
    Cliente unificado para OpenAI e Anthropic usando neural_hive_llm.

    Wrapper que mantém a API existente do architect-agent (generate)
    enquanto delega para a biblioteca neural_hive_llm.
    """

    def __init__(self):
        """Inicializa o cliente LLM."""
        settings = get_settings()
        self.provider = settings.llm.provider
        self.api_key = settings.llm.api_key
        self.model = settings.llm.model
        self.timeout = settings.llm.timeout_seconds
        self.max_tokens = settings.llm.max_tokens

        # Criar cliente neural_hive_llm interno
        self._client: NeuralHiveLLMClient | None = None

    async def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Gera resposta do LLM.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema opcional

        Returns:
            String com a resposta gerada
        """
        if not self._client:
            # Inicializar lazy
            await self._initialize_client()

        if not self._client:
            # Fallback: retornar resposta padrão
            return self._get_default_response(prompt)

        try:
            response: LLMResponse = await self._client.generate(
                prompt=prompt, system_prompt=system_prompt
            )
            return response.text

        except Exception as e:
            logger.warning("llm_generate_failed", error=str(e))
            return self._get_default_response(prompt)

    async def _initialize_client(self):
        """Inicializa o cliente neural_hive_llm."""
        if not self.provider or not self.api_key:
            logger.info("llm_not_configured_using_fallback")
            return

        try:
            # Converter provider string para enum
            if self.provider == "openai":
                provider_enum = LLMProvider.OPENAI
            elif self.provider == "anthropic":
                provider_enum = LLMProvider.ANTHROPIC
            else:
                provider_enum = LLMProvider.LOCAL

            self._client = NeuralHiveLLMClient(
                provider=provider_enum,
                api_key=self.api_key,
                model=self.model,
            )
            await self._client.start()
            logger.info("llm_client_initialized", provider=self.provider)

        except Exception as e:
            logger.error("llm_client_init_failed", error=str(e))
            self._client = None

    def _get_default_response(self, prompt: str) -> str:
        """Resposta padrão quando LLM não disponível.

        Usa heurísticas simples baseadas em palavras-chave do prompt.

        Args:
            prompt: Prompt original para análise

        Returns:
            JSON string com resposta padrão
        """
        # Heurísticas simples baseadas em palavras-chave
        prompt_lower = prompt.lower()

        if "microservice" in prompt_lower or "scale" in prompt_lower:
            return """{
  "architecture_type": "microservices",
  "components": [{"name": "api", "stack": "python/fastapi", "replicas": 3}],
  "patterns": ["repository", "api_gateway"],
  "rationale": "Microservices for independent scaling"
}"""
        return """{
  "architecture_type": "monolith",
  "components": [{"name": "app", "stack": "python/fastapi", "replicas": 1}],
  "patterns": ["repository"],
  "rationale": "Monolith for simplicity and faster development"
}"""

    def get_default_response(self, prompt: str) -> str:
        """Versão pública de _get_default_response para testes."""
        return self._get_default_response(prompt)
