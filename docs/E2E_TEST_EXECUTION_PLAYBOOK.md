# Playbook de Execucao de Testes E2E - Neural Hive-Mind

**Data de Geracao**: 2026-01-15
**Versao**: 1.0.0
**Ambiente Alvo**: Kubeadm (1 master + 2 workers) ou Docker Compose local

---

## Indice

1. [Pre-requisitos e Setup](#1-pre-requisitos-e-setup)
2. [Fluxo A: Gateway -> Kafka](#2-fluxo-a-gateway---kafka)
3. [Fluxo B: STE -> Specialists -> Plano](#3-fluxo-b-ste---specialists---plano)
4. [Fluxo C: Consensus -> Orchestrator -> Tickets](#4-fluxo-c-consensus---orchestrator---tickets)
5. [Coleta de Metricas Prometheus](#5-coleta-de-metricas-prometheus)
6. [Analise de Traces no Jaeger](#6-analise-de-traces-no-jaeger)
7. [Validacao de Persistencia](#7-validacao-de-persistencia)
8. [Relatorio de Resultados](#8-relatorio-de-resultados)

---

## 1. Pre-requisitos e Setup

### 1.1 Verificar Ferramentas

```bash
# Verificar instalacao de ferramentas necessarias
kubectl version --client
curl --version
jq --version
mongosh --version 2>/dev/null || echo "mongosh nao instalado"
redis-cli --version 2>/dev/null || echo "redis-cli nao instalado"
```

### 1.2 Verificar Conectividade do Cluster

```bash
# Kubernetes
kubectl cluster-info

# Listar todos os pods
kubectl get pods -A | grep -E "gateway|semantic|specialist|consensus|orchestrator|kafka|mongodb|redis|prometheus|jaeger"
```

### 1.3 Configurar Port-Forwards (manter em terminais separados)

```bash
# Terminal 1 - Prometheus
kubectl port-forward -n observability svc/prometheus-server 9090:80 &

# Terminal 2 - Jaeger
kubectl port-forward -n observability svc/jaeger-query 16686:16686 &

# Terminal 3 - Grafana (opcional)
kubectl port-forward -n observability svc/grafana 3000:80 &
```

### 1.4 Detectar Pods Automaticamente

```bash
# Exportar variaveis de ambiente
export NAMESPACE_GATEWAY="${NAMESPACE_GATEWAY:-gateway-intencoes}"
export NAMESPACE_KAFKA="${NAMESPACE_KAFKA:-kafka}"
export NAMESPACE_MONGODB="${NAMESPACE_MONGODB:-mongodb}"
export NAMESPACE_REDIS="${NAMESPACE_REDIS:-redis}"
export NAMESPACE_STE="${NAMESPACE_STE:-semantic-translation}"
export NAMESPACE_CONSENSUS="${NAMESPACE_CONSENSUS:-consensus-engine}"
export NAMESPACE_ORCHESTRATOR="${NAMESPACE_ORCHESTRATOR:-orchestrator-dynamic}"

# Detectar pods
export GATEWAY_POD=$(kubectl get pod -n $NAMESPACE_GATEWAY -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
export KAFKA_POD=$(kubectl get pod -n $NAMESPACE_KAFKA -l app=kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
export MONGODB_POD=$(kubectl get pod -n $NAMESPACE_MONGODB -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
export REDIS_POD=$(kubectl get pod -n $NAMESPACE_REDIS -l app=redis -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
export STE_POD=$(kubectl get pod -n $NAMESPACE_STE -l app=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
export CONSENSUS_POD=$(kubectl get pod -n $NAMESPACE_CONSENSUS -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
export ORCHESTRATOR_POD=$(kubectl get pod -n $NAMESPACE_ORCHESTRATOR -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

echo "=== Pods Detectados ==="
echo "Gateway: $GATEWAY_POD"
echo "Kafka: $KAFKA_POD"
echo "MongoDB: $MONGODB_POD"
echo "Redis: $REDIS_POD"
echo "STE: $STE_POD"
echo "Consensus: $CONSENSUS_POD"
echo "Orchestrator: $ORCHESTRATOR_POD"
```

---

## 2. Fluxo A: Gateway -> Kafka

### 2.1 Health Check do Gateway

**Comando de Execucao:**
```bash
kubectl exec -n $NAMESPACE_GATEWAY $GATEWAY_POD -- \
  curl -s http://localhost:8000/health | jq
```

**Documentacao - Input Enviado:**
```
Endpoint: GET /health
Headers: None
Body: None
```

**Documentacao - Output Esperado:**
```json
{
  "status": "healthy",
  "timestamp": "<ISO8601_TIMESTAMP>",
  "version": "1.0.0",
  "service_name": "gateway-intencoes",
  "components": {
    "redis": {"status": "healthy"},
    "kafka_producer": {"status": "healthy"},
    "nlu_pipeline": {"status": "healthy"},
    "asr_pipeline": {"status": "healthy"}
  }
}
```

**Checklist de Validacao:**
- [ ] HTTP Status: 200
- [ ] `status`: "healthy"
- [ ] `components.redis.status`: "healthy"
- [ ] `components.kafka_producer.status`: "healthy"
- [ ] `components.nlu_pipeline.status`: "healthy"

---

### 2.2 Envio de Intencao

**Criar Payload de Teste:**
```bash
cat > /tmp/intent-test-001.json <<'EOF'
{
  "text": "Analisar viabilidade tecnica de implementar autenticacao biometrica no aplicativo movel",
  "language": "pt-BR",
  "correlation_id": "test-e2e-$(date +%Y%m%d%H%M%S)-001",
  "context": {
    "user_id": "test-user-001",
    "session_id": "session-$(date +%s)",
    "channel": "API",
    "environment": "e2e-testing"
  },
  "constraints": {
    "priority": "HIGH",
    "timeout_ms": 30000,
    "max_specialists": 5
  },
  "metadata": {
    "test_run": "manual-e2e-validation",
    "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  }
}
EOF

# Substituir variaveis dinamicas
sed -i "s/\$(date +%Y%m%d%H%M%S)/$(date +%Y%m%d%H%M%S)/g" /tmp/intent-test-001.json
sed -i "s/\$(date +%s)/$(date +%s)/g" /tmp/intent-test-001.json
sed -i "s/\$(date -u +%Y-%m-%dT%H:%M:%SZ)/$(date -u +%Y-%m-%dT%H:%M:%SZ)/g" /tmp/intent-test-001.json

cat /tmp/intent-test-001.json | jq
```

**Comando de Envio:**
```bash
# Copiar payload para o pod
kubectl cp /tmp/intent-test-001.json $NAMESPACE_GATEWAY/$GATEWAY_POD:/tmp/intent-test-001.json

# Enviar via curl
RESPONSE=$(kubectl exec -n $NAMESPACE_GATEWAY $GATEWAY_POD -- \
  curl -s -X POST http://localhost:8000/intentions \
  -H 'Content-Type: application/json' \
  -d @/tmp/intent-test-001.json)

echo "$RESPONSE" | jq
```

**Documentacao - Input Enviado:**
```
Endpoint: POST /intentions
Headers: Content-Type: application/json
Body: Ver /tmp/intent-test-001.json
```

**Documentacao - Output Esperado:**
```json
{
  "intent_id": "<UUID>",
  "correlation_id": "test-e2e-<timestamp>-001",
  "status": "processed",
  "confidence": 0.85,
  "domain": "technical",
  "classification": "analysis_request",
  "trace_id": "<trace_id>",
  "processing_time_ms": 150.5
}
```

**Extrair e Salvar IDs:**
```bash
export INTENT_ID=$(echo "$RESPONSE" | jq -r '.intent_id')
export TRACE_ID=$(echo "$RESPONSE" | jq -r '.trace_id')
export CONFIDENCE=$(echo "$RESPONSE" | jq -r '.confidence')
export DOMAIN=$(echo "$RESPONSE" | jq -r '.domain')

echo "=== IDs Capturados - Fluxo A ==="
echo "INTENT_ID: $INTENT_ID"
echo "TRACE_ID: $TRACE_ID"
echo "CONFIDENCE: $CONFIDENCE"
echo "DOMAIN: $DOMAIN"
```

**Checklist de Validacao:**
- [ ] HTTP Status: 200
- [ ] `intent_id`: UUID valido
- [ ] `status`: "processed"
- [ ] `confidence`: > 0.7
- [ ] `domain`: identificado (technical/business/etc)
- [ ] `trace_id`: presente

---

### 2.3 Logs Relevantes do Gateway

**Comando:**
```bash
kubectl logs -n $NAMESPACE_GATEWAY $GATEWAY_POD --tail=100 | \
  grep -E "intent_id|Kafka|published|Processando|NLU" | tail -30
```

**Documentacao - Logs Esperados:**
```
[INFO] Processando intencao de texto
[INFO] NLU pipeline: domain=technical, confidence=0.85
[INFO] Publicando no Kafka: topic=intentions.technical
[INFO] Kafka publish success: offset=<offset_number>
```

**Checklist de Logs:**
- [ ] Log de "Processando intencao"
- [ ] Log de NLU com domain e confidence
- [ ] Log de publicacao no Kafka (topic: `intentions.technical`)
- [ ] Log de offset do Kafka
- [ ] Sem logs de erro

---

### 2.4 Validar Publicacao no Kafka

**Comando:**
```bash
kubectl exec -n $NAMESPACE_KAFKA $KAFKA_POD -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.technical \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 10000 2>/dev/null | jq
```

**Alternativa - Verificar topico intentions.inbound:**
```bash
kubectl exec -n $NAMESPACE_KAFKA $KAFKA_POD -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic intentions.inbound \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 10000 2>/dev/null | jq
```

**Documentacao - Output Esperado:**
```json
{
  "id": "<INTENT_ID>",
  "actor": {"id": "test-user-001", "actorType": "HUMAN"},
  "intent": {
    "text": "Analisar viabilidade tecnica...",
    "domain": "TECHNICAL",
    "classification": "analysis_request",
    "entities": ["autenticacao", "biometrica", "aplicativo"],
    "confidence": 0.85
  },
  "constraints": {
    "priority": "HIGH",
    "deadline": "<timestamp>",
    "maxRetries": 3,
    "securityLevel": "INTERNAL"
  },
  "qos": {
    "deliveryMode": "EXACTLY_ONCE",
    "durability": "PERSISTENT",
    "consistency": "STRONG"
  }
}
```

**Checklist de Validacao Kafka:**
- [ ] Mensagem presente no topico
- [ ] `id` corresponde ao `INTENT_ID`
- [ ] `intent.text` corresponde ao input
- [ ] `intent.confidence` presente

---

### 2.5 Validar Cache no Redis

**Comando:**
```bash
# Verificar existencia da key
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli GET "intent:$INTENT_ID"

# Verificar TTL
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli TTL "intent:$INTENT_ID"

# Listar todas as keys de intencoes
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli KEYS "intent:*" | head -10
```

**Documentacao - Output Esperado:**
```json
{
  "intent_id": "<INTENT_ID>",
  "text": "...",
  "domain": "technical",
  "confidence": 0.85,
  "cached_at": "<timestamp>"
}
```

**Checklist de Validacao Redis:**
- [ ] Key `intent:{intent_id}` existe
- [ ] JSON do IntentEnvelope presente
- [ ] TTL configurado (> 0 segundos)

---

## 3. Fluxo B: STE -> Specialists -> Plano

### 3.1 Validar Consumo pelo Semantic Translation Engine (STE)

**Comando:**
```bash
kubectl logs -n $NAMESPACE_STE $STE_POD --tail=150 | \
  grep -E "Consumindo|Intent|plan_id|Gerando|plano" | tail -30
```

**Documentacao - Logs Esperados:**
```
[INFO] Consumindo Intent do topico: neural-hive.intents
[INFO] Intent recebido: intent_id=<INTENT_ID>
[INFO] Gerando plano cognitivo
[INFO] Plan gerado: plan_id=<PLAN_ID>
[INFO] Publicando no topico: plans.ready
```

**Extrair Plan ID:**
```bash
export PLAN_ID=$(kubectl logs -n $NAMESPACE_STE $STE_POD --tail=200 | \
  grep -oP 'plan_id[=:]\s*\K[a-f0-9-]+' | tail -1)

echo "PLAN_ID: $PLAN_ID"
```

**Checklist de Logs STE:**
- [ ] Log de consumo do topico
- [ ] Log de intent recebido com `intent_id` do Fluxo A
- [ ] Log de geracao de plano
- [ ] `plan_id` capturado
- [ ] Log de publicacao no topico `plans.ready`

---

### 3.2 Validar Publicacao no Kafka (plans.ready)

**Comando:**
```bash
kubectl exec -n $NAMESPACE_KAFKA $KAFKA_POD -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.ready \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 10000 2>/dev/null | jq
```

**Documentacao - Output Esperado:**
```json
{
  "plan_id": "<PLAN_ID>",
  "intent_id": "<INTENT_ID>",
  "version": "1.0.0",
  "risk_band": "medium",
  "tasks": [
    {
      "task_id": "task-1",
      "task_type": "ANALYZE",
      "description": "Analisar requisitos de autenticacao biometrica",
      "dependencies": [],
      "estimated_duration_ms": 5000
    }
  ],
  "specialists_to_consult": ["business", "technical", "architecture", "evolution", "behavior"],
  "valid_until": "<timestamp>"
}
```

**Checklist de Validacao:**
- [ ] `plan_id` presente
- [ ] `intent_id` corresponde ao Fluxo A
- [ ] `tasks[]` com pelo menos 1 task
- [ ] `risk_band` definido

---

### 3.3 Validar Opinioes dos 5 Specialists

**Para cada specialist, executar:**

```bash
# Lista de specialists
SPECIALISTS=("business" "technical" "behavior" "evolution" "architecture")

for SPECIALIST in "${SPECIALISTS[@]}"; do
  echo "=== Specialist: $SPECIALIST ==="

  SPECIALIST_POD=$(kubectl get pod -n $NAMESPACE_STE -l app=specialist-$SPECIALIST -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

  if [ -n "$SPECIALIST_POD" ]; then
    echo "Pod: $SPECIALIST_POD"

    # Buscar logs de opiniao
    kubectl logs -n $NAMESPACE_STE $SPECIALIST_POD --tail=50 | \
      grep -E "GetOpinion|opinion_id|confidence|recommendation" | tail -5
  else
    echo "Pod nao encontrado para specialist-$SPECIALIST"
  fi

  echo ""
done
```

**Documentacao - Output Esperado por Specialist:**

| Specialist | opinion_id | confidence | recommendation |
|------------|------------|------------|----------------|
| Business | `__________` | `____` | APPROVE/REJECT/CONDITIONAL |
| Technical | `__________` | `____` | APPROVE/REJECT/CONDITIONAL |
| Behavior | `__________` | `____` | APPROVE/REJECT/CONDITIONAL |
| Evolution | `__________` | `____` | APPROVE/REJECT/CONDITIONAL |
| Architecture | `__________` | `____` | APPROVE/REJECT/CONDITIONAL |

**Checklist de Validacao Specialists:**
- [ ] Specialist Business respondeu (opinion_id presente)
- [ ] Specialist Technical respondeu (opinion_id presente)
- [ ] Specialist Behavior respondeu (opinion_id presente)
- [ ] Specialist Evolution respondeu (opinion_id presente)
- [ ] Specialist Architecture respondeu (opinion_id presente)
- [ ] Todas as 5 opinioes com confidence > 0

---

### 3.4 Validar Persistencia de Opinioes no MongoDB

**Comando:**
```bash
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
  db.cognitive_ledger.find({
    plan_id: '$PLAN_ID',
    specialist_type: { \$exists: true }
  }).toArray()
" neural_hive | jq
```

**Contagem de Opinioes:**
```bash
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
  db.cognitive_ledger.countDocuments({
    plan_id: '$PLAN_ID',
    specialist_type: { \$exists: true }
  })
" neural_hive
```

**Documentacao - Output Esperado:**
```
5 opinioes persistidas
```

**Checklist de Validacao MongoDB (Fluxo B):**
- [ ] 5 opinioes persistidas em `cognitive_ledger`
- [ ] Cada opiniao com `specialist_type`
- [ ] Cada opiniao com `confidence`
- [ ] Cada opiniao com `recommendation`

---

## 4. Fluxo C: Consensus -> Orchestrator -> Tickets

### 4.1 Validar Consumo pelo Consensus Engine

**Comando:**
```bash
kubectl logs -n $NAMESPACE_CONSENSUS $CONSENSUS_POD --tail=150 | \
  grep -E "Consumindo|plan_id|decision_id|Agregando|bayesian|consensus" | tail -30
```

**Extrair Decision ID:**
```bash
export DECISION_ID=$(kubectl logs -n $NAMESPACE_CONSENSUS $CONSENSUS_POD --tail=200 | \
  grep -oP 'decision_id[=:]\s*\K[a-f0-9-]+' | tail -1)

export CONSENSUS_SCORE=$(kubectl logs -n $NAMESPACE_CONSENSUS $CONSENSUS_POD --tail=200 | \
  grep -oP 'consensus_score[=:]\s*\K[0-9.]+' | tail -1)

export DIVERGENCE_SCORE=$(kubectl logs -n $NAMESPACE_CONSENSUS $CONSENSUS_POD --tail=200 | \
  grep -oP 'divergence_score[=:]\s*\K[0-9.]+' | tail -1)

echo "=== IDs Capturados - Fluxo C Consensus ==="
echo "DECISION_ID: $DECISION_ID"
echo "CONSENSUS_SCORE: $CONSENSUS_SCORE"
echo "DIVERGENCE_SCORE: $DIVERGENCE_SCORE"
```

**Documentacao - Logs Esperados:**
```
[INFO] Consumindo plano do topico: plans.ready
[INFO] Plan recebido: plan_id=<PLAN_ID>
[INFO] Chamando gRPC para 5 specialists
[INFO] Agregando opinioes (metodo: bayesian)
[INFO] Decision gerada: decision_id=<DECISION_ID>
[INFO] consensus_score=0.87, divergence_score=0.12
[INFO] Publicando no Kafka: topic=plans.consensus
[INFO] Publicando feromonios no Redis
```

**Checklist de Logs Consensus:**
- [ ] Log de consumo do topico `plans.ready`
- [ ] Log de plan recebido com `plan_id` do Fluxo B
- [ ] Logs de chamadas gRPC para 5 specialists
- [ ] Log de agregacao (metodo: bayesian)
- [ ] `decision_id` capturado
- [ ] `consensus_score` capturado
- [ ] `divergence_score` capturado
- [ ] Log de publicacao no Kafka

---

### 4.2 Validar Publicacao no Kafka (plans.consensus)

**Comando:**
```bash
kubectl exec -n $NAMESPACE_KAFKA $KAFKA_POD -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.consensus \
  --from-beginning \
  --max-messages 1 \
  --timeout-ms 10000 2>/dev/null | jq
```

**Documentacao - Output Esperado:**
```json
{
  "decision_id": "<DECISION_ID>",
  "plan_id": "<PLAN_ID>",
  "intent_id": "<INTENT_ID>",
  "consensus_score": 0.87,
  "divergence_score": 0.12,
  "final_recommendation": "APPROVED",
  "specialist_votes": {
    "business": {"recommendation": "APPROVE", "confidence": 0.9},
    "technical": {"recommendation": "APPROVE", "confidence": 0.85},
    "behavior": {"recommendation": "CONDITIONAL", "confidence": 0.75},
    "evolution": {"recommendation": "APPROVE", "confidence": 0.88},
    "architecture": {"recommendation": "APPROVE", "confidence": 0.92}
  },
  "aggregation_method": "bayesian",
  "explainability_token": "<token>"
}
```

**Checklist de Validacao:**
- [ ] `decision_id` presente
- [ ] `plan_id` corresponde ao Fluxo B
- [ ] `consensus_score` > 0
- [ ] `divergence_score` < 0.5 (baixa divergencia)
- [ ] `specialist_votes` com 5 votos

---

### 4.3 Validar Persistencia da Decisao no MongoDB

**Comando:**
```bash
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
  db.consensus_decisions.findOne({decision_id: '$DECISION_ID'})
" neural_hive | jq
```

**Documentacao - Campos Esperados:**
```json
{
  "decision_id": "<DECISION_ID>",
  "plan_id": "<PLAN_ID>",
  "intent_id": "<INTENT_ID>",
  "specialist_votes": {...},
  "consensus_metrics": {
    "consensus_score": 0.87,
    "divergence_score": 0.12
  },
  "explainability_token": "<token>",
  "created_at": "<timestamp>"
}
```

**Checklist de Validacao MongoDB (Consensus):**
- [ ] Decisao persistida em `consensus_decisions`
- [ ] `specialist_votes` presente
- [ ] `consensus_metrics` presente
- [ ] `explainability_token` presente
- [ ] `decision_id` correto

---

### 4.4 Validar Feromonios no Redis

**Comando:**
```bash
# Listar todas as keys de feromonios
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli KEYS 'pheromone:*'

# Verificar feromonio especifico
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli HGETALL 'pheromone:business:workflow-analysis:SUCCESS'

# Contar total de feromonios
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli KEYS 'pheromone:*' | wc -l
```

**Documentacao - Output Esperado:**
```
pheromone:business:workflow-analysis:SUCCESS
pheromone:technical:biometric-auth:SUCCESS
pheromone:architecture:mobile-integration:SUCCESS
...

Campos do feromonio:
- strength: 0.85
- plan_id: <PLAN_ID>
- decision_id: <DECISION_ID>
- created_at: <timestamp>
```

**Checklist de Validacao Feromonios:**
- [ ] Keys `pheromone:*` criadas
- [ ] Campo `strength` presente
- [ ] Campo `plan_id` presente
- [ ] Campo `decision_id` presente
- [ ] Campo `created_at` presente

---

### 4.5 Validar Consumo pelo Orchestrator Dynamic

**Comando:**
```bash
kubectl logs -n $NAMESPACE_ORCHESTRATOR $ORCHESTRATOR_POD --tail=150 | \
  grep -E "Consumindo|decision_id|ticket_id|Gerando|tickets" | tail -30
```

**Extrair Ticket IDs:**
```bash
export TICKET_ID=$(kubectl logs -n $NAMESPACE_ORCHESTRATOR $ORCHESTRATOR_POD --tail=200 | \
  grep -oP 'ticket_id[=:]\s*\K[a-f0-9-]+' | head -1)

export NUM_TICKETS=$(kubectl logs -n $NAMESPACE_ORCHESTRATOR $ORCHESTRATOR_POD --tail=200 | \
  grep -c 'ticket_id')

echo "=== IDs Capturados - Fluxo C Orchestrator ==="
echo "TICKET_ID (primeiro): $TICKET_ID"
echo "NUM_TICKETS: $NUM_TICKETS"
```

**Documentacao - Logs Esperados:**
```
[INFO] Consumindo decisao do topico: plans.consensus
[INFO] Decision recebida: decision_id=<DECISION_ID>
[INFO] Gerando execution tickets
[INFO] Ticket gerado: ticket_id=<TICKET_ID>
[INFO] Total de tickets: N
[INFO] Publicando no Kafka: topic=execution.tickets
[INFO] Persistindo tickets no MongoDB
```

**Checklist de Logs Orchestrator:**
- [ ] Log de consumo do topico `plans.consensus`
- [ ] Log de decisao recebida com `decision_id` do C1
- [ ] Logs de geracao de tickets
- [ ] `ticket_id` capturado
- [ ] Numero de tickets gerados
- [ ] Log de publicacao no Kafka

---

### 4.6 Validar Publicacao no Kafka (execution.tickets)

**Comando:**
```bash
kubectl exec -n $NAMESPACE_KAFKA $KAFKA_POD -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets \
  --from-beginning \
  --max-messages 3 \
  --timeout-ms 10000 2>/dev/null | jq
```

**Documentacao - Output Esperado:**
```json
{
  "ticket_id": "<TICKET_ID>",
  "plan_id": "<PLAN_ID>",
  "intent_id": "<INTENT_ID>",
  "task_id": "task-1",
  "task_type": "ANALYZE",
  "status": "PENDING",
  "priority": "HIGH",
  "risk_band": "medium",
  "sla": {
    "deadline": "<timestamp>",
    "timeout_ms": 60000,
    "max_retries": 3
  },
  "qos": {
    "delivery_mode": "EXACTLY_ONCE",
    "consistency": "STRONG",
    "durability": "PERSISTENT"
  }
}
```

**Checklist de Validacao:**
- [ ] `ticket_id` presente
- [ ] `plan_id` corresponde ao Fluxo B
- [ ] `intent_id` corresponde ao Fluxo A
- [ ] `status`: "PENDING"
- [ ] `sla` configurado

---

### 4.7 Validar Persistencia de Tickets no MongoDB

**Comando:**
```bash
# Listar tickets do plano
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
  db.execution_tickets.find({plan_id: '$PLAN_ID'}).toArray()
" neural_hive | jq

# Contar tickets
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
  db.execution_tickets.countDocuments({plan_id: '$PLAN_ID'})
" neural_hive
```

**Documentacao - Campos Esperados por Ticket:**
```json
{
  "ticket_id": "<TICKET_ID>",
  "plan_id": "<PLAN_ID>",
  "intent_id": "<INTENT_ID>",
  "task_id": "task-1",
  "status": "PENDING",
  "priority": "HIGH",
  "sla": {
    "deadline": "<timestamp>",
    "timeout_ms": 60000,
    "max_retries": 3
  },
  "dependencies": [],
  "created_at": "<timestamp>"
}
```

**Checklist de Validacao MongoDB (Tickets):**
- [ ] Tickets persistidos em `execution_tickets`
- [ ] Quantidade correta de tickets
- [ ] Cada ticket com `status`
- [ ] Cada ticket com `priority`
- [ ] Cada ticket com `sla.deadline`
- [ ] Cada ticket com `dependencies[]`

---

## 5. Coleta de Metricas Prometheus

### 5.1 Metricas do Gateway (Fluxo A)

```bash
# Intencoes publicadas
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_intents_published_total' | jq '.data.result'

# Duracao de processamento
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(neural_hive_intent_processing_duration_seconds_bucket[5m]))' | jq '.data.result'

# Confidence score medio
curl -s 'http://localhost:9090/api/v1/query?query=avg(neural_hive_nlu_confidence_score)' | jq '.data.result'

# Taxa de intencoes por minuto
curl -s 'http://localhost:9090/api/v1/query?query=rate(neural_hive_intents_published_total[5m])*60' | jq '.data.result'
```

**Tabela de Metricas Gateway:**

| Metrica | Query | Valor Obtido |
|---------|-------|--------------|
| Total intencoes | `neural_hive_intents_published_total` | `__________` |
| Latencia P95 | `histogram_quantile(0.95, ...)` | `________ ms` |
| Confidence medio | `avg(neural_hive_nlu_confidence_score)` | `__________` |

---

### 5.2 Metricas do STE e Specialists (Fluxo B)

```bash
# Planos gerados
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_plans_generated_total' | jq '.data.result'

# Risk score medio
curl -s 'http://localhost:9090/api/v1/query?query=avg(neural_hive_plan_risk_score)' | jq '.data.result'

# Opinioes de specialists
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_specialist_opinions_total' | jq '.data.result'

# Opinioes por tipo de specialist
curl -s 'http://localhost:9090/api/v1/query?query=sum(neural_hive_specialist_opinions_total)by(specialist_type)' | jq '.data.result'
```

**Tabela de Metricas Fluxo B:**

| Metrica | Query | Valor Obtido |
|---------|-------|--------------|
| Total planos | `neural_hive_plans_generated_total` | `__________` |
| Risk score medio | `avg(neural_hive_plan_risk_score)` | `__________` |
| Total opinioes | `neural_hive_specialist_opinions_total` | `__________` |

---

### 5.3 Metricas do Consensus e Orchestrator (Fluxo C)

```bash
# Decisoes de consenso
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_consensus_decisions_total' | jq '.data.result'

# Divergence score medio
curl -s 'http://localhost:9090/api/v1/query?query=avg(neural_hive_consensus_divergence_score)' | jq '.data.result'

# Forca de feromonios
curl -s 'http://localhost:9090/api/v1/query?query=avg(neural_hive_pheromone_strength)' | jq '.data.result'

# Tickets gerados
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_execution_tickets_generated_total' | jq '.data.result'

# Latencia do orchestrator
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(neural_hive_orchestrator_processing_duration_seconds_bucket[5m]))' | jq '.data.result'
```

**Tabela de Metricas Fluxo C:**

| Metrica | Query | Valor Obtido |
|---------|-------|--------------|
| Total decisoes | `neural_hive_consensus_decisions_total` | `__________` |
| Divergence medio | `avg(neural_hive_consensus_divergence_score)` | `__________` |
| Forca feromonios | `avg(neural_hive_pheromone_strength)` | `__________` |
| Total tickets | `neural_hive_execution_tickets_generated_total` | `__________` |
| Latencia P95 | `histogram_quantile(0.95, ...)` | `________ ms` |

---

### 5.4 Metricas de Erro e SLA

```bash
# Taxa de erro geral
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(neural_hive_errors_total[5m]))' | jq '.data.result'

# Violacoes de SLA
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_sla_violations_total' | jq '.data.result'

# Uso de CPU
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(container_cpu_usage_seconds_total{namespace=~"gateway.*|consensus.*|orchestrator.*"}[5m]))by(namespace)' | jq '.data.result'

# Uso de memoria
curl -s 'http://localhost:9090/api/v1/query?query=sum(container_memory_working_set_bytes{namespace=~"gateway.*|consensus.*|orchestrator.*"})by(namespace)' | jq '.data.result'
```

---

## 6. Analise de Traces no Jaeger

### 6.1 Acessar Interface do Jaeger

**URL**: http://localhost:16686

### 6.2 Buscar Trace Completo E2E

**Passos:**
1. Acessar http://localhost:16686
2. Selecionar Service: `gateway-intencoes`
3. Buscar por Tag: `trace_id=<TRACE_ID_CAPTURADO>`
4. Ou buscar por Tag: `intent.id=<INTENT_ID>`

### 6.3 Validar Spans Presentes

**Checklist de Spans:**
- [ ] Gateway: NLU processing
- [ ] Gateway: Kafka publish
- [ ] STE: semantic parsing
- [ ] STE: DAG generation
- [ ] STE: risk scoring
- [ ] Specialist Business: GetOpinion
- [ ] Specialist Technical: GetOpinion
- [ ] Specialist Behavior: GetOpinion
- [ ] Specialist Evolution: GetOpinion
- [ ] Specialist Architecture: GetOpinion
- [ ] Consensus: plan consumption
- [ ] Consensus: bayesian aggregation
- [ ] Consensus: decision publish
- [ ] Orchestrator: decision consumption
- [ ] Orchestrator: ticket generation
- [ ] Orchestrator: Kafka publish

### 6.4 Capturar Latencias por Componente

**Tabela de Latencias:**

| Componente | Span | Duracao (ms) |
|------------|------|--------------|
| Gateway (total) | root span | `__________` |
| NLU Pipeline | nlu-processing | `__________` |
| Kafka Publish | kafka-publish | `__________` |
| STE (total) | ste-processing | `__________` |
| Specialist Business | grpc-specialist-business | `__________` |
| Specialist Technical | grpc-specialist-technical | `__________` |
| Specialist Behavior | grpc-specialist-behavior | `__________` |
| Specialist Evolution | grpc-specialist-evolution | `__________` |
| Specialist Architecture | grpc-specialist-architecture | `__________` |
| Consensus (total) | consensus-processing | `__________` |
| Orchestrator (total) | orchestrator-processing | `__________` |
| **E2E Total** | root to leaf | `__________` |

### 6.5 Exportar Trace via API

```bash
# Buscar trace por ID
curl -s "http://localhost:16686/api/traces/$TRACE_ID" | jq '.data[0].spans | length'

# Exportar trace completo
curl -s "http://localhost:16686/api/traces/$TRACE_ID" > /tmp/trace-e2e-$TRACE_ID.json
```

---

## 7. Validacao de Persistencia

### 7.1 MongoDB - Correlacao Completa

**Query de Agregacao:**
```bash
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
db.cognitive_ledger.aggregate([
  {\$match: {intent_id: '$INTENT_ID'}},
  {\$group: {_id: '\$type', count: {\$sum: 1}}}
])
" neural_hive
```

**Output Esperado:**
```
{ _id: 'intent', count: 1 }
{ _id: 'plan', count: 1 }
{ _id: 'opinion', count: 5 }
```

**Verificar consensus_decisions:**
```bash
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
  db.consensus_decisions.countDocuments({intent_id: '$INTENT_ID'})
" neural_hive
```

**Verificar execution_tickets:**
```bash
kubectl exec -n $NAMESPACE_MONGODB $MONGODB_POD -- mongosh --eval "
  db.execution_tickets.countDocuments({intent_id: '$INTENT_ID'})
" neural_hive
```

**Checklist de Validacao MongoDB:**
- [ ] `cognitive_ledger`: 1 intent
- [ ] `cognitive_ledger`: 1 plan
- [ ] `cognitive_ledger`: 5 opinions
- [ ] `consensus_decisions`: 1 decisao
- [ ] `execution_tickets`: N tickets

---

### 7.2 Redis - Estado de Cache e Feromonios

**Verificar Cache:**
```bash
# Intent cache
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli EXISTS "intent:$INTENT_ID"

# Plan cache
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli EXISTS "plan:$PLAN_ID"
```

**Verificar Feromonios:**
```bash
# Contar feromonios
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli KEYS 'pheromone:*' | wc -l

# Verificar feromonio especifico
kubectl exec -n $NAMESPACE_REDIS $REDIS_POD -- \
  redis-cli HGETALL "pheromone:technical:biometric-auth:SUCCESS"
```

**Checklist de Validacao Redis:**
- [ ] Cache de intent presente
- [ ] Cache de plan presente
- [ ] Feromonios criados (> 0 keys)
- [ ] Campos de feromonios corretos

---

### 7.3 ClickHouse - Metricas Historicas (ML Pipelines)

**Verificar tabelas de metricas:**
```bash
kubectl exec -n clickhouse clickhouse-0 -- clickhouse-client --query "
  SELECT
    count() as total_records,
    min(timestamp) as first_record,
    max(timestamp) as last_record
  FROM neural_hive.ml_metrics
  WHERE intent_id = '$INTENT_ID'
"
```

**Verificar latencias historicas:**
```bash
kubectl exec -n clickhouse clickhouse-0 -- clickhouse-client --query "
  SELECT
    component,
    avg(latency_ms) as avg_latency,
    max(latency_ms) as max_latency,
    count() as samples
  FROM neural_hive.latency_metrics
  WHERE timestamp > now() - INTERVAL 1 HOUR
  GROUP BY component
  ORDER BY avg_latency DESC
"
```

**Checklist de Validacao ClickHouse:**
- [ ] Registros de metricas presentes
- [ ] Latencias registradas por componente
- [ ] Timestamps recentes

---

## 8. Relatorio de Resultados

### 8.1 Resumo Executivo

**Data de Execucao**: _______________
**Executado por**: _______________
**Ambiente**: _______________

### 8.2 IDs Capturados

| Campo | Valor |
|-------|-------|
| intent_id | `_________________________________` |
| trace_id | `_________________________________` |
| plan_id | `_________________________________` |
| decision_id | `_________________________________` |
| ticket_id (primeiro) | `_________________________________` |

### 8.3 Metricas Consolidadas

| Metrica | Valor | Status |
|---------|-------|--------|
| Tempo total E2E | _____ ms | [] |
| Gateway latency | _____ ms | [] |
| STE latency | _____ ms | [] |
| Consensus latency | _____ ms | [] |
| Orchestrator latency | _____ ms | [] |
| Specialists responderam | ___/5 | [] |
| Confidence final | _____ | [] |
| Consensus score | _____ | [] |
| Divergence score | _____ | [] |
| Tickets gerados | _____ | [] |
| Erros encontrados | _____ | [] |

### 8.4 Status Final

- [ ] PASS: Todos os fluxos funcionaram corretamente
- [ ] PARTIAL: Alguns componentes falharam (detalhar)
- [ ] FAIL: Falha critica no pipeline (detalhar)

### 8.5 Observacoes e Issues

```
[Anotar aqui qualquer comportamento inesperado, erros, timeouts ou insights]





```

### 8.6 Proximos Passos Recomendados

1. [ ] Executar testes com diferentes tipos de intencoes
2. [ ] Testar cenarios de falha (specialist timeout)
3. [ ] Validar comportamento de retry
4. [ ] Testar carga (multiplas intencoes simultaneas)
5. [ ] Configurar alertas no Prometheus
6. [ ] Criar dashboards no Grafana

---

## Anexos

### A. Script de Execucao Automatizada

```bash
#!/usr/bin/env bash
# Script: run-e2e-tests.sh
# Executa testes E2E completos e gera relatorio

set -euo pipefail

# Importar variaveis de ambiente
source ./e2e-env.sh

# Executar Fluxo A
echo "=== Executando Fluxo A ==="
# ... comandos do Fluxo A

# Executar Fluxo B
echo "=== Executando Fluxo B ==="
# ... comandos do Fluxo B

# Executar Fluxo C
echo "=== Executando Fluxo C ==="
# ... comandos do Fluxo C

# Coletar metricas
echo "=== Coletando Metricas ==="
# ... comandos de metricas

# Gerar relatorio
echo "=== Gerando Relatorio ==="
./scripts/15-validate-e2e-results.sh --output-file /tmp/e2e-report.md

echo "Teste E2E concluido!"
```

### B. Troubleshooting

| Problema | Causa Provavel | Solucao |
|----------|----------------|---------|
| Gateway nao responde | Pod nao esta Running | `kubectl get pods -n gateway-intencoes` |
| Kafka sem mensagens | Consumer group offset | Reset offset: `kafka-consumer-groups.sh --reset-offsets` |
| Specialists timeout | Conectividade gRPC | Verificar NetworkPolicies |
| MongoDB sem dados | Erro de persistencia | Verificar logs e conectividade |
| Metricas ausentes | ServiceMonitor | `kubectl get servicemonitor -A` |
| Traces incompletos | Sampling rate | Verificar configuracao do Jaeger |

---

**Documento gerado automaticamente**
**Versao**: 1.0.0
**Neural Hive-Mind E2E Testing Playbook**
