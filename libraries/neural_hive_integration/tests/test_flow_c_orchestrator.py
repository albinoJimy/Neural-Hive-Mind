"""
Testes unitários para FlowCOrchestrator.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from neural_hive_integration.orchestration.flow_c_orchestrator import FlowCOrchestrator
from neural_hive_integration.models.flow_c_context import FlowCResult
from neural_hive_integration.clients.service_registry_client import AgentInfo


@pytest.fixture
def orchestrator():
    """Fixture do FlowCOrchestrator."""
    return FlowCOrchestrator()


@pytest.fixture
def sample_decision():
    """Decision consolidada de exemplo."""
    return {
        "intent_id": "intent-123",
        "plan_id": "plan-456",
        "decision_id": "decision-789",
        "correlation_id": "corr-abc",
        "priority": 5,
        "risk_band": "medium",
        "cognitive_plan": {
            "tasks": [
                {
                    "type": "code_generation",
                    "template_id": "microservice",
                    "parameters": {"language": "python"},
                    "capabilities": ["python", "fastapi"],
                    "description": "Generate microservice"
                }
            ]
        }
    }


@pytest.fixture
def mock_workers():
    """Workers de exemplo."""
    return [
        AgentInfo(
            agent_id="worker-1",
            agent_type="worker",
            capabilities=["python", "fastapi"],
            endpoint="http://worker-1:8000",
            metadata={"version": "1.0.0"}
        ),
        AgentInfo(
            agent_id="worker-2",
            agent_type="worker",
            capabilities=["python", "terraform"],
            endpoint="http://worker-2:8000",
            metadata={"version": "1.0.0"}
        )
    ]


@pytest.mark.asyncio
async def test_initialize_and_close(orchestrator):
    """Testa inicialização e fechamento do orchestrator."""
    await orchestrator.initialize()
    await orchestrator.close()


@pytest.mark.asyncio
async def test_execute_flow_c_success(orchestrator, sample_decision, mock_workers):
    """Testa execução bem-sucedida do Flow C completo."""
    # Mock dos clientes
    orchestrator.orchestrator_client.start_workflow = AsyncMock(return_value="workflow-123")
    orchestrator.service_registry.discover_agents = AsyncMock(return_value=mock_workers)

    # Mock ticket client
    mock_ticket = MagicMock()
    mock_ticket.ticket_id = "ticket-001"
    mock_ticket.status = "completed"
    mock_ticket.model_dump.return_value = {
        "ticket_id": "ticket-001",
        "task_type": "code_generation",
        "required_capabilities": ["python", "fastapi"],
        "payload": {"template_id": "microservice", "parameters": {}, "ticket_id": "ticket-001"},
        "sla_deadline": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
        "priority": 5
    }
    orchestrator.ticket_client.create_ticket = AsyncMock(return_value=mock_ticket)
    orchestrator.ticket_client.get_ticket = AsyncMock(return_value=mock_ticket)
    orchestrator.ticket_client.update_ticket_status = AsyncMock()

    # Mock worker client assignment
    with patch('neural_hive_integration.orchestration.flow_c_orchestrator.WorkerAgentClient') as mock_worker_client_class:
        mock_worker_instance = AsyncMock()
        mock_worker_instance.assign_task = AsyncMock()
        mock_worker_instance.close = AsyncMock()
        mock_worker_client_class.return_value = mock_worker_instance

        # Mock telemetry
        orchestrator.telemetry.publish_event = AsyncMock()

        # Executar Flow C
        result = await orchestrator.execute_flow_c(sample_decision)

    # Verificações
    assert result.success is True
    assert len(result.steps) == 6  # C1 a C6
    assert result.tickets_generated == 1
    assert result.tickets_completed == 1
    assert result.tickets_failed == 0
    assert result.telemetry_published is True

    # Verificar chamadas
    orchestrator.orchestrator_client.start_workflow.assert_called_once()
    orchestrator.service_registry.discover_agents.assert_called_once()
    orchestrator.ticket_client.create_ticket.assert_called_once()


@pytest.mark.asyncio
async def test_execute_c1_validate_missing_fields(orchestrator):
    """Testa C1 com campos faltando."""
    invalid_decision = {"intent_id": "123"}

    with pytest.raises(ValueError, match="Missing required field"):
        await orchestrator._execute_c1_validate(invalid_decision, MagicMock())


@pytest.mark.asyncio
async def test_execute_c2_generate_tickets(orchestrator, sample_decision):
    """Testa C2 geração de tickets."""
    orchestrator.orchestrator_client.start_workflow = AsyncMock(return_value="workflow-123")

    mock_ticket = MagicMock()
    mock_ticket.ticket_id = "ticket-001"
    mock_ticket.model_dump.return_value = {
        "ticket_id": "ticket-001",
        "task_type": "code_generation",
        "payload": {"template_id": "microservice", "ticket_id": "ticket-001"}
    }
    orchestrator.ticket_client.create_ticket = AsyncMock(return_value=mock_ticket)

    context = MagicMock()
    context.plan_id = "plan-456"
    context.correlation_id = "corr-abc"
    context.priority = 5
    context.sla_deadline = datetime.utcnow() + timedelta(hours=4)

    workflow_id, tickets = await orchestrator._execute_c2_generate_tickets(sample_decision, context)

    assert workflow_id == "workflow-123"
    assert len(tickets) == 1
    assert tickets[0]["ticket_id"] == "ticket-001"
    assert "template_id" in tickets[0]["payload"]
    assert tickets[0]["payload"]["ticket_id"] == "ticket-001"


@pytest.mark.asyncio
async def test_execute_c3_discover_workers(orchestrator, mock_workers):
    """Testa C3 descoberta de workers."""
    orchestrator.service_registry.discover_agents = AsyncMock(return_value=mock_workers)

    tickets = [
        {"required_capabilities": ["python", "fastapi"]},
        {"required_capabilities": ["terraform"]}
    ]

    workers = await orchestrator._execute_c3_discover_workers(tickets, MagicMock())

    assert len(workers) == 2
    assert workers[0].agent_id == "worker-1"
    orchestrator.service_registry.discover_agents.assert_called_once_with(
        capabilities=["python", "fastapi", "terraform"],
        filters={"status": "healthy"}
    )


@pytest.mark.asyncio
async def test_execute_c4_assign_tickets_no_workers(orchestrator):
    """Testa C4 sem workers disponíveis."""
    tickets = [{"ticket_id": "ticket-001"}]
    workers = []

    assignments = await orchestrator._execute_c4_assign_tickets(tickets, workers, MagicMock())

    assert len(assignments) == 0


@pytest.mark.asyncio
async def test_execute_c5_monitor_execution_timeout(orchestrator):
    """Testa C5 com timeout baseado em SLA."""
    mock_ticket = MagicMock()
    mock_ticket.status = "in_progress"
    orchestrator.ticket_client.get_ticket = AsyncMock(return_value=mock_ticket)

    tickets = [{"ticket_id": "ticket-001"}]
    context = MagicMock()
    # SLA deadline já passou
    context.sla_deadline = datetime.utcnow() - timedelta(seconds=1)

    results = await orchestrator._execute_c5_monitor_execution(tickets, context)

    assert results["completed"] == 0
    assert results["failed"] == 0


@pytest.mark.asyncio
async def test_execute_c5_monitor_execution_completed(orchestrator):
    """Testa C5 com tickets completados."""
    mock_ticket = MagicMock()
    mock_ticket.status = "completed"
    orchestrator.ticket_client.get_ticket = AsyncMock(return_value=mock_ticket)

    tickets = [{"ticket_id": "ticket-001"}, {"ticket_id": "ticket-002"}]
    context = MagicMock()
    context.sla_deadline = datetime.utcnow() + timedelta(hours=4)

    results = await orchestrator._execute_c5_monitor_execution(tickets, context)

    assert results["completed"] == 2
    assert results["failed"] == 0


@pytest.mark.asyncio
async def test_flow_c_sla_violation(orchestrator, sample_decision, mock_workers):
    """Testa detecção de violação de SLA."""
    orchestrator.orchestrator_client.start_workflow = AsyncMock(return_value="workflow-123")
    orchestrator.service_registry.discover_agents = AsyncMock(return_value=mock_workers)

    mock_ticket = MagicMock()
    mock_ticket.ticket_id = "ticket-001"
    mock_ticket.status = "completed"
    mock_ticket.model_dump.return_value = {
        "ticket_id": "ticket-001",
        "task_type": "code_generation",
        "required_capabilities": ["python"],
        "payload": {"template_id": "test", "ticket_id": "ticket-001"},
        "sla_deadline": (datetime.utcnow() - timedelta(hours=1)).isoformat(),  # SLA violado
        "priority": 5
    }
    orchestrator.ticket_client.create_ticket = AsyncMock(return_value=mock_ticket)
    orchestrator.ticket_client.get_ticket = AsyncMock(return_value=mock_ticket)
    orchestrator.ticket_client.update_ticket_status = AsyncMock()
    orchestrator.telemetry.publish_event = AsyncMock()

    with patch('neural_hive_integration.orchestration.flow_c_orchestrator.WorkerAgentClient') as mock_worker_client_class:
        mock_worker_instance = AsyncMock()
        mock_worker_instance.assign_task = AsyncMock()
        mock_worker_instance.close = AsyncMock()
        mock_worker_client_class.return_value = mock_worker_instance

        # Forçar deadline no passado no context
        with patch('neural_hive_integration.orchestration.flow_c_orchestrator.datetime') as mock_datetime:
            past_time = datetime.utcnow() - timedelta(hours=5)
            mock_datetime.utcnow.return_value = past_time
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            result = await orchestrator.execute_flow_c(sample_decision)

    assert result.success is True  # Flow completa mesmo com SLA violado


@pytest.mark.asyncio
async def test_flow_c_failure_handling(orchestrator, sample_decision):
    """Testa tratamento de falhas no Flow C."""
    orchestrator.orchestrator_client.start_workflow = AsyncMock(side_effect=Exception("Workflow failed"))

    result = await orchestrator.execute_flow_c(sample_decision)

    assert result.success is False
    assert result.error == "Workflow failed"
    assert result.tickets_generated == 0
