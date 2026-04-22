"""Dependencies module for FastAPI dependency injection.

Este módulo fornece funções de dependência para injeção de dependências
do FastAPI, evitando circular imports.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.requirements_engineer import RequirementsEngineer

logger = logging.getLogger(__name__)

# Global instance - será definido em main.py
_requirements_engineer = None


def set_requirements_engineer(engineer):
    """Define a instância global do RequirementsEngineer."""
    global _requirements_engineer
    _requirements_engineer = engineer


def get_engineering_service() -> "RequirementsEngineer":
    """Retorna instância singleton do RequirementsEngineer.

    Raises:
        RuntimeError: Se o serviço não foi inicializado.
    """
    if _requirements_engineer is None:
        raise RuntimeError("Service not initialized")
    return _requirements_engineer
