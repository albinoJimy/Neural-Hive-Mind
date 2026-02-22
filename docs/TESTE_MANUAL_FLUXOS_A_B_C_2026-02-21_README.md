# Teste Manual Profundo - Fluxos A-B-C
## Data: 2026-02-21

## Descrição

Este documento contém os resultados do teste manual profundo executado no Neural Hive-Mind (Fluxos A-B-C) em 21 de fevereiro de 2026.

## Arquivos do Teste

### Documentação Principal
- **TESTE_MANUAL_FLUXO_A_2026-02-21.md** (32KB)
  - Documentação completa do teste com 959 linhas
  - Contém INPUT/OUTPUT/ANÁLISE PROFUNDA/EXPLICABILIDADE/PEGADAS para cada etapa
  - Análise detalhada dos Fluxos A (Gateway), B (STE) e C (Orchestrator)

### Dados Capturados
- **test_tracking_ids_2026-02-21.txt** (266B)
  - IDs de rastreabilidade usados no teste
  - intent_id, correlation_id, trace_id, plan_id, decision_id

- **consensus-decision-raw_2026-02-21.txt** (6.1KB)
  - Documento bruto do MongoDB (collection: consensus_decisions)
  - Decisão completa com votos dos 5 especialistas
  - Cognitive plan gerado

- **intent-response_2026-02-21.json** (510B)
  - Resposta RAW do Gateway ao receber a intenção
  - Contém intent_id, correlation_id, trace_id, span_id

- **kafka-messages-consumed_2026-02-21.txt** (4.8KB)
  - Mensagens consumidas do Kafka topic `plans.consensus`
  - Mostra histórico de decisões anteriores

- **jaeger-traces-consensus_2026-02-21.json** (4.8KB)
  - Traces do serviço consensus-engine do Jaeger
  - Apenas health check traces disponíveis

## Resultados Resumidos

### Fluxo A (Gateway) - ✅ FUNCIONAL
- Intenção processada em 685ms
- Confidence score: 0.95 (TECHNICAL/performance)
- Mensagem publicada no Kafka (topic: intentions.technical)
- Cache escrito no Redis (TTL: 415s)
- Gateway saudável (todos os health checks passando)

### Fluxo B (STE) - ⚠️ PARCIALMENTE FUNCIONAL COM ALERTAS CRÍTICOS
- Plano gerado com 1 tarefa de query
- 5 especialistas analisaram o plano
- **CRÍTICO**: 4/5 especialistas com confiança < 10% (9.6%)
- **CRÍTICO**: Aggregated confidence: 21% (abaixo do threshold de 50%)
- **CRÍTICO**: 5 models em estado "degraded"
- **CRÍTICO**: Divergence score: 41% (acima do threshold de 35%)
- **CRÍTICO**: Consensus method: fallback
- Decisão final: review_required (requer intervenção humana)

### Fluxo C (Orchestrator) - ⚠️ EXECUÇÃO BLOQUEADA
- Orchestrator recebeu a decisão do Kafka (offset 207)
- Decisão: review_required bloqueou execução automática
- Execution tickets: 0 (nenhum gerado)
- Todos os serviços UP (Prometheus metrics)

### Observabilidade - ⚠️ INCOMPLETA
- Prometheus: funcional (métricas coletadas)
- Jaeger: traces de negócio ausentes (apenas health checks)
- Logs: disponíveis nos pods

## Problemas Críticos Identificados

1. **Models Degraded** (CRÍTICO)
   - 5 specialists (business, technical, behavior, evolution, architecture) degraded
   - Confiança dos specialists < 10%
   - Provável causa: modelos não treinados ou mal treinados

2. **Baixa Confiança Agregada** (CRÍTICO)
   - Aggregated confidence: 21% (muito abaixo do threshold de 50%)
   - Sistema depende de aprovação humana

3. **Alta Divergência** (CRÍTICO)
   - Divergence score: 41% (acima do threshold de 35%)
   - Specialists não concordam entre si

4. **Consensus Method: Fallback** (CRÍTICO)
   - Sistema usou método de fallback
   - Qualidade das decisões inferior

5. **Traces Ausentes** (ALERTA)
   - Jaeger não capturando traces de negócio
   - Rastreabilidade end-to-end quebrada

6. **Bug no Gateway** (ALERTA)
   - `convert_enum()` converte para UPPER_CASE com hífen (EXACTLY-ONCE)
   - Avro espera UPPER_CASE com underscore (EXACTLY_ONCE)

## IDs de Rastreabilidade

```
INTENT_ID: 327403ce-8292-46cb-a13a-d863de64cc5e
CORRELATION_ID: c3f7e2ca-0d2f-4662-bb9b-58b415c7dad1
TRACE_ID: 53f92ad9258b95fc0e6e7a1d05e39c86
PLAN_ID: d7e564dc-8319-41d0-8411-f636b3cbca46
DECISION_ID: e4457805-4266-49a5-b4d5-f26e72867871
```

## Próximos Passos Recomendados

1. **Treinar/re-treinar os 5 models dos specialists** (prioridade crítica)
2. **Corrigir o bug no `convert_enum()`** do Gateway
3. **Configurar Jaeger** para capturar traces de negócio
4. **Implementar monitoramento** de health dos models
5. **Investigar causa raiz** do estado degraded dos specialists

## Credenciais Usadas (para Investigação)

- **MongoDB**: `mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017`
- **Kafka**: `neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092`
- **Redis**: `redis-66b84474ff-tv686.redis-cluster.svc.cluster.local:6379`

---
*Teste executado manualmente em 2026-02-21*
*Documentação: 959 linhas, 32KB*
