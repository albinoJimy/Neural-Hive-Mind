"""HTTP middleware that emits Prometheus metrics for every request."""

from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.observability import record_request


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records latency, status code and method for every request.

    Excludes ``/metrics`` itself (would create self-referential noise)
    and the OpenAPI/health paths that already have their own probes.
    """

    DEFAULT_EXCLUDE_PATHS: tuple[str, ...] = (
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
    )

    def __init__(self, app, *, exclude_paths: tuple[str, ...] | None = None) -> None:
        super().__init__(app)
        self.exclude_paths = exclude_paths or self.DEFAULT_EXCLUDE_PATHS

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in self.exclude_paths):
            return await call_next(request)

        started = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # FastAPI converte excepções em 500 mais à frente; metricamos
            # como 500 para que não percamos as falhas no histograma.
            status_code = 500
            raise
        finally:
            elapsed = time.perf_counter() - started
            record_request(
                method=request.method,
                path=path,
                status_code=status_code,
                latency_seconds=elapsed,
            )
