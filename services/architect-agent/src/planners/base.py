"""Interface base para planners de arquitetura."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from src.models.architecture import ArchitecturePlan
from src.models.validation import ValidationReport


class BasePlanner(ABC):
    """Interface base para planners de arquitetura."""

    @abstractmethod
    async def plan(
        self, requirements: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> ArchitecturePlan:
        """Cria um plano arquitetural baseado nos requisitos.

        Args:
            requirements: Dicionário com requisitos do sistema
            context: Contexto adicional opcional

        Returns:
            ArchitecturePlan com a proposta arquitetural
        """
        pass

    @abstractmethod
    async def refine(self, plan_id: str, feedback: Dict[str, Any]) -> ArchitecturePlan:
        """Refina um plano existente com feedback.

        Args:
            plan_id: ID do plano a ser refinado
            feedback: Feedback para refinamento

        Returns:
            ArchitecturePlan refinado
        """
        pass
