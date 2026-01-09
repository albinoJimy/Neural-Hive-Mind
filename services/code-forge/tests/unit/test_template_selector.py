"""
Testes unitarios para TemplateSelector.

Cobertura:
- Selecao via MCP Tool Catalog (sucesso, timeout, fallback)
- Cache hit/miss no Redis
- Calculo de complexity_score
- Mapeamento de ferramentas para generation_method
- Validacao de criterios de selecao
- Metricas Prometheus
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTemplateSelectorMCPIntegration:
    """Testes de integracao com MCP Tool Catalog."""

    @pytest.mark.asyncio
    async def test_select_with_mcp_success(
        self,
        mock_git_client,
        mock_redis_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context
    ):
        """Deve selecionar template via MCP com sucesso."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        result = await selector.select(sample_pipeline_context)

        assert result is not None
        assert result.template_id == 'microservice-python-v1'
        mock_mcp_client.request_tool_selection.assert_called_once()
        mock_metrics.mcp_selection_requests_total.labels.assert_called()

    @pytest.mark.asyncio
    async def test_select_mcp_timeout_fallback(
        self,
        mock_git_client,
        mock_redis_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context
    ):
        """Deve usar fallback quando MCP timeout."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        # Simular timeout
        mock_mcp_client.request_tool_selection.side_effect = asyncio.TimeoutError()

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        result = await selector.select(sample_pipeline_context)

        assert result is not None
        mock_metrics.mcp_selection_requests_total.labels.assert_called_with(status='timeout')

    @pytest.mark.asyncio
    async def test_select_mcp_error_fallback(
        self,
        mock_git_client,
        mock_redis_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context
    ):
        """Deve usar fallback quando MCP retorna erro."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        mock_mcp_client.request_tool_selection.side_effect = Exception('MCP error')

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        result = await selector.select(sample_pipeline_context)

        assert result is not None
        mock_metrics.mcp_selection_requests_total.labels.assert_called_with(status='failure')

    @pytest.mark.asyncio
    async def test_select_without_mcp_client(
        self,
        mock_git_client,
        mock_redis_client,
        sample_pipeline_context
    ):
        """Deve funcionar sem cliente MCP."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        result = await selector.select(sample_pipeline_context)

        assert result is not None
        assert result.template_id == 'microservice-python-v1'


class TestTemplateSelectorCache:
    """Testes de cache Redis."""

    @pytest.mark.asyncio
    async def test_select_cache_hit(
        self,
        mock_git_client,
        mock_redis_client,
        sample_pipeline_context,
        cached_template
    ):
        """Deve retornar template cacheado."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        mock_redis_client.get_cached_template.return_value = cached_template

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        result = await selector.select(sample_pipeline_context)

        assert result == cached_template
        mock_git_client.clone_templates_repo.assert_not_called()

    @pytest.mark.asyncio
    async def test_select_cache_miss(
        self,
        mock_git_client,
        mock_redis_client,
        sample_pipeline_context
    ):
        """Deve carregar template do Git quando cache miss."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        mock_redis_client.get_cached_template.return_value = None

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        result = await selector.select(sample_pipeline_context)

        assert result is not None
        mock_git_client.clone_templates_repo.assert_called_once()
        mock_redis_client.cache_template.assert_called_once()


class TestTemplateSelectorComplexityScore:
    """Testes de calculo de complexity_score."""

    @pytest.mark.asyncio
    async def test_calculate_complexity_score_low(
        self,
        mock_git_client,
        mock_redis_client,
        sample_pipeline_context
    ):
        """Deve calcular score baixo para poucos tasks e risk_band LOW."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        sample_pipeline_context.ticket.parameters['tasks'] = ['task-1']
        sample_pipeline_context.metadata['risk_band'] = 'LOW'

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        score = selector._calculate_complexity_score(sample_pipeline_context)

        assert 0.0 <= score <= 0.5  # Score baixo

    @pytest.mark.asyncio
    async def test_calculate_complexity_score_high(
        self,
        mock_git_client,
        mock_redis_client,
        sample_pipeline_context
    ):
        """Deve calcular score alto para muitos tasks e risk_band HIGH."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        sample_pipeline_context.ticket.parameters['tasks'] = [f'task-{i}' for i in range(15)]
        sample_pipeline_context.metadata['risk_band'] = 'HIGH'

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        score = selector._calculate_complexity_score(sample_pipeline_context)

        assert 0.5 <= score <= 1.0  # Score alto

    @pytest.mark.asyncio
    async def test_calculate_complexity_score_critical(
        self,
        mock_git_client,
        mock_redis_client,
        sample_pipeline_context
    ):
        """Deve calcular score maximo para risk_band CRITICAL."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        sample_pipeline_context.ticket.parameters['tasks'] = [f'task-{i}' for i in range(25)]
        sample_pipeline_context.metadata['risk_band'] = 'CRITICAL'
        sample_pipeline_context.ticket.dependencies = [f'dep-{i}' for i in range(60)]

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        score = selector._calculate_complexity_score(sample_pipeline_context)

        assert score == 1.0  # Score maximo


class TestTemplateSelectorGenerationMethod:
    """Testes de mapeamento de ferramentas para generation_method."""

    @pytest.mark.asyncio
    async def test_map_tools_to_llm_method(
        self,
        mock_git_client,
        mock_redis_client
    ):
        """Deve mapear ferramentas LLM para method LLM."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        tools = [
            {'tool_name': 'GitHub Copilot', 'category': 'GENERATION'}
        ]

        method = selector._map_tools_to_generation_method(tools)

        assert method == 'LLM'

    @pytest.mark.asyncio
    async def test_map_tools_to_template_method(
        self,
        mock_git_client,
        mock_redis_client
    ):
        """Deve mapear ferramentas de template para method TEMPLATE."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        tools = [
            {'tool_name': 'Cookiecutter', 'category': 'GENERATION'}
        ]

        method = selector._map_tools_to_generation_method(tools)

        assert method == 'TEMPLATE'

    @pytest.mark.asyncio
    async def test_map_tools_to_hybrid_method(
        self,
        mock_git_client,
        mock_redis_client
    ):
        """Deve mapear ferramentas LLM + Template para method HYBRID."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        tools = [
            {'tool_name': 'GitHub Copilot', 'category': 'GENERATION'},
            {'tool_name': 'Cookiecutter', 'category': 'GENERATION'}
        ]

        method = selector._map_tools_to_generation_method(tools)

        assert method == 'HYBRID'

    @pytest.mark.asyncio
    async def test_map_tools_to_heuristic_method(
        self,
        mock_git_client,
        mock_redis_client
    ):
        """Deve mapear ferramentas desconhecidas para method HEURISTIC."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        tools = [
            {'tool_name': 'Custom Tool', 'category': 'GENERATION'}
        ]

        method = selector._map_tools_to_generation_method(tools)

        assert method == 'HEURISTIC'

    @pytest.mark.asyncio
    async def test_map_empty_tools(
        self,
        mock_git_client,
        mock_redis_client
    ):
        """Deve retornar TEMPLATE para lista vazia."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        method = selector._map_tools_to_generation_method([])

        assert method == 'TEMPLATE'


class TestTemplateSelectorMetrics:
    """Testes de metricas Prometheus."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_success(
        self,
        mock_git_client,
        mock_redis_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context
    ):
        """Deve registrar metricas em caso de sucesso."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        await selector.select(sample_pipeline_context)

        mock_metrics.mcp_selection_requests_total.labels.assert_called_with(status='success')
        mock_metrics.mcp_selection_duration_seconds.observe.assert_called()

    @pytest.mark.asyncio
    async def test_metrics_tools_selected_counted(
        self,
        mock_git_client,
        mock_redis_client,
        mock_mcp_client,
        mock_metrics,
        sample_pipeline_context,
        sample_mcp_response
    ):
        """Deve contar ferramentas selecionadas."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        mock_mcp_client.request_tool_selection.return_value = sample_mcp_response

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=mock_mcp_client,
            metrics=mock_metrics
        )

        await selector.select(sample_pipeline_context)

        # Deve chamar para cada categoria de ferramenta
        assert mock_metrics.mcp_tools_selected_total.labels.call_count >= 1


class TestTemplateSelectorContextUpdate:
    """Testes de atualizacao do contexto."""

    @pytest.mark.asyncio
    async def test_context_updated_with_mcp_selection(
        self,
        mock_git_client,
        mock_redis_client,
        mock_mcp_client,
        sample_pipeline_context,
        sample_mcp_response
    ):
        """Deve atualizar contexto com selecao MCP."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        mock_mcp_client.request_tool_selection.return_value = sample_mcp_response

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=mock_mcp_client,
            metrics=None
        )

        await selector.select(sample_pipeline_context)

        assert sample_pipeline_context.mcp_selection_id == sample_mcp_response['request_id']
        assert len(sample_pipeline_context.selected_tools) == 2
        assert sample_pipeline_context.generation_method is not None

    @pytest.mark.asyncio
    async def test_context_updated_with_template(
        self,
        mock_git_client,
        mock_redis_client,
        sample_pipeline_context
    ):
        """Deve atualizar contexto com template selecionado."""
        from services.code_forge.src.services.template_selector import TemplateSelector

        selector = TemplateSelector(
            git_client=mock_git_client,
            redis_client=mock_redis_client,
            mcp_client=None,
            metrics=None
        )

        result = await selector.select(sample_pipeline_context)

        assert sample_pipeline_context.selected_template == result
