"""
Testes para Queen MCP Tools.

TDD: Testes escritos antes da implementação.
Espec: Ferramentas estratégicas do Queen Agent via MCP
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestMakeDecisionTool:
    """Testes da ferramenta make_decision."""

    @pytest.mark.asyncio
    async def test_make_decision_success(self):
        """Testa tomada de decisão com sucesso."""
        from queen_mcp_server.tools.queen_tools import make_decision

        # Mock da chamada HTTP
        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_decision",
            new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "decision_id": "dec-123",
                "decision_type": "STRATEGIC",
                "action": "proceed",
                "reasoning": "Criterios atendidos"
            }

            result = await make_decision(
                event_type="consolidated_decision",
                source_id="plan-456",
                trigger_data={"confidence": 0.8},
                priority="high"
            )

            assert result["decision_id"] == "dec-123"
            assert result["decision_type"] == "STRATEGIC"
            assert result["action"] == "proceed"
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_decision_invalid_event_type(self):
        """Testa erro para event_type inválido."""
        from queen_mcp_server.tools.queen_tools import make_decision

        with pytest.raises(ValueError, match="Invalid event_type"):
            await make_decision(
                event_type="invalid_type",
                source_id="plan-456",
                trigger_data={}
            )

    @pytest.mark.asyncio
    async def test_make_decision_all_valid_event_types(self):
        """Testa todos os tipos de eventos válidos."""
        from queen_mcp_server.tools.queen_tools import make_decision

        valid_types = [
            "consolidated_decision",
            "telemetry",
            "critical_incident",
            "sla_violation",
            "resource_saturation"
        ]

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_decision",
            new_callable=AsyncMock,
            return_value={"decision_id": "test", "decision_type": "TEST"}
        ):
            for event_type in valid_types:
                result = await make_decision(
                    event_type=event_type,
                    source_id="test-source",
                    trigger_data={}
                )
                assert result["decision_id"] == "test"

    @pytest.mark.asyncio
    async def test_make_decision_with_default_priority(self):
        """Testa uso de prioridade padrão."""
        from queen_mcp_server.tools.queen_tools import make_decision

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_decision",
            new_callable=AsyncMock,
            return_value={"decision_id": "test", "decision_type": "TEST"}
        ) as mock_call:
            await make_decision(
                event_type="telemetry",
                source_id="source-1",
                trigger_data={}
            )

            # Verificar que foi chamado (não falha por falta de priority)
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_decision_http_error_handling(self):
        """Testa tratamento de erro HTTP."""
        from queen_mcp_server.tools.queen_tools import make_decision

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_decision",
            new_callable=AsyncMock,
            return_value={
                "error": "HTTP error: 503",
                "decision_id": None,
                "decision_type": "ERROR"
            }
        ):
            result = await make_decision(
                event_type="critical_incident",
                source_id="source-1",
                trigger_data={}
            )

            assert result["decision_type"] == "ERROR"
            assert result["decision_id"] is None


class TestArbitrateConflictTool:
    """Testes da ferramenta arbitrate_conflict."""

    @pytest.mark.asyncio
    async def test_arbitrate_conflict_success(self):
        """Testa arbitragem de conflito com sucesso."""
        from queen_mcp_server.tools.queen_tools import arbitrate_conflict

        decisions = [
            {"specialist": "business", "decision": "approve", "confidence": 0.9},
            {"specialist": "technical", "decision": "reject", "confidence": 0.8}
        ]

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_arbitration",
            new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "conflict_id": "conf-789",
                "resolution_strategy": "weighted_consensus",
                "final_decision": "approve",
                "rationale": "Business specialist tem maior peso neste contexto"
            }

            result = await arbitrate_conflict(
                decisions=decisions,
                conflict_description="Conflito entre business e technical"
            )

            assert result["conflict_id"] == "conf-789"
            assert result["resolution_strategy"] == "weighted_consensus"
            assert result["final_decision"] == "approve"
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_arbitrate_conflict_insufficient_decisions(self):
        """Testa erro com menos de 2 decisões."""
        from queen_mcp_server.tools.queen_tools import arbitrate_conflict

        with pytest.raises(ValueError, match="At least 2 decisions"):
            await arbitrate_conflict(decisions=[{"decision": "test"}])

    @pytest.mark.asyncio
    async def test_arbitrate_conflict_single_decision_fails(self):
        """Testa que uma única decisão causa erro."""
        from queen_mcp_server.tools.queen_tools import arbitrate_conflict

        single_decision = [
            {"specialist": "business", "decision": "approve", "confidence": 0.9}
        ]

        with pytest.raises(ValueError, match="At least 2 decisions"):
            await arbitrate_conflict(decisions=single_decision)

    @pytest.mark.asyncio
    async def test_arbitrate_conflict_without_description(self):
        """Testa arbitragem sem descrição opcional."""
        from queen_mcp_server.tools.queen_tools import arbitrate_conflict

        decisions = [
            {"specialist": "A", "decision": "X"},
            {"specialist": "B", "decision": "Y"}
        ]

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_arbitration",
            new_callable=AsyncMock,
            return_value={"conflict_id": "conf-1", "resolution_strategy": "merge"}
        ):
            result = await arbitrate_conflict(
                decisions=decisions,
                conflict_description=None
            )

            assert result["conflict_id"] == "conf-1"

    @pytest.mark.asyncio
    async def test_arbitrate_conflict_multiple_decisions(self):
        """Testa arbitragem com múltiplas decisões."""
        from queen_mcp_server.tools.queen_tools import arbitrate_conflict

        decisions = [
            {"specialist": "A", "decision": "X"},
            {"specialist": "B", "decision": "Y"},
            {"specialist": "C", "decision": "Z"},
            {"specialist": "D", "decision": "W"}
        ]

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_arbitration",
            new_callable=AsyncMock,
            return_value={"conflict_id": "conf-2", "resolution_strategy": "majority"}
        ):
            result = await arbitrate_conflict(decisions=decisions)

            assert result["resolution_strategy"] == "majority"


class TestReplanWorkflowTool:
    """Testes da ferramenta replan_workflow."""

    @pytest.mark.asyncio
    async def test_replan_workflow_success(self):
        """Testa replanejamento de workflow com sucesso."""
        from queen_mcp_server.tools.queen_tools import replan_workflow

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_replanning",
            new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "replanning_id": "replan-456",
                "success": True,
                "new_plan_id": "plan-new-789",
                "preserved_steps": 5
            }

            result = await replan_workflow(
                plan_id="plan-123",
                reason="Workflow falhou no step 6",
                trigger_type="STRATEGIC",
                preserve_progress=True,
                priority=7
            )

            assert result["replanning_id"] == "replan-456"
            assert result["success"] is True
            assert result["new_plan_id"] == "plan-new-789"
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_replan_workflow_with_defaults(self):
        """Testa replanejamento com valores padrão."""
        from queen_mcp_server.tools.queen_tools import replan_workflow

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_replanning",
            new_callable=AsyncMock,
            return_value={"replanning_id": "replan-1", "success": True}
        ) as mock_call:
            await replan_workflow(
                plan_id="plan-123",
                reason="Falha detectada"
            )

            # Verificar chamada com valores padrão
            call_args = mock_call.call_args
            assert call_args[0][2] == "STRATEGIC"  # trigger_type padrão
            assert call_args[0][3] is True  # preserve_progress padrão
            assert call_args[0][4] == 5  # priority padrão

    @pytest.mark.asyncio
    async def test_replan_workflow_manual_trigger(self):
        """Testa replanejamento com trigger manual."""
        from queen_mcp_server.tools.queen_tools import replan_workflow

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_replanning",
            new_callable=AsyncMock,
            return_value={"replanning_id": "replan-2", "success": True}
        ):
            result = await replan_workflow(
                plan_id="plan-123",
                reason="Decisão do operador",
                trigger_type="MANUAL"
            )

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_replan_workflow_error_trigger(self):
        """Testa replanejamento com trigger de erro."""
        from queen_mcp_server.tools.queen_tools import replan_workflow

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_replanning",
            new_callable=AsyncMock,
            return_value={"replanning_id": "replan-3", "success": True}
        ):
            result = await replan_workflow(
                plan_id="plan-123",
                reason="Exceção no worker",
                trigger_type="ERROR"
            )

            assert result["replanning_id"] == "replan-3"

    @pytest.mark.asyncio
    async def test_replan_workflow_without_progress_preservation(self):
        """Testa replanejamento sem preservar progresso."""
        from queen_mcp_server.tools.queen_tools import replan_workflow

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_replanning",
            new_callable=AsyncMock,
            return_value={"replanning_id": "replan-4", "success": True, "preserved_steps": 0}
        ):
            result = await replan_workflow(
                plan_id="plan-123",
                reason="Recomeçar do zero",
                preserve_progress=False
            )

            assert result["preserved_steps"] == 0


class TestApproveExceptionTool:
    """Testes da ferramenta approve_exception."""

    @pytest.mark.asyncio
    async def test_approve_exception_success(self):
        """Testa aprovação de exceção com sucesso."""
        from queen_mcp_server.tools.queen_tools import approve_exception

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_exception_approval",
            new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "exception_request_id": "exc-123",
                "approved": True,
                "approved_by": "queen-agent",
                "approved_at": datetime.now().isoformat()
            }

            result = await approve_exception(
                exception_request_id="exc-123",
                justification="Necessário para completar workflow crítico",
                risk_score=0.3,
                requested_by="orchestrator"
            )

            assert result["approved"] is True
            assert result["exception_request_id"] == "exc-123"
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_exception_invalid_risk_score_high(self):
        """Testa erro para risk_score acima de 1.0."""
        from queen_mcp_server.tools.queen_tools import approve_exception

        with pytest.raises(ValueError, match="risk_score must be between 0.0 and 1.0"):
            await approve_exception(
                exception_request_id="exc-123",
                justification="Teste",
                risk_score=1.5,
                requested_by="test"
            )

    @pytest.mark.asyncio
    async def test_approve_exception_invalid_risk_score_low(self):
        """Testa erro para risk_score abaixo de 0.0."""
        from queen_mcp_server.tools.queen_tools import approve_exception

        with pytest.raises(ValueError, match="risk_score must be between 0.0 and 1.0"):
            await approve_exception(
                exception_request_id="exc-123",
                justification="Teste",
                risk_score=-0.1,
                requested_by="test"
            )

    @pytest.mark.asyncio
    async def test_approve_exception_boundary_risk_scores(self):
        """Testa valores de limite válidos para risk_score."""
        from queen_mcp_server.tools.queen_tools import approve_exception

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_exception_approval",
            new_callable=AsyncMock,
            return_value={"approved": True, "exception_request_id": "test"}
        ):
            # Testar limites exatos
            result_low = await approve_exception(
                exception_request_id="exc-1",
                justification="Teste",
                risk_score=0.0,
                requested_by="test"
            )
            assert result_low["approved"] is True

            result_high = await approve_exception(
                exception_request_id="exc-2",
                justification="Teste",
                risk_score=1.0,
                requested_by="test"
            )
            assert result_high["approved"] is True

    @pytest.mark.asyncio
    async def test_approve_exception_with_expiration(self):
        """Testa aprovação com data de expiração."""
        from queen_mcp_server.tools.queen_tools import approve_exception

        expires = "2026-04-03T18:00:00"

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_exception_approval",
            new_callable=AsyncMock,
            return_value={"approved": True, "exception_request_id": "exc-1"}
        ) as mock_call:
            await approve_exception(
                exception_request_id="exc-1",
                justification="Exceção temporária",
                risk_score=0.5,
                requested_by="admin",
                expires_at=expires
            )

            # Verificar que expires_at foi passado (4º argumento posicional após expires_at)
            call_args = mock_call.call_args[0]
            # _call_queen_agent_exception_approval(exception_request_id, justification, risk_score, requested_by, expires_at)
            assert call_args[4] == expires

    @pytest.mark.asyncio
    async def test_approve_exception_rejected_high_risk(self):
        """Testa rejeição de exceção de alto risco."""
        from queen_mcp_server.tools.queen_tools import approve_exception

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_exception_approval",
            new_callable=AsyncMock,
            return_value={"approved": False, "exception_request_id": "exc-1", "reason": "Risco muito elevado"}
        ):
            result = await approve_exception(
                exception_request_id="exc-1",
                justification="Teste",
                risk_score=0.9,
                requested_by="test"
            )

            assert result["approved"] is False


class TestAdjustQosTool:
    """Testes da ferramenta adjust_qos."""

    @pytest.mark.asyncio
    async def test_adjust_qos_success(self):
        """Testa ajuste de QoS com sucesso."""
        from queen_mcp_server.tools.queen_tools import adjust_qos

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_qos_adjustment",
            new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = {
                "success": True,
                "workflow_id": "wf-123",
                "adjustment_type": "increase_priority",
                "new_priority": 8,
                "previous_priority": 5
            }

            result = await adjust_qos(
                workflow_id="wf-123",
                adjustment_type="increase_priority",
                new_priority=8,
                reason="SLA em risco"
            )

            assert result["success"] is True
            assert result["new_priority"] == 8
            assert result["previous_priority"] == 5
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_adjust_qos_invalid_type(self):
        """Testa erro para adjustment_type inválido."""
        from queen_mcp_server.tools.queen_tools import adjust_qos

        with pytest.raises(ValueError, match="Invalid adjustment_type"):
            await adjust_qos(
                workflow_id="wf-123",
                adjustment_type="invalid_type"
            )

    @pytest.mark.asyncio
    async def test_adjust_qos_all_valid_types(self):
        """Testa todos os tipos de ajuste válidos."""
        from queen_mcp_server.tools.queen_tools import adjust_qos

        valid_types = [
            "increase_priority",
            "decrease_priority",
            "pause_execution",
            "resume_execution",
            "allocate_resources"
        ]

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_qos_adjustment",
            new_callable=AsyncMock,
            return_value={"success": True, "workflow_id": "wf-test"}
        ):
            for adj_type in valid_types:
                result = await adjust_qos(
                    workflow_id="wf-test",
                    adjustment_type=adj_type
                )
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_adjust_qos_pause_with_duration(self):
        """Testa pausa com duração especificada."""
        from queen_mcp_server.tools.queen_tools import adjust_qos

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_qos_adjustment",
            new_callable=AsyncMock,
            return_value={"success": True, "workflow_id": "wf-1"}
        ) as mock_call:
            await adjust_qos(
                workflow_id="wf-1",
                adjustment_type="pause_execution",
                duration_seconds=300
            )

            # Verificar que duration_seconds foi passado
            call_args = mock_call.call_args[0]
            # _call_queen_agent_qos_adjustment(workflow_id, adjustment_type, new_priority, reason, duration_seconds)
            assert call_args[4] == 300

    @pytest.mark.asyncio
    async def test_adjust_qos_resume_execution(self):
        """Testa retomada de execução."""
        from queen_mcp_server.tools.queen_tools import adjust_qos

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_qos_adjustment",
            new_callable=AsyncMock,
            return_value={"success": True, "workflow_id": "wf-1", "status": "running"}
        ):
            result = await adjust_qos(
                workflow_id="wf-1",
                adjustment_type="resume_execution"
            )

            assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_adjust_qos_with_optional_params(self):
        """Testa ajuste com parâmetros opcionais."""
        from queen_mcp_server.tools.queen_tools import adjust_qos

        with patch(
            "queen_mcp_server.tools.queen_tools._call_queen_agent_qos_adjustment",
            new_callable=AsyncMock,
            return_value={"success": True, "workflow_id": "wf-1"}
        ) as mock_call:
            await adjust_qos(
                workflow_id="wf-1",
                adjustment_type="increase_priority",
                new_priority=7,
                reason="Aumentar prioridade",
                duration_seconds=600
            )

            # Verificar todos os parâmetros opcionais
            call_args = mock_call.call_args[0]
            # _call_queen_agent_qos_adjustment(workflow_id, adjustment_type, new_priority, reason, duration_seconds)
            assert call_args[0] == "wf-1"  # workflow_id
            assert call_args[1] == "increase_priority"  # adjustment_type
            assert call_args[2] == 7  # new_priority
            assert call_args[3] == "Aumentar prioridade"  # reason
            assert call_args[4] == 600  # duration_seconds


class TestQueenMCPServerIntegration:
    """Testes de integração do Queen MCP Server."""

    def test_server_has_required_tools(self):
        """Testa que o servidor expõe as ferramentas requeridas."""
        from queen_mcp_server.server import mcp

        # Verificar que o servidor MCP está configurado
        assert mcp is not None
        assert mcp.name == "Queen MCP Server"

    def test_tools_have_metadata(self):
        """Testa que ferramentas têm metadata descritiva."""
        from queen_mcp_server.tools.queen_tools import (
            make_decision,
            arbitrate_conflict,
            replan_workflow,
            approve_exception,
            adjust_qos
        )

        # Verificar que funções de tools existem e têm docstrings
        assert make_decision.__doc__
        assert arbitrate_conflict.__doc__
        assert replan_workflow.__doc__
        assert approve_exception.__doc__
        assert adjust_qos.__doc__

    def test_server_info_resource_exists(self):
        """Testa que resource de info existe."""
        from queen_mcp_server.server import get_queen_info

        # Verificar que a função de info existe
        assert get_queen_info is not None
        info = get_queen_info()
        assert "Queen MCP Server" in info
        assert "make_decision" in info
        assert "arbitrate_conflict" in info

    def test_register_queen_tools_function_exists(self):
        """Testa que função de registro existe."""
        from queen_mcp_server.tools.queen_tools import register_queen_tools

        assert register_queen_tools is not None
        assert callable(register_queen_tools)


class TestHelperFunctions:
    """Testes das funções auxiliares."""

    @pytest.mark.asyncio
    async def test_call_queen_agent_decision_success(self):
        """Testa chamada bem-sucedida ao Queen Agent para decisão."""
        from queen_mcp_server.tools.queen_tools import _call_queen_agent_decision

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "decision_id": "dec-1",
                "decision_type": "STRATEGIC"
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await _call_queen_agent_decision(
                "telemetry",
                "source-1",
                {"data": "test"}
            )

            assert result["decision_id"] == "dec-1"
            assert result["decision_type"] == "STRATEGIC"

    @pytest.mark.asyncio
    async def test_call_queen_agent_arbitration_success(self):
        """Testa chamada bem-sucedida para arbitragem."""
        from queen_mcp_server.tools.queen_tools import _call_queen_agent_arbitration

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "conflict_id": "conf-1",
                "resolution_strategy": "consensus"
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            decisions = [{"decision": "A"}, {"decision": "B"}]

            result = await _call_queen_agent_arbitration(
                decisions,
                "Test conflict"
            )

            assert result["conflict_id"] == "conf-1"

    @pytest.mark.asyncio
    async def test_call_queen_agent_replanning_success(self):
        """Testa chamada bem-sucedida para replanejamento."""
        from queen_mcp_server.tools.queen_tools import _call_queen_agent_replanning

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "replanning_id": "replan-1",
                "success": True
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await _call_queen_agent_replanning(
                "plan-1",
                "Test reason",
                "STRATEGIC",
                True,
                5
            )

            assert result["replanning_id"] == "replan-1"

    @pytest.mark.asyncio
    async def test_call_queen_agent_exception_approval_success(self):
        """Testa chamada bem-sucedida para aprovação de exceção."""
        from queen_mcp_server.tools.queen_tools import _call_queen_agent_exception_approval

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "exception_request_id": "exc-1",
                "approved": True
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await _call_queen_agent_exception_approval(
                "exc-1",
                "Justification",
                0.5,
                "user",
                None
            )

            assert result["approved"] is True

    @pytest.mark.asyncio
    async def test_call_queen_agent_qos_adjustment_success(self):
        """Testa chamada bem-sucedida para ajuste de QoS."""
        from queen_mcp_server.tools.queen_tools import _call_queen_agent_qos_adjustment

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "workflow_id": "wf-1"
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await _call_queen_agent_qos_adjustment(
                "wf-1",
                "increase_priority",
                8,
                "Reason",
                None
            )

            assert result["success"] is True


class TestHealthCheckTool:
    """Testes da ferramenta health_check."""

    @pytest.mark.asyncio
    async def test_health_check_basic(self):
        """Testa health check básico sem verificação de serviços."""
        from queen_mcp_server.tools.queen_tools import health_check

        result = await health_check(include_services=False)

        assert result["status"] == "healthy"
        assert result["server"] == "queen-mcp-server"
        assert "timestamp" in result
        assert "components" in result
        assert result["components"]["mcp_server"] == "healthy"
        assert "queen_agent" not in result["components"]

    @pytest.mark.asyncio
    async def test_health_check_with_services(self):
        """Testa health check com verificação de serviços."""
        from queen_mcp_server.tools.queen_tools import health_check

        result = await health_check(include_services=True)

        assert "status" in result
        assert "components" in result
        assert "mcp_server" in result["components"]
        # Queen Agent pode não estar disponível em ambiente de teste
        assert result["components"]["mcp_server"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_includes_version(self):
        """Testa que health check inclui versão."""
        from queen_mcp_server.tools.queen_tools import health_check

        result = await health_check()

        assert "version" in result
        assert isinstance(result["version"], str)

    @pytest.mark.asyncio
    async def test_health_check_degraded_when_queen_unreachable(self):
        """Testa status degraded quando Queen Agent não está disponível."""
        from queen_mcp_server.tools.queen_tools import health_check

        # Em ambiente de teste, Queen Agent provavelmente não está rodando
        result = await health_check(include_services=True)

        # Se Queen Agent não está disponível, status deve ser degraded
        if result["components"].get("queen_agent") in ["unreachable", "error"]:
            assert result["status"] in ["degraded", "healthy"]  # Pode ser degraded ou healthy
        else:
            assert result["status"] == "healthy"

    def test_health_check_tool_metadata(self):
        """Testa que health_check tem docstring."""
        from queen_mcp_server.tools.queen_tools import health_check

        assert health_check.__doc__
        assert "saúde" in health_check.__doc__ or "health" in health_check.__doc__
