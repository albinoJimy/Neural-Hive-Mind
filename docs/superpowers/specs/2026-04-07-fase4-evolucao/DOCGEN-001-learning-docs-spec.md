# DOCGEN-001: Gerador Automático de Documentação de Aprendizado

**Data:** 2026-04-07
**Prioridade:** ALTA
**Estimativa:** L (2-3 semanas)

---

## Metadata

| Campo | Valor |
|-------|-------|
| Componente | Learning Documentation Generator |
| Localização | services/learning-doc-generator/ |
| Status Atual | NÃO_EXISTE (0%) |
| Status Alvo | IMPLEMENTADO (90%+) |

---

## 1. Validação Funcionalidade

### 1.1 Funcionalidade Esperada

Baseado na especificação da Fase 4, o componente deve:
- Extrair insights automáticos de experimentos
- Gerar relatórios de evolução do sistema
- Documentar hipóteses testadas e resultados
- Criar visualizações de progresso
- Manter histórico de decisões aprendidas

### 1.2 Funcionalidade Implementada

**Atual:** N/A (componente não existe)

**Gaps Identificados:**
- ❌ Sistema de geração automática não implementado
- ❌ Extração automática de insights de experimentos
- ❌ Geração de relatórios de evolução
- ❌ Visualizações de progresso
- ❌ Histórico de decisões aprendidas

### 1.3 Gaps de Funcionalidade

- [ ] DOCGEN-001-01: Criar serviço `learning-doc-generator`
- [ ] DOCGEN-001-02: Implementar extractor de insights de experimentos
- [ ] DOCGEN-001-03: Implementar gerador de relatórios Markdown
- [ ] DOCGEN-001-04: Implementar gerador de visualizações (gráficos)
- [ ] DOCGEN-001-05: Implementar armazenamento de histórico (MongoDB)
- [ ] DOCGEN-001-06: Criar API REST para consulta de documentos
- [ ] DOCGEN-001-07: Implementar geração periódica agendada
- [ ] DOCGEN-001-08: Implementar geração on-demand via evento

---

## 2. Validação Testes

### 2.1 Cobertura Unitária

**Atual:** N/A

**Gaps:**
- [ ] DOCGEN-001-09: Testar extração de insights
- [ ] DOCGEN-001-10: Testar geração de Markdown
- [ ] DOCGEN-001-11: Testar geração de visualizações
- [ ] DOCGEN-001-12: Testar persistência no MongoDB

### 2.2 Cobertura Integração

**Gaps:**
- [ ] DOCGEN-001-13: Teste E2E de geração de documento
- [ ] DOCGEN-001-14: Teste de integração com MLflow (experimentos)
- [ ] DOCGEN-001-15: Teste de integração com Kafka (eventos)

---

## 3. Validação Integração

### 3.1 Dependências Externas

| Serviço | Método | Status |
|---------|--------|--------|
| MLflow | Experiment data | ❌ |
| Kafka | Events | ❌ |
| MongoDB | Document storage | ❌ |
| Grafana | Dashboards | ❌ |

### 3.2 Gaps de Integração

- [ ] DOCGEN-001-16: Integração com MLflow para ler experimentos
- [ ] DOCGEN-001-17: Consumer Kafka para eventos de conclusão de experimento
- [ ] DOCGEN-001-18: Integração com MongoDB para persistir documentos
- [ ] DOCGEN-001-19: Integração com Grafana para embed de gráficos
- [ ] DOCGEN-001-20: Webhook para notificar Slack em novo documento

---

## 4. Validação Observabilidade

### 4.1 Métricas Prometheus

**Gaps:**
- [ ] DOCGEN-001-21: `learning_docs_generated_total`
- [ ] DOCGEN-001-22: `learning_docs_generation_duration_seconds`
- [ ] DOCGEN-001-23: `learning_insights_extracted_total`

### 4.2 Tracing OpenTelemetry

**Gaps:**
- [ ] DOCGEN-001-24: Spans para geração de documentos
- [ ] DOCGEN-001-25: Spans para extração de insights

### 4.3 Logging Structlog

**Gaps:**
- [ ] DOCGEN-001-26: Logs estruturados de geração
- [ ] DOCGEN-001-27: Logs de insights extraídos

---

## 5. Validação Documentação

### 5.1 Documentação Técnica

| Doc | Existe | Localização |
|-----|--------|-------------|
| README | ❌ | — |
| API Docs | ❌ | — |
| Examples | ❌ | — |

### 5.2 Gaps de Documentação

- [ ] DOCGEN-001-28: README com instruções de uso
- [ ] DOCGEN-001-29: API Documentation (OpenAPI)
- [ ] DOCGEN-001-30: Examples de documentos gerados
- [ ] DOCGEN-001-31: Template de documento customizável

---

## 6. Tickets Decompostos

### DOCGEN-001-01: Criar serviço `learning-doc-generator`

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Criar estrutura do serviço FastAPI com configuração base.

**Acceptance Criteria:**
- [ ] Projeto criado com FastAPI
- [ ] Configuração (settings, logging)
- [ ] Dockerfile e docker-compose
- [ ] Health check endpoint
- [ ] Estrutura de diretórios

---

### DOCGEN-001-02: Implementar extractor de insights de experimentos

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Implementar módulo para extrair insights de experimentos MLflow.

**Acceptance Criteria:**
- [ ] `ExperimentInsightExtractor` class
- [ ] Conexão com MLflow Tracking Server
- [ ] Extração de: métricas, parâmetros, feature importance
- [ ] Comparação entre runs (baseline vs experiment)
- [ ] Identificação de melhoria/piora
- [ ] Testes unitários

---

### DOCGEN-001-03: Implementar gerador de relatórios Markdown

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Implementar gerador de relatórios em formato Markdown.

**Acceptance Criteria:**
- [ ] `MarkdownReportGenerator` class
- [ ] Template configurável (Jinja2)
- [ ] Seções: Summary, Experiment Details, Results, Insights, Recommendations
- [ ] Tabelas de comparação
- [ ] Code blocks para snippets
- [ ] Testes de geração

---

### DOCGEN-001-04: Implementar gerador de visualizações (gráficos)

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Implementar gerador de gráficos para relatórios.

**Acceptance Criteria:**
- [ ] `PlotGenerator` class
- [ ] Gráficos: line (métricas over time), bar (comparação), scatter (correlações)
- [ ] Export PNG/SVG
- [ ] Integração com Matplotlib/Plotly
- [ ] Testes de geração

---

### DOCGEN-001-05: Implementar armazenamento de histórico (MongoDB)

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Implementar persistência de documentos gerados no MongoDB.

**Acceptance Criteria:**
- [ ] Schema MongoDB para documentos
- [ ] `DocumentRepository` class
- [ ] Indexes: date, experiment_id, tags
- [ ] CRUD operations
- [ ] Testes de integração

---

### DOCGEN-001-06: Criar API REST para consulta de documentos

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Implementar API REST para consultar documentos gerados.

**Endpoints:**
- `POST /api/v1/docs/generate` - Gerar novo documento
- `GET /api/v1/docs` - Listar documentos
- `GET /api/v1/docs/{doc_id}` - Obter documento
- `GET /api/v1/docs/{doc_id}/download` - Download Markdown/PDF

**Acceptance Criteria:**
- [ ] Todos os endpoints implementados
- [ ] Validação de requests
- [ ] Paginação e filtros
- [ ] OpenAPI documentation
- [ ] Testes de integração

---

### DOCGEN-001-07: Implementar geração periódica agendada

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Implementar scheduler para geração automática periódica de documentos.

**Acceptance Criteria:**
- [ ] Scheduler com APScheduler
- [ ] Configuração de cron: diário, semanal, mensal
- [ ] Geração de relatório consolidado do período
- [ ] Publicação em Kafka
- [ ] Testes de scheduling

---

### DOCGEN-001-08: Implementar geração on-demand via evento

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Implementar consumer Kafka para geração de documentos em resposta a eventos.

**Eventos:**
- `experiment.completed` - Gerar relatório de experimento
- `model.promoted` - Gerar relatório de promoção
- `deployment.rolled_back` - Gerar análise de rollback

**Acceptance Criteria:**
- [ ] Consumer Kafka implementado
- [ ] Handlers para cada tipo de evento
- [ ] Geração assíncrona (background tasks)
- [ ] Retry em falha
- [ ] Testes de integração

---

## 7. Template de Documento

```markdown
# Learning Document - {title}

**Generated:** {timestamp}
**Period:** {start_date} to {end_date}
**Experiments Analyzed:** {count}

---

## Executive Summary

{auto-generated summary of key learnings}

## Key Insights

1. **Insight 1:** {description}
   - **Evidence:** {metrics}
   - **Confidence:** {high/medium/low}

2. **Insight 2:** {description}
   - **Evidence:** {metrics}
   - **Confidence:** {high/medium/low}

## Experiments Overview

| ID | Name | Type | Status | Improvement |
|----|------|------|--------|-------------|
| ... | ... | ... | ... | ... |

## Detailed Analysis

### Experiment: {name}

**Hypothesis:** {hypothesis_text}

**Results:**
```
{metrics_table}
```

**Visualization:**
![{caption}]({plot_path})

**Conclusion:** {auto-generated_conclusion}

---

## Recommendations

Based on the analysis, we recommend:

1. {recommendation_1}
2. {recommendation_2}
3. {recommendation_3}

---

## Appendix

- **Data Source:** MLflow runs {run_ids}
- **Generation Time:** {duration}s
- **Template Version:** {version}
```

---

## 8. Resumo Executivo

**Completude Atual:** 0%
**Completude Alvo:** 90%
**Gaps Totais:** 31
**Tickets Propostos:** 8 (acima) + 23 (detalhados nos gaps)
**Estimativa Total:** L (2-3 semanas)

**Dependências:**
- MLflow Tracking Server
- MongoDB
- Kafka
- Python 3.12+

**Riscos:**
- Qualidade dos insights depende de qualidade dos dados
- Geração de relatórios pode ser demorada para muitos experimentos

**Mitigações:**
- Cache de insights extraídos
- Geração assíncrona
- Limitação de escopo (últimos N experimentos)
- Validação humana opcional antes de publicar
