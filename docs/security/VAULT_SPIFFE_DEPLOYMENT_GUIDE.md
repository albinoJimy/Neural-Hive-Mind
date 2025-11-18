## Guia de Deployment - Integração Vault/SPIFFE

**Objetivo**: Documentação completa para deployment da integração Vault/SPIFFE no Neural Hive-Mind em ambiente EKS.

### Pré-requisitos

Antes de iniciar o deployment, certifique-se de que:

- **Cluster EKS** está provisionado e acessível via `kubectl`
- **Ferramentas instaladas**:
  - AWS CLI (`aws --version`)
  - Terraform >= 1.5 (`terraform version`)
  - Helm >= 3.12 (`helm version`)
  - kubectl (`kubectl version`)
  - Vault CLI (`vault version`)
- **Permissões IAM**:
  - IRSA (IAM Roles for Service Accounts) configurado para Vault
  - IRSA configurado para SPIRE Server (acesso ao RDS PostgreSQL)
  - Permissões para criar Secrets Manager secrets
- **Namespaces Kubernetes**:
  ```bash
  kubectl create namespace vault
  kubectl create namespace spire-system
  kubectl create namespace neural-hive-orchestration
  ```

---

### Passo 1: Provisionar Infraestrutura com Terraform

#### 1.1. Módulo `vault-ha`

Este módulo provisiona recursos AWS para Vault em HA:

```bash
cd /jimy/Neural-Hive-Mind/infrastructure/terraform

# Inicializar Terraform
terraform init

# Revisar plano
terraform plan -target=module.vault-ha

# Aplicar
terraform apply -target=module.vault-ha
```

**Outputs importantes**:
- `vault_kms_key_id`: KMS key para auto-unseal
- `vault_service_account_role_arn`: IRSA role para Vault pods
- `vault_s3_bucket`: Bucket para snapshots Raft

Salve esses outputs:
```bash
terraform output -json vault-ha > vault-outputs.json
```

#### 1.2. Módulo `spire-datastore`

Este módulo provisiona RDS PostgreSQL para SPIRE Server e armazena credenciais no AWS Secrets Manager:

```bash
# Aplicar módulo spire-datastore
terraform apply -target=module.spire-datastore

# Capturar outputs
terraform output -json spire-datastore > spire-outputs.json
```

**Outputs importantes**:
- `secret_arn`: ARN do AWS Secrets Manager secret com credenciais do DB
- `connection_string`: String de conexão PostgreSQL (sensível)
- `secret_name`: Nome do secret (ex: `neural-hive-spire-db-production`)

Exemplo de captura do connection string:
```bash
CONNECTION_STRING=$(terraform output -raw connection_string)
echo "Connection string capturado (não logar em produção)"
```

---

### Passo 2: Instalar Vault com Helm

**Nota:** Os templates Helm estão agora completos em `helm-charts/vault/templates/`. Incluem:
- StatefulSet HA com Raft
- Services (ClusterIP + headless)
- ConfigMap com HCL
- ServiceAccount com IRSA
- NetworkPolicy
- ServiceMonitor
- Vault Agent Injector (Deployment + Service + MutatingWebhook)

#### 2.1. Deploy Vault

```bash
cd /jimy/Neural-Hive-Mind

# Instalar Vault em modo HA
helm install vault ./helm-charts/vault \
  --namespace vault \
  --set server.ha.enabled=true \
  --set server.ha.replicas=3 \
  --set server.image.tag=1.15.0 \
  --set server.serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="$(cat vault-outputs.json | jq -r '.vault_service_account_role_arn.value')"

# Aguardar pods
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=vault -n vault --timeout=300s
```

#### 2.2. Inicializar e Unseal Vault

**Importante**: Este passo deve ser feito apenas uma vez na primeira instalação.

```bash
# Exec no pod vault-0
kubectl exec -n vault vault-0 -- vault operator init \
  -key-shares=5 \
  -key-threshold=3 \
  -format=json > vault-init.json

# IMPORTANTE: Salvar vault-init.json em local seguro (AWS Secrets Manager recomendado)
aws secretsmanager create-secret \
  --name neural-hive-vault-init-keys \
  --secret-string file://vault-init.json \
  --region us-east-1

# Unseal Vault (executar em vault-0, vault-1, vault-2)
for i in 0 1 2; do
  kubectl exec -n vault vault-$i -- vault operator unseal $(cat vault-init.json | jq -r '.unseal_keys_b64[0]')
  kubectl exec -n vault vault-$i -- vault operator unseal $(cat vault-init.json | jq -r '.unseal_keys_b64[1]')
  kubectl exec -n vault vault-$i -- vault operator unseal $(cat vault-init.json | jq -r '.unseal_keys_b64[2]')
done

# Verificar status
kubectl exec -n vault vault-0 -- vault status
```

#### 2.3. Executar Script de Configuração PKI

```bash
# Port-forward para acesso local
kubectl port-forward -n vault svc/vault 8200:8200 &

# Login com root token
export VAULT_ADDR='http://localhost:8200'
export VAULT_TOKEN=$(cat vault-init.json | jq -r '.root_token')
vault login $VAULT_TOKEN

# Executar script de inicialização PKI
./scripts/vault-init-pki.sh
```

**O script faz**:
1. Habilita PKI engine em `pki/`
2. Gera Root CA interna (10 anos)
3. Configura URLs de CA e CRL
4. Cria role `neural-hive-services` (TTL 168h/720h)
5. Cria policy `pki-issue` para emissão de certificados

#### 2.4. Configurar Políticas de Serviços

```bash
# Executar script de configuração de políticas
./scripts/vault-configure-policies.sh
```

**O script faz**:
1. Cria policies para cada serviço (orchestrator, worker-agents, etc.)
2. Habilita Kubernetes auth method
3. Cria roles vinculando ServiceAccounts a policies
4. Configura database secrets engine para credenciais dinâmicas

Exemplo de policy criada:
```hcl
# orchestrator-dynamic policy
path "secret/data/orchestrator-dynamic/*" {
  capabilities = ["read"]
}
path "database/creds/orchestrator-dynamic" {
  capabilities = ["read"]
}
path "pki/issue/neural-hive-services" {
  capabilities = ["create", "update"]
}
```

---

### Passo 3: Instalar SPIRE com Helm

**Nota:** Os templates Helm estão agora completos em `helm-charts/spire/templates/`. Incluem:
- Server StatefulSet
- Agent DaemonSet
- OIDC Discovery Provider Deployment
- ConfigMaps separados (server + agent + oidc)
- Services
- RBAC (ClusterRole + ClusterRoleBinding)
- Job de registration entries
- ServiceMonitors
- NetworkPolicy

#### 3.1. Criar Kubernetes Secret com Connection String

**Opção A: Manual (kubectl)**

```bash
# Criar Secret a partir do output do Terraform
kubectl create secret generic spire-database-secret \
  --from-literal=connection-string="$(terraform output -raw connection_string)" \
  -n spire-system

# Verificar
kubectl get secret spire-database-secret -n spire-system -o yaml
```

**Opção B: External Secrets Operator (Recomendado para Produção)**

1. Instalar External Secrets Operator:
```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace
```

2. Criar ClusterSecretStore:
```yaml
# cluster-secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secrets-manager
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets
            namespace: external-secrets
```

3. Criar ExternalSecret:
```yaml
# spire-db-external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: spire-db-secret
  namespace: spire-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: spire-database-secret
    creationPolicy: Owner
  data:
    - secretKey: connection-string
      remoteRef:
        key: $(terraform output -raw secret_name)
        property: connection_string
```

Aplicar:
```bash
kubectl apply -f cluster-secret-store.yaml
kubectl apply -f spire-db-external-secret.yaml

# Verificar sincronização
kubectl get externalsecret -n spire-system
kubectl get secret spire-database-secret -n spire-system
```

#### 3.2. Deploy SPIRE Server

```bash
cd /jimy/Neural-Hive-Mind

# Instalar SPIRE
helm install spire ./helm-charts/spire \
  --namespace spire-system \
  --set server.datastore.sql.connectionStringSecret.enabled=true \
  --set server.datastore.sql.connectionStringSecret.name=spire-database-secret \
  --set server.datastore.sql.connectionStringSecret.key=connection-string \
  --set global.trustDomain=neural-hive.local

# Aguardar pods
kubectl wait --for=condition=Ready pod -l app=spire-server -n spire-system --timeout=300s
kubectl wait --for=condition=Ready pod -l app=spire-agent -n spire-system --timeout=300s
```

#### 3.3. Criar Entradas SPIRE

Criar SPIFFE IDs para workloads:

```bash
# Orchestrator Dynamic
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic \
  -parentID spiffe://neural-hive.local/spire/agent/k8s_psat/production \
  -selector k8s:ns:neural-hive-orchestration \
  -selector k8s:sa:orchestrator-dynamic \
  -ttl 3600

# Worker Agents
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents \
  -parentID spiffe://neural-hive.local/spire/agent/k8s_psat/production \
  -selector k8s:ns:neural-hive-execution \
  -selector k8s:sa:worker-agents \
  -ttl 3600

# Service Registry
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/neural-hive-execution/sa/service-registry \
  -parentID spiffe://neural-hive.local/spire/agent/k8s_psat/production \
  -selector k8s:ns:neural-hive-execution \
  -selector k8s:sa:service-registry \
  -ttl 3600

# Verificar entradas
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry show
```

**Script automatizado** (opcional):
```bash
./scripts/spire-register-entries.sh
```

---

### Passo 4: Deploy Orchestrator com Vault/SPIFFE Habilitado

#### 4.1. Atualizar Helm Values

Editar `helm-charts/orchestrator-dynamic/values.yaml`:

```yaml
vault:
  enabled: true
  address: "http://vault.vault.svc.cluster.local:8200"
  authMethod: "kubernetes"
  kubernetesRole: "orchestrator-dynamic"
  failOpen: false  # Fail-closed em produção

spiffe:
  enabled: true
  socketPath: "unix:///run/spire/sockets/agent.sock"
  trustDomain: "neural-hive.local"
  jwtAudience: "vault.neural-hive.local"
  enableX509: true

serviceAccount:
  create: true
  name: orchestrator-dynamic
  annotations:
    # IRSA (se necessário para outros recursos AWS)
    eks.amazonaws.com/role-arn: "arn:aws:iam::ACCOUNT_ID:role/orchestrator-dynamic-role"
```

#### 4.2. Deploy Orchestrator

```bash
helm upgrade --install orchestrator-dynamic ./helm-charts/orchestrator-dynamic \
  --namespace neural-hive-orchestration \
  --set vault.enabled=true \
  --set spiffe.enabled=true

# Verificar logs
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep -E "(vault|spiffe)"
```

**Logs esperados**:
```
vault_client_initialized vault_addr=http://vault.vault.svc.cluster.local:8200
spiffe_manager_initialized trust_domain=neural-hive.local
jwt_svid_fetched_from_spire audience=vault.neural-hive.local spiffe_id=spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic
```

---

### Passo 5: Validação

#### 5.1. Validar Vault

```bash
# Status
kubectl exec -n vault vault-0 -- vault status

# Verificar HA leader
kubectl exec -n vault vault-0 -- vault operator raft list-peers

# Verificar PKI
kubectl exec -n vault vault-0 -- vault read pki/cert/ca
```

#### 5.2. Validar SPIRE

```bash
# Status do servidor
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server healthcheck

# Status dos agentes (DaemonSet)
kubectl get pods -n spire-system -l app=spire-agent

# Verificar socket montado no orchestrator
kubectl exec -n neural-hive-orchestration <orchestrator-pod> -- \
  ls -la /run/spire/sockets/
```

#### 5.3. Validar Integração Orchestrator

```bash
# Verificar fetch de JWT-SVID via socket
kubectl exec -n neural-hive-orchestration <orchestrator-pod> -- \
  curl --unix-socket /run/spire/sockets/agent.sock \
  http://localhost/v1/spiffe/workload/jwt \
  -H "Content-Type: application/json" \
  -d '{"audience": ["vault.neural-hive.local"]}'

# Verificar logs do orchestrator
kubectl logs -n neural-hive-orchestration <orchestrator-pod> | grep jwt_svid_fetched
```

Resultado esperado (log):
```json
{
  "level": "info",
  "msg": "jwt_svid_fetched_from_spire",
  "audience": "vault.neural-hive.local",
  "spiffe_id": "spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic",
  "expiry": "2025-11-17T12:34:56Z"
}
```

#### 5.4. Validar Vault Login via JWT-SVID

```bash
# Simular login do orchestrator
kubectl exec -n neural-hive-orchestration <orchestrator-pod> -- sh -c '
  JWT_TOKEN=$(curl --unix-socket /run/spire/sockets/agent.sock \
    http://localhost/v1/spiffe/workload/jwt \
    -H "Content-Type: application/json" \
    -d "{\"audience\": [\"vault.neural-hive.local\"]}" | jq -r ".svids[0].svid")

  vault write auth/kubernetes/login \
    role=orchestrator-dynamic \
    jwt=$JWT_TOKEN
'
```

Sucesso esperado:
```
Key                  Value
---                  -----
token                hvs.CAESI...
token_accessor       1234abcd...
token_policies       ["default" "orchestrator-dynamic"]
```

---

### Passo 6: Configurar Observabilidade

#### 6.1. Importar Dashboard Grafana

```bash
# Dashboard está em monitoring/dashboards/vault-spiffe-dashboard.json
kubectl create configmap vault-spiffe-dashboard \
  --from-file=vault-spiffe-dashboard.json=monitoring/dashboards/vault-spiffe-dashboard.json \
  -n monitoring \
  --dry-run=client -o yaml | kubectl apply -f -

# Adicionar label para auto-import
kubectl label configmap vault-spiffe-dashboard \
  grafana_dashboard=1 \
  -n monitoring
```

#### 6.2. Aplicar Alertas Prometheus

```bash
kubectl apply -f monitoring/alerts/vault-spiffe-alerts.yaml

# Verificar alertas carregados
kubectl exec -n monitoring prometheus-0 -- \
  promtool check config /etc/prometheus/prometheus.yml
```

#### 6.3. Verificar Métricas

```bash
# Port-forward Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &

# Queries de teste:
# - up{job="vault"}
# - vault_core_unsealed
# - up{job="spire-server"}
# - spire_agent_workload_api_requests_total
```

---

### Secret Sync com External Secrets (Alternativa Avançada)

Para sincronização automática de secrets Terraform → K8s:

1. Terraform output para Secrets Manager:
```hcl
# Em spire-datastore/main.tf
resource "aws_secretsmanager_secret_version" "spire_connection_string" {
  secret_id     = aws_secretsmanager_secret.spire_db.id
  secret_string = jsonencode({
    connection_string = local.connection_string
    username          = aws_db_instance.spire.username
    endpoint          = aws_db_instance.spire.address
    port              = aws_db_instance.spire.port
  })
}
```

2. External Secret consumindo:
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: spire-db-auto-sync
  namespace: spire-system
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: spire-database-secret
  dataFrom:
    - extract:
        key: $(terraform output -raw secret_name)
```

---

### Troubleshooting Comum

#### Vault Sealed
```bash
# Verificar
kubectl exec -n vault vault-0 -- vault status

# Unseal
kubectl exec -n vault vault-0 -- vault operator unseal <UNSEAL_KEY_1>
kubectl exec -n vault vault-0 -- vault operator unseal <UNSEAL_KEY_2>
kubectl exec -n vault vault-0 -- vault operator unseal <UNSEAL_KEY_3>
```

#### SPIRE Entry Missing
```bash
# Listar entradas
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry show

# Recriar entrada
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server entry create \
  -spiffeID spiffe://neural-hive.local/ns/.../sa/... \
  -parentID spiffe://neural-hive.local/spire/agent/k8s_psat/production \
  -selector k8s:ns:... \
  -selector k8s:sa:...
```

#### JWT Auth Fail
```bash
# Verificar trust bundle
kubectl exec -n spire-system spire-server-0 -- \
  /opt/spire/bin/spire-server bundle show

# Verificar audience no JWT
kubectl exec -n neural-hive-orchestration <pod> -- sh -c '
  curl --unix-socket /run/spire/sockets/agent.sock \
    http://localhost/v1/spiffe/workload/jwt \
    -d "{\"audience\": [\"vault.neural-hive.local\"]}" | jq .
'
```

#### Service Registry UNAUTHENTICATED
```bash
# Verificar SPIFFE ID autorizado no interceptor
kubectl logs -n neural-hive-execution <service-registry-pod> | grep UNAUTHENTICATED

# Verificar lista de allowed SPIFFE IDs em auth_interceptor.py
# Adicionar SPIFFE ID do cliente se necessário
```

---

### Próximos Passos

1. **Backup**: Snapshots automáticos do Vault Raft (S3)
2. **DR**: Documentar procedimento de recovery
3. **Istio**: Integrar SPIRE com Istio mTLS (opcional)

### Veja também

- [VAULT_SPIFFE_OPERATIONS_RUNBOOK.md](./VAULT_SPIFFE_OPERATIONS_RUNBOOK.md) - Operações dia-a-dia
- [VAULT_POLICIES.md](./VAULT_POLICIES.md) - Templates de políticas e testing
- [SECRETS_MANAGEMENT_GUIDE.md](./SECRETS_MANAGEMENT_GUIDE.md) - Gestão de secrets
