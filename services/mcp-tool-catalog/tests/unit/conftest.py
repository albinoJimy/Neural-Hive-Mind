"""
Configuracao de fixtures pytest para testes unitarios do MCP Tool Catalog.

Importa fixtures do conftest.py principal e adiciona fixtures especificas
para testes unitarios.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# Importar fixtures do conftest.py principal
from tests.conftest import *  # noqa: F401, F403


# ============================================================================
# Fixtures Adicionais para Testes Unitarios
# ============================================================================


@pytest.fixture
def sample_tool_selection_request():
    """Requisicao de selecao de ferramentas sample."""
    from src.models.tool_selection import ToolSelectionRequest

    return ToolSelectionRequest(
        request_id=str(uuid.uuid4()),
        ticket_id=str(uuid.uuid4()),
        artifact_type='CODE',
        language='python',
        complexity_score=0.7,
        required_categories=['VALIDATION', 'GENERATION'],
        constraints={
            'max_execution_time_ms': 300000,
            'max_cost_score': 0.8,
            'min_reputation_score': 0.6
        },
        context={
            'framework': 'fastapi',
            'description': 'Microservice for user management'
        }
    )


@pytest.fixture
def sample_tool_selection_request_simple():
    """Requisicao de selecao simples."""
    from src.models.tool_selection import ToolSelectionRequest

    return ToolSelectionRequest(
        request_id=str(uuid.uuid4()),
        ticket_id=str(uuid.uuid4()),
        artifact_type='CODE',
        language='python',
        complexity_score=0.3,
        required_categories=['VALIDATION'],
        constraints={},
        context={}
    )


@pytest.fixture
def mock_redis_client():
    """Mock para Redis client."""
    client = AsyncMock()
    client.get_cached_selection = AsyncMock(return_value=None)
    client.cache_selection = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_mongodb_client_with_tools(cli_tool, rest_tool, container_tool):
    """Mock MongoDB client com ferramentas pre-carregadas."""
    client = AsyncMock()
    client.save_selection_history = AsyncMock(return_value=True)
    client.get_tool = AsyncMock(side_effect=lambda tool_id: {
        'pytest-001': cli_tool,
        'sonarqube-001': rest_tool,
        'trivy-001': container_tool
    }.get(tool_id))
    return client


@pytest.fixture
def mock_tool_registry_with_multiple_tools():
    """Mock ToolRegistry com multiplas ferramentas por categoria."""
    from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType

    # Criar ferramentas de VALIDATION
    validation_tools = [
        ToolDescriptor(
            tool_id=f'val-{i:03d}',
            tool_name=f'validator-{i}',
            category=ToolCategory.VALIDATION,
            version='1.0.0',
            capabilities=['testing'],
            reputation_score=0.7 + (i * 0.05),
            cost_score=0.1 * i,
            average_execution_time_ms=5000,
            integration_type=IntegrationType.CLI,
            authentication_method='NONE',
            output_format='json'
        )
        for i in range(5)
    ]

    # Criar ferramentas de GENERATION
    generation_tools = [
        ToolDescriptor(
            tool_id=f'gen-{i:03d}',
            tool_name=f'generator-{i}',
            category=ToolCategory.GENERATION,
            version='1.0.0',
            capabilities=['code-generation'],
            reputation_score=0.6 + (i * 0.08),
            cost_score=0.2 * i,
            average_execution_time_ms=10000,
            integration_type=IntegrationType.REST_API,
            authentication_method='BEARER',
            output_format='json'
        )
        for i in range(5)
    ]

    registry = AsyncMock()
    registry.list_tools_by_category = AsyncMock(side_effect=lambda cat: {
        ToolCategory.VALIDATION: validation_tools,
        ToolCategory.GENERATION: generation_tools
    }.get(cat, []))
    registry.redis_client = AsyncMock()
    registry.redis_client.get_cached_selection = AsyncMock(return_value=None)
    registry.redis_client.cache_selection = AsyncMock(return_value=True)
    registry.mongodb_client = AsyncMock()
    registry.mongodb_client.save_selection_history = AsyncMock(return_value=True)

    return registry


@pytest.fixture
def sample_tool_combination():
    """ToolCombination sample."""
    from src.models.tool_combination import ToolCombination
    from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType

    tools = [
        ToolDescriptor(
            tool_id='val-001',
            tool_name='validator-1',
            category=ToolCategory.VALIDATION,
            version='1.0.0',
            capabilities=['testing'],
            reputation_score=0.85,
            cost_score=0.1,
            average_execution_time_ms=5000,
            integration_type=IntegrationType.CLI,
            authentication_method='NONE',
            output_format='json'
        ),
        ToolDescriptor(
            tool_id='gen-001',
            tool_name='generator-1',
            category=ToolCategory.GENERATION,
            version='1.0.0',
            capabilities=['code-generation'],
            reputation_score=0.9,
            cost_score=0.2,
            average_execution_time_ms=10000,
            integration_type=IntegrationType.REST_API,
            authentication_method='BEARER',
            output_format='json'
        )
    ]

    return ToolCombination(tools=tools, generation=0)
