"""Prometheus metrics for MCP Tool Catalog."""
from prometheus_client import Counter, Gauge, Histogram


class MCPToolCatalogMetrics:
    """Prometheus metrics for MCP Tool Catalog service."""

    def __init__(self):
        """Initialize Prometheus metrics."""
        # Counters
        self.tool_selections_total = Counter(
            "mcp_tool_selections_total",
            "Total number of tool selections",
            ["selection_method", "cached"],
        )

        self.tool_executions_total = Counter(
            "mcp_tool_executions_total",
            "Total number of tool executions",
            ["tool_id", "category", "status"],
        )

        self.cache_hits_total = Counter(
            "mcp_cache_hits_total",
            "Total number of cache hits",
        )

        self.cache_misses_total = Counter(
            "mcp_cache_misses_total",
            "Total number of cache misses",
        )

        self.tool_feedback_total = Counter(
            "mcp_tool_feedback_total",
            "Total number of tool feedback events",
            ["tool_id", "success"],
        )

        self.genetic_algorithm_runs_total = Counter(
            "mcp_genetic_algorithm_runs_total",
            "Total number of genetic algorithm runs",
            ["converged", "timeout"],
        )

        # Métricas para arquitetura híbrida (MCP Server vs Adapter Local)
        self.mcp_server_executions_total = Counter(
            "mcp_server_executions_total",
            "Total de execuções via MCP Server externo",
            ["tool_id", "mcp_server", "status"],
        )

        self.adapter_executions_total = Counter(
            "mcp_adapter_executions_total",
            "Total de execuções via adapters locais (CLI/REST/Container)",
            ["tool_id", "adapter_type", "status"],
        )

        self.execution_route_total = Counter(
            "mcp_execution_route_total",
            "Total de execuções por rota (mcp, adapter, fallback)",
            ["route", "status"],
        )

        self.mcp_fallback_total = Counter(
            "mcp_fallback_total",
            "Total de fallbacks de MCP para adapters locais",
            ["tool_id", "reason"],
        )

        # Histograms
        self.tool_selection_duration_seconds = Histogram(
            "mcp_tool_selection_duration_seconds",
            "Tool selection duration in seconds",
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
        )

        self.genetic_algorithm_duration_seconds = Histogram(
            "mcp_genetic_algorithm_duration_seconds",
            "Genetic algorithm duration in seconds",
            buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
        )

        self.tool_execution_duration_seconds = Histogram(
            "mcp_tool_execution_duration_seconds",
            "Tool execution duration in seconds",
            ["tool_id"],
            buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300],
        )

        self.fitness_score = Histogram(
            "mcp_fitness_score",
            "Fitness score distribution",
            buckets=[0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0],
        )

        # Gauges
        self.active_tool_selections = Gauge(
            "mcp_active_tool_selections",
            "Number of tool selections in progress",
        )

        self.registered_tools_total = Gauge(
            "mcp_registered_tools_total",
            "Total number of registered tools",
            ["category"],
        )

        self.healthy_tools_total = Gauge(
            "mcp_healthy_tools_total",
            "Total number of healthy tools",
            ["category"],
        )

        self.cache_size_bytes = Gauge(
            "mcp_cache_size_bytes",
            "Redis cache size in bytes",
        )

        self.genetic_algorithm_population_size = Gauge(
            "mcp_genetic_algorithm_population_size",
            "Current genetic algorithm population size",
        )

        self.genetic_algorithm_generations = Gauge(
            "mcp_genetic_algorithm_generations",
            "Current genetic algorithm generation number",
        )

        # Gauges para arquitetura híbrida
        self.mcp_clients_connected = Gauge(
            "mcp_clients_connected",
            "Número de clientes MCP conectados",
        )

        self.mcp_circuit_breakers_open = Gauge(
            "mcp_circuit_breakers_open",
            "Número de circuit breakers abertos em clientes MCP",
        )

    def record_selection(self, method: str, cached: bool, duration: float, fitness: float):
        """Record tool selection metrics."""
        self.tool_selections_total.labels(selection_method=method, cached=str(cached)).inc()
        self.tool_selection_duration_seconds.observe(duration)
        self.fitness_score.observe(fitness)

        if cached:
            self.cache_hits_total.inc()
        else:
            self.cache_misses_total.inc()

    def record_tool_execution(
        self,
        tool_id: str,
        category: str,
        status: str,
        duration: float,
        execution_route: str = "adapter",
        adapter_type: str = None,
        mcp_server: str = None
    ):
        """
        Registra métricas de execução de ferramenta.

        Args:
            tool_id: ID da ferramenta
            category: Categoria da ferramenta
            status: 'success' ou 'failure'
            duration: Duração em segundos
            execution_route: 'mcp', 'adapter', ou 'fallback'
            adapter_type: Tipo de adapter (CLI/REST/Container) se route='adapter'
            mcp_server: URL do MCP server se route='mcp'
        """
        # Métricas existentes (backward compatible)
        self.tool_executions_total.labels(tool_id=tool_id, category=category, status=status).inc()
        self.tool_execution_duration_seconds.labels(tool_id=tool_id).observe(duration)

        # Métricas híbridas
        self.execution_route_total.labels(route=execution_route, status=status).inc()

        if execution_route == "mcp" and mcp_server:
            self.mcp_server_executions_total.labels(
                tool_id=tool_id,
                mcp_server=mcp_server,
                status=status
            ).inc()
        elif execution_route == "adapter" and adapter_type:
            self.adapter_executions_total.labels(
                tool_id=tool_id,
                adapter_type=adapter_type,
                status=status
            ).inc()

    def record_feedback(self, tool_id: str, success: bool):
        """Record tool feedback."""
        self.tool_feedback_total.labels(tool_id=tool_id, success=str(success)).inc()

    def record_genetic_algorithm(self, converged: bool, timeout: bool, duration: float, generations: int):
        """Record genetic algorithm metrics."""
        self.genetic_algorithm_runs_total.labels(converged=str(converged), timeout=str(timeout)).inc()
        self.genetic_algorithm_duration_seconds.observe(duration)
        self.genetic_algorithm_generations.set(generations)

    def update_tool_registry(self, category: str, total: int, healthy: int):
        """Update tool registry metrics."""
        self.registered_tools_total.labels(category=category).set(total)
        self.healthy_tools_total.labels(category=category).set(healthy)

    def record_mcp_fallback(self, tool_id: str, reason: str):
        """
        Registra fallback de MCP para adapter local.

        Args:
            tool_id: ID da ferramenta
            reason: Razão do fallback (circuit_breaker, timeout, error)
        """
        self.mcp_fallback_total.labels(tool_id=tool_id, reason=reason).inc()

    def update_mcp_clients_status(self, connected: int, circuit_breakers_open: int = 0):
        """
        Atualiza status dos clientes MCP.

        Args:
            connected: Número de clientes MCP conectados
            circuit_breakers_open: Número de circuit breakers abertos
        """
        self.mcp_clients_connected.set(connected)
        self.mcp_circuit_breakers_open.set(circuit_breakers_open)
