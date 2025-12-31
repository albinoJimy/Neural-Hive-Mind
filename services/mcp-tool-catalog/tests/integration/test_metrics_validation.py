"""
Testes de validacao de metricas Prometheus.

Cobertura:
- Counters (tool_selections_total, tool_executions_total, etc.)
- Histograms (selection_duration, execution_duration, etc.)
- Gauges (active_selections, registered_tools, etc.)
- Labels (execution_route, adapter_type, mcp_server, etc.)
"""

import pytest
from unittest.mock import MagicMock, patch
from prometheus_client import REGISTRY, CollectorRegistry

from src.observability.metrics import MCPToolCatalogMetrics


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def fresh_registry():
    """Registry Prometheus limpo para cada teste."""
    return CollectorRegistry()


@pytest.fixture
def metrics():
    """MCPToolCatalogMetrics com registry padrao."""
    # Nota: Em testes reais, usar registry isolado
    return MCPToolCatalogMetrics()


# ============================================================================
# Testes de Counters
# ============================================================================

class TestCounters:
    """Testes de counters Prometheus."""

    def test_tool_selections_total_incremented(self, metrics):
        """Verifica que counter de selecoes e incrementado."""
        # Registrar selecao
        metrics.record_selection(
            method="genetic_algorithm",
            cached=False,
            duration=1.5,
            fitness=0.85
        )

        # Verificar counter
        counter_value = metrics.tool_selections_total._metrics[
            ("genetic_algorithm", "False")
        ]._value.get()
        assert counter_value >= 1

    def test_tool_executions_total_incremented(self, metrics):
        """Verifica que counter de execucoes e incrementado."""
        metrics.record_tool_execution(
            tool_id="pytest-001",
            category="VALIDATION",
            status="success",
            duration=2.5,
            execution_route="adapter",
            adapter_type="CLI"
        )

        # Verificar counter
        counter_value = metrics.tool_executions_total._metrics[
            ("pytest-001", "VALIDATION", "success")
        ]._value.get()
        assert counter_value >= 1

    def test_cache_hits_total_incremented(self, metrics):
        """Verifica que counter de cache hits e incrementado."""
        # Cache hit
        metrics.record_selection(
            method="cache",
            cached=True,
            duration=0.01,
            fitness=0.9
        )

        counter_value = metrics.cache_hits_total._value.get()
        assert counter_value >= 1

    def test_cache_misses_total_incremented(self, metrics):
        """Verifica que counter de cache misses e incrementado."""
        # Cache miss
        metrics.record_selection(
            method="genetic_algorithm",
            cached=False,
            duration=2.0,
            fitness=0.8
        )

        counter_value = metrics.cache_misses_total._value.get()
        assert counter_value >= 1

    def test_mcp_fallback_total_incremented(self, metrics):
        """Verifica que counter de fallback e incrementado."""
        metrics.record_mcp_fallback(
            tool_id="trivy-001",
            reason="circuit_breaker"
        )

        counter_value = metrics.mcp_fallback_total._metrics[
            ("trivy-001", "circuit_breaker")
        ]._value.get()
        assert counter_value >= 1

    def test_mcp_server_executions_total_incremented(self, metrics):
        """Verifica counter de execucoes via MCP server."""
        metrics.record_tool_execution(
            tool_id="trivy-001",
            category="SECURITY",
            status="success",
            duration=5.0,
            execution_route="mcp",
            mcp_server="http://trivy-mcp:3000"
        )

        counter_value = metrics.mcp_server_executions_total._metrics[
            ("trivy-001", "http://trivy-mcp:3000", "success")
        ]._value.get()
        assert counter_value >= 1

    def test_adapter_executions_total_incremented(self, metrics):
        """Verifica counter de execucoes via adapter."""
        metrics.record_tool_execution(
            tool_id="pytest-001",
            category="VALIDATION",
            status="success",
            duration=1.0,
            execution_route="adapter",
            adapter_type="CLI"
        )

        counter_value = metrics.adapter_executions_total._metrics[
            ("pytest-001", "CLI", "success")
        ]._value.get()
        assert counter_value >= 1

    def test_execution_route_total_incremented(self, metrics):
        """Verifica counter de rotas de execucao."""
        # Execucao via MCP
        metrics.record_tool_execution(
            tool_id="tool-1",
            category="TEST",
            status="success",
            duration=1.0,
            execution_route="mcp"
        )

        # Execucao via adapter
        metrics.record_tool_execution(
            tool_id="tool-2",
            category="TEST",
            status="success",
            duration=1.0,
            execution_route="adapter"
        )

        mcp_count = metrics.execution_route_total._metrics[
            ("mcp", "success")
        ]._value.get()
        adapter_count = metrics.execution_route_total._metrics[
            ("adapter", "success")
        ]._value.get()

        assert mcp_count >= 1
        assert adapter_count >= 1


# ============================================================================
# Testes de Histograms
# ============================================================================

class TestHistograms:
    """Testes de histograms Prometheus."""

    def test_tool_selection_duration_recorded(self, metrics):
        """Verifica que histogram de duracao de selecao e registrado."""
        metrics.record_selection(
            method="genetic_algorithm",
            cached=False,
            duration=2.5,
            fitness=0.85
        )

        # Verificar que histogram tem amostras
        histogram_sum = metrics.tool_selection_duration_seconds._sum.get()
        assert histogram_sum >= 2.5

    def test_tool_execution_duration_recorded(self, metrics):
        """Verifica que histogram de duracao de execucao e registrado."""
        metrics.record_tool_execution(
            tool_id="pytest-001",
            category="VALIDATION",
            status="success",
            duration=3.5,
            execution_route="adapter"
        )

        # Verificar histogram por tool_id
        histogram_sum = metrics.tool_execution_duration_seconds._metrics[
            ("pytest-001",)
        ]._sum.get()
        assert histogram_sum >= 3.5

    def test_genetic_algorithm_duration_recorded(self, metrics):
        """Verifica que histogram de duracao GA e registrado."""
        metrics.record_genetic_algorithm(
            converged=True,
            timeout=False,
            duration=4.2,
            generations=50
        )

        histogram_sum = metrics.genetic_algorithm_duration_seconds._sum.get()
        assert histogram_sum >= 4.2

    def test_fitness_score_recorded(self, metrics):
        """Verifica que histogram de fitness e registrado."""
        metrics.record_selection(
            method="genetic_algorithm",
            cached=False,
            duration=1.0,
            fitness=0.92
        )

        # Verificar que fitness foi registrado
        histogram_sum = metrics.fitness_score._sum.get()
        assert histogram_sum >= 0.92


# ============================================================================
# Testes de Gauges
# ============================================================================

class TestGauges:
    """Testes de gauges Prometheus."""

    def test_active_tool_selections_gauge(self, metrics):
        """Verifica que gauge de selecoes ativas funciona."""
        # Incrementar
        metrics.active_tool_selections.inc()
        assert metrics.active_tool_selections._value.get() >= 1

        # Decrementar
        metrics.active_tool_selections.dec()
        # Nao verificar valor exato pois outros testes podem ter modificado

    def test_registered_tools_total_gauge(self, metrics):
        """Verifica que gauge de ferramentas registradas funciona."""
        metrics.update_tool_registry(
            category="SECURITY",
            total=10,
            healthy=8
        )

        total = metrics.registered_tools_total._metrics[
            ("SECURITY",)
        ]._value.get()
        assert total == 10

    def test_healthy_tools_total_gauge(self, metrics):
        """Verifica que gauge de ferramentas saudaveis funciona."""
        metrics.update_tool_registry(
            category="SECURITY",
            total=10,
            healthy=8
        )

        healthy = metrics.healthy_tools_total._metrics[
            ("SECURITY",)
        ]._value.get()
        assert healthy == 8

    def test_mcp_clients_connected_gauge(self, metrics):
        """Verifica gauge de clientes MCP conectados."""
        metrics.update_mcp_clients_status(
            connected=3,
            circuit_breakers_open=1
        )

        connected = metrics.mcp_clients_connected._value.get()
        assert connected == 3

    def test_mcp_circuit_breakers_open_gauge(self, metrics):
        """Verifica gauge de circuit breakers abertos."""
        metrics.update_mcp_clients_status(
            connected=3,
            circuit_breakers_open=2
        )

        open_breakers = metrics.mcp_circuit_breakers_open._value.get()
        assert open_breakers == 2

    def test_genetic_algorithm_generations_gauge(self, metrics):
        """Verifica gauge de geracoes do GA."""
        metrics.record_genetic_algorithm(
            converged=True,
            timeout=False,
            duration=3.0,
            generations=75
        )

        generations = metrics.genetic_algorithm_generations._value.get()
        assert generations == 75


# ============================================================================
# Testes de Labels
# ============================================================================

class TestLabels:
    """Testes de labels em metricas."""

    def test_metrics_include_execution_route_label(self, metrics):
        """Verifica que label execution_route esta presente."""
        metrics.record_tool_execution(
            tool_id="test-001",
            category="TEST",
            status="success",
            duration=1.0,
            execution_route="mcp"
        )

        # Verificar que metrica com label 'mcp' existe
        assert ("mcp", "success") in metrics.execution_route_total._metrics

    def test_metrics_include_adapter_type_label(self, metrics):
        """Verifica que label adapter_type esta presente."""
        metrics.record_tool_execution(
            tool_id="test-001",
            category="TEST",
            status="success",
            duration=1.0,
            execution_route="adapter",
            adapter_type="REST"
        )

        # Verificar que metrica com label 'REST' existe
        assert ("test-001", "REST", "success") in metrics.adapter_executions_total._metrics

    def test_metrics_include_mcp_server_label(self, metrics):
        """Verifica que label mcp_server esta presente."""
        metrics.record_tool_execution(
            tool_id="trivy-001",
            category="SECURITY",
            status="success",
            duration=2.0,
            execution_route="mcp",
            mcp_server="http://trivy-mcp:3000"
        )

        # Verificar que metrica com mcp_server existe
        assert ("trivy-001", "http://trivy-mcp:3000", "success") in \
            metrics.mcp_server_executions_total._metrics

    def test_metrics_include_category_label(self, metrics):
        """Verifica que label category esta presente."""
        metrics.record_tool_execution(
            tool_id="test-001",
            category="ANALYSIS",
            status="success",
            duration=1.0,
            execution_route="adapter"
        )

        # Verificar que metrica com category existe
        assert ("test-001", "ANALYSIS", "success") in metrics.tool_executions_total._metrics

    def test_metrics_include_status_label(self, metrics):
        """Verifica que label status esta presente para sucesso e falha."""
        # Sucesso
        metrics.record_tool_execution(
            tool_id="test-001",
            category="TEST",
            status="success",
            duration=1.0,
            execution_route="adapter"
        )

        # Falha
        metrics.record_tool_execution(
            tool_id="test-002",
            category="TEST",
            status="failure",
            duration=0.5,
            execution_route="adapter"
        )

        assert ("test-001", "TEST", "success") in metrics.tool_executions_total._metrics
        assert ("test-002", "TEST", "failure") in metrics.tool_executions_total._metrics


# ============================================================================
# Testes de Cenarios Integrados
# ============================================================================

class TestIntegratedScenarios:
    """Testes de cenarios integrados de metricas."""

    def test_complete_mcp_execution_flow_metrics(self, metrics):
        """Testa fluxo completo de execucao MCP com todas as metricas."""
        # 1. Selecao de ferramenta
        metrics.active_tool_selections.inc()

        # 2. Registro de selecao
        metrics.record_selection(
            method="genetic_algorithm",
            cached=False,
            duration=2.0,
            fitness=0.88
        )

        # 3. Execucao via MCP
        metrics.record_tool_execution(
            tool_id="trivy-001",
            category="SECURITY",
            status="success",
            duration=5.0,
            execution_route="mcp",
            mcp_server="http://trivy-mcp:3000"
        )

        # 4. Feedback
        metrics.record_feedback(tool_id="trivy-001", success=True)

        # 5. Finalizar selecao
        metrics.active_tool_selections.dec()

        # Verificacoes
        assert metrics.tool_selections_total._metrics[
            ("genetic_algorithm", "False")
        ]._value.get() >= 1

        assert metrics.mcp_server_executions_total._metrics[
            ("trivy-001", "http://trivy-mcp:3000", "success")
        ]._value.get() >= 1

        assert metrics.tool_feedback_total._metrics[
            ("trivy-001", "True")
        ]._value.get() >= 1

    def test_complete_fallback_flow_metrics(self, metrics):
        """Testa fluxo completo de fallback MCP -> adapter."""
        # 1. Tentativa MCP falha
        metrics.record_mcp_fallback(
            tool_id="trivy-001",
            reason="circuit_breaker"
        )

        # 2. Execucao via adapter
        metrics.record_tool_execution(
            tool_id="trivy-001",
            category="SECURITY",
            status="success",
            duration=10.0,
            execution_route="adapter",
            adapter_type="CONTAINER"
        )

        # Verificacoes
        assert metrics.mcp_fallback_total._metrics[
            ("trivy-001", "circuit_breaker")
        ]._value.get() >= 1

        assert metrics.adapter_executions_total._metrics[
            ("trivy-001", "CONTAINER", "success")
        ]._value.get() >= 1

    def test_multiple_tool_categories_metrics(self, metrics):
        """Testa metricas para multiplas categorias de ferramentas."""
        categories = [
            ("SECURITY", 5, 4),
            ("ANALYSIS", 10, 8),
            ("VALIDATION", 3, 3),
        ]

        for category, total, healthy in categories:
            metrics.update_tool_registry(
                category=category,
                total=total,
                healthy=healthy
            )

        # Verificar cada categoria
        for category, total, healthy in categories:
            reg_total = metrics.registered_tools_total._metrics[
                (category,)
            ]._value.get()
            reg_healthy = metrics.healthy_tools_total._metrics[
                (category,)
            ]._value.get()

            assert reg_total == total
            assert reg_healthy == healthy
