"""Interface base para validadores de arquitetura."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseValidator(ABC):
    """Interface base para validadores."""

    @abstractmethod
    async def validate(self, target: Dict[str, Any]) -> Dict[str, Any]:
        """Executa validação e retorna resultado."""
        pass
