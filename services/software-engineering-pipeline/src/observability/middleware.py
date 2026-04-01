"""Middleware para tracking de métricas de requisições da API."""

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.observability.metrics import MetricsHelper


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware para coletar métricas de requisições HTTP."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Processa a requisição e coleta métricas."""
        start_time = time.time()

        # Processa a requisição
        response = await call_next(request)

        # Calcula duração
        duration = time.time() - start_time

        # Extrai nome do endpoint (remove prefixo /api/v1)
        path = request.url.path
        if path.startswith("/api/v1/"):
            endpoint = path[len("/api/v1/") :].split("?")[0].split("/")[0]
        elif path == "/health" or path == "/ping" or path == "/status":
            endpoint = path.lstrip("/")
        elif path == "/metrics":
            # Não registrar métricas do endpoint de métricas
            return response
        else:
            endpoint = "unknown"

        # Registra a métrica
        MetricsHelper.record_api_request(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
            duration=duration,
        )

        return response
