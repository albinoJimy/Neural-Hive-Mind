"""Testes unitários para métodos RAG do CodeComposer"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.code_composer import CodeComposer


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDBClient"""
    client = AsyncMock()
    client.save_artifact_content = AsyncMock()
    return client


@pytest.fixture
def mock_llm_client():
    """Mock do LLMClient"""
    client = AsyncMock()
    client.generate_code = AsyncMock(return_value={
        'code': 'print("Hello World")',
        'confidence_score': 0.85
    })
    return client


@pytest.fixture
def mock_analyst_client():
    """Mock do AnalystAgentsClient"""
    client = AsyncMock()
    client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
    client.find_similar_templates = AsyncMock(return_value=[
        {'text': 'FastAPI microservice template', 'similarity': 0.9},
        {'text': 'Python REST API template', 'similarity': 0.85}
    ])
    client.get_architectural_patterns = AsyncMock(return_value=[
        'microservices', 'event-driven', 'REST API'
    ])
    return client


@pytest.fixture
def sample_ticket():
    """Criar ticket de exemplo"""
    ticket = MagicMock()
    ticket.ticket_id = 'test-ticket-123'
    ticket.parameters = {
        'description': 'Create a Python microservice',
        'language': 'python',
        'artifact_type': 'MICROSERVICE',
        'domain': 'TECHNICAL',
        'service_name': 'test-service',
        'requirements': ['REST API', 'PostgreSQL']
    }
    return ticket


@pytest.mark.asyncio
async def test_build_rag_context_success(mock_mongodb_client, mock_analyst_client, sample_ticket):
    """Testar construção de contexto RAG bem-sucedida"""
    composer = CodeComposer(
        mongodb_client=mock_mongodb_client,
        llm_client=None,
        analyst_client=mock_analyst_client
    )

    rag_context = await composer._build_rag_context(sample_ticket)

    assert 'similar_templates' in rag_context
    assert 'architectural_patterns' in rag_context
    assert len(rag_context['similar_templates']) == 2
    assert len(rag_context['architectural_patterns']) == 3

    mock_analyst_client.find_similar_templates.assert_called_once()
    mock_analyst_client.get_architectural_patterns.assert_called_once_with('TECHNICAL')


@pytest.mark.asyncio
async def test_build_rag_context_no_analyst_client(mock_mongodb_client, sample_ticket):
    """Testar construção de contexto RAG sem analyst_client"""
    composer = CodeComposer(
        mongodb_client=mock_mongodb_client,
        llm_client=None,
        analyst_client=None
    )

    rag_context = await composer._build_rag_context(sample_ticket)

    assert rag_context == {'similar_templates': [], 'architectural_patterns': []}


@pytest.mark.asyncio
async def test_build_rag_context_analyst_failure(mock_mongodb_client, sample_ticket):
    """Testar construção de contexto RAG com falha no analyst"""
    mock_analyst_client = AsyncMock()
    mock_analyst_client.find_similar_templates.side_effect = Exception('Connection failed')

    composer = CodeComposer(
        mongodb_client=mock_mongodb_client,
        llm_client=None,
        analyst_client=mock_analyst_client
    )

    rag_context = await composer._build_rag_context(sample_ticket)

    # Deve retornar contexto vazio em caso de falha
    assert rag_context == {'similar_templates': [], 'architectural_patterns': []}


def test_build_llm_prompt(mock_mongodb_client, sample_ticket):
    """Testar construção de prompt LLM"""
    composer = CodeComposer(
        mongodb_client=mock_mongodb_client,
        llm_client=None,
        analyst_client=None
    )

    rag_context = {
        'similar_templates': [
            {'text': 'FastAPI template', 'similarity': 0.9}
        ],
        'architectural_patterns': ['microservices', 'REST API']
    }

    prompt = composer._build_llm_prompt(sample_ticket, rag_context)

    assert 'Python' in prompt
    assert 'microservice' in prompt or 'MICROSERVICE' in prompt
    assert 'FastAPI template' in prompt
    assert 'microservices' in prompt
    assert 'REST API' in prompt


def test_generate_heuristic_microservice(mock_mongodb_client, sample_ticket):
    """Testar geração heurística de microservice"""
    composer = CodeComposer(
        mongodb_client=mock_mongodb_client,
        llm_client=None,
        analyst_client=None
    )

    code = composer._generate_heuristic(sample_ticket.parameters)

    assert 'fastapi' in code.lower() or 'FastAPI' in code
    assert 'def' in code or 'async def' in code
    assert len(code) > 100  # Código não trivial


def test_generate_heuristic_library(mock_mongodb_client):
    """Testar geração heurística de library"""
    composer = CodeComposer(
        mongodb_client=mock_mongodb_client,
        llm_client=None,
        analyst_client=None
    )

    parameters = {
        'artifact_type': 'LIBRARY',
        'language': 'python',
        'service_name': 'my-lib'
    }

    code = composer._generate_heuristic(parameters)

    assert 'class' in code
    assert len(code) > 50


def test_generate_heuristic_script(mock_mongodb_client):
    """Testar geração heurística de script"""
    composer = CodeComposer(
        mongodb_client=mock_mongodb_client,
        llm_client=None,
        analyst_client=None
    )

    parameters = {
        'artifact_type': 'SCRIPT',
        'language': 'python',
        'service_name': 'my-script'
    }

    code = composer._generate_heuristic(parameters)

    assert '#!/usr/bin/env python3' in code
    assert 'def main()' in code
    assert len(code) > 50
