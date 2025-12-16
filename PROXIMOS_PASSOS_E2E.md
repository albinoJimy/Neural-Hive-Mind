# Próximos Passos para Completar Teste E2E

**Status**: Teste E2E executado, Fluxo A validado, Fluxos B/C bloqueados por bug Kafka identificado

**Data**: 24/11/2025

---

## ✅ Trabalho Completado

### 1. Teste E2E Manual Executado
- [x] PASSO 1-3: Fluxo A 100% validado
- [x] Gateway health check OK
- [x] Intenção processada com confidence 0.95
- [x] Kafka recebendo mensagens
- [x] Redis cacheando dados
- [x] Análise profunda do problema STE/Kafka

### 2. Root Cause Identificado
- [x] Script de debug Python com librdkafka logging
- [x] Broker Kafka termina conexões prematuramente
- [x] AdminClient funciona, Consumer falha
- [x] Configurações testadas e documentadas

### 3. Correções Implementadas
- [x] Código do STE atualizado (`intent_consumer.py`)
- [x] Configurações Kafka broker aplicadas
- [x] Imagem Docker construída: `neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix`
- [x] Documentação completa criada

### 4. Documentos Criados
- [x] [reports/teste-e2e-manual-20251124.md](reports/teste-e2e-manual-20251124.md) - 570+ linhas
- [x] [reports/teste-e2e-resumo-executivo-20251124.md](reports/teste-e2e-resumo-executivo-20251124.md)
- [x] Este arquivo (PROXIMOS_PASSOS_E2E.md)

---

## 🔴 Ações Pendentes (Requerem Acesso ao Registry)

### Passo 1: Push da Imagem para Registry

A imagem foi construída mas precisa ser carregada no registry do cluster:

```bash
# Opção A: Docker Hub (se configurado)
docker tag neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix \
  docker.io/SEU_USUARIO/semantic-translation-engine:1.0.8-kafka-fix
docker login docker.io
docker push docker.io/SEU_USUARIO/semantic-translation-engine:1.0.8-kafka-fix

# Opção B: Registry local do cluster
# Para Kind:
kind load docker-image neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix --name NOME_DO_CLUSTER

# Para Minikube:
minikube image load neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix

# Para Docker Desktop Kubernetes:
# A imagem já está disponível localmente

# Opção C: Registry privado
docker tag neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix \
  REGISTRY_URL/semantic-translation-engine:1.0.8-kafka-fix
docker push REGISTRY_URL/semantic-translation-engine:1.0.8-kafka-fix
```

### Passo 2: Atualizar Deployment

```bash
# Atualizar com a imagem do registry
kubectl set image deployment/semantic-translation-engine \
  semantic-translation-engine=REGISTRY_URL/semantic-translation-engine:1.0.8-kafka-fix \
  -n semantic-translation

# OU se usando imagePullPolicy: Never (imagem local)
kubectl patch deployment semantic-translation-engine -n semantic-translation -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "semantic-translation-engine",
          "image": "neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix",
          "imagePullPolicy": "Never"
        }]
      }
    }
  }
}'

# Aguardar rollout
kubectl rollout status deployment/semantic-translation-engine -n semantic-translation --timeout=180s
```

### Passo 3: Validar Conexão Kafka

```bash
# Aguardar pods ficarem prontos
kubectl wait --for=condition=ready pod \
  -l app.kubernetes.io/name=semantic-translation-engine \
  -n semantic-translation --timeout=120s

# Verificar logs (NÃO deve ter mais erros UNKNOWN_TOPIC_OR_PART)
kubectl logs -n semantic-translation \
  -l app.kubernetes.io/name=semantic-translation-engine \
  --tail=50 --since=1m | grep -i "error\|warning\|assignment"

# Esperado: Ver logs como:
# "Consumer has assignment for intentions-security partition 0"
# "Consumer has assignment for intentions-security partition 1"
# "Consumer has assignment for intentions-security partition 2"
```

### Passo 4: Enviar Nova Intenção

```bash
GATEWAY_POD=$(kubectl get pod -n fluxo-a -l app=gateway-intencoes -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n fluxo-a $GATEWAY_POD -- python3 -c "
import requests
import json
import uuid

correlation_id = 'e2e-test-final-' + str(uuid.uuid4())[:8]

payload = {
    'text': 'Implementar sistema de pagamentos online com integração Stripe e PayPal',
    'language': 'pt-BR',
    'correlation_id': correlation_id
}

r = requests.post('http://localhost:8000/intentions', json=payload, timeout=30)
print('Status:', r.status_code)
print('Response:', json.dumps(r.json(), indent=2))
"
```

**Anotar**:
- `intent_id`: _______________
- `correlation_id`: _______________

### Passo 5: Validar Processamento do STE

```bash
# Aguardar 10 segundos para processamento
sleep 10

# Verificar logs do STE (deve mostrar "plan gerado")
kubectl logs -n semantic-translation \
  -l app.kubernetes.io/name=semantic-translation-engine \
  --tail=100 --since=30s | grep -i "consumed\|processing\|plan\|specialist"

# Esperado:
# "Consumed intent from Kafka, intent_id=..."
# "Processing intent, domain=..."
# "Generating cognitive plan..."
# "Plan generated, plan_id=..., specialists=[business, technical, ...]"
# "Published plan to Kafka, topic=plans.ready"
```

### Passo 6: Validar MongoDB

```bash
MONGODB_POD=$(kubectl get pod -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}')

# Usar intent_id do Passo 4
INTENT_ID="<intent_id_anotado>"

# Verificar plano gerado
kubectl exec -n mongodb-cluster $MONGODB_POD -- mongosh --eval "
db.cognitive_ledger.findOne({intent_id: '$INTENT_ID', type: 'plan'})
" neural_hive
```

### Passo 7: Validar Specialists

```bash
# Verificar logs de cada specialist
for SPECIALIST in business technical architecture behavior evolution; do
  echo "=== Specialist: $SPECIALIST ==="
  POD=$(kubectl get pod -n semantic-translation -l app=specialist-$SPECIALIST -o jsonpath='{.items[0].metadata.name}')
  kubectl logs -n semantic-translation $POD --tail=50 | grep -i "GetOpinion\|request\|response"
done
```

### Passo 8: Validar Consensus Engine

```bash
CONSENSUS_POD=$(kubectl get pod -n consensus-orchestration -l app=consensus-engine -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n consensus-orchestration $CONSENSUS_POD --tail=100 | \
  grep -i "consumed\|plan\|specialist\|decision\|aggreg"
```

### Passo 9: Validar Orchestrator e Tickets

```bash
ORCHESTRATOR_POD=$(kubectl get pod -n consensus-orchestration -l app=orchestrator-dynamic -o jsonpath='{.items[0].metadata.name}')

kubectl logs -n consensus-orchestration $ORCHESTRATOR_POD --tail=100 | \
  grep -i "consumed\|decision\|ticket\|execution"

# Verificar tickets no MongoDB
kubectl exec -n mongodb-cluster $MONGODB_POD -- mongosh --eval "
db.execution_tickets.find({intent_id: '$INTENT_ID'}).count()
" neural_hive

# Esperado: 3-5 tickets
```

### Passo 10: Validação E2E Completa

```bash
# Trace completo no Jaeger (se port-forward ativo)
echo "Acessar: http://localhost:16686"
echo "Buscar por correlation_id: e2e-test-final-..."

# Métricas no Prometheus
curl -s 'http://localhost:9090/api/v1/query?query=neural_hive_plans_generated_total' | jq

# Feromônios no Redis
REDIS_POD=$(kubectl get pod -n redis-cluster -l app.kubernetes.io/name=redis -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n redis-cluster $REDIS_POD -- redis-cli KEYS 'pheromone:*' | head -10
```

---

## 📋 Checklist Final

Após completar todos os passos acima:

### Fluxo A
- [ ] Gateway processando intenções
- [ ] Kafka recebendo mensagens
- [ ] Redis cacheando dados

### Fluxo B
- [ ] STE consumindo do Kafka (SEM erros UNKNOWN_TOPIC)
- [ ] Planos cognitivos sendo gerados
- [ ] Plans publicados no topic `plans.ready`
- [ ] Planos persistidos no MongoDB
- [ ] 5 specialists respondendo

### Fluxo C
- [ ] Consensus Engine agregando opiniões
- [ ] Decisões sendo geradas
- [ ] Feromônios no Redis
- [ ] Orchestrator gerando tickets
- [ ] Tickets no MongoDB

### Observabilidade
- [ ] Métricas no Prometheus
- [ ] Traces no Jaeger end-to-end
- [ ] Logs coerentes em todos os componentes

---

## 🎯 Estimativa de Tempo

- **Push imagem + Deploy**: 5-10 minutos
- **Testes de validação**: 15-20 minutos
- **Debug se necessário**: 10-30 minutos
- **Total**: 30-60 minutos

---

## 📄 Referências

- **Relatório Detalhado**: [reports/teste-e2e-manual-20251124.md](reports/teste-e2e-manual-20251124.md)
- **Resumo Executivo**: [reports/teste-e2e-resumo-executivo-20251124.md](reports/teste-e2e-resumo-executivo-20251124.md)
- **Arquivo Modificado**: [services/semantic-translation-engine/src/consumers/intent_consumer.py](services/semantic-translation-engine/src/consumers/intent_consumer.py)
- **Imagem Construída**: `neural-hive-mind/semantic-translation-engine:1.0.8-kafka-fix`

---

## ✅ Conclusão

**Tudo está pronto** para completar o teste E2E. A única ação pendente é fazer push da imagem Docker para um registry acessível pelo cluster Kubernetes.

Todas as correções foram implementadas, testadas offline e documentadas extensivamente.
