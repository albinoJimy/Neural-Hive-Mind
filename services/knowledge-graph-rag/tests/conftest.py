"""Configuração pytest para Knowledge Graph RAG."""

import pytest
from unittest.mock import AsyncMock, Mock


@pytest.fixture
def mock_llm_client():
    """Mock do cliente LLM (wrapper neural_hive_llm)."""
    from knowledge_graph_rag.clients.llm_client_wrapper import LLMClient, ChatCompletion

    client = Mock(spec=LLMClient)

    async def mock_generate(messages, model=None, temperature=0.7, max_tokens=None):
        return ChatCompletion.from_text("Resposta de teste", model or "gpt-4")

    client.generate = AsyncMock(side_effect=mock_generate)

    return client


# Alias para compatibilidade
mock_openai_client = mock_llm_client


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
        qdrant_collection="test_collection",
    )

    with patch("src.config.settings.get_settings", return_value=settings):
        yield settings
