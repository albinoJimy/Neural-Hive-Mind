"""
Exemplo de wrapper para code-forge usando neural_hive_llm.

Este exemplo mostra como criar um wrapper compatível com a API existente
do code-forge enquanto usa neural_hive_llm internamente.
"""

import asyncio
from typing import Optional

from neural_hive_llm import LLMClient as NeuralHiveLLMClient
from neural_hive_llm import LLMProvider, LLMResponse


class CodeForgeLLMClient:
    """
    Wrapper LLM Client para code-forge usando neural_hive_llm.

    Mantém compatibilidade com a API existente:
    - generate_code(prompt, constraints, temperature, stream)
    - calculate_confidence(code, constraints)
    - validate_code(code, language)
    """

    def __init__(
        self,
        provider: str = "local",
        api_key: Optional[str] = None,
        model_name: str = "gpt-4",
        endpoint_url: Optional[str] = None,
    ):
        """Inicializa cliente LLM."""
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.endpoint_url = endpoint_url
        self._client: Optional[NeuralHiveLLMClient] = None

    async def start(self):
        """Inicializa HTTP client e provider neural_hive_llm."""
        # Converter string de provider para enum
        provider_map = {
            "openai": LLMProvider.OPENAI,
            "anthropic": LLMProvider.ANTHROPIC,
            "local": LLMProvider.LOCAL,
        }
        provider_enum = provider_map.get(self.provider, LLMProvider.LOCAL)

        self._client = NeuralHiveLLMClient(
            provider=provider_enum,
            api_key=self.api_key,
            model=self.model_name,
            base_url=self.endpoint_url,
        )
        await self._client.start()
        print(f"✓ Cliente {self.provider} inicializado")

    async def stop(self):
        """Fecha HTTP client."""
        if self._client:
            await self._client.stop()
            print(f"✓ Cliente {self.provider} parado")

    async def generate_code(
        self,
        prompt: str,
        constraints: dict,
        temperature: float = 0.2,
        stream: bool = False,
    ) -> Optional[dict]:
        """Gera código usando LLM.

        Args:
            prompt: Prompt para geração de código
            constraints: Dict com language, framework, patterns, max_lines
            temperature: Temperatura de amostragem (0.0-1.0)
            stream: Habilita streaming (não suportado nesta versão)

        Returns:
            Dict com 'code', 'confidence_score', 'explanation',
                  'prompt_tokens', 'completion_tokens'
        """
        if not self._client:
            await self.start()

        try:
            # Construir system prompt com constraints
            system_prompt = self._build_system_prompt(constraints)

            # Chamar neural_hive_llm
            response: LLMResponse = await self._client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            )

            # Extrair código da resposta
            code = self._extract_code_from_response(response.text)

            # Calcular confiança
            confidence = self._calculate_confidence(code, constraints)

            print(f"✓ Código gerado: {len(code)} caracteres, confiança: {confidence:.2f}")

            return {
                "code": code,
                "confidence_score": confidence,
                "explanation": "",
                "prompt_tokens": response.prompt_tokens or 0,
                "completion_tokens": response.completion_tokens or 0,
            }

        except Exception as e:
            print(f"✗ Erro na geração: {e}")
            return None

    def _build_system_prompt(self, constraints: dict) -> str:
        """Constrói system prompt com constraints."""
        language = constraints.get("language", "python")
        framework = constraints.get("framework", "")
        patterns = constraints.get("patterns", [])

        return f"""You are an expert software engineer specializing in {language}.
Generate production-ready, well-structured code following best practices.

Constraints:
- Language: {language}
- Framework: {framework if framework else 'None'}
- Patterns: {', '.join(patterns) if patterns else 'Standard patterns'}

Return ONLY valid code without markdown formatting."""

    def _extract_code_from_response(self, response: str) -> str:
        """Extrai código da resposta do LLM."""
        code = response.strip()

        # Remover markdown code blocks
        if "```" in code:
            parts = code.split("```")
            if len(parts) >= 3:
                code = parts[1]
                if "\n" in code:
                    code = code.split("\n", 1)[1]

        return code.strip()

    def _calculate_confidence(self, code: str, constraints: dict) -> float:
        """Calcula score de confiança."""
        if not code:
            return 0.0

        confidence = 0.5

        if len(code) > 100:
            confidence += 0.1
        if '"""' in code or "#" in code:
            confidence += 0.1
        if constraints.get("language") == "python" and "->" in code:
            confidence += 0.1
        if "try" in code or "except" in code:
            confidence += 0.1
        if "import" in code or "from" in code:
            confidence += 0.1

        return min(confidence, 1.0)

    async def calculate_confidence(self, code: str, constraints: dict) -> float:
        """Calcula confiança final (API pública)."""
        return self._calculate_confidence(code, constraints)

    async def validate_code(self, code: str, language: str) -> bool:
        """Valida sintaxe do código (simplificado)."""
        return bool(code and len(code) > 10)


async def main():
    """Demonstra o wrapper code-forge."""
    print("=" * 60)
    print("Exemplo: Wrapper code-forge com neural_hive_llm")
    print("=" * 60)

    # Criar cliente
    client = CodeForgeLLMClient(
        provider="local",  # ou "openai" com API key
        model_name="llama2",
        endpoint_url="http://localhost:11434",
    )

    try:
        await client.start()

        # Gerar código Python
        print("\nGerando código Python...")
        result = await client.generate_code(
            prompt="Create a FastAPI service with a health check endpoint",
            constraints={
                "language": "python",
                "framework": "fastapi",
                "patterns": ["dependency_injection"],
                "max_lines": 100,
            },
            temperature=0.2,
        )

        if result:
            print("\n--- Código Gerado ---")
            print(result["code"][:500] + "..." if len(result["code"]) > 500 else result["code"])
            print("---\n")
            print(f"Confiança: {result['confidence_score']:.2f}")
            print(f"Tokens: {result['prompt_tokens'] + result['completion_tokens']}")

    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
