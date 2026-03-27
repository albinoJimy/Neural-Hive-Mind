"""Planejador de arquitetura usando LLM."""

import json
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from src.models.architecture import (
    ArchitecturePlan,
    ArchitectureType,
    Component,
    Pattern,
)
from src.planners.base import BasePlanner
from src.planners.llm_client import LLMClient
from src.planners.templates import SYSTEM_PROMPT, get_user_prompt


class DesignPlanner(BasePlanner):
    """Planejador de arquitetura usando LLM."""

    def __init__(self):
        """Inicializa o DesignPlanner."""
        self.llm_client = LLMClient()

    async def plan(
        self, requirements: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ArchitecturePlan:
        """Cria plano arquitetural.

        Args:
            requirements: Dicionário com requisitos do sistema
            context: Contexto adicional (não utilizado atualmente)

        Returns:
            ArchitecturePlan com a proposta gerada
        """
        # Gerar prompt
        user_prompt = get_user_prompt(requirements)

        # Chamar LLM
        response = await self.llm_client.generate(user_prompt, SYSTEM_PROMPT)

        # Parsear resposta JSON
        plan_data = self._parse_llm_response(response)

        # Criar ArchitecturePlan
        return ArchitecturePlan(
            plan_id=f"arch-{uuid.uuid4().hex[:8]}",
            cognitive_plan_id=requirements.get("cognitive_plan_id"),
            **plan_data,
        )

    async def refine(self, plan_id: str, feedback: Dict[str, Any]) -> ArchitecturePlan:
        """Refina plano existente com feedback.

        Args:
            plan_id: ID do plano a ser refinado (não utilizado diretamente)
            feedback: Feedback contendo new_intent e feedback

        Returns:
            ArchitecturePlan refinado
        """
        # Implementar refinamento baseado em feedback
        # Por simplicidade, gera novo plano com requisitos atualizados
        requirements = {
            "intent": feedback.get("new_intent", ""),
            "feedback": feedback.get("feedback", ""),
        }
        return await self.plan(requirements)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parseia resposta JSON do LLM.

        Args:
            response: String de resposta do LLM

        Returns:
            Dicionário com dados parseados ou fallback
        """
        # Extrair JSON de markdown code blocks
        json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            response = json_match.group(1)
        else:
            # Tentar extrair JSON sem markdown
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                response = json_match.group(0)

        try:
            data = json.loads(response)

            # Normalizar componentes
            components = []
            for comp in data.get("components", []):
                if isinstance(comp, dict):
                    components.append(Component(**comp))
                elif isinstance(comp, str):
                    components.append(
                        Component(name=comp, stack="python/fastapi")
                    )

            # Normalizar padrões
            patterns = []
            for p in data.get("patterns", []):
                if isinstance(p, str):
                    try:
                        patterns.append(Pattern(p))
                    except ValueError:
                        # Padrão inválido, ignorar
                        pass
                elif isinstance(p, dict):
                    try:
                        patterns.append(Pattern(p["name"]))
                    except (KeyError, ValueError):
                        # Padrão inválido, ignorar
                        pass

            # Normalizar tipo de arquitetura
            arch_type_str = data.get("architecture_type", "monolith")
            try:
                architecture_type = ArchitectureType(arch_type_str)
            except ValueError:
                architecture_type = ArchitectureType.MONOLITH

            return {
                "architecture_type": architecture_type,
                "components": components,
                "patterns": patterns,
                "rationale": data.get(
                    "rationale", "Auto-generated architecture"
                ),
                "requirements": data.get("requirements", {}),
            }
        except (json.JSONDecodeError, KeyError) as e:
            # Fallback para resposta padrão
            return {
                "architecture_type": ArchitectureType.MONOLITH,
                "components": [
                    Component(name="app", stack="python/fastapi")
                ],
                "patterns": [Pattern.REPOSITORY],
                "rationale": f"Error parsing LLM response: {str(e)}",
                "requirements": {},
            }
