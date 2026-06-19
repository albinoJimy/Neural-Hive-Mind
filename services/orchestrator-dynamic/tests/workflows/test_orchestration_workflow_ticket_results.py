"""Testes para o tracking de conclusão de tickets no OrchestrationWorkflow.

Cobre o fix do status "PARTIAL": o workflow consolidava imediatamente após
publicar os tickets (todos PENDING). Agora o signal ticket_completed regista o
resultado em self._ticket_results, que um wait_condition em run() usa para
esperar pela conclusão real antes de consolidar.
"""

from unittest.mock import AsyncMock, patch

import pytest
from src.workflows.orchestration_workflow import OrchestrationWorkflow


class TestTicketResultsInitialization:
    def test_ticket_results_initialized_empty(self):
        """__init__ deve criar self._ticket_results vazio."""
        wf = OrchestrationWorkflow()
        assert wf._ticket_results == {}


class TestTicketCompletedSignalRecords:
    """O signal ticket_completed deve registar o resultado para o wait_condition."""

    @pytest.mark.asyncio()
    async def test_signal_records_result(self):
        wf = OrchestrationWorkflow()
        wf._workflow_id = "wf-1"

        # workflow.execute_activity (publicação do evento de otimização) é
        # irrelevante para o tracking; mockar para não tocar no contexto Temporal.
        with patch("src.workflows.orchestration_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value=None)
            mock_wf.logger = AsyncMock()

            result = {"status": "COMPLETED", "output": {"rows": 3}}
            await wf.ticket_completed("ticket-abc", result)

        assert wf._ticket_results["ticket-abc"] == result
        assert wf._ticket_results["ticket-abc"]["status"] == "COMPLETED"

    @pytest.mark.asyncio()
    async def test_signal_records_failed_result(self):
        """Um ticket FAILED também é registado (estado terminal)."""
        wf = OrchestrationWorkflow()
        wf._workflow_id = "wf-1"

        with patch("src.workflows.orchestration_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(return_value=None)
            mock_wf.logger = AsyncMock()

            await wf.ticket_completed("ticket-x", {"status": "FAILED"})

        assert wf._ticket_results["ticket-x"]["status"] == "FAILED"

    @pytest.mark.asyncio()
    async def test_signal_records_even_if_optimization_event_fails(self):
        """Falha na publicação do evento não impede o registo do resultado."""
        wf = OrchestrationWorkflow()
        wf._workflow_id = "wf-1"

        with patch("src.workflows.orchestration_workflow.workflow") as mock_wf:
            mock_wf.execute_activity = AsyncMock(side_effect=RuntimeError("kafka down"))
            mock_wf.logger = AsyncMock()

            # O registo acontece ANTES do execute_activity; a exceção é engolida.
            await wf.ticket_completed("ticket-y", {"status": "COMPLETED"})

        assert wf._ticket_results["ticket-y"]["status"] == "COMPLETED"
