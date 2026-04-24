"""
Wrapper LLM Client para code-forge usando neural_hive_llm.

Mantém compatibilidade com a API existente do code-forge enquanto usa
a biblioteca centralizada neural_hive_llm internamente.
"""

from typing import Optional

import structlog

from neural_hive_llm import LLMClient as NeuralHiveLLMClient
from neural_hive_llm import LLMProvider, LLMResponse

logger = structlog.get_logger()


class LLMProvider(str):
    """Supported LLM providers (backward compatibility)."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class LLMClient:
    """
    Cliente LLM para code-forge usando neural_hive_llm.

    Wrapper que mantém a API existente do code-forge (generate_code)
    enquanto delega para a biblioteca neural_hive_llm.
    """

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.LOCAL,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4",
        endpoint_url: Optional[str] = None,
    ):
        """Inicializa cliente LLM.

        Args:
            provider: Provider LLM a utilizar
            api_key: API key para providers remotos
            model_name: Nome do modelo
            endpoint_url: URL base para provider local
        """
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.endpoint_url = endpoint_url

        # Criar cliente neural_hive_llm interno
        self._client: Optional[NeuralHiveLLMClient] = None

    async def start(self):
        """Inicializa HTTP client e provider neural_hive_llm."""
        # Converter para enum neural_hive_llm
        provider_enum = (
            LLMProvider.OPENAI
            if self.provider == "openai"
            else LLMProvider.ANTHROPIC
            if self.provider == "anthropic"
            else LLMProvider.LOCAL
        )

        self._client = NeuralHiveLLMClient(
            provider=provider_enum,
            api_key=self.api_key,
            model=self.model_name,
            base_url=self.endpoint_url,
        )
        await self._client.start()
        logger.info(
            "llm_client_initialized",
            provider=self.provider,
            model=self.model_name,
        )

    async def stop(self):
        """Fecha HTTP client."""
        if self._client:
            await self._client.stop()
        logger.info("llm_client_stopped", provider=self.provider)

    async def generate_code(
        self, prompt: str, constraints: dict, temperature: float = 0.2, stream: bool = False
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
            logger.error("llm_client_not_initialized")
            return None

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
            confidence = await self.calculate_confidence(code, constraints)

            logger.info(
                "llm_code_generated",
                provider=self.provider,
                confidence=confidence,
                code_length=len(code),
                prompt_tokens=response.prompt_tokens or 0,
                completion_tokens=response.completion_tokens or 0,
            )

            return {
                "code": code,
                "confidence_score": confidence,
                "explanation": "",  # neural_hive_llm não retorna explanation separado
                "prompt_tokens": response.prompt_tokens or 0,
                "completion_tokens": response.completion_tokens or 0,
            }

        except Exception as e:
            logger.error("llm_generation_failed", error=str(e))
            return None

    def _build_system_prompt(self, constraints: dict) -> str:
        """Constrói system prompt com constraints."""
        language = constraints.get("language", "python")
        framework = constraints.get("framework", "")
        patterns = constraints.get("patterns", [])

        prompt = f"""You are an expert software engineer specializing in {language}.
Generate production-ready, well-structured code following best practices.

Constraints:
- Language: {language}
- Framework: {framework if framework else 'None'}
- Patterns: {', '.join(patterns) if patterns else 'Standard patterns'}
- Include docstrings and type hints
- Handle errors appropriately
- Follow PEP-8 (Python) or equivalent style guides

Return ONLY valid code without markdown formatting or explanations unless requested."""

        return prompt

    def _extract_code_from_response(self, response: str) -> str:
        """Extrai código da resposta do LLM."""
        code = response.strip()

        # Remover markdown code blocks se presente
        if "```" in code:
            # Extrair conteúdo entre primeiro ``` e último ```
            parts = code.split("```")
            if len(parts) >= 3:
                code = parts[1]
                # Remover identificador de linguagem (ex: "python\n")
                if "\n" in code:
                    code = code.split("\n", 1)[1]

        return code.strip()

    def _calculate_confidence(self, code: str, constraints: dict) -> float:
        """Calcula score de confiança baseado em validações."""
        if not code:
            return 0.0

        confidence = 0.5  # Confiança base

        # Verificar se código é não-trivial
        if len(code) > 100:
            confidence += 0.1

        # Verificar docstrings/comentários
        if '"""' in code or "#" in code:
            confidence += 0.1

        # Verificar type hints (Python)
        if constraints.get("language") == "python" and "->" in code:
            confidence += 0.1

        # Verificar error handling
        if "try" in code or "except" in code or "raise" in code:
            confidence += 0.1

        # Verificar imports/dependências
        if "import" in code or "from" in code:
            confidence += 0.1

        return min(confidence, 1.0)

    async def validate_code(self, code: str, language: str) -> bool:
        """Valida sintaxe do código (simplificado)."""
        # Implementação completa usaria parsers específicos por linguagem
        # Para Python: compile(code, '<string>', 'exec')
        return bool(code and len(code) > 10)

    async def calculate_confidence(self, code: str, constraints: dict) -> float:
        """Calcula confiança final do código gerado.

        API pública recomendada para calcular confiança baseado em
        heurísticas internas e constraints fornecidos.

        Args:
            code: Código gerado
            constraints: Dict com language, framework, patterns, max_lines

        Returns:
            Score de confiança (0.0-1.0)
        """
        return self._calculate_confidence(code, constraints)
