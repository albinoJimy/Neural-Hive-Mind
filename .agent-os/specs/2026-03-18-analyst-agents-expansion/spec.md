# Spec Requirements Document

> Spec: Analyst Agents Expansion
> Created: 2026-03-18
> Status: Planning

## Overview

Expandir o serviço Analyst Agents de 70% para 100% de completude, adicionando API REST para insights, integração com MCP servers, análise avançada de dados com suporte a time-series, e dashboard de analytics com métricas em tempo real.

## User Stories

### API REST para Insights

Como um **engenheiro de dados**, eu quero consultar insights analíticos via REST API, para que eu possa integrar análises do Neural Hive Mind em dashboards externos e aplicações de monitoring.

**Workflow:**
1. Engenheiro faz GET `/api/v1/analytics/insights` com filtros (time_range, analysis_type)
2. Analyst Agents retorna insights paginados com metadados
3. Engenheimer pode acessar insight específico via ID
4. Exportação disponível em JSON/CSV/PDF

### Integração MCP Servers

Como um **arquiteto de sistema**, eu quero que Analyst Agents se integre com MCP Servers, para que análises possam usar ferramentas especializadas (scout, optimizer) para insights mais profundos.

**Workflow:**
1. Analyst Agent recebe requisição de análise complexa
2. Roteia para MCP Server apropriado (scout/optimizer)
3. Agrega resultados de múltiplas ferramentas
4. Retorna insight consolidado com proveniência

### Análise Time-Series

Como um **analista de negócios**, eu quero análise de séries temporais de métricas do sistema, para que eu possa identificar tendências, anomalias e padrões sazonais.

**Workflow:**
1. Analista seleciona métrica e período
2. Analyst Engine aplica detecção de anomalias
3. Retorna gráfico com estações e outliers
4. Sugere ações corretivas baseadas em padrões

## Spec Scope

1. **REST API para Insights** - Endpoints para consultar, criar e exportar insights analíticos
2. **MCP Client Integration** - Cliente HTTP para comunicar com scout-mcp-server e optimizer-mcp-server
3. **Time-Series Analysis** - Serviço para análise de métricas temporais com detecção de anomalias
4. **Analytics Dashboard** - Dashboard Grafana com visualizações de insights em tempo real
5. **Insight Repository** - Repositório MongoDB para persistência de insights com TTL configurável

## Out of Scope

- Rewriting existing gRPC service (mantido para compatibilidade)
- Novos tipos de análise fora de time-series e agregações MCP
- UI/UX customizada (apenas dashboard Grafana)
- Machine learning para predição (apenas detecção de anomalias estatística)

## Expected Deliverable

1. API REST com 8 endpoints operacionais testados via pytest
2. Integração MCP com scout e optimizer servers validada
3. Serviço de time-series com 3+ tipos de análise (tendência, sazonalidade, anomalia)
4. Dashboard Grafana importável com 6+ painéis
5. 50+ testes automatizados passando (unitários + integração)
6. Repositório MongoDB com índices otimizados
