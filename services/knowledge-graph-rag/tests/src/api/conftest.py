"""Configuração pytest para API tests."""

import sys
from unittest.mock import Mock
import pytest
from fastapi import FastAPI


# Mock service_registry_pb2 antes de importar main
sys.modules["proto"] = Mock()
sys.modules["proto"].service_registry_pb2 = Mock()
sys.modules["proto"].service_registry_pb2.KNOWLEDGE_GRAPH_RAG = 7


@pytest.fixture
def app():
    """App FastAPI para teste sem lifespan."""
    from knowledge_graph_rag.api.routers.rag import router as rag_router
    from knowledge_graph_rag.api.routers.knowledge_graph import router as knowledge_router
    from knowledge_graph_rag.config.settings import get_settings

    settings = get_settings()

    app = FastAPI(title=settings.api_title)

    # Incluir routers
    app.include_router(rag_router, prefix=settings.api_prefix)
    app.include_router(knowledge_router, prefix=settings.api_prefix)

    @app.get("/")
    async def root():
        return {"service": "knowledge-graph-rag", "version": settings.api_version}

    @app.get("/health")
    async def health_check():
        return {"service": "knowledge-graph-rag", "status": "healthy"}

    return app


@pytest.fixture
def client(app):
    """Cliente de teste."""
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def mock_rag_service():
    """Mock do serviço RAG."""
    from unittest.mock import AsyncMock

    service = Mock()
    service.create_node = AsyncMock()
    service.create_relation = AsyncMock()
    service.search = AsyncMock()
    service.query_with_rag = AsyncMock()

    return service
