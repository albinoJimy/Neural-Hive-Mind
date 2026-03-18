# Technical Specification

This is the technical specification for the spec detailed in @.agent-os/specs/2026-03-18-analyst-agents-expansion/spec.md

## Technical Requirements

### REST API for Insights
- **Framework:** FastAPI (já usado no projeto)
- **Router:** `/api/v1/analytics`
- **Endpoints:**
  - `GET /insights` - List insights com paginação
  - `GET /insights/{id}` - Detalhes do insight
  - `POST /insights/query` - Nova análise
  - `GET /insights/{id}/export` - Export JSON/CSV/PDF
  - `GET /metrics` - Métricas do analyst agent
  - `GET /timeseries/{metric}` - Análise time-series
  - `GET /timeseries/{metric}/anomalies` - Detecção de anomalias
  - `GET /dashboard` - Dados agregados para dashboard

### MCP Client Integration
- **Client:** HTTPMCPClient (de `neural_hive_mcp`)
- **Servers:**
  - `scout-mcp-server` - ferramentas de descoberta de código
  - `optimizer-mcp-server` - ferramentas de otimização
- **Timeout:** 30 segundos por call
- **Retry:** 3 tentativas com exponential backoff

### Time-Series Analysis Service
- **Algoritmos:**
  - Moving Average (tendência)
  - Seasonal Decomposition (STL)
  - Z-Score/Isolation Forest (anomalias)
- **Window:** 7 dias padrão, configurável
- **Resolution:** 1 minuto, 5 minutos, 1 hora, 1 dia

### MongoDB Repository
- **Collection:** `insights`
- **Indexes:**
  - `{created_at: -1}`
  - `{analysis_type: 1, created_at: -1}`
  - `{source_id: 1}`
  - `{tags: 1}`
- **TTL:** 90 dias para insights temporários

### Grafana Dashboard
- **Panels:** 6+ (insights por tipo, anomalias detectadas, tempo de resposta, top análises, distribuição de fontes, tendências)
- **Refresh:** 30 segundos
- **Variables:** analysis_type, time_range

### Integration Points
- **Kafka:** Consumer `analyst_results` (resultados de outros agentes)
- **Queen Agent:** gRPC para coordenação (existente)
- **Prometheus:** Métricas de taxa de insights, latência, erros

## External Dependencies

- **httpx** - HTTP client para MCP (já em requirements)
- **pandas** - Time-series processing (já em requirements)
- **numpy** - Computação estatística (já em requirements)
- **scipy** - Algoritmos de anomalias (já em requirements)
- **reportlab** - Geração de PDF (nova dependência)

### Justification
- `reportlab`: Necessário para exportação de insights em PDF formato

## Performance Criteria
- API response time: < 200ms (p95)
- Time-series analysis: < 2 segundos para 7 dias de dados
- MCP call timeout: 30 segundos
- Max insights per query: 1000
