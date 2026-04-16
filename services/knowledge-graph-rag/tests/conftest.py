"""Configuração pytest para Knowledge Graph RAG."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from openai import AsyncOpenAI


@pytest.fixture
def mock_openai_client():
    """Mock do cliente OpenAI."""
    client = AsyncMock(spec=AsyncOpenAI)

    # Mock embeddings
    client.embeddings.create = AsyncMock(
        return_value=MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )
    )

    # Mock chat completions
    client.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="Resposta de teste"))]
        )
    )

    return client


@pytest.fixture
def mock_settings():
    """Mock das configurações."""
    from unittest.mock import patch
    from src.config.settings import Settings

    settings = Settings(
        openai_api_key="test-key",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
        qdrant_url="http://localhost:6333",
        qdrant_collection="test_collection"
    )

    with patch("src.config.settings.get_settings", return_value=settings):
        yield settings
