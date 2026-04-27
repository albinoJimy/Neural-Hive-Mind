"""Testes unitários para Entity Extractor."""

from unittest.mock import AsyncMock

import pytest

from src.clients.llm_client_wrapper import ChatCompletion, Choice
from src.models.entities import EntityType
from src.services.entity_extractor import EntityExtractor


@pytest.fixture
def mock_llm_response():
    """Fixture para resposta mock do LLM wrapper."""
    choice = Choice(
        message={
            "role": "assistant",
            "content": """[
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
    ]""",
        }
    )
    return ChatCompletion(choices=[choice], model="gpt-4")


@pytest.fixture
def mock_llm_response_low_confidence():
    """Fixture para resposta mock com entidade de baixa confiança."""
    choice = Choice(
        message={
            "role": "assistant",
            "content": """[
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
    ]""",
        }
    )
    return ChatCompletion(choices=[choice], model="gpt-4")


@pytest.fixture
def mock_llm_response_with_context():
    """Fixture para resposta mock com contexto."""
    choice = Choice(
        message={
            "role": "assistant",
            "content": """[
        {
            "type": "tech_stack",
            "name": "PostgreSQL",
            "description": "Database system",
            "source_text": "Uses PostgreSQL for persistence",
            "confidence_score": 0.95
        }
    ]""",
        }
    )
    return ChatCompletion(choices=[choice], model="gpt-4")


@pytest.fixture
def mock_llm_response_invalid_entity():
    """Fixture para resposta mock com tipo inválido."""
    choice = Choice(
        message={
            "role": "assistant",
            "content": """[
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
    ]""",
        }
    )
    return ChatCompletion(choices=[choice], model="gpt-4")


@pytest.fixture
def mock_llm_response_markdown():
    """Fixture para resposta mock com markdown code blocks."""
    choice = Choice(
        message={
            "role": "assistant",
            "content": """```json
[
    {
        "type": "dependency",
        "name": "Redis",
        "description": "Caching layer",
        "source_text": "Uses Redis for caching",
        "confidence_score": 0.90
    }
]
```""",
        }
    )
    return ChatCompletion(choices=[choice], model="gpt-4")


@pytest.fixture
def mock_llm_response_empty():
    """Fixture para resposta mock vazia."""
    choice = Choice(message={"role": "assistant", "content": "[]"})
    return ChatCompletion(choices=[choice], model="gpt-4")


@pytest.fixture
def mock_llm_response_invalid_json():
    """Fixture para resposta mock com JSON inválido."""
    choice = Choice(message={"role": "assistant", "content": "This is not valid JSON"})
    return ChatCompletion(choices=[choice], model="gpt-4")


@pytest.mark.asyncio
async def test_extract_entities_openai(mock_llm_response):
    """Testa extração de entidades usando OpenAI (via LLMClient)."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response)

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
async def test_extract_entities_with_low_confidence(mock_llm_response_low_confidence):
    """Testa filtro de entidades com baixa confiança."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response_low_confidence)

    extractor = EntityExtractor(llm_client=mock_client, min_confidence=0.7)
    entities = await extractor.extract(document_id="doc-001", text="Test text")

    # Apenas entidade com confiança >= 0.7
    assert len(entities) == 1
    assert entities[0].name == "High Confidence"


@pytest.mark.asyncio
async def test_extract_entities_with_context(mock_llm_response_with_context):
    """Testa extração com contexto adicional."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response_with_context)

    extractor = EntityExtractor(llm_client=mock_client)
    context = {"document_type": "architecture", "section": "database"}

    entities = await extractor.extract(
        document_id="doc-003", text="Uses PostgreSQL for persistence", context=context
    )

    assert len(entities) == 1
    assert entities[0].type == EntityType.TECH_STACK


@pytest.mark.asyncio
async def test_extract_entities_filters_invalid_json(mock_llm_response_invalid_entity):
    """Testa que entidades com tipo inválido são ignoradas."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response_invalid_entity)

    extractor = EntityExtractor(llm_client=mock_client)
    entities = await extractor.extract(document_id="doc-001", text="Test text")

    # Apenas entidade válida (invalid_type não existe no enum)
    assert len(entities) == 1
    assert entities[0].name == "Valid Entity"


@pytest.mark.asyncio
async def test_extract_entities_with_markdown_response(mock_llm_response_markdown):
    """Testa parsing de resposta com markdown code blocks."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response_markdown)

    extractor = EntityExtractor(llm_client=mock_client)
    entities = await extractor.extract(document_id="doc-001", text="Uses Redis for caching")

    assert len(entities) == 1
    assert entities[0].type == EntityType.DEPENDENCY


@pytest.mark.asyncio
async def test_extract_entities_empty_result(mock_llm_response_empty):
    """Testa retorno vazio quando LLM não retorna entidades."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response_empty)

    extractor = EntityExtractor(llm_client=mock_client)
    entities = await extractor.extract(document_id="doc-001", text="No entities here")

    assert len(entities) == 0


@pytest.mark.asyncio
async def test_extract_entities_llm_error():
    """Testa tratamento de erro do LLM."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(side_effect=Exception("LLM API Error"))

    extractor = EntityExtractor(llm_client=mock_client)

    with pytest.raises(Exception) as exc_info:
        await extractor.extract(document_id="doc-001", text="Test text")

    assert "LLM API Error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_extract_entities_invalid_json(mock_llm_response_invalid_json):
    """Testa erro quando resposta não é JSON válido."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(return_value=mock_llm_response_invalid_json)

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


def test_extractor_initialization_with_provider():
    """Testa inicialização do extrator com provider específico."""
    extractor = EntityExtractor(provider="openai")
    assert extractor._provider == "openai"
    assert extractor._min_confidence == 0.7


def test_extractor_initialization_with_custom_confidence():
    """Testa inicialização do extrator com confiança customizada."""
    extractor = EntityExtractor(provider="openai", min_confidence=0.5)
    assert extractor._min_confidence == 0.5
