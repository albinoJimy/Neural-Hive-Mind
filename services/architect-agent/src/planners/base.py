"""Interface base para planners de arquitetura."""

from abc import ABC, abstractmethod
from typing import Any

from src.models.architecture import ArchitecturePlan


class BasePlanner(ABC):
    """Interface base para planners de arquitetura."""

    @abstractmethod
    async def plan(
        self, requirements: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ArchitecturePlan:
        """Cria um plano arquitetural baseado nos requisitos.

        Args:
            requirements: Dicionário com requisitos do sistema
            context: Contexto adicional opcional

        Returns:
            ArchitecturePlan com a proposta arquitetural
        """

    @abstractmethod
    async def refine(self, plan_id: str, feedback: dict[str, Any]) -> ArchitecturePlan:
        """Refina um plano existente com feedback.

        Args:
            plan_id: ID do plano a ser refinado
            feedback: Feedback para refinamento

        Returns:
            ArchitecturePlan refinado
        """
