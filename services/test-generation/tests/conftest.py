"""Configuração pytest para Test Generation."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add project root to Python path for "from src.xyz import" imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@pytest.fixture()
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


@pytest.fixture()
def mock_settings():
    """Mock das configurações."""
    from unittest.mock import patch

    from src.config.settings import Settings

    settings = Settings(
        openai_api_key="test-key",
        llm_model="gpt-4-turbo-preview",
        mongodb_url="mongodb://localhost:27017",
    )

    with patch("src.config.settings.get_settings", return_value=settings):
        yield settings
