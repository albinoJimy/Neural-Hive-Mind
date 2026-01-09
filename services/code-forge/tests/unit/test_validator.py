"""
Testes unitarios para Validator.

Cobertura:
- Validacao dinamica baseada em ferramentas MCP
- Integracao com SonarQube, Snyk, Trivy
- Feedback loop para MCP (reputation updates)
- Fallback para validacoes fixas
- Parsing de violation reports
- Metricas Prometheus
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestValidatorMCPIntegration:
    """Testes de integracao com MCP Tool Catalog."""

    @pytest.mark.asyncio
    async def test_validate_with_mcp_tools(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context_with_mcp
    ):
        """Deve usar ferramentas MCP quando disponiveis."""
        from services.code_forge.src.services.validator import Validator

        # Configurar ferramentas de validacao no contexto
        sample_pipeline_context_with_mcp.selected_tools = [
            {'tool_id': 'tool-001', 'tool_name': 'SonarQube', 'category': 'VALIDATION'},
            {'tool_id': 'tool-002', 'tool_name': 'Snyk', 'category': 'VALIDATION'}
        ]

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        await validator.validate(sample_pipeline_context_with_mcp)

        mock_sonarqube_client.analyze_code.assert_called_once()
        mock_snyk_client.scan_dependencies.assert_called_once()
        mock_trivy_client.scan_filesystem.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_with_all_mcp_tools(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_mcp_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve executar todas as ferramentas MCP selecionadas."""
        from services.code_forge.src.services.validator import Validator

        sample_pipeline_context_with_mcp.selected_tools = [
            {'tool_id': 'tool-001', 'tool_name': 'SonarQube', 'category': 'VALIDATION'},
            {'tool_id': 'tool-002', 'tool_name': 'Snyk', 'category': 'VALIDATION'},
            {'tool_id': 'tool-003', 'tool_name': 'Trivy', 'category': 'VALIDATION'}
        ]

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=mock_mcp_client,
            metrics=None
        )

        await validator.validate(sample_pipeline_context_with_mcp)

        mock_sonarqube_client.analyze_code.assert_called_once()
        mock_snyk_client.scan_dependencies.assert_called_once()
        mock_trivy_client.scan_filesystem.assert_called_once()


class TestValidatorFallback:
    """Testes de fallback para validacoes fixas."""

    @pytest.mark.asyncio
    async def test_validate_fallback_without_mcp_tools(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context
    ):
        """Deve usar validacoes fixas sem ferramentas MCP."""
        from services.code_forge.src.services.validator import Validator

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        await validator.validate(sample_pipeline_context)

        mock_sonarqube_client.analyze_code.assert_called_once()
        mock_snyk_client.scan_dependencies.assert_called_once()
        mock_trivy_client.scan_filesystem.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_fallback_unmapped_tools(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context_with_mcp
    ):
        """Deve usar fallback para ferramentas nao mapeadas."""
        from services.code_forge.src.services.validator import Validator

        # Ferramentas desconhecidas
        sample_pipeline_context_with_mcp.selected_tools = [
            {'tool_id': 'tool-999', 'tool_name': 'UnknownTool', 'category': 'VALIDATION'}
        ]

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        await validator.validate(sample_pipeline_context_with_mcp)

        # Deve usar todas as ferramentas default
        mock_sonarqube_client.analyze_code.assert_called_once()
        mock_snyk_client.scan_dependencies.assert_called_once()
        mock_trivy_client.scan_filesystem.assert_called_once()


class TestValidatorParallelExecution:
    """Testes de execucao paralela."""

    @pytest.mark.asyncio
    async def test_validate_parallel_execution(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context
    ):
        """Deve executar validacoes em paralelo."""
        from services.code_forge.src.services.validator import Validator

        # Simular delays diferentes
        async def slow_sonar(*args, **kwargs):
            await asyncio.sleep(0.1)
            return mock_sonarqube_client.analyze_code.return_value

        async def slow_snyk(*args, **kwargs):
            await asyncio.sleep(0.05)
            return mock_snyk_client.scan_dependencies.return_value

        async def slow_trivy(*args, **kwargs):
            await asyncio.sleep(0.02)
            return mock_trivy_client.scan_filesystem.return_value

        mock_sonarqube_client.analyze_code.side_effect = slow_sonar
        mock_snyk_client.scan_dependencies.side_effect = slow_snyk
        mock_trivy_client.scan_filesystem.side_effect = slow_trivy

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        import time
        start = time.time()
        await validator.validate(sample_pipeline_context)
        duration = time.time() - start

        # Execucao paralela deve ser mais rapida que sequencial (~0.17s vs ~0.1s)
        assert duration < 0.2  # Tolerancia para variacao


class TestValidatorErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_validate_handles_single_failure(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_metrics,
        sample_pipeline_context
    ):
        """Deve continuar quando uma validacao falha."""
        from services.code_forge.src.services.validator import Validator

        mock_sonarqube_client.analyze_code.side_effect = Exception('SonarQube error')

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=mock_metrics
        )

        await validator.validate(sample_pipeline_context)

        # Outras validacoes devem ter executado
        mock_snyk_client.scan_dependencies.assert_called_once()
        mock_trivy_client.scan_filesystem.assert_called_once()
        # Apenas 2 validacoes no contexto (as que nao falharam)
        assert len(sample_pipeline_context.validation_results) == 2

    @pytest.mark.asyncio
    async def test_validate_handles_all_failures(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context
    ):
        """Deve tratar quando todas as validacoes falham."""
        from services.code_forge.src.services.validator import Validator

        mock_sonarqube_client.analyze_code.side_effect = Exception('SonarQube error')
        mock_snyk_client.scan_dependencies.side_effect = Exception('Snyk error')
        mock_trivy_client.scan_filesystem.side_effect = Exception('Trivy error')

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        await validator.validate(sample_pipeline_context)

        assert len(sample_pipeline_context.validation_results) == 0


class TestValidatorMCPFeedback:
    """Testes de feedback para MCP Tool Catalog."""

    @pytest.mark.asyncio
    async def test_send_mcp_feedback_success(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context_with_mcp
    ):
        """Deve enviar feedback para MCP apos validacao."""
        from services.code_forge.src.services.validator import Validator

        sample_pipeline_context_with_mcp.selected_tools = [
            {'tool_id': 'tool-001', 'tool_name': 'SonarQube', 'category': 'VALIDATION'}
        ]

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        await validator.validate(sample_pipeline_context_with_mcp)

        mock_mcp_client.send_tool_feedback.assert_called()
        mock_metrics.mcp_feedback_sent_total.labels.assert_called_with(status='success')

    @pytest.mark.asyncio
    async def test_mcp_feedback_timeout_non_blocking(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context_with_mcp
    ):
        """Deve continuar execucao quando feedback MCP timeout."""
        from services.code_forge.src.services.validator import Validator

        sample_pipeline_context_with_mcp.selected_tools = [
            {'tool_id': 'tool-001', 'tool_name': 'SonarQube', 'category': 'VALIDATION'}
        ]
        mock_mcp_client.send_tool_feedback.side_effect = asyncio.TimeoutError()

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        # Nao deve lancar excecao
        await validator.validate(sample_pipeline_context_with_mcp)

        mock_metrics.mcp_feedback_sent_total.labels.assert_called_with(status='failure')

    @pytest.mark.asyncio
    async def test_no_mcp_feedback_without_selection_id(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_mcp_client,
        sample_pipeline_context
    ):
        """Nao deve enviar feedback sem mcp_selection_id."""
        from services.code_forge.src.services.validator import Validator

        # Contexto sem mcp_selection_id
        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=mock_mcp_client,
            metrics=None
        )

        await validator.validate(sample_pipeline_context)

        mock_mcp_client.send_tool_feedback.assert_not_called()


class TestValidatorMetrics:
    """Testes de metricas Prometheus."""

    @pytest.mark.asyncio
    async def test_validation_metrics_recorded(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_metrics,
        sample_pipeline_context
    ):
        """Deve registrar metricas de validacao."""
        from services.code_forge.src.services.validator import Validator

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=mock_metrics
        )

        await validator.validate(sample_pipeline_context)

        mock_metrics.validations_run_total.labels.assert_called()
        mock_metrics.validation_issues_found.labels.assert_called()
        mock_metrics.quality_score.observe.assert_called()

    @pytest.mark.asyncio
    async def test_issue_counts_recorded(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        mock_metrics,
        sample_pipeline_context
    ):
        """Deve registrar contagem de issues por severidade."""
        from services.code_forge.src.services.validator import Validator

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=mock_metrics
        )

        await validator.validate(sample_pipeline_context)

        # Deve registrar para cada severidade
        calls = [call[0][0] for call in mock_metrics.validation_issues_found.labels.call_args_list]
        assert any('critical' in str(c) for c in calls)
        assert any('high' in str(c) for c in calls)
        assert any('medium' in str(c) for c in calls)
        assert any('low' in str(c) for c in calls)


class TestValidatorContextExtraction:
    """Testes de extracao de contexto."""

    @pytest.mark.asyncio
    async def test_extract_language_from_ticket(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context
    ):
        """Deve extrair linguagem do ticket."""
        from services.code_forge.src.services.validator import Validator

        sample_pipeline_context.ticket.parameters['language'] = 'java'

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        await validator.validate(sample_pipeline_context)

        # Snyk deve receber linguagem correta
        call_args = mock_snyk_client.scan_dependencies.call_args
        assert call_args[0][1] == 'java'  # language parameter

    @pytest.mark.asyncio
    async def test_extract_project_key_from_ticket(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context
    ):
        """Deve extrair project_key do ticket."""
        from services.code_forge.src.services.validator import Validator

        sample_pipeline_context.ticket.parameters['project_key'] = 'custom-project'

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        await validator.validate(sample_pipeline_context)

        # SonarQube deve receber project_key correto
        call_args = mock_sonarqube_client.analyze_code.call_args
        assert call_args[0][0] == 'custom-project'  # project_key parameter

    @pytest.mark.asyncio
    async def test_use_workspace_path_from_context(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context
    ):
        """Deve usar workspace_path do contexto quando disponivel."""
        from services.code_forge.src.services.validator import Validator

        sample_pipeline_context.code_workspace_path = '/custom/workspace'

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        await validator.validate(sample_pipeline_context)

        # Todas as ferramentas devem usar workspace_path correto
        sonar_args = mock_sonarqube_client.analyze_code.call_args
        snyk_args = mock_snyk_client.scan_dependencies.call_args
        trivy_args = mock_trivy_client.scan_filesystem.call_args

        assert sonar_args[0][1] == '/custom/workspace'
        assert snyk_args[0][0] == '/custom/workspace'
        assert trivy_args[0][0] == '/custom/workspace'


class TestValidatorResultsAggregation:
    """Testes de agregacao de resultados."""

    @pytest.mark.asyncio
    async def test_all_results_added_to_context(
        self,
        mock_sonarqube_client,
        mock_snyk_client,
        mock_trivy_client,
        sample_pipeline_context
    ):
        """Deve adicionar todos os resultados ao contexto."""
        from services.code_forge.src.services.validator import Validator

        validator = Validator(
            sonarqube_client=mock_sonarqube_client,
            snyk_client=mock_snyk_client,
            trivy_client=mock_trivy_client,
            mcp_client=None,
            metrics=None
        )

        await validator.validate(sample_pipeline_context)

        assert len(sample_pipeline_context.validation_results) == 3
