"""Testes para activity de publicação de eventos de otimização."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.activities.optimization_event import (
    publish_ticket_completed_event,
    publish_workflow_optimization_events,
)


@pytest.mark.asyncio
class TestOptimizationEventActivity:
    """Testes para activity de otimização."""

    async def test_publish_ticket_completed_success(self):
        """Testa publicação bem-sucedida de evento ticket.completed."""
        ticket = {
            "ticket_id": "test-ticket-001",
            "status": "COMPLETED",
            "actual_duration_ms": 1500,
            "peak_memory_mb": 128,
            "tasks": [
                {
                    "task_id": "task-1",
                    "executor_type": "query",
                    "duration_ms": 500,
                    "execution_context": {
                        "collection": "users",
                        "query": '{"status": "active"}',
                    },
                }
            ],
            "completed_at": "2026-03-18T12:00:00Z",
        }

        # Mock do producer
        mock_producer = AsyncMock()
        mock_producer.publish_ticket_completed = AsyncMock()

        with patch(
            "src.activities.optimization_event.get_optimization_producer",
            return_value=mock_producer,
        ):
            result = await publish_ticket_completed_event(ticket, "workflow-001")

        assert result["success"] is True
        assert result["ticket_id"] == "test-ticket-001"
        assert result["workflow_id"] == "workflow-001"
        mock_producer.publish_ticket_completed.assert_called_once()

    async def test_publish_ticket_completed_error_handling(self):
        """Testa tratamento de erro na publicação."""
        ticket = {
            "ticket_id": "test-ticket-002",
            "status": "FAILED",
            "tasks": [],
        }

        # Mock que lança exceção
        async def failing_init():
            raise Exception("Kafka connection failed")

        with patch(
            "src.activities.optimization_event.get_optimization_producer", side_effect=failing_init
        ):
            result = await publish_ticket_completed_event(ticket, "workflow-002")

        # Não deve falhar, apenas retornar success=False
        assert result["success"] is False
        assert result["ticket_id"] == "test-ticket-002"
        assert "error" in result

    async def test_publish_workflow_optimization_events_multiple_tickets(self):
        """Testa publicação em massa para múltiplos tickets."""
        tickets = [
            {
                "ticket": {
                    "ticket_id": "ticket-001",
                    "status": "COMPLETED",
                    "tasks": [],
                }
            },
            {
                "ticket": {
                    "ticket_id": "ticket-002",
                    "status": "COMPLETED",
                    "tasks": [],
                }
            },
            {
                "ticket": {
                    "ticket_id": "ticket-003",
                    "status": "PENDING",  # Deve ser ignorado
                    "tasks": [],
                }
            },
            {
                "ticket": {
                    "ticket_id": "ticket-004",
                    "status": "FAILED",
                    "tasks": [],
                }
            },
        ]

        # Mock da activity individual
        async def mock_publish(ticket, workflow_id):
            return {
                "success": True,
                "ticket_id": ticket["ticket_id"],
                "workflow_id": workflow_id,
            }

        with patch(
            "src.activities.optimization_event.publish_ticket_completed_event",
            side_effect=mock_publish,
        ):
            result = await publish_workflow_optimization_events(tickets, "workflow-001")

        # 3 tickets com status válido (COMPLETED, FAILED, COMPENSATED)
        assert result["successful_count"] == 3
        assert result["failed_count"] == 0
        assert result["workflow_id"] == "workflow-001"

    async def test_publish_workflow_optimization_events_partial_failure(self):
        """Testa publicação em massa com falhas parciais."""
        tickets = [
            {
                "ticket": {
                    "ticket_id": "ticket-001",
                    "status": "COMPLETED",
                    "tasks": [],
                }
            },
            {
                "ticket": {
                    "ticket_id": "ticket-002",
                    "status": "COMPLETED",
                    "tasks": [],
                }
            },
        ]

        call_count = 0

        async def mock_publish(ticket, workflow_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": True, "ticket_id": ticket["ticket_id"]}
            else:
                return {"success": False, "ticket_id": ticket["ticket_id"]}

        with patch(
            "src.activities.optimization_event.publish_ticket_completed_event",
            side_effect=mock_publish,
        ):
            result = await publish_workflow_optimization_events(tickets, "workflow-001")

        assert result["successful_count"] == 1
        assert result["failed_count"] == 1
