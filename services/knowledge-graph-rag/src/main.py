"""Aplicação FastAPI para Knowledge Graph RAG."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from knowledge_graph_rag.api.routers.rag import router as rag_router
from knowledge_graph_rag.api.routers.knowledge_graph import router as knowledge_router
from knowledge_graph_rag.clients.engineering_service_registry_client import (
    EngineeringServiceRegistryClient,
)
from knowledge_graph_rag.config.settings import get_settings

# Import proto para AgentType
import sys
from pathlib import Path

# Adicionar caminho para o service-registry
sr_path = Path(__file__).parent.parent.parent.parent.parent / "service-registry" / "src"
if str(sr_path) not in sys.path:
    sys.path.insert(0, str(sr_path))

from proto import service_registry_pb2

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
    """Lifecycle manager."""
    global _registry_client

    logger.info(
        "starting_service",
        service=settings.service_name,
        version=settings.service_version,
        port=settings.port,
    )

    # Registrar no Service Registry
    try:
        _registry_client = EngineeringServiceRegistryClient(
            service_name="knowledge-graph-rag",
            agent_type=service_registry_pb2.KNOWLEDGE_GRAPH_RAG,
        )

        if await _registry_client.initialize():
            agent_id = await _registry_client.register(
                capabilities=[
                    "rag_query",
                    "contextual_retrieval",
                    "template_indexing",
                    "code_indexing",
                ],
                metadata={
                    "neo4j": "enabled",
                    "qdrant": "enabled",
                    "version": "1.0.0",
                },
            )

            if agent_id:
                logger.info(
                    "service_registered_successfully",
                    service="knowledge-graph-rag",
                    agent_id=agent_id,
                    port=8016,
                )
                await _registry_client.start_heartbeat(interval_seconds=30)
                app.state.registry_client = _registry_client
            else:
                logger.error("service_registration_failed", service="knowledge-graph-rag")
        else:
            logger.error("service_registry_init_failed", service="knowledge-graph-rag")
    except Exception as e:
        logger.error("service_registry_exception", error=str(e))

    yield

    logger.info("shutting_down_service", service=settings.service_name)

    # Deregister do Service Registry
    if _registry_client:
        try:
            await _registry_client.close()
            logger.info("service_deregistered", service="knowledge-graph-rag")
        except Exception as e:
            logger.error("service_deregister_failed", error=str(e))


app = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir routers
app.include_router(rag_router, prefix=settings.api_prefix)
app.include_router(knowledge_router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Endpoint raiz."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"service": "knowledge-graph-rag", "status": "healthy", "version": settings.api_version}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
