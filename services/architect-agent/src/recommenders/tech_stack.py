"""Tech Stack Recommender using LLM."""

import json

from structlog import get_logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from neural_hive_llm import LLMClient, LLMProvider, LLMResponse
from src.models.tech_stack import TechChoice, TechStackRecommendation
from src.recommenders.knowledge_base import TECH_KNOWLEDGE_BASE

logger = get_logger(__name__)


class TechStackRecommender:
    """Recomenda stack tecnológico baseado em requisitos."""

    PROMPT_TEMPLATE = """
Analise os requisitos e recomende um stack tecnológico.

REQUISITOS:
{requirements}

RESTRIÇÕES:
{constraints}

Baseado no conhecimento disponível, recomenda tecnologias para:
1. Backend framework
2. Database primária
3. Cache/Messaging (se necessário)

Para cada escolha, justifique com base nos requisitos.

Responda em JSON:
{{
  "choices": [
    {{"category": "backend", "name": "FastAPI", "version": "0.104", "rationale": "..."}},
    {{"category": "database", "name": "PostgreSQL", "version": "15", "rationale": "..."}}
  ],
  "constraints_satisfied": ["Python", "PostgreSQL"],
  "constraints_violated": [],
  "confidence_score": 0.9,
  "estimated_complexity": "media",
  "estimated_cost": "$$$"
}}
"""

    def __init__(self, llm_client: LLMClient | None = None, model: str = "gpt-4"):
        """
        Inicializa o recomendador de stack tecnológico.

        Args:
            llm_client: Cliente LLM (opcional, cria padrão se não fornecido)
            model: Modelo LLM a usar
        """
        self._llm_client = llm_client
        self._model = model
        self._logger = logger
        self._knowledge_base = TECH_KNOWLEDGE_BASE
        self._llm_started = False

    async def _ensure_llm_started(self):
        """Garante que o cliente LLM está inicializado."""
        if not self._llm_client:
            # Criar cliente padrão com settings
            from src.config.settings import get_settings

            settings = get_settings()
            if not settings.llm.provider or not settings.llm.api_key:
                raise ConnectionError("LLM not configured: provider or api_key missing")

            provider = (
                LLMProvider.OPENAI if settings.llm.provider == "openai" else LLMProvider.ANTHROPIC
            )
            self._llm_client = LLMClient(
                provider=provider, api_key=settings.llm.api_key, model=self._model
            )
            await self._llm_client.start()
            self._llm_started = True
        elif not self._llm_started:
            await self._llm_client.start()
            self._llm_started = True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )
    async def _call_llm(self, prompt: str) -> dict:
        """Chama LLM com retry logic.

        Args:
            prompt: Prompt completo

        Returns:
            Dict com resposta JSON

        Raises:
            ConnectionError: Se falhar após 3 tentativas
            TimeoutError: Se timeout após 3 tentativas
        """
        await self._ensure_llm_started()

        response: LLMResponse = await self._llm_client.generate(
            prompt=prompt,
            system_prompt="Você é um arquiteto de software especialista. Responda em JSON válido.",
        )

        return json.loads(response.text)

    async def recommend(
        self, requirements: str, constraints: list[dict] | None = None
    ) -> TechStackRecommendation:
        """
        Recomenda stack tecnológico.

        Args:
            requirements: Descrição dos requisitos do sistema
            constraints: Lista de restrições técnicas (opcional)

        Returns:
            TechStackRecommendation com escolhas tecnológicas

        Raises:
            ConnectionError: Se LLM API falhar após retries
            TimeoutError: Se LLM API timeout após retries
        """
        self._logger.info("recommending_tech_stack", constraints=constraints)

        prompt = self.PROMPT_TEMPLATE.format(
            requirements=requirements, constraints=self._format_constraints(constraints or [])
        )

        try:
            # Chamar LLM com retry logic
            result_data = await self._call_llm(prompt)

            choices = [
                TechChoice(
                    category=choice["category"],
                    name=choice["name"],
                    version=choice.get("version"),
                    rationale=choice["rationale"],
                )
                for choice in result_data.get("choices", [])
            ]

            recommendation = TechStackRecommendation(
                choices=choices,
                constraints_satisfied=result_data.get("constraints_satisfied", []),
                constraints_violated=result_data.get("constraints_violated", []),
                confidence_score=result_data.get("confidence_score", 0.8),
                estimated_complexity=result_data.get("estimated_complexity"),
                estimated_cost=result_data.get("estimated_cost"),
            )

            self._logger.info(
                "tech_stack_recommended",
                choices_count=len(choices),
                complexity=recommendation.estimated_complexity,
            )

            return recommendation

        except (ConnectionError, TimeoutError):
            # Re-raise retry errors com contexto
            self._logger.error("tech_stack_llm_failed_after_retries")
            raise
        except Exception as e:
            # Log outros errors inesperados
            self._logger.error(
                "failed_to_recommend_tech_stack", error=str(e), error_type=type(e).__name__
            )
            raise

    def _format_constraints(self, constraints: list[dict]) -> str:
        """Formata restrições para o prompt."""
        if not constraints:
            return "Nenhuma"

        return "\n".join(f"- {c.get('type', 'N/A')}: {c.get('value', 'N/A')}" for c in constraints)
