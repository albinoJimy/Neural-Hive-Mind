"""Planejador de arquitetura usando LLM."""

import json
import re
import uuid
from typing import Any, Dict, List, Optional

from pydantic import ValidationError
from openai import AsyncOpenAI

from src.models.architecture import (
    ArchitecturePlan,
    ArchitectureType,
    Component,
    Pattern,
)
from src.models.bounded_context import BoundedContext
from src.models.tech_stack import TechChoice
from src.planners.base import BasePlanner
from src.planners.llm_client import LLMClient
from src.planners.templates import SYSTEM_PROMPT, get_user_prompt

# Novos módulos (opcionais)
try:
    from src.identifiers.bounded_contexts import BoundedContextsIdentifier
    from src.recommenders.tech_stack import TechStackRecommender
    from src.generators.architecture_diagram_generator import ArchitectureDiagramGenerator
    EXTENDED_MODULES_AVAILABLE = True
except ImportError:
    EXTENDED_MODULES_AVAILABLE = False


class DesignPlanner(BasePlanner):
    """Planejador de arquitetura usando LLM."""

    def __init__(
        self,
        bounded_contexts_identifier: Optional[BoundedContextsIdentifier] = None,
        tech_stack_recommender: Optional[TechStackRecommender] = None,
        diagram_generator: Optional[ArchitectureDiagramGenerator] = None,
        use_extended_features: bool = True,
    ):
        """Inicializa o DesignPlanner.

        Args:
            bounded_contexts_identifier: Identificador de bounded contexts
            tech_stack_recommender: Recomendador de stack tecnológico
            diagram_generator: Gerador de diagramas
            use_extended_features: Se False, desativa novos módulos para testes
        """
        self.llm_client = LLMClient()
        self._use_extended_features = use_extended_features

        if use_extended_features:
            # Tentar criar AsyncOpenAI client
            llm = None
            try:
                import os
                if os.getenv("OPENAI_API_KEY"):
                    llm = AsyncOpenAI()
            except Exception:
                pass

            # Inicializar novos módulos apenas se LLM disponível
            if llm:
                self._bounded_contexts_identifier = bounded_contexts_identifier or BoundedContextsIdentifier(llm)
                self._tech_stack_recommender = tech_stack_recommender or TechStackRecommender(llm)
                self._diagram_generator = diagram_generator or ArchitectureDiagramGenerator()
            else:
                # Módulos desativados
                self._bounded_contexts_identifier = None
                self._tech_stack_recommender = None
                self._diagram_generator = None
        else:
            self._bounded_contexts_identifier = None
            self._tech_stack_recommender = None
            self._diagram_generator = None

    async def plan(
        self, requirements: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ArchitecturePlan:
        """Cria plano arquitetural.

        Args:
            requirements: Dicionário com requisitos do sistema
            context: Contexto adicional

        Returns:
            ArchitecturePlan com a proposta gerada
        """
        # Gerar componentes e padrões usando LLM existente
        user_prompt = get_user_prompt(requirements)
        response = await self.llm_client.generate(user_prompt, SYSTEM_PROMPT)
        plan_data = self._parse_llm_response(response)

        # Criar ArchitecturePlan
        return ArchitecturePlan(
            plan_id=f"arch-{uuid.uuid4().hex[:8]}",
            cognitive_plan_id=requirements.get("cognitive_plan_id"),
            architecture_type=plan_data["architecture_type"],
            components=plan_data["components"],
            patterns=plan_data["patterns"],
            rationale=plan_data["rationale"],
            requirements=plan_data["requirements"],
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

    def _extract_requirements_text(self, requirements: Dict[str, Any]) -> str:
        """Extrai texto de requisitos do dicionário.

        Args:
            requirements: Dicionário com requisitos

        Returns:
            String com texto dos requisitos
        """
        if isinstance(requirements, str):
            return requirements

        # Tentar encontrar campo 'intent' ou 'requirements'
        if "intent" in requirements:
            return str(requirements["intent"])
        if "requirements" in requirements:
            return str(requirements["requirements"])
        if "description" in requirements:
            return str(requirements["description"])

        # Fallback: converter dicionário para string
        return json.dumps(requirements, ensure_ascii=False)

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
                    # Filtrar apenas campos permitidos pelo modelo Component
                    allowed_fields = {"name", "stack", "replicas", "ha", "resources"}
                    filtered_comp = {k: v for k, v in comp.items() if k in allowed_fields}
                    # Garantir campos obrigatórios
                    if "name" not in filtered_comp:
                        filtered_comp["name"] = "unknown"
                    if "stack" not in filtered_comp:
                        filtered_comp["stack"] = "python/fastapi"
                    components.append(Component(**filtered_comp))
                elif isinstance(comp, str):
                    components.append(Component(name=comp, stack="python/fastapi"))

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
                "rationale": data.get("rationale", "Auto-generated architecture"),
                "requirements": data.get("requirements", {}),
            }
        except (json.JSONDecodeError, KeyError, ValidationError) as e:
            # Fallback para resposta padrão
            return {
                "architecture_type": ArchitectureType.MONOLITH,
                "components": [Component(name="app", stack="python/fastapi")],
                "patterns": [Pattern.REPOSITORY],
                "rationale": f"Error parsing LLM response: {str(e)}",
                "requirements": {},
            }
