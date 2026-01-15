# Schema Registry - Guia de Troubleshooting

> Diagnóstico e resolução de problemas comuns do Apicurio Registry no Neural Hive-Mind.

## Índice

1. [Invalid Magic Byte](#problema-invalid-magic-byte)
2. [Schema Não Encontrado](#problema-schema-não-encontrado)
3. [Schema Registry Indisponível](#problema-schema-registry-indisponível)
4. [Incompatibilidade de Schema](#problema-incompatibilidade-de-schema)
5. [Alta Latência no Registry](#problema-alta-latência-no-registry)
6. [Schemas Críticos Ausentes](#problema-schemas-críticos-ausentes)
7. [Path do Schema Incorreto](#problema-path-do-schema-incorreto)
8. [Comandos de Diagnóstico Rápido](#comandos-de-diagnóstico-rápido)

---

## Problema: Invalid Magic Byte

### Sintomas

- Consumer falha ao deserializar mensagens
- Logs mostram: `This message was not produced with a Confluent Schema Registry serializer`
- Erro: `Invalid magic byte`
- Erro: `Expecting data framing of length 6 bytes or more but total data size is X bytes`

### Causa Raiz

- Mensagem foi produzida em JSON puro, não Avro
- Producer não está usando Schema Registry
- Schema Registry estava indisponível durante produção (fallback para JSON)
- Mistura de mensagens Avro e JSON no mesmo tópico

### Diagnóstico

```bash
# 1. Verificar se producer está configurado com Schema Registry
kubectl get configmap -n <namespace> <service>-config -o yaml | grep SCHEMA_REGISTRY_URL

# 2. Verificar logs do producer
kubectl logs -n <namespace> -l app=<producer> | grep -i "schema\|avro\|fallback"

# 3. Consumir mensagem raw do Kafka para verificar formato
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.ready \
  --max-messages 1 \
  --from-beginning

# Se a mensagem começar com '{', é JSON. Se começar com bytes binários, é Avro.

# 4. Verificar primeiros bytes da mensagem (hex dump)
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic plans.ready \
  --max-messages 1 \
  --from-beginning 2>&1 | xxd | head -1

# Magic byte Avro: 00 (primeiro byte deve ser 0x00)
```

### Solução

1. **Verificar configuração do producer**
   ```bash
   # Verificar que SCHEMA_REGISTRY_URL está definido
   kubectl exec -n <namespace> <producer-pod> -- env | grep SCHEMA_REGISTRY_URL
   ```

2. **Verificar que schema está registrado**
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -s http://localhost:8080/apis/ccompat/v6/subjects/plans.ready-value/versions/latest
   ```

3. **Restart do producer**
   ```bash
   kubectl rollout restart deployment/<producer> -n <namespace>
   ```

4. **Purgar mensagens JSON antigas (se necessário)**
   ```bash
   # Criar arquivo de offsets para deletar
   cat > /tmp/delete-records.json << EOF
   {
     "partitions": [
       {"topic": "plans.ready", "partition": 0, "offset": -1}
     ],
     "version": 1
   }
   EOF

   # Deletar records
   kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-delete-records.sh \
     --bootstrap-server localhost:9092 \
     --offset-json-file /tmp/delete-records.json
   ```

---

## Problema: Schema Não Encontrado

### Sintomas

- Producer falha ao serializar
- Logs mostram: `Schema not found` ou `Subject not found`
- HTTP 404 ao buscar schema
- Erro: `Schema <subject> not found`

### Diagnóstico

```bash
# 1. Listar schemas registrados
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq .

# 2. Verificar subject específico
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -sv http://localhost:8080/apis/ccompat/v6/subjects/plans.ready-value/versions/latest 2>&1

# 3. Verificar se init job foi executado
kubectl get jobs -n kafka | grep schema-registry-init
kubectl logs -n kafka job/schema-registry-init
```

### Solução

1. **Executar init job para registrar schemas**
   ```bash
   kubectl delete job schema-registry-init -n kafka --ignore-not-found
   kubectl apply -f k8s/jobs/schema-registry-init-job.yaml
   kubectl logs -n kafka job/schema-registry-init -f
   ```

2. **Registrar manualmente via API**
   ```bash
   # Carregar schema do arquivo
   SCHEMA=$(cat schemas/cognitive-plan/cognitive-plan.avsc | jq -c . | jq -Rs .)

   # Registrar no Registry
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -X POST \
     -H "Content-Type: application/json" \
     -d "{\"schema\": $SCHEMA, \"schemaType\": \"AVRO\"}" \
     http://localhost:8080/apis/ccompat/v6/subjects/plans.ready-value/versions
   ```

3. **Verificar registro**
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -s http://localhost:8080/apis/ccompat/v6/subjects/plans.ready-value/versions/latest | jq .
   ```

---

## Problema: Schema Registry Indisponível

### Sintomas

- Producers/consumers não conseguem conectar
- Timeout ao acessar Registry
- Logs mostram: `Connection refused` ou `Timeout`
- Erro: `Failed to connect to schema registry`

### Diagnóstico

```bash
# 1. Verificar status do pod
kubectl get pods -n kafka -l app=apicurio-registry
kubectl describe pod -n kafka -l app=apicurio-registry

# 2. Verificar logs
kubectl logs -n kafka -l app=apicurio-registry --tail=100

# 3. Verificar service
kubectl get svc -n kafka schema-registry
kubectl get endpoints -n kafka schema-registry

# 4. Testar conectividade
kubectl run test-registry --image=curlimages/curl --rm -it --restart=Never -- \
  curl -sf http://schema-registry.kafka.svc.cluster.local:8081/health/ready

# 5. Verificar eventos do pod
kubectl get events -n kafka --field-selector involvedObject.name=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')
```

### Solução

1. **Verificar se Kafka está operacional**
   ```bash
   kubectl get pods -n kafka -l app.kubernetes.io/name=kafka
   kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-broker-api-versions.sh \
     --bootstrap-server localhost:9092
   ```

2. **Restart do Registry**
   ```bash
   kubectl rollout restart deployment/apicurio-registry -n kafka
   kubectl rollout status deployment/apicurio-registry -n kafka
   ```

3. **Verificar recursos**
   ```bash
   kubectl top pod -n kafka -l app=apicurio-registry
   kubectl describe pod -n kafka -l app=apicurio-registry | grep -A5 "Limits:\|Requests:"
   ```

4. **Verificar logs de conexão com Kafka**
   ```bash
   kubectl logs -n kafka -l app=apicurio-registry | grep -i "kafka\|connect\|error"
   ```

---

## Problema: Incompatibilidade de Schema

### Sintomas

- Erro ao registrar nova versão de schema
- Logs mostram: `Schema is incompatible with previous version`
- HTTP 409 Conflict
- Erro: `Schema being registered is incompatible with an earlier schema`

### Diagnóstico

```bash
# 1. Verificar versões existentes
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/plans.ready-value/versions | jq .

# 2. Obter schema da última versão
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/plans.ready-value/versions/latest | jq '.schema | fromjson'

# 3. Verificar modo de compatibilidade
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/config/plans.ready-value | jq .

# 4. Testar compatibilidade antes de registrar
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -X POST -H "Content-Type: application/json" \
  -d '{"schema": "{...novo schema...}"}' \
  http://localhost:8080/apis/ccompat/v6/compatibility/subjects/plans.ready-value/versions/latest
```

### Solução

1. **Revisar mudanças para garantir compatibilidade BACKWARD**
   - ✅ Adicionar campos opcionais com defaults
   - ✅ Adicionar novos tipos em unions
   - ❌ Remover campos obrigatórios
   - ❌ Mudar tipo de campos existentes

2. **Exemplo de mudança compatível**
   ```json
   // Adicionar campo opcional
   {"name": "newField", "type": ["null", "string"], "default": null}
   ```

3. **Se breaking change é necessário**
   ```bash
   # Criar novo subject (versionado)
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -X POST -H "Content-Type: application/json" \
     -d '{"schema": "<novo-schema>", "schemaType": "AVRO"}' \
     http://localhost:8080/apis/ccompat/v6/subjects/plans.ready-v2-value/versions
   ```

4. **Desabilitar verificação (apenas desenvolvimento)**
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -X PUT -H "Content-Type: application/json" \
     -d '{"compatibility": "NONE"}' \
     http://localhost:8080/apis/ccompat/v6/config/plans.ready-value
   ```

---

## Problema: Alta Latência no Registry

### Sintomas

- Serialização/deserialização lenta
- Timeout em operações
- Alerta `SchemaRegistryHighLatency` ativo
- p95 latência > 100ms

### Diagnóstico

```bash
# 1. Verificar métricas de latência
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/q/metrics | grep http_server_requests_seconds

# 2. Verificar uso de recursos
kubectl top pod -n kafka -l app=apicurio-registry

# 3. Verificar limites configurados
kubectl describe deployment apicurio-registry -n kafka | grep -A10 "Limits:"

# 4. Verificar performance do Kafka
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-producer-perf-test.sh \
  --topic _schemas \
  --num-records 100 \
  --record-size 100 \
  --throughput -1 \
  --producer-props bootstrap.servers=localhost:9092
```

### Solução

1. **Aumentar recursos**
   ```bash
   kubectl patch deployment apicurio-registry -n kafka -p='{"spec":{"template":{"spec":{"containers":[{"name":"apicurio-registry","resources":{"limits":{"memory":"768Mi","cpu":"1000m"},"requests":{"memory":"512Mi","cpu":"500m"}}}]}}}}'
   ```

2. **Escalar horizontalmente**
   ```bash
   kubectl scale deployment/apicurio-registry -n kafka --replicas=3
   ```

3. **Verificar cache do client**
   ```python
   # Verificar se cache está habilitado no cliente
   # O confluent-kafka habilita cache por padrão
   schema_registry_conf = {
       'url': SCHEMA_REGISTRY_URL,
       # Cache habilitado por padrão
   }
   ```

4. **Otimizar JVM**
   ```yaml
   # No deployment, adicionar JAVA_OPTS
   env:
     - name: JAVA_OPTS
       value: "-Xmx512m -Xms256m -XX:+UseG1GC"
   ```

---

## Problema: Schemas Críticos Ausentes

### Sintomas

- Alerta `SchemaCriticalMissing` ativo
- Health check `/health/schemas` retorna 503
- Serviços não conseguem processar mensagens
- Sidecar reporta schemas missing

### Diagnóstico

```bash
# 1. Verificar health do sidecar
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -c schema-health-checker -- \
  curl -s http://localhost:8090/health/schemas | jq .

# 2. Verificar logs do sidecar
kubectl logs -n kafka -l app=apicurio-registry -c schema-health-checker | grep -i "missing"

# 3. Listar schemas existentes
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq .

# 4. Verificar schemas críticos individualmente
for subject in plans.ready-value execution.tickets-value; do
  echo "Checking $subject..."
  kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
    curl -sf http://localhost:8080/apis/ccompat/v6/subjects/$subject/versions/latest && echo "✅ OK" || echo "❌ MISSING"
done
```

### Solução

1. **Executar init job**
   ```bash
   kubectl delete job schema-registry-init -n kafka --ignore-not-found
   kubectl apply -f k8s/jobs/schema-registry-init-job.yaml
   kubectl logs -n kafka job/schema-registry-init -f
   ```

2. **Verificar que job completou com sucesso**
   ```bash
   kubectl get job schema-registry-init -n kafka
   # STATUS deve ser Complete
   ```

3. **Aguardar próximo health check**
   ```bash
   # Health check ocorre a cada 60s
   # Ou restart do pod para forçar
   kubectl delete pod -n kafka -l app=apicurio-registry
   ```

4. **Verificar ConfigMap de schemas**
   ```bash
   kubectl get configmap schema-files -n kafka -o yaml
   ```

---

## Problema: Path do Schema Incorreto

### Sintomas

- Producer/consumer não encontra arquivo de schema
- Logs mostram: `FileNotFoundError: /app/schemas/cognitive-plan.avsc`
- Fallback para JSON
- Erro: `No such file or directory`

### Causa Raiz

- Path incorreto no código (ex: `/app/schemas/cognitive-plan.avsc` vs `/app/schemas/cognitive-plan/cognitive-plan.avsc`)
- Dockerfile não copia diretório `schemas/` corretamente
- Volume não montado corretamente

### Diagnóstico

```bash
# 1. Verificar estrutura de diretórios no container
kubectl exec -n <namespace> <pod> -- ls -laR /app/schemas/

# 2. Verificar variável de ambiente
kubectl exec -n <namespace> <pod> -- env | grep AVRO_SCHEMA_PATH

# 3. Verificar Dockerfile
cat services/<service>/Dockerfile | grep -A5 "COPY.*schemas"

# 4. Verificar logs de erro
kubectl logs -n <namespace> <pod> | grep -i "schema\|file\|not found"
```

### Solução

1. **Corrigir path no código**
   ```python
   # Errado
   SCHEMA_PATH = '/app/schemas/cognitive-plan.avsc'

   # Correto
   SCHEMA_PATH = '/app/schemas/cognitive-plan/cognitive-plan.avsc'
   ```

2. **Verificar Dockerfile**
   ```dockerfile
   # Copiar estrutura de schemas
   COPY schemas/ /app/schemas/
   ```

3. **Verificar ConfigMap/Volume mount**
   ```yaml
   volumeMounts:
     - name: schemas
       mountPath: /app/schemas
   volumes:
     - name: schemas
       configMap:
         name: schema-files
   ```

4. **Rebuild e redeploy**
   ```bash
   docker build -t <image>:<tag> services/<service>/
   docker push <image>:<tag>
   kubectl rollout restart deployment/<service> -n <namespace>
   ```

---

## Comandos de Diagnóstico Rápido

### Script de Health Check Completo

```bash
#!/bin/bash
echo "=== Schema Registry Health Check ==="
echo "Date: $(date)"
echo ""

REGISTRY_POD=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$REGISTRY_POD" ]; then
  echo "❌ Registry pod not found!"
  exit 1
fi

# 1. Pod status
echo "[1/6] Pod Status:"
kubectl get pods -n kafka -l app=apicurio-registry -o wide
echo ""

# 2. Registry health
echo "[2/6] Registry Health:"
if kubectl exec -n kafka $REGISTRY_POD -- curl -sf http://localhost:8080/health/ready > /dev/null 2>&1; then
  echo "✅ Registry Ready"
else
  echo "❌ Registry Not Ready"
fi
echo ""

# 3. Schemas críticos
echo "[3/6] Critical Schemas:"
kubectl exec -n kafka $REGISTRY_POD -c schema-health-checker -- curl -s http://localhost:8090/health/schemas 2>/dev/null | jq . || echo "⚠️  Health checker not available"
echo ""

# 4. Total de schemas
echo "[4/6] Total Schemas:"
TOTAL=$(kubectl exec -n kafka $REGISTRY_POD -- curl -s http://localhost:8080/apis/ccompat/v6/subjects 2>/dev/null | jq 'length')
echo "Total: $TOTAL schemas"
echo ""

# 5. Métricas
echo "[5/6] Registry Metrics:"
kubectl exec -n kafka $REGISTRY_POD -- curl -s http://localhost:8080/q/metrics 2>/dev/null | grep registry_artifacts_total || echo "⚠️  Metrics not available"
echo ""

# 6. Recursos
echo "[6/6] Resource Usage:"
kubectl top pod -n kafka -l app=apicurio-registry 2>/dev/null || echo "⚠️  Metrics server not available"

echo ""
echo "=== Health Check Complete ==="
```

### Verificação Rápida de Schema Específico

```bash
#!/bin/bash
SUBJECT=${1:-"plans.ready-value"}
REGISTRY_POD=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')

echo "Checking subject: $SUBJECT"
echo ""

# Versões
echo "Versions:"
kubectl exec -n kafka $REGISTRY_POD -- curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT/versions | jq .

# Schema atual
echo ""
echo "Current Schema:"
kubectl exec -n kafka $REGISTRY_POD -- curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT/versions/latest | jq '.schema | fromjson'
```

### One-liner para Diagnóstico

```bash
# Status rápido
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  sh -c 'echo "Health:"; curl -sf http://localhost:8080/health/ready && echo OK || echo FAIL; echo "Schemas:"; curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq length'
```
