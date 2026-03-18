# Analyst Agents

Serviço de análise avançada do Neural Hive Mind, fornecendo insights analíticos, detecção de anomalias, e integração com MCP Servers.

## Funcionalidades

### REST API V2 (/api/v1/analytics/*)

- **GET /analytics/insights** - Listar insights com paginação e filtros
- **GET /analytics/insights/{id}** - Obter detalhes de insight
- **POST /analytics/insights/query** - Criar nova análise
- **GET /analytics/insights/{id}/export** - Exportar (JSON/CSV/PDF)
- **GET /analytics/metrics** - Métricas Prometheus
- **GET /analytics/timeseries/{metric}** - Obter série temporal
- **GET /analytics/timeseries/{metric}/anomalies** - Detectar anomalias
- **GET /analytics/dashboard** - Dados agregados para dashboard
- **GET /analytics/mcp-health** - Saúde dos servidores MCP

### Integração MCP Servers

- **scout-mcp-server**: Descoberta de código (list_files, search_code, analyze_structure)
- **optimizer-mcp-server**: Otimização (analyze_performance, suggest_refactors, optimize_queries)

### Análise Time-Series

- Detecção de anomalias (Z-Score, IQR, Moving Average)
- Análise de tendências (increasing, decreasing, stable)
- Detecção de sazonalidade
- Cache de séries temporais (24h TTL)

### gRPC Integration

### Compilar Protos
```bash
make proto
```

### Clientes gRPC Disponíveis
- `QueenAgentGRPCClient`: Comunicação com Queen Agent

### Exemplo de Uso
Ver `docs/grpc-integration-guide.md` para exemplos completos.

## Configuração

Variáveis de ambiente adicionais:
- `SCOUT_MCP_URL` - URL do scout MCP server (default: http://scout-mcp-server:8000)
- `OPTIMIZER_MCP_URL` - URL do optimizer MCP server (default: http://optimizer-mcp-server:8001)
- `MCP_TIMEOUT` - Timeout para chamadas MCP (default: 30.0)
- `ANOMALY_THRESHOLD` - Limiar de anomalias (default: 2.5)
- `INSIGHTS_TTL_DAYS` - TTL de insights no MongoDB (default: 90)
- `TS_CACHE_TTL_HOURS` - TTL de cache de time-series (default: 24)

## Testes

```bash
# Unitários
pytest tests/test_insight_repository.py
pytest tests/test_timeseries_analyzer.py
pytest tests/test_mcp_integration.py

# API
pytest tests/test_analytics_api.py

# E2E
pytest tests/test_e2e_analytics.py
```

## Dashboard Grafana

Importar `dashboards/analyst-agents-dashboard.json` para visualização em tempo real.
