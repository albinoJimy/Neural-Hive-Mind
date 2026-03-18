# Spec Tasks

## Tasks

- [ ] 1. REST API para Insights
  - [ ] 1.1 Escrever testes para AnalyticsRouter
  - [ ] 1.2 Implementar GET /api/v1/analytics/insights (listagem com paginação)
  - [ ] 1.3 Implementar GET /api/v1/analytics/insights/{id} (detalhes)
  - [ ] 1.4 Implementar POST /api/v1/analytics/insights/query (nova análise)
  - [ ] 1.5 Implementar GET /api/v1/analytics/insights/{id}/export (JSON/CSV/PDF)
  - [ ] 1.6 Implementar GET /api/v1/analytics/metrics (Prometheus)
  - [ ] 1.7 Verificar todos os testes passam

- [ ] 2. MCP Client Integration
  - [ ] 2.1 Escrever testes para MCPClientIntegration
  - [ ] 2.2 Implementar HTTPMCPClient wrapper para Analyst Agents
  - [ ] 2.3 Integrar com scout-mcp-server (ferramentas list_files, search_code)
  - [ ] 2.4 Integrar com optimizer-mcp-server (ferramentas analyze_performance)
  - [ ] 2.5 Implementar agregação de resultados de múltiplas tools
  - [ ] 2.6 Adicionar retry com exponential backoff
  - [ ] 2.7 Verificar todos os testes passam

- [ ] 3. Time-Series Analysis Service
  - [ ] 3.1 Escrever testes para TimeSeriesAnalyzer
  - [ ] 3.2 Implementar moving average analysis (tendência)
  - [ ] 3.3 Implementar seasonal decomposition (STL)
  - [ ] 3.4 Implementar anomaly detection (Z-Score, Isolation Forest)
  - [ ] 3.5 Implementar cache no MongoDB (time_series_cache)
  - [ ] 3.6 Verificar todos os testes passam

- [ ] 4. MongoDB Repository e Migration
  - [ ] 4.1 Escrever testes para InsightRepository
  - [ ] 4.2 Criar migration m003_insights_collection.py
  - [ ] 4.3 Implementar InsightRepository (CRUD)
  - [ ] 4.4 Implementar queries por analysis_type, source, tags
  - [ ] 4.5 Implementar TTL configuration
  - [ ] 4.6 Verificar todos os testes passam

- [ ] 5. API Endpoints para Time-Series
  - [ ] 5.1 Escrever testes para TimeSeriesRouter
  - [ ] 5.2 Implementar GET /api/v1/analytics/timeseries/{metric}
  - [ ] 5.3 Implementar GET /api/v1/analytics/timeseries/{metric}/anomalies
  - [ ] 5.4 Implementar GET /api/v1/analytics/dashboard
  - [ ] 5.5 Verificar todos os testes passam

- [ ] 6. Grafana Dashboard
  - [ ] 6.1 Criar dashboard JSON com 6+ painéis
  - [ ] 6.2 Adicionar painel: Insights por Tipo (pie chart)
  - [ ] 6.3 Adicionar painel: Anomalias Detectadas (graph)
  - [ ] 6.4 Adicionar painel: Tempo de Processamento (histogram)
  - [ ] 6.5 Adicionar painel: Top Análises (table)
  - [ ] 6.6 Adicionar painel: Distribuição de Fontes (bar chart)
  - [ ] 6.7 Validar importação no Grafana

- [ ] 7. Integração com Serviços Existentes
  - [ ] 7.1 Escrever testes de integração
  - [ ] 7.2 Integrar API REST com gRPC service existente
  - [ ] 7.3 Consumir eventos Kafka de execution completed
  - [ ] 7.4 Publicar insights no Kafka topic
  - [ ] 7.5 Verificar fluxo E2E com testes

- [ ] 8. Testes E2E e Documentação
  - [ ] 8.1 Escrever teste E2E: API query → insight → export
  - [ ] 8.2 Escrever teste E2E: MCP call → aggregation → dashboard
  - [ ] 8.3 Escreverteste E2E: Time-series analysis → anomaly detection
  - [ ] 8.4 Atualizar README.md com nova API
  - [ ] 8.5 Verificar todos os testes passam (50+ total)

## Resumo de Progresso

**Status:** Planejamento (0/8 tasks)

**Estimativa de Testes:**
- Task 1: 12 testes (2 por endpoint + 2 integração)
- Task 2: 10 testes (MCP integration)
- Task 3: 15 testes (time-series algorithms)
- Task 4: 8 testes (repository)
- Task 5: 8 testes (endpoints time-series)
- Task 6: 0 testes (dashboard Grafana)
- Task 7: 5 testes (integração)
- Task 8: 5 testes (E2E)

**Total Estimado:** 63 testes

**Componentes a Implementar:**
- AnalyticsRouter (8 endpoints REST)
- MCPClientIntegration (scout + optimizer)
- TimeSeriesAnalyzer (3 algoritmos)
- InsightRepository (MongoDB)
- Grafana Dashboard (6+ painéis)
- Migration m003 (insights collection)
