"""Aplicação principal Approval Gateway."""

from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import proto para AgentType (arquivos locais)
from proto import service_registry_pb2
from src.api.routers.approvals import router as approvals_router
from src.api.routers.auth import router as auth_router
from src.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from src.config.settings import get_settings

settings = get_settings()

# Global instance
_registry_client: Optional[EngineeringServiceRegistryClient] = None

# Configurar structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    global _registry_client

    logger.info("starting_service", service=settings.service_name, version=settings.service_version)

    # Registrar no Service Registry
    try:
        _registry_client = EngineeringServiceRegistryClient(
            service_name="approval-gateway",
            agent_type=service_registry_pb2.APPROVAL_GATEWAY,
        )

        if await _registry_client.initialize():
            agent_id = await _registry_client.register(
                capabilities=[
                    "approval_management",
                    "artifact_storage",
                    "jwt_tokens",
                    "authentication",
                    "notifications",
                ],
                metadata={
                    "mongodb": "enabled",
                    "jwt": "enabled",
                    "version": "1.0.0",
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="approval-gateway",
                    agent_id=agent_id,
                    port=8017,
                )
                await _registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = _registry_client
            else:
                logger.error("service_registration_failed", service="approval-gateway")
        else:
            logger.error("service_registry_init_failed", service="approval-gateway")
    except Exception as e:
        logger.error("service_registry_exception", error=str(e))

    yield

    logger.info("shutting_down_service")

    # Deregister do Service Registry
    if _registry_client:
        try:
            await _registry_client.close()
            logger.info("service_deregistered", service="approval-gateway")
        except Exception as e:
            logger.error("service_deregister_failed", error=str(e))


app = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router
app.include_router(approvals_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Endpoint raiz."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check simplificado."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=True)
