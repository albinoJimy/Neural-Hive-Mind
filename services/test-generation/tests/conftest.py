"""Configuração pytest para Test Generation."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add src to Python path para imports diretos de models, services, etc.
src_root = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_root))


@pytest.fixture()
def mock_openai_client():
    """Mock do cliente LLM (compatível com neural_hive_llm)."""
    client = AsyncMock()

    # Mock generate method
    mock_response = MagicMock()
    mock_choice = MagicMock()

    # Usar dict para message (compatível com neural_hive_llm)
    mock_choice.message = {
        "role": "assistant",
        "content": """\
import pytest

def test_example_feature():
    \"\"\"Test example feature works correctly.\"\"\"
    assert True
""",
    }
    mock_response.choices = [mock_choice]

    client.generate = AsyncMock(return_value=mock_response)

    return client


@pytest.fixture()
def mock_settings():
    """Mock das configurações."""
    from unittest.mock import patch

    from config.settings import Settings

    settings = Settings.model_construct(
        openai_api_key="test-key",
        llm_model="gpt-4-turbo-preview",
        mongodb_url="mongodb://localhost:27017",
    )

    with patch("config.settings.get_settings", return_value=settings):
        yield settings
