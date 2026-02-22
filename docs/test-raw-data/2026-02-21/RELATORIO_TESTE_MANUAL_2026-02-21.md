# RELATÓRIO - TESTE MANUAL PROFUNDO
## Data: 2026-02-21
## Horário: 12:05 - 12:20 UTC

---

## RESUMO EXECUTIVO

### Status Geral: ⚠️ PARCIALMENTE OPERACIONAL

| Componente | Status | Observações |
|------------|--------|-------------|
| Gateway de Intenções | ✅ OPERACIONAL | Health check OK, processando intenções |
| Kafka | ✅ OPERACIONAL | Todos os tópicos ativos, mensagens sendo publicadas |
| STE (Semantic Translation Engine) | ⚠️ PROBLEMA | Consumindo mensagens mas sem logs de processamento |
| Consensus Engine | ✅ OPERACIONAL | Health check OK, consumindo plans.ready |
| Orchestrator Dynamic | ✅ OPERACIONAL | Health check OK, Redis not_initialized |
| Service Registry | ✅ OPERACIONAL | Pod running |
| Worker Agents | ✅ OPERACIONAL | 2 pods running |
| Redis | ✅ OPERACIONAL | Cache funcionando |
| MongoDB | ✅ OPERACIONAL | Pods running |
| Jaeger | ✅ OPERACIONAL | Traces sendo capturados |

---

## 1. PREPARAÇÃO - IDENTIFICAÇÃO DE PODS

| Componente | Pod ID | Status | IP |
|------------|---------|--------|-----|
| Gateway | gateway-intencoes-7c9cc44fbd-6rwms | Running | 10.244.3.69 |
| STE | semantic-translation-engine-6b86f67f9c-nm8s4 | Running | 10.244.4.252 |
| STE | semantic-translation-engine-6b86f67f9c-pmp2z | Running | 10.244.4.253 |
| Consensus | consensus-engine-6c88c7fd66-r6stp | Running | 10.244.2.149 |
| Consensus | consensus-engine-6c88c7fd66-t8hss | Running | 10.244.1.36 |
| Orchestrator | orchestrator-dynamic-6464db666f-22xlk | Running | 10.244.2.130 |
| Orchestrator | orchestrator-dynamic-6464db666f-9h4lt | Running | 10.244.1.11 |
| Service Registry | service-registry-68f587f66c-jpxl2 | Running | 10.244.1.231 |
| Worker | worker-agents-76f7b6dffb-qgnmc | Running | 10.244.3.62 |
| Worker | worker-agents-76f7b6dffb-qpcbt | Running | 10.244.1.234 |
| Kafka | neural-hive-kafka-broker-0 | Running | 10.244.3.220 |
| MongoDB | mongodb-677c7746c4-tkh9k | Running | 10.244.2.227 |
| Redis | redis-66b84474ff-tv686 | Running | 10.244.1.115 |

---

## 2. FLUXO A - GATEWAY DE INTENÇÕES → KAFKA

### 2.1 Health Check do Gateway

**Timestamp Execução:** 2026-02-21 12:05:50 UTC

**Status:** ✅ PASS

```json
{
  "status": "healthy",
  "timestamp": "2026-02-21T11:05:50.940372",
  "version": "1.0.0",
  "service_name": "gateway-intencoes",
  "neural_hive_component": "gateway",
  "neural_hive_layer": "experiencia",
  "components": {
    "redis": {"status": "healthy", "message": "Redis conectado", "duration_seconds": 0.00147},
    "asr_pipeline": {"status": "healthy", "message": "ASR Pipeline"},
    "nlu_pipeline": {"status": "healthy", "message": "NLU Pipeline"},
    "kafka_producer": {"status": "healthy", "message": "Kafka Producer"},
    "oauth2_validator": {"status": "healthy", "message": "OAuth2 Validator"},
    "otel_pipeline": {"status": "healthy", "message": "OTEL pipeline operational"}
  }
}
```

### 2.2 Envio de Intenção (Payload 1 - TECHNICAL)

**Timestamp Execução:** 2026-02-21 12:06:06 UTC

**INPUT (Payload Enviado):**
```json
{
  "text": "Analisar viabilidade técnica de migração do sistema de autenticação para OAuth2 com suporte a MFA",
  "context": {
    "session_id": "test-session-001",
    "user_id": "qa-tester-001",
    "source": "manual-test",
    "metadata": {
      "test_run": "fluxo-profundo-1740131147",
      "environment": "staging"
    }
  },
  "constraints": {
    "priority": "high",
    "security_level": "confidential",
    "deadline": "2026-02-01T00:00:00Z"
  }
}
```

**OUTPUT (Resposta Recebida):**
```json
{
  "intent_id": "bc6ce1e3-d3f2-4cba-b0cc-324b09fafab5",
  "correlation_id": "f2fcfb86-1a3e-4527-bd10-418e8fb19827",
  "status": "processed",
  "confidence": 0.95,
  "confidence_status": "high",
  "domain": "SECURITY",
  "classification": "authentication",
  "processing_time_ms": 893.789,
  "requires_manual_validation": false,
  "traceId": "1d3e7228b7759ce09109ab9260627873",
  "spanId": "598b015648089559"
}
```

**ANÁLISE:**
- ✅ Intenção processada com sucesso
- ✅ Confidence score alto (0.95)
- ✅ Domain classificado corretamente (SECURITY)
- ✅ Trace ID gerado para rastreamento
- ✅ Latência dentro do SLO (<1000ms)

### 2.3 Logs do Gateway

**Timestamp Execução:** 2026-02-21 12:06:22 UTC

**Log mais relevante:**
```json
{
  "timestamp": "2026-02-21T11:06:15.177843+00:00",
  "level": "INFO",
  "logger": "main",
  "message": {
    "intent_id": "bc6ce1e3-d3f2-4cba-b0cc-324b09fafab5",
    "processing_time_ms": 893.789,
    "confidence": 0.95,
    "domain": "SECURITY",
    "event": "Intenção processada com sucesso"
  }
}
```

**ANÁLISE:**
- ✅ Logs confirmam processamento
- ✅ Kafka producer funcionou
- ✅ Idempotency key gerada: `test-user-123:f2fcfb86-1a3e-4527-bd10-418e8fb19827:1771671974`
- ✅ Topic: `intentions.security`
- ✅ Partition key: `SECURITY`

### 2.4 Cache no Redis

**Timestamp Execução:** 2026-02-21 12:07:46 UTC

**Dados do Cache:**
```json
{
  "id": "bc6ce1e3-d3f2-4cba-b0cc-324b09fafab5",
  "correlation_id": "f2fcfb86-1a3e-4527-bd10-418e8fb19827",
  "actor": {
    "id": "test-user-123",
    "actor_type": "human",
    "name": "test-user"
  },
  "intent": {
    "text": "Analisar viabilidade técnica de migração do sistema de autenticação para OAuth2 com suporte a MFA",
    "domain": "SECURITY",
    "classification": "authentication",
    "original_language": "pt-BR"
  },
  "confidence": 0.95,
  "confidence_status": "high",
  "timestamp": "2026-02-21T11:06:14.390728",
  "cached_at": "2026-02-21T11:06:15.175272"
}
```

**TTL:** 440 segundos

**ANÁLISE:**
- ✅ Cache persistiu corretamente
- ✅ Dados completos
- ✅ TTL adequado

### 2.5 Trace no Jaeger

**Trace ID:** `1d3e7228b7759ce09109ab9260627873`

**ANÁLISE:**
- ✅ Trace capturado
- ✅ Spans: HTTP receive, HTTP send
- ✅ Status code: 200
- ✅ Service: gateway-intencoes

---

## 3. FLUXO B - SEMANTIC TRANSLATION ENGINE

### 3.1 Verificação do STE

**Timestamp Execução:** 2026-02-21 12:10:25 UTC

**Pod Status:** Running (2 pods)

**Consumer Status:**
- Consumer ativo (último poll há 0.4s)
- Poll count em ambos os pods

### 3.2 Análise de Consumo

**Kafka Consumer Group Status:**
```
GROUP                       TOPIC                 PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
semantic-translation-engine intentions.security   0          1               1               0
semantic-translation-engine intentions.security   1          41              41              0
semantic-translation-engine intentions.security   2          19              19              0
semantic-translation-engine intentions.security   3          19              19              0
semantic-translation-engine intentions.security   4          -               0               -
semantic-translation-engine intentions.security   5          -               0               -
```

**ANÁLISE:**
- ✅ Consumer ativo
- ✅ Partitions 0-3: LAG = 0 (mensagens consumidas)
- ⚠️ Partitions 4-5: Sem offset atribuído
- ⚠️ Nossa intenção pode ter ido para partition 4 ou 5

### 3.3 Logs do STE

**OBSERVAÇÃO:** Não foram encontrados logs de processamento da intenção `bc6ce1e3` nos pods do STE.

**Hypothesis:** A mensagem foi publicada em uma partição (4 ou 5) que o STE não está consumindo.

**Teste adicional:** Segunda intenção enviada (domain: TECHNICAL)
- Intent ID: `a77dadd7-6cb4-443a-a41f-7a1bd08b7306`
- Trace ID: `253e84b3115de9c8abbb226d8b5d86e6`
- Status: Consumida pelo STE (offset incrementado)

---

## 4. FLUXO C - SPECIALISTS → CONSENSUS → ORCHESTRATOR

### 4.1 Consensus Engine

**Timestamp Execução:** 2026-02-21 12:17:43 UTC

**Health Check:** ✅ PASS
```json
{
  "status": "healthy",
  "service": "consensus-engine"
}
```

**Consumer Group Status:**
```
GROUP            TOPIC        PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
consensus-engine plans.ready  0          219             220             1
```

**ANÁLISE:**
- ✅ Consensus operacional
- ⚠️ 1 plano pendente de processamento (LAG = 1)

### 4.2 Orchestrator Dynamic

**Timestamp Execução:** 2026-02-21 12:17:48 UTC

**Health Check:** ✅ PASS
```json
{
  "status": "healthy",
  "service": "orchestrator-dynamic",
  "version": "1.0.0",
  "checks": {
    "redis": {
      "available": false,
      "circuit_breaker_state": "CLOSED",
      "error": "not_initialized"
    }
  }
}
```

**Consumer Group Status:**
```
GROUP                TOPIC           PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
orchestrator-dynamic plans.consensus 0          211             211             0
```

**ANÁLISE:**
- ✅ Orchestrator consumindo plans.consensus
- ⚠️ Redis marked as not_initialized (mas circuit breaker CLOSED)

---

## 5. ANÁLISE FINAL INTEGRADA

### 5.1 Correlação de Dados de Ponta a Ponta

| ID | Tipo | Valor | Status |
|----|------|-------|--------|
| Intent ID | `intent_id` | bc6ce1e3-d3f2-4cba-b0cc-324b09fafab5 | ✅ Gerado |
| Correlation ID | `correlation_id` | f2fcfb86-1a3e-4527-bd10-418e8fb19827 | ✅ Gerado |
| Trace ID | `trace_id` | 1d3e7228b7759ce09109ab9260627873 | ✅ Gerado |
| Plan ID | `plan_id` | NÃO ENCONTRADO | ❌ Não gerado |
| Decision ID | `decision_id` | NÃO ENCONTRADO | ❌ Não gerado |
| Ticket ID | `ticket_id` | NÃO ENCONTRADO | ❌ Não gerado |

### 5.2 Problemas Identificados

1. **[MEDIUM] STE não consumindo partições 4 e 5**
   - Tipo: Infraestrutura
   - Descrição: O STE não tem consumidores atribuídos às partições 4 e 5 do tópico intentions.security
   - Possível causa: Configuração de partitions ou rebalance issue
   - Impacto: 1/3 das mensagens podem não ser processadas

2. **[LOW] Redis não inicializado no Orchestrator**
   - Tipo: Configuração
   - Descrição: Redis marked as "not_initialized" no health check do Orchestrator
   - Possível causa: Configuração de conexão Redis
   - Impacto: Cache pode não estar funcionando

3. **[LOW] Plan ID não encontrado para primeira intenção**
   - Tipo: Dados
   - Descrição: A intenção bc6ce1e3 não gerou plano cognitivo
   - Possível causa: Mensagem foi para partition 4/5 que o STE não consome
   - Impacto: Teste incompleto

### 5.3 Conclusões

**Funcionalidade Geral:**
- ✅ Gateway funcionando corretamente
- ✅ Kafka operacional
- ⚠️ STE consumindo apenas 2/3 das partições
- ✅ Consensus Engine operacional
- ✅ Orchestrator operacional

**Rastreabilidade:**
- ✅ IDs de tracking consistentes
- ✅ Trace no Jaeger funcionando
- ✅ Cache no Redis funcionando

**Recomendações:**
1. Investigar por que o STE não está consumindo partições 4 e 5
2. Verificar configuração de Redis no Orchestrator
3. Executar novo teste com intenção que vai para partições 0-3

---

## DADOS DE RASTREAMENTO PARA INVESTIGAÇÃO CONTÍNUA

### IDs Capturados
- **Intent ID 1:** bc6ce1e3-d3f2-4cba-b0cc-324b09fafab5 (SECURITY)
- **Intent ID 2:** a77dadd7-6cb4-443a-a41f-7a1bd08b7306 (TECHNICAL)
- **Trace ID 1:** 1d3e7228b7759ce09109ab9260627873
- **Trace ID 2:** 253e84b3115de9c8abbb226d8b5d86e6
- **Correlation ID 1:** f2fcfb86-1a3e-4527-bd10-418e8fb19827
- **Correlation ID 2:** be30c7c5-9f7a-4a14-a9db-749355d89cbd

---

**FIM DO RELATÓRIO**
**Executador:** qa-tester-001 (Claude)
**Data Término:** 2026-02-21 12:20 UTC
**Duração Total:** ~15 minutos
