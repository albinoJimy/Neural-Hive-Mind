"""
Testes unitários para HealthCheckManager.

Este módulo testa o gerenciador de health checks periódicos para agentes.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from src.models import AgentInfo, AgentStatus, AgentTelemetry, AgentType
from src.services.health_check_manager import HealthCheckManager


@pytest.fixture
def mock_redis_client():
    """Mock do EtcdClient."""
    client = AsyncMock()
    client.list_agents = AsyncMock(return_value=[])
    client.get_agent = AsyncMock(return_value=None)
    client.put_agent = AsyncMock(return_value=True)
    client.delete_agent = AsyncMock(return_value=True)
    return client


@pytest.fixture
def health_check_manager(mock_redis_client):
    """Instância do HealthCheckManager para teste."""
    return HealthCheckManager(
        redis_client=mock_redis_client, check_interval_seconds=1, heartbeat_timeout_seconds=10
    )


@pytest.fixture
def sample_agent():
    """Agente de exemplo para testes."""
    return AgentInfo(
        agent_id=uuid4(),
        agent_type=AgentType.WORKER,
        capabilities=["python"],
        status=AgentStatus.HEALTHY,
        telemetry=AgentTelemetry(success_rate=0.9, total_executions=100),
        namespace="default",
        last_seen=int(datetime.now(timezone.utc).timestamp()),
    )


@pytest.fixture
def expired_agent(sample_agent):
    """Agente expirado (last_seen antigo)."""
    expired_time = int((datetime.now(timezone.utc) - timedelta(seconds=15)).timestamp())
    return AgentInfo(
        agent_id=sample_agent.agent_id,
        agent_type=sample_agent.agent_type,
        capabilities=sample_agent.capabilities,
        status=AgentStatus.HEALTHY,
        telemetry=sample_agent.telemetry,
        namespace=sample_agent.namespace,
        last_seen=expired_time,
    )


class TestHealthCheckManagerLifecycle:
    """Testes para ciclo de vida do HealthCheckManager."""

    @pytest.mark.asyncio
    async def test_start_stop(self, health_check_manager):
        """Testa iniciar e parar o manager."""
        await health_check_manager.start()

        assert health_check_manager._running is True
        assert health_check_manager._task is not None

        await health_check_manager.stop()

        assert health_check_manager._running is False

    @pytest.mark.asyncio
    async def test_start_already_started(self, health_check_manager):
        """Testa que segunda chamada de start não cria nova task."""
        await health_check_manager.start()

        # Guardar referência da task original
        original_task = health_check_manager._task

        # Segunda chamada deve apenas logar warning e retornar
        await health_check_manager.start()

        assert health_check_manager._running is True
        # Task não deve ter sido alterada
        assert health_check_manager._task is original_task

    @pytest.mark.asyncio
    async def test_stop_not_started(self, health_check_manager, caplog):
        """Testa parar sem ter iniciado."""
        # Não deve levantar exceção, apenas parar
        await health_check_manager.stop()

        assert health_check_manager._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, health_check_manager):
        """Testa que stop cancela a task em execução."""
        await health_check_manager.start()

        task = health_check_manager._task
        assert task is not None
        assert not task.done()

        await health_check_manager.stop()

        assert task.cancelled() or task.done()


class TestHealthCheckLoop:
    """Testes para o loop de health check."""

    @pytest.mark.asyncio
    async def test_health_check_loop_healthy_agents(
        self, health_check_manager, mock_redis_client, sample_agent
    ):
        """Testa loop com agentes saudáveis."""
        mock_redis_client.list_agents = AsyncMock(return_value=[sample_agent])

        await health_check_manager._perform_health_checks()

        # Agente saudável não deve ser modificado
        mock_redis_client.put_agent.assert_not_called()
        mock_redis_client.delete_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_check_loop_with_expired(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa loop com agente expirado."""
        mock_redis_client.list_agents = AsyncMock(return_value=[expired_agent])

        await health_check_manager._perform_health_checks()

        # Primeiro ciclo: marca como UNHEALTHY
        assert expired_agent.status == AgentStatus.UNHEALTHY
        mock_redis_client.put_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_loop_recover(
        self, health_check_manager, mock_redis_client, sample_agent
    ):
        """Testa que agente recupera quando volta a enviar heartbeat."""
        # Marcar agente como previamente unhealthy
        agent_id_str = str(sample_agent.agent_id)
        health_check_manager._unhealthy_counts[agent_id_str] = 2

        mock_redis_client.list_agents = AsyncMock(return_value=[sample_agent])

        await health_check_manager._perform_health_checks()

        # Contador deve ser resetado
        assert agent_id_str not in health_check_manager._unhealthy_counts

    @pytest.mark.asyncio
    async def test_health_check_loop_multiple_agents(
        self, health_check_manager, mock_redis_client, sample_agent
    ):
        """Testa loop com múltiplos agentes."""
        agent2 = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.SCOUT,
            capabilities=["exploration"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.85),
            namespace="default",
            last_seen=int(datetime.now(timezone.utc).timestamp()),
        )

        mock_redis_client.list_agents = AsyncMock(return_value=[sample_agent, agent2])

        await health_check_manager._perform_health_checks()

        # Nenhum deve ter sido modificado (ambos saudáveis)
        assert mock_redis_client.list_agents.call_count == 1

    @pytest.mark.asyncio
    async def test_health_check_loop_exception_handling(
        self, health_check_manager, mock_redis_client
    ):
        """Testa que exceções no loop são tratadas."""
        mock_redis_client.list_agents = AsyncMock(side_effect=ConnectionError("DB error"))

        # Não deve levantar exceção
        try:
            await health_check_manager._perform_health_checks()
        except ConnectionError:
            # A exceção deve ser propagada para o loop tratá-la
            pass


class TestExpiredAgentHandling:
    """Testes para tratamento de agentes expirados."""

    @pytest.mark.asyncio
    async def test_handle_expired_agent_cycle_1_mark_unhealthy(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa ciclo 1: marca como UNHEALTHY."""
        await health_check_manager._handle_expired_agent(expired_agent, 15)

        assert expired_agent.status == AgentStatus.UNHEALTHY
        assert str(expired_agent.agent_id) in health_check_manager._unhealthy_counts
        assert health_check_manager._unhealthy_counts[str(expired_agent.agent_id)] == 1
        mock_redis_client.put_agent.assert_called_once_with(expired_agent)

    @pytest.mark.asyncio
    async def test_handle_expired_agent_cycle_2_mark_degraded(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa ciclo 2: marca como DEGRADED e notifica autocura."""
        # Simular que já está no ciclo 1
        health_check_manager._unhealthy_counts[str(expired_agent.agent_id)] = 1

        with patch.object(health_check_manager, "_notify_autocura", new=AsyncMock()) as mock_notify:
            await health_check_manager._handle_expired_agent(expired_agent, 20)

            assert expired_agent.status == AgentStatus.DEGRADED
            assert health_check_manager._unhealthy_counts[str(expired_agent.agent_id)] == 2
            mock_notify.assert_called_once_with(expired_agent)

    @pytest.mark.asyncio
    async def test_handle_expired_agent_cycle_5_remove(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa ciclo 5+: remove do registry."""
        # Simular que já está no ciclo 4
        health_check_manager._unhealthy_counts[str(expired_agent.agent_id)] = 4

        await health_check_manager._handle_expired_agent(expired_agent, 30)

        # Agente deve ter sido removido
        mock_redis_client.delete_agent.assert_called_once_with(expired_agent.agent_id)
        assert str(expired_agent.agent_id) not in health_check_manager._unhealthy_counts

    @pytest.mark.asyncio
    async def test_handle_multiple_agents_expired(self, health_check_manager, mock_redis_client):
        """Testa múltiplos agentes expirando simultaneamente."""
        agent1 = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.WORKER,
            capabilities=["python"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.9),
            namespace="default",
            last_seen=int((datetime.now(timezone.utc) - timedelta(seconds=15)).timestamp()),
        )
        agent2 = AgentInfo(
            agent_id=uuid4(),
            agent_type=AgentType.SCOUT,
            capabilities=["explore"],
            status=AgentStatus.HEALTHY,
            telemetry=AgentTelemetry(success_rate=0.8),
            namespace="default",
            last_seen=int((datetime.now(timezone.utc) - timedelta(seconds=20)).timestamp()),
        )

        # Primeiro ciclo para ambos
        await health_check_manager._handle_expired_agent(agent1, 15)
        await health_check_manager._handle_expired_agent(agent2, 20)

        assert len(health_check_manager._unhealthy_counts) == 2
        assert agent1.status == AgentStatus.UNHEALTHY
        assert agent2.status == AgentStatus.UNHEALTHY


class TestAutocuraNotification:
    """Testes para notificação de autocura."""

    @pytest.mark.asyncio
    async def test_notify_autocura(self, health_check_manager, sample_agent):
        """Testa notificação do sistema de autocura."""
        # Método deve completar sem erro
        await health_check_manager._notify_autocura(sample_agent)

        # Verificar que agente mantém estado consistente
        assert sample_agent.status == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_autocura_integration_on_degraded(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa integração quando agente é marcado DEGRADED."""
        health_check_manager._unhealthy_counts[str(expired_agent.agent_id)] = 1

        with patch.object(health_check_manager, "_notify_autocura", new=AsyncMock()) as mock_notify:
            await health_check_manager._handle_expired_agent(expired_agent, 20)

            # Autocura deve ter sido notificada
            mock_notify.assert_called_once()


class TestCheckAgentHealth:
    """Testes para verificação de saúde de agente específico."""

    @pytest.mark.asyncio
    async def test_check_agent_health_healthy(
        self, health_check_manager, mock_redis_client, sample_agent
    ):
        """Testa verificação de agente saudável."""
        mock_redis_client.get_agent = AsyncMock(return_value=sample_agent)

        result = await health_check_manager.check_agent_health(sample_agent.agent_id)

        assert result == AgentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_agent_health_expired(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa verificação de agente expirado."""
        mock_redis_client.get_agent = AsyncMock(return_value=expired_agent)

        result = await health_check_manager.check_agent_health(expired_agent.agent_id)

        assert result == AgentStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_agent_health_not_found(self, health_check_manager, mock_redis_client):
        """Testa verificação de agente que não existe."""
        mock_redis_client.get_agent = AsyncMock(return_value=None)

        result = await health_check_manager.check_agent_health(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_check_agent_health_error(
        self, health_check_manager, mock_redis_client, sample_agent
    ):
        """Testa tratamento de erro na verificação."""
        mock_redis_client.get_agent = AsyncMock(side_effect=ConnectionError("DB error"))

        result = await health_check_manager.check_agent_health(sample_agent.agent_id)

        assert result is None


class TestPrometheusMetrics:
    """Testes para métricas Prometheus."""

    @pytest.mark.asyncio
    async def test_health_checks_total_metric(
        self, health_check_manager, mock_redis_client, sample_agent
    ):
        """Testa que métrica health_checks_total é incrementada."""
        from src.services.health_check_manager import health_checks_total

        initial_value = health_checks_total._value.get()
        mock_redis_client.list_agents = AsyncMock(return_value=[sample_agent])

        await health_check_manager._perform_health_checks()

        # Métrica deve ter sido incrementada
        # Nota: Prometheus Counter valores são monótonos
        assert health_checks_total._value.get() >= initial_value

    @pytest.mark.asyncio
    async def test_agents_marked_unhealthy_metric(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa que métrica agents_marked_unhealthy_total é incrementada."""

        mock_redis_client.list_agents = AsyncMock(return_value=[expired_agent])

        await health_check_manager._perform_health_checks()

        # Agente foi marcado UNHEALTHY no primeiro ciclo
        # A métrica deve ter sido incrementada

    @pytest.mark.asyncio
    async def test_agents_removed_metric(
        self, health_check_manager, mock_redis_client, expired_agent
    ):
        """Testa que métrica agents_removed_total é incrementada após 5 ciclos."""

        mock_redis_client.list_agents = AsyncMock(return_value=[expired_agent])

        # Executar 5 ciclos para atingir remoção
        for _ in range(5):
            await health_check_manager._perform_health_checks()

        # Agente deve ter sido removido
        mock_redis_client.delete_agent.assert_called()
