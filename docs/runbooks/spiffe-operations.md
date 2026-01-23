# SPIFFE/SPIRE Operations Runbook

## Overview

Este runbook cobre operacoes comuns de SPIFFE/SPIRE no Neural Hive-Mind.

## Daily Operations

### Verificar Saude do SPIRE Server

```bash
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server healthcheck
```

**Saida esperada:**
```
Server is healthy.
```

### Verificar Saude do SPIRE Agent

```bash
kubectl exec -n spire-system daemonset/spire-agent -- \
  /opt/spire/bin/spire-agent healthcheck -socketPath /run/spire/sockets/agent.sock
```

**Saida esperada:**
```
Agent is healthy.
```

### Listar Entries SPIFFE

```bash
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry show
```

### Verificar Metricas de Autenticacao

```bash
# Service Registry
kubectl port-forward -n neural-hive-execution svc/service-registry 9090:9090
curl http://localhost:9090/metrics | grep -E "(grpc_auth_attempts|grpc_auth_failures)"

# Orchestrator Dynamic
kubectl port-forward -n neural-hive-orchestration svc/orchestrator-dynamic 9090:9090
curl http://localhost:9090/metrics | grep -E "(grpc_jwt_auth_attempts|grpc_jwt_auth_failures)"
```

## Incident Response

### Incident: High Authentication Failure Rate

**Symptoms:**
- Metrica `grpc_auth_failures_total` aumentando
- Logs com `UNAUTHENTICATED` errors
- Fluxo C falhando em C3 (discovery)

**Diagnosis:**

```bash
# 1. Verificar logs do Service Registry
kubectl logs -n neural-hive-execution deployment/service-registry --tail=100 | grep -i auth

# 2. Verificar se SPIRE Agent esta rodando
kubectl get pods -n spire-system -l app=spire-agent

# 3. Verificar entries SPIFFE
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry show | grep worker-agents
```

**Resolution:**

1. Se SPIRE Agent down:
   ```bash
   kubectl rollout restart daemonset/spire-agent -n spire-system
   ```

2. Se entry SPIFFE ausente:
   ```bash
   # Recriar entry
   kubectl exec -n spire-system deployment/spire-server -- \
     /opt/spire/bin/spire-server entry create \
     -spiffeID spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents \
     -parentID spiffe://neural-hive.local/ns/spire-system/sa/spire-agent \
     -selector k8s:ns:neural-hive-execution \
     -selector k8s:sa:worker-agents \
     -ttl 3600
   ```

3. Se JWT expirado:
   - Verificar TTL configurado (deve ser >= 3600s)
   - Reiniciar pods para obter novos JWTs

### Incident: X.509-SVID Expiration

**Symptoms:**
- Logs com `SSL handshake failed`
- Metrica `spiffe_x509_svid_expiration_seconds` < 3600

**Resolution:**

```bash
# 1. Verificar expiracao
kubectl exec -n neural-hive-execution <pod-name> -- \
  curl -s --unix-socket /run/spire/sockets/agent.sock \
  http://localhost/v1/spiffe/workload/x509svid | jq '.svids[0].expires_at'

# 2. Forcar renovacao (restart pod)
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
kubectl rollout restart deployment/worker-agents -n neural-hive-execution
```

### Incident: Socket Permission Denied

**Symptoms:**
- Logs com `permission denied` ao acessar socket
- Pods nao conseguem obter SVIDs

**Resolution:**

```bash
# 1. Verificar permissoes do socket
kubectl exec -n spire-system daemonset/spire-agent -- ls -la /run/spire/sockets/

# 2. Verificar se volume esta montado
kubectl exec -n neural-hive-execution <pod-name> -- ls -la /run/spire/sockets/

# 3. Verificar securityContext do pod
kubectl get pod -n neural-hive-execution <pod-name> -o yaml | grep -A10 securityContext
```

## Maintenance

### Rotacionar SPIRE Server Root CA

**Frequency:** Anualmente

**Procedure:**

1. Backup atual:
   ```bash
   kubectl exec -n spire-system deployment/spire-server -- \
     /opt/spire/bin/spire-server bundle show > spire-bundle-backup.pem
   ```

2. Gerar novo CA (seguir documentacao oficial SPIRE)

3. Validar apos rotacao:
   ```bash
   kubectl exec -n spire-system deployment/spire-server -- \
     /opt/spire/bin/spire-server bundle show
   ```

### Atualizar SPIRE Version

**Procedure:**

1. Verificar versao atual:
   ```bash
   kubectl get deployment -n spire-system spire-server -o jsonpath='{.spec.template.spec.containers[0].image}'
   ```

2. Atualizar Helm chart:
   ```bash
   helm upgrade spire ./helm-charts/spire \
     --set server.image.tag=<new-version> \
     --set agent.image.tag=<new-version> \
     --namespace spire-system
   ```

3. Validar:
   ```bash
   kubectl rollout status deployment/spire-server -n spire-system
   kubectl rollout status daemonset/spire-agent -n spire-system
   ```

### Criar Nova Entry SPIFFE

Para adicionar um novo servico ao trust domain:

```bash
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/<namespace>/sa/<service-account> \
  -parentID spiffe://neural-hive.local/ns/spire-system/sa/spire-agent \
  -selector k8s:ns:<namespace> \
  -selector k8s:sa:<service-account> \
  -ttl 3600
```

### Remover Entry SPIFFE

```bash
# Listar entries para encontrar o ID
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry show

# Remover entry por ID
kubectl exec -n spire-system deployment/spire-server -- \
  /opt/spire/bin/spire-server entry delete -entryID <entry-id>
```

## Monitoring

### Metricas Chave

| Metrica | Descricao | Threshold de Alerta |
|---------|-----------|---------------------|
| `grpc_auth_attempts_total{status="success"}` | Autenticacoes bem-sucedidas | N/A |
| `grpc_auth_failures_total` | Falhas de autenticacao | > 5% do total |
| `spiffe_x509_svid_expiration_seconds` | Tempo ate expiracao do SVID | < 3600s |
| `spire_agent_attestation_errors_total` | Erros de attestation | > 0 |

### Alertas Recomendados

```yaml
# Prometheus AlertManager rules
groups:
  - name: spiffe-alerts
    rules:
      - alert: SPIFFEAuthFailureRateHigh
        expr: |
          sum(rate(grpc_auth_failures_total[5m]))
          / sum(rate(grpc_auth_attempts_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Taxa de falha de autenticacao SPIFFE alta"
          description: "Mais de 5% das autenticacoes estao falhando"

      - alert: SPIFFESVIDExpirationSoon
        expr: spiffe_x509_svid_expiration_seconds < 3600
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "X.509-SVID expirando em menos de 1 hora"
          description: "SVID expira em {{ $value }}s"

      - alert: SPIREAgentDown
        expr: up{job="spire-agent"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "SPIRE Agent nao disponivel"
          description: "SPIRE Agent em {{ $labels.node }} esta down"
```

## Escalation

- **L1:** Verificar logs e metricas
- **L2:** Reiniciar pods/agents
- **L3:** Recriar entries SPIFFE
- **L4:** Contatar time de seguranca para rotacao de CA
