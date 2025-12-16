# Checklist de Validação E2E - Neural Hive-Mind

## Objetivo
Checklist estruturado para validação end-to-end dos Fluxos A, B e C, cobrindo inputs, outputs, logs, métricas, traces e persistência.

---

## FLUXO A: Gateway → Kafka

### A1. Health Check do Gateway
- [ ] **Status HTTP**: 200
- [ ] **Status do serviço**: "healthy"
- [ ] **Componentes**:
  - [ ] Redis: healthy
  - [ ] Kafka Producer: healthy
  - [ ] NLU Pipeline: healthy
  - [ ] ASR Pipeline: healthy

### A2. Envio de Intenção
**Input:**
```json
{
  "text": "Analisar viabilidade técnica de implementar autenticação biométrica no aplicativo móvel",
  "language": "pt-BR",
  "correlation_id": "test-manual-001"
}
```

**Output Esperado:**
- [ ] **HTTP Status**: 200
- [ ] **intent_id**: UUID válido → `_________________`
- [ ] **correlation_id**: "test-manual-001"
- [ ] **status**: "processed"
- [ ] **confidence**: > 0.7 → `_________________`
- [ ] **domain**: identificado → `_________________`
- [ ] **trace_id**: presente → `_________________`
- [ ] **processing_time_ms**: < 500ms → `_________________`

### A3. Logs do Gateway
- [ ] Log de "Processando intenção de texto"
- [ ] Log de NLU com domain e confidence
- [ ] Log de publicação no Kafka (topic: `intentions.technical`)
- [ ] Log de offset do Kafka
- [ ] Sem logs de erro

### A4. Métricas no Prometheus
- [ ] `neural_hive_intents_published_total` incrementou
- [ ] `neural_hive_intent_processing_duration_seconds` presente
- [ ] `neural_hive_nlu_confidence_score` presente

### A5. Trace no Jaeger
- [ ] Trace encontrado com `trace_id`
- [ ] Span: NLU processing
- [ ] Span: Kafka publish
- [ ] Tags: `intent.domain`, `intent.confidence`

### A6. Cache no Redis
- [ ] Key `intent:{intent_id}` existe
- [ ] JSON do IntentEnvelope presente
- [ ] TTL configurado

---

## FLUXO B: STE → Specialists → Plano

### B1. Semantic Translation Engine
**Logs:**
- [ ] Log de consumo do tópico `neural-hive.intents`
- [ ] Log de intent recebido com `intent_id` do Fluxo A
- [ ] Log de geração de plano
- [ ] **plan_id** anotado → `_________________`
- [ ] Lista de specialists identificados → `_________________`
- [ ] Log de publicação no tópico `neural-hive.plans`

**Persistência MongoDB:**
- [ ] Plano persistido em `cognitive_ledger`
- [ ] Campos presentes:
  - [ ] `tasks`
  - [ ] `explainability_token`
  - [ ] `created_at`
  - [ ] `status`
  - [ ] `risk_score`

**Métricas Prometheus:**
- [ ] `neural_hive_plans_generated_total` incrementou
- [ ] `neural_hive_plan_risk_score` presente

**Trace Jaeger:**
- [ ] Spans: semantic parsing, DAG generation, risk scoring
- [ ] Correlação com spans do Gateway

### B2. Specialists (5 total)

#### B2.1. Specialist Business
- [ ] Log de requisição GetOpinion recebida
- [ ] Log de processamento
- [ ] Log de resposta enviada
- [ ] **opinion_id** → `_________________`
- [ ] **confidence** → `_________________`

#### B2.2. Specialist Technical
- [ ] Log de requisição GetOpinion recebida
- [ ] Log de processamento
- [ ] Log de resposta enviada
- [ ] **opinion_id** → `_________________`
- [ ] **confidence** → `_________________`

#### B2.3. Specialist Behavior
- [ ] Log de requisição GetOpinion recebida
- [ ] Log de processamento
- [ ] Log de resposta enviada
- [ ] **opinion_id** → `_________________`
- [ ] **confidence** → `_________________`

#### B2.4. Specialist Evolution
- [ ] Log de requisição GetOpinion recebida
- [ ] Log de processamento
- [ ] Log de resposta enviada
- [ ] **opinion_id** → `_________________`
- [ ] **confidence** → `_________________`

#### B2.5. Specialist Architecture
- [ ] Log de requisição GetOpinion recebida
- [ ] Log de processamento
- [ ] Log de resposta enviada
- [ ] **opinion_id** → `_________________`
- [ ] **confidence** → `_________________`

### B3. Validação Consolidada de Opiniões
**Persistência MongoDB:**
- [ ] 5 opiniões persistidas em `cognitive_ledger`
- [ ] Cada opinião com `specialist_type`

**Métricas Prometheus:**
- [ ] `neural_hive_specialist_opinions_total` = 5

**Traces Jaeger:**
- [ ] 5 spans (um por specialist)
- [ ] Tags: `specialist.type`, `opinion.recommendation`

---

## FLUXO C: Consensus Engine → Orchestrator → Tickets

### C1. Consensus Engine

**Logs:**
- [ ] Log de consumo do tópico `plans.ready`
- [ ] Log de plan recebido com `plan_id` do Fluxo B
- [ ] Logs de chamadas gRPC para 5 specialists
- [ ] Log de agregação de opiniões (método: bayesian)
- [ ] **decision_id** anotado → `_________________`
- [ ] **consensus_score** → `_________________`
- [ ] **divergence_score** → `_________________`
- [ ] Log de publicação no Kafka (topic: `plans.consensus`)
- [ ] Log de publicação de feromônios no Redis

**Persistência MongoDB:**
- [ ] Decisão persistida em `consensus_decisions`
- [ ] Campos presentes:
  - [ ] `specialist_votes`
  - [ ] `consensus_metrics`
  - [ ] `explainability_token`
  - [ ] `decision_id`

**Feromônios Redis:**
- [ ] Keys `pheromone:*` criadas
- [ ] Exemplo: `pheromone:business:workflow-analysis:SUCCESS`
- [ ] Campos: `strength`, `plan_id`, `decision_id`, `created_at`

**Métricas Prometheus:**
- [ ] `neural_hive_consensus_decisions_total` incrementou
- [ ] `neural_hive_consensus_divergence_score` presente
- [ ] `neural_hive_pheromone_strength` presente

**Trace Jaeger:**
- [ ] Spans: plan consumption, specialist orchestration, bayesian aggregation, decision publish
- [ ] Correlação com spans anteriores (Gateway → STE → Specialists)

### C2. Orchestrator Dynamic

**Logs:**
- [ ] Log de consumo do tópico `plans.consensus`
- [ ] Log de decisão recebida com `decision_id` do C1
- [ ] Logs de geração de tickets
- [ ] **ticket_id** (primeiro) → `_________________`
- [ ] **Número de tickets gerados** → `_________________`
- [ ] Log de publicação no Kafka (topic: `execution.tickets`)
- [ ] Log de persistência no MongoDB

**Persistência MongoDB:**
- [ ] Tickets persistidos em `execution_tickets`
- [ ] Quantidade correta de tickets
- [ ] Campos de cada ticket:
  - [ ] `status`
  - [ ] `priority`
  - [ ] `sla.deadline`
  - [ ] `dependencies[]`

**Métricas Prometheus:**
- [ ] `neural_hive_execution_tickets_generated_total` incrementou
- [ ] `neural_hive_orchestrator_processing_duration_seconds` presente

**Trace Jaeger:**
- [ ] Spans: decision consumption, ticket generation, Kafka publish
- [ ] **Trace completo E2E**: Gateway → STE → Specialists → Consensus → Orchestrator

---

## VALIDAÇÃO CONSOLIDADA E2E

### V1. Correlação Completa no MongoDB
```bash
INTENT_ID="<intent_id_anotado>"
```

**Verificações:**
- [ ] `cognitive_ledger` contém:
  - [ ] 1 intent
  - [ ] 1 plan
  - [ ] 5 opinions
- [ ] `consensus_decisions` contém 1 decisão com `intent_id`
- [ ] `execution_tickets` contém N tickets com `intent_id`

### V2. Trace Completo no Jaeger
- [ ] Trace encontrado com `trace_id` inicial
- [ ] Presença de todos os spans:
  - [ ] Gateway (NLU, Kafka publish)
  - [ ] STE (semantic parsing, DAG generation)
  - [ ] 5 Specialists (opinion generation)
  - [ ] Consensus Engine (aggregation, decision)
  - [ ] Orchestrator (ticket generation)
- [ ] Duração total E2E: `_________________` ms
- [ ] Latências por componente anotadas

### V3. Métricas Agregadas no Prometheus
- [ ] Taxa de intenções (últimos 5min): consistente
- [ ] Taxa de planos: consistente
- [ ] Taxa de decisões: consistente
- [ ] Taxa de tickets: consistente
- [ ] **Sem perdas de mensagens**

### V4. Feromônios Agregados no Redis
- [ ] Contagem total de keys `pheromone:*`: `_________________`
- [ ] Força líquida de exemplo verificada

### V5. Memory Layer API (Opcional)
- [ ] HTTP Status: 200
- [ ] Resposta contém:
  - [ ] `intent_id` correto
  - [ ] `status`: "completed"
  - [ ] `plan` com `plan_id` e `specialists_consulted`
  - [ ] `opinions[]` com 5 opiniões
  - [ ] `consensus` com decisão final

---

## RESUMO DE MÉTRICAS COLETADAS

| Métrica | Valor | Status |
|---------|-------|--------|
| Tempo total E2E | _____ ms | ⏱️ |
| Gateway latency | _____ ms | ⏱️ |
| STE latency | _____ ms | ⏱️ |
| Consensus Engine latency | _____ ms | ⏱️ |
| Orchestrator latency | _____ ms | ⏱️ |
| Specialists responderam | ___/5 | 📊 |
| Confidence final | _____ | 📊 |
| Consensus score | _____ | 📊 |
| Divergence score | _____ | 📊 |
| Tickets gerados | _____ | 📊 |
| Erros encontrados | _____ | ❌ |

---

## OBSERVAÇÕES E ISSUES

```
[Anotar aqui qualquer comportamento inesperado, erros, timeouts, ou insights]








```

---

## STATUS FINAL

- [ ] ✅ **PASS**: Todos os fluxos funcionaram corretamente
- [ ] ⚠️ **PARTIAL**: Alguns componentes falharam (detalhar acima)
- [ ] ❌ **FAIL**: Falha crítica no pipeline (detalhar acima)

**Data da validação**: _______________  
**Executado por**: _______________  
**Ambiente**: Kubeadm (1 master + 2 workers)
