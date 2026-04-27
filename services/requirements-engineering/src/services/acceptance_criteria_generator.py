"""Serviço para geração de Critérios de Aceitação."""

import json
import uuid

import structlog
from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import get_settings
from src.models.acceptance_criteria import (
    AcceptanceCriteriaSet,
    AcceptanceCriterion,
    CriterionType,
)
from src.models.user_story import UserStory

logger = structlog.get_logger(__name__)

ACCEPTANCE_CRITERIA_PROMPT = """
Você é um especialista em Scrum e Critérios de Aceitação. Analise a seguinte User Story e gere critérios de aceitação.

**User Story:**
{user_story}

**Instruções:**
1. Gere 3-5 critérios de aceitação para a User Story
2. Use o formato Given-When-Then (GWT)
3. Inclua GIVEN (contexto), WHEN (acção), THEN (resultado esperado)
4. Retorne APENAS JSON válido

**Formato JSON:**
[
  {{
    "id": "AC-001",
    "statement": "Declaração completa do critério",
    "given": "Contexto inicial",
    "when": "Acção ou evento",
    "then": "Resultado esperado",
    "type": "functional|performance|usability|security|compliance"
  }}
]
"""


class AcceptanceCriteriaGenerator:
    """Serviço para geração de Critérios de Aceitação usando LLM."""

    def __init__(self, llm_client: LLMClient | None = None):
        """Inicializa o AcceptanceCriteriaGenerator.

        Args:
            llm_client: Cliente LLM (opcional, cria padrão se não fornecido)
        """
        settings = get_settings()
        self._llm_client = llm_client or LLMClient()
        self._model = settings.llm_model
        self._logger = logger

    async def generate_for_user_story(
        self,
        user_story: UserStory,
    ) -> list[AcceptanceCriterion]:
        """Gera critérios de aceitação para uma user story.

        Args:
            user_story: User Story alvo

        Returns:
            Lista de critérios de aceitação
        """
        self._logger.info("generating_acceptance_criteria", story_id=user_story.id)

        story_text = user_story.get_user_story_format()
        prompt = ACCEPTANCE_CRITERIA_PROMPT.format(user_story=story_text)

        try:
            response = await self._llm_client.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um especialista em Scrum e Critérios de Aceitação.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self._model,
                temperature=0.6,
                max_tokens=2000,
            )

            content = response.choices[0].message["content"]

            # Extrair JSON da resposta
            json_match = self._extract_json(content)
            if json_match:
                criteria_data = json.loads(json_match)
            else:
                criteria_data = json.loads(content)

            # Criar objetos AcceptanceCriterion
            criteria = []
            for criterion_data in criteria_data:
                try:
                    criterion = AcceptanceCriterion(
                        id=criterion_data.get("id", f"AC-{uuid.uuid4().hex[:6].upper()}"),
                        user_story_id=user_story.id,
                        criterion_type=self._parse_type(criterion_data.get("type", "functional")),
                        statement=criterion_data.get("statement", ""),
                        given=criterion_data.get("given"),
                        when=criterion_data.get("when"),
                        then=criterion_data.get("then"),
                    )
                    criteria.append(criterion)
                except Exception as e:
                    self._logger.warning("invalid_criterion_skipping", error=str(e))
                    continue

            self._logger.info(
                "acceptance_criteria_generated",
                story_id=user_story.id,
                total=len(criteria),
            )

            return criteria

        except Exception as e:
            self._logger.error("failed_to_generate_acceptance_criteria", error=str(e))
            raise

    async def generate_for_stories(
        self,
        user_stories: list[UserStory],
    ) -> dict[str, AcceptanceCriteriaSet]:
        """Gera critérios para múltiplas user stories.

        Args:
            user_stories: Lista de user stories

        Returns:
            Dicionário mapeando story_id para AcceptanceCriteriaSet
        """
        result: dict[str, AcceptanceCriteriaSet] = {}

        for story in user_stories:
            criteria = await self.generate_for_user_story(story)

            criteria_set = AcceptanceCriteriaSet(
                id=f"ACS-{uuid.uuid4().hex[:8].upper()}",
                parent_id=story.id,
                parent_type="user_story",
            )

            for criterion in criteria:
                criteria_set.add_criterion(criterion)

            result[story.id] = criteria_set

        return result

    def _parse_type(self, value: str) -> CriterionType:
        """Converte string para CriterionType."""
        mapping = {
            "functional": CriterionType.FUNCTIONAL,
            "performance": CriterionType.PERFORMANCE,
            "usability": CriterionType.USABILITY,
            "security": CriterionType.SECURITY,
            "compliance": CriterionType.COMPLIANCE,
        }
        return mapping.get(value.lower(), CriterionType.FUNCTIONAL)

    def _extract_json(self, text: str) -> str | None:
        """Extrai JSON de texto markdown."""
        import re

        # Tentar encontrar JSON em blocos markdown
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # Tentar encontrar JSON sem markdown
        json_match = re.search(r"\[.*\]", text, re.DOTALL)
        if json_match:
            return json_match.group(0)

        return None
