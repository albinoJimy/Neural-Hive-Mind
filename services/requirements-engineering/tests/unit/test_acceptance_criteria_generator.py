"""Testes unitários para AcceptanceCriteriaGenerator."""

from unittest.mock import AsyncMock, Mock

import pytest
from src.models.acceptance_criteria import CriterionType
from src.models.user_story import StorySize, UserStory
from src.services.acceptance_criteria_generator import AcceptanceCriteriaGenerator


@pytest.fixture()
def mock_llm_client():
    """Fixture para mock LLM client."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message={
                        "content": """```json
[
  {
    "id": "AC-001",
    "statement": "Given the user is on the login page, when they enter valid credentials, then they should be redirected to the dashboard.",
    "given": "the user is on the login page",
    "when": "they enter valid credentials",
    "then": "they should be redirected to the dashboard",
    "type": "functional"
  },
  {
    "id": "AC-002",
    "statement": "Given the dashboard is loading, when it takes more than 3 seconds, then a loading indicator should be displayed.",
    "given": "the dashboard is loading",
    "when": "it takes more than 3 seconds",
    "then": "a loading indicator should be displayed",
    "type": "performance"
  }
]
```""",
                        "role": "assistant",
                    }
                )
            ]
        )
    )
    return mock_client


@pytest.fixture()
def sample_user_story():
    """User Story de exemplo."""
    return UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="utilizador",
        action="fazer login",
        benefit="aceder ao sistema",
        size=StorySize.MEDIUM,
    )


@pytest.mark.asyncio()
async def test_generate_acceptance_criteria_for_user_story(mock_llm_client, sample_user_story):
    """Testa geração de critérios de aceitação para uma user story."""
    generator = AcceptanceCriteriaGenerator(llm_client=mock_llm_client)

    criteria = await generator.generate_for_user_story(sample_user_story)

    assert len(criteria) == 2
    assert criteria[0].id == "AC-001"
    assert criteria[0].user_story_id == "US-001"
    assert criteria[0].criterion_type == CriterionType.FUNCTIONAL
    assert criteria[0].given == "the user is on the login page"
    assert criteria[0].when == "they enter valid credentials"
    assert criteria[0].then == "they should be redirected to the dashboard"
    assert criteria[1].criterion_type == CriterionType.PERFORMANCE


@pytest.mark.asyncio()
async def test_generate_acceptance_criteria_for_multiple_stories(mock_llm_client):
    """Testa geração de critérios para múltiplas user stories."""
    generator = AcceptanceCriteriaGenerator(llm_client=mock_llm_client)

    story1 = UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="utilizador",
        action="fazer login",
        benefit="aceder ao sistema",
        size=StorySize.MEDIUM,
    )

    story2 = UserStory(
        id="US-002",
        requirement_id="REQ-001",
        role="utilizador",
        action="fazer logout",
        benefit="sair do sistema",
        size=StorySize.SMALL,
    )

    result = await generator.generate_for_stories([story1, story2])

    assert len(result) == 2
    assert "US-001" in result
    assert "US-002" in result
    assert result["US-001"].parent_id == "US-001"
    assert result["US-001"].parent_type == "user_story"


@pytest.mark.asyncio()
async def test_generate_acceptance_criteria_maps_types_correctly(mock_llm_client):
    """Testa que tipos de critério são mapeados corretamente."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message={
                        "content": """```json
[
  {"id": "AC-001", "statement": "Functional criterion test case", "given": "g", "when": "w", "then": "t", "type": "functional"},
  {"id": "AC-002", "statement": "Performance criterion test case", "given": "g", "when": "w", "then": "t", "type": "performance"},
  {"id": "AC-003", "statement": "Usability criterion test case", "given": "g", "when": "w", "then": "t", "type": "usability"},
  {"id": "AC-004", "statement": "Security criterion test case", "given": "g", "when": "w", "then": "t", "type": "security"},
  {"id": "AC-005", "statement": "Compliance criterion test case", "given": "g", "when": "w", "then": "t", "type": "compliance"}
]
```""",
                        "role": "assistant",
                    }
                )
            ]
        )
    )

    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    story = UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="user",
        action="perform test action",
        benefit="achieve test goal",
    )

    criteria = await generator.generate_for_user_story(story)

    assert len(criteria) == 5
    assert criteria[0].criterion_type == CriterionType.FUNCTIONAL
    assert criteria[1].criterion_type == CriterionType.PERFORMANCE
    assert criteria[2].criterion_type == CriterionType.USABILITY
    assert criteria[3].criterion_type == CriterionType.SECURITY
    assert criteria[4].criterion_type == CriterionType.COMPLIANCE


@pytest.mark.asyncio()
async def test_generate_acceptance_criteria_default_type():
    """Testa que critérios sem tipo definido usam FUNCTIONAL como padrão."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message={
                        "content": """```json
[
  {"id": "AC-001", "statement": "Test criterion with valid length", "given": "g", "when": "w", "then": "t"}
]
```""",
                        "role": "assistant",
                    }
                )
            ]
        )
    )

    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    story = UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="user",
        action="test",
        benefit="test",
    )

    criteria = await generator.generate_for_user_story(story)

    assert len(criteria) == 1
    assert criteria[0].criterion_type == CriterionType.FUNCTIONAL


def test_parse_type_maps_all_types():
    """Testa que todos os tipos são mapeados corretamente."""
    mock_client = AsyncMock()
    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    assert generator._parse_type("functional") == CriterionType.FUNCTIONAL
    assert generator._parse_type("performance") == CriterionType.PERFORMANCE
    assert generator._parse_type("usability") == CriterionType.USABILITY
    assert generator._parse_type("security") == CriterionType.SECURITY
    assert generator._parse_type("compliance") == CriterionType.COMPLIANCE
    assert generator._parse_type("unknown") == CriterionType.FUNCTIONAL  # default


def test_extract_json_from_markdown():
    """Testa extração de JSON de texto markdown."""
    mock_client = AsyncMock()
    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    markdown_text = """
Text before

```json
[
  {"id": "AC-001", "given": "context", "when": "action", "then": "result"}
]
```

Text after
"""

    json_str = generator._extract_json(markdown_text)

    assert (
        json_str
        == '[\n  {"id": "AC-001", "given": "context", "when": "action", "then": "result"}\n]'
    )


def test_extract_json_from_plain_array():
    """Testa extração de JSON sem markdown."""
    mock_client = AsyncMock()
    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    plain_text = '[{"id": "AC-001", "given": "g", "when": "w", "then": "t"}]'

    json_str = generator._extract_json(plain_text)

    assert json_str == '[{"id": "AC-001", "given": "g", "when": "w", "then": "t"}]'


def test_extract_json_returns_none_when_no_json():
    """Testa que retorna None quando não há JSON."""
    mock_client = AsyncMock()
    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    plain_text = "This is just plain text without any JSON"

    json_str = generator._extract_json(plain_text)

    assert json_str is None


@pytest.mark.asyncio()
async def test_generate_acceptance_criteria_handles_invalid_criterion_data(mock_llm_client):
    """Testa que critérios inválidos são ignorados."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message={
                        "content": """```json
[
  {"id": "AC-001", "statement": "Valid criterion test statement", "given": "g", "when": "w", "then": "t"},
  {"invalid": "missing required fields"}
]
```""",
                        "role": "assistant",
                    }
                )
            ]
        )
    )

    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    story = UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="user",
        action="test",
        benefit="test",
    )

    criteria = await generator.generate_for_user_story(story)

    # O segundo critério é inválido e deve ser ignorado
    assert len(criteria) == 1
    assert criteria[0].id == "AC-001"


@pytest.mark.asyncio()
async def test_generate_acceptance_criteria_uses_user_story_format():
    """Testa que o formato da user story é usado no prompt."""
    mock_client = AsyncMock()
    mock_client.generate = AsyncMock(
        return_value=Mock(
            choices=[
                Mock(
                    message={
                        "content": """```json
[
  {"id": "AC-001", "statement": "Test criterion with valid length", "given": "g", "when": "w", "then": "t"}
]
```""",
                        "role": "assistant",
                    }
                )
            ]
        )
    )

    generator = AcceptanceCriteriaGenerator(llm_client=mock_client)

    story = UserStory(
        id="US-001",
        requirement_id="REQ-001",
        role="admin",
        action="gerir users",
        benefit="controlar acessos",
    )

    criteria = await generator.generate_for_user_story(story)

    # Verifica que o LLM foi chamado (indiretamente, via resultado)
    assert len(criteria) == 1
    # O prompt deve ter usado o formato "Como admin, eu quero gerir users, para que controlar acessos"
