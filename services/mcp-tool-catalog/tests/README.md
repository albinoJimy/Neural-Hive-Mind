# Testes do MCP Tool Catalog

Suite de testes para o servico MCP Tool Catalog com cobertura de arquitetura hibrida (MCP Server + Adapters).

## Estrutura

```
tests/
├── conftest.py                    # Fixtures compartilhadas
├── test_tool_executor.py          # Testes unitarios ToolExecutor
├── test_rest_adapter.py           # Testes unitarios RESTAdapter
├── test_mcp_server_client.py      # Testes unitarios MCPServerClient
├── integration/
│   ├── conftest.py                # Fixtures de integracao
│   ├── test_hybrid_execution.py   # Testes de execucao hibrida
│   ├── test_metrics_validation.py # Testes de metricas Prometheus
│   └── test_feedback_loop.py      # Testes de feedback loop
├── performance/
│   └── test_tool_executor_performance.py  # Testes de performance
└── e2e/
    ├── conftest.py                # Fixtures E2E (mock MCP servers)
    ├── test_rest_adapter_real.py  # Testes com servidores HTTP reais
    └── test_mcp_hybrid_execution.sh  # Script E2E completo
```

## Cobertura

| Componente | Cobertura Alvo |
|------------|----------------|
| ToolExecutor | 90% |
| RESTAdapter | 85% |
| MCPServerClient | 85% |
| Metricas | 80% |
| Feedback Loop | 80% |
| **Total** | **85%** |

## Execucao

### Todos os testes
```bash
cd services/mcp-tool-catalog
pytest tests/ -v
```

### Por camada
```bash
# Unitarios
pytest tests/test_*.py -v

# Integracao
pytest tests/integration/ -v

# Performance
pytest tests/performance/ -v --benchmark

# E2E
pytest tests/e2e/ -v
./tests/e2e/test_mcp_hybrid_execution.sh
```

### Com cobertura
```bash
pytest tests/ --cov=src --cov-report=html --cov-report=term
```

## Cenarios Principais

### Execucao Hibrida
1. MCP Server disponivel -> executa via MCP
2. MCP Server indisponivel -> fallback para adapter local
3. Circuit breaker aberto -> fallback automatico
4. Timeout MCP -> fallback com metricas

### Metricas
- `mcp_tool_selections_total` - Counter de selecoes
- `mcp_tool_executions_total` - Counter de execucoes
- `mcp_tool_execution_duration_seconds` - Histogram de latencia
- `mcp_fallback_total` - Counter de fallbacks
- `mcp_circuit_breakers_open` - Gauge de circuit breakers

### Feedback Loop
- Atualizacao de reputacao (sucesso/falha)
- EMA para tempo medio de execucao
- Health status baseado em falhas consecutivas

## Dependencias

```
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-aiohttp>=1.0.5
pytest-cov>=4.1.0
aioresponses>=0.7.4
```
