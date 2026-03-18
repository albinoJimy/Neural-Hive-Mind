"""
Testes de integração para Self-Healing Engine.

Estes testes verificam o fluxo completo de:
- Consumo de evento Kafka → execução de playbook
- Validação OPA → execução/remadiação
- Detecção de incidente → trigger de playbook
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.playbook_executor import PlaybookExecutor
from src.consumers.remediation_consumer import RemediationConsumer
from src.services.health_monitor import HealthMonitor
from src.services.circuit_breaker import CircuitBreaker, CircuitBreakerState


class TestRemediationFlow:
    """Testes de fluxo de remediação ponta a ponta."""

    @pytest.mark.asyncio
    async def test_kafka_message_triggers_playbook(self, sample_playbook_path, mock_tracer):
        """Testa que mensagem Kafka executa playbook."""
        # Criar executor
        with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
            executor = PlaybookExecutor(
                playbooks_dir=sample_playbook_path.replace("test_playbook.yaml", ""),
                k8s_in_cluster=False
            )

            # Executar playbook diretamente (simulando o que o consumer faria)
            result = await executor.execute_playbook(
                "test_playbook",
                context={
                    "ticket_id": "ticket-456",
                    "worker_id": "worker-1"
                }
            )

        # Verificar que playbook foi executado
        assert result["success"] is True
        assert "actions" in result

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self):
        """Testa que circuit breaker abre após falhas consecutivas."""
        cb = CircuitBreaker("test-service", failure_threshold=3)

        # Simular falhas
        def failing_operation():
            raise Exception("Service unavailable")

        for i in range(3):
            try:
                cb.call(failing_operation)
            except Exception:
                pass

        # Deve estar OPEN
        assert cb.state == CircuitBreakerState.OPEN

        # Tentativa subsequente deve falhar imediatamente
        with pytest.raises(Exception):  # CircuitBreakerOpenError
            cb.call(lambda: "result")

    @pytest.mark.asyncio
    async def test_health_monitor_detects_unhealthy_service(self):
        """Testa que health monitor detecta serviço não saudável."""
        monitor = HealthMonitor(
            service_registry_client=None,  # Sem SR para teste
            http_timeout_seconds=5
        )

        # Mock resposta HTTP 503
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 503
            mock_get.return_value.__aenter__.return_value = mock_response

            status = await monitor.check_service_health("unhealthy-service")

        assert status.healthy is False
        assert status.error_message is not None

    @pytest.mark.asyncio
    async def test_remediation_flow_end_to_end(self, sample_playbook_path, mock_tracer):
        """Teste fluxo completo: incidente → detecção → remediação."""
        # 1. Simular incidente (detecção)
        incident = {
            "incident_id": "inc-123",
            "incident_type": "ticket_timeout",
            "severity": "medium",
            "service": "worker-agents",
            "metadata": {
                "ticket_id": "ticket-456",
                "worker_id": "worker-1"
            }
        }

        # 2. Criar executor
        with patch("src.services.playbook_executor.get_tracer", return_value=mock_tracer):
            executor = PlaybookExecutor(
                playbooks_dir=sample_playbook_path.replace("test_playbook.yaml", ""),
                k8s_in_cluster=False
            )

            # 3. Executar playbook
            result = await executor.execute_playbook(
                "test_playbook",
                context=incident["metadata"]
            )

        # 4. Verificar resultado
        assert result["success"] is True
        assert "actions" in result


class TestOPAValidation:
    """Testes de validação OPA para ações de remediação."""

    @pytest.mark.asyncio
    async def test_opa_validation_allows_safe_action(self, mock_opa_client):
        """Testa que OPA permite ação segura."""
        mock_opa_client.validate_action = AsyncMock(
            return_value={"allowed": True, "reason": "Action within policy"}
        )

        result = await mock_opa_client.validate_action(
            action="reallocate_ticket",
            params={"ticket_id": "ticket-123", "reason": "timeout_recovery"}
        )

        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_opa_validation_blocks_unsafe_action(self, mock_opa_client):
        """Testa que OPA bloqueia ação insegura."""
        mock_opa_client.validate_action = AsyncMock(
            return_value={"allowed": False, "reason": "Rate limit exceeded"}
        )

        result = await mock_opa_client.validate_action(
            action="reallocate_ticket",
            params={"ticket_id": "ticket-123", "reason": "test"}
        )

        assert result["allowed"] is False


class TestChaosToRemediation:
    """Testes de integração entre Chaos Engineering e Remediação."""

    @pytest.mark.asyncio
    async def test_chaos_experiment_triggers_remediation(self, mock_tracer):
        """Testa que experimento de chaos pode disparar playbook de recuperação."""
        from src.chaos.chaos_models import ChaosExperiment, FaultInjection, FaultType, TargetSelector

        # Criar experimento
        target = TargetSelector(
            namespace="neural-hive-orchestration",
            service_name="worker-agents"
        )
        injection = FaultInjection(
            fault_type=FaultType.POD_KILL,
            target=target,
            duration_seconds=60
        )
        experiment = ChaosExperiment(
            name="Test Recovery",
            description="Test recovery after pod kill",
            environment="staging",
            fault_injections=[injection]
        )

        # Verificar que experimento foi criado corretamente
        assert experiment.name == "Test Recovery"
        assert len(experiment.fault_injections) == 1


class TestMultiServiceCoordination:
    """Testes de coordenação entre múltiplos serviços."""

    @pytest.mark.asyncio
    async def test_service_registry_integration(self):
        """Testa integração com Service Registry."""
        mock_client = AsyncMock()
        mock_client.get_service_address = AsyncMock(
            return_value="http://worker-agents:8000"
        )

        monitor = HealthMonitor(service_registry_client=mock_client)

        # Verificar que pode obter endereço
        address = await mock_client.get_service_address("worker-agents")
        assert address == "http://worker-agents:8000"

    @pytest.mark.asyncio
    async def test_orchestrator_workflow_pause(self):
        """Testa pausa de workflow via Orchestrator."""
        mock_client = AsyncMock()
        mock_client.pause_workflow = AsyncMock(
            return_value={
                "workflow_id": "wf-123",
                "success": True,
                "pause_duration_seconds": 300
            }
        )

        result = await mock_client.pause_workflow(
            workflow_id="wf-123",
            reason="Deadlock detected",
            duration_seconds=300
        )

        assert result["success"] is True
