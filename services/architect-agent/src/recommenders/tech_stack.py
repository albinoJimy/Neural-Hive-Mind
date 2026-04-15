"""Tech Stack Recommender using LLM."""

from typing import List, Optional
import json
from openai import AsyncOpenAI
from structlog import get_logger

from src.models.tech_stack import (
    TechStackRecommendation,
    TechChoice,
    Constraint
)
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

    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4"
    ):
        """
        Inicializa o recomendador de stack tecnológico.

        Args:
            llm_client: Cliente OpenAI (opcional, cria padrão se não fornecido)
            model: Modelo LLM a usar
        """
        self._llm_client = llm_client or AsyncOpenAI()
        self._model = model
        self._logger = logger
        self._knowledge_base = TECH_KNOWLEDGE_BASE

    async def recommend(
        self,
        requirements: str,
        constraints: Optional[List[dict]] = None
    ) -> TechStackRecommendation:
        """
        Recomenda stack tecnológico.

        Args:
            requirements: Descrição dos requisitos do sistema
            constraints: Lista de restrições técnicas (opcional)

        Returns:
            TechStackRecommendation com escolhas tecnológicas
        """
        self._logger.info("recommending_tech_stack", constraints=constraints)

        prompt = self.PROMPT_TEMPLATE.format(
            requirements=requirements,
            constraints=self._format_constraints(constraints or [])
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "Você é um arquiteto de software especialista."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            result_data = json.loads(response.choices[0].message.content)

            choices = [
                TechChoice(
                    category=choice["category"],
                    name=choice["name"],
                    version=choice.get("version"),
                    rationale=choice["rationale"]
                )
                for choice in result_data.get("choices", [])
            ]

            recommendation = TechStackRecommendation(
                choices=choices,
                constraints_satisfied=result_data.get("constraints_satisfied", []),
                constraints_violated=result_data.get("constraints_violated", []),
                confidence_score=result_data.get("confidence_score", 0.8),
                estimated_complexity=result_data.get("estimated_complexity"),
                estimated_cost=result_data.get("estimated_cost")
            )

            self._logger.info(
                "tech_stack_recommended",
                choices_count=len(choices),
                complexity=recommendation.estimated_complexity
            )

            return recommendation

        except Exception as e:
            self._logger.error("failed_to_recommend_tech_stack", error=str(e))
            raise

    def _format_constraints(self, constraints: List[dict]) -> str:
        """Formata restrições para o prompt."""
        if not constraints:
            return "Nenhuma"

        return "\n".join(
            f"- {c.get('type', 'N/A')}: {c.get('value', 'N/A')}"
            for c in constraints
        )
