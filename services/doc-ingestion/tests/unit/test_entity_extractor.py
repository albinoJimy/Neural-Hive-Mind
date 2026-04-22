"""Testes unitários para Entity Extractor."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.models.entities import EntityType
from src.services.entity_extractor import EntityExtractor


@pytest.fixture
def mock_openai_response():
    """Fixture para resposta mock do OpenAI."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = """[
        {
            "type": "functionality",
            "name": "User Authentication",
            "description": "Users can authenticate with email and password",
            "source_text": "The system shall support user authentication...",
            "confidence_score": 0.95
        },
        {
            "type": "requirement",
            "name": "Password Requirements",
            "description": "Passwords must be at least 8 characters",
            "source_text": "Passwords shall be minimum 8 characters...",
            "confidence_score": 0.90
        },
        {
            "type": "api",
            "name": "GET /api/users",
            "description": "Endpoint to list users",
            "source_text": "GET /api/users returns a list of users",
            "confidence_score": 0.88
        }
    ]"""
    return mock_response


@pytest.fixture
def mock_anthropic_response():
    """Fixture para resposta mock do Anthropic."""
    mock_response = Mock()
    mock_content = Mock()
    mock_content.text = """[
        {
            "type": "data_model",
            "name": "User",
            "description": "User entity with authentication fields",
            "source_text": "User model contains id, email, password_hash",
            "confidence_score": 0.92
        }
    ]"""
    mock_response.content = [mock_content]
    return mock_response


@pytest.mark.asyncio
async def test_extract_entities_openai(mock_openai_response):
    """Testa extração de entidades usando OpenAI."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)

    extractor = EntityExtractor(llm_client=mock_client, min_confidence=0.7)
    entities = await extractor.extract(
        document_id="doc-001",
        text="The system shall support user authentication with email and password. Passwords shall be minimum 8 characters.",
    )

    assert len(entities) == 3
    assert entities[0].type == EntityType.FUNCTIONALITY
    assert entities[0].name == "User Authentication"
    assert entities[0].confidence_score == 0.95
    assert entities[1].type == EntityType.REQUIREMENT
    assert entities[1].name == "Password Requirements"
    assert entities[2].type == EntityType.API


@pytest.mark.asyncio
async def test_extract_entities_anthropic(mock_anthropic_response):
    """Testa extração de entidades usando Anthropic."""
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_anthropic_response)

    extractor = EntityExtractor(llm_client=mock_client, provider="anthropic", min_confidence=0.7)
    entities = await extractor.extract(
        document_id="doc-002",
        text="User model contains id, email, password_hash",
    )

    assert len(entities) == 1
    assert entities[0].type == EntityType.DATA_MODEL
    assert entities[0].name == "User"
    assert entities[0].confidence_score == 0.92


@pytest.mark.asyncio
async def test_extract_entities_with_low_confidence():
    """Testa filtro de entidades com baixa confiança."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = """[
        {
            "type": "functionality",
            "name": "High Confidence",
            "description": "Test",
            "source_text": "Test",
            "confidence_score": 0.85
        },
        {
            "type": "functionality",
            "name": "Low Confidence",
            "description": "Test",
            "source_text": "Test",
            "confidence_score": 0.45
        }
    ]"""

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    extractor = EntityExtractor(llm_client=mock_client, min_confidence=0.7)
    entities = await extractor.extract(document_id="doc-001", text="Test text")

    # Apenas entidade com confiança >= 0.7
    assert len(entities) == 1
    assert entities[0].name == "High Confidence"


@pytest.mark.asyncio
async def test_extract_entities_with_context():
    """Testa extração com contexto adicional."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = """[
        {
            "type": "tech_stack",
            "name": "PostgreSQL",
            "description": "Database system",
            "source_text": "Uses PostgreSQL for persistence",
            "confidence_score": 0.95
        }
    ]"""

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    extractor = EntityExtractor(llm_client=mock_client)
    context = {"document_type": "architecture", "section": "database"}

    entities = await extractor.extract(
        document_id="doc-003", text="Uses PostgreSQL for persistence", context=context
    )

    assert len(entities) == 1
    assert entities[0].type == EntityType.TECH_STACK


@pytest.mark.asyncio
async def test_extract_entities_filters_invalid_json():
    """Testa que entidades com tipo inválido são ignoradas."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = """[
        {
            "type": "functionality",
            "name": "Valid Entity",
            "description": "Test",
            "source_text": "Test",
            "confidence_score": 0.85
        },
        {
            "type": "invalid_type",
            "name": "Invalid Entity",
            "description": "Test",
            "source_text": "Test",
            "confidence_score": 0.75
        }
    ]"""

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    extractor = EntityExtractor(llm_client=mock_client)
    entities = await extractor.extract(document_id="doc-001", text="Test text")

    # Apenas entidade válida (invalid_type não existe no enum)
    assert len(entities) == 1
    assert entities[0].name == "Valid Entity"


@pytest.mark.asyncio
async def test_extract_entities_with_markdown_response():
    """Testa parsing de resposta com markdown code blocks."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = """```json
[
    {
        "type": "dependency",
        "name": "Redis",
        "description": "Caching layer",
        "source_text": "Uses Redis for caching",
        "confidence_score": 0.90
    }
]
```"""

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    extractor = EntityExtractor(llm_client=mock_client)
    entities = await extractor.extract(document_id="doc-001", text="Uses Redis for caching")

    assert len(entities) == 1
    assert entities[0].type == EntityType.DEPENDENCY


@pytest.mark.asyncio
async def test_extract_entities_empty_result():
    """Testa retorno vazio quando LLM não retorna entidades."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = "[]"

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    extractor = EntityExtractor(llm_client=mock_client)
    entities = await extractor.extract(document_id="doc-001", text="No entities here")

    assert len(entities) == 0


@pytest.mark.asyncio
async def test_extract_entities_llm_error():
    """Testa tratamento de erro do LLM."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM API Error"))

    extractor = EntityExtractor(llm_client=mock_client)

    with pytest.raises(Exception) as exc_info:
        await extractor.extract(document_id="doc-001", text="Test text")

    assert "LLM API Error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_extract_entities_invalid_json():
    """Testa erro quando resposta não é JSON válido."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message = Mock()
    mock_response.choices[0].message.content = "This is not valid JSON"

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    extractor = EntityExtractor(llm_client=mock_client)

    with pytest.raises(ValueError) as exc_info:
        await extractor.extract(document_id="doc-001", text="Test text")

    assert "not valid JSON" in str(exc_info.value)


def test_system_prompt_content():
    """Testa que o system prompt contém instruções corretas."""
    extractor = EntityExtractor(llm_client=AsyncMock())
    prompt = extractor._get_system_prompt()

    assert "expert software analyst" in prompt.lower()
    assert "functionalities" in prompt.lower()
    assert "requirements" in prompt.lower()
    assert "data models" in prompt.lower()
    assert "apis" in prompt.lower()
    assert "confidence_score" in prompt.lower()


def test_build_extraction_prompt():
    """Testa construção do prompt de extração."""
    extractor = EntityExtractor(llm_client=AsyncMock())
    prompt = extractor._build_extraction_prompt("Sample text", {"key": "value"})

    assert "Sample text" in prompt
    assert "Additional Context" in prompt
    assert "key" in prompt
    assert "value" in prompt


def test_build_extraction_prompt_without_context():
    """Testa construção do prompt sem contexto."""
    extractor = EntityExtractor(llm_client=AsyncMock())
    prompt = extractor._build_extraction_prompt("Sample text", None)

    assert "Sample text" in prompt
    assert "Additional Context" not in prompt


def test_build_extraction_prompt_truncates_long_text():
    """Testa que texto longo é truncado."""
    extractor = EntityExtractor(llm_client=AsyncMock())
    long_text = "x" * 15000  # Maior que max_text_length
    prompt = extractor._build_extraction_prompt(long_text, None)

    assert len(prompt) < 20000
    assert "truncated" in prompt.lower()
