"""
Testes unitários para ExecutionTicketClient - validação de cache e expiração de tokens.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from clients.execution_ticket_client import ExecutionTicketClient  # noqa: E402


@pytest.fixture
def config():
    """Configuração básica para testes."""
    return SimpleNamespace(
        execution_ticket_service_url='http://localhost:8080',
        ticket_api_timeout_seconds=30,
        service_version='1.0.0',
    )


@pytest.fixture
def mock_metrics():
    """Métricas mock para validação de chamadas."""
    metrics = MagicMock()
    metrics.ticket_tokens_obtained_total = MagicMock()
    metrics.ticket_tokens_obtained_total.inc = MagicMock()
    return metrics


def create_jwt_token(exp_offset_seconds: int) -> str:
    """Cria token JWT com expiração relativa ao tempo atual."""
    exp = int(time.time()) + exp_offset_seconds
    payload = {'sub': 'test-ticket', 'exp': exp, 'iat': int(time.time())}
    return jwt.encode(payload, 'secret', algorithm='HS256')


class TestIsTokenExpired:
    """Testes para o método _is_token_expired."""

    def test_valid_token_not_expired(self, config):
        """Token válido com expiração futura não deve ser considerado expirado."""
        client = ExecutionTicketClient(config)
        token = create_jwt_token(3600)  # Expira em 1 hora
        assert client._is_token_expired(token) is False

    def test_expired_token(self, config):
        """Token expirado deve ser detectado."""
        client = ExecutionTicketClient(config)
        token = create_jwt_token(-60)  # Expirou há 1 minuto
        assert client._is_token_expired(token) is True

    def test_token_about_to_expire(self, config):
        """Token que expira em menos de 30 segundos deve ser considerado expirado."""
        client = ExecutionTicketClient(config)
        token = create_jwt_token(20)  # Expira em 20 segundos (< margem de 30s)
        assert client._is_token_expired(token) is True

    def test_malformed_token(self, config):
        """Token malformado deve ser considerado expirado."""
        client = ExecutionTicketClient(config)
        assert client._is_token_expired('invalid-token') is True

    def test_token_without_exp_claim(self, config):
        """Token sem claim 'exp' deve ser considerado expirado."""
        client = ExecutionTicketClient(config)
        payload = {'sub': 'test-ticket', 'iat': int(time.time())}
        token = jwt.encode(payload, 'secret', algorithm='HS256')
        assert client._is_token_expired(token) is True


class TestGetTicketToken:
    """Testes para o método get_ticket_token."""

    @pytest.mark.asyncio
    async def test_returns_cached_valid_token(self, config, mock_metrics):
        """Deve retornar token do cache se válido."""
        client = ExecutionTicketClient(config, metrics=mock_metrics)
        client.client = MagicMock()

        valid_token = create_jwt_token(3600)
        client._token_cache['ticket-123'] = {'access_token': valid_token}

        result = await client.get_ticket_token('ticket-123')

        assert result == valid_token
        client.client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_new_token_when_cache_empty(self, config, mock_metrics):
        """Deve buscar novo token quando cache está vazio."""
        client = ExecutionTicketClient(config, metrics=mock_metrics)

        new_token = create_jwt_token(3600)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'access_token': new_token}
        mock_response.raise_for_status = MagicMock()

        client.client = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_ticket_token('ticket-456')

        assert result == new_token
        assert 'ticket-456' in client._token_cache
        mock_metrics.ticket_tokens_obtained_total.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetches_new_token_when_cached_expired(self, config, mock_metrics):
        """Deve buscar novo token quando token no cache está expirado."""
        client = ExecutionTicketClient(config, metrics=mock_metrics)

        expired_token = create_jwt_token(-60)
        new_token = create_jwt_token(3600)

        client._token_cache['ticket-789'] = {'access_token': expired_token}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'access_token': new_token}
        mock_response.raise_for_status = MagicMock()

        client.client = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_ticket_token('ticket-789')

        assert result == new_token
        assert client._token_cache['ticket-789']['access_token'] == new_token

    @pytest.mark.asyncio
    async def test_fetches_new_token_when_cached_malformed(self, config, mock_metrics):
        """Deve buscar novo token quando token no cache está malformado."""
        client = ExecutionTicketClient(config, metrics=mock_metrics)

        new_token = create_jwt_token(3600)
        client._token_cache['ticket-abc'] = {'access_token': 'malformed-token'}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'access_token': new_token}
        mock_response.raise_for_status = MagicMock()

        client.client = MagicMock()
        client.client.get = AsyncMock(return_value=mock_response)

        result = await client.get_ticket_token('ticket-abc')

        assert result == new_token
