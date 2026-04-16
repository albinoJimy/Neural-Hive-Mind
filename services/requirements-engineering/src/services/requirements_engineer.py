"""Serviço para geração de requisitos funcionais e não-funcionais."""

import json
import uuid
from typing import Any

import structlog
from openai import AsyncOpenAI
from pydantic import ValidationError
from src.config.settings import get_settings
from src.models.requirements import (
    Requirement,
    RequirementPriority,
    RequirementsSet,
    RequirementType,
)

logger = structlog.get_logger(__name__)

# Prompt template para geração de requisitos
REQUIREMENTS_GENERATION_PROMPT = """
Você é um engenheiro de requisitos especialista. Analise o seguinte plano cognitivo e gere uma lista completa de requisitos.

**Plano Cognitivo:**
{plan_text}

**Instruções:**
1. Gere requisitos funcionais e não-funcionais
2. Cada requisito deve ter:
   - ID único no formato REQ-XXX
   - Título claro
   - Descrição detalhada
   - Prioridade (critical, high, medium, low)
   - Tipo (functional, non_functional)
   - Rationale (justificativa)

3. Inclua pelo menos:
   - 3-5 requisitos funcionais
   - 2-3 requisitos não-funcionais (performance, segurança, usabilidade)

Responda em JSON válido:
[
  {{
    "id": "REQ-001",
    "title": "Título",
    "description": "Descrição detalhada",
    "priority": "high",
    "type": "functional",
    "rationale": "Justificativa"
  }}
]
"""

DEPENDENCY_ANALYSIS_PROMPT = """
Analise as dependências entre os seguintes requisitos:

{requirements_text}

Identifique:
1. Quais requisitos dependem de outros (pré-requisitos)
2. Quais requisitos conflitam entre si

Responda em JSON:
[
  {{
    "id": "REQ-001",
    "dependencies": ["REQ-002"],
    "conflicts": []
  }}
]
"""


class RequirementsEngineer:
    """Serviço para engenharia de requisitos usando LLM."""

    def __init__(self, llm_client: AsyncOpenAI | None = None):
        """
        Inicializa o RequirementsEngineer.

        Args:
            llm_client: Cliente OpenAI (opcional, cria padrão se não fornecido)
        """
        settings = get_settings()
        self._llm_client = llm_client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        self._logger = logger

    async def generate_from_cognitive_plan(
        self, plan_id: str, plan_text: str, context: dict[str, Any] | None = None
    ) -> RequirementsSet:
        """
        Gera requisitos a partir de um plano cognitivo.

        Args:
            plan_id: ID do CognitivePlan
            plan_text: Texto do plano
            context: Contexto adicional

        Returns:
            RequirementsSet com requisitos gerados
        """
        self._logger.info("generating_requirements", plan_id=plan_id)

        prompt = REQUIREMENTS_GENERATION_PROMPT.format(plan_text=plan_text)

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um engenheiro de requisitos especialista.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4000,
            )

            content = response.choices[0].message.content

            # Extrair JSON da resposta
            json_match = self._extract_json(content)
            if json_match:
                requirements_data = json.loads(json_match)
            else:
                requirements_data = json.loads(content)

            # Criar objetos Requirement
            requirements = []
            for req_data in requirements_data:
                try:
                    req = Requirement(
                        id=req_data.get("id", f"REQ-{uuid.uuid4().hex[:6]}"),
                        title=req_data.get("title", "Sem título"),
                        description=req_data.get("description", ""),
                        priority=RequirementPriority(req_data.get("priority", "medium")),
                        requirement_type=RequirementType(req_data.get("type", "functional")),
                        rationale=req_data.get("rationale", ""),
                    )
                    requirements.append(req)
                except ValidationError as e:
                    self._logger.warning("invalid_requireation_skipping", error=str(e))
                    continue

            # Criar RequirementsSet
            requirements_set = RequirementsSet(
                id=f"RS-{uuid.uuid4().hex[:8]}", cognitive_plan_id=plan_id
            )

            for req in requirements:
                requirements_set.add_requirement(req)

            self._logger.info(
                "requirements_generated",
                plan_id=plan_id,
                total=len(requirements),
                functional=requirements_set.functional_count,
                non_functional=requirements_set.non_functional_count,
            )

            return requirements_set

        except Exception as e:
            self._logger.error("failed_to_generate_requirements", error=str(e))
            raise

    async def prioritize_requirements(self, requirements: list[Requirement]) -> list[Requirement]:
        """
        Prioriza requisitos baseado em impacto e urgência.

        Args:
            requirements: Lista de requisitos

        Returns:
            Lista de requisitos ordenada por prioridade
        """
        priority_order = {
            RequirementPriority.CRITICAL: 0,
            RequirementPriority.HIGH: 1,
            RequirementPriority.MEDIUM: 2,
            RequirementPriority.LOW: 3,
        }

        return sorted(requirements, key=lambda r: priority_order.get(r.priority, 99))

    async def analyze_dependencies(self, requirements: list[Requirement]) -> list[Requirement]:
        """
        Analisa dependências entre requisitos usando LLM.

        Args:
            requirements: Lista de requisitos

        Returns:
            Lista de requisitos com dependências preenchidas
        """
        self._logger.info("analyzing_dependencies", count=len(requirements))

        # Preparar texto dos requisitos
        requirements_text = "\n".join(
            [f"{r.id}: {r.title} - {r.description[:100]}..." for r in requirements]
        )

        prompt = DEPENDENCY_ANALYSIS_PROMPT.format(requirements_text=requirements_text)

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "Você é um analista de requisitos especialista."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )

            content = response.choices[0].message.content

            # Extrair JSON
            json_match = self._extract_json(content)
            if json_match:
                dependencies_data = json.loads(json_match)
            else:
                dependencies_data = json.loads(content)

            # Atualizar requisitos com dependências
            req_map = {r.id: r for r in requirements}

            for dep_data in dependencies_data:
                req_id = dep_data.get("id")
                if req_id in req_map:
                    req = req_map[req_id]
                    req.dependencies = dep_data.get("dependencies", [])
                    req.conflicts = dep_data.get("conflicts", [])

            return list(req_map.values())

        except Exception as e:
            self._logger.error("failed_to_analyze_dependencies", error=str(e))
            # Retornar requisitos sem análise de dependências
            return requirements

    def _extract_json(self, text: str) -> str | None:
        """Extrai JSON de texto markdown."""
        import re

        # Tentar encontrar JSON em bloques markdown
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # Tentar encontrar JSON sem markdown
        json_match = re.search(r"\[.*\]", text, re.DOTALL)
        if json_match:
            return json_match.group(0)

        return None
