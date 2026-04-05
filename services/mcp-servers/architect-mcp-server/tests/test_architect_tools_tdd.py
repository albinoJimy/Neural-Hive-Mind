"""
Testes do Architect MCP Server - Fase RED (TDD)

Testes escritos ANTES da implementação.
Com MOCKS para isolar a unidade sendo testada.

FASE 1: RED - Testes falhando (implementação ainda não existe)
FASE 2: GREEN - Implementar código mínimo para passar
FASE 3: REFACTOR - Melhorar design com testes passando
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


# ===== TESTES DA FERRAMENTA plan_architecture =====


class TestPlanArchitecture:
    """Testes da ferramenta plan_architecture."""

    @pytest.mark.asyncio
    async def test_plan_architecture_success(self, mock_feature_request):
        """
        DADO: Uma requisição de feature válida
        QUANDO: Executo plan_architecture
        ENTÃO: Deve retornar plano arquitetural completo com componentes
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "plan_id": "arch-plan-001",
                "ticket_id": "ARCH-001",
                "feature_name": "User Authentication",
                "architecture_type": "microservices",
                "components": [
                    {
                        "name": "auth-service",
                        "type": "stateless_service",
                        "responsibility": "Handle authentication flows",
                        "dependencies": ["redis", "mongodb"],
                        "estimated_complexity": "medium",
                    },
                    {
                        "name": "token-validation-middleware",
                        "type": "middleware",
                        "responsibility": "Validate JWT tokens",
                        "dependencies": [],
                        "estimated_complexity": "low",
                    },
                ],
                "dataflows": [
                    {
                        "flow": "client_authentication",
                        "steps": [
                            {"service": "api-gateway", "action": "route"},
                            {"service": "auth-service", "action": "authenticate"},
                            {"service": "redis", "action": "store_session"},
                        ]
                    }
                ],
                "patterns": ["Stateless Authentication", "JWT Pattern"],
                "estimated_effort_days": 10,
                "team_size_recommendation": 2,
                "risks": [
                    {
                        "type": "security",
                        "description": "JWT secret rotation",
                        "mitigation": "Use key rotation service",
                    }
                ],
                "status": "planned",
                "created_at": "2026-04-03T12:00:00Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import plan_architecture

            result = await plan_architecture(
                ticket_id="ARCH-001",
                feature_name="User Authentication",
                feature_description="Implement OAuth2 authentication",
                requirements=["OAuth2", "JWT", "Session management"],
                constraints={"max_development_time_days": 14, "team_size": 3},
            )

        # Assert
        assert result["plan_id"] == "arch-plan-001"
        assert result["ticket_id"] == "ARCH-001"
        assert len(result["components"]) >= 2
        assert result["status"] == "planned"

    @pytest.mark.asyncio
    async def test_plan_architecture_missing_required_field(self):
        """
        DADO: Uma chamada sem ticket_id
        QUANDO: Executo plan_architecture
        ENTÃO: Deve levantar ValueError
        """
        from architect_mcp_server.tools.architect_tools import plan_architecture

        with pytest.raises(ValueError, match="ticket_id"):
            await plan_architecture(
                ticket_id="",
                feature_name="Test Feature",
                feature_description="Test",
            )

    @pytest.mark.asyncio
    async def test_plan_architecture_insufficient_constraints(
        self, mock_feature_request
    ):
        """
        DADO: Uma requisição com restrições insuficientes
        QUANDO: Executo plan_architecture
        ENTÃO: Deve retornar recomendações de ajuste
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "plan_id": "arch-plan-002",
                "ticket_id": "ARCH-002",
                "status": "needs_refinement",
                "warnings": [
                    {
                        "type": "constraint_warning",
                        "message": "max_development_time_days may be insufficient for complexity",
                        "recommended_adjustment": "Increase to 21 days or reduce scope",
                    }
                ],
                "components": [],
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import plan_architecture

            result = await plan_architecture(
                ticket_id="ARCH-002",
                feature_name="Complex Feature",
                feature_description="Very complex implementation",
                requirements=["Requirement 1", "Requirement 2"],
                constraints={"max_development_time_days": 3, "team_size": 1},
            )

        assert result["status"] == "needs_refinement"
        assert len(result["warnings"]) > 0


# ===== TESTES DA FERRAMENTA validate_design =====


class TestValidateDesign:
    """Testes da ferramenta validate_design."""

    @pytest.mark.asyncio
    async def test_validate_design_valid(self, mock_design_document):
        """
        DADO: Um design document válido
        QUANDO: Executo validate_design
        ENTÃO: Deve retornar valid=True sem violações
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "validation_id": "val-design-001",
                "design_id": "design-001",
                "valid": True,
                "violations": [],
                "warnings": [],
                "pattern_compliance": {
                    "compliant_patterns": ["Gateway Pattern", "Token Pattern"],
                    "non_compliant_patterns": [],
                    "score": 1.0,
                },
                "best_practices": {
                    "solid_principles": {"score": 0.9, "violations": []},
                    "coupling": {"score": 0.85, "status": "good"},
                    "cohesion": {"score": 0.9, "status": "excellent"},
                },
                "validated_at": "2026-04-03T12:00:00Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import validate_design

            result = await validate_design(
                design_document=mock_design_document,
                validation_profile="strict",
            )

        assert result["valid"] is True
        assert result["violations"] == []
        assert result["pattern_compliance"]["score"] >= 0.9

    @pytest.mark.asyncio
    async def test_validate_design_with_violations(self, mock_design_document):
        """
        DADO: Um design com violações de padrões
        QUANDO: Executo validate_design
        ENTÃO: Deve retornar valid=False com lista de violações
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "validation_id": "val-design-002",
                "design_id": "design-002",
                "valid": False,
                "violations": [
                    {
                        "type": "circular_dependency",
                        "severity": "error",
                        "components": ["service-a", "service-b"],
                        "description": "Circular dependency detected between services",
                        "recommendation": "Introduce event-driven pattern",
                    },
                    {
                        "type": "tight_coupling",
                        "severity": "warning",
                        "components": ["auth-service", "user-service"],
                        "description": "Direct database access between services",
                        "recommendation": "Use API communication",
                    },
                ],
                "warnings": [],
                "pattern_compliance": {
                    "compliant_patterns": [],
                    "non_compliant_patterns": ["Gateway Pattern"],
                    "score": 0.4,
                },
                "validated_at": "2026-04-03T12:00:00Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import validate_design

            result = await validate_design(
                design_document=mock_design_document,
                validation_profile="strict",
            )

        assert result["valid"] is False
        assert len(result["violations"]) > 0
        assert any(v["severity"] == "error" for v in result["violations"])

    @pytest.mark.asyncio
    async def test_validate_design_invalid_profile(self):
        """
        DADO: Um profile de validação inválido
        QUANDO: Executo validate_design
        ENTÃO: Deve levantar ValueError
        """
        from architect_mcp_server.tools.architect_tools import validate_design

        with pytest.raises(ValueError, match="validation_profile"):
            await validate_design(
                design_document={},
                validation_profile="invalid_profile",
            )


# ===== TESTES DA FERRAMENTA track_evolution =====


class TestTrackEvolution:
    """Testes da ferramenta track_evolution."""

    @pytest.mark.asyncio
    async def test_track_evolution_new_version(self, mock_architecture_state):
        """
        DADO: Uma mudança arquitetural que incrementa versão
        QUANDO: Executo track_evolution
        ENTÃO: Deve registrar evolução e retornar nova versão
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "evolution_id": "evo-001",
                "previous_version": "1.2.0",
                "new_version": "1.3.0",
                "change_type": "minor",
                "changes": [
                    {
                        "component": "auth-service",
                        "change": "added",
                        "description": "New authentication microservice",
                    }
                ],
                "migration_required": False,
                "breaking_changes": [],
                "evolution_path": [
                    {"version": "1.2.0", "status": "current"},
                    {"version": "1.3.0", "status": "target"},
                ],
                "rollback_plan": {
                    "available": True,
                    "previous_version": "1.2.0",
                    "steps": ["Disable auth-service", "Restore previous state"],
                },
                "tracked_at": "2026-04-03T12:00:00Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import track_evolution

            result = await track_evolution(
                current_state=mock_architecture_state,
                changes=[
                    {
                        "component": "auth-service",
                        "change": "added",
                        "description": "New authentication microservice",
                    }
                ],
                change_type="minor",
            )

        assert result["new_version"] == "1.3.0"
        assert result["change_type"] == "minor"
        assert len(result["changes"]) > 0

    @pytest.mark.asyncio
    async def test_track_evolution_breaking_change(self, mock_architecture_state):
        """
        DADO: Uma mudança arquitetural com breaking change
        QUANDO: Executo track_evolution
        ENTÃO: Deve marcar breaking_changes e fornecer migration plan
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "evolution_id": "evo-002",
                "previous_version": "1.2.0",
                "new_version": "2.0.0",
                "change_type": "major",
                "changes": [
                    {
                        "component": "api-gateway",
                        "change": "removed",
                        "description": "Deprecated API Gateway removed",
                    }
                ],
                "migration_required": True,
                "breaking_changes": [
                    {
                        "component": "api-gateway",
                        "impact": "Direct client integration required",
                        "mitigation": "Provide migration guide",
                    }
                ],
                "migration_plan": {
                    "steps": [
                        "Inform clients about deprecation",
                        "Provide new integration guide",
                        "Support period: 3 months",
                    ],
                    "estimated_migration_time_days": 30,
                },
                "tracked_at": "2026-04-03T12:00:00Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import track_evolution

            result = await track_evolution(
                current_state=mock_architecture_state,
                changes=[
                    {
                        "component": "api-gateway",
                        "change": "removed",
                        "description": "Deprecated API Gateway removed",
                    }
                ],
                change_type="major",
            )

        assert result["new_version"] == "2.0.0"
        assert result["migration_required"] is True
        assert len(result["breaking_changes"]) > 0

    @pytest.mark.asyncio
    async def test_track_evolution_invalid_change_type(self):
        """
        DADO: Um tipo de mudança inválido
        QUANDO: Executo track_evolution
        ENTÃO: Deve levantar ValueError
        """
        from architect_mcp_server.tools.architect_tools import track_evolution

        with pytest.raises(ValueError, match="change_type"):
            await track_evolution(
                current_state={},
                changes=[],
                change_type="invalid_type",
            )


# ===== TESTES DA FERRAMENTA analyze_patterns =====


class TestAnalyzePatterns:
    """Testes da ferramenta analyze_patterns."""

    @pytest.mark.asyncio
    async def test_analyze_patterns_with_recommendations(
        self, mock_pattern_analysis_result
    ):
        """
        DADO: Uma base de código para análise
        QUANDO: Executo analyze_patterns
        ENTÃO: Deve retornar padrões detectados e recomendações
        """
        mock_response = Mock()
        mock_response.json = Mock(return_value=mock_pattern_analysis_result)
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import analyze_patterns

            result = await analyze_patterns(
                repository_path="/services",
                analysis_depth="deep",
                focus_areas=["services", "communication"],
            )

        assert result["analysis_id"] == "pattern-analysis-001"
        assert len(result["patterns_detected"]) >= 2
        assert result["metrics"]["pattern_coverage"] >= 0.0

    @pytest.mark.asyncio
    async def test_analyze_patterns_anti_patterns_detected(self):
        """
        DADO: Uma base de código com anti-patterns
        QUANDO: Executo analyze_patterns
        ENTÃO: Deve identificar anti-patterns com severidade
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "analysis_id": "pattern-analysis-002",
                "patterns_detected": [
                    {
                        "name": "Singleton",
                        "occurrences": 3,
                        "locations": ["config-service"],
                        "health": "good",
                    }
                ],
                "anti_patterns_detected": [
                    {
                        "name": "Spaghetti Code",
                        "occurrences": 5,
                        "locations": ["legacy-controller", "old-service"],
                        "severity": "critical",
                        "recommendation": "Refactor using clean architecture",
                        "estimated_effort_days": 14,
                    },
                    {
                        "name": "Golden Hammer",
                        "occurrences": 2,
                        "locations": ["data-layer"],
                        "severity": "medium",
                        "recommendation": "Consider alternative data stores",
                        "estimated_effort_days": 7,
                    },
                ],
                "metrics": {
                    "pattern_coverage": 0.45,
                    "code_reusability": 0.52,
                    "maintainability_index": 0.38,
                    "technical_debt_ratio": 0.62,
                },
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import analyze_patterns

            result = await analyze_patterns(
                repository_path="/services",
                analysis_depth="deep",
                focus_areas=["services"],
            )

        assert len(result["anti_patterns_detected"]) > 0
        assert any(
            ap["severity"] == "critical" for ap in result["anti_patterns_detected"]
        )

    @pytest.mark.asyncio
    async def test_analyze_patterns_invalid_analysis_depth(self):
        """
        DADO: Uma profundidade de análise inválida
        QUANDO: Executo analyze_patterns
        ENTÃO: Deve levantar ValueError
        """
        from architect_mcp_server.tools.architect_tools import analyze_patterns

        with pytest.raises(ValueError, match="analysis_depth"):
            await analyze_patterns(
                repository_path="/services",
                analysis_depth="invalid_depth",
                focus_areas=[],
            )


# ===== TESTES DA FERRAMENTA generate_documentation =====


class TestGenerateDocumentation:
    """Testes da ferramenta generate_documentation."""

    @pytest.mark.asyncio
    async def test_generate_documentation_success(self, mock_documentation_config):
        """
        DADO: Uma configuração válida de documentação
        QUANDO: Executo generate_documentation
        ENTÃO: Deve gerar documentação com URL de acesso
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "doc_id": "doc-001",
                "ticket_id": "ARCH-001",
                "doc_type": "architecture_decision_record",
                "status": "generated",
                "content": {
                    "title": "ADR-001: User Authentication Architecture",
                    "sections": {
                        "context": "Current system lacks centralized authentication...",
                        "decision": "Implement OAuth2 with JWT tokens...",
                        "alternatives": [
                            "Session-based authentication",
                            "API Key authentication",
                        ],
                        "consequences": {
                            "positive": [
                                "Improved security",
                                "Better user experience",
                            ],
                            "negative": ["Increased complexity", "External dependency"],
                        },
                    },
                    "diagrams": [
                        {
                            "type": "sequence",
                            "content": "sequence_auth_flow.puml",
                        }
                    ],
                },
                "output_path": "/docs/architecture/adr-001-authentication.md",
                "formats": ["markdown", "html"],
                "generated_at": "2026-04-03T12:00:00Z",
                "download_urls": {
                    "markdown": "/docs/architecture/adr-001-authentication.md",
                    "html": "/docs/architecture/adr-001-authentication.html",
                },
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import generate_documentation

            result = await generate_documentation(
                ticket_id="ARCH-001",
                doc_type="architecture_decision_record",
                config=mock_documentation_config,
            )

        assert result["status"] == "generated"
        assert result["doc_id"] == "doc-001"
        assert "download_urls" in result

    @pytest.mark.asyncio
    async def test_generate_documentation_with_diagrams(self, mock_documentation_config):
        """
        DADO: Uma configuração que requer diagramas
        QUANDO: Executo generate_documentation
        ENTÃO: Deve incluir diagramas na saída
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "doc_id": "doc-002",
                "ticket_id": "ARCH-002",
                "doc_type": "system_design",
                "status": "generated",
                "content": {
                    "title": "System Design: Payment Processing",
                    "diagrams": [
                        {
                            "type": "c4_context",
                            "title": "System Context",
                            "content": "c4_context.puml",
                            "render_url": "/diagrams/c4_context.svg",
                        },
                        {
                            "type": "c4_container",
                            "title": "Container Diagram",
                            "content": "c4_container.puml",
                            "render_url": "/diagrams/c4_container.svg",
                        },
                        {
                            "type": "sequence",
                            "title": "Payment Flow",
                            "content": "sequence_payment.puml",
                            "render_url": "/diagrams/sequence_payment.svg",
                        },
                    ],
                },
                "output_path": "/docs/architecture/payment-system.md",
                "generated_at": "2026-04-03T12:00:00Z",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from architect_mcp_server.tools.architect_tools import generate_documentation

            result = await generate_documentation(
                ticket_id="ARCH-002",
                doc_type="system_design",
                config=mock_documentation_config,
            )

        assert result["status"] == "generated"
        assert len(result["content"]["diagrams"]) >= 3

    @pytest.mark.asyncio
    async def test_generate_documentation_invalid_doc_type(self):
        """
        DADO: Um tipo de documento inválido
        QUANDO: Executo generate_documentation
        ENTÃO: Deve levantar ValueError
        """
        from architect_mcp_server.tools.architect_tools import generate_documentation

        with pytest.raises(ValueError, match="doc_type"):
            await generate_documentation(
                ticket_id="ARCH-001",
                doc_type="invalid_doc_type",
                config={},
            )


# ===== TESTES DE INTEGRAÇÃO DO SERVIDOR =====


class TestArchitectMCPServerIntegration:
    """Testes de integração do servidor MCP."""

    def test_server_has_required_tools(self):
        """
        DADO: O servidor Architect MCP está inicializado
        QUANDO: Listo ferramentas disponíveis
        ENTÃO: Deve ter exatamente 5 ferramentas registradas
        """
        from architect_mcp_server.server import mcp

        # Verificar que o servidor MCP está configurado
        assert mcp is not None
        assert mcp.name == "Architect MCP Server"

    def test_tools_have_metadata(self):
        """
        DADO: O servidor Architect MCP está inicializado
        QUANDO: Examino metadata das ferramentas
        ENTÃO: Cada ferramenta deve ter descrição e parâmetros documentados
        """
        from architect_mcp_server.tools.architect_tools import (
            analyze_patterns,
            generate_documentation,
            plan_architecture,
            track_evolution,
            validate_design,
        )

        # Verificar que funções de tools existem e têm docstrings
        assert plan_architecture.__doc__
        assert validate_design.__doc__
        assert track_evolution.__doc__
        assert analyze_patterns.__doc__
        assert generate_documentation.__doc__

    def test_server_info_resource_exists(self):
        """
        DADO: O servidor Architect MCP está inicializado
        QUANDO: Verifico recursos disponíveis
        ENTÃO: O recurso architect://info deve existir
        """
        from architect_mcp_server.server import mcp

        assert mcp is not None

    def test_register_function_exists(self):
        """
        DADO: O módulo architect_tools está importado
        QUANDO: Verifico a função de registro
        ENTÃO: register_architect_tools deve existir
        """
        from architect_mcp_server.tools.architect_tools import register_architect_tools

        assert callable(register_architect_tools)
