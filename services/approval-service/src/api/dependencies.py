"""
FastAPI Dependencies

Dependencias injetaveis para os endpoints da API.
"""

from typing import Optional
from fastapi import Depends

from src.config.settings import Settings, get_settings
from src.services.approval_service import ApprovalService


# Referencia global para o servico
_approval_service: Optional[ApprovalService] = None


def set_approval_service(service: ApprovalService):
    """Define referencia para o servico de aprovacao"""
    global _approval_service
    _approval_service = service


async def get_approval_service() -> ApprovalService:
    """
    Dependencia para obter servico de aprovacao

    Returns:
        Instancia do ApprovalService

    Raises:
        RuntimeError: Se servico nao inicializado
    """
    if _approval_service is None:
        raise RuntimeError("ApprovalService nao inicializado")
    return _approval_service
