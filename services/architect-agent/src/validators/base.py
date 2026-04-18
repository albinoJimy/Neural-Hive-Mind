"""Interface base para validadores de arquitetura."""

from abc import ABC, abstractmethod
from typing import Any


class BaseValidator(ABC):
    """Interface base para validadores."""

    @abstractmethod
    async def validate(self, target: dict[str, Any]) -> dict[str, Any]:
        """Executa validação e retorna resultado."""
