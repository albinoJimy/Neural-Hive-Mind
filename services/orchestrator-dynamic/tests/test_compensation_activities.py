"""
Testes unitários para activities de compensação (Saga Pattern).

Cobre:
- compensate_ticket: Criação e publicação de tickets de compensação
- build_compensation_order: Ordenação topológica reversa
- update_ticket_compensation_status: Atualização de status
- _get_compensation_action: Mapeamento de ações de compensação
"""

from datetime import timezone
UTC = timezone.utc
from unittest.mock import AsyncMock, MagicMock

import pytest

UTC = timezone.utc

# Configure path
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.activities.compensation import (
    _get_compensation_action,
    build_compensation_order,
    compensate_ticket,
    set_compensation_dependencies,
    update_ticket_compensation_status,
)


@pytest.fixture()
def mock_config():
    """Config mock para testes."""
    config = MagicMock()
    config.saga_retry_max_attempts = 3
    config.saga_retry_initial_delay_ms = 1000
    config.saga_retry_max_delay_ms = 30000
    return config


@pytest.fixture()
def mock_kafka_producer():
    """Mock do Kafka producer."""
    producer = AsyncMock()
    producer.publish_ticket = AsyncMock(return_value=True)
    return producer


@pytest.fixture()
def mock_mongodb_client():
    """Mock do MongoDB client."""
    client = AsyncMock()
    client.save_ticket = AsyncMock(return_value=True)
    client.update_ticket_compensation = AsyncMock(return_value=True)
    return client


@pytest.fixture()
def mock_metrics():
    """Mock das métricas."""
    metrics = MagicMock()
    metrics.record_compensation = MagicMock()
    return metrics


@pytest.fixture()
def setup_dependencies(mock_config, mock_kafka_producer, mock_mongodb_client, mock_metrics):
    """Setup das dependências globais."""
    set_compensation_dependencies(
        config=mock_config,
        kafka_producer=mock_kafka_producer,
        mongodb_client=mock_mongodb_client,
        metrics=mock_metrics,
    )
    return {
        "config": mock_config,
        "kafka_producer": mock_kafka_producer,
        "mongodb_client": mock_mongodb_client,
        "metrics": mock_metrics,
    }


class TestGetCompensationAction:
    """Testes para _get_compensation_action."""

    def test_compensation_action_for_build(self):
        """Testa ação de compensação para task_type BUILD."""
        original_params = {
            "artifact_ids": ["artifact-1", "artifact-2"],
            "registry_url": "registry.example.com",
            "image_tag": "v1.0.0",
            "repository": "my-repo",
        }

        action = _get_compensation_action("BUILD", original_params)

        assert action["action"] == "delete_artifacts"
        assert action["artifact_ids"] == ["artifact-1", "artifact-2"]
        assert action["registry_url"] == "registry.example.com"
        assert action["image_tag"] == "v1.0.0"
        assert action["repository"] == "my-repo"

    def test_compensation_action_for_deploy(self):
        """Testa ação de compensação para task_type DEPLOY."""
        original_params = {
            "deployment_name": "my-deployment",
            "previous_revision": "HEAD~1",
            "namespace": "production",
            "provider": "argocd",
            "cluster_server": "https://cluster.example.com",
        }

        action = _get_compensation_action("DEPLOY", original_params)

        assert action["action"] == "rollback_deployment"
        assert action["deployment_name"] == "my-deployment"
        assert action["previous_revision"] == "HEAD~1"
        assert action["namespace"] == "production"

    def test_compensation_action_for_test(self):
        """Testa ação de compensação para task_type TEST."""
        original_params = {
            "test_id": "test-123",
            "namespace": "testing",
            "resources": ["pod-1", "pod-2"],
            "cleanup_jobs": True,
        }

        action = _get_compensation_action("TEST", original_params)

        assert action["action"] == "cleanup_test_env"
        assert action["test_id"] == "test-123"
        assert action["namespace"] == "testing"
        assert action["resources"] == ["pod-1", "pod-2"]

    def test_compensation_action_for_validate(self):
        """Testa ação de compensação para task_type VALIDATE."""
        original_params = {
            "approval_id": "approval-123",
            "validation_id": "validation-456",
        }

        action = _get_compensation_action("VALIDATE", original_params)

        assert action["action"] == "revert_approval"
        assert action["approval_id"] == "approval-123"
        assert action["validation_id"] == "validation-456"
        assert action["revert_status"] == "PENDING"

    def test_compensation_action_for_execute(self):
        """Testa ação de compensação para task_type EXECUTE."""
        original_params = {
            "execution_id": "exec-123",
            "rollback_script": "rollback.sh",
            "working_dir": "/tmp/work",
            "cleanup_outputs": True,
        }

        action = _get_compensation_action("EXECUTE", original_params)

        assert action["action"] == "rollback_execution"
        assert action["execution_id"] == "exec-123"
        assert action["rollback_script"] == "rollback.sh"
        assert action["working_dir"] == "/tmp/work"

    def test_compensation_action_for_unknown_task_type(self):
        """Testa ação de compensação para task_type desconhecido."""
        original_params = {"key": "value"}

        action = _get_compensation_action("UNKNOWN", original_params)

        assert action["action"] == "generic_cleanup"
        assert action["original_task_type"] == "UNKNOWN"
        assert action["original_params"] == original_params


class TestCompensateTicket:
    """Testes para compensate_ticket activity."""

    @pytest.mark.asyncio()
    async def test_compensate_ticket_build_success(
        self, setup_dependencies, mock_kafka_producer, mock_mongodb_client
    ):
        """Testa compensação de ticket BUILD com sucesso."""
        ticket = {
            "ticket_id": "ticket-123",
            "task_type": "BUILD",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "priority": "HIGH",
            "risk_band": "high",
            "parameters": {
                "artifact_ids": ["artifact-1"],
                "registry_url": "registry.example.com",
            },
        }

        result = await compensate_ticket(ticket, "task_failed")

        assert result is not None
        assert len(result) == 36  # UUID format
        mock_mongodb_client.save_ticket.assert_called_once()
        mock_kafka_producer.publish_ticket.assert_called_once()

        # Verificar ticket criado
        call_args = mock_mongodb_client.save_ticket.call_args[0][0]
        assert call_args["task_type"] == "COMPENSATE"
        assert call_args["original_ticket_id"] == "ticket-123"
        assert call_args["parameters"]["action"] == "delete_artifacts"

    @pytest.mark.asyncio()
    async def test_compensate_ticket_deploy_success(
        self, setup_dependencies, mock_kafka_producer, mock_mongodb_client
    ):
        """Testa compensação de ticket DEPLOY com sucesso."""
        ticket = {
            "ticket_id": "ticket-deploy-123",
            "task_type": "DEPLOY",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "priority": "HIGH",
            "risk_band": "critical",
            "parameters": {
                "deployment_name": "my-app",
                "namespace": "production",
                "provider": "argocd",
            },
        }

        result = await compensate_ticket(ticket, "workflow_inconsistent")

        assert result is not None
        call_args = mock_mongodb_client.save_ticket.call_args[0][0]
        assert call_args["parameters"]["action"] == "rollback_deployment"
        assert call_args["parameters"]["deployment_name"] == "my-app"

    @pytest.mark.asyncio()
    async def test_compensate_ticket_with_retry_config(
        self, setup_dependencies, mock_kafka_producer, mock_mongodb_client
    ):
        """Testa compensação com configuração customizada de retry."""
        ticket = {
            "ticket_id": "ticket-retry-123",
            "task_type": "TEST",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "priority": "NORMAL",
            "risk_band": "medium",
            "parameters": {"test_id": "test-123"},
        }

        retry_config = {
            "max_attempts": 5,
            "initial_delay_ms": 2000,
            "max_delay_ms": 60000,
        }

        result = await compensate_ticket(ticket, "test_failed", retry_config)

        assert result is not None
        mock_kafka_producer.publish_ticket.assert_called()

    @pytest.mark.asyncio()
    async def test_compensate_ticket_records_metrics(
        self, setup_dependencies, mock_kafka_producer, mock_mongodb_client, mock_metrics
    ):
        """Testa que compensação registra métricas."""
        ticket = {
            "ticket_id": "ticket-metrics-123",
            "task_type": "BUILD",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "priority": "NORMAL",
            "risk_band": "low",
            "parameters": {},
        }

        await compensate_ticket(ticket, "task_failed")

        mock_metrics.record_compensation.assert_called_once_with(reason="task_failed")

    @pytest.mark.asyncio()
    async def test_compensate_ticket_without_mongodb(self, setup_dependencies, mock_kafka_producer):
        """Testa compensação quando MongoDB não está disponível."""
        # Remove MongoDB
        set_compensation_dependencies(
            config=setup_dependencies["config"],
            kafka_producer=mock_kafka_producer,
            mongodb_client=None,
            metrics=setup_dependencies["metrics"],
        )

        ticket = {
            "ticket_id": "ticket-no-mongo-123",
            "task_type": "BUILD",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "priority": "NORMAL",
            "risk_band": "low",
            "parameters": {},
        }

        result = await compensate_ticket(ticket, "task_failed")

        # Deve criar ticket mesmo sem MongoDB (fail-open)
        assert result is not None
        mock_kafka_producer.publish_ticket.assert_called_once()

    @pytest.mark.asyncio()
    async def test_compensate_ticket_without_kafka(self, setup_dependencies, mock_mongodb_client):
        """Testa compensação quando Kafka não está disponível."""
        # Remove Kafka
        set_compensation_dependencies(
            config=setup_dependencies["config"],
            kafka_producer=None,
            mongodb_client=mock_mongodb_client,
            metrics=setup_dependencies["metrics"],
        )

        ticket = {
            "ticket_id": "ticket-no-kafka-123",
            "task_type": "BUILD",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "priority": "NORMAL",
            "risk_band": "low",
            "parameters": {},
        }

        result = await compensate_ticket(ticket, "task_failed")

        # Deve criar ticket mesmo sem Kafka (foi persistido no MongoDB)
        assert result is not None
        mock_mongodb_client.save_ticket.assert_called_once()

    @pytest.mark.asyncio()
    async def test_compensate_ticket_metadata(self, setup_dependencies):
        """Testa que metadados são incluídos corretamente."""
        ticket = {
            "ticket_id": "ticket-meta-123",
            "task_type": "VALIDATE",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "priority": "HIGH",
            "status": "FAILED",
            "risk_band": "high",
            "parameters": {"approval_id": "approval-123"},
        }

        result = await compensate_ticket(ticket, "validation_failed")

        call_args = setup_dependencies["mongodb_client"].save_ticket.call_args[0][0]
        metadata = call_args["metadata"]

        assert metadata["compensation_reason"] == "validation_failed"
        assert metadata["original_task_type"] == "VALIDATE"
        assert metadata["original_status"] == "FAILED"


class TestBuildCompensationOrder:
    """Testes para build_compensation_order activity."""

    @pytest.mark.asyncio()
    async def test_build_order_simple_chain(self):
        """Testa ordenação de compensação para cadeia simples A -> B -> C."""
        failed_tickets = [{"ticket_id": "C"}]
        all_tickets = [
            {"ticket_id": "A", "status": "COMPLETED", "dependencies": []},
            {"ticket_id": "B", "status": "COMPLETED", "dependencies": ["A"]},
            {"ticket_id": "C", "status": "FAILED", "dependencies": ["B"]},
        ]

        result = await build_compensation_order(failed_tickets, all_tickets)

        # Ordem deve ser reversa: C, B, A
        assert len(result) == 3
        assert result[0]["ticket_id"] == "C"
        assert result[1]["ticket_id"] == "B"
        assert result[2]["ticket_id"] == "A"

    @pytest.mark.asyncio()
    async def test_build_order_with_multiple_failures(self):
        """Testa ordenação com múltiplas falhas."""
        failed_tickets = [
            {"ticket_id": "B"},
            {"ticket_id": "D"},
        ]
        all_tickets = [
            {"ticket_id": "A", "status": "COMPLETED", "dependencies": []},
            {"ticket_id": "B", "status": "FAILED", "dependencies": ["A"]},
            {"ticket_id": "C", "status": "COMPLETED", "dependencies": ["A"]},
            {"ticket_id": "D", "status": "FAILED", "dependencies": ["C"]},
        ]

        result = await build_compensation_order(failed_tickets, all_tickets)

        # Ordem deve respeitar dependências: D, C, B, A
        # ou B, A, D, C dependendo da ordem de processamento
        assert len(result) >= 2
        ticket_ids = [t["ticket_id"] for t in result]
        assert "B" in ticket_ids
        assert "D" in ticket_ids

    @pytest.mark.asyncio()
    async def test_build_order_only_compensates_executed(self):
        """Testa que apenas tickets executados são compensados."""
        failed_tickets = [{"ticket_id": "B"}]
        all_tickets = [
            {"ticket_id": "A", "status": "COMPLETED", "dependencies": []},
            {"ticket_id": "B", "status": "FAILED", "dependencies": ["A"]},
            {"ticket_id": "C", "status": "PENDING", "dependencies": ["B"]},
        ]

        result = await build_compensation_order(failed_tickets, all_tickets)

        # C não deve estar incluído (PENDING)
        ticket_ids = [t["ticket_id"] for t in result]
        assert "A" in ticket_ids
        assert "B" in ticket_ids
        assert "C" not in ticket_ids

    @pytest.mark.asyncio()
    async def test_build_order_compensating_status(self):
        """Testa que tickets em compensação também são incluídos."""
        failed_tickets = [{"ticket_id": "B"}]
        all_tickets = [
            {"ticket_id": "A", "status": "COMPLETED", "dependencies": []},
            {"ticket_id": "B", "status": "COMPENSATING", "dependencies": ["A"]},
        ]

        result = await build_compensation_order(failed_tickets, all_tickets)

        # Ambos devem estar incluídos
        ticket_ids = [t["ticket_id"] for t in result]
        assert "A" in ticket_ids
        assert "B" in ticket_ids

    @pytest.mark.asyncio()
    async def test_build_order_with_ticket_dict(self):
        """Testa quando tickets estão aninhados em dict."""
        failed_tickets = [{"ticket": {"ticket_id": "B"}}]
        all_tickets = [
            {"ticket": {"ticket_id": "A", "status": "COMPLETED", "dependencies": []}},
            {"ticket": {"ticket_id": "B", "status": "FAILED", "dependencies": ["A"]}},
        ]

        result = await build_compensation_order(failed_tickets, all_tickets)

        assert len(result) == 2
        assert result[0]["ticket_id"] == "B"
        assert result[1]["ticket_id"] == "A"

    @pytest.mark.asyncio()
    async def test_build_order_diamond_dependency(self):
        """Testa grafo de dependências em diamante."""
        # A -> B -> D
        # A -> C -> D
        failed_tickets = [{"ticket_id": "D"}]
        all_tickets = [
            {"ticket_id": "A", "status": "COMPLETED", "dependencies": []},
            {"ticket_id": "B", "status": "COMPLETED", "dependencies": ["A"]},
            {"ticket_id": "C", "status": "COMPLETED", "dependencies": ["A"]},
            {"ticket_id": "D", "status": "FAILED", "dependencies": ["B", "C"]},
        ]

        result = await build_compensation_order(failed_tickets, all_tickets)

        # D primeiro, depois B e C (em qualquer ordem), depois A
        assert len(result) == 4
        assert result[0]["ticket_id"] == "D"
        assert result[-1]["ticket_id"] == "A"

    @pytest.mark.asyncio()
    async def test_build_order_empty_failed(self):
        """Testa com lista vazia de falhas."""
        result = await build_compensation_order([], [])
        assert result == []

    @pytest.mark.asyncio()
    async def test_build_order_complex_dag(self):
        """Testa DAG mais complexo."""
        # A -> B -> E
        # A -> C -> E
        # A -> D -> E
        failed_tickets = [{"ticket_id": "E"}]
        all_tickets = [
            {"ticket_id": "A", "status": "COMPLETED", "dependencies": []},
            {"ticket_id": "B", "status": "COMPLETED", "dependencies": ["A"]},
            {"ticket_id": "C", "status": "COMPLETED", "dependencies": ["A"]},
            {"ticket_id": "D", "status": "COMPLETED", "dependencies": ["A"]},
            {"ticket_id": "E", "status": "FAILED", "dependencies": ["B", "C", "D"]},
        ]

        result = await build_compensation_order(failed_tickets, all_tickets)

        assert len(result) == 5
        assert result[0]["ticket_id"] == "E"
        assert result[-1]["ticket_id"] == "A"


class TestUpdateTicketCompensationStatus:
    """Testes para update_ticket_compensation_status activity."""

    @pytest.mark.asyncio()
    async def test_update_status_success(self, setup_dependencies, mock_mongodb_client):
        """Testa atualização de status com sucesso."""
        await update_ticket_compensation_status("ticket-123", "comp-456")

        mock_mongodb_client.update_ticket_compensation.assert_called_once_with(
            ticket_id="ticket-123",
            compensation_ticket_id="comp-456",
            status="COMPENSATING",
        )

    @pytest.mark.asyncio()
    async def test_update_status_without_mongodb(self, setup_dependencies):
        """Testa atualização quando MongoDB não está disponível."""
        set_compensation_dependencies(
            config=setup_dependencies["config"],
            kafka_producer=setup_dependencies["kafka_producer"],
            mongodb_client=None,
            metrics=setup_dependencies["metrics"],
        )

        result = await update_ticket_compensation_status("ticket-123", "comp-456")

        # Deve retornar False sem erro
        assert result is False

    @pytest.mark.asyncio()
    async def test_update_status_exception_handling(self, setup_dependencies, mock_mongodb_client):
        """Testa que exceções são tratadas corretamente."""
        mock_mongodb_client.update_ticket_compensation.side_effect = Exception("DB error")

        result = await update_ticket_compensation_status("ticket-123", "comp-456")

        # Deve retornar False em caso de exceção
        assert result is False
