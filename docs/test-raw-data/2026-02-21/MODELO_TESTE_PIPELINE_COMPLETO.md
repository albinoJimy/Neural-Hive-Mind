# MODELO DE TESTE MANUAL - PIPELINE COMPLETO NEURAL HIVE-MIND
## Data de Execução: ___ / ___ / ____
## Horário de Início: __:__:__ UTC
## Horário de Término: __:__:__ UTC
## Testador: ________________________
## Ambiente: [ ] Dev [ ] Staging [ ] Production
## Objetivo: Validar o fluxo completo do pipeline de ponta a ponta, capturando evidências em cada etapa.

---

## PREPARAÇÃO DO AMBIENTE

### 1.1 Verificação de Pods (Execução Atual)

| Componente | Pod ID | Status | IP | Namespace | Age |
|------------|---------|--------|----|-----------|-----|
| Gateway | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| STE (Replica 1) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| STE (Replica 2) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Consensus (Replica 1) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Consensus (Replica 2) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Orchestrator (Replica 1) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Orchestrator (Replica 2) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Service Registry | service-registry-68f587f66c-________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Specialist (Security) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Specialist (Technical) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Specialist (Business) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Specialist (Infrastructure) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Workers (Replica 1) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Workers (Replica 2) | _________________________________ | [ ] Running [ ] Error | 10.244.__.__ | neural-hive | __h |
| Kafka Broker | neural-hive-kafka-broker-0 | [ ] Running [ ] Error | 10.244.__.__ | kafka | __h |
| MongoDB | mongodb-677c7746c4-__________ | [ ] Running [ ] Error | 10.244.__.__ | mongodb-cluster | __h |
| Redis | redis-66b84474ff-__________ | [ ] Running [ ] Error | 10.244.__.__ | redis-cluster | __h |
| Jaeger | neural-hive-jaeger-5fbd6fffcc-________ | [ ] Running [ ] Error | 10.244.__.__ | observability | __h |
| Prometheus | prometheus-neural-hive-__________ | [ ] Running [ ] Error | 10.244.__.__ | observability | __h |

**STATUS GERAL:** [ ] Todos pods running [ ] Há pods com erro [ ] Há pods não listados

### 1.2 Credenciais e Endpoints Fixos (DADOS ESTÁTICOS)

**MongoDB Connection:**
```
URI: mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017
Database: neural_hive
Collections disponíveis: 
  - cognitive_plans
  - opinions
  - decisions
  - tickets
  - executions
  - telemetry_events
```

**Kafka Bootstrap:**
```
Bootstrap servers: neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092

Topics disponíveis:
  [ ] intentions.security
  [ ] intentions.technical
  [ ] intentions.business
  [ ] intentions.infrastructure
  [ ] intentions.validation
  [ ] plans.ready
  [ ] plans.consensus
  [ ] opinions.ready
  [ ] decisions.ready
  [ ] execution.tickets
  [ ] workers.status
  [ ] workers.capabilities
  [ ] workers.discovery
  [ ] telemetry.events
```

**Redis Connection:**
```
Host: redis-redis-cluster.svc.cluster.local
Port: 6379
Password: (nenhum - sem autenticação)
```

**Jaeger:**
```
UI: http://localhost:16686 (via port-forward)
API: http://neural-hive-jaeger.observability.svc.cluster.local:16686/api/traces
```

**Prometheus:**
```
UI: http://localhost:9090 (via port-forward)
API: http://neural-hive-prometheus-kub-prometheus.observability.svc.cluster.local:9090/api/v1/query
```

**Service Registry:**
```
Endpoint: http://service-registry.neural-hive.svc.cluster.local:8080
APIs disponíveis:
  - GET /services
  - GET /workers
  - GET /capabilities
  - POST /register
```

### 1.3 Checklist Pré-Teste

[ ] Todos os pods estão Running
[ ] Port-forward Gateway ativo (porta 8000:80)
[ ] Port-forward Jaeger ativo (porta 16686:16686)
[ ] Port-forward Prometheus ativo (porta 9090:9090)
[ ] Acesso ao MongoDB verificado
[ ] Acesso ao Redis verificado
[ ] Accesso ao Kafka verificado
[ ] Todos os topics Kafka existem
[ ] Consumer groups criados e ativos
[ ] Service Registry respondendo
[ ] Documento de teste preenchido e salvo

---

## FLUXO A - Gateway de Intenções → Kafka

### 2.1 Health Check do Gateway

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Gateway:** _________________________________
**Endpoint:** `/health`

**INPUT (Comando Executado):**
```
kubectl port-forward -n neural-hive svc/gateway-intencoes 8000:80 &
curl -s http://localhost:8000/health | jq .
```

**OUTPUT (Dados Recebidos - RAW JSON):**
```json
{
  "status": "____________",
  "timestamp": "____________",
  "version": "________",
  "service_name": "________",
  "neural_hive_component": "________",
  "neural_hive_layer": "________",
  "components": {
    "redis": {
      "status": "____________",
      "message": "____________",
      "duration_seconds": _________
    },
    "asr_pipeline": {
      "status": "____________",
      "message": "____________",
      "duration_seconds": _________
    },
    "nlu_pipeline": {
      "status": "____________",
      "message": "____________",
      "duration_seconds": _________
    },
    "kafka_producer": {
      "status": "____________",
      "message": "____________",
      "duration_seconds": _________
    },
    "oauth2_validator": {
      "status": "____________",
      "message": "____________",
      "duration_seconds": _________
    },
    "otel_pipeline": {
      "status": "____________",
      "message": "____________",
      "duration_seconds": _________,
      "details": {
        "otel_endpoint": "____________",
        "service_name": "________",
        "collector_reachable": [ ] true [ ] false,
        "trace_export_verified": [ ] true [ ] false
      }
    }
  }
}
```

**ANÁLISE:**
1. Status geral: [ ] healthy [ ] unhealthy [ ] degraded
2. Componentes verificados:
   [ ] Redis: [ ] OK [ ] Falha
   [ ] ASR Pipeline: [ ] OK [ ] Falha
   [ ] NLU Pipeline: [ ] OK [ ] Falha
   [ ] Kafka Producer: [ ] OK [ ] Falha
   [ ] OAuth2 Validator: [ ] OK [ ] Falha
   [ ] OTEL Pipeline: [ ] OK [ ] Falha
3. Latências (ms): Redis: ___ ASR: ___ NLU: ___ Kafka: ___ OAuth2: ___ OTEL: ___
4. Conexões externas:
   [ ] Redis conectado
   [ ] Kafka configurado
   [ ] OTEL conectado ao collector
5. Anomalias: [ ] Nenhuma [ ] Descrever: ___________________________________

---

### 2.2 Envio de Intenção (Payload de Teste)

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Gateway:** _________________________________
**Endpoint:** `POST /intentions`
**Payload Selecionado:** [ ] SECURITY [ ] TECHNICAL [ ] BUSINESS [ ] INFRASTRUCTURE

**INPUT (Payload Enviado - RAW JSON):**

```json
{
  "text": "Analisar viabilidade técnica de migração do sistema de autenticação para OAuth2 com suporte a MFA",
  "context": {
    "session_id": "test-session-__________",
    "user_id": "qa-tester-__________",
    "source": "manual-test",
    "metadata": {
      "test_run": "pipeline-completo-__________",
      "environment": "__________",
      "timestamp": "2026-__-__T__:__:__:__Z"
    }
  },
  "constraints": {
    "priority": "high",
    "security_level": "confidential",
    "deadline": "2026-__-__T__:__:__:__Z"
  }
}
```

**OUTPUT (Resposta Recebida - RAW JSON):**

```json
{
  "intent_id": "________________________________",
  "correlation_id": "________________________________",
  "status": "____________",
  "confidence": ________,
  "confidence_status": "___________",
  "domain": "____________",
  "classification": "____________",
  "processing_time_ms": ________.___,
  "requires_manual_validation": [ ] true [ ] false,
  "routing_thresholds": {
    "high": ________,
    "low": ________,
    "adaptive_used": [ ] true [ ] false
  },
  "traceId": "____________________________________________________",
  "spanId": "____________________________________"
}
```

**ANÁLISE:**
1. Intent ID gerado: ________________________________________
2. Correlation ID gerado: ________________________________________
3. Confidence score: ________ [ ] Alto [ ] Médio [ ] Baixo
4. Domain classificado: ______________ [ ] Esperado [ ] Inesperado
5. Latência de processamento: ________.___ ms [ ] <100ms [ ] 100-500ms [ ] >500ms
6. Requires validation: [ ] Sim [ ] Não
7. Trace ID gerado: ______________________________________________________

**DADOS PARA RASTREAMENTO:**
- Intent ID: ________________________________________
- Correlation ID: ________________________________________
- Trace ID: ______________________________________________________
- Span ID: ______________________________________
- Topic de destino: intentions.____________
- Timestamp envio: 2026-__-__ __:__:__ UTC
- Timestamp resposta: 2026-__-__ __:__:__ UTC

---

### 2.3 Logs do Gateway - Captura e Análise

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Gateway:** _________________________________

**INPUT (Comando Executado):**
```
kubectl logs --tail=500 -n neural-hive _________________________________ | \
  grep -E "(intent_id|correlation_id|trace_id|Processando|NLU|Kafka)" | \
  jq -r 'select(.timestamp | contains("'__'"))'
```

**OUTPUT (Logs Relevantes - RAW):**
```
[INSERIR LOGS AQUI - últimos 10-20 linhas relevantes]
```

**ANÁLISE DE SEQUÊNCIA:**

| Etapa | Timestamp | Ação | Status |
|-------|-----------|-------|--------|
| Recebimento da intenção | 2026-__-__ __:__:__.___ | _________________________________ | [ ] OK |
| NLU processamento | 2026-__-__ __:__:__.___ | _________________________________ | [ ] OK |
| Routing decision | 2026-__-__ __:__:__.___ | _________________________________ | [ ] OK |
| Preparação Kafka | 2026-__-__ __:__:__.___ | _________________________________ | [ ] OK |
| Serialização mensagem | 2026-__-__ __:__:__.___ | _________________________________ | [ ] OK |
| Publicação Kafka | 2026-__-__ __:__:__.___ | _________________________________ | [ ] OK |
| Confirmação sucesso | 2026-__-__ __:__:__.___ | _________________________________ | [ ] OK |

**TEMPOS DE PROCESSAMENTO:**
- NLU Pipeline: _________ ms
- Serialização: _________ ms
- Publicação: _________ ms
- Tempo total: _________ ms

**ANOMALIAS DETECTADAS:**
[ ] Nenhuma anomalia
[ ] Erros nos logs: ________________________________________
[ ] Warnings nos logs: ________________________________________
[ ] Performance anormal: ________________________________________

---

### 2.4 Mensagem no Kafka - Captura Completa

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Kafka:** neural-hive-kafka-broker-0
**Topic:** `intentions.____________` (baseado no domain)
**Intent ID (Capturado em 2.2):** ________________________________________

**INPUT (Comando Executado):**
```
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.____________ \
  --from-beginning \
  --max-messages 3 \
  --property print.key=true \
  --property key.separator=" : "
```

**OUTPUT (Mensagem Capturada - RAW):**
```
[INSERIR MENSAGEM KAFKA AQUI - formato Avro binário visível]
```

**ANÁLISE DA MENSAGEM:**

1. Formato: [ ] Avro binário [ ] JSON [ ] Texto plano
2. Schema ID: H____________________________________
3. Schema Version: ______.__
4. Intent ID na mensagem: ________________________________________ [ ] Matches
5. Partition key: _______________
6. Offset: _____
7. Partition: __
8. Tamanho da mensagem: _____ bytes
9. Timestamp Kafka: ___________

**CAMPOS DA MENSAGEM:**
[ ] Intent ID: ________________________________________
[ ] Correlation ID: ________________________________________
[ ] User ID: _______________
[ ] Actor Type: _______________
[ ] Intent Text: _________________________________________________
[ ] Domain: _______________
[ ] Classification: _______________
[ ] Language: ______
[ ] Original Text: _________________________________________________
[ ] Entities: [ ] Presentes [ ] Ausentes
  - Entity 1: _______________ (Confiança: ___)
  - Entity 2: _______________ (Confiança: ___)
  - Entity 3: _______________ (Confiança: ___)

**ANOMALIAS:**
[ ] Nenhuma
[ ] Schema incompatível: ________________________________________
[ ] Campos faltando: ________________________________________
[ ] Campos extras: ________________________________________

---

### 2.5 Cache no Redis - Verificação de Persistência

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Redis:** _________________________________
**Intent ID (Capturado em 2.2):** ________________________________________

**INPUT (Comandos Executados):**
```
# Listar chaves por intent_id
kubectl exec -n redis-cluster _________________________________ -- \
  redis-cli KEYS "*intent:*__________________________*"

# Obter cache da intenção
kubectl exec -n redis-cluster _________________________________ -- \
  redis-cli GET "intent:__________________________"

# Obter contexto enriquecido
kubectl exec -n redis-cluster _________________________________ -- \
  redis-cli GET "context:enriched:__________________________"

# Verificar TTL (opcional)
kubectl exec -n redis-cluster _________________________________ -- \
  redis-cli TTL "intent:__________________________"
```

**OUTPUT (Cache da Intenção - RAW JSON):**
```json
[INSERIR CACHE DA INTENÇÃO AQUI]
```

**OUTPUT (Contexto Enriquecido - RAW JSON):**
```json
[INSERIR CONTEXTO ENRIQUECIDO AQUI]
```

**ANÁLISE DO CACHE:**

| Item | Valor | Status |
|------|-------|--------|
| Chave intent presente? | [ ] Sim [ ] Não | [ ] OK |
| Chave context presente? | [ ] Sim [ ] Não | [ ] OK |
| TTL configurado? | ___ segundos [ ] -1 (sem expiração) | [ ] OK |
| Correlation ID | _________________________________ | [ ] OK |
| Actor ID | _________________________________ | [ ] OK |
| Domain | _______________ | [ ] OK |
| Confidence | ________ | [ ] OK |
| Entities count | ___ entidades | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Cache inconsistente com resposta do Gateway: ________________________
[ ] TTL muito curto/muito longo: ________________________
[ ] Campos faltando no cache: ________________________

---

### 2.6 Métricas no Prometheus - Coleta

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Prometheus:** _________________________________
**Intent ID (Capturado em 2.2):** ________________________________________

**INPUT (Comandos Executados):**
```
# Queries Prometheus
curl -s "http://localhost:9090/api/v1/query?query=neural_hive_requests_total{neural_hive_component=\"gateway\"}" | jq .

curl -s "http://localhost:9090/api/v1/query?query=neural_hive_captura_duration_seconds{neural_hive_component=\"gateway\"}" | jq .

curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95, rate(neural_hive_captura_duration_seconds_bucket{neural_hive_component=\"gateway\"}[5m]))" | jq .

curl -s "http://localhost:9090/api/v1/query?query=rate(neural_hive_requests_total[1m])" | jq .
```

**OUTPUT (Métricas Capturadas - RAW):**
```
[INSERIR MÉTRICAS PROMETHEUS AQUI]
```

**ANÁLISE DE MÉTRICAS:**

| Métrica | Valor | Status |
|---------|-------|--------|
| Requests total | _____ requests | [ ] Disponível |
| Requests rate (1m) | _____ req/s | [ ] Disponível |
| Captura duration (p50) | _____ ms | [ ] Disponível |
| Captura duration (p95) | _____ ms | [ ] Disponível |
| Captura duration (p99) | _____ ms | [ ] Disponível |
| Error rate | _____ % | [ ] Disponível |

**LABELS PRESENTES:**
[ ] domain: _______________
[ ] classification: _______________
[ ] confidence_status: _______________
[ ] status: _______________
[ ] user_id: _______________

**ANOMALIAS:**
[ ] Nenhuma
[ ] Métricas não disponíveis: ________________________
[ ] Métricas em zero: ________________________
[ ] Labels incorretos: ________________________

---

### 2.7 Trace no Jaeger - Análise Completa

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Jaeger:** _________________________________
**Trace ID (Capturado em 2.2):** ______________________________________________________

**INPUT (Comando Executado):**
```
# Buscar trace por ID
curl -s "http://neural-hive-jaeger.observability.svc.cluster.local:16686/api/traces/____________________________________________________" | jq .

# Ou via UI
# http://localhost:16686/trace/____________________________________________________
```

**OUTPUT (Trace Capturado - RAW JSON):**
```
[INSERIR TRACE DO JAEGER AQUI - estrutura de spans]
```

**ANÁLISE DO TRACE:**

| Item | Valor | Status |
|------|-------|--------|
| Trace encontrado? | [ ] Sim [ ] Não | [ ] OK |
| Número de spans | _____ spans | [ ] OK |
| Service principal | _______________ | [ ] OK |
| Span raiz | _______________ | [ ] OK |
| Duração total | _____ ms | [ ] OK |

**TOP 5 SPANS POR DURAÇÃO:**

| Posição | Span ID | Operation Name | Duration | Service |
|---------|----------|----------------|----------|---------|
| 1 | ______________________ | _______________ | _____ ms | _______________ |
| 2 | ______________________ | _______________ | _____ ms | _______________ |
| 3 | ______________________ | _______________ | _____ ms | _______________ |
| 4 | ______________________ | _______________ | _____ ms | _______________ |
| 5 | ______________________ | _______________ | _____ ms | _______________ |

**TAGS DO TRACE:**
[ ] Traceparent: ______________________
[ ] Correlation-ID: ______________________
[ ] User-ID: _______________
[ ] Timestamp: ___________

**ANOMALIAS:**
[ ] Nenhuma
[ ] Trace não encontrado: ________________________
[ ] Spans com erro: ________________________
[ ] Spans com duração anormal: ________________________

---

## FLUXO B - Semantic Translation Engine → Plano Cognitivo

### 3.1 Verificação do STE - Estado Atual

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod STE:** _________________________________

**INPUT (Comandos Executados):**
```
# Status do pod
kubectl get pod -n neural-hive _________________________________

# Health check (via port-forward)
kubectl port-forward -n neural-hive svc/semantic-translation-engine 8001:8000 &
curl -s http://localhost:8001/health | jq .

# Consumer group status
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group semantic-translation-engine \
  --describe
```

**OUTPUT (Estado do STE):**

```
Pod Status:
[INSERIR STATUS DO POD AQUI]

Health Check:
[INSERIR HEALTH CHECK AQUI]

Consumer Group Status:
[INSERIR CONSUMER GROUP STATUS AQUI]
```

**ANÁLISE DO STE:**

| Componente | Status | Observações |
|-----------|--------|-------------|
| Pod | [ ] Running [ ] Error | ________________________ |
| Health Check | [ ] OK [ ] Falha | ________________________ |
| MongoDB | [ ] Conectado [ ] Desconectado | ________________________ |
| Neo4j | [ ] Conectado [ ] Desconectado | ________________________ |
| Kafka Consumer | [ ] Ativo [ ] Inativo | ________________________ |

**CONSUMER GROUP DETAILS:**

| Topic | Partition | Current Offset | Log End Offset | LAG | Status |
|-------|-----------|----------------|-----------------|-----|--------|
| intentions.security | __ | _________ | _________ | _____ | [ ] OK |
| intentions.technical | __ | _________ | _________ | _____ | [ ] OK |
| intentions.business | __ | _________ | _________ | _____ | [ ] OK |
| intentions.infrastructure | __ | _________ | _________ | _____ | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] LAG alto (>10): ________________________
[ ] Pod em CrashLoopBackOff: ________________________
[ ] Health check falhando: ________________________

---

### 3.2 Logs do STE - Consumo da Intenção

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod STE:** _________________________________
**Intent ID (Capturado em 2.2):** ________________________________________
**Correlation ID (Capturado em 2.2):** ________________________________________

**INPUT (Comando Executado):**
```
kubectl logs --tail=1000 -n neural-hive _________________________________ | \
  grep -E "(intent_id|correlation_id|trace_id|Message received|Processando intent)" | \
  grep "__________________________\|__________________________\|____________________________________________________"
```

**OUTPUT (Logs Relevantes - RAW):**
```
[INSERIR LOGS DO STE AQUI - busca por nossa intenção]
```

**ANÁLISE DE CONSUMO:**

| Item | Valor | Status |
|------|-------|--------|
| Intenção consumida? | [ ] Sim [ ] Não | [ ] OK |
| Timestamp de consumo | 2026-__-__ __:__:__.___ UTC | [ ] OK |
| Topic de consumo | intentions.____________ | [ ] OK |
| Partition | __ | [ ] OK |
| Offset consumido | _____ | [ ] OK |
| Erro de deserialização? | [ ] Sim [ ] Não | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Intenção não consumida após 60s: ________________________
[ ] Erro de deserialização Avro: ________________________
[ ] Schema incompatível: ________________________

---

### 3.3 Logs do STE - Geração do Plano Cognitivo

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod STE:** _________________________________

**INPUT (Comando Executado):**
```
kubectl logs --tail=2000 -n neural-hive _________________________________ | \
  grep -E "(plano gerado|plan_id|generated.*plan|cognitive.*plan|tasks.*created)" | \
  tail -20
```

**OUTPUT (Logs Relevantes - RAW):**
```
[INSERIR LOGS DE GERAÇÃO DE PLANO AQUI]
```

**ANÁLISE DE GERAÇÃO DE PLANO:**

| Item | Valor | Status |
|------|-------|--------|
| Plano gerado? | [ ] Sim [ ] Não | [ ] OK |
| Plan ID gerado | ________________________________________ | [ ] OK |
| Timestamp de geração | 2026-__-__ __:__:__.___ UTC | [ ] OK |
| Número de tarefas | _____ tarefas | [ ] OK |
| Template usado | _______________ | [ ] OK |
| Modelo usado | _______________ | [ ] OK |
| Score de risco | ________ | [ ] OK |

**DADOS DO PLANO:**

- Plan ID: ________________________________________
- Intent ID referenciado: ________________________________________
- Domain: _______________
- Priority: ________
- Security Level: _______________
- Complexity: ________
- Risk Score: ________

**ANOMALIAS:**
[ ] Nenhuma
[ ] Plano não gerado após 30s: ________________________
[ ] Erro na geração de tarefas: ________________________
[ ] Score de risco inválido: ________________________

---

### 3.4 Mensagem do Plano no Kafka - Captura Completa

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Kafka:** neural-hive-kafka-broker-0
**Topic:** `plans.ready`
**Plan ID (Capturado em 3.3):** ________________________________________

**INPUT (Comando Executado):**
```
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.ready \
  --from-beginning \
  --max-messages 3 \
  --property print.key=true \
  --property key.separator=" : "
```

**OUTPUT (Mensagem Capturada - RAW):**
```
[INSERIR MENSAGEM DO PLANO NO KAFKA AQUI - formato Avro binário]
```

**ANÁLISE DA MENSAGEM DO PLANO:**

| Item | Valor | Status |
|------|-------|--------|
| Formato | [ ] Avro [ ] JSON | [ ] OK |
| Schema ID | H____________________________________ | [ ] OK |
| Schema Version | ______.__ | [ ] OK |
| Plan ID | ________________________________________ | [ ] Matches |
| Intent ID Ref | ________________________________________ | [ ] Matches |
| Partition key | _______________ | [ ] OK |
| Offset | _____ | [ ] OK |
| Partition | __ | [ ] OK |
| Tamanho | _____ bytes | [ ] OK |

**TAREFAS DO PLANO:**

| Task ID | Query | Ações | Dependencies | Template | Parallel |
|---------|-------|--------|--------------|----------|----------|
| task_0 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |
| task_1 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |
| task_2 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |
| task_3 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |
| task_4 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |
| task_5 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |
| task_6 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |
| task_7 | _______________ | ________________________ | ____________________ | _______________ | [ ] Yes [ ] No |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Número de tarefas diferente do esperado: ________________________
[ ] Tarefas sem dependências: ________________________
[ ] Tarefas não paralelizáveis marcadas como paralelas: ________________________

---

### 3.5 Persistência no MongoDB - Verificação do Plano

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod MongoDB:** _________________________________
**Plan ID (Capturado em 3.3 ou 3.4):** ________________________________________

**INPUT (Comando Executado):**
```
# Criar pod temporário MongoDB
kubectl run mongo-shell --image=mongo:7.0 --restart=Never -i --tty --rm -- \
  mongo "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive" \
  --eval "db.cognitive_plans.find({id: '________________________________________'}).pretty()"
```

**OUTPUT (Plano Persistido - RAW JSON):**
```json
[INSERIR DOCUMENTO DO PLANO NO MONGODB AQUI]
```

**ANÁLISE DE PERSISTÊNCIA:**

| Item | Valor | Status |
|------|-------|--------|
| Plano encontrado no MongoDB? | [ ] Sim [ ] Não | [ ] OK |
| Document ID (_id) | _________________________________ | [ ] OK |
| Timestamp de criação | 2026-__-__ __:__:__.___ UTC | [ ] OK |
| Timestamp de atualização | 2026-__-__ __:__:__.___ UTC | [ ] OK |
| Status do plano | ______________________ | [ ] OK |

**CAMPOS DO DOCUMENTO:**
[ ] id: ________________________________________
[ ] intent_id: ________________________________________
[ ] domain: _______________
[ ] priority: ________
[ ] security_level: _______________
[ ] complexity: ________
[ ] risk_score: ________
[ ] tasks: [ ] Presentes [ ] Ausentes (count: ___)
[ ] created_at: ______________________
[ ] updated_at: ______________________
[ ] created_by: ______________________

**ANOMALIAS:**
[ ] Nenhuma
[ ] Plano não encontrado no MongoDB: ________________________
[ ] Campos diferentes do Kafka: ________________________
[ ] Timestamps inconsistentes: ________________________

---

## FLUXO C - Specialists → Consensus → Orchestrator

### C1: Specialists - Análise das Opiniões

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Plan ID (Capturado em 3.3):** ________________________________________

**INPUT (Comando Executado):**
```
# Verificar pods de specialists
kubectl get pods -n neural-hive | grep specialist

# Verificar consumer groups dos specialists
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list | grep specialist

# Logs dos specialists
kubectl logs --tail=200 -n neural-hive | grep specialist
```

**OUTPUT (Estado dos Specialists):**

```
[INSERIR ESTADO DOS SPECIALISTS AQUI]
```

**ANÁLISE DOS SPECIALISTS:**

| Specialist | Pod ID | Status | Service Registry | Status |
|------------|---------|--------|------------------|--------|
| Security Specialist | _________________________________ | [ ] Running [ ] Error | [ ] Registrado [ ] Não | [ ] OK |
| Technical Specialist | _________________________________ | [ ] Running [ ] Error | [ ] Registrado [ ] Não | [ ] OK |
| Business Specialist | _________________________________ | [ ] Running [ ] Error | [ ] Registrado [ ] Não | [ ] OK |
| Infrastructure Specialist | _________________________________ | [ ] Running [ ] Error | [ ] Registrado [ ] Não | [ ] OK |

**OPINIÕES GERADAS (verificar no Kafka):**

**INPUT (Comando Executado):**
```
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic opinions.ready \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true
```

**OUTPUT (Opiniões no Kafka - RAW):**
```
[INSERIR OPINIÕES NO KAFKA AQUI]
```

**ANÁLISE DE OPINIÕES:**

| Item | Valor | Status |
|------|-------|--------|
| Número de opiniões | _____ opiniões | [ ] OK |
| Opiniões positivas | _____ | [ ] OK |
| Opiniões negativas | _____ | [ ] OK |
| Opiniões neutras | _____ | [ ] OK |
| Plan ID referenciado | ________________________________________ | [ ] Matches |
| Specialists participantes | _____ specialists | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Número de opiniões < esperado: ________________________
[ ] Specialis ts não respondendo: ________________________

---

### C2: Consensus Engine - Agregação de Decisões

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Consensus:** _________________________________
**Plan ID (Capturado em 3.3):** ________________________________________

**INPUT (Comando Executado):**
```
# Status do pod Consensus
kubectl get pod -n neural-hive _________________________________

# Consumer group Consensus
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group consensus-engine \
  --describe

# Logs do Consensus
kubectl logs --tail=500 -n neural-hive _________________________________ | \
  grep -E "(consensus|decision|opinion|aggregation)"
```

**OUTPUT (Estado do Consensus):**

```
[INSERIR ESTADO DO CONSENSUS AQUI]
```

**ANÁLISE DO CONSENSUS:**

| Componente | Status | Observações |
|-----------|--------|-------------|
| Pod Consensus | [ ] Running [ ] Error | ________________________ |
| Consumer de opinions | [ ] Ativo [ ] Inativo | ________________________ |
| Consumer de plans | [ ] Ativo [ ] Inativo | ________________________ |
| Agregação ativa | [ ] Sim [ ] Não | ________________________ |

**DECISÕES GERADAS (verificar no Kafka):**

**INPUT (Comando Executado):**
```
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic decisions.ready \
  --from-beginning \
  --max-messages 3 \
  --property print.key=true
```

**OUTPUT (Decisões no Kafka - RAW):**
```
[INSERIR DECISÕES NO KAFKA AQUI]
```

**ANÁLISE DA DECISÃO:**

| Item | Valor | Status |
|------|-------|--------|
| Decisão gerada? | [ ] Sim [ ] Não | [ ] OK |
| Decision ID | _________________________________ | [ ] OK |
| Plan ID referenciado | ________________________________________ | [ ] Matches |
| Decisão final | [ ] Approved [ ] Rejected [ ] Needs Review | [ ] OK |
| Confiança da decisão | ________ | [ ] OK |
| Timestamp da decisão | 2026-__-__ __:__:__.___ UTC | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Decisão não gerada: ________________________
[ ] Decisão contraria consenso: ________________________

---

### C3: Orchestrator - Validação de Planos

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Orchestrator:** _________________________________
**Decision ID (Capturado em C2):** _________________________________

**INPUT (Comando Executado):**
```
# Status do pod Orchestrator
kubectl get pod -n neural-hive _________________________________

# Health check Orchestrator
kubectl port-forward -n neural-hive svc/orchestrator-dynamic 8002:8000 &
curl -s http://localhost:8002/health | jq .

# Consumer group Orchestrator
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orchestrator-dynamic \
  --describe

# Logs do Orchestrator
kubectl logs --tail=500 -n neural-hive _________________________________ | \
  grep -E "(validate|plan|decision|approved|rejected)"
```

**OUTPUT (Estado do Orchestrator):**

```
[INSERIR ESTADO DO ORCHESTRATOR AQUI]
```

**ANÁLISE DO ORCHESTRATOR (C3):**

| Componente | Status | Observações |
|-----------|--------|-------------|
| Pod Orchestrator | [ ] Running [ ] Error | ________________________ |
| Health Check | [ ] OK [ ] Falha | ________________________ |
| Consumer de decisions | [ ] Ativo [ ] Inativo | ________________________ |
| Validação de planos | [ ] Ativa [ ] Inativa | ________________________ |

**CONSUMER GROUP DETAILS:**

| Topic | Partition | Current Offset | Log End Offset | LAG | Status |
|-------|-----------|----------------|-----------------|-----|--------|
| decisions.ready | __ | _________ | _________ | _____ | [ ] OK |
| plans.consensus | __ | _________ | _________ | _____ | [ ] OK |

**ANOMALIAS:**
[ ] Nenhuma
[ ] LAG alto (>10): ________________________
[ ] Validação falhando: ________________________

---

### C4: Orchestrator - Criação de Tickets

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Orchestrator:** _________________________________
**Decision ID (Capturado em C2):** _________________________________

**INPUT (Comando Executado):**
```
# Logs de criação de tickets
kubectl logs --tail=1000 -n neural-hive _________________________________ | \
  grep -E "(ticket|created|generated.*task|assign)" | \
  tail -30

# Verificar tickets no Kafka
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true
```

**OUTPUT (Tickets Criados - RAW):**
```
[INSERIR TICKETS NO KAFKA AQUI]
```

**ANÁLISE DE TICKETS:**

| Item | Valor | Status |
|------|-------|--------|
| Tickets criados? | [ ] Sim [ ] Não | [ ] OK |
| Número de tickets | _____ tickets | [ ] OK |
| Ticket IDs (primeiros 5) | _________________________________ | [ ] OK |
| Decision ID referenciado | _________________________________ | [ ] Matches |
| Timestamp de criação | 2026-__-__ __:__:__.___ UTC | [ ] OK |

**DETALHES DOS TICKETS:**

| Ticket ID | Task ID | Status | Worker ID | Created At |
|-----------|---------|--------|-----------|------------|
| ______________________ | ________ | [ ] Pending [ ] Assigned [ ] Completed | _______________ | 2026-__-__ __:__:__ |
| ______________________ | ________ | [ ] Pending [ ] Assigned [ ] Completed | _______________ | 2026-__-__ __:__:__ |
| ______________________ | ________ | [ ] Pending [ ] Assigned [ ] Completed | _______________ | 2026-__-__ __:__:__ |
| ______________________ | ________ | [ ] Pending [ ] Assigned [ ] Completed | _______________ | 2026-__-__ __:__:__ |
| ______________________ | ________ | [ ] Pending [ ] Assigned [ ] Completed | _______________ | 2026-__-__ __:__:__ |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Tickets não criados: ________________________
[ ] Número de tickets diferente das tarefas: ________________________

---

### C5: Orchestrator - Workers Discovery e Assignação

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Orchestrator:** _________________________________

**INPUT (Comandos Executados):**
```
# Verificar workers no Service Registry
kubectl run curl-test --image=curlimages/curl:latest --rm -it --restart=Never -- \
  curl -s http://service-registry.neural-hive.svc.cluster.local:8080/workers | jq .

# Verificar workers capabilities
kubectl run curl-test --image=curlimages/curl:latest --rm -it --restart=Never -- \
  curl -s http://service-registry.neural-hive.svc.cluster.local:8080/capabilities | jq .

# Logs de workers discovery no Orchestrator
kubectl logs --tail=500 -n neural-hive _________________________________ | \
  grep -E "(worker.*discovered|discovery.*worker|assign.*worker)"
```

**OUTPUT (Workers Disponíveis - RAW JSON):**
```json
[INSERIR WORKERS NO SERVICE REGISTRY AQUI]
```

**OUTPUT (Workers Capabilities - RAW JSON):**
```json
[INSERIR WORKERS CAPABILITIES AQUI]
```

**ANÁLISE DE WORKERS:**

| Worker ID | Service | Status | Capabilities | Last Heartbeat |
|-----------|---------|--------|--------------|----------------|
| ______________________ | _______________ | [ ] Active [ ] Inactive | ____________________ | 2026-__-__ __:__:__ |
| ______________________ | _______________ | [ ] Active [ ] Inactive | ____________________ | 2026-__-__ __:__:__ |
| ______________________ | _______________ | [ ] Active [ ] Inactive | ____________________ | 2026-__-__ __:__:__ |
| ______________________ | _______________ | [ ] Active [ ] Inactive | ____________________ | 2026-__-__ __:__:__ |
| ______________________ | _______________ | [ ] Active [ ] Inactive | ____________________ | 2026-__-__ __:__:__ |

**CAPABILITIES POR WORKER:**

| Worker ID | Capabilities (Security) | Capabilities (Technical) | Capabilities (Business) | Capabilities (Infra) |
|-----------|------------------------|---------------------------|-------------------------|-----------------------|
| ______________________ | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No |
| ______________________ | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No |
| ______________________ | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No |
| ______________________ | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No | [ ] Yes [ ] No |

**ASSIGNAÇÃO DE TICKETS:**

| Ticket ID | Task ID | Worker ID | Assigned At | Status |
|-----------|---------|-----------|-------------|--------|
| ______________________ | ________ | _______________ | 2026-__-__ __:__:__ | [ ] Assigned |
| ______________________ | ________ | _______________ | 2026-__-__ __:__:__ | [ ] Assigned |
| ______________________ | ________ | _______________ | 2026-__-__ __:__:__ | [ ] Assigned |
| ______________________ | ________ | _______________ | 2026-__-__ __:__:__ | [ ] Assigned |
| ______________________ | ________ | _______________ | 2026-__-__ __:__:__ | [ ] Assigned |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Nenhum worker disponível: ________________________
[ ] Workers sem heartbeat recente: ________________________
[ ] Tickets não assignados: ________________________

---

### C6: Orchestrator - Telemetry e Monitoramento

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod Orchestrator:** _________________________________

**INPUT (Comandos Executados):**
```
# Logs de telemetry no Orchestrator
kubectl logs --tail=500 -n neural-hive _________________________________ | \
  grep -E "(telemetry|event|monitoring|status.*updated)"

# Verificar eventos de telemetry no Kafka
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic telemetry.events \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true

# Verificar status de workers no Kafka
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic workers.status \
  --from-beginning \
  --max-messages 5 \
  --property print.key=true
```

**OUTPUT (Telemetry Events - RAW):**
```
[INSERIR EVENTOS DE TELEMETRY AQUI]
```

**OUTPUT (Workers Status - RAW):**
```
[INSERIR STATUS DOS WORKERS AQUI]
```

**ANÁLISE DE TELEMETRY:**

| Item | Valor | Status |
|------|-------|--------|
| Eventos de telemetry gerados? | [ ] Sim [ ] Não | [ ] OK |
| Número de eventos | _____ eventos | [ ] OK |
| Event types (count) | _________________________________ | [ ] OK |
| Workers status updates | _____ atualizações | [ ] OK |

**EVENTOS DE TELEMETRY (TOP 5):**

| Timestamp | Event Type | Details | Worker ID | Ticket ID |
|-----------|------------|---------|-----------|-----------|
| 2026-__-__ __:__:__ | ________________________ | _________________________________ | _______________ | ______________________ |
| 2026-__-__ __:__:__ | ________________________ | _________________________________ | _______________ | ______________________ |
| 2026-__-__ __:__:__ | ________________________ | _________________________________ | _______________ | ______________________ |
| 2026-__-__ __:__:__ | ________________________ | _________________________________ | _______________ | ______________________ |
| 2026-__-__ __:__:__ | ________________________ | _________________________________ | _______________ | ______________________ |

**WORKERS STATUS:**

| Worker ID | Status | Tasks Assigned | Tasks Completed | Last Activity |
|-----------|--------|----------------|-----------------|----------------|
| ______________________ | [ ] Idle [ ] Busy [ ] Offline | ___ | ___ | 2026-__-__ __:__:__ |
| ______________________ | [ ] Idle [ ] Busy [ ] Offline | ___ | ___ | 2026-__-__ __:__:__ |
| ______________________ | [ ] Idle [ ] Busy [ ] Offline | ___ | ___ | 2026-__-__ __:__:__ |
| ______________________ | [ ] Idle [ ] Busy [ ] Offline | ___ | ___ | 2026-__-__ __:__:__ |
| ______________________ | [ ] Idle [ ] Busy [ ] Offline | ___ | ___ | 2026-__-__ __:__:__ |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Eventos de telemetry não gerados: ________________________
[ ] Workers offline: ________________________
[ ] Tasks pendentes há muito tempo: ________________________

---

## FLUXO D - Verificação Final - MongoDB Persistência

**Timestamp Execução:** 2026-__-__ __:__:__ UTC
**Pod MongoDB:** _________________________________

**INPUT (Comando Executado):**
```
# Verificar todas as collections do plano
kubectl run mongo-shell --image=mongo:7.0 --restart=Never -i --tty --rm -- \
  mongo "mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive" \
  --eval "
    print('=== COGNITIVE PLANS ===');
    db.cognitive_plans.find({id: '________________________________________'}).pretty();
    print('\\n=== OPINIONS ===');
    db.opinions.find({plan_id: '________________________________________'}).pretty();
    print('\\n=== DECISIONS ===');
    db.decisions.find({plan_id: '________________________________________'}).pretty();
    print('\\n=== TICKETS ===');
    db.tickets.find({plan_id: '________________________________________'}).pretty();
    print('\\n=== TELEMETRY EVENTS ===');
    db.telemetry_events.find({plan_id: '________________________________________'}).sort({timestamp: -1}).limit(5).pretty();
  "
```

**OUTPUT (Persistência Completa - RAW):**

```
=== COGNITIVE PLANS ===
[INSERIR DOCUMENTO DO PLANO AQUI]

=== OPINIONS ===
[INSERIR OPINIÕES AQUI]

=== DECISIONS ===
[INSERIR DECISÕES AQUI]

=== TICKETS ===
[INSERIR TICKETS AQUI]

=== TELEMETRY EVENTS ===
[INSERIR EVENTOS DE TELEMETRY AQUI]
```

**ANÁLISE DE PERSISTÊNCIA:**

| Collection | Documentos Encontrados | IDs Capturados | Status |
|------------|----------------------|----------------|--------|
| cognitive_plans | [ ] Sim [ ] Não | id: __________ | [ ] OK |
| opinions | [ ] Sim [ ] Não | count: ___ | [ ] OK |
| decisions | [ ] Sim [ ] Não | id: __________ | [ ] OK |
| tickets | [ ] Sim [ ] Não | count: ___ | [ ] OK |
| telemetry_events | [ ] Sim [ ] Não | count: ___ | [ ] OK |

**INTEGRIDADE DOS DADOS:**

| Item | Gateway | Kafka | STE | MongoDB | Status |
|------|---------|-------|-----|---------|--------|
| Intent ID | ________ | ________ | ________ | ________ | [ ] Consistente |
| Plan ID | N/A | ________ | ________ | ________ | [ ] Consistente |
| Correlation ID | ________ | N/A | N/A | ________ | [ ] Consistente |

**TIMESTAMPS DE PERSISTÊNCIA:**

| Documento | Created At | Updated At | Latência (desde criação) |
|-----------|------------|------------|---------------------------|
| Cognitive Plan | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | _____ ms |
| Opinions | 2026-__-__ __:__:__ | N/A | _____ ms |
| Decisions | 2026-__-__ __:__:__ | N/A | _____ ms |
| Tickets | 2026-__-__ __:__:__ | 2026-__-__ __:__:__ | _____ ms |

**ANOMALIAS:**
[ ] Nenhuma
[ ] Documentos não encontrados no MongoDB: ________________________
[ ] Timestamps inconsistentes: ________________________
[ ] IDs não correlacionados: ________________________

---

## ANÁLISE FINAL INTEGRADA

### 5.1 Correlação de IDs de Ponta a Ponta

**MATRIZ DE CORRELAÇÃO:**

| ID | Tipo | Capturado em | Propagou para | Status |
|----|------|-------------|----------------|--------|
| Intent ID | intent_id | Seção 2.2 | STE, Kafka, Redis | [ ] ✅ [ ] ❌ |
| Correlation ID | correlation_id | Seção 2.2 | Gateway, Kafka, Redis | [ ] ✅ [ ] ❌ |
| Trace ID | trace_id | Seção 2.2 | Gateway, Jaeger | [ ] ✅ [ ] ❌ |
| Plan ID | plan_id | Seção 3.3 | Kafka, MongoDB | [ ] ✅ [ ] ❌ |
| Decision ID | decision_id | Seção C2 | Kafka, Orchestrator | [ ] ✅ [ ] ❌ |
| Ticket IDs | ticket_ids | Seção C4 | Kafka, MongoDB | [ ] ✅ [ ] ❌ |
| Worker IDs | worker_ids | Seção C5 | Service Registry, Orchestrator | [ ] ✅ [ ] ❌ |
| Telemetry IDs | telemetry_ids | Seção C6 | Kafka, MongoDB | [ ] ✅ [ ] ❌ |

**RESUMO DE PROPAGAÇÃO:**
- IDs propagados com sucesso: _____ / 8
- IDs não propagados: _____ / 8
- Quebras na cadeia de rastreamento: [ ] Nenhuma [ ] Descrever: ________________________

---

### 5.2 Timeline de Latências End-to-End

**TIMELINE COMPLETA:**

| Etapa | Início | Fim | Duração | SLO | Status |
|-------|--------|------|----------|-----|--------|
| Gateway - Recepção da Intenção | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <1000ms | [ ] ✅ [ ] ❌ |
| Gateway - NLU Pipeline | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <200ms | [ ] ✅ [ ] ❌ |
| Gateway - Serialização Kafka | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <100ms | [ ] ✅ [ ] ❌ |
| Gateway - Publicação Kafka | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <200ms | [ ] ✅ [ ] ❌ |
| Gateway - Cache Redis | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <100ms | [ ] ✅ [ ] ❌ |
| Gateway - Trace Export | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <50ms | [ ] ✅ [ ] ❌ |
| STE - Consumo Kafka | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <500ms | [ ] ✅ [ ] ❌ |
| STE - Processamento Plano | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <2000ms | [ ] ✅ [ ] ❌ |
| STE - Geração Tarefas | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <1000ms | [ ] ✅ [ ] ❌ |
| STE - Persistência MongoDB | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <500ms | [ ] ✅ [ ] ❌ |
| Specialists - Geração Opiniões | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <5000ms | [ ] ✅ [ ] ❌ |
| Consensus - Agregação Decisões | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <3000ms | [ ] ✅ [ ] ❌ |
| Orchestrator - Validação Planos | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <500ms | [ ] ✅ [ ] ❌ |
| Orchestrator - Criação Tickets | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <500ms | [ ] ✅ [ ] ❌ |
| Orchestrator - Workers Discovery | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <1000ms | [ ] ✅ [ ] ❌ |
| Orchestrator - Assignação Tickets | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <500ms | [ ] ✅ [ ] ❌ |
| Orchestrator - Telemetry Events | 2026-__-__ __:__:__.___ | 2026-__-__ __:__:__.___ | _____ ms | <200ms | [ ] ✅ [ ] ❌ |

**RESUMO DE SLOS:**
- SLOs passados: _____ / 16
- SLOs excedidos: _____ / 16
- Tempo total end-to-end: _____ segundos

**GARGALOS IDENTIFICADOS:**
1. Etapa mais lenta: ________________________ (_____ ms)
2. Etapa com mais violações de SLO: ________________________
3. Anomalias de latência: ________________________

---

### 5.3 Matriz de Qualidade de Dados

**QUALIDADE POR ETAPA:**

| Etapa | Completude | Consistência | Integridade | Validade | Pontuação |
|-------|-----------|--------------|------------|---------|----------|
| Gateway - Resposta HTTP | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Gateway - Logs | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Gateway - Cache Redis | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Gateway - Mensagem Kafka | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Gateway - Métricas Prometheus | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Gateway - Trace Jaeger | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| STE - Logs | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| STE - Plano Kafka | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| STE - Plano MongoDB | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Specialists - Opiniões | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Consensus - Decisões | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Orchestrator - Logs | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Orchestrator - Tickets | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |
| Orchestrator - Telemetry | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | [ ] Alta [ ] Média [ ] Baixa | ___/4 |

**RESUMO DE QUALIDADE:**
- Pontuação máxima possível: 52 pontos
- Pontuação obtida: _____ pontos (_____ %)
- Qualidade geral: [ ] Excelente (>80%) [ ] Boa (60-80%) [ ] Média (40-60%) [ ] Baixa (<40%)

---

### 5.4 Matriz de Validação - Critérios de Aceitação

**CRITÉRIOS FUNCIONAIS:**

| Critério | Especificado | Resultado | Status |
|----------|-------------|-----------|--------|
| Gateway processa intenções | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Gateway classifica corretamente | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Gateway publica no Kafka | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Gateway cacheia no Redis | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| STE consome intenções | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| STE gera plano cognitivo | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| STE persiste plano no MongoDB | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| STE publica plano no Kafka | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Specialists geram opiniões | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Consensus agrega decisões | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Orchestrator valida planos | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Orchestrator cria tickets | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Orchestrator descobre workers | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Orchestrator assigna tickets | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Orchestrator gera telemetry | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |

**CRITÉRIOS DE PERFORMANCE:**

| Critério | Especificado | Resultado | Status |
|----------|-------------|-----------|--------|
| Latência total < 30s | Sim | _____ s | [ ] ✅ [ ] ❌ |
| Gateway latência < 500ms | Sim | _____ ms | [ ] ✅ [ ] ❌ |
| STE latência < 5s | Sim | _____ ms | [ ] ✅ [ ] ❌ |
| Specialists latência < 10s | Sim | _____ ms | [ ] ✅ [ ] ❌ |
| Consensus latência < 5s | Sim | _____ ms | [ ] ✅ [ ] ❌ |
| Orchestrator latência < 5s | Sim | _____ ms | [ ] ✅ [ ] ❌ |

**CRITÉRIOS DE OBSERVABILIDADE:**

| Critério | Especificado | Resultado | Status |
|----------|-------------|-----------|--------|
| Logs presentes em todos os serviços | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Métricas disponíveis no Prometheus | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Traces disponíveis no Jaeger | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| IDs propagados ponta a ponta | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |
| Dados persistidos no MongoDB | Sim | [ ] Sim [ ] Não | [ ] ✅ [ ] ❌ |

**RESUMO DE VALIDAÇÃO:**
- Critérios funcionais passados: _____ / 15
- Critérios de performance passados: _____ / 6
- Critérios de observabilidade passados: _____ / 5
- Taxa geral de sucesso: _____ % (_____ / 26)

---

### 5.5 Problemas e Anomalias Identificadas

**PROBLEMAS CRÍTICOS (Bloqueadores):**

| ID | Problema | Severidade | Etapa Afetada | Impacto | Status |
|----|----------|-------------|----------------|---------|--------|
| P1 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| P2 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| P3 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |

**PROBLEMAS NÃO CRÍTICOS (Observabilidade):**

| ID | Problema | Severidade | Etapa Afetada | Impacto | Status |
|----|----------|-------------|----------------|---------|--------|
| O1 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| O2 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |
| O3 | ________________________ | [ ] Alta [ ] Média [ ] Baixa | ____________ | ____________________ | [ ] Aberto [ ] Fechado |

**ANOMALIAS DE PERFORMANCE:**

| Etapa | Problema | Medido | Esperado | Desvio | Status |
|-------|----------|---------|----------|--------|--------|
| ____________ | ________________________ | _____ ms | _____ ms | _____ % | [ ] Investigado [ ] Aceito |
| ____________ | ________________________ | _____ ms | _____ ms | _____ % | [ ] Investigado [ ] Aceito |
| ____________ | ________________________ | _____ ms | _____ ms | _____ % | [ ] Investigado [ ] Aceito |

---

## CONCLUSÃO FINAL

### 6.1 Status Geral do Pipeline

**RESULTADO DO TESTE:**

| Fluxo | Status | Taxa de Sucesso | Observações |
|-------|--------|------------------|-------------|
| Fluxo A (Gateway → Kafka) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| Fluxo B (STE → Plano) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| Fluxo C1 (Specialists) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| Fluxo C2 (Consensus) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| Fluxo C3-C6 (Orchestrator) | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |
| Pipeline Completo | [ ] ✅ Completo [ ] ⚠️ Parcial [ ] ❌ Falhou | _____ % | ________________________ |

**VEREDITO FINAL:**
[ ] ✅ **APROVADO** - Pipeline funcionando conforme especificação
[ ] ⚠️ **APROVADO COM RESERVAS** - Pipeline funcionando mas com problemas menores
[ ] ❌ **REPROVADO** - Pipeline com bloqueadores críticos

---

### 6.2 Recomendações

**RECOMENDAÇÕES IMEDIATAS (Bloqueadores Críticos):**

1. [ ] ________________________
   - Prioridade: [ ] P0 (Crítica) [ ] P1 (Alta)
   - Responsável: ________________________
   - Estimativa: ______ horas

2. [ ] ________________________
   - Prioridade: [ ] P0 (Crítica) [ ] P1 (Alta)
   - Responsável: ________________________
   - Estimativa: ______ horas

**RECOMENDAÇÕES DE CURTO PRAZO (1-3 dias):**

1. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ dias

2. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ dias

**RECOMENDAÇÕES DE MÉDIO PRAZO (1-2 semanas):**

1. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ semanas

2. [ ] ________________________
   - Prioridade: [ ] P2 (Média) [ ] P3 (Baixa)
   - Responsável: ________________________
   - Estimativa: ______ semanas

---

### 6.3 Assinatura e Data

**TESTADOR RESPONSÁVEL:**

Nome: ______________________________________________________
Função: ______________________________________________________
Email: ______________________________________________________

**APROVAÇÃO DO TESTE:**

[ ] Aprovado por: ______________________________________________________
[ ] Data de aprovação: 2026-__-__ __/__

**ASSINATURA:**
____________________________________________________

---

## ANEXOS - EVIDÊNCIAS TÉCNICAS

### A1. IDs de Rastreamento Capturados

- Intent ID: ________________________________________
- Correlation ID: ________________________________________
- Trace ID: ______________________________________________________
- Span ID: ______________________________________
- Plan ID: ________________________________________
- Decision ID: ________________________________________
- Ticket IDs (5 primeiros): _________________________________________________
- Worker IDs (ativos): _________________________________________________
- Telemetry IDs (últimos 3): _________________________________________________

### A2. Comandos Executados (para reprodutibilidade)

```
[INSERIR LISTA DE COMANDOS KUBECTLE/KAFKA/MONGODB/REDIS UTILIZADOS]
```

### A3. Scripts de Coleta de Evidências

```
[INSERIR SCRIPTS CUSTOMIZADOS UTILIZADOS DURANTE O TESTE]
```

### A4. Screenshots/Capturas (referências)

```
[INSERIR REFERÊNCIAS PARA SCREENSHOTS OU CAPTURAS DE TELA]
```

---

## CHECKLIST FINAL DE TESTE

**PREPARAÇÃO:**
[ ] Documento preenchido e salvo antes do teste
[ ] Ambiente de teste preparado
[ ] Pods verificados e running
[ ] Conexões testadas (MongoDB, Redis, Kafka)
[ ] Port-forwards estabelecidos
[ ] Horário de início registrado

**EXECUÇÃO:**
[ ] Fluxo A executado completamente
[ ] Fluxo B executado completamente
[ ] Fluxo C1-C6 executados completamente
[ ] Todos os dados capturados em tempo real
[ ] Evidências salvas durante o teste
[ ] Logs coletados para cada etapa
[ ] IDs de rastreamento registrados

**FINALIZAÇÃO:**
[ ] Análises completas realizadas
[ ] Matrizes preenchidas
[ ] Problemas identificados
[ ] Recomendações elaboradas
[ ] Documento revisado e finalizado
[ ] Horário de término registrado
[ ] Relatório assinado

---

## FIM DO DOCUMENTO DE TESTE

**Versão do documento:** 1.0
**Data de criação:** 2026-02-21
**Última atualização:** 2026-__-__ __/__
**Próximo teste agendado para:** 2026-__-__ __/__
