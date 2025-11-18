## Runbook de Operações - Vault/SPIFFE

**Objetivo**: Guia operacional para manutenção, troubleshooting e recuperação da integração Vault/SPIFFE no Neural Hive-Mind.

---

### Health Checks

#### Vault

**Verificação Básica**:
```bash
# Status de todos os pods
kubectl get pods -n vault

# Status do Vault
kubectl exec -n vault vault-0 -- vault status

# Verificar HA cluster
kubectl exec -n vault vault-0 -- vault operator raft list-peers
```

**Outputs esperados**:
```
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             false
HA Enabled         true
HA Mode            active
HA Cluster         https://vault-0.vault-internal:8201
```

**Verificar Leader**:
```bash
# Identificar leader
kubectl exec -n vault vault-0 -- vault operator raft list-peers | grep leader

# Logs do leader
kubectl logs -n vault vault-0 --tail=50 | grep -E "(leader|standby)"
```

#### SPIRE

**SPIRE Server**:
```bash
# Pods
kubectl get pods -n spire-system -l app=spire-server

# Health check
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server healthcheck

# Verificar entradas registradas
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry show | grep -E "(Entry ID|SPIFFE ID)" | head -20
```

**SPIRE Agents (DaemonSet)**:
```bash
# Status de todos os agents
kubectl get pods -n spire-system -l app=spire-agent

# Logs de um agent
kubectl logs -n spire-system <spire-agent-pod> --tail=50

# Verificar socket montado
kubectl exec -n spire-system <spire-agent-pod> -- ls -la /run/spire/sockets/
```

#### Integração Orchestrator/Worker

**Verificar montagem do socket SPIRE**:
```bash
# Orchestrator
kubectl exec -n neural-hive-orchestration <orchestrator-pod> -- \
  ls -la /run/spire/sockets/agent.sock

# Worker
kubectl exec -n neural-hive-execution <worker-pod> -- \
  ls -la /run/spire/sockets/agent.sock
```

**Testar fetch de JWT-SVID**:
```bash
kubectl exec -n neural-hive-orchestration <orchestrator-pod> -- \
  curl --unix-socket /run/spire/sockets/agent.sock \
  http://localhost/v1/spiffe/workload/jwt \
  -H "Content-Type: application/json" \
  -d '{"audience": ["vault.neural-hive.local"]}' | jq .
```

---

### Problemas Comuns

#### 1. Vault Sealed

**Sintomas**:
```bash
kubectl exec -n vault vault-0 -- vault status
# Output: Sealed = true
```

**Causa**: Vault foi reiniciado e não foi unsealed (chaves não estão em memória).

**Solução**:
```bash
# Recuperar unseal keys do AWS Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id neural-hive-vault-init-keys \
  --query SecretString --output text > vault-keys.json

# Unseal cada pod (vault-0, vault-1, vault-2)
for i in 0 1 2; do
  echo "Unsealing vault-$i..."
  kubectl exec -n vault vault-$i -- vault operator unseal $(cat vault-keys.json | jq -r '.unseal_keys_b64[0]')
  kubectl exec -n vault vault-$i -- vault operator unseal $(cat vault-keys.json | jq -r '.unseal_keys_b64[1]')
  kubectl exec -n vault vault-$i -- vault operator unseal $(cat vault-keys.json | jq -r '.unseal_keys_b64[2]')
done

# Verificar
kubectl exec -n vault vault-0 -- vault status
```

**Prevenção**: Configurar auto-unseal com AWS KMS (requer atualização de Helm values).

#### 2. Token Vault Expirado

**Sintomas**:
```
vault_token_renewal_failed error="token is expired" service=orchestrator-dynamic
```

**Causa**: Token Kubernetes auth expirou (TTL default 1h).

**Verificação**:
```bash
# Verificar logs do orchestrator
kubectl logs -n neural-hive-orchestration <pod> | grep token_renewal

# Verificar TTL do token no Vault
kubectl exec -n vault vault-0 -- vault token lookup <TOKEN>
```

**Solução**:
O `VaultClient` renova automaticamente a 80% do TTL. Se falhar:

```bash
# Restart do pod para reautenticar
kubectl rollout restart deployment orchestrator-dynamic -n neural-hive-orchestration

# Verificar nova autenticação nos logs
kubectl logs -n neural-hive-orchestration <new-pod> | grep vault_client_initialized
```

**Troubleshooting adicional**:
```bash
# Verificar role Kubernetes no Vault
kubectl exec -n vault vault-0 -- vault read auth/kubernetes/role/orchestrator-dynamic

# Verificar service account token
kubectl get secret -n neural-hive-orchestration | grep orchestrator-dynamic-token
```

#### 3. JWT-SVID Fetch Fail

**Sintomas**:
```
jwt_svid_fetch_failed error="connection refused" audience=vault.neural-hive.local
```

**Causa**: SPIRE Agent inacessível ou SPIFFE ID não registrado.

**Diagnóstico**:
```bash
# 1. Verificar SPIRE Agent rodando no mesmo node
kubectl get pods -n spire-system -l app=spire-agent -o wide
kubectl get pods -n neural-hive-orchestration <orchestrator-pod> -o wide

# 2. Verificar socket montado
kubectl exec -n neural-hive-orchestration <pod> -- ls -la /run/spire/sockets/

# 3. Verificar SPIFFE ID registrado
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry show | grep orchestrator-dynamic
```

**Solução**:

Se SPIFFE ID não existe:
```bash
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic \
  -parentID spiffe://neural-hive.local/spire/agent/k8s_psat/production \
  -selector k8s:ns:neural-hive-orchestration \
  -selector k8s:sa:orchestrator-dynamic \
  -ttl 3600
```

Se socket não está montado, verificar volumeMount no Deployment:
```yaml
volumes:
  - name: spire-agent-socket
    hostPath:
      path: /run/spire/sockets
      type: DirectoryOrCreate
volumeMounts:
  - name: spire-agent-socket
    mountPath: /run/spire/sockets
    readOnly: true
```

#### 4. mTLS Handshake Fail

**Sintomas**:
```
grpc_error code=Unavailable details="SSL handshake failed"
```

**Causa**: Certificado X.509-SVID inválido ou CA mismatch.

**Diagnóstico**:
```bash
# Verificar X.509-SVID do orchestrator
kubectl exec -n neural-hive-orchestration <pod> -- \
  curl --unix-socket /run/spire/sockets/agent.sock \
  http://localhost/v1/spiffe/workload/x509 | jq .

# Verificar logs de TLS no service-registry
kubectl logs -n neural-hive-execution <service-registry-pod> | grep -i "tls\|ssl"
```

**Solução**:

Forçar renovação do certificado (restart do pod):
```bash
kubectl rollout restart deployment service-registry -n neural-hive-execution
kubectl rollout restart deployment orchestrator-dynamic -n neural-hive-orchestration
```

Verificar trust bundle:
```bash
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server bundle show
```

#### 5. Service Registry UNAUTHENTICATED/PERMISSION_DENIED

**Sintomas**:
```
grpc_auth_failure code=UNAUTHENTICATED method=DiscoverAgents reason=invalid_token
grpc_auth_failure code=PERMISSION_DENIED method=DiscoverAgents reason=unauthorized_spiffe_id
```

**Causa**: SPIFFE ID não está na lista de IDs autorizados no interceptor.

**Diagnóstico**:
```bash
# Verificar SPIFFE ID do orchestrator
kubectl logs -n neural-hive-orchestration <pod> | grep spiffe_id

# Verificar allowed IDs no service-registry
kubectl exec -n neural-hive-execution <service-registry-pod> -- \
  cat /app/src/grpc_server/auth_interceptor.py | grep -A 10 "allowed_spiffe_ids"
```

**Solução**:

Atualizar `auth_interceptor.py` para incluir SPIFFE ID:
```python
self.allowed_spiffe_ids = {
    "DiscoverAgents": [
        f"spiffe://{settings.SPIFFE_TRUST_DOMAIN}/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
        # Adicionar outros IDs autorizados
    ],
}
```

Redeploy:
```bash
kubectl rollout restart deployment service-registry -n neural-hive-execution
```

---

### Rotação de Credenciais

#### Token Vault (Automático)

O `VaultClient` renova automaticamente tokens a 80% do TTL:

**Verificar renovação**:
```bash
# Logs de renovação
kubectl logs -n neural-hive-orchestration <pod> | grep token_renewed

# TTL atual
kubectl exec -n vault vault-0 -- vault token lookup <TOKEN> | grep ttl
```

**Forçar renovação manual** (se necessário):
```bash
kubectl exec -n neural-hive-orchestration <pod> -- sh -c '
  vault token renew
'
```

#### Credenciais de Banco de Dados (Vault Dynamic Secrets)

**Verificação**:
```bash
# Listar leases ativos
kubectl exec -n vault vault-0 -- vault list sys/leases/lookup/database/creds/orchestrator-dynamic

# TTL de uma credencial
kubectl exec -n vault vault-0 -- vault lease lookup <LEASE_ID>
```

**Renovação automática**: O `VaultClient` renova a 80% do TTL (default 1h).

**Rotação manual** (forçar nova credencial):
```bash
# Revogar lease atual
kubectl exec -n vault vault-0 -- vault lease revoke <LEASE_ID>

# Restart do pod para obter nova credencial
kubectl rollout restart deployment orchestrator-dynamic -n neural-hive-orchestration
```

#### SVID Refresh (Automático)

O `SPIFFEManager` renova SVIDs automaticamente:
- **JWT-SVID**: Renovação a 80% do TTL (default 1h)
- **X.509-SVID**: Renovação a 80% do TTL (default 24h)

**Verificar refresh**:
```bash
# Logs de renovação
kubectl logs -n neural-hive-orchestration <pod> | grep -E "(refreshing_jwt_svid|refreshing_x509_svid)"

# Expiry atual
kubectl exec -n neural-hive-orchestration <pod> -- sh -c '
  curl --unix-socket /run/spire/sockets/agent.sock \
    http://localhost/v1/spiffe/workload/jwt \
    -d "{\"audience\": [\"vault.neural-hive.local\"]}" | jq ".svids[0].expiry"
'
```

---

### Monitoramento e Alertas

#### Métricas Prometheus

**Vault**:
```promql
# Request errors
rate(vault_requests_total{status="error"}[5m]) > 0.05

# Seal status (0=unsealed, 1=sealed)
vault_core_unsealed == 0
```

**SPIFFE**:
```promql
# SVID fetch errors
rate(spiffe_svid_fetch_total{status="error"}[5m]) > 0.10

# SVID fetch duration
histogram_quantile(0.95, spiffe_svid_fetch_duration_seconds_bucket) > 2.0
```

**gRPC Auth**:
```promql
# Auth failures
rate(grpc_auth_failures_total[5m]) > 0.10

# UNAUTHENTICATED errors
grpc_auth_attempts_total{status="missing_token"} > 10
```

#### Alertas Recomendados

```yaml
# prometheus-alerts.yaml
groups:
  - name: vault-spiffe
    interval: 30s
    rules:
      - alert: VaultSealed
        expr: vault_core_unsealed == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Vault está sealed no namespace {{ $labels.namespace }}"
          description: "Executar unseal imediatamente"

      - alert: SPIFFESVIDFetchErrors
        expr: rate(spiffe_svid_fetch_total{status="error"}[5m]) > 0.10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Alta taxa de erros em fetch de SVID"
          description: "Verificar SPIRE Agent em {{ $labels.pod }}"

      - alert: GRPCAuthFailures
        expr: rate(grpc_auth_failures_total[5m]) > 0.10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Alta taxa de falhas de autenticação gRPC"
          description: "Verificar SPIFFE IDs autorizados e tokens JWT"
```

---

### Backup e Recovery

#### Vault Raft Snapshots

**Criar snapshot manual**:
```bash
# Exec no leader
kubectl exec -n vault vault-0 -- vault operator raft snapshot save /tmp/vault-snapshot.snap

# Copiar para S3
kubectl cp vault/vault-0:/tmp/vault-snapshot.snap ./vault-snapshot-$(date +%Y%m%d).snap
aws s3 cp ./vault-snapshot-$(date +%Y%m%d).snap s3://neural-hive-vault-backups/
```

**Snapshot automático (CronJob)**:
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: vault-snapshot
  namespace: vault
spec:
  schedule: "0 2 * * *"  # Diário às 2h
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: vault-snapshot
          containers:
            - name: snapshot
              image: hashicorp/vault:1.15.0
              command:
                - sh
                - -c
                - |
                  vault operator raft snapshot save /tmp/snapshot.snap
                  aws s3 cp /tmp/snapshot.snap s3://neural-hive-vault-backups/vault-$(date +%Y%m%d-%H%M%S).snap
              env:
                - name: VAULT_ADDR
                  value: "http://vault:8200"
```

**Restore de snapshot**:
```bash
# Download do S3
aws s3 cp s3://neural-hive-vault-backups/vault-20251117.snap ./

# Copiar para pod
kubectl cp ./vault-20251117.snap vault/vault-0:/tmp/restore.snap

# Restore (PERDA DE DADOS - confirmar antes)
kubectl exec -n vault vault-0 -- vault operator raft snapshot restore /tmp/restore.snap
```

#### SPIRE PostgreSQL Backup

**Backup automático via RDS**:
- Configurado no Terraform (`backup_retention_period = 7`)
- Snapshots diários automáticos
- Recovery Point: últimas 24h

**Restore manual**:
```bash
# Listar snapshots
aws rds describe-db-snapshots \
  --db-instance-identifier neural-hive-spire-db

# Restore para nova instância
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier neural-hive-spire-db-restored \
  --db-snapshot-identifier rds:neural-hive-spire-db-2025-11-17

# Atualizar connection string no Secret
kubectl edit secret spire-database-secret -n spire-system
```

#### SPIRE Entries Backup

**Exportar entradas**:
```bash
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry show -output json > spire-entries-$(date +%Y%m%d).json

# Upload para S3
aws s3 cp spire-entries-$(date +%Y%m%d).json s3://neural-hive-config-backups/
```

**Restaurar entradas**:
```bash
# Download
aws s3 cp s3://neural-hive-config-backups/spire-entries-20251117.json ./

# Script de restore (criar se necessário)
./scripts/spire-restore-entries.sh spire-entries-20251117.json
```

---

### Manutenção

#### Upgrade Vault

```bash
# Atualizar Helm chart
helm upgrade vault ./helm-charts/vault \
  --namespace vault \
  --set server.image.tag=1.16.0 \
  --reuse-values

# Rolling restart (HA mantém disponibilidade)
kubectl rollout status statefulset/vault -n vault

# Verificar após upgrade
kubectl exec -n vault vault-0 -- vault version
kubectl exec -n vault vault-0 -- vault status
```

#### Upgrade SPIRE

```bash
# Backup de entradas primeiro
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry show -output json > spire-entries-backup.json

# Upgrade
helm upgrade spire ./helm-charts/spire \
  --namespace spire-system \
  --set server.image.tag=1.9.0 \
  --reuse-values

# Verificar
kubectl rollout status statefulset/spire-server -n spire-system
kubectl exec -n spire-system spire-server-0 -- /opt/spire/bin/spire-server --version
```

#### Rotação de Certificados PKI

**Certificados emitidos automaticamente renovam a 80% do TTL.**

**Rotação do Root CA** (raro, ~10 anos):
```bash
# Gerar novo Root CA
kubectl exec -n vault vault-0 -- vault write pki/root/rotate/internal \
  common_name="Neural Hive-Mind Root CA v2"

# Atualizar trust bundle no SPIRE
# (requer reconfiguração do upstream authority)
```

#### Atualização de Policies

```bash
# Editar policy
kubectl exec -n vault vault-0 -- vault policy write orchestrator-dynamic - <<EOF
path "secret/data/orchestrator-dynamic/*" {
  capabilities = ["read"]
}
path "database/creds/orchestrator-dynamic" {
  capabilities = ["read"]
}
# Nova permissão
path "kv/data/ml-models/*" {
  capabilities = ["read", "list"]
}
EOF

# Verificar
kubectl exec -n vault vault-0 -- vault policy read orchestrator-dynamic

# Teste com token
kubectl exec -n vault vault-0 -- vault token create -policy=orchestrator-dynamic
```

---

### Comandos de Debug

#### Vault

```bash
# Logs com nível debug
kubectl logs -n vault vault-0 --tail=100 | grep -E "(ERROR|WARN)"

# Audit log (se habilitado)
kubectl exec -n vault vault-0 -- vault audit enable file file_path=/vault/logs/audit.log
kubectl exec -n vault vault-0 -- tail -f /vault/logs/audit.log

# Listar tokens ativos
kubectl exec -n vault vault-0 -- vault list auth/token/accessors

# Lookup de token específico
kubectl exec -n vault vault-0 -- vault token lookup <TOKEN>
```

#### SPIRE

```bash
# Logs do servidor
kubectl logs -n spire-system spire-server-0 --tail=100

# Logs de agent específico
kubectl logs -n spire-system <spire-agent-pod> --tail=100

# Debug de fetch JWT via grpcurl (se disponível)
kubectl exec -n spire-system <spire-agent-pod> -- \
  grpcurl -unix /run/spire/sockets/agent.sock \
  spire.api.agent.workload.Workload/FetchJWTSVID

# Listar bundles
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server bundle show
```

#### Orchestrator/Worker

```bash
# Logs filtrados por SPIFFE/Vault
kubectl logs -n neural-hive-orchestration <pod> | grep -E "(vault|spiffe|jwt|x509)"

# Exec interativo para debug
kubectl exec -it -n neural-hive-orchestration <pod> -- sh

# Dentro do pod:
# - Verificar env vars: env | grep -E "(VAULT|SPIFFE)"
# - Testar socket: ls -la /run/spire/sockets/
# - Curl Workload API: curl --unix-socket /run/spire/sockets/agent.sock http://localhost/v1/spiffe/workload/jwt ...
```

---

### Disaster Recovery

#### Cenário 1: Perda Total do Vault Cluster

1. **Restaurar infraestrutura via Terraform**:
```bash
cd infrastructure/terraform
terraform apply -target=module.vault-ha
```

2. **Redeploy Vault**:
```bash
helm install vault ./helm-charts/vault --namespace vault
```

3. **Restore snapshot**:
```bash
aws s3 cp s3://neural-hive-vault-backups/vault-latest.snap ./
kubectl cp ./vault-latest.snap vault/vault-0:/tmp/restore.snap
kubectl exec -n vault vault-0 -- vault operator raft snapshot restore /tmp/restore.snap
```

4. **Unseal e verificar**:
```bash
./scripts/vault-unseal.sh
kubectl exec -n vault vault-0 -- vault status
```

#### Cenário 2: Perda do SPIRE RDS

1. **Restore RDS de snapshot**:
```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier neural-hive-spire-db \
  --db-snapshot-identifier rds:neural-hive-spire-db-latest
```

2. **Atualizar connection string**:
```bash
NEW_ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier neural-hive-spire-db --query 'DBInstances[0].Endpoint.Address' --output text)

kubectl create secret generic spire-database-secret \
  --from-literal=connection-string="postgresql://spire_server:PASSWORD@$NEW_ENDPOINT:5432/spire?sslmode=require" \
  -n spire-system --dry-run=client -o yaml | kubectl apply -f -
```

3. **Restart SPIRE**:
```bash
kubectl rollout restart statefulset/spire-server -n spire-system
```

4. **Restaurar entradas** (se não estavam no RDS):
```bash
./scripts/spire-restore-entries.sh spire-entries-backup.json
```

---

### Contatos e Escalação

- **Vault Issues**: Time de Platform Engineering
- **SPIRE Issues**: Time de Security
- **Aplicação**: Time de Neural Hive-Mind

**SLO**: Tempo de resposta < 30min para incidentes críticos (Vault sealed, SPIRE down).
