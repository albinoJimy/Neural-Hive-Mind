# Runbook: Approval Service Queue Backlog

**Alerta:** `ApprovalServiceQueueBacklog`
**Severidade:** Warning
**Camada:** decision

---

## Descrição

A fila de aprovações do Approval Service está crescendo (mais de 100 itens pendentes). Isso pode indicar que o serviço não está processando aprovações rápido o suficiente.

## Impacto

- **Médio:** Planos cognitivos aguardando aprovação
- Usuários podem enfrentar delays em decisões críticas
- Aprovações automáticas (ML) podem estar falhando
- Kafka pode estar com backlog de mensagens

## Primeiras Ações (5 minutos)

### 1. Verificar Tamanho da Fila

```bash
# Via métricas Prometheus
kubectl port-forward -n observability svc/neural-hive-prometheus-kub-prometheus 9090:9090

# Query: approval_queue_size
# Query: approval_queue_rate_{enqueue,dequeue}
```

### 2. Verificar Pods do Approval Service

```bash
kubectl get pods -n neural-hive -l app=approval-service

# Verificar se algum pod está sob carga
kubectl top pods -n neural-hive -l app=approval-service
```

### 3. Verificar Consumer Lag

```bash
# Verificar lag do Kafka
kubectl exec -n kafka -it neural-hive-kafka-0 -- \
  bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group approval-service-group \
  --describe

# Verificar lag mensagens
kubectl logs -n neural-hive -l app=approval-service | grep "lag\|backlog"
```

## Diagnóstico

### Causa Comum 1: Pods Insuficientes

**Sintomas:** CPU/Memory alta, pods throttling

**Diagnóstico:**
```bash
kubectl top pods -n neural-hive -l app=approval-service
kubectl describe pod -n neural-hive <pod-name> | grep -A 5 Limits
```

**Resolução:**
1. Aumentar replicas do deployment
2. Verificar HPA settings
3. Aumentar recursos se necessário

### Causa Comum 2: Consumer Parado

**Sintomas:** Lag aumentando continuamente, pods healthy

**Diagnóstico:**
```bash
# Verificar se consumer está rodando
kubectl logs -n neural-hive -l app=approval-service | grep "consumer.*start\|consumer.*stop"

# Verificar exceptions
kubectl logs -n neural-hive -l app=approval-service | grep -i "exception\|error" | tail -20
```

**Resolução:**
1. Identificar exceção nos logs
2. Corrigir problema (bug, configuração)
3. Restart do deployment

### Causa Comum 3: ML Predictor Lento

**Sintomas:** Aprovações demoram mais que o normal

**Diagnóstico:**
```bash
# Verificar tempo de predição
kubectl logs -n neural-hive -l app=approval-service | grep "prediction.*ms\|inference.*time"

# Verificar se ML predictor está ativo
kubectl logs -n neural-hive -l app=approval-service | grep "ml_predictor.*enabled"
```

**Resolução:**
1. Desabilitar ML prediction temporariamente
2. Aumentar recursos do ML model
3. Considerar cache de predições

### Causa Comum 4: Rejeições em Massa

**Sintomas:** Fila cresce mas itens são processados

**Diagnóstico:**
```bash
# Verificar taxa de rejeição
kubectl logs -n neural-hive -l app=approval-service | grep "rejected\|denied"

# Query: rate(approval_decisions_rejected_total[5m])
```

**Resolução:**
1. Investigar por que há muitas rejeições
2. Verificar se é comportamento esperado
3. Ajustar thresholds de ML se necessário

## Ações de Recuperação

### Recuperação 1: Escalar Pods

```bash
# Aumentar replicas
kubectl scale deployment/approval-service -n neural-hive --replicas=3

# Verificar HPA
kubectl get hpa -n neural-hive -l app=approval-service

# Se HPA existe, ajustar min/max
kubectl patch hpa approval-service -n neural-hive -p '{"spec":{"minReplicas":2,"maxReplicas":10}}'
```

### Recuperação 2: Aumentar Recursos

```bash
# Editar deployment
kubectl edit deployment/approval-service -n neural-hive

# Aumentar limits
# resources:
#   limits:
#     cpu: 1000m  # aumentar de 500m
#     memory: 2Gi  # aumentar de 1Gi
```

### Recuperação 3: Desabilitar ML Temporariamente

⚠️ **Reduz qualidade das decisões**

```bash
# Editar ConfigMap
kubectl edit configmap approval-service-config -n neural-hive

# Alterar
# enable_ml_prediction: "false"

# Restart
kubectl rollout restart deployment/approval-service -n neural-hive
```

### Recuperação 4: Drenar Fila Manualmente

⚠️ **Apenas para recuperação crítica - pode aprovar itens incorretamente**

```bash
# Aprovar todos pendentes (via API)
curl -X POST http://approval-service.neural-hive.svc.cluster.local:8004/admin/drain \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"action": "approve_all", "reason": "emergency_drain"}'
```

## Verificação Pós-Recovery

```bash
# 1. Verificar tamanho da fila reduzindo
# Query: approval_queue_size
# Deve estar < 100 e reduzindo

# 2. Verificar lag do Kafka
kubectl exec -n kafka -it neural-hive-kafka-0 -- \
  bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group approval-service-group \
  --describe | grep -E "LAG|CURRENT-OFFSET"

# 3. Verificar throughput
# Query: rate(approval_decisions_total[5m])
# Deve estar > 0

# 4. Verificar pods sem overload
kubectl top pods -n neural-hive -l app=approval-service
```

## Ajuste de Performance

### Configurar HPA Adequadamente

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: approval-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: approval-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Pods
    pods:
      metric:
        name: approval_queue_size
      target:
        type: AverageValue
        averageValue: "50"
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Otimizar Batch Size

```yaml
# ConfigMap
approval_batch_size: "10"  # Aumentar para processar mais por lote
approval_concurrency: "5"   # Aumentar paralelismo
```

## Escalation

| Tempo | Ação |
|-------|------|
| Imediato | Monitorar taxa de crescimento |
| 5 min | Escalar se crescimento contínuo |
| 15 min | Investigar causa raiz |
| 30 min | Escalar se fila > 500 |
| 1 hora | Considerar aprovação em lote |

## Prevenção

### Alertas Adicionais

```yaml
- alert: ApprovalServiceProcessingRateLow
  expr: rate(approval_decisions_total[5m]) < 0.1
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Taxa de processamento muito baixa"

- alert: ApprovalServiceKafkaLagHigh
  expr: kafka_consumergroup_lag{topic="approval-requests"} > 1000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Kafka lag muito alto"
```

### Configuração de Auto-scaling

```yaml
# HPA baseado em métricas customizadas
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: approval-service-hpa-queue
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: approval-service
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Pods
    pods:
      metric:
        name: approval_queue_size_per_pod
      target:
        type: AverageValue
        averageValue: "25"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Pods
        value: 2
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 120
```

## Referências

- **Dashboard:** [Approval Monitoring Dashboard](http://grafana.observability.svc.cluster.local:3000/d/approval-monitoring)
- **Documentação:** `docs/services/approval-service.md`
- **Kafka:** `kafka-local.yaml`

---

**Última atualização:** 2026-04-13
**Versão:** 1.0
