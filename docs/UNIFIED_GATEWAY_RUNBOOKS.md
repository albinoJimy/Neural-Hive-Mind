# Unified Gateway - Runbooks Operacionais

**Versão:** 1.0.0
**Última atualização:** 2026-05-05

---

## Índice

1. [Alertas e Métricas](#alertas-e-métricas)
2. [Diagnóstico](#diagnóstico)
3. [Resolução de Problemas](#resolução-de-problemas)
4. [Escalation](#escalation)

---

## Alertas e Métricas

### Prometheus Metrics Principais

| Métrica | Tipo | Descrição | Alerta |
|---------|------|-----------|--------|
| `http_requests_total` | Counter | Total de requests HTTP | p90 > 1000/s |
| `http_request_duration_seconds` | Histogram | Latência de requests | p95 > 5s |
| `rate_limit_exceeded_total` | Counter | Requests bloqueados por rate limit | > 10/min |
| `circuit_breaker_state` | Gauge | Estado do circuit breaker | 1 (open) |
| `nlu_grpc_errors_total` | Counter | Erros gRPC do NLU Service | > 5/min |
| `pii_grpc_errors_total` | Counter | Erros gRPC do PII Service | > 5/min |

### Health Check Dashboard

```bash
# Health check rápido
kubectl get pods -n gateway -l app=unified-gateway
kubectl get pods -n nlu -l app=nlu-service
kubectl get pods -n pii -l app=pii-service

# Métricas agregadas
curl http://unified-gateway:7999/metrics | grep -E "(http_requests|circuit_breaker)"
```

---

## Diagnóstico

### 1. Serviço Respondendo Lentamente

**Sintomas:**
- Latência p95 > 5s
- Timeouts em clientes
- Pods healthy mas slow

**Diagnóstico:**
```bash
# Verificar latência por endpoint
kubectl exec -n gateway deployment/unified-gateway -- \
  curl -s localhost:7999/metrics | \
  grep 'http_request_duration_seconds_bucket' | \
  grep 'le="5"'

# Verificar se NLU/PII services são o gargalo
kubectl logs -n gateway deployment/unified-gateway --tail=500 | \
  grep -E "(nlu_service|pii_service)" | grep "duration"

# Verificar uso de recursos
kubectl top pods -n gateway -l app=unified-gateway
kubectl top pods -n nlu -l app=nlu-service
kubectl top pods -n pii -l app=pii-service
```

**Possíveis causas:**
1. NLU/PII services sobrecarregados → Escalar via HPA
2. Redis lento → Verificar latency Redis
3. Problema de rede → Verificar latency entre pods

### 2. Circuit Breaker Aberto

**Sintomas:**
- HTTP 503 com header `X-Circuit-State: open`
- Requests falhando com "service unavailable"

**Diagnóstico:**
```bash
# Verificar estado atual
kubectl exec -n gateway deployment/unified-gateway -- \
  curl -s localhost:7999/metrics | grep circuit_breaker_state

# Logs do Unified Gateway
kubectl logs -n gateway deployment/unified-gateway --tail=200 | \
  grep -E "(circuit|breaker|nlu|pii)" | tail -50

# Verificar saúde dos serviços downstream
kubectl exec -n nlu deployment/nlu-service -- \
  curl -s localhost:8021/health
kubectl exec -n pii deployment/pii-service -- \
  curl -s localhost:9021/health
```

### 3. Rate Limiting Excedido

**Sintomas:**
- HTTP 429 com header `Retry-After`
- Clientes legítimos bloqueados

**Diagnóstico:**
```bash
# Verificar contadores Redis
kubectl exec -n gateway deployment/unified-gateway -- \
  redis-cli -h redis.redis-cluster.svc.cluster.local \
  KEYS "rate_limit:*"

# Verificar taxa de requests por tenant
kubectl exec -n gateway deployment/unified-gateway -- \
  curl -s localhost:7999/metrics | \
  grep -E "rate_limit_exceeded|http_requests_total" | \
  grep tenant
```

### 4. Erros de Autenticação

**Sintomas:**
- HTTP 401 inesperados
- Erros "JWT validation failed"

**Diagnóstico:**
```bash
# Verificar logs de autenticação
kubectl logs -n gateway deployment/unified-gateway --tail=500 | \
  grep -E "(auth|jwt|token)" | grep -i error

# Verificar configuração Keycloak
kubectl get cm unified-gateway-config -n gateway -o yaml | \
  grep -A5 KEYCLOAK
```

---

## Resolução de Problemas

### Circuit Breaker Aberto

**Opção 1: Aguardar recuperação automática**
```bash
# O circuit breaker fecha automaticamente após recovery_timeout (60s)
# Monitorar transição para half-open
watch -n 5 'kubectl exec -n gateway deployment/unified-gateway -- \
  curl -s localhost:7999/metrics | grep circuit_breaker_state'
```

**Opção 2: Reiniciar pods downstream**
```bash
# Se NLU/PII estão com problemas
kubectl rollout restart deployment/nlu-service -n nlu
kubectl rollout restart deployment/pii-service -n pii

# Aguardar readiness
kubectl wait --for=condition=ready pod -l app=nlu-service -n nlu --timeout=120s
```

**Opção 3: Ajustar thresholds (emergência)**
```bash
# Aumentar failure_threshold temporariamente
kubectl patch cm unified-gateway-config -n gateway --type=json \
  -p='[{"op": "replace", "path": "/data/CIRCUIT_BREAKER_THRESHOLD", "value": "10"}]'

# Reiniciar unified-gateway para aplicar
kubectl rollout restart deployment/unified-gateway -n gateway
```

### Rate Limiting Agressivo

**Opção 1: Aumentar limite global**
```bash
kubectl patch cm unified-gateway-config -n gateway --type=json \
  -p='[{"op": "replace", "path": "/data/RATE_LIMIT_REQUESTS_PER_MINUTE", "value": "200"}]'

# Reiniciar para aplicar
kubectl rollout restart deployment/unified-gateway -n gateway
```

**Opção 2: Whitelist de tenant**
```bash
# Adicionar tenant à whitelist (se implementado)
kubectl patch cm unified-gateway-config -n gateway --type=json \
  -p='[{"op": "add", "path": "/data/RATE_LIMIT_WHITELIST", "value": "tenant-123,tenant-456"}]'
```

### Pods CrashLoopBackOff

**Diagnóstico:**
```bash
# Verificar logs do pod
kubectl logs -n gateway deployment/unified-gateway --tail=200 --previous

# Descrever pod para ver events
kubectl describe pod -n gateway -l app=unified-gateway
```

**Causas comuns:**

1. **ConfigMap/Secret ausente**
   ```bash
   kubectl get cm,secret -n gateway | grep unified-gateway
   ```

2. **Dependency service unavailable**
   ```bash
   # Verificar se Redis/Kafka/MongoDB estão acessíveis
   kubectl exec -n gateway deployment/unified-gateway -- \
     nc -zv redis.redis-cluster.svc.cluster.local 6379
   ```

3. **Resource limits**
   ```bash
   kubectl describe pod -n gateway -l app=unified-gateway | grep -A5 Limits
   ```

### Alta Latência

**Opção 1: Escalar horizontalmente**
```bash
# Verificar HPA
kubectl get hpa -n gateway

# Escalar manualmente se HPA não estiver respondendo
kubectl scale deployment/unified-gateway -n gateway --replicas=10
```

**Opção 2: Escalar NLU/PII services**
```bash
kubectl scale deployment/nlu-service -n nlu --replicas=4
kubectl scale deployment/pii-service -n pii --replicas=4
```

**Opção 3: Ajustar resource requests/limits**
```bash
kubectl set resources deployment/unified-gateway \
  -n gateway \
  --requests=cpu=1000m,memory=2Gi \
  --limits=cpu=2000m,memory=4Gi
```

---

## Escalation

### Níveis de Escalation

| Nível | SLA | Responsável |
|-------|-----|-------------|
| P1 - Crítico | 15min | On-call Engineer |
| P2 - Alto | 1h | Team Lead |
| P3 - Médio | 4h | Engineering Manager |
| P4 - Baixo | 1d | Product Owner |

### Critérios de P1

- Serviço 100% down (nenhum request sendo processado)
- Perda de dados
- Breach de segurança confirmado

### Critérios de P2

- Degradation severa (>50% error rate)
- Performance impactada (p95 > 30s)
- Funcionalidade crítica não disponível

### Comandos de Escalation

```bash
# P1 - Page on-call
/slack @on-call "P1: Unified Gateway 100% down"

# Criar incident
gh issue create --repo albinoJimy/Neural-Hive-Mind \
  --title "INCIDENT: Unified Gateway down" \
  --body "P1 - Services affected..." \
  --label "incident,p1"

# Atualar status page
# (ferramenta de status page específica)
```

---

## Maintenance

### Rolling Update

```bash
# Atualizar imagem
kubectl set image deployment/unified-gateway \
  unified-gateway=ghcr.io/.../unified-gateway:v1.0.1 \
  -n gateway

# Monitorar rollout
kubectl rollout status deployment/unified-gateway -n gateway

# Verificar novos pods
kubectl get pods -n gateway -l app=unified-gateway --watch
```

### Rollback

```bash
# Rollback para versão anterior
kubectl rollout undo deployment/unified-gateway -n gateway

# Rollback para revisão específica
kubectl rollout undo deployment/unified-gateway \
  --to-revision=3 -n gateway
```

### Config Change

```bash
# Editar ConfigMap
kubectl edit cm unified-gateway-config -n gateway

# Rollout restart para aplicar
kubectl rollout restart deployment/unified-gateway -n gateway
```

---

## Debugging Avançado

### kubectl port-forward

```bash
# Forward local para debugging
kubectl port-forward -n gateway deployment/unified-gateway 7999:7999

# Testar localmente
curl -v http://localhost:7999/health
```

### Executar no pod

```bash
# Shell interativo
kubectl exec -it -n gateway deployment/unified-gateway -- /bin/bash

# Testar conectividade
kubectl exec -n gateway deployment/unified-gateway -- \
  curl -v http://nlu-service.nlu.svc.cluster.local:8020/health

# Verificar ambiente
kubectl exec -n gateway deployment/unified-gateway -- env | sort
```

### Tcpdump

```bash
# Capturar tráfego (requer privilege)
kubectl exec -n gateway deployment/unified-gateway -- \
  tcpdump -i any -w /tmp/capture.pcap port 7999

# Copiar para local
kubectl cp gateway/pod-name:/tmp/capture.pcap capture.pcap
```
