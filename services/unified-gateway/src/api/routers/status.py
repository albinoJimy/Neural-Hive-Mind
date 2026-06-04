"""Router para consulta de status de requests assíncronos.

Implementa GET /api/v1/nhm/status/{request_id} conforme gap identificado na spec.
Permite aos clientes consultarem o status de requests processados.
"""

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.middleware import get_auth_context_optional
from src.services.redis_client import get_redis_client

logger = structlog.get_logger(__name__)

status_router = APIRouter(tags=["Status"])

# TTL para status de requests (24 horas)
STATUS_TTL_SECONDS = 86400


class RequestStatus(BaseModel):
    """Status de um request."""

    request_id: str
    status: str  # processing, completed, failed, timeout
    flow_type: str | None = None
    processing_time_ms: int | None = None
    created_at: str
    completed_at: str | None = None
    error: str | None = None
    gateway_used: str | None = None
    data: dict[str, Any] | None = None


class StatusResponse(BaseModel):
    """Response do endpoint de status."""

    request_id: str
    exists: bool
    status: RequestStatus | None = None


async def save_request_status(
    request_id: str,
    status_value: str,
    flow_type: str | None = None,
    processing_time_ms: int | None = None,
    error: str | None = None,
    gateway_used: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Salva o status de um request no Redis.

    Args:
        request_id: ID do request
        status_value: Status (processing, completed, failed)
        flow_type: Tipo de fluxo (A-H)
        processing_time_ms: Tempo de processamento em ms
        error: Mensagem de erro (se houver)
        gateway_used: Gateway utilizado
        data: Dados adicionais
    """
    redis_client = await get_redis_client()

    if not redis_client:
        logger.warning("redis_not_available", request_id=request_id)
        return

    try:
        now = datetime.utcnow()
        now_iso = now.isoformat()

        status_data = {
            "request_id": request_id,
            "status": status_value,
            "flow_type": flow_type,
            "processing_time_ms": processing_time_ms,
            "created_at": now_iso,
            "completed_at": now_iso if status_value in ("completed", "failed") else None,
            "error": error,
            "gateway_used": gateway_used,
            "data": data,
        }

        # Serializar para JSON e salvar no Redis
        import json

        key = f"request_status:{request_id}"
        value = json.dumps(status_data)

        await redis_client.set(key, value, ex=STATUS_TTL_SECONDS)

        logger.debug(
            "status_saved",
            request_id=request_id,
            status=status_value,
        )

    except Exception as e:
        logger.exception(
            "failed_to_save_status",
            request_id=request_id,
            error=str(e),
        )


@status_router.get(
    "/api/v1/nhm/status/{request_id}",
    response_model=StatusResponse,
    summary="Consultar status de request",
    description=(
        "Retorna o status de processamento de um request. "
        "Útil para implementar polling em vez de SSE."
    ),
)
async def get_request_status(
    request_id: str,
    auth_context=Depends(get_auth_context_optional),
) -> StatusResponse:
    """
    Endpoint GET /api/v1/nhm/status/{request_id}

    Retorna o status de processamento de um request específico.

    Args:
        request_id: ID do request a consultar
        auth_context: Contexto de autenticação (opcional)

    Returns:
        StatusResponse com o status do request

    Raises:
        HTTPException: Se o request_id for inválido
    """
    # Validar formato do request_id (deve ser UUID ou similar)
    if not request_id or len(request_id) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request_id format",
        )

    redis_client = await get_redis_client()

    if not redis_client:
        # Redis indisponível - retornar status de erro
        return StatusResponse(
            request_id=request_id,
            exists=False,
            status=None,
        )

    try:
        import json

        key = f"request_status:{request_id}"
        value = await redis_client.get(key)

        if not value:
            return StatusResponse(
                request_id=request_id,
                exists=False,
                status=None,
            )

        status_data = json.loads(value)

        return StatusResponse(
            request_id=request_id,
            exists=True,
            status=RequestStatus(**status_data),
        )

    except Exception as e:
        logger.exception(
            "failed_to_get_status",
            request_id=request_id,
            error=str(e),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve status: {str(e)}",
        )


@status_router.get(
    "/api/v1/nhm/status",
    summary="Health check do endpoint de status",
    description="Verifica se o serviço de status está operacional",
)
async def status_health_check() -> dict[str, Any]:
    """Health check do endpoint de status."""
    redis_client = await get_redis_client()

    return {
        "service": "unified-gateway-status",
        "status": "healthy",
        "redis_available": redis_client is not None,
        "ttl_seconds": STATUS_TTL_SECONDS,
    }
