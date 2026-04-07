# Tasks - Analyst Services Implementation

## Epic: ANA-001 - Analyst Agents Missing Services

### Ticket ANA-001.1: EmbeddingService Implementation

- [ ] 1.1 Escrever testes para EmbeddingService
  - [ ] 1.1.1 Test generate_embeddings com sucesso
  - [ ] 1.1.2 Test search_embeddings com resultados
  - [ ] 1.1.3 Test update_embeddings
  - [ ] 1.1.4 Test delete_embeddings
  - [ ] 1.1.5 Test error handling para API calls

- [ ] 1.2 Implementar EmbeddingService core
  - [ ] 1.2.1 Setup de cliente OpenAI/Anthropic (configurável)
  - [ ] 1.2.2 Implementar generate_embeddings()
  - [ ] 1.2.3 Implementar search_embeddings() com cosine similarity
  - [ ] 1.2.4 Implementar update_embeddings()
  - [ ] 1.2.5 Implementar delete_embeddings()
  - [ ] 1.2.6 Cache Redis para embeddings

- [ ] 1.3 Integração com InsightRepository
  - [ ] 1.3.1 Adicionar campo embedding ao modelo Insight
  - [ ] 1.3.2 Index de busca vetorial no MongoDB
  - [ ] 1.3.3 Atualizar repository para gerir embeddings

- [ ] 1.4 Endpoint API V2
  - [ ] 1.4.1 POST /analytics/insights/search - busca semântica
  - [ ] 1.4.2 PUT /analytics/insights/{id}/embedding - atualizar embedding
  - [ ] 1.4.3 DELETE /analytics/insights/{id}/embedding - remover embedding

- [ ] 1.5 Testes de integração E2E
  - [ ] 1.5.1 Test fluxo completo de busca
  - [ ] 1.5.2 Test cache hit/miss
  - [ ] 1.5.3 Test error handling para API downtime

### Ticket ANA-001.2: DataFusionEngine Implementation

- [ ] 2.1 Escrever testes para DataFusionEngine
  - [ ] 2.1.1 Test fuse_data_sources com 2 fontes
  - [ ] 2.1.2 Test resolve_conflicts (last_write_wins)
  - [ ] 2.1.3 Test resolve_conflicts (merge_strategy)
  - [ ] 2.1.4 Test calculate_confidence
  - [ ] 2.1.5 Test get_provenance

- [ ] 2.2 Implementar DataFusionEngine core
  - [ ] 2.2.1 Definir DataSourceConfig (Kafka, MongoDB, ClickHouse, HTTP)
  - [ ] 2.2.2 Implementar fuse_data_sources() com fetch paralelo
  - [ ] 2.2.3 Implementar normalize_data() para schema comum
  - [ ] 2.2.4 Implementar resolve_conflicts() com estratégias
  - [ ] 2.2.5 Implementar calculate_confidence() baseado em source quality
  - [ ] 2.2.6 Implementar get_provenance() para rastrear origem

- [ ] 2.3 Clients para data sources
  - [ ] 2.3.1 KafkaDataSourceClient (consumer groups)
  - [ ] 2.3.2 ClickHouseDataSourceClient (HTTP client)
  - [ ] 2.3.3 HttpDataSourceClient (generic REST APIs)

- [ ] 2.4 Endpoint API V2
  - [ ] 2.4.1 POST /analytics/fusion - fundir fontes de dados
  - [ ] 2.4.2 GET /analytics/fusion/{id}/provenance - obter proveniência

- [ ] 2.5 Testes de integração E2E
  - [ ] 2.5.1 Test fusão MongoDB + ClickHouse
  - [ ] 2.5.2 Test resolução de conflitos
  - [ ] 2.5.3 Test fallback quando source indisponível

### Ticket ANA-001.3: QueryEngine Implementation

- [ ] 3.1 Escrever testes para QueryEngine
  - [ ] 3.1.1 Test parse_query (linguagem natural)
  - [ ] 3.1.2 Test parse_query (SQL-like)
  - [ ] 3.1.3 Test optimize_query com cache
  - [ ] 3.1.4 Test execute_query
  - [ ] 3.1.5 Test validate_query

- [ ] 3.2 Implementar QueryEngine core
  - [ ] 3.2.1 Implementar parse_query() - NLP ou SQL parser
  - [ ] 3.2.2 Implementar validate_query() - sanity checks
  - [ ] 3.2.3 Implementar optimize_query() - cache, índices, paralelização
  - [ ] 3.2.4 Implementar execute_query() - roteamento para fonte correta
  - [ ] 3.2.5 Cache Redis para queries frequentes

- [ ] 3.3 Query Parser (simples)
  - [ ] 3.3.1 Detetar tipo de query (aggregation, filter, join)
  - [ ] 3.3.2 Extrair entidades (métricas, dimensões, filtros)
  - [ ] 3.3.3 Validar sintaxe

- [ ] 3.4 Query Optimizer
  - [ ] 3.4.1 Cache lookup antes de executar
  - [ ] 3.4.2 Push-down de filtros para data source
  - [ ] 3.4.3 Paralelização de subqueries independentes
  - [ ] 3.4.4 Limite de resultados com early termination

- [ ] 3.5 Endpoint API V2
  - [ ] 3.5.1 POST /analytics/query - executar query
  - [ ] 3.5.2 GET /analytics/query/history - histórico de queries
  - [ ] 3.5.3 GET /analytics/query/{id}/results - resultados de query async

- [ ] 3.6 Testes de integração E2E
  - [ ] 3.6.1 Test query completo com cache miss
  - [ ] 3.6.2 Test query com cache hit
  - [ ] 3.6.3 Test query complexa com otimizações

### Ticket ANA-001.4: Integration & Documentation

- [ ] 4.1 Integração com API V2 existente
  - [ ] 4.1.1 Adicionar routers ao main.py
  - [ ] 4.1.2 Atualizar OpenAPI schema
  - [ ] 4.1.3 Configurar dependências no container

- [ ] 4.2 Configurações
  - [ ] 4.2.1 Embedding provider config (OpenAI/Anthropic/local)
  - [ ] 4.2.2 Data source connections config
  - [ ] 4.2.3 Query engine config (cache TTL, limits)

- [ ] 4.3 Documentação
  - [ ] 4.3.1 README dos novos services
  - [ ] 4.3.2 Exemplos de uso da API
  - [ ] 4.3.3 Diagramas de arquitetura

- [ ] 4.4 Métricas e Monitoramento
  - [ ] 4.4.1 Métricas Prometheus para operações
  - [ ] 4.4.2 Health checks para dependências externas
  - [ ] 4.4.3 Tracing para queries complexas

- [ ] 4.5 Validação final
  - [ ] 4.5.1 Todos os testes passando (unit + integration + e2e)
  - [ ] 4.5.2 Coverage >80%
  - [ ] 4.5.3 Linting e formatação (ruff, black)
  - [ ] 4.5.4 Validação de segurança (sem segredos em código)
