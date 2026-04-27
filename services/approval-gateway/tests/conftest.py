"""Configuração pytest para Approval Gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def mock_openai_client():
    """Mock do cliente LLM usando neural_hive_llm."""
    # Mock simples da resposta
    mock_response = MagicMock()
    mock_choice = MagicMock()
    # Novo padrão: message é um dict com "content"
    mock_choice.message = {
        "content": "AVALIACAO: 85\nRACIOCINIO: Solicitação bem elaborada, requisitos claros e alinhados com os objetivos do projeto.",
        "role": "assistant",
    }
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]

    # Mock do cliente usando o novo padrão generate()
    client = MagicMock()
    client.generate = AsyncMock(return_value=mock_response)

    return client


@pytest.fixture()
def mock_mongodb():
    """Mock do cliente MongoDB."""
    mock_db = MagicMock()
    mock_collection = MagicMock()

    # Mock database methods
    mock_db.database = mock_db
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock()

    # Mock collection methods
    mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test-id"))
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_collection.count_documents = AsyncMock(return_value=0)
    mock_collection.find = MagicMock(return_value=mock_collection)
    mock_collection.sort = MagicMock(return_value=mock_collection)
    mock_collection.skip = MagicMock(return_value=mock_collection)
    mock_collection.limit = MagicMock(return_value=mock_collection)
    mock_collection.to_list = AsyncMock(return_value=[])
    mock_collection.aggregate = MagicMock(return_value=mock_collection)
    mock_collection.update_many = AsyncMock(return_value=MagicMock(modified_count=0))

    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.database = mock_db
    mock_client.client = mock_client

    with patch("src.db.mongodb.get_mongodb_client", return_value=mock_client):
        yield mock_client


@pytest.fixture()
def mock_settings():
    """Mock das configurações."""
    from src.config.settings import Settings

    settings = Settings(
        openai_api_key="test-key",
        llm_model="gpt-4-turbo-preview",
        llm_temperature=0.3,
        auto_approval_threshold=0.8,
        auto_rejection_threshold=0.3,
        require_human_threshold=0.5,
        mongodb_url="mongodb://localhost:27017",
        kafka_bootstrap_servers="localhost:9092",
    )

    with patch("src.config.settings.get_settings", return_value=settings):
        yield settings
