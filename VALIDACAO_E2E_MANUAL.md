# Validação End-to-End Manual do Fluxo de Intenção

## Objetivo
Validar cada passo do pipeline de processamento de intenções, analisando inputs e outputs em cada etapa.

---

## PASSO 1: VALIDAR GATEWAY - HEALTH CHECK

### 📥 INPUT
```bash
# Comando
kubectl exec -n gateway-intencoes pod/gateway-intencoes-c84457f84-fqblg -- python3 -c "import requests; r = requests.get('http://localhost:8000/health'); print(r.status_code); print(r.json())"
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

# Enviar intenção
kubectl exec -n gateway-intencoes pod/gateway-intencoes-c84457f84-fqblg -- python3 -c "
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
- `domain`: ________________________
- `confidence`: ________________________

---

## PASSO 3: VERIFICAR LOGS DO GATEWAY - PUBLICAÇÃO NO KAFKA

### 📥 INPUT
```bash
# Ver logs recentes do Gateway
kubectl logs -n gateway-intencoes pod/gateway-intencoes-c84457f84-fqblg --tail=50 | grep -i "kafka\|producer\|intent"
```

### 📤 OUTPUT ESPERADO
```
Processando intenção de texto, intent_id=..., correlation_id=test-manual-001
Pipeline NLU processou, domain=technical, confidence=0.85
Publicando no Kafka, topic=neural-hive.intents, partition=..., offset=...
Intenção publicada com sucesso, intent_id=...
```

### ✅ CRITÉRIOS DE SUCESSO
- Log de "Processando intenção de texto"
- Log de NLU com domain e confidence
- Log de publicação no Kafka
- Log de sucesso
- Sem logs de erro

---

## PASSO 4: VERIFICAR SEMANTIC TRANSLATION ENGINE

### 📥 INPUT
```bash
# Ver logs do Semantic Translation Engine
kubectl logs -n semantic-translation-engine pod/semantic-translation-engine-65678fc7bb-q5bzs --tail=100 | grep -i "consumed\|intent\|plan"
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

---

## PASSO 5: VERIFICAR CONSENSUS ENGINE

### 📥 INPUT
```bash
# Ver logs do Consensus Engine
kubectl logs -n consensus-engine pod/consensus-engine-b5968848d-wsbld --tail=100 | grep -i "consumed\|plan\|specialist\|grpc"
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
kubectl logs -n specialist-business pod/specialist-business-74b97f76c4-lczt6 --tail=50 | grep -i "GetOpinion\|request\|response"
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
kubectl logs -n specialist-technical pod/specialist-technical-98d677d95-vqlc4 --tail=50 | grep -i "GetOpinion\|request\|response"
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
kubectl logs -n specialist-architecture pod/specialist-architecture-58b6fddf5d-pl9tj --tail=50 | grep -i "GetOpinion\|request\|response"
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
kubectl logs -n specialist-behavior pod/specialist-behavior-5595c9966c-tj64h --tail=50 | grep -i "GetOpinion\|request\|response"
```

---

### 6.5 SPECIALIST EVOLUTION

#### 📥 INPUT
```bash
kubectl logs -n specialist-evolution pod/specialist-evolution-765c948dbc-fvg99 --tail=50 | grep -i "GetOpinion\|request\|response"
```

---

## PASSO 7: VERIFICAR MEMORY LAYER API

### 📥 INPUT
```bash
# Usar o intent_id anotado no PASSO 2
INTENT_ID="<intent_id_do_passo_2>"

# Consultar Memory Layer
kubectl exec -n memory-layer-api pod/memory-layer-api-767654798d-2qz48 -- python3 -c "
import requests
r = requests.get(f'http://localhost:8000/api/v1/intents/${INTENT_ID}')
print('Status:', r.status_code)
if r.status_code == 200:
    print('Response:', r.json())
else:
    print('Error:', r.text)
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

- [ ] **PASSO 1**: Gateway respondendo health check
- [ ] **PASSO 2**: Intenção aceita e processada
- [ ] **PASSO 3**: Logs confirmam publicação no Kafka
- [ ] **PASSO 4**: Semantic Translation processou e gerou plan
- [ ] **PASSO 5**: Consensus Engine orquestrou specialists
- [ ] **PASSO 6**: Todos specialists responderam
  - [ ] Business
  - [ ] Technical
  - [ ] Architecture
  - [ ] Behavior
  - [ ] Evolution
- [ ] **PASSO 7**: Memory Layer armazenou e retornou dados completos

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
[Anotar aqui qualquer comportamento inesperado, erros, timeouts, ou insights]










```

---

## Próximos Passos

Com base nos resultados:

1. ✅ **Se todos passos passaram**: Sistema está funcionando corretamente end-to-end
2. ⚠️ **Se alguns specialists não responderam**: Investigar conectividade gRPC
3. ❌ **Se falhou no Kafka**: Verificar configuração de brokers e tópicos
4. ❌ **Se Memory Layer não tem dados**: Verificar persistência e Redis

