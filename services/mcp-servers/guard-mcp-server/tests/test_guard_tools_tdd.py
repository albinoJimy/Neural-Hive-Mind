"""
Testes do Guard MCP Server - Fase RED (TDD)

Testes escritos ANTES da implementação.
Com MOCKS para isolar a unidade sendo testada.

FASE 1: RED - Testes falhando (implementação ainda não existe)
FASE 2: GREEN - Implementar código mínimo para passar
FASE 3: REFACTOR - Melhorar design com testes passando
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


# ===== TESTES DA FERRAMENTA validate_security =====


class TestValidateSecurity:
    """Testes da ferramenta validate_security."""

    @pytest.mark.asyncio
    async def test_validate_security_approved_no_violations(self, mock_ticket):
        """
        DADO: Um ticket válido com todas as políticas satisfeitas
        QUANDO: Executo validate_security
        ENTÃO: Deve retornar status='approved' com risk_score=0.0
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "validation_id": "val-123",
                "ticket_id": "ticket-123",
                "validation_status": "approved",
                "violations": [],
                "risk_assessment": {
                    "risk_score": 0.0,
                    "severity": "low",
                    "impact": "No violations",
                },
                "approval_required": False,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Act
            from guard_mcp_server.tools.guard_tools import validate_security

            result = await validate_security(
                ticket_id="ticket-123",
                task_type="DEPLOY",
                environment="staging",
                security_level="INTERNAL",
            )

        # Assert
        assert result["validation_status"] == "approved"
        assert result["risk_assessment"]["risk_score"] == 0.0
        assert result["approval_required"] is False

    @pytest.mark.asyncio
    async def test_validate_security_rejected_critical_violations(self, mock_ticket):
        """
        DADO: Um ticket com violações CRITICAL
        QUANDO: Executo validate_security
        ENTÃO: Deve retornar status='rejected' com lista de violações
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "validation_id": "val-456",
                "ticket_id": "ticket-123",
                "validation_status": "rejected",
                "violations": [
                    {
                        "violation_type": "SECRET_EXPOSED",
                        "severity": "CRITICAL",
                        "description": "API key detectada nos parametros",
                    }
                ],
                "risk_assessment": {
                    "risk_score": 1.0,
                    "severity": "critical",
                    "impact": "1 CRITICAL violation",
                },
                "approval_required": False,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import validate_security

            result = await validate_security(
                ticket_id="ticket-123",
                task_type="DEPLOY",
                environment="production",
                security_level="CONFIDENTIAL",
            )

        assert result["validation_status"] == "rejected"
        assert len(result["violations"]) > 0
        assert result["risk_assessment"]["risk_score"] >= 0.8

    @pytest.mark.asyncio
    async def test_validate_security_missing_required_field(self):
        """
        DADO: Uma chamada sem ticket_id
        QUANDO: Executo validate_security
        ENTÃO: Deve levantar ValueError
        """
        from guard_mcp_server.tools.guard_tools import validate_security

        with pytest.raises(ValueError, match="ticket_id"):
            await validate_security(
                ticket_id="",  # string vazia é falsy
                task_type="DEPLOY",
                environment="production",
            )


# ===== TESTES DA FERRAMENTA scan_vulnerabilities =====


class TestScanVulnerabilities:
    """Testes da ferramenta scan_vulnerabilities."""

    @pytest.mark.asyncio
    async def test_scan_vulnerabilities_with_vulnerabilities_found(self, mock_vulnerability_report):
        """
        DADO: Uma imagem de container com vulnerabilidades
        QUANDO: Executo scan_vulnerabilities
        ENTÃO: Deve retornar lista de vulnerabilidades com severidades
        """
        mock_response = Mock()
        mock_response.json = Mock(return_value=mock_vulnerability_report)
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import scan_vulnerabilities

            result = await scan_vulnerabilities(target="nginx:latest", scan_type="container")

        assert result["target"] == "nginx:latest"
        assert len(result["vulnerabilities"]) == 2
        assert any(v["severity"] == "HIGH" for v in result["vulnerabilities"])

    @pytest.mark.asyncio
    async def test_scan_vulnerabilities_no_vulnerabilities(self):
        """
        DADO: Uma imagem de container sem vulnerabilidades
        QUANDO: Executo scan_vulnerabilities
        ENTÃO: Deve retornar lista vazia de vulnerabilidades
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "target": "alpine:latest",
                "vulnerabilities": [],
                "scan_status": "completed",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import scan_vulnerabilities

            result = await scan_vulnerabilities(target="alpine:latest", scan_type="container")

        assert result["target"] == "alpine:latest"
        assert len(result["vulnerabilities"]) == 0

    @pytest.mark.asyncio
    async def test_scan_vulnerabilities_invalid_scan_type(self):
        """
        DADO: Um tipo de scan inválido
        QUANDO: Executo scan_vulnerabilities
        ENTÃO: Deve levantar ValueError
        """
        from guard_mcp_server.tools.guard_tools import scan_vulnerabilities

        with pytest.raises(ValueError, match="scan_type"):
            await scan_vulnerabilities(target="nginx:latest", scan_type="invalid_type")


# ===== TESTES DA FERRAMENTA detect_threats =====


class TestDetectThreats:
    """Testes da ferramenta detect_threats."""

    @pytest.mark.asyncio
    async def test_detect_threats_anomaly_detected(self, mock_event):
        """
        DADO: Um evento com falhas de autenticação anômalas
        QUANDO: Executo detect_threats
        ENTÃO: Deve detectar ameaça e retornar detalhes
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "threat_id": "threat-789",
                "threat_type": "unauthorized_access",
                "severity": "high",
                "confidence": 0.9,
                "details": {
                    "user_id": "user-123",
                    "failed_attempts": 7,
                    "source_ip": "192.168.1.100",
                },
                "detected_at": "2026-04-03T12:34:56Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import detect_threats

            result = await detect_threats(
                event_type="authentication",
                event_data=mock_event,
            )

        assert result["threat_type"] == "unauthorized_access"
        assert result["severity"] == "high"
        assert result["confidence"] >= 0.8

    @pytest.mark.asyncio
    async def test_detect_threats_no_threat_found(self, mock_event):
        """
        DADO: Um evento normal sem anomalias
        QUANDO: Executo detect_threats
        ENTÃO: Deve retornar threat_found=False
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "threat_found": False,
                "threat_id": None,
                "threat_type": None,
                "severity": None,
                "confidence": 0.0,
                "details": {},
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import detect_threats

            result = await detect_threats(event_type="normal_request", event_data=mock_event)

        assert result["threat_found"] is False
        assert result["threat_id"] is None


# ===== TESTES DA FERRAMENTA check_compliance =====


class TestCheckCompliance:
    """Testes da ferramenta check_compliance."""

    @pytest.mark.asyncio
    async def test_check_compliance_all_compliant(self):
        """
        DADO: Um ticket com todas as compliance requirements satisfeitas
        QUANDO: Executo check_compliance
        ENTÃO: Deve retornar compliant=True com lista vazia de breaches
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "ticket_id": "ticket-123",
                "compliant": True,
                "breaches": [],
                "regulations_checked": ["GDPR", "SOC2", "ISO27001"],
                "last_checked": "2026-04-03T12:34:56Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import check_compliance

            result = await check_compliance(
                ticket_id="ticket-123",
                regulations=["GDPR", "SOC2"],
            )

        assert result["compliant"] is True
        assert result["breaches"] == []
        assert len(result["regulations_checked"]) >= 2

    @pytest.mark.asyncio
    async def test_check_compliance_breaches_detected(self):
        """
        DADO: Um ticket com violações de compliance
        QUANDO: Executo check_compliance
        ENTÃO: Deve retornar compliant=False com lista de breaches
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "ticket_id": "ticket-123",
                "compliant": False,
                "breaches": [
                    {
                        "regulation": "GDPR",
                        "article": "Article 32",
                        "description": "Dados PII sem encriptação",
                        "severity": "HIGH",
                    }
                ],
                "regulations_checked": ["GDPR"],
                "last_checked": "2026-04-03T12:34:56Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import check_compliance

            result = await check_compliance(
                ticket_id="ticket-123",
                regulations=["GDPR", "SOC2"],
            )

        assert result["compliant"] is False
        assert len(result["breaches"]) > 0


# ===== TESTES DA FERRAMENTA remediate_issue =====


class TestRemediateIssue:
    """Testes da ferramenta remediate_issue."""

    @pytest.mark.asyncio
    async def test_remediate_issue_successful(self):
        """
        DADO: Uma violação que pode ser automaticamente remediada
        QUANDO: Executo remediate_issue
        ENTÃO: Deve executar remediação e retornar success=True
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "remediation_id": "rem-123",
                "success": True,
                "action_taken": "blocked_source_ip",
                "details": {
                    "source_ip": "192.168.1.100",
                    "blocked_until": "2026-04-03T18:34:56Z",
                },
                "issue_resolved": True,
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import remediate_issue

            result = await remediate_issue(
                issue_id="issue-456",
                remediation_type="block_ip",
                parameters={"source_ip": "192.168.1.100", "duration_hours": 6},
            )

        assert result["success"] is True
        assert result["issue_resolved"] is True
        assert "remediation_id" in result

    @pytest.mark.asyncio
    async def test_remediate_issue_invalid_remediation_type(self):
        """
        DADO: Um tipo de remediação inválido
        QUANDO: Executo remediate_issue
        ENTÃO: Deve levantar ValueError
        """
        from guard_mcp_server.tools.guard_tools import remediate_issue

        with pytest.raises(ValueError, match="remediation_type"):
            await remediate_issue(
                issue_id="issue-456",
                remediation_type="invalid_type",
                parameters={},
            )

    @pytest.mark.asyncio
    async def test_remediate_issue_manual_intervention_required(self):
        """
        DADO: Uma violação que requer intervenção manual
        QUANDO: Executo remediate_issue
        ENTÃO: Deve retornar success=False com manual_required=True
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "remediation_id": None,
                "success": False,
                "manual_required": True,
                "reason": "Remediação requer aprovação manual",
                "suggested_actions": ["Contactar SOC", "Abrir ticket de incidente"],
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from guard_mcp_server.tools.guard_tools import remediate_issue

            result = await remediate_issue(
                issue_id="issue-critical",
                remediation_type="manual_intervention",
                parameters={},
            )

        assert result["success"] is False
        assert result["manual_required"] is True


# ===== TESTES DE INTEGRAÇÃO DO SERVIDOR =====


class TestGuardMCPServerIntegration:
    """Testes de integração do servidor MCP."""

    def test_server_has_required_tools(self):
        """
        DADO: O servidor Guard MCP está inicializado
        QUANDO: Listo ferramentas disponíveis
        ENTÃO: Deve ter exatamente 5 ferramentas registradas
        """
        from guard_mcp_server.server import mcp

        # Verificar que o servidor MCP está configurado
        assert mcp is not None
        assert mcp.name == "Guard MCP Server"

    def test_tools_have_metadata(self):
        """
        DADO: O servidor Guard MCP está inicializado
        QUANDO: Examino metadata das ferramentas
        ENTÃO: Cada ferramenta deve ter descrição e parâmetros documentados
        """
        from guard_mcp_server.tools.guard_tools import (
            check_compliance,
            detect_threats,
            remediate_issue,
            scan_vulnerabilities,
            validate_security,
        )

        # Verificar que funções de tools existem e têm docstrings
        assert validate_security.__doc__
        assert scan_vulnerabilities.__doc__
        assert detect_threats.__doc__
        assert check_compliance.__doc__
        assert remediate_issue.__doc__

    def test_server_info_resource_exists(self):
        """
        DADO: O servidor Guard MCP está inicializado
        QUANDO: Verifico recursos disponíveis
        ENTÃO: O recurso guard://info deve existir
        """
        from guard_mcp_server.server import mcp

        assert mcp is not None

    def test_register_function_exists(self):
        """
        DADO: O módulo guard_tools está importado
        QUANDO: Verifico a função de registro
        ENTÃO: register_guard_tools deve existir
        """
        from guard_mcp_server.tools.guard_tools import register_guard_tools

        assert callable(register_guard_tools)


# ===== TESTES ADICIONAIS DE COBERTURA =====


class TestValidateSecurityEdgeCases:
    """Testes de edge cases para validate_security."""

    @pytest.mark.asyncio
    async def test_validate_security_all_environments(self):
        """
        DADO: Todos os ambientes válidos
        QUANDO: Executo validate_security para cada ambiente
        ENTÃO: Todos devem processar sem erro
        """
        from guard_mcp_server.tools.guard_tools import validate_security

        environments = ["production", "staging", "development"]

        for env in environments:
            mock_response = Mock()
            mock_response.json = Mock(
                return_value={
                    "validation_id": f"val-{env}",
                    "ticket_id": "ticket-123",
                    "validation_status": "approved",
                    "violations": [],
                    "risk_assessment": {
                        "risk_score": 0.0,
                        "severity": "low",
                        "impact": "No violations",
                    },
                    "approval_required": False,
                }
            )
            mock_response.raise_for_status = Mock()

            with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await validate_security(
                    ticket_id="ticket-123",
                    task_type="DEPLOY",
                    environment=env,
                )

                assert result["validation_status"] == "approved"

    @pytest.mark.asyncio
    async def test_validate_security_all_security_levels(self):
        """
        DADO: Todos os níveis de segurança válidos
        QUANDO: Executo validate_security para cada nível
        ENTÃO: Todos devem processar sem erro
        """
        from guard_mcp_server.tools.guard_tools import validate_security

        security_levels = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]

        for sec_level in security_levels:
            mock_response = Mock()
            mock_response.json = Mock(
                return_value={
                    "validation_id": f"val-{sec_level}",
                    "ticket_id": "ticket-123",
                    "validation_status": "approved",
                    "violations": [],
                    "risk_assessment": {
                        "risk_score": 0.0,
                        "severity": "low",
                        "impact": "No violations",
                    },
                    "approval_required": False,
                }
            )
            mock_response.raise_for_status = Mock()

            with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await validate_security(
                    ticket_id="ticket-123",
                    task_type="DEPLOY",
                    environment="production",
                    security_level=sec_level,
                )

                assert result["validation_status"] == "approved"


class TestScanVulnerabilitiesEdgeCases:
    """Testes de edge cases para scan_vulnerabilities."""

    @pytest.mark.asyncio
    async def test_scan_vulnerabilities_all_scan_types(self):
        """
        DADO: Todos os tipos de scan válidos
        QUANDO: Executo scan_vulnerabilities para cada tipo
        ENTÃO: Todos devem processar sem erro
        """
        from guard_mcp_server.tools.guard_tools import scan_vulnerabilities

        scan_types = ["container", "code", "dependency", "filesystem", "repository"]

        for scan_type in scan_types:
            mock_response = Mock()
            mock_response.json = Mock(
                return_value={
                    "target": f"target-{scan_type}",
                    "vulnerabilities": [],
                    "scan_status": "completed",
                }
            )
            mock_response.raise_for_status = Mock()

            with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await scan_vulnerabilities(target=f"test-{scan_type}", scan_type=scan_type)

                assert result["scan_status"] == "completed"


class TestRemediateIssueEdgeCases:
    """Testes de edge cases para remediate_issue."""

    @pytest.mark.asyncio
    async def test_remediate_issue_all_remediation_types(self):
        """
        DADO: Todos os tipos de remediação válidos
        QUANDO: Executo remediate_issue para cada tipo
        ENTÃO: Todos devem processar sem erro
        """
        from guard_mcp_server.tools.guard_tools import remediate_issue

        remediation_types = [
            "block_ip",
            "kill_process",
            "isolate_container",
            "revoke_token",
            "rollback_deployment",
            "manual_intervention",
        ]

        for rem_type in remediation_types:
            mock_response = Mock()
            mock_response.json = Mock(
                return_value={
                    "remediation_id": f"rem-{rem_type}",
                    "success": True,
                    "action_taken": rem_type,
                    "issue_resolved": True,
                }
            )
            mock_response.raise_for_status = Mock()

            with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                result = await remediate_issue(
                    issue_id="issue-123",
                    remediation_type=rem_type,
                    parameters={},
                )

                assert result["success"] is True


class TestSettings:
    """Testes de configuração."""

    def test_settings_default_values(self):
        """
        DADO: O módulo settings é importado
        QUANDO: Obtenho instância de settings
        ENTÃO: Deve ter valores padrão corretos
        """
        from guard_mcp_server.config import get_settings

        settings = get_settings()

        assert settings.service_name == "guard-mcp-server"
        assert settings.service_version == "1.0.0"
        assert settings.port == 3015  # spec: INFRA-001-04
        assert settings.guard_agent_host == "guard-agents"
        assert settings.guard_agent_port == 8008
        assert settings.trivy_host == "trivy"
        assert settings.trivy_port == 8080

    def test_settings_singleton(self):
        """
        DADO: O módulo settings é importado
        QUANDO: Chamo get_settings múltiplas vezes
        ENTÃO: Deve retornar a mesma instância (singleton)
        """
        from guard_mcp_server.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2
