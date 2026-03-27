# Validação End-to-End Manual do Fluxo de Intenção

> **📘 Guia Completo**: Para validação detalhada com Prometheus, Jaeger, MongoDB e Redis, consulte:  
> [`docs/manual-deployment/08-e2e-testing-manual-guide.md`](docs/manual-deployment/08-e2e-testing-manual-guide.md)

## Objetivo
Validar cada passo do pipeline de processamento de intenções (Fluxos A, B e C), analisando inputs, outputs, métricas, traces e persistência em cada etapa.

## Recursos Auxiliares

- **📋 Checklist Estruturado**: [`docs/manual-deployment/E2E_TESTING_CHECKLIST.md`](docs/manual-deployment/E2E_TESTING_CHECKLIST.md)
- **🔧 Preparar Dados de Teste**: `./scripts/14-prepare-e2e-test-data.sh`
- **✅ Validar Resultados**: `./scripts/15-validate-e2e-results.sh`

---

## PASSO 1: VALIDAR GATEWAY - HEALTH CHECK

### 📥 INPUT
```bash
# Resolver nome do pod dinamicamente
GATEWAY_POD=$(kubectl get pod -n gateway-intencoes -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}')

# Comando
kubectl exec -n gateway-intencoes $GATEWAY_POD -- python3 -c "import requests; r = requests.get('http://localhost:8000/health'); print(r.status_code); print(r.json())"
```

### 📤 OUTPUT ESPERADO
```json
{
  "status": "healthy",
  "timestamp": "2025-...",
  "version": "1.0.0",
  "service_name": "gateway-intencoes",
  "components": {
    "redis": {"status": "healthy"},
    "asr_pipeline": {"status": "healthy"},
    "nlu_pipeline": {"status": "healthy"},
    "kafka_producer": {"status": "healthy"}
  }
}
```

### ✅ CRITÉRIOS DE SUCESSO
- HTTP Status Code: 200
- status: "healthy"
- Todos os components: "healthy"

---

## PASSO 2: ENVIAR INTENÇÃO AO GATEWAY

### 📥 INPUT
```bash
# Criar arquivo com payload
cat > /tmp/intent-request.json <<'EOF'
{
  "text": "Analisar viabilidade técnica de implementar autenticação biométrica no aplicativo móvel",
  "language": "pt-BR",
  "correlation_id": "test-manual-001"
}
EOF

# Enviar intenção (usar GATEWAY_POD do PASSO 1)
kubectl exec -n gateway-intencoes $GATEWAY_POD -- python3 -c "
import requests
import json

with open('/tmp/intent-request.json') as f:
    payload = json.load(f)

r = requests.post('http://localhost:8000/intentions', json=payload)
print('Status:', r.status_code)
print('Response:', json.dumps(r.json(), indent=2))
"
```

### 📤 OUTPUT ESPERADO
```json
{
  "intent_id": "uuid-gerado",
  "correlation_id": "test-manual-001",
  "status": "processed",
  "confidence": 0.85,
  "domain": "technical",
  "classification": "analysis_request",
  "processing_time_ms": 150.5
}
```

### ✅ CRITÉRIOS DE SUCESSO
- HTTP Status Code: 200
- intent_id: UUID válido
- status: "processed"
- confidence: > 0.7
- domain: identificado
- Tempo < 500ms

### 📝 ANOTAR
- `intent_id`: ________________________
- `correlation_id`: ________________________
- `trace_id`: ________________________ (para busca no Jaeger)
- `domain`: ________________________
- `confidence`: ________________________

---

## PASSO 3: VERIFICAR LOGS DO GATEWAY - PUBLICAÇÃO NO KAFKA

> **📖 Detalhes**: [Seção 4.3 do guia completo](docs/manual-deployment/08-e2e-testing-manual-guide.md#43-validar-logs-do-gateway)

### 📥 INPUT
```bash
# Ver logs recentes do Gateway (usar GATEWAY_POD do PASSO 1)
kubectl logs -n gateway-intencoes $GATEWAY_POD --tail=50 | grep -i "kafka\|producer\|intent"
```

### 📤 OUTPUT ESPERADO
```
Processando intenção de texto, intent_id=..., correlation_id=test-manual-001
Pipeline NLU processou, domain=technical, confidence=0.85
Publicando no Kafka, topic=intentions.technical, partition=..., offset=...
Intenção publicada com sucesso, intent_id=...
```

### ✅ CRITÉRIOS DE SUCESSO
- Log de "Processando intenção de texto"
- Log de NLU com domain e confidence
- Log de publicação no Kafka (topic: `intentions.technical`)
- Log de sucesso
- Sem logs de erro

### 🔍 VALIDAÇÕES ADICIONAIS

#### 3.1. Métricas no Prometheus
```bash
# Port-forward (se ainda não estiver ativo)
kubectl port-forward -n observability svc/prometheus-server 9090:80 &

# Verificar métrica de intenções publicadas
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_intents_published_total{service="gateway-intencoes"}' | jq '.data.result[0].value[1]'
```
**Esperado**: Valor incrementado

#### 3.2. Trace no Jaeger
```bash
# Port-forward (se ainda não estiver ativo)
kubectl port-forward -n observability svc/jaeger-query 16686:16686 &
```
1. Acessar: http://localhost:16686
2. Service: `gateway-intencoes`
3. Buscar por `trace_id` anotado no PASSO 2
4. Verificar spans: NLU processing, Kafka publish

#### 3.3. Cache no Redis
```bash
REDIS_POD=$(kubectl get pod -n redis -l app=redis -o jsonpath='{.items[0].metadata.name}')
INTENT_ID="<intent_id_do_passo_2>"

kubectl exec -n redis $REDIS_POD -- redis-cli GET "intent:$INTENT_ID"
```
**Esperado**: JSON do IntentEnvelope cacheado

---

## PASSO 4: VERIFICAR SEMANTIC TRANSLATION ENGINE

### 📥 INPUT
```bash
# Resolver nome do pod dinamicamente
STE_POD=$(kubectl get pod -n semantic-translation -l app=semantic-translation-engine -o jsonpath='{.items[0].metadata.name}')

# Ver logs do Semantic Translation Engine
kubectl logs -n semantic-translation $STE_POD --tail=100 | grep -i "consumed\|intent\|plan"
```

### 📤 OUTPUT ESPERADO
```
Consumindo mensagem do Kafka, topic=neural-hive.intents
Intent recebido, intent_id=..., domain=technical
Analisando intenção, classificação=analysis_request
Gerando plano cognitivo, specialists=[business, technical, architecture]
Plan gerado, plan_id=..., num_specialists=3
Publicando plan no Kafka, topic=neural-hive.plans
```

### ✅ CRITÉRIOS DE SUCESSO
- Log de consumo do tópico `neural-hive.intents`
- Log de intent recebido com mesmo intent_id do PASSO 2
- Log de geração de plano
- Lista de specialists identificados
- Log de publicação no tópico `neural-hive.plans`
- Sem erros

### 📝 ANOTAR
- `plan_id`: ________________________
- `specialists`: ________________________

### 🔍 VALIDAÇÕES ADICIONAIS

#### 4.1. Persistência no MongoDB
```bash
MONGODB_POD=$(kubectl get pod -n mongodb -l app=mongodb -o jsonpath='{.items[0].metadata.name}')
PLAN_ID="<plan_id_anotado>"

kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval \
  "db.cognitive_ledger.findOne({plan_id: '$PLAN_ID'})" neural_hive
```
**Verificar campos**: `tasks`, `explainability_token`, `created_at`, `status`

#### 4.2. Métricas do STE no Prometheus
```bash
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_plans_generated_total' | jq
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_plan_risk_score' | jq
```

#### 4.3. Trace do STE no Jaeger
- Buscar pelo mesmo `trace_id` do PASSO 2
- Verificar spans adicionais: semantic parsing, DAG generation, risk scoring
- Verificar correlação com spans do Gateway

---

## PASSO 5: VERIFICAR CONSENSUS ENGINE

### 📥 INPUT
```bash
# Resolver nome do pod dinamicamente
CONSENSUS_POD=$(kubectl get pod -n consensus-engine -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}')

# Ver logs do Consensus Engine
kubectl logs -n consensus-engine $CONSENSUS_POD --tail=100 | grep -i "consumed\|plan\|specialist\|grpc"
```

### 📤 OUTPUT ESPERADO
```
Consumindo mensagem do Kafka, topic=neural-hive.plans
Plan recebido, plan_id=..., intent_id=...
Orquestrando specialists, lista=[business, technical, architecture]
Chamando specialist-business via gRPC, endpoint=specialist-business.specialist-business:50051
Chamando specialist-technical via gRPC
Chamando specialist-architecture via gRPC
Opiniões recebidas: 3/3
Agregando opiniões, consensus_score=...
Decisão final gerada
Publicando resultado no Kafka
```

### ✅ CRITÉRIOS DE SUCESSO
- Log de consumo do tópico `neural-hive.plans`
- Log de plan recebido com plan_id do PASSO 4
- Logs de chamadas gRPC para cada specialist
- Log de agregação de opiniões
- Log de decisão final
- Sem timeouts ou erros de conexão

### 📝 ANOTAR
- Quantos specialists responderam: ____/____
- Teve timeout?: ________________________

---

## PASSO 6: VERIFICAR SPECIALISTS INDIVIDUAIS

Para cada specialist, executar:

### 6.1 SPECIALIST BUSINESS

#### 📥 INPUT
```bash
BUSINESS_POD=$(kubectl get pod -n specialist-business -l app=specialist-business -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n specialist-business $BUSINESS_POD --tail=50 | grep -i "GetOpinion\|request\|response"
```

#### 📤 OUTPUT ESPERADO
```
Received GetOpinion request, request_id=..., intent_id=...
Processing opinion, domain=business, aspect=viability
Generated opinion, confidence=0.82, sentiment=positive
Returning opinion response
```

#### ✅ CRITÉRIOS
- Log de requisição GetOpinion recebida
- Log de processamento
- Log de resposta enviada
- Confidence score gerado

---

### 6.2 SPECIALIST TECHNICAL

#### 📥 INPUT
```bash
TECHNICAL_POD=$(kubectl get pod -n specialist-technical -l app=specialist-technical -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n specialist-technical $TECHNICAL_POD --tail=50 | grep -i "GetOpinion\|request\|response"
```

#### 📤 OUTPUT ESPERADO
```
Received GetOpinion request, request_id=..., intent_id=...
Processing opinion, domain=technical, aspect=feasibility
Analyzing technical constraints
Generated opinion, confidence=0.88, recommendations=[...]
Returning opinion response
```

#### ✅ CRITÉRIOS
- Similar ao business specialist
- Deve ter recomendações técnicas

---

### 6.3 SPECIALIST ARCHITECTURE

#### 📥 INPUT
```bash
ARCHITECTURE_POD=$(kubectl get pod -n specialist-architecture -l app=specialist-architecture -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n specialist-architecture $ARCHITECTURE_POD --tail=50 | grep -i "GetOpinion\|request\|response"
```

#### 📤 OUTPUT ESPERADO
```
Received GetOpinion request
Analyzing architectural implications
Generated architectural opinion, patterns_suggested=[...]
```

---

### 6.4 SPECIALIST BEHAVIOR

#### 📥 INPUT
```bash
BEHAVIOR_POD=$(kubectl get pod -n specialist-behavior -l app=specialist-behavior -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n specialist-behavior $BEHAVIOR_POD --tail=50 | grep -i "GetOpinion\|request\|response"
```

---

### 6.5 SPECIALIST EVOLUTION

#### 📥 INPUT
```bash
EVOLUTION_POD=$(kubectl get pod -n specialist-evolution -l app=specialist-evolution -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n specialist-evolution $EVOLUTION_POD --tail=50 | grep -i "GetOpinion\|request\|response"
```

### 🔍 VALIDAÇÕES ADICIONAIS DOS SPECIALISTS

#### 6.6. Persistência de Opiniões no MongoDB
```bash
kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval \
  "db.cognitive_ledger.find({plan_id: '$PLAN_ID', specialist_type: {\$exists: true}}).count()" neural_hive
```
**Esperado**: 5 opiniões

#### 6.7. Métricas dos Specialists no Prometheus
```bash
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_specialist_opinions_total' | jq
```

#### 6.8. Traces dos Specialists no Jaeger
- Buscar pelo `trace_id` original
- Verificar 5 spans (um por specialist)
- Tags esperadas: `specialist.type`, `opinion.recommendation`

---

## PASSO 7: VERIFICAR FLUXO C - CONSENSUS ENGINE

> **📖 Detalhes**: [Seção 7 do guia completo](docs/manual-deployment/08-e2e-testing-manual-guide.md#7-fase-4---teste-do-fluxo-c-consensus-engine--decisão)

### 📥 INPUT
```bash
# Ver logs do Consensus Engine
CONSENSUS_POD=$(kubectl get pod -n consensus-engine -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n consensus-engine $CONSENSUS_POD --tail=100 | grep -i "consumed\|plan\|decision\|aggreg"
```

### 📤 OUTPUT ESPERADO
```
Consumindo mensagem do Kafka, topic=plans.ready
Plan recebido, plan_id=..., intent_id=...
Orquestrando specialists, lista=[business, technical, behavior, evolution, architecture]
Chamando specialist-business via gRPC
Chamando specialist-technical via gRPC
Chamando specialist-behavior via gRPC
Chamando specialist-evolution via gRPC
Chamando specialist-architecture via gRPC
Opiniões recebidas: 5/5
Agregando opiniões, método=bayesian
Divergence score=0.15
Decisão final gerada, decision_id=...
Publicando no Kafka, topic=plans.consensus
Publicando feromônios no Redis
```

### ✅ CRITÉRIOS DE SUCESSO
- Log de consumo do tópico `plans.ready`
- Log de plan recebido com `plan_id` do PASSO 4
- Logs de chamadas gRPC para todos os 5 specialists
- Log de agregação de opiniões
- Log de decisão final
- Log de publicação no Kafka e Redis
- Sem timeouts ou erros

### 📝 ANOTAR
- `decision_id`: ________________________
- `final_decision`: ________________________
- `consensus_score`: ________________________
- `divergence_score`: ________________________

### 🔍 VALIDAÇÕES ADICIONAIS

#### 7.1. Persistência da Decisão no MongoDB
```bash
DECISION_ID="<decision_id_anotado>"

kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval \
  "db.consensus_decisions.findOne({decision_id: '$DECISION_ID'})" neural_hive
```
**Verificar campos**: `specialist_votes`, `consensus_metrics`, `explainability_token`

#### 7.2. Feromônios no Redis
```bash
# Listar keys de feromônios
kubectl exec -n redis $REDIS_POD -- redis-cli KEYS 'pheromone:*'

# Exemplo de query específica
kubectl exec -n redis $REDIS_POD -- redis-cli HGETALL 'pheromone:business:workflow-analysis:SUCCESS'
```
**Verificar campos**: `strength`, `plan_id`, `decision_id`, `created_at`

#### 7.3. Métricas do Consensus Engine no Prometheus
```bash
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_consensus_decisions_total' | jq
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_consensus_divergence_score' | jq
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_pheromone_strength' | jq
```

#### 7.4. Trace do Consensus Engine no Jaeger
- Buscar pelo `trace_id` original
- Verificar spans: plan consumption, specialist orchestration, bayesian aggregation, decision publish
- Verificar correlação com spans anteriores (Gateway → STE → Specialists)

---

## PASSO 8: VERIFICAR FLUXO C - ORCHESTRATOR DYNAMIC

> **📖 Detalhes**: [Seção 8 do guia completo](docs/manual-deployment/08-e2e-testing-manual-guide.md#8-fase-5---teste-do-fluxo-c-orchestrator--execution-tickets)

### 📥 INPUT
```bash
# Ver logs do Orchestrator Dynamic
ORCHESTRATOR_POD=$(kubectl get pod -n orchestrator-dynamic -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n orchestrator-dynamic $ORCHESTRATOR_POD --tail=100 | grep -i "consumed\|decision\|ticket\|execution"
```

### 📤 OUTPUT ESPERADO
```
Consumindo mensagem do Kafka, topic=plans.consensus
Decisão recebida, decision_id=..., plan_id=...
Gerando execution tickets
Ticket gerado, ticket_id=..., task_type=..., priority=HIGH
Ticket gerado, ticket_id=..., task_type=..., priority=MEDIUM
Total de tickets gerados: 5
Publicando tickets no Kafka, topic=execution.tickets
Tickets persistidos no MongoDB
```

### ✅ CRITÉRIOS DE SUCESSO
- Log de consumo do tópico `plans.consensus`
- Log de decisão recebida com `decision_id` do PASSO 7
- Logs de geração de tickets
- Log de publicação no Kafka
- Log de persistência no MongoDB
- Sem erros

### 📝 ANOTAR
- `ticket_id` (primeiro): ________________________
- Número de tickets gerados: ________________________

### 🔍 VALIDAÇÕES ADICIONAIS

#### 8.1. Persistência de Tickets no MongoDB
```bash
kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval \
  "db.execution_tickets.find({plan_id: '$PLAN_ID'}).count()" neural_hive
```
**Esperado**: Número de tickets gerados

```bash
TICKET_ID="<ticket_id_anotado>"
kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval \
  "db.execution_tickets.findOne({ticket_id: '$TICKET_ID'})" neural_hive
```
**Verificar campos**: `status`, `priority`, `sla.deadline`, `dependencies[]`

#### 8.2. Métricas do Orchestrator no Prometheus
```bash
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_execution_tickets_generated_total' | jq
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_orchestrator_processing_duration_seconds' | jq
```

#### 8.3. Trace do Orchestrator no Jaeger
- Buscar pelo `trace_id` original
- Verificar spans: decision consumption, ticket generation, Kafka publish
- **Verificar trace completo end-to-end**: Gateway → STE → Specialists → Consensus → Orchestrator

---

## PASSO 9: VALIDAÇÃO CONSOLIDADA END-TO-END

> **📖 Detalhes**: [Seção 9 do guia completo](docs/manual-deployment/08-e2e-testing-manual-guide.md#9-validação-consolidada-e2e)

### 9.1. Verificar Correlação Completa no MongoDB
```bash
INTENT_ID="<intent_id_do_passo_2>"

kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval "
db.cognitive_ledger.aggregate([
  {\$match: {intent_id: '$INTENT_ID'}},
  {\$group: {_id: '\$type', count: {\$sum: 1}}}
])
" neural_hive
```

**Esperado**:
- intents: 1
- plans: 1
- opinions: 5

```bash
# Verificar decisões
kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval \
  "db.consensus_decisions.findOne({intent_id: '$INTENT_ID'})" neural_hive

# Verificar tickets
kubectl exec -n mongodb $MONGODB_POD -- mongosh --eval \
  "db.execution_tickets.find({intent_id: '$INTENT_ID'}).count()" neural_hive
```

### 9.2. Verificar Trace Completo no Jaeger
1. Acessar: http://localhost:16686
2. Buscar por `trace_id` inicial (do PASSO 2)
3. Verificar presença de todos os spans:
   - Gateway (NLU, Kafka publish)
   - STE (semantic parsing, DAG generation)
   - 5 Specialists (opinion generation)
   - Consensus Engine (aggregation, decision)
   - Orchestrator (ticket generation)
4. Verificar duração total end-to-end
5. Verificar latências por componente

### 9.3. Verificar Métricas Agregadas no Prometheus
```bash
# Taxa de intenções (últimos 5 minutos)
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(neural_hive_intents_published_total[5m]))' | jq

# Taxa de planos
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(neural_hive_plans_generated_total[5m]))' | jq

# Taxa de decisões
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(neural_hive_consensus_decisions_total[5m]))' | jq

# Taxa de tickets
curl -s 'http://localhost:9090/api/v1/query?query=sum(rate(neural_hive_execution_tickets_generated_total[5m]))' | jq
```

**Verificar**: Todas as taxas devem ser consistentes (sem perdas)

### 9.4. Verificar Feromônios Agregados no Redis
```bash
# Contagem total de keys de feromônios
kubectl exec -n redis $REDIS_POD -- redis-cli --scan --pattern 'pheromone:*' | wc -l

# Verificar força líquida de exemplo
kubectl exec -n redis $REDIS_POD -- redis-cli HGET 'pheromone:business:workflow-analysis:SUCCESS' strength
```

---

## PASSO 10: VERIFICAR MEMORY LAYER API (OPCIONAL)

### 📥 INPUT
```bash
# Usar o intent_id anotado no PASSO 2
INTENT_ID="<intent_id_do_passo_2>"

# Validar formato UUID do INTENT_ID
if [[ ! "$INTENT_ID" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
  echo "❌ ERRO: INTENT_ID inválido. Deve ser um UUID válido."
  echo "   Formato esperado: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  exit 1
fi

# Pré-interpolar URL no shell (evita problemas de interpolação Python)
FULL_URL="http://localhost:8000/api/v1/intents/$INTENT_ID"

# Resolver nome do pod dinamicamente
MEMORY_LAYER_POD=$(kubectl get pod -n memory-layer-api -l app=memory-layer-api -o jsonpath='{.items[0].metadata.name}')

# Verificar se pod foi encontrado
if [[ -z "$MEMORY_LAYER_POD" ]]; then
  echo "❌ ERRO: Nenhum pod encontrado para memory-layer-api"
  exit 1
fi

# Aguardar pod estar pronto
echo "⏳ Aguardando pod $MEMORY_LAYER_POD estar pronto..."
kubectl wait --for=condition=ready pod/$MEMORY_LAYER_POD -n memory-layer-api --timeout=30s

# Consultar Memory Layer com tratamento robusto de erros
echo "🔍 Consultando Memory Layer: $FULL_URL"
kubectl exec -n memory-layer-api $MEMORY_LAYER_POD -- python3 -c "
import requests
import json

try:
    # Realizar GET com timeout e headers
    r = requests.get(
        '$FULL_URL',
        timeout=10,
        headers={'User-Agent': 'E2E-Test'}
    )
    
    print('Status:', r.status_code)
    
    if r.status_code == 200:
        print('Response:', json.dumps(r.json(), indent=2))
    else:
        print('Error:', r.text)
        
except requests.exceptions.Timeout:
    print('❌ Python Error: Request timeout após 10s')
except requests.exceptions.ConnectionError as e:
    print('❌ Python Error: Falha de conexão -', str(e))
except json.JSONDecodeError as e:
    print('❌ Python Error: Resposta não é JSON válido -', str(e))
except Exception as e:
    print('❌ Python Error:', str(e))
"
```

### 📤 OUTPUT ESPERADO
```json
{
  "intent_id": "...",
  "status": "completed",
  "domain": "technical",
  "confidence": 0.85,
  "plan": {
    "plan_id": "...",
    "specialists_consulted": ["business", "technical", "architecture"]
  },
  "opinions": [
    {
      "specialist": "business",
      "confidence": 0.82,
      "sentiment": "positive"
    },
    ...
  ],
  "consensus": {
    "decision": "approved",
    "confidence": 0.85
  },
  "created_at": "...",
  "updated_at": "..."
}
```

### ✅ CRITÉRIOS DE SUCESSO
- HTTP Status Code: 200
- intent_id: corresponde ao anotado
- status: "completed"
- Contém plan com specialists
- Contém opinions de cada specialist
- Contém consensus com decisão final

---

## RESUMO DA VALIDAÇÃO

### Checklist Geral

#### Fluxo A (Gateway → Kafka)
- [ ] **PASSO 1**: Gateway respondendo health check
- [ ] **PASSO 2**: Intenção aceita e processada
- [ ] **PASSO 3**: Logs confirmam publicação no Kafka
- [ ] **PASSO 3.1**: Métricas do Gateway no Prometheus
- [ ] **PASSO 3.2**: Trace do Gateway no Jaeger
- [ ] **PASSO 3.3**: Cache no Redis

#### Fluxo B (STE → Specialists → Plano)
- [ ] **PASSO 4**: Semantic Translation processou e gerou plan
- [ ] **PASSO 4.1**: Plano persistido no MongoDB
- [ ] **PASSO 4.2**: Métricas do STE no Prometheus
- [ ] **PASSO 4.3**: Trace do STE no Jaeger
- [ ] **PASSO 5**: Consensus Engine orquestrou specialists
- [ ] **PASSO 6**: Todos specialists responderam
  - [ ] Business
  - [ ] Technical
  - [ ] Architecture
  - [ ] Behavior
  - [ ] Evolution
- [ ] **PASSO 6.6**: Opiniões persistidas no MongoDB (5 total)
- [ ] **PASSO 6.7**: Métricas dos Specialists no Prometheus
- [ ] **PASSO 6.8**: Traces dos Specialists no Jaeger

#### Fluxo C (Consensus → Orchestrator → Tickets)
- [ ] **PASSO 7**: Consensus Engine agregou opiniões e gerou decisão
- [ ] **PASSO 7.1**: Decisão persistida no MongoDB
- [ ] **PASSO 7.2**: Feromônios publicados no Redis
- [ ] **PASSO 7.3**: Métricas do Consensus Engine no Prometheus
- [ ] **PASSO 7.4**: Trace do Consensus Engine no Jaeger
- [ ] **PASSO 8**: Orchestrator gerou execution tickets
- [ ] **PASSO 8.1**: Tickets persistidos no MongoDB
- [ ] **PASSO 8.2**: Métricas do Orchestrator no Prometheus
- [ ] **PASSO 8.3**: Trace do Orchestrator no Jaeger

#### Validação Consolidada E2E
- [ ] **PASSO 9.1**: Correlação completa verificada no MongoDB
- [ ] **PASSO 9.2**: Trace end-to-end completo no Jaeger
- [ ] **PASSO 9.3**: Métricas agregadas consistentes no Prometheus
- [ ] **PASSO 9.4**: Feromônios agregados no Redis
- [ ] **PASSO 10**: Memory Layer armazenou e retornou dados completos (opcional)

### Métricas Coletadas

| Métrica | Valor | Status |
|---------|-------|--------|
| Tempo total E2E | _____ ms | ⏱️ |
| Gateway latency | _____ ms | ⏱️ |
| Semantic Translation latency | _____ ms | ⏱️ |
| Consensus Engine latency | _____ ms | ⏱️ |
| Specialists responderam | ___/5 | 📊 |
| Confidence final | _____ | 📊 |
| Erros encontrados | _____ | ❌ |

### Observações

```
INCONSISTÊNCIAS IDENTIFICADAS - Teste E2E 2025-11-27

======================================================================
ISSUE #1 - CRÍTICO: correlation_id não propagado no Fluxo C
======================================================================
Componente: Orchestrator Dynamic
Erro: "1 validation error for FlowCContext - correlation_id - Input should be
      a valid string [type=string_type, input_value=None]"
Impacto: Execution tickets NÃO são gerados
Causa Raiz: Consensus Engine publica decisões com correlation_id=null
Evidência: MongoDB mostra correlation_id: null nas decisões
Fix Necessário:
  - services/consensus-engine/src/services/consensus_orchestrator.py
  - Propagar correlation_id do plano original para a decisão

======================================================================
ISSUE #2 - ALTO: Timeout gRPC insuficiente para Specialists
======================================================================
Componente: Consensus Engine → Specialists (gRPC)
Erro: "Timeout ao invocar especialista timeout_ms=5000"
Impacto: 0/5 specialists respondiam, fluxo falhava completamente
Causa Raiz:
  - ConfigMap usava SPECIALIST_GRPC_TIMEOUT_MS mas código espera GRPC_TIMEOUT_MS
  - Specialists levam ~6-8s para processar (modelo ML + heurísticas)
  - Timeout padrão era 5s (insuficiente)
Fix Aplicado:
  - Adicionado GRPC_TIMEOUT_MS=15000 no ConfigMap
  - Atualizado helm-charts/consensus-engine/values-local.yaml para 15000ms
Pendente:
  - Atualizar templates Helm para usar variável correta

======================================================================
ISSUE #3 - ALTO: Endpoints de Specialists incorretos no values-local.yaml
======================================================================
Componente: helm-charts/consensus-engine/values-local.yaml
Configuração Incorreta (ANTES):
  - specialist-business.specialist-business.svc.cluster.local:50051
Configuração Correta (DEPOIS):
  - specialist-business.semantic-translation.svc.cluster.local:50051
Fix Aplicado: Corrigidos os 5 endpoints no values-local.yaml

======================================================================
ISSUE #4 - MÉDIO: Modelo ML com atributo incompatível
======================================================================
Componente: Specialists (business, technical, etc.)
Erro: "'DecisionTreeClassifier' object has no attribute 'monotonic_cst'"
Impacto: Inferência ML falha, sistema usa fallback heurístico
Causa Raiz: Incompatibilidade sklearn entre treino e inferência
Workaround: Fallback para heurísticas funciona

======================================================================
ISSUE #5 - MÉDIO: Consumer loop finaliza após erro
======================================================================
Componente: Consensus Engine Kafka Consumer
Log: "Consumer loop finalizado" após erro de processamento
Impacto: Novas mensagens não processadas até restart

======================================================================
ISSUE #6 - BAIXO: Schema Registry não configurado (JSON fallback)
ISSUE #7 - BAIXO: Neo4j sem dados históricos (similar intents = 0)
ISSUE #8 - BAIXO: OpenTelemetry desabilitado (sem traces no Jaeger)
======================================================================







```

---

## Próximos Passos

Com base nos resultados:

1. ✅ **Se todos passos passaram**: Sistema está funcionando corretamente end-to-end
2. ⚠️ **Se alguns specialists não responderam**: Investigar conectividade gRPC
3. ❌ **Se falhou no Kafka**: Verificar configuração de brokers e tópicos
4. ❌ **Se Memory Layer não tem dados**: Verificar persistência e Redis

