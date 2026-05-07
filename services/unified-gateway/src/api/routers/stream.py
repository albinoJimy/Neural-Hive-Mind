"""Router para SSE Streaming de status de requests.

Implementa GET /api/v1/nhm/stream/{request_id} conforme gap identificado na spec.
Permite aos clientes receberem atualizações em tempo real via Server-Sent Events.
"""

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.middleware import get_auth_context_optional
from src.services.redis_client import get_redis_client

logger = structlog.get_logger(__name__)

stream_router = APIRouter(tags=["Stream"])

# Timeout para streams (30 segundos)
STREAM_TIMEOUT_SECONDS = 30

# Intervalo entre eventos de keep-alive (5 segundos)
KEEP_ALIVE_INTERVAL_SECONDS = 5


class StreamEvent(BaseModel):
    """Evento SSE para streaming."""

    event: str  # "status", "completed", "error", "keep-alive"
    data: dict[str, Any]
    retry: int | None = None


async def _generate_sse(event: StreamEvent) -> str:
    """Gera linha no formato SSE.

    Formato: event: {event}\ndata: {json}\n\n
    """
    line = f"event: {event.event}\n"
    line += f"data: {json.dumps(event.data)}\n"

    if event.retry is not None:
        line += f"retry: {event.retry}\n"

    line += "\n"
    return line


async def _status_event_generator(
    request_id: str,
    timeout_seconds: int = STREAM_TIMEOUT_SECONDS,
) -> AsyncGenerator[str, None]:
    """Gerador de eventos SSE para status de request.

    Args:
        request_id: ID do request a monitorar
        timeout_seconds: Tempo máximo de espera

    Yields:
        Strings no formato SSE
    """
    start_time = asyncio.get_event_loop().time()

    # Evento inicial
    yield await _generate_sse(StreamEvent(
        event="connected",
        data={"request_id": request_id, "message": "Stream connected"},
        retry=3000,  # Cliente deve reconectar após 3s
    ))

    last_status = None
    completed = False

    while True:
        # Verificar timeout
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout_seconds:
            yield await _generate_sse(StreamEvent(
                event="timeout",
                data={"request_id": request_id, "message": "Stream timeout"},
            ))
            break

        try:
            redis_client = await get_redis_client()

            if redis_client:
                # Buscar status no Redis
                key = f"request_status:{request_id}"
                value = await redis_client.get(key)

                if value:
                    status_data = json.loads(value)

                    # Verificar se status mudou
                    if status_data != last_status:
                        last_status = status_data

                        # Determinar tipo de evento
                        status_value = status_data.get("status")
                        if status_value == "completed":
                            yield await _generate_sse(StreamEvent(
                                event="completed",
                                data=status_data,
                            ))
                            completed = True
                            break
                        elif status_value == "failed":
                            yield await _generate_sse(StreamEvent(
                                event="error",
                                data=status_data,
                            ))
                            completed = True
                            break
                        elif status_value == "processing":
                            yield await _generate_sse(StreamEvent(
                                event="status",
                                data=status_data,
                            ))

        except Exception as e:
            logger.warning(
                "stream_error",
                request_id=request_id,
                error=str(e),
            )

        # Se não completado, enviar keep-alive e continuar
        if not completed:
            yield await _generate_sse(StreamEvent(
                event="keep-alive",
                data={"timestamp": datetime.utcnow().isoformat()},
            ))

            # Aguardar antes da próxima verificação
            await asyncio.sleep(KEEP_ALIVE_INTERVAL_SECONDS)

    # Evento final
    yield await _generate_sse(StreamEvent(
        event="end",
        data={"request_id": request_id, "message": "Stream ended"},
    ))


@stream_router.get(
    "/api/v1/nhm/stream/{request_id}",
    summary="Stream de status via SSE",
    description=(
        "Retorna stream de eventos Server-Sent Events para monitoramento "
        "em tempo real do status de um request."
    ),
)
async def stream_request_status(
    request_id: str,
    timeout: int = Query(
        default=STREAM_TIMEOUT_SECONDS,
        ge=5,
        le=300,
        description="Timeout do stream em segundos",
    ),
    auth_context=Depends(get_auth_context_optional),
) -> StreamingResponse:
    """
    Endpoint GET /api/v1/nhm/stream/{request_id}

    Retorna stream SSE com atualizações de status em tempo real.

    Args:
        request_id: ID do request a monitorar
        timeout: Tempo máximo de espera (padrão: 30s)
        auth_context: Contexto de autenticação (opcional)

    Returns:
        StreamingResponse com eventos SSE

    Raises:
        HTTPException: Se o request_id for inválido
    """
    # Validar formato do request_id
    if not request_id or len(request_id) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request_id format",
        )

    logger.info(
        "stream_started",
        request_id=request_id,
        timeout=timeout,
    )

    return StreamingResponse(
        _status_event_generator(request_id, timeout),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Desabilitar buffering em nginx
        },
    )


@stream_router.get(
    "/api/v1/nhm/stream",
    summary="Health check do streaming",
    description="Verifica se o serviço de streaming está operacional",
)
async def stream_health_check() -> dict[str, Any]:
    """Health check do endpoint de streaming."""
    redis_client = await get_redis_client()

    return {
        "service": "unified-gateway-stream",
        "status": "healthy",
        "redis_available": redis_client is not None,
        "stream_timeout_seconds": STREAM_TIMEOUT_SECONDS,
        "keep_alive_interval_seconds": KEEP_ALIVE_INTERVAL_SECONDS,
    }
