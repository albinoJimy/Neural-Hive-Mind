"""Configuração pytest para Test Generation."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_openai_client():
    """Mock do cliente OpenAI."""
    client = AsyncMock()

    # Mock chat completions
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()

    mock_message.content = """\
import pytest

def test_example_feature():
    \"\"\"Test example feature works correctly.\"\"\"
    assert True
"""
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]

    client.chat.completions.create = AsyncMock(return_value=mock_response)

    return client


@pytest.fixture
def mock_settings():
    """Mock das configurações."""
    from unittest.mock import patch

    from config.settings import Settings

    settings = Settings(
        openai_api_key="test-key",
        llm_model="gpt-4-turbo-preview",
        mongodb_url="mongodb://localhost:27017",
    )

    with patch("config.settings.get_settings", return_value=settings):
        yield settings
