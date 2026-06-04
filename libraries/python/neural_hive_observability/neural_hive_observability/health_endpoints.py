"""
Health endpoints padronizados para Neural Hive-Mind.

Fornece helpers para criar endpoints de health check (startup, liveness, readiness)
compatíveis com Kubernetes probes, seguindo padrões consistentes entre serviços.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

UTC = timezone.utc
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field


class StartupResponse(BaseModel):
    """Response model para startup probe."""

    status: str = Field(description="Status do serviço: started ou starting")
    service: str = Field(description="Nome do serviço")
    version: str = Field(description="Versão do serviço")
    started_at: str = Field(description="Timestamp ISO 8601 de quando o serviço iniciou")


class HealthResponse(BaseModel):
    """Response model para liveness probe."""

    status: str = Field(description="Status do serviço: healthy, unhealthy, degraded")
    service: str = Field(description="Nome do serviço")
    version: str = Field(description="Versão do serviço")


def create_startup_router(
    service_name: str,
    service_version: str,
) -> APIRouter:
    """
    Cria router FastAPI com endpoint /health/startup.

    Este endpoint é usado como startup probe pelo Kubernetes para garantir
    que o serviço está pronto para receber tráfego antes de ser marcado
    como Ready.

    Args:
        service_name: Nome do serviço (ex: "gateway-intencoes")
        service_version: Versão do serviço (ex: "1.0.0")

    Returns:
        APIRouter configurado com o endpoint /health/startup

    Example:
        ```python
        from fastapi import FastAPI
        from neural_hive_observability import create_startup_router

        app = FastAPI()
        startup_router = create_startup_router("my-service", "1.0.0")
        app.include_router(startup_router)
        # Para adicionar prefixo:
        # app.include_router(startup_router, prefix="/api/v1")
        ```
    """
    router = APIRouter()

    @router.get("/health/startup", response_model=StartupResponse, status_code=200)
    async def startup_check() -> StartupResponse:
        """
        Startup probe para Kubernetes.

        Retorna status indicando que o serviço iniciou com sucesso.
        Usado por Kubernetes como startupProbe para determinar quando
        marcar o Pod como Ready.

        Returns:
            StartupResponse com status, nome do serviço, versão e timestamp
        """
        return StartupResponse(
            status="started",
            service=service_name,
            version=service_version,
            started_at=datetime.now(UTC).isoformat(),
        )

    return router


def create_liveness_router(
    service_name: str,
    service_version: str,
    health_check_fn: Optional[Callable[[], Awaitable[str]]] = None,
) -> APIRouter:
    """
    Cria router FastAPI com endpoint /health/live.

    Este endpoint é usado como liveness probe pelo Kubernetes para determinar
    se o contêiner precisa ser reiniciado.

    Args:
        service_name: Nome do serviço
        service_version: Versão do serviço
        health_check_fn: Função opcional para verificar saúde do serviço

    Returns:
        APIRouter configurado com o endpoint /health/live

    Example:
        ```python
        from neural_hive_observability import create_liveness_router

        async def check_health():
            return "healthy"

        liveness_router = create_liveness_router(
            "my-service", "1.0.0", health_check_fn=check_health
        )
        ```
    """
    router = APIRouter()

    @router.get("/health/live", response_model=HealthResponse, status_code=200)
    async def liveness_check() -> HealthResponse:
        """
        Liveness probe para Kubernetes.

        Verifica se o serviço está rodando. Se falhar repetidamente,
        Kubernetes reiniciará o contêiner.

        Returns:
            HealthResponse com status atual do serviço
        """
        status = "healthy"
        if health_check_fn:
            try:
                result = await health_check_fn()
                if result:
                    status = result
            except Exception:
                status = "unhealthy"

        return HealthResponse(
            status=status,
            service=service_name,
            version=service_version,
        )

    return router


def create_readiness_router(
    service_name: str,
    service_version: str,
    health_check_fn: Optional[Callable[[], Awaitable[str]]] = None,
) -> APIRouter:
    """
    Cria router FastAPI com endpoint /health/ready.

    Este endpoint é usado como readiness probe pelo Kubernetes para determinar
    se o contêiner está pronto para receber tráfego.

    Args:
        service_name: Nome do serviço
        service_version: Versão do serviço
        health_check_fn: Função opcional para verificar dependências críticas

    Returns:
        APIRouter configurado com o endpoint /health/ready

    Example:
        ```python
        from neural_hive_observability import create_readiness_router

        async def check_ready():
            # Verificar dependências (DB, Kafka, etc.)
            return "ready"

        readiness_router = create_readiness_router(
            "my-service", "1.0.0", health_check_fn=check_ready
        )
        ```
    """
    router = APIRouter()

    @router.get("/health/ready", response_model=HealthResponse, status_code=200)
    async def readiness_check() -> HealthResponse:
        """
        Readiness probe para Kubernetes.

        Verifica se o serviço está pronto para receber tráfego.
        Se não estiver pronto, Kubernetes remove o Pod dos Services.

        Returns:
            HealthResponse com status de prontidão do serviço
        """
        status = "ready"
        if health_check_fn:
            try:
                result = await health_check_fn()
                if result:
                    status = result
            except Exception:
                status = "not_ready"

        return HealthResponse(
            status=status,
            service=service_name,
            version=service_version,
        )

    return router
