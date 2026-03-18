"""
Testes para QueenAgentIntegration.

TDD: Testes escritos antes da implementação.
Espec: GAPS-05 Scout Agents
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import Dict, Any

# Import com skip automático se módulo não disponível
QueenAgentIntegration = pytest.importorskip('src.integration.queen_agent_integration').QueenAgentIntegration


class TestQueenAgentIntegrationInitialization:
    """Testes de inicialização da integração."""

    def test_integration_initialization(self):
        """Testa que a integração é inicializada corretamente."""
        mock_channel = AsyncMock()
        mock_stub = AsyncMock()

        integration = QueenAgentIntegration(
            channel=mock_channel,
            stub=mock_stub,
            agent_id='scout-agent-1'
        )

        assert integration is not None
        assert integration.agent_id == 'scout-agent-1'

    def test_default_heartbeat_interval(self):
        """Testa intervalo padrão de heartbeat."""
        mock_channel = AsyncMock()
        mock_stub = AsyncMock()

        integration = QueenAgentIntegration(
            channel=mock_channel,
            stub=mock_stub
        )

        assert integration.heartbeat_interval_sec == 30


class TestAgentRegistration:
    """Testes de registro no Queen Agent."""

    @pytest.fixture
    def integration(self):
        mock_channel = AsyncMock()
        mock_stub = AsyncMock()
        mock_stub.RegisterAgent = AsyncMock(return_value=MagicMock(
            agent_id='registered-1',
            status='accepted'
        ))

        return QueenAgentIntegration(
            channel=mock_channel,
            stub=mock_stub,
            agent_id='scout-agent-1'
        )

    @pytest.mark.asyncio
    async def test_register_agent_success(self, integration):
        """Testa registro bem-sucedido."""
        result = await integration.register_agent()

        assert result['status'] == 'accepted'

    @pytest.mark.asyncio
    async def test_register_with_capabilities(self, integration):
        """Testa registro com capacidades declaradas."""
        integration.capabilities = [
            'codebase_exploration',
            'pattern_discovery',
            'solution_synthesis'
        ]

        result = await integration.register_agent()

        assert result['status'] == 'accepted'


class TestHeartbeat:
    """Testes de heartbeat para Queen Agent."""

    @pytest.fixture
    def integration(self):
        mock_channel = AsyncMock()
        mock_stub = AsyncMock()
        mock_stub.SendHeartbeat = AsyncMock(return_value=MagicMock(
            acknowledged=True
        ))

        integration = QueenAgentIntegration(
            channel=mock_channel,
            stub=mock_stub,
            agent_id='scout-agent-1'
        )
        return integration

    @pytest.mark.asyncio
    async def test_send_heartbeat(self, integration):
        """Testa envio de heartbeat."""
        result = await integration.send_heartbeat()

        assert result['acknowledged'] is True

    @pytest.mark.asyncio
    async def test_heartbeat_with_status(self, integration):
        """Testa heartbeat com status atual."""
        integration.current_status = {
            'active_explorations': 3,
            'total_processed': 42
        }

        result = await integration.send_heartbeat()

        assert result['acknowledged'] is True


class TestReportExplorationResults:
    """Testes de report de resultados para Queen Agent."""

    @pytest.fixture
    def integration(self):
        mock_channel = AsyncMock()
        mock_stub = AsyncMock()
        mock_stub.ReportExploration = AsyncMock(return_value=MagicMock(
            received=True,
            exploration_id='scout-exp-1'
        ))

        return QueenAgentIntegration(
            channel=mock_channel,
            stub=mock_stub,
            agent_id='scout-agent-1'
        )

    @pytest.mark.asyncio
    async def test_report_exploration_completed(self, integration):
        """Testa report de exploração completada."""
        results = {
            'exploration_id': 'scout-exp-1',
            'status': 'completed',
            'patterns_found': 5,
            'recommendations': []
        }

        result = await integration.report_exploration_results(results)

        assert result['received'] is True

    @pytest.mark.asyncio
    async def test_report_with_error(self, integration):
        """Testa report de erro na exploração."""
        error_report = {
            'exploration_id': 'scout-exp-2',
            'status': 'failed',
            'error': 'Timeout exceeded'
        }

        result = await integration.report_exploration_results(error_report)

        assert result['received'] is True


class TestHandleQueenCommands:
    """Testes de manipulação de comandos do Queen Agent."""

    @pytest.fixture
    def integration(self):
        mock_channel = AsyncMock()
        mock_stub = AsyncMock()

        integration = QueenAgentIntegration(
            channel=mock_channel,
            stub=mock_stub,
            agent_id='scout-agent-1'
        )
        return integration

    def test_register_command_handler(self, integration):
        """Testa registro de handler de comando."""
        async def dummy_handler(command):
            return {'handled': True}

        integration.register_command_handler('explore', dummy_handler)

        assert 'explore' in integration.command_handlers

    @pytest.mark.asyncio
    async def test_execute_registered_command(self, integration):
        """Testa execução de comando registrado."""
        async def dummy_handler(command):
            return {'handled': True, 'command': command}

        integration.register_command_handler('explore', dummy_handler)

        result = await integration.handle_command({
            'command': 'explore',
            'params': {'target': '/code'}
        })

        assert result['handled'] is True


class TestAgentStatusReporting:
    """Testes de report de status do agente."""

    @pytest.fixture
    def integration(self):
        mock_channel = AsyncMock()
        mock_stub = AsyncMock()
        mock_stub.ReportStatus = AsyncMock(return_value=MagicMock(
            received=True
        ))

        return QueenAgentIntegration(
            channel=mock_channel,
            stub=mock_stub,
            agent_id='scout-agent-1'
        )

    @pytest.mark.asyncio
    async def test_report_status_to_queen(self, integration):
        """Testa report de status para Queen Agent."""
        status = {
            'agent_id': 'scout-agent-1',
            'status': 'ready',
            'uptime_sec': 3600
        }

        result = await integration.report_status(status)

        assert result['received'] is True
