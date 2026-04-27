"""Serviço para geração de User Stories."""

import json
import uuid

import structlog
from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import get_settings
from src.models.requirements import Requirement
from src.models.user_story import StorySize, UserStory, UserStorySet

logger = structlog.get_logger(__name__)

USER_STORY_GENERATION_PROMPT = """
Você é um especialista em Product Ownership e User Stories. Analise o seguinte requisito e decomponha em User Stories.

**Requisito:**
{title}
{description}

**Instruções:**
1. Decomponha o requisito em User Stories menores e acionáveis
2. Cada User Story deve seguir o formato: Como [role], eu quero [action], para que [benefit]
3. Atribua um tamanho estimado (xs, s, m, l, xl)
4. Retorne APENAS JSON válido

**Formato JSON:**
[
  {{
    "id": "US-001",
    "role": "papel do utilizador",
    "action": "acção desejada",
    "benefit": "benefício esperado",
    "size": "xs|s|m|l|xl"
  }}
]
"""


class UserStoryGenerator:
    """Serviço para geração de User Stories usando LLM."""

    def __init__(self, llm_client: LLMClient | None = None):
        """Inicializa o UserStoryGenerator.

        Args:
            llm_client: Cliente LLM (opcional, cria padrão se não fornecido)
        """
        settings = get_settings()
        self._llm_client = llm_client or LLMClient(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def generate_from_requirement(
        self,
        requirement: Requirement,
    ) -> list[UserStory]:
        """Gera user stories a partir de um requisito.

        Args:
            requirement: Requisito a decompor

        Returns:
            Lista de User Stories
        """
        self._logger.info("generating_user_stories", requirement_id=requirement.id)

        prompt = USER_STORY_GENERATION_PROMPT.format(
            title=requirement.title,
            description=requirement.description,
        )

        try:
            response = await self._llm_client.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um especialista em Product Ownership e User Stories.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self._model,
                temperature=0.7,
                max_tokens=2000,
            )

            content = response.choices[0].message["content"]

            # Extrair JSON da resposta
            json_match = self._extract_json(content)
            if json_match:
                stories_data = json.loads(json_match)
            else:
                stories_data = json.loads(content)

            # Criar objetos UserStory
            stories = []
            for story_data in stories_data:
                try:
                    story = UserStory(
                        id=story_data.get("id", f"US-{uuid.uuid4().hex[:6].upper()}"),
                        requirement_id=requirement.id,
                        role=story_data.get("role", "utilizador"),
                        action=story_data.get("action", ""),
                        benefit=story_data.get("benefit", ""),
                        size=self._parse_size(story_data.get("size", "m")),
                    )
                    stories.append(story)
                except Exception as e:
                    self._logger.warning("invalid_story_skipping", error=str(e))
                    continue

            self._logger.info(
                "user_stories_generated",
                requirement_id=requirement.id,
                total=len(stories),
            )

            return stories

        except Exception as e:
            self._logger.error("failed_to_generate_user_stories", error=str(e))
            raise

    async def generate_from_requirements(
        self,
        requirements: list[Requirement],
    ) -> UserStorySet:
        """Gera user stories para múltiplos requisitos.

        Args:
            requirements: Lista de requisitos

        Returns:
            UserStorySet com todas as stories
        """
        all_stories: list[UserStory] = []

        for requirement in requirements:
            stories = await self.generate_from_requirement(requirement)
            all_stories.extend(stories)

        # Criar UserStorySet
        story_set = UserStorySet(
            id=f"USS-{uuid.uuid4().hex[:8].upper()}",
            requirements_set_id=requirements[0].cognitive_plan_id or "unknown",
        )

        for story in all_stories:
            story_set.add_story(story)

        return story_set

    def _parse_size(self, value: str) -> StorySize:
        """Converte string para StorySize."""
        mapping = {
            "xs": StorySize.EXTRA_SMALL,
            "s": StorySize.SMALL,
            "m": StorySize.MEDIUM,
            "l": StorySize.LARGE,
            "xl": StorySize.EXTRA_LARGE,
        }
        return mapping.get(value.lower(), StorySize.MEDIUM)

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
