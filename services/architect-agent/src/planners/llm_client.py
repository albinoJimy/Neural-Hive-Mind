"""Cliente unificado para OpenAI e Anthropic LLMs."""

from typing import Optional

from src.config.settings import get_settings


class LLMClient:
    """Cliente unificado para OpenAI e Anthropic."""

    def __init__(self):
        """Inicializa o cliente LLM."""
        settings = get_settings()
        self.provider = settings.llm.provider
        self.api_key = settings.llm.api_key
        self.model = settings.llm.model
        self.timeout = settings.llm.timeout_seconds
        self.max_tokens = settings.llm.max_tokens

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Gera resposta do LLM.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema opcional

        Returns:
            String com a resposta gerada
        """
        if not self.provider or not self.api_key:
            # Fallback: retornar resposta padrão
            return self._get_default_response(prompt)

        if self.provider == "openai":
            return await self._generate_openai(prompt, system_prompt)
        elif self.provider == "anthropic":
            return await self._generate_anthropic(prompt, system_prompt)
        else:
            return self._get_default_response(prompt)

    async def _generate_openai(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Gera resposta usando OpenAI.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema opcional

        Returns:
            String com a resposta gerada
        """
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.api_key)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            return response.choices[0].message.content
        except Exception:
            # Fallback em erro
            return self._get_default_response(prompt)

    async def _generate_anthropic(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Gera resposta usando Anthropic.

        Args:
            prompt: Prompt principal
            system_prompt: Prompt de sistema opcional

        Returns:
            String com a resposta gerada
        """
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.api_key)

            messages = [{"role": "user", "content": prompt}]

            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or "",
                messages=messages,
            )
            return response.content[0].text
        except Exception:
            return self._get_default_response(prompt)

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
        else:
            return """{
  "architecture_type": "monolith",
  "components": [{"name": "app", "stack": "python/fastapi", "replicas": 1}],
  "patterns": ["repository"],
  "rationale": "Monolith for simplicity and faster development"
}"""
