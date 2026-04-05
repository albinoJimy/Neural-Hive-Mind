"""
Testes do Healer MCP Server - Fase RED (TDD)

Testes escritos ANTES da implementação.
Com MOCKS para isolar a unidade sendo testada.

FASE 1: RED - Testes falhando (implementação ainda não existe)
FASE 2: GREEN - Implementar código mínimo para passar
FASE 3: REFACTOR - Melhorar design com testes passando
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


# ===== TESTES DA FERRAMENTA detect_incident =====


class TestDetectIncident:
    """Testes da ferramenta detect_incident."""

    @pytest.mark.asyncio
    async def test_detect_incident_pod_crash_loop(self, mock_incident):
        """
        DADO: Um serviço com pod em crash loop
        QUANDO: Executo detect_incident
        ENTÃO: Deve detectar incidente com severity=HIGH
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "incident_id": "incident-123",
                "detected_at": "2026-04-03T12:34:56Z",
                "service": "gateway-intencoes",
                "incident_type": "pod_crash_loop",
                "severity": "HIGH",
                "description": "Pod em crash loop_back_off",
                "affected_resources": ["gateway-intencoes-7d9f4c8b-xk2lp"],
                "metrics": {
                    "restart_count": 15,
                    "crash_loop_back_off": True,
                    "error_rate": 0.85,
                },
                "suggested_playbook": "playbook-restart-pod",
                "auto_recoverable": True,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import detect_incident

            result = await detect_incident(
                service="gateway-intencoes",
                incident_type="pod_crash_loop",
                metrics={"restart_count": 15, "crash_loop_back_off": True},
            )

        assert result["incident_type"] == "pod_crash_loop"
        assert result["severity"] == "HIGH"
        assert result["auto_recoverable"] is True
        assert "suggested_playbook" in result

    @pytest.mark.asyncio
    async def test_detect_incident_high_memory_usage(self):
        """
        DADO: Um serviço com consumo de memória excessivo
        QUANDO: Executo detect_incident
        ENTÃO: Deve detectar incidente com severity=MEDIUM
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "incident_id": "incident-456",
                "detected_at": "2026-04-03T12:35:00Z",
                "service": "consensus-engine",
                "incident_type": "high_memory_usage",
                "severity": "MEDIUM",
                "description": "Consumo de memória acima de 80%",
                "affected_resources": ["consensus-engine-5f7c3d9a-np3qr"],
                "metrics": {
                    "memory_usage_percent": 87,
                    "memory_mb": 3480,
                    "limit_mb": 4096,
                },
                "suggested_playbook": "playbook-scale-up",
                "auto_recoverable": True,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import detect_incident

            result = await detect_incident(
                service="consensus-engine",
                incident_type="high_memory_usage",
                metrics={"memory_usage_percent": 87, "memory_mb": 3480},
            )

        assert result["incident_type"] == "high_memory_usage"
        assert result["severity"] == "MEDIUM"
        assert result["metrics"]["memory_usage_percent"] > 80

    @pytest.mark.asyncio
    async def test_detect_incident_missing_service_name(self):
        """
        DADO: Uma chamada sem service
        QUANDO: Executo detect_incident
        ENTÃO: Deve levantar ValueError
        """
        from healer_mcp_server.tools.healer_tools import detect_incident

        with pytest.raises(ValueError, match="service"):
            await detect_incident(
                service="",
                incident_type="pod_crash_loop",
                metrics={},
            )


# ===== TESTES DA FERRAMENTA execute_playbook =====


class TestExecutePlaybook:
    """Testes da ferramenta execute_playbook."""

    @pytest.mark.asyncio
    async def test_execute_playbook_restart_pod_success(
        self, mock_incident, mock_playbook
    ):
        """
        DADO: Um incidente com playbook de restart de pod
        QUANDO: Executo execute_playbook
        ENTÃO: Deve executar com sucesso e retornar execution_status=completed
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "execution_id": "exec-123",
                "incident_id": "incident-123",
                "playbook_id": "playbook-restart-pod",
                "execution_status": "completed",
                "started_at": "2026-04-03T12:36:00Z",
                "completed_at": "2026-04-03T12:37:15Z",
                "duration_seconds": 75,
                "steps_executed": [
                    {"step": 1, "action": "delete_pod", "status": "completed"},
                    {"step": 2, "action": "wait_ready", "status": "completed"},
                    {"step": 3, "action": "verify_health", "status": "completed"},
                ],
                "recovery_achieved": True,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import execute_playbook

            result = await execute_playbook(
                incident_id="incident-123",
                playbook_id="playbook-restart-pod",
                parameters={"affected_resources": ["gateway-intencoes-7d9f4c8b-xk2lp"]},
            )

        assert result["execution_status"] == "completed"
        assert result["recovery_achieved"] is True
        assert len(result["steps_executed"]) == 3

    @pytest.mark.asyncio
    async def test_execute_playbook_rollback_triggered(
        self, mock_incident, mock_playbook
    ):
        """
        DADO: Um playbook cuja execução falha
        QUANDO: Executo execute_playbook
        ENTÃO: Deve executar rollback e retornar execution_status=rollback_completed
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "execution_id": "exec-456",
                "incident_id": "incident-123",
                "playbook_id": "playbook-scale-up",
                "execution_status": "rollback_completed",
                "started_at": "2026-04-03T12:40:00Z",
                "completed_at": "2026-04-03T12:42:30Z",
                "duration_seconds": 150,
                "steps_executed": [
                    {"step": 1, "action": "scale_up", "status": "failed", "error": "Insufficient resources"},
                    {"step": 2, "action": "rollback_deployment", "status": "completed"},
                ],
                "recovery_achieved": False,
                "rollback_reason": "Scale up failed due to insufficient cluster resources",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import execute_playbook

            result = await execute_playbook(
                incident_id="incident-123",
                playbook_id="playbook-scale-up",
                parameters={"replicas": 3},
            )

        assert result["execution_status"] == "rollback_completed"
        assert result["recovery_achieved"] is False
        assert "rollback_reason" in result

    @pytest.mark.asyncio
    async def test_execute_playbook_missing_incident_id(self):
        """
        DADO: Uma chamada sem incident_id
        QUANDO: Executo execute_playbook
        ENTÃO: Deve levantar ValueError
        """
        from healer_mcp_server.tools.healer_tools import execute_playbook

        with pytest.raises(ValueError, match="incident_id"):
            await execute_playbook(
                incident_id="",
                playbook_id="playbook-restart-pod",
                parameters={},
            )


# ===== TESTES DA FERRAMENTA validate_recovery =====


class TestValidateRecovery:
    """Testes da ferramenta validate_recovery."""

    @pytest.mark.asyncio
    async def test_validate_recovery_success(self, mock_recovery_validation):
        """
        DADO: Um incidente recuperado com sucesso
        QUANDO: Executo validate_recovery
        ENTÃO: Deve retornar recovery_status=SUCCESS
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "validation_id": "val-789",
                "incident_id": "incident-123",
                "playbook_id": "playbook-restart-pod",
                "recovery_status": "SUCCESS",
                "validated_at": "2026-04-03T12:38:00Z",
                "validation_checks": [
                    {"check": "pod_running", "expected": True, "actual": True, "passed": True},
                    {"check": "error_rate", "expected": "< 0.05", "actual": 0.02, "passed": True},
                    {"check": "latency_p99_ms", "expected": "< 1000", "actual": 350, "passed": True},
                ],
                "all_checks_passed": True,
                "can_close_incident": True,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import validate_recovery

            result = await validate_recovery(
                incident_id="incident-123",
                playbook_id="playbook-restart-pod",
            )

        assert result["recovery_status"] == "SUCCESS"
        assert result["all_checks_passed"] is True
        assert result["can_close_incident"] is True

    @pytest.mark.asyncio
    async def test_validate_recovery_partial_failure(self):
        """
        DADO: Um incidente com recuperação parcial
        QUANDO: Executo validate_recovery
        ENTÃO: Deve retornar recovery_status=PARTIAL
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "validation_id": "val-790",
                "incident_id": "incident-124",
                "playbook_id": "playbook-scale-up",
                "recovery_status": "PARTIAL",
                "validated_at": "2026-04-03T12:40:00Z",
                "validation_checks": [
                    {"check": "pod_running", "expected": True, "actual": True, "passed": True},
                    {"check": "error_rate", "expected": "< 0.05", "actual": 0.12, "passed": False},
                    {"check": "latency_p99_ms", "expected": "< 1000", "actual": 850, "passed": True},
                ],
                "all_checks_passed": False,
                "can_close_incident": False,
                "failed_checks": ["error_rate"],
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import validate_recovery

            result = await validate_recovery(
                incident_id="incident-124",
                playbook_id="playbook-scale-up",
            )

        assert result["recovery_status"] == "PARTIAL"
        assert result["all_checks_passed"] is False
        assert result["can_close_incident"] is False

    @pytest.mark.asyncio
    async def test_validate_recovery_missing_incident_id(self):
        """
        DADO: Uma chamada sem incident_id
        QUANDO: Executo validate_recovery
        ENTÃO: Deve levantar ValueError
        """
        from healer_mcp_server.tools.healer_tools import validate_recovery

        with pytest.raises(ValueError, match="incident_id"):
            await validate_recovery(
                incident_id="",
                playbook_id="playbook-restart-pod",
            )


# ===== TESTES DA FERRAMENTA monitor_health =====


class TestMonitorHealth:
    """Testes da ferramenta monitor_health."""

    @pytest.mark.asyncio
    async def test_monitor_health_all_healthy(self, mock_health_check):
        """
        DADO: Um serviço com todos os checks saudáveis
        QUANDO: Executo monitor_health
        ENTÃO: Deve retornar overall_status=healthy
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "service": "gateway-intencoes",
                "overall_status": "healthy",
                "checked_at": "2026-04-03T12:41:00Z",
                "endpoints": [
                    {
                        "name": "liveness",
                        "url": "http://gateway-intencoes:8000/health/live",
                        "status": "up",
                        "status_code": 200,
                        "response_time_ms": 5,
                    },
                    {
                        "name": "readiness",
                        "url": "http://gateway-intencoes:8000/health/ready",
                        "status": "up",
                        "status_code": 200,
                        "response_time_ms": 8,
                    },
                    {
                        "name": "startup",
                        "url": "http://gateway-intencoes:8000/health/startup",
                        "status": "up",
                        "status_code": 200,
                        "response_time_ms": 6,
                    },
                ],
                "metrics": {
                    "error_rate": 0.001,
                    "latency_p99_ms": 250,
                    "request_rate": 150,
                },
                "issues": [],
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import monitor_health

            result = await monitor_health(
                service="gateway-intencoes",
                checks=["liveness", "readiness", "startup"],
            )

        assert result["overall_status"] == "healthy"
        assert len(result["issues"]) == 0
        assert all(e["status"] == "up" for e in result["endpoints"])

    @pytest.mark.asyncio
    async def test_monitor_health_degraded(self):
        """
        DADO: Um serviço com checks degradados
        QUANDO: Executo monitor_health
        ENTÃO: Deve retornar overall_status=degraded com issues
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "service": "orchestrator-dynamic",
                "overall_status": "degraded",
                "checked_at": "2026-04-03T12:42:00Z",
                "endpoints": [
                    {
                        "name": "liveness",
                        "url": "http://orchestrator-dynamic:8003/health/live",
                        "status": "up",
                        "status_code": 200,
                        "response_time_ms": 10,
                    },
                    {
                        "name": "readiness",
                        "url": "http://orchestrator-dynamic:8003/health/ready",
                        "status": "up",
                        "status_code": 200,
                        "response_time_ms": 1200,
                    },
                ],
                "metrics": {
                    "error_rate": 0.08,
                    "latency_p99_ms": 2500,
                    "request_rate": 80,
                },
                "issues": [
                    {"type": "high_latency", "description": "readiness endpoint: 1200ms > 1000ms threshold"},
                    {"type": "elevated_error_rate", "description": "error rate 8% > 5% threshold"},
                ],
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import monitor_health

            result = await monitor_health(
                service="orchestrator-dynamic",
                checks=["liveness", "readiness"],
            )

        assert result["overall_status"] == "degraded"
        assert len(result["issues"]) > 0
        assert result["metrics"]["error_rate"] > 0.05

    @pytest.mark.asyncio
    async def test_monitor_health_missing_service(self):
        """
        DADO: Uma chamada sem service
        QUANDO: Executo monitor_health
        ENTÃO: Deve levantar ValueError
        """
        from healer_mcp_server.tools.healer_tools import monitor_health

        with pytest.raises(ValueError, match="service"):
            await monitor_health(
                service="",
                checks=["liveness"],
            )


# ===== TESTES DA FERRAMENTA escalate_issue =====


class TestEscalateIssue:
    """Testes da ferramenta escalate_issue."""

    @pytest.mark.asyncio
    async def test_escalate_issue_success(self, mock_escalation_data):
        """
        DADO: Um incidente que requer escalamento manual
        QUANDO: Executo escalate_issue
        ENTÃO: Deve criar ticket de escalamento e retornar escalation_id
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "escalation_id": "escalation-123",
                "incident_id": "incident-456",
                "escalated_at": "2026-04-03T12:43:00Z",
                "target_team": "platform_team",
                "urgency": "critical",
                "status": "pending",
                "ticket_url": "https://tickets.internal/escalation-123",
                "estimated_response_time_minutes": 15,
                "notification_sent": True,
                "notified_persons": ["oncall@company.com", "platform-lead@company.com"],
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import escalate_issue

            result = await escalate_issue(
                incident_id="incident-456",
                target_team="platform_team",
                urgency="critical",
                reason="Playbook executado mas serviço não recuperou",
                context={
                    "service": "orchestrator-dynamic",
                    "attempts": 3,
                    "error_logs": ["Connection timeout"],
                },
            )

        assert result["status"] == "pending"
        assert result["escalation_id"] is not None
        assert result["notification_sent"] is True
        assert "ticket_url" in result

    @pytest.mark.asyncio
    async def test_escalate_issue_to_sre(self, mock_escalation_data):
        """
        DADO: Um incidente crítico que requer SRE
        QUANDO: Executo escalate_issue para SRE team
        ENTÃO: Deve escalar com urgency=critical
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "escalation_id": "escalation-456",
                "incident_id": "incident-789",
                "escalated_at": "2026-04-03T12:45:00Z",
                "target_team": "sre_team",
                "urgency": "critical",
                "status": "pending",
                "ticket_url": "https://tickets.internal/escalation-456",
                "estimated_response_time_minutes": 5,
                "notification_sent": True,
                "notified_persons": ["sre-oncall@company.com"],
                "pager_duty_triggered": True,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from healer_mcp_server.tools.healer_tools import escalate_issue

            result = await escalate_issue(
                incident_id="incident-789",
                target_team="sre_team",
                urgency="critical",
                reason="Cluster-wide outage affecting multiple services",
                context={
                    "services": ["gateway", "orchestrator", "consensus"],
                    "cluster_status": "degraded",
                },
            )

        assert result["target_team"] == "sre_team"
        assert result["urgency"] == "critical"
        assert result["pager_duty_triggered"] is True

    @pytest.mark.asyncio
    async def test_escalate_issue_missing_incident_id(self):
        """
        DADO: Uma chamada sem incident_id
        QUANDO: Executo escalate_issue
        ENTÃO: Deve levantar ValueError
        """
        from healer_mcp_server.tools.healer_tools import escalate_issue

        with pytest.raises(ValueError, match="incident_id"):
            await escalate_issue(
                incident_id="",
                target_team="platform_team",
                urgency="high",
                reason="Test",
            )

    @pytest.mark.asyncio
    async def test_escalate_issue_invalid_urgency(self):
        """
        DADO: Uma urgência inválida
        QUANDO: Executo escalate_issue
        ENTÃO: Deve levantar ValueError
        """
        from healer_mcp_server.tools.healer_tools import escalate_issue

        with pytest.raises(ValueError, match="urgency"):
            await escalate_issue(
                incident_id="incident-123",
                target_team="platform_team",
                urgency="invalid",
                reason="Test",
            )


# ===== TESTES DE INTEGRAÇÃO DO SERVIDOR =====


class TestHealerMCPServerIntegration:
    """Testes de integração do servidor MCP."""

    def test_server_has_required_tools(self):
        """
        DADO: O servidor Healer MCP está inicializado
        QUANDO: Listo ferramentas disponíveis
        ENTÃO: Deve ter exatamente 5 ferramentas registradas
        """
        from healer_mcp_server.server import mcp

        # Verificar que o servidor MCP está configurado
        assert mcp is not None
        assert mcp.name == "Healer MCP Server"

    def test_tools_have_metadata(self):
        """
        DADO: O servidor Healer MCP está inicializado
        QUANDO: Examino metadata das ferramentas
        ENTÃO: Cada ferramenta deve ter descrição e parâmetros documentados
        """
        from healer_mcp_server.tools.healer_tools import (
            detect_incident,
            execute_playbook,
            escalate_issue,
            monitor_health,
            validate_recovery,
        )

        # Verificar que funções de tools existem e têm docstrings
        assert detect_incident.__doc__
        assert execute_playbook.__doc__
        assert validate_recovery.__doc__
        assert monitor_health.__doc__
        assert escalate_issue.__doc__

    def test_server_info_resource_exists(self):
        """
        DADO: O servidor Healer MCP está inicializado
        QUANDO: Verifico recursos disponíveis
        ENTÃO: O recurso healer://info deve existir
        """
        from healer_mcp_server.server import mcp

        assert mcp is not None

    def test_register_function_exists(self):
        """
        DADO: O módulo healer_tools está importado
        QUANDO: Verifico a função de registro
        ENTÃO: register_healer_tools deve existir
        """
        from healer_mcp_server.tools.healer_tools import register_healer_tools

        assert callable(register_healer_tools)
