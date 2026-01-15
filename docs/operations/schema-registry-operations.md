# Schema Registry - Runbook Operacional

> Procedimentos operacionais para o Apicurio Registry no Neural Hive-Mind.

## Informações do Sistema

| Item | Valor |
|------|-------|
| **Namespace** | `kafka` |
| **Service** | `schema-registry.kafka.svc.cluster.local:8081` |
| **Deployment** | `apicurio-registry` |
| **Replicas** | 1 (stateless, escalável horizontalmente) |
| **Storage Backend** | Kafka topics (`_schemas`, `_schemas_snapshot`) |
| **Health Check Sidecar** | Porta 8090, endpoint `/health/schemas` |

---

## Procedimentos de Startup

### Startup do Schema Registry

```bash
# Restart do deployment
kubectl rollout restart deployment/apicurio-registry -n kafka

# Aguardar rollout completo
kubectl rollout status deployment/apicurio-registry -n kafka

# Verificar health
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -sf http://localhost:8080/health/ready && echo "✅ Registry Ready" || echo "❌ Registry Not Ready"
```

### Verificar Schemas Após Startup

```bash
# Verificar schemas críticos via sidecar
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -c schema-health-checker -- \
  curl -s http://localhost:8090/health/schemas | jq .

# Listar todos os subjects
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq .
```

### Re-executar Init Job (se schemas ausentes)

```bash
# Deletar job anterior (se existir)
kubectl delete job schema-registry-init -n kafka --ignore-not-found

# Aplicar init job
kubectl apply -f k8s/jobs/schema-registry-init-job.yaml

# Acompanhar logs
kubectl logs -n kafka job/schema-registry-init -f
```

---

## Procedimentos de Manutenção

### Backup de Schemas

Os schemas são armazenados em Kafka topics. Para backup:

```bash
# Exportar conteúdo do topic _schemas
kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic _schemas \
  --from-beginning \
  --timeout-ms 10000 > schemas-backup-$(date +%Y%m%d).json

# Exportar lista de subjects via API
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq . > subjects-backup-$(date +%Y%m%d).json
```

### Restore de Schemas

```bash
# Opção 1: Re-aplicar init job (recomendado)
kubectl apply -f k8s/jobs/schema-registry-init-job.yaml

# Opção 2: Importar via API (para schemas individuais)
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -X POST -H "Content-Type: application/json" \
  -d '{"schema": "<schema-json>", "schemaType": "AVRO"}' \
  http://localhost:8080/apis/ccompat/v6/subjects/<subject>/versions
```

### Limpeza de Schemas Obsoletos

```bash
# Listar versões de um subject
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/<subject>/versions | jq .

# Deletar versão específica (soft delete)
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -X DELETE http://localhost:8080/apis/ccompat/v6/subjects/<subject>/versions/<version>

# Deletar subject inteiro (soft delete)
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -X DELETE http://localhost:8080/apis/ccompat/v6/subjects/<subject>

# Hard delete (permanente)
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -X DELETE http://localhost:8080/apis/ccompat/v6/subjects/<subject>?permanent=true
```

### Verificação de Integridade Semanal

```bash
#!/bin/bash
# Script de verificação semanal

REGISTRY_POD=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')
CRITICAL_SUBJECTS=("plans.ready-value" "execution.tickets-value")

echo "=== Schema Registry Weekly Check ==="
echo "Date: $(date)"
echo ""

# Verificar schemas críticos
echo "[1/3] Verificando schemas críticos..."
for subject in "${CRITICAL_SUBJECTS[@]}"; do
  if kubectl exec -n kafka $REGISTRY_POD -- curl -sf http://localhost:8080/apis/ccompat/v6/subjects/$subject/versions/latest > /dev/null 2>&1; then
    echo "  ✅ $subject"
  else
    echo "  ❌ $subject MISSING"
  fi
done

# Contar total de schemas
echo ""
echo "[2/3] Total de schemas:"
kubectl exec -n kafka $REGISTRY_POD -- curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq 'length'

# Verificar métricas
echo ""
echo "[3/3] Métricas do Registry:"
kubectl exec -n kafka $REGISTRY_POD -- curl -s http://localhost:8080/q/metrics | grep registry_artifacts_total
```

---

## Procedimentos de Gestão de Schemas

### Adicionar Novo Schema

**Pré-condições**:
- Schema Registry operacional (verificar com health check)
- Schema Avro válido e testado localmente
- Subject name definido conforme convenção (ex: `<topic>-value`, `<topic>-key`)
- Modo de compatibilidade do subject definido (default: `BACKWARD`)

**Procedimento**:

```bash
# 1. Definir variáveis
REGISTRY_POD=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')
SUBJECT_NAME="meu-topico-value"
SCHEMA_FILE="path/to/schema.avsc"

# 2. Verificar se o subject já existe
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions

# 3. Validar compatibilidade antes de registrar (se subject existir)
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"schema\": $(cat $SCHEMA_FILE | jq -Rs .), \"schemaType\": \"AVRO\"}" \
  http://localhost:8080/apis/ccompat/v6/compatibility/subjects/$SUBJECT_NAME/versions/latest

# Resposta esperada: {"is_compatible": true}

# 4. Registrar novo schema
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"schema\": $(cat $SCHEMA_FILE | jq -Rs .), \"schemaType\": \"AVRO\"}" \
  http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions

# Resposta esperada: {"id": <schema-id>}

# 5. Validação pós-registro - verificar se schema foi registrado
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/latest | jq .

# 6. Verificar schema ID retornado
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/schemas/ids/<schema-id> | jq .
```

**Validação pós-registro**:

```bash
# Confirmar versão registrada
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions | jq .

# Testar serialização com o novo schema (exemplo Python)
kubectl exec -n <namespace> <producer-pod> -- python3 -c "
from confluent_kafka.schema_registry import SchemaRegistryClient
sr = SchemaRegistryClient({'url': 'http://schema-registry.kafka.svc.cluster.local:8081'})
schema = sr.get_latest_version('$SUBJECT_NAME')
print(f'Schema ID: {schema.schema_id}, Version: {schema.version}')
"
```

### Migrar para Nova Versão de Schema

**Pré-condições**:
- Schema atual registrado e em uso pelos producers/consumers
- Novo schema compatível com o modo de compatibilidade configurado
- Plano de rollback documentado
- Backup do schema atual realizado

**Procedimento**:

```bash
# 1. Definir variáveis
REGISTRY_POD=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')
SUBJECT_NAME="plans.ready-value"
NEW_SCHEMA_FILE="path/to/new-schema.avsc"

# 2. Listar versões atuais do subject
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions | jq .

# 3. Obter schema atual para backup
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/latest | jq . > backup-$SUBJECT_NAME-$(date +%Y%m%d%H%M%S).json

# 4. Verificar modo de compatibilidade atual
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/config/$SUBJECT_NAME | jq .

# 5. Testar compatibilidade do novo schema
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"schema\": $(cat $NEW_SCHEMA_FILE | jq -Rs .), \"schemaType\": \"AVRO\"}" \
  http://localhost:8080/apis/ccompat/v6/compatibility/subjects/$SUBJECT_NAME/versions/latest

# IMPORTANTE: Só prosseguir se resposta for {"is_compatible": true}

# 6. Registrar nova versão do schema
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"schema\": $(cat $NEW_SCHEMA_FILE | jq -Rs .), \"schemaType\": \"AVRO\"}" \
  http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions

# 7. Verificar nova versão registrada
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/latest | jq .

# 8. Reiniciar producers para usar nova versão (rolling restart)
kubectl rollout restart deployment/<producer-deployment> -n <namespace>
kubectl rollout status deployment/<producer-deployment> -n <namespace>

# 9. Monitorar métricas de serialização após migração
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/q/metrics | grep -E "http_server_requests.*subjects"
```

**Checklist de migração**:

| Etapa | Verificação | Status |
|-------|-------------|--------|
| Backup schema atual | Arquivo JSON salvo | [ ] |
| Teste de compatibilidade | `is_compatible: true` | [ ] |
| Registro nova versão | Schema ID retornado | [ ] |
| Producers atualizados | Rollout completo | [ ] |
| Métricas estáveis | Sem erros de serialização | [ ] |
| Consumers operacionais | Mensagens sendo consumidas | [ ] |

### Rollback de Schema

**Cenários de rollback**:
1. **Incompatibilidade detectada após migração**: Consumers não conseguem deserializar
2. **Bug no novo schema**: Campos incorretos ou faltando
3. **Problemas de performance**: Novo schema causando overhead

**Procedimento de Rollback - Opção 1: Forçar uso de versão anterior**

```bash
# 1. Definir variáveis
REGISTRY_POD=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')
SUBJECT_NAME="plans.ready-value"
TARGET_VERSION=1  # Versão para rollback

# 2. Listar todas as versões disponíveis
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions | jq .

# 3. Obter schema da versão alvo
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/$TARGET_VERSION | jq .

# 4. Salvar schema da versão alvo
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/$TARGET_VERSION | jq -r '.schema' > rollback-schema.avsc

# 5. Temporariamente desabilitar verificação de compatibilidade
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X PUT -H "Content-Type: application/json" \
  -d '{"compatibility": "NONE"}' \
  http://localhost:8080/apis/ccompat/v6/config/$SUBJECT_NAME

# 6. Re-registrar schema anterior (cria nova versão com conteúdo antigo)
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"schema\": $(cat rollback-schema.avsc | jq -Rs .), \"schemaType\": \"AVRO\"}" \
  http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions

# 7. Restaurar modo de compatibilidade
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X PUT -H "Content-Type: application/json" \
  -d '{"compatibility": "BACKWARD"}' \
  http://localhost:8080/apis/ccompat/v6/config/$SUBJECT_NAME

# 8. Verificar versão atual
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/latest | jq .

# 9. Reiniciar producers para usar schema restaurado
kubectl rollout restart deployment/<producer-deployment> -n <namespace>
```

**Procedimento de Rollback - Opção 2: Deletar versão problemática e recriar subject**

> **ATENÇÃO**: Este procedimento causa indisponibilidade temporária. Use apenas em emergências.

```bash
# 1. Definir variáveis
REGISTRY_POD=$(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}')
SUBJECT_NAME="plans.ready-value"

# 2. Exportar schema desejado (versão anterior)
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/1 | jq -r '.schema' > restore-schema.avsc

# 3. Soft delete do subject (marca como deletado)
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X DELETE http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME

# 4. Hard delete do subject (remove permanentemente)
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X DELETE "http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME?permanent=true"

# 5. Recriar subject com schema anterior
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"schema\": $(cat restore-schema.avsc | jq -Rs .), \"schemaType\": \"AVRO\"}" \
  http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions

# 6. Validar recriação
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/latest | jq .

# 7. Reiniciar todos os producers e consumers afetados
kubectl rollout restart deployment/<producer-deployment> -n <namespace>
kubectl rollout restart deployment/<consumer-deployment> -n <namespace>
```

**Validação pós-rollback**:

```bash
# 1. Verificar schema ativo
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/apis/ccompat/v6/subjects/$SUBJECT_NAME/versions/latest | jq .

# 2. Verificar health do sidecar
kubectl exec -n kafka $REGISTRY_POD -c schema-health-checker -- \
  curl -s http://localhost:8090/health/schemas | jq .

# 3. Monitorar logs de serialização nos producers
kubectl logs -n <namespace> -l app=<producer> --tail=50 | grep -i "schema\|avro\|serial"

# 4. Verificar métricas de erro
kubectl exec -n kafka $REGISTRY_POD -- \
  curl -s http://localhost:8080/q/metrics | grep -E "http_server_requests.*error"

# 5. Confirmar consumo de mensagens
kubectl logs -n <namespace> -l app=<consumer> --tail=50 | grep -i "consumed\|processed"
```

**Checklist de rollback**:

| Etapa | Verificação | Status |
|-------|-------------|--------|
| Schema anterior identificado | Versão e conteúdo confirmados | [ ] |
| Backup do schema atual | Arquivo JSON salvo | [ ] |
| Rollback executado | Nova versão com schema antigo | [ ] |
| Compatibilidade restaurada | Modo BACKWARD ativo | [ ] |
| Producers reiniciados | Rollout completo | [ ] |
| Consumers operacionais | Sem erros de deserialização | [ ] |
| Métricas estáveis | Sem alertas ativos | [ ] |

---

## Procedimentos de Scaling

### Scale Horizontal

O Apicurio Registry é stateless e suporta múltiplas réplicas:

```bash
# Aumentar réplicas
kubectl scale deployment/apicurio-registry -n kafka --replicas=3

# Verificar distribuição
kubectl get pods -n kafka -l app=apicurio-registry -o wide

# Verificar endpoints do service
kubectl get endpoints -n kafka schema-registry
```

### Scale Down

```bash
# Reduzir réplicas (mínimo 1)
kubectl scale deployment/apicurio-registry -n kafka --replicas=1
```

---

## Procedimentos de Upgrade

### Upgrade do Apicurio Registry

1. **Backup de schemas**
   ```bash
   kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic _schemas \
     --from-beginning \
     --timeout-ms 10000 > pre-upgrade-backup.json
   ```

2. **Atualizar imagem no deployment**
   ```bash
   kubectl set image deployment/apicurio-registry -n kafka \
     apicurio-registry=apicurio/apicurio-registry-mem:<nova-versao>
   ```

3. **Rolling update**
   ```bash
   kubectl rollout status deployment/apicurio-registry -n kafka
   ```

4. **Validar schemas após upgrade**
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq 'length'
   ```

5. **Testar serialização/deserialização**
   ```bash
   # Executar testes de integração
   make test-avro-integration
   ```

---

## Monitoramento de Rotina

### Métricas Prometheus

| Métrica | Descrição | Threshold |
|---------|-----------|-----------|
| `registry_artifacts_total` | Número total de schemas | > 0 |
| `http_server_requests_seconds` | Latência de requisições | p95 < 100ms |
| `jvm_memory_used_bytes` | Uso de memória JVM | < 80% do limite |
| `http_server_requests_seconds_count` | Taxa de requisições | baseline |

```bash
# Verificar métricas
kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
  curl -s http://localhost:8080/q/metrics | grep -E "(registry_artifacts|http_server_requests|jvm_memory)"
```

### Verificar Alertas Ativos

```bash
# Listar regras de alerta
kubectl get prometheusrules -n kafka schema-registry-alerts -o yaml

# Verificar alertas disparados (via Prometheus)
curl -s http://prometheus.monitoring.svc.cluster.local:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname | startswith("Schema"))'
```

### Dashboard Grafana

- **Dashboard**: "Schema Registry Overview"
- **Painéis**:
  - Total de schemas registrados
  - Latência p50/p95/p99
  - Taxa de requisições por endpoint
  - Uso de memória JVM
  - Health status

---

## Resposta a Alertas

### SchemaRegistryDown

**Descrição**: Schema Registry não está respondendo

**Ações**:
1. Verificar logs do pod
   ```bash
   kubectl logs -n kafka -l app=apicurio-registry --tail=100
   ```
2. Verificar status do pod
   ```bash
   kubectl get pods -n kafka -l app=apicurio-registry
   kubectl describe pod -n kafka -l app=apicurio-registry
   ```
3. Verificar conectividade com Kafka
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     nc -zv neural-hive-kafka.kafka.svc.cluster.local 9092
   ```
4. Restart do deployment
   ```bash
   kubectl rollout restart deployment/apicurio-registry -n kafka
   ```

### SchemaRegistryNoSchemas

**Descrição**: Nenhum schema registrado no Registry

**Ações**:
1. Verificar se Kafka está operacional
   ```bash
   kubectl get pods -n kafka -l app.kubernetes.io/name=kafka
   ```
2. Verificar topic `_schemas`
   ```bash
   kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-topics.sh \
     --bootstrap-server localhost:9092 --describe --topic _schemas
   ```
3. Executar init job
   ```bash
   kubectl apply -f k8s/jobs/schema-registry-init-job.yaml
   ```

### SchemaCriticalMissing

**Descrição**: Schemas críticos (`plans.ready-value`, `execution.tickets-value`) não encontrados

**Ações**:
1. Verificar health do sidecar
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -c schema-health-checker -- \
     curl -s http://localhost:8090/health/schemas | jq .
   ```
2. Listar schemas existentes
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -s http://localhost:8080/apis/ccompat/v6/subjects | jq .
   ```
3. Executar init job
   ```bash
   kubectl delete job schema-registry-init -n kafka --ignore-not-found
   kubectl apply -f k8s/jobs/schema-registry-init-job.yaml
   ```

### AvroSerializationFailureHigh

**Descrição**: Alta taxa de falhas de serialização Avro

**Ações**:
1. Verificar configuração de `SCHEMA_REGISTRY_URL` nos producers
   ```bash
   kubectl get configmap -n <namespace> <service>-config -o yaml | grep SCHEMA_REGISTRY_URL
   ```
2. Verificar logs dos producers
   ```bash
   kubectl logs -n <namespace> -l app=<producer> | grep -i "schema\|avro\|serial"
   ```
3. Testar conectividade com Registry
   ```bash
   kubectl exec -n <namespace> <producer-pod> -- curl -sf http://schema-registry.kafka.svc.cluster.local:8081/subjects
   ```

### AvroDeserializationFailureHigh

**Descrição**: Alta taxa de falhas de deserialização Avro

**Ações**:
1. Verificar se mensagens foram produzidas com Schema Registry
   ```bash
   # Consumir mensagem raw
   kubectl exec -n kafka neural-hive-kafka-0 -- /opt/bitnami/kafka/bin/kafka-console-consumer.sh \
     --bootstrap-server localhost:9092 \
     --topic <topic> \
     --max-messages 1 \
     --from-beginning
   ```
2. Verificar magic byte (deve iniciar com `\x00`)
3. Consultar [Troubleshooting Guide](schema-registry-troubleshooting.md#problema-invalid-magic-byte)

### SchemaRegistryHighLatency

**Descrição**: Latência do Registry acima do threshold (p95 > 100ms)

**Ações**:
1. Verificar uso de recursos
   ```bash
   kubectl top pod -n kafka -l app=apicurio-registry
   ```
2. Verificar métricas de latência
   ```bash
   kubectl exec -n kafka $(kubectl get pods -n kafka -l app=apicurio-registry -o jsonpath='{.items[0].metadata.name}') -- \
     curl -s http://localhost:8080/q/metrics | grep http_server_requests_seconds
   ```
3. Aumentar recursos ou escalar horizontalmente
   ```bash
   kubectl scale deployment/apicurio-registry -n kafka --replicas=3
   ```
