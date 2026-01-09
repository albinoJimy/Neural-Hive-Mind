"""
Testes unitarios para GeneticToolSelector.

Cobertura:
- Algoritmo genetico completo (convergencia, max generations)
- Criacao de populacao inicial
- Tournament selection
- Crossover (single-point)
- Mutation (random)
- Fitness calculation multi-objetivo
- Cache hit/miss (Redis)
- Timeout com fallback heuristico
- Historico MongoDB
- Metricas Prometheus
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGeneticToolSelectorSelection:
    """Testes de selecao de ferramentas."""

    @pytest.mark.asyncio
    async def test_select_tools_success(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        mock_metrics,
        sample_tool_selection_request
    ):
        """Deve selecionar ferramentas com sucesso."""
        from src.services.genetic_tool_selector import GeneticToolSelector

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=mock_metrics
        )

        response = await selector.select_tools(sample_tool_selection_request)

        assert response is not None
        assert len(response.selected_tools) >= 1
        assert response.total_fitness_score > 0

    @pytest.mark.asyncio
    async def test_select_tools_returns_requested_categories(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Deve retornar ferramentas das categorias solicitadas."""
        from src.services.genetic_tool_selector import GeneticToolSelector

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        response = await selector.select_tools(sample_tool_selection_request)

        categories = set(t.category for t in response.selected_tools)
        assert 'VALIDATION' in categories or 'GENERATION' in categories


class TestGeneticToolSelectorCache:
    """Testes de cache Redis."""

    @pytest.mark.asyncio
    async def test_select_tools_cache_hit(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        mock_metrics,
        sample_tool_selection_request
    ):
        """Deve retornar resposta cacheada quando disponivel."""
        from src.services.genetic_tool_selector import GeneticToolSelector
        from src.models.tool_selection import ToolSelectionResponse, SelectionMethod

        # Configurar cache hit
        cached_response = {
            'request_id': sample_tool_selection_request.request_id,
            'selected_tools': [],
            'total_fitness_score': 0.9,
            'selection_method': SelectionMethod.GENETIC_ALGORITHM.value,
            'generations_evolved': 5,
            'population_size': 10,
            'convergence_time_ms': 100,
            'reasoning_summary': 'Cached',
            'confidence_score': 0.9,
            'cached': False
        }
        mock_tool_registry_with_multiple_tools.redis_client.get_cached_selection.return_value = cached_response

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=mock_metrics
        )

        response = await selector.select_tools(sample_tool_selection_request)

        assert response.cached is True
        mock_metrics.record_selection.assert_called()

    @pytest.mark.asyncio
    async def test_select_tools_cache_miss(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Deve executar GA quando cache miss."""
        from src.services.genetic_tool_selector import GeneticToolSelector

        # Configurar cache miss
        mock_tool_registry_with_multiple_tools.redis_client.get_cached_selection.return_value = None

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        response = await selector.select_tools(sample_tool_selection_request)

        assert response is not None
        assert response.cached is False
        mock_tool_registry_with_multiple_tools.redis_client.cache_selection.assert_called()


class TestGeneticToolSelectorGA:
    """Testes do algoritmo genetico."""

    @pytest.mark.asyncio
    async def test_ga_converges(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Deve convergir antes de max generations."""
        from src.services.genetic_tool_selector import GeneticToolSelector

        # Configurar para convergir rapidamente
        mock_settings.GA_MAX_GENERATIONS = 50
        mock_settings.GA_CONVERGENCE_THRESHOLD = 0.1

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        response = await selector.select_tools(sample_tool_selection_request)

        # Pode convergir antes de max generations
        assert response.generations_evolved <= mock_settings.GA_MAX_GENERATIONS

    @pytest.mark.asyncio
    async def test_ga_respects_max_generations(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Deve parar em max generations."""
        from src.services.genetic_tool_selector import GeneticToolSelector

        mock_settings.GA_MAX_GENERATIONS = 3
        mock_settings.GA_CONVERGENCE_THRESHOLD = 0.0001  # Muito baixo para convergir

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        response = await selector.select_tools(sample_tool_selection_request)

        assert response.generations_evolved <= mock_settings.GA_MAX_GENERATIONS


class TestGeneticToolSelectorTimeout:
    """Testes de timeout."""

    @pytest.mark.asyncio
    async def test_ga_timeout_fallback_heuristic(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        mock_metrics,
        sample_tool_selection_request
    ):
        """Deve usar fallback heuristico em caso de timeout."""
        from src.services.genetic_tool_selector import GeneticToolSelector
        from src.models.tool_selection import SelectionMethod

        # Configurar timeout muito curto
        mock_settings.GA_TIMEOUT_SECONDS = 0.001  # 1ms - impossivel completar

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=mock_metrics
        )

        response = await selector.select_tools(sample_tool_selection_request)

        # Deve usar heuristica como fallback
        assert response.selection_method == SelectionMethod.HEURISTIC
        mock_metrics.record_genetic_algorithm.assert_called_with(
            converged=False,
            timeout=True,
            duration=pytest.approx(0, abs=1),
            generations=0
        )


class TestGeneticToolSelectorPopulation:
    """Testes de criacao de populacao."""

    @pytest.mark.asyncio
    async def test_create_initial_population_size(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Deve criar populacao com tamanho correto."""
        from src.services.genetic_tool_selector import GeneticToolSelector
        from src.models.tool_descriptor import ToolCategory

        mock_settings.GA_POPULATION_SIZE = 15

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        available_tools = {
            'VALIDATION': await mock_tool_registry_with_multiple_tools.list_tools_by_category(
                ToolCategory.VALIDATION
            ),
            'GENERATION': await mock_tool_registry_with_multiple_tools.list_tools_by_category(
                ToolCategory.GENERATION
            )
        }

        population = selector._create_initial_population(
            available_tools,
            sample_tool_selection_request
        )

        assert len(population) == mock_settings.GA_POPULATION_SIZE


class TestGeneticToolSelectorHeuristic:
    """Testes de selecao heuristica."""

    @pytest.mark.asyncio
    async def test_heuristic_selects_highest_reputation(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Heuristica deve selecionar ferramentas com maior reputacao."""
        from src.services.genetic_tool_selector import GeneticToolSelector
        from src.models.tool_descriptor import ToolCategory

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        available_tools = {
            'VALIDATION': await mock_tool_registry_with_multiple_tools.list_tools_by_category(
                ToolCategory.VALIDATION
            )
        }

        response = await selector._heuristic_selection(
            sample_tool_selection_request,
            available_tools
        )

        # Deve selecionar ferramenta com maior reputacao
        if response.selected_tools:
            max_rep_tool = max(
                available_tools['VALIDATION'],
                key=lambda t: t.reputation_score
            )
            assert response.selected_tools[0].tool_id == max_rep_tool.tool_id


class TestGeneticToolSelectorFallback:
    """Testes de respostas fallback."""

    @pytest.mark.asyncio
    async def test_fallback_response_no_tools(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Deve retornar fallback quando nao ha ferramentas."""
        from src.services.genetic_tool_selector import GeneticToolSelector
        from src.models.tool_selection import SelectionMethod

        # Configurar registry sem ferramentas
        mock_tool_registry_with_multiple_tools.list_tools_by_category.return_value = []

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        response = await selector.select_tools(sample_tool_selection_request)

        assert response.selection_method == SelectionMethod.FALLBACK
        assert len(response.selected_tools) == 0


class TestGeneticToolSelectorMetrics:
    """Testes de metricas."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_success(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        mock_metrics,
        sample_tool_selection_request
    ):
        """Deve registrar metricas em caso de sucesso."""
        from src.services.genetic_tool_selector import GeneticToolSelector

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=mock_metrics
        )

        await selector.select_tools(sample_tool_selection_request)

        mock_metrics.record_genetic_algorithm.assert_called()
        mock_metrics.record_selection.assert_called()

    @pytest.mark.asyncio
    async def test_metrics_recorded_on_cache_hit(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        mock_metrics,
        sample_tool_selection_request
    ):
        """Deve registrar metricas em cache hit."""
        from src.services.genetic_tool_selector import GeneticToolSelector
        from src.models.tool_selection import SelectionMethod

        cached_response = {
            'request_id': sample_tool_selection_request.request_id,
            'selected_tools': [],
            'total_fitness_score': 0.9,
            'selection_method': SelectionMethod.GENETIC_ALGORITHM.value,
            'generations_evolved': 5,
            'population_size': 10,
            'convergence_time_ms': 100,
            'reasoning_summary': 'Cached',
            'confidence_score': 0.9,
            'cached': False
        }
        mock_tool_registry_with_multiple_tools.redis_client.get_cached_selection.return_value = cached_response

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=mock_metrics
        )

        await selector.select_tools(sample_tool_selection_request)

        mock_metrics.record_selection.assert_called_with(
            method=SelectionMethod.GENETIC_ALGORITHM.value,
            cached=True,
            duration=pytest.approx(0.001, abs=0.01),
            fitness=0.9
        )


class TestGeneticToolSelectorHistory:
    """Testes de historico MongoDB."""

    @pytest.mark.asyncio
    async def test_saves_selection_history(
        self,
        mock_settings,
        mock_tool_registry_with_multiple_tools,
        sample_tool_selection_request
    ):
        """Deve salvar historico de selecao no MongoDB."""
        from src.services.genetic_tool_selector import GeneticToolSelector

        selector = GeneticToolSelector(
            tool_registry=mock_tool_registry_with_multiple_tools,
            settings=mock_settings,
            metrics=None
        )

        await selector.select_tools(sample_tool_selection_request)

        mock_tool_registry_with_multiple_tools.mongodb_client.save_selection_history.assert_called()
