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
        HTTPException 503: Se o serviço ainda não foi inicializado (startup race).
            O caller (Fluxo G G1 via Temporal) interpreta 503 como transitório e
            faz retry — em vez de um 500 opaco.
    """
    if _requirements_engineer is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Requirements engineer not initialized",
        )
    return _requirements_engineer
