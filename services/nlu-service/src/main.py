"""Aplicação principal do NLU Service.

Inicia:
- API REST FastAPI na porta 8020
- Servidor gRPC na porta 8021 (background task)
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Adicionar proto dir ao sys.path antes de importar módulos que usam protobuf
proto_dir = Path(__file__).parent / "proto"
sys.path.insert(0, str(proto_dir))

from src.api.routers.nlu import router as nlu_router
from src.config.settings import get_settings
from src.services.grpc_server import serve_grpc
from src.services.nlu_pipeline import get_nlu_service

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciar ciclo de vida da aplicação."""
    logger.info("Inicializando NLU Service...")

    # Inicializar serviço NLU
    nlu_service = await get_nlu_service()
    if not nlu_service.is_ready():
        raise RuntimeError("Falha ao inicializar NLU Pipeline")

    # Iniciar servidor gRPC em background
    grpc_task = asyncio.create_task(serve_grpc(settings.grpc_port))

    yield

    # Cleanup
    logger.info("Encerrando NLU Service...")
    grpc_task.cancel()
    try:
        await grpc_task
    except asyncio.CancelledError:
        pass
    await nlu_service.close()
    logger.info("NLU Service encerrado")


app = FastAPI(
    title="NLU Service",
    description="Serviço centralizado de Processamento de Linguagem Natural",
    version=settings.service_version,
    lifespan=lifespan,
)


# Health check raiz (INV-10)
@app.get("/health")
async def root_health():
    """Health check básico."""
    return JSONResponse(
        content={
            "status": "healthy" if True else "unhealthy",
            "version": settings.service_version,
            "service": settings.service_name,
        }
    )


@app.get("/")
async def root():
    """Endpoint raiz com informações do serviço."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "description": "NLU Service - Processamento de Linguagem Natural Centralizado",
        "endpoints": {
            "rest": f"http://localhost:{settings.port}/api/v1/nlu/",
            "grpc": f"localhost:{settings.grpc_port}",
        },
        "docs": "/docs",
    }


# Incluir routers
app.include_router(nlu_router)


# Exception handlers
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Tratamento de erros de validação."""
    return JSONResponse(
        status_code=400,
        content={"error": "Bad Request", "detail": str(exc)},
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request, exc):
    """Tratamento de erros de runtime."""
    return JSONResponse(
        status_code=503,
        content={"error": "Service Unavailable", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level="info",
    )
