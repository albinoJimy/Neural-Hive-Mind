"""
Testes de integração entre PlaybookExecutor e CircuitBreaker.

Verifica que chamadas externas são protegidas pelo circuit breaker.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.services.playbook_executor import PlaybookExecutor
from src.services.circuit_breaker import CircuitBreakerState


class TestPlaybookExecutorCircuitBreaker:
    """Testes de integração PlaybookExecutor + CircuitBreaker."""

    @pytest.fixture
    def executor_with_circuit_breaker(self, mock_tracer):
        """Executor com circuit breaker habilitado."""
        with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
            return PlaybookExecutor(
                playbooks_dir="/tmp/fake_playbooks",
                k8s_in_cluster=False,
                circuit_breaker_enabled=True,
                circuit_breaker_failure_threshold=3,
            )

    @pytest.mark.asyncio
    async def test_reallocate_ticket_uses_circuit_breaker(
        self, executor_with_circuit_breaker, mock_execution_ticket_client
    ):
        """Testa que reallocate_ticket usa circuit breaker."""
        # Configurar executor com o mock client
        executor_with_circuit_breaker.execution_ticket_client = mock_execution_ticket_client

        # Configurar mock para falhar e abrir circuit breaker
        mock_execution_ticket_client.reallocate_ticket = AsyncMock(
            side_effect=Exception("Service unavailable")
        )

        context = {"ticket_id": "ticket-123", "reason": "timeout_recovery", "incident_id": "inc-1"}

        # Fazer 3 chamadas para abrir o circuit breaker
        for i in range(3):
            result = await executor_with_circuit_breaker._reallocate_ticket(
                action={"ticket_id": "ticket-123"}, context=context
            )
            # Com o client disponível, deve tentar e falhar
            assert result["success"] is False

        # Verificar que circuit breaker está OPEN
        ets_breaker = executor_with_circuit_breaker._circuit_breakers.get(
            "execution_ticket_service"
        )
        assert ets_breaker.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_reallocate_ticket_blocked_when_circuit_open(self, executor_with_circuit_breaker):
        """Testa que chamadas são bloqueadas quando circuit breaker está OPEN."""
        # Configurar executor com client mock
        mock_client = AsyncMock()
        mock_client.reallocate_ticket = AsyncMock(
            return_value={"success": True, "reallocation_id": "realloc-1"}
        )
        executor_with_circuit_breaker.execution_ticket_client = mock_client

        # Abrir manualmente o circuit breaker
        ets_breaker = executor_with_circuit_breaker._circuit_breakers.get(
            "execution_ticket_service"
        )
        for _ in range(3):
            try:
                ets_breaker.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass

        assert ets_breaker.state == CircuitBreakerState.OPEN

        # Tentar realocar ticket - deve retornar circuit_breaker_open
        context = {"ticket_id": "ticket-123", "reason": "timeout_recovery"}

        result = await executor_with_circuit_breaker._reallocate_ticket(
            action={"ticket_id": "ticket-123"}, context=context
        )

        assert result["success"] is False
        assert result.get("circuit_breaker_open") is True
        assert "Circuit breaker is OPEN" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_orchestrator_calls_use_circuit_breaker(
        self, executor_with_circuit_breaker, mock_orchestrator_client
    ):
        """Testa que chamadas ao orchestrator usam circuit breaker."""
        # Configurar executor com o mock client
        executor_with_circuit_breaker.orchestrator_client = mock_orchestrator_client

        mock_orchestrator_client.get_workflow_status = AsyncMock(return_value={"state": "PAUSED"})
        mock_orchestrator_client.resume_workflow = AsyncMock(
            side_effect=Exception("Orchestrator unavailable")
        )

        # Fazer chamadas suficientes para abrir circuit breaker
        orchestrator_breaker = executor_with_circuit_breaker._circuit_breakers.get("orchestrator")

        for _ in range(3):
            try:
                result = await executor_with_circuit_breaker._restart_workflow(
                    action={"workflow_id": "wf-123"}, context={}
                )
            except Exception:
                pass

        # Verificar estado do circuit breaker
        assert orchestrator_breaker.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_pause_workflow_blocked_when_circuit_open(
        self, executor_with_circuit_breaker, mock_orchestrator_client
    ):
        """Testa que pause_workflow respeita circuit breaker OPEN."""
        # Configurar executor com o mock client
        executor_with_circuit_breaker.orchestrator_client = mock_orchestrator_client

        mock_orchestrator_client.pause_workflow = AsyncMock(return_value={"success": True})

        # Abrir circuit breaker manualmente
        orchestrator_breaker = executor_with_circuit_breaker._circuit_breakers.get("orchestrator")
        for _ in range(3):
            try:
                orchestrator_breaker.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass

        # Tentar pausar workflow - deve retornar circuit_breaker_open
        result = await executor_with_circuit_breaker._pause_workflow(
            action={"workflow_id": "wf-123", "duration_seconds": 300}, context={}
        )

        assert result["success"] is False
        assert result.get("circuit_breaker_open") is True

    @pytest.mark.asyncio
    async def test_restart_workflow_blocked_when_circuit_open(
        self, executor_with_circuit_breaker, mock_orchestrator_client
    ):
        """Testa que restart_workflow respeita circuit breaker OPEN."""
        # Configurar executor com o mock client
        executor_with_circuit_breaker.orchestrator_client = mock_orchestrator_client

        mock_orchestrator_client.get_workflow_status = AsyncMock(return_value={"state": "PAUSED"})
        mock_orchestrator_client.resume_workflow = AsyncMock(return_value={"success": True})

        # Abrir circuit breaker manualmente
        orchestrator_breaker = executor_with_circuit_breaker._circuit_breakers.get("orchestrator")
        for _ in range(3):
            try:
                orchestrator_breaker.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass

        # Tentar reiniciar workflow - deve retornar circuit_breaker_open
        result = await executor_with_circuit_breaker._restart_workflow(
            action={"workflow_id": "wf-123"}, context={}
        )

        assert result["success"] is False
        assert result.get("circuit_breaker_open") is True

    @pytest.mark.asyncio
    async def test_circuit_breaker_disabled_uses_direct_calls(
        self, mock_tracer, mock_execution_ticket_client
    ):
        """Testa que com circuit breaker disabled, chamadas são diretas."""
        with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
            executor = PlaybookExecutor(
                playbooks_dir="/tmp/fake_playbooks",
                k8s_in_cluster=False,
                circuit_breaker_enabled=False,  # Desabilitado
            )

        # Verificar que não há circuit breakers
        assert len(executor._circuit_breakers) == 0

        # Mock cliente
        mock_execution_ticket_client.reallocate_ticket = AsyncMock(
            return_value={"success": True, "reallocation_id": "realloc-1"}
        )
        executor.execution_ticket_client = mock_execution_ticket_client

        # Chamada deve funcionar normalmente
        result = await executor._reallocate_ticket(action={"ticket_id": "ticket-123"}, context={})

        assert result["success"] is True
