# Comandos para Correção de Bloqueadores Críticos
## Neural Hive-Mind - Fase 1

---

## 🔴 BLOQUEADOR 1: Tópicos Kafka Faltantes

### Problema
```
❌ plans.ready não existe
❌ plans.consensus não existe
```

### Solução (5 minutos)

```bash
# Criar tópico plans.ready
kubectl apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: plans-ready
  namespace: kafka
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: 604800000  # 7 dias
    segment.bytes: 1073741824
    cleanup.policy: delete
EOF

# Criar tópico plans.consensus
kubectl apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: plans-consensus
  namespace: kafka
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: 604800000  # 7 dias
    segment.bytes: 1073741824
    cleanup.policy: delete
EOF
```

### Validação

```bash
# Listar todos os tópicos
kubectl get kafkatopic -n kafka

# Verificar status dos novos tópicos
kubectl get kafkatopic plans-ready -n kafka -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
kubectl get kafkatopic plans-consensus -n kafka -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'

# Resultado esperado: True
```

---

## 🔴 BLOQUEADOR 2: Publicação Kafka Falha

### Problema
```
Script phase1-end-to-end-test.sh não consegue publicar mensagens
Função kafka_publish_message() falha após 3 tentativas
```

### Diagnóstico (10 minutos)

```bash
# 1. Verificar conectividade do Kafka
kubectl get svc -n kafka neural-hive-kafka-kafka-bootstrap

# 2. Testar com port-forward
kubectl port-forward -n kafka svc/neural-hive-kafka-kafka-bootstrap 9092:9092 &
PF_PID=$!

# Aguardar 3 segundos
sleep 3

# 3. Testar conectividade local
nc -zv localhost 9092

# 4. Publicar mensagem de teste usando kcat (se disponível)
echo '{"test":"message","timestamp":'$(date +%s)'}' | \
  kcat -P -b localhost:9092 -t intentions.business

# OU usando kafka-console-producer localmente
echo '{"test":"message","timestamp":'$(date +%s)'}' | \
  kafka-console-producer.sh --bootstrap-server localhost:9092 --topic intentions.business

# 5. Consumir para validar
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic intentions.business --from-beginning --max-messages 1

# 6. Limpar port-forward
kill $PF_PID
```

### Solução Alternativa: Script Python

Se a abordagem com pod efêmero falhar, usar producer Python:

```bash
# Criar script de publicação
cat > /tmp/kafka_producer.py <<'EOF'
#!/usr/bin/env python3
import sys
import json
from kafka import KafkaProducer

def publish_message(bootstrap_servers, topic, message):
    try:
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks=1,
            retries=3,
            request_timeout_ms=10000
        )

        future = producer.send(topic, message)
        record_metadata = future.get(timeout=10)

        print(f"✅ Mensagem publicada com sucesso!")
        print(f"   Topic: {record_metadata.topic}")
        print(f"   Partition: {record_metadata.partition}")
        print(f"   Offset: {record_metadata.offset}")

        producer.close()
        return 0
    except Exception as e:
        print(f"❌ Erro ao publicar: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: kafka_producer.py <bootstrap_servers> <topic> <json_message>")
        sys.exit(1)

    bootstrap_servers = sys.argv[1]
    topic = sys.argv[2]
    message = json.loads(sys.argv[3])

    sys.exit(publish_message(bootstrap_servers, topic, message))
EOF

chmod +x /tmp/kafka_producer.py

# Instalar dependência (se necessário)
pip3 install kafka-python

# Criar port-forward
kubectl port-forward -n kafka svc/neural-hive-kafka-kafka-bootstrap 9092:9092 &
PF_PID=$!
sleep 3

# Publicar mensagem de teste
python3 /tmp/kafka_producer.py localhost:9092 intentions.business \
  '{"test":"message","timestamp":'$(date +%s)'}'

# Limpar
kill $PF_PID
```

### Validação

```bash
# Consumir últimas mensagens do tópico
kubectl port-forward -n kafka svc/neural-hive-kafka-kafka-bootstrap 9092:9092 &
PF_PID=$!
sleep 3

kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic intentions.business --from-beginning --max-messages 5

kill $PF_PID
```

---

## 🔴 BLOQUEADOR 3: Serialização Protobuf (TypeError)

### Problema
```
Consensus Engine:
  [error] Falha ao obter parecer de especialista
  error='RetryError[<Future ... raised TypeError>]'
```

### Diagnóstico (15 minutos)

```bash
# 1. Verificar versões de protobuf nos pods
kubectl exec -n consensus-engine \
  $(kubectl get pod -n consensus-engine -l app.kubernetes.io/name=consensus-engine -o jsonpath='{.items[0].metadata.name}') \
  -- pip3 list | grep protobuf

kubectl exec -n specialist-business \
  $(kubectl get pod -n specialist-business -l app.kubernetes.io/name=specialist-business -o jsonpath='{.items[0].metadata.name}') \
  -- pip3 list | grep protobuf

# 2. Verificar schemas no Apicurio Registry
kubectl port-forward -n kafka svc/schema-registry 8081:8081 &
PF_PID=$!
sleep 3

curl http://localhost:8081/apis/ccompat/v6/subjects | jq .

# 3. Baixar schema de cognitive-plan
curl http://localhost:8081/apis/ccompat/v6/subjects/cognitive-plan-value/versions/latest \
  | jq -r '.schema' | jq . > /tmp/cognitive-plan-schema.json

# 4. Baixar schema de specialist-opinion
curl http://localhost:8081/apis/ccompat/v6/subjects/specialist-opinion-value/versions/latest \
  | jq -r '.schema' | jq . > /tmp/specialist-opinion-schema.json

kill $PF_PID

# 5. Verificar arquivos .proto locais
ls -la proto/
cat proto/specialist.proto | grep -A 5 "message Opinion"
```

### Solução: Re-gerar Schemas Protobuf (30 minutos)

```bash
# 1. Re-gerar código protobuf para todos os serviços
./scripts/generate_protos.sh

# 2. Re-build imagens dos serviços afetados
# Consensus Engine
docker build -t neural-hive-mind/consensus-engine:1.0.8 services/consensus-engine/
docker tag neural-hive-mind/consensus-engine:1.0.8 neural-hive-mind/consensus-engine:latest

# 5 Specialists (se necessário)
for specialist in business technical behavior evolution architecture; do
  docker build -t neural-hive-mind/specialist-${specialist}:1.0.8 services/specialist-${specialist}/
  docker tag neural-hive-mind/specialist-${specialist}:1.0.8 neural-hive-mind/specialist-${specialist}:latest
done

# 3. Carregar imagens no cluster (se usando kind/minikube)
kind load docker-image neural-hive-mind/consensus-engine:1.0.8
for specialist in business technical behavior evolution architecture; do
  kind load docker-image neural-hive-mind/specialist-${specialist}:1.0.8
done

# OU para containerd direto
ctr -n k8s.io images import consensus-engine-1.0.8.tar
for specialist in business technical behavior evolution architecture; do
  ctr -n k8s.io images import specialist-${specialist}-1.0.8.tar
done

# 4. Atualizar deployments
kubectl set image deployment/consensus-engine -n consensus-engine \
  consensus-engine=neural-hive-mind/consensus-engine:1.0.8

for specialist in business technical behavior evolution architecture; do
  kubectl set image deployment/specialist-${specialist} -n specialist-${specialist} \
    specialist-${specialist}=neural-hive-mind/specialist-${specialist}:1.0.8
done

# 5. Aguardar rollout
kubectl rollout status deployment/consensus-engine -n consensus-engine --timeout=5m

for specialist in business technical behavior evolution architecture; do
  kubectl rollout status deployment/specialist-${specialist} -n specialist-${specialist} --timeout=5m
done
```

### Solução Alternativa: Downgrade Temporário

Se re-build não for viável imediatamente:

```bash
# Verificar versões anteriores das imagens
crictl images | grep -E "specialist|consensus"

# Reverter para última versão conhecida funcional (se existir)
kubectl set image deployment/consensus-engine -n consensus-engine \
  consensus-engine=neural-hive-mind/consensus-engine:1.0.6

for specialist in business technical behavior evolution architecture; do
  kubectl set image deployment/specialist-${specialist} -n specialist-${specialist} \
    specialist-${specialist}=neural-hive-mind/specialist-${specialist}:1.0.6
done
```

### Validação

```bash
# 1. Verificar logs do Consensus Engine
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=50

# Procurar por:
# ✅ "Specialists gRPC client inicializado"
# ✅ "gRPC channel initialized" (5 vezes)
# ❌ "TypeError" ou "RetryError"

# 2. Publicar mensagem de teste e monitorar
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=50 -f &
LOG_PID=$!

# Publicar Intent Envelope (usar método que funcionar do BLOQUEADOR 2)

# Aguardar 30 segundos e verificar logs
sleep 30
kill $LOG_PID

# 3. Verificar se specialists processaram
for specialist in business technical behavior evolution architecture; do
  echo "=== specialist-$specialist ==="
  kubectl logs -n specialist-$specialist -l app.kubernetes.io/name=specialist-$specialist --tail=20 | grep -i "plan_id"
done
```

---

## ⚠️ PROBLEMA SECUNDÁRIO: Specialist Business Crashloop

### Diagnóstico

```bash
# 1. Identificar pod problemático
kubectl get pods -n specialist-business

# 2. Verificar logs atuais
kubectl logs -n specialist-business specialist-business-5d774d6f95-wzcvp --tail=100

# 3. Verificar logs anteriores (antes do último restart)
kubectl logs -n specialist-business specialist-business-5d774d6f95-wzcvp --previous

# 4. Descrever pod para ver eventos
kubectl describe pod -n specialist-business specialist-business-5d774d6f95-wzcvp
```

### Solução Rápida

```bash
# Deletar pod problemático (será recriado automaticamente)
kubectl delete pod specialist-business-5d774d6f95-wzcvp -n specialist-business

# Aguardar novo pod ficar ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=specialist-business -n specialist-business --timeout=2m

# Verificar status
kubectl get pods -n specialist-business
```

---

## ⚠️ PROBLEMA SECUNDÁRIO: Specialist Technical Pod Pending

### Diagnóstico

```bash
# Verificar por que está Pending
kubectl describe pod -n specialist-technical specialist-technical-685bf56bbd-tzzx2 | grep -A 10 "Events:"

# Verificar recursos do cluster
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### Solução

Se for falta de recursos:

```bash
# Opção 1: Escalar down para 1 réplica
kubectl scale deployment specialist-technical -n specialist-technical --replicas=1

# Opção 2: Reduzir resource requests
kubectl set resources deployment specialist-technical -n specialist-technical \
  --requests=cpu=50m,memory=128Mi --limits=cpu=500m,memory=512Mi
```

---

## 📊 Validação Final (Após Correções)

### 1. Verificar Tópicos Kafka

```bash
kubectl get kafkatopic -n kafka

# Resultado esperado:
# intentions.business         Ready
# intentions.infrastructure   Ready
# intentions.security         Ready
# intentions.technical        Ready
# intentions.validation       Ready
# plans.ready                 Ready  ← NOVO
# plans.consensus             Ready  ← NOVO
```

### 2. Verificar Todos os Pods

```bash
# Verificar status de todos os componentes da Fase 1
for ns in gateway-intencoes semantic-translation-engine consensus-engine memory-layer-api \
          specialist-business specialist-technical specialist-behavior specialist-evolution specialist-architecture; do
  echo "=== $ns ==="
  kubectl get pods -n $ns
done

# Resultado esperado: Todos Running, nenhum com restarts excessivos
```

### 3. Re-executar Teste E2E

```bash
# Executar teste completo
cd /jimy/Neural-Hive-Mind
./tests/phase1-end-to-end-test.sh --continue-on-error --debug

# Verificar relatórios gerados
ls -lht tests/results/

# Analisar resultado
cat tests/results/phase1-test-summary-*.md
```

### 4. Validação Manual do Fluxo

```bash
# 1. Publicar Intent Envelope
kubectl port-forward -n kafka svc/neural-hive-kafka-kafka-bootstrap 9092:9092 &
PF_PID=$!
sleep 3

INTENT_ID="test-intent-$(date +%s)"
echo "{
  \"id\": \"${INTENT_ID}\",
  \"actor\": {\"type\":\"human\",\"id\":\"test-user\",\"name\":\"Test User\"},
  \"intent\": {
    \"text\":\"Criar workflow de aprovação de pedidos\",
    \"domain\":\"business\",
    \"classification\":\"workflow-automation\"
  },
  \"confidence\":0.95,
  \"timestamp\":$(date +%s)000
}" | kafka-console-producer.sh --bootstrap-server localhost:9092 --topic intentions.business

echo "Intent ID: $INTENT_ID"

# 2. Monitorar STE
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine -f &
STE_PID=$!

# Aguardar 15 segundos
sleep 15

# 3. Verificar se Plan foi gerado
kill $STE_PID
kubectl logs -n semantic-translation-engine -l app.kubernetes.io/name=semantic-translation-engine --tail=50 | grep "$INTENT_ID"

# 4. Verificar Consensus Engine
kubectl logs -n consensus-engine -l app.kubernetes.io/name=consensus-engine --tail=100 | grep -A 5 "plan_id"

# 5. Verificar MongoDB
MONGO_POD=$(kubectl get pod -n mongodb-cluster -l app=mongodb -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n mongodb-cluster $MONGO_POD -- \
  mongosh --quiet --eval "db.cognitive_ledger.find({intent_id: '${INTENT_ID}'}).pretty()"

# Limpar
kill $PF_PID
```

---

## 📝 Checklist de Correções

- [ ] Criar tópico `plans.ready`
- [ ] Criar tópico `plans.consensus`
- [ ] Validar tópicos criados (status Ready)
- [ ] Testar publicação Kafka via port-forward
- [ ] Resolver TypeError de serialização protobuf
- [ ] Re-gerar schemas protobuf (se necessário)
- [ ] Re-build e re-deploy serviços afetados
- [ ] Validar logs do Consensus Engine (sem TypeError)
- [ ] Deletar pod specialist-business problemático
- [ ] Resolver pod specialist-technical Pending
- [ ] Re-executar teste E2E completo
- [ ] Validar fluxo manual (Intent → Plan → Decision)
- [ ] Documentar resultados finais

---

## 🎯 Critério de Sucesso

✅ **Teste E2E considerado bem-sucedido quando**:

1. Todos os 7 tópicos Kafka estão Ready
2. Publicação de Intent Envelope funciona sem erros
3. STE gera Cognitive Plan em < 10s
4. 5/5 Specialists avaliam o plano (ou mínimo 3/5)
5. Consensus Engine gera decisão consolidada
6. Registros persistidos no MongoDB
7. Nenhum erro de TypeError nos logs
8. Relatório E2E com status "PASSED" nas 5 fases

---

**Estimativa Total**: 2-4 horas (incluindo troubleshooting)
**Prioridade**: P0 (Crítico para operacionalização)
**Próxima Revisão**: Após execução de correções
