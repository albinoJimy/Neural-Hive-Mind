"""Testes unitários para AnalystAgentsClient"""
import pytest
from unittest.mock import AsyncMock, patch
import httpx
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.analyst_agents_client import AnalystAgentsClient


@pytest.fixture
def mock_httpx_client():
    """Mock do httpx.AsyncClient"""
    client = AsyncMock()
    client.post = AsyncMock()
    client.get = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_initialize_success(mock_httpx_client):
    """Testar inicialização bem-sucedida do cliente"""
    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        client = AnalystAgentsClient(host='localhost', port=8000)
        await client.start()

        assert client.client is not None


@pytest.mark.asyncio
async def test_get_embedding_success(mock_httpx_client):
    """Testar geração de embedding bem-sucedida"""
    # Mock response
    mock_response = AsyncMock()
    mock_response.json.return_value = {'embedding': [0.1, 0.2, 0.3]}
    mock_response.raise_for_status = AsyncMock()
    mock_httpx_client.post.return_value = mock_response

    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        client = AnalystAgentsClient(host='localhost', port=8000)
        await client.start()

        embedding = await client.get_embedding('test text')

        assert embedding == [0.1, 0.2, 0.3]
        mock_httpx_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_embedding_failure(mock_httpx_client):
    """Testar falha na geração de embedding"""
    mock_httpx_client.post.side_effect = httpx.HTTPError('Connection failed')

    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        client = AnalystAgentsClient(host='localhost', port=8000)
        await client.start()

        embedding = await client.get_embedding('test text')

        assert embedding is None


@pytest.mark.asyncio
async def test_find_similar_templates_success(mock_httpx_client):
    """Testar busca de templates similares bem-sucedida"""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        'results': [
            {'text': 'template1', 'similarity': 0.9},
            {'text': 'template2', 'similarity': 0.8}
        ]
    }
    mock_response.raise_for_status = AsyncMock()
    mock_httpx_client.post.return_value = mock_response

    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        client = AnalystAgentsClient(host='localhost', port=8000)
        await client.start()

        templates = await client.find_similar_templates('python microservice', top_k=5)

        assert len(templates) == 2
        assert templates[0]['similarity'] == 0.9


@pytest.mark.asyncio
async def test_get_architectural_patterns_success(mock_httpx_client):
    """Testar busca de padrões arquiteturais bem-sucedida"""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        'patterns': ['microservices', 'event-driven', 'CQRS']
    }
    mock_response.raise_for_status = AsyncMock()
    mock_httpx_client.get.return_value = mock_response

    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        client = AnalystAgentsClient(host='localhost', port=8000)
        await client.start()

        patterns = await client.get_architectural_patterns('TECHNICAL')

        assert len(patterns) == 3
        assert 'microservices' in patterns


@pytest.mark.asyncio
async def test_close_connection(mock_httpx_client):
    """Testar fechamento da conexão"""
    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        client = AnalystAgentsClient(host='localhost', port=8000)
        await client.start()
        await client.stop()

        mock_httpx_client.aclose.assert_called_once()
