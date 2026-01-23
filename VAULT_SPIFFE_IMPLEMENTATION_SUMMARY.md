# Resumo de Implementação - Integração Vault/SPIFFE

## Visão Geral

Implementação completa da integração de segurança Vault/SPIFFE para o Neural Hive-Mind, fornecendo:
- Credenciais efêmeras e dinâmicas via HashiCorp Vault
- Identidade de workload via SPIFFE/SPIRE
- Auto-unseal do Vault com AWS KMS
- Autenticação JWT-SVID para gRPC inter-service

## Componentes Implementados

### 1. Biblioteca de Segurança (`libraries/security/neural_hive_security/`)

**Status**: ✅ COMPLETO

#### Arquivos Principais:
- `__init__.py`: Exports de classes públicas
- `vault_client.py`: Cliente Vault async com retry, circuit breaker, métricas
- `spiffe_manager.py`: Cliente SPIRE Workload API com auto-refresh
- `config.py`: Modelos Pydantic para configuração
- `token_cache.py`: Cache LRU com refresh automático
- `workload_pb2.py` / `workload_pb2_grpc.py`: Stubs gRPC SPIRE

#### Funcionalidades:
- **VaultClient**:
  - Autenticação Kubernetes/JWT
  - KV v2 secrets engine
  - Dynamic database credentials (PostgreSQL, MongoDB)
  - PKI certificate issuance
  - Auto token renewal
  - Retry exponencial com tenacity
  - Métricas Prometheus
  
- **SPIFFEManager**:
  - Fetch JWT-SVID com audience configurável
  - Fetch X.509-SVID para mTLS
  - Trust bundle management para JWT validation
  - Auto-refresh SVIDs at 80% TTL
  - Fallback para env vars se SPIRE indisponível

- **TokenCache**:
  - Estratégias EAGER/LAZY/DISABLED
  - Thread-safe com asyncio.Lock
  - Background refresh antes de expiração

#### Dependências:
```python
hvac>=1.2.0
grpcio>=1.54.0
httpx>=0.24.0
pydantic>=2.0.0
tenacity>=8.2.0
structlog>=23.1.0
prometheus-client>=0.17.0
cryptography>=41.0.0
```

### 2. Integração nos Serviços

#### 2.1 Orchestrator Dynamic

**Arquivos Modificados**:
- `services/orchestrator-dynamic/src/main.py`
- `services/orchestrator-dynamic/src/clients/kafka_producer.py`
- `services/orchestrator-dynamic/src/workers/temporal_worker.py`
- `services/orchestrator-dynamic/src/clients/vault_integration.py` (já existia)

**Implementação**:
```python
# main.py - Startup
if config.vault_enabled:
    vault_client = OrchestratorVaultClient(config)
    await vault_client.initialize()
    
    # Get credentials from Vault
    mongodb_uri = await vault_client.get_mongodb_uri()
    pg_creds = await vault_client.get_postgres_credentials()
    kafka_creds = await vault_client.get_kafka_credentials()
    
    # Pass to clients
    app_state.mongodb_client = MongoDBClient(config, uri_override=mongodb_uri)
    app_state.kafka_producer = KafkaProducerClient(
        config,
        sasl_username_override=kafka_creds['username'],
        sasl_password_override=kafka_creds['password']
    )
    app_state.temporal_client = await create_temporal_client(
        config,
        postgres_user=pg_creds['username'],
        postgres_password=pg_creds['password']
    )
```

**Renewal Task**:
- Background task `renew_credentials()` monitora TTLs
- Renovação automática em 80% do TTL
- Recreação de conexões com novas credenciais

#### 2.2 Worker Agents

**Arquivos Modificados**:
- `services/worker-agents/src/main.py`
- `services/worker-agents/src/clients/vault_integration.py` (já existia)

**Implementação**:
```python
# main.py - Startup
if config.vault_enabled:
    vault_client = WorkerVaultClient(config)
    await vault_client.initialize()
    app_state['vault_client'] = vault_client
    
    # Get Kafka credentials
    kafka_creds = await vault_client.get_kafka_credentials()
    
    # Pass SPIFFE manager to ServiceRegistryClient
    spiffe_manager = vault_client.spiffe_manager
    registry_client = ServiceRegistryClient(config, spiffe_manager=spiffe_manager)
    
    # Pass vault_client to executors
    executor_registry.register_executor(BuildExecutor(config, vault_client=vault_client))
    # ... outros executors
```

**Funcionalidades**:
- Credenciais de execução por tipo de task
- JWT-SVID para Service Registry auth
- Armazenamento de resultados sensíveis no Vault

#### 2.3 Service Registry

**Arquivos Existentes** (não modificados nesta sessão, já implementados):
- `services/service-registry/src/grpc_server/auth_interceptor.py`

**Funcionalidades Já Implementadas**:
- **SPIFFEAuthInterceptor**: Valida JWT-SVID em metadata gRPC
- Decode JWT header para extrair `kid`
- Fetch trust bundle keys do SPIFFEManager
- Verificação com PyJWT (RS256/ES256/ES384)
- Validação de claims: `iss`, `aud`, `exp`, `sub`
- Extração de SPIFFE ID do claim `sub`
- Autorização baseada em allowed_spiffe_ids por método

### 3. Infraestrutura

#### 3.1 Terraform - Módulo vault-ha

**Localização**: `infrastructure/terraform/modules/vault-ha/`

**Recursos Criados**:
- **KMS Key**: Auto-unseal do Vault
  - Key rotation habilitada
  - Alias: `<cluster-name>-vault-unseal`
  
- **IAM Role**: IRSA para Vault Server
  - Trust policy para OIDC provider do EKS
  - Service account: `vault:vault-server`
  
- **IAM Policies**:
  - KMS unseal: `kms:Encrypt`, `kms:Decrypt`, `kms:DescribeKey`
  - Secrets Manager: Backup de root token e unseal keys
  - S3 (opcional): Audit logs
  
- **Secrets Manager**:
  - `<cluster-name>/vault/root-token`
  - `<cluster-name>/vault/unseal-keys`
  
- **S3 Bucket** (opcional):
  - Audit logs com versioning e encryption

**Outputs**:
```hcl
output "kms_key_id"
output "vault_server_role_arn"
output "root_token_secret_arn"
output "audit_logs_bucket_name"
```

**Integração em main.tf**:
```hcl
module "vault-ha" {
  source = "./modules/vault-ha"
  
  cluster_name      = var.cluster_name
  region            = var.aws_region
  account_id        = var.aws_account_id
  oidc_provider_arn = module.k8s-cluster.oidc_provider_arn
  oidc_provider_url = module.k8s-cluster.oidc_issuer_url
  enable_audit_logs = var.enable_vault_audit_logs
  
  depends_on = [module.k8s-cluster]
}
```

#### 3.2 Helm Chart - Vault

**Localização**: `helm-charts/vault/`

**Componentes**:
- **Server StatefulSet**:
  - 3 replicas para HA
  - Raft storage backend
  - TLS listener (porta 8200)
  - KMS auto-unseal via IRSA
  - PVC 10Gi para Raft data
  
- **Service Account**:
  - Anotação IRSA: `eks.amazonaws.com/role-arn`
  
- **Injector Deployment**:
  - vault-k8s sidecar injector
  - Webhook para injeção de secrets
  
- **Services**:
  - ClusterIP para UI (8200)
  - Headless para Raft peers
  
- **NetworkPolicy**:
  - Ingress de namespaces `neural-hive-orchestration` e `neural-hive-execution`
  
- **ServiceMonitor**:
  - Prometheus scraping em /v1/sys/metrics

**Configuração Raft**:
```hcl
storage "raft" {
  path = "/vault/data"
  retry_join {
    leader_api_addr = "https://vault-0.vault-internal:8200"
    leader_ca_cert_file = "/vault/userconfig/vault-tls/ca.crt"
  }
}

seal "awskms" {
  region     = "us-east-1"
  kms_key_id = "<from terraform output>"
}
```

#### 3.3 Helm Chart - SPIRE

**Localização**: `helm-charts/spire/`

**Componentes**:
- **SPIRE Server StatefulSet**:
  - 3 replicas para HA
  - PostgreSQL datastore (para produção)
  - Node attestation: Kubernetes PSAT
  - Workload attestation: Kubernetes
  - Upstream authority: Vault PKI (opcional)
  
- **SPIRE Agent DaemonSet**:
  - Executa em cada nó
  - Socket Unix: `/run/spire/sockets/agent.sock`
  - HostPath volumes para socket e data
  - Tolerations para todos os nós
  
- **OIDC Discovery Provider**:
  - 2 replicas
  - Ingress: `spire-oidc.neural-hive.local`
  - Para validação de JWT-SVID externa
  
- **Workload Entries** (via Job):
  ```yaml
  - spiffe://neural-hive.local/ns/neural-hive-orchestration/sa/orchestrator-dynamic
  - spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents
  - spiffe://neural-hive.local/ns/neural-hive-registry/sa/service-registry
  ```

**RBAC**:
- ClusterRole para SPIRE Server: `get/list/watch` em `pods`, `nodes`, `serviceaccounts`
- ClusterRole para SPIRE Agent: `get/list` em `pods`

**NetworkPolicy**:
- Server ingress de Agent
- Agent egress para Server

#### 3.4 Service Helm Charts - Vault/SPIRE Integration

**orchestrator-dynamic**:
```yaml
# deployment.yaml - annotations
vault.hashicorp.com/agent-inject: "true"
vault.hashicorp.com/role: "orchestrator-dynamic"
vault.hashicorp.com/agent-inject-secret-mongodb: "secret/data/orchestrator/mongodb"
vault.hashicorp.com/agent-inject-secret-postgres: "database/creds/temporal-orchestrator"
vault.hashicorp.com/agent-inject-secret-kafka: "secret/data/orchestrator/kafka"

# deployment.yaml - volumes
- name: spire-agent-socket
  hostPath:
    path: /run/spire/sockets
    type: Directory

# deployment.yaml - volumeMounts
- name: spire-agent-socket
  mountPath: /run/spire/sockets
  readOnly: true
```

**worker-agents**:
```yaml
# deployment.yaml - annotations
vault.hashicorp.com/agent-inject: "true"
vault.hashicorp.com/role: "worker-agents"
vault.hashicorp.com/agent-inject-secret-kafka: "secret/data/worker/kafka"
vault.hashicorp.com/agent-inject-secret-execution: "secret/data/worker/execution"

# deployment.yaml - volumes/volumeMounts (igual orchestrator)
```

### 4. Fluxo de Segurança

#### 4.1 Vault Authentication Flow
1. Pod inicia com service account Kubernetes
2. Vault Agent Injector adiciona init container
3. Init container lê SA token de `/var/run/secrets/kubernetes.io/serviceaccount/token`
4. Autentica no Vault via `/v1/auth/kubernetes/login` com role específico
5. Vault valida token via Kubernetes TokenReview API
6. Retorna client token Vault com policies associadas
7. Agent sidecar renova token automaticamente

#### 4.2 SPIFFE Identity Flow
1. SPIRE Agent em cada nó conecta ao SPIRE Server
2. Workload (pod) conecta ao Agent via socket Unix
3. Agent atesta workload via selectors (`k8s:ns`, `k8s:sa`)
4. Server valida attestation e consulta registration entries
5. Retorna JWT-SVID ou X.509-SVID com SPIFFE ID
6. Workload usa SVID para autenticar em outros serviços
7. Auto-refresh antes de 80% do TTL

#### 4.3 gRPC Authentication Flow (Service Registry)
1. Cliente (worker) fetch JWT-SVID via SPIFFEManager
   ```python
   jwt_svid = await spiffe_manager.fetch_jwt_svid("service-registry.neural-hive.local")
   ```
2. Adiciona JWT em metadata gRPC:
   ```python
   metadata = [("authorization", f"Bearer {jwt_svid.token}")]
   ```
3. SPIFFEAuthInterceptor no servidor:
   - Extrai token de metadata
   - Decode header para `kid`
   - Fetch trust bundle keys do SPIFFEManager
   - Verifica signature com PyJWT
   - Valida claims: `iss`, `aud`, `exp`, `sub`
   - Extrai SPIFFE ID de `sub`
   - Autoriza baseado em allowed_spiffe_ids

### 5. Métricas e Observabilidade

#### Vault Metrics (Prometheus)
```
vault_requests_total{operation, status}
vault_request_duration_seconds{operation}
vault_token_renewals_total{status}
```

#### SPIFFE Metrics
```
spiffe_svid_fetch_total{svid_type, status}
spiffe_svid_fetch_duration_seconds{svid_type}
```

#### gRPC Auth Metrics
```
grpc_auth_attempts_total{method, status}
grpc_auth_failures_total{method, reason}
```

#### Token Cache Metrics
```
token_cache_hits_total
token_cache_misses_total
token_cache_refresh_total{status}
cache_size
```

### 6. Configuração e Deploy

#### 6.1 Terraform
```bash
cd infrastructure/terraform

# Initialize
terraform init

# Plan com outputs do vault-ha
terraform plan -out=plan.out

# Apply
terraform apply plan.out

# Outputs
export VAULT_KMS_KEY_ID=$(terraform output -raw vault_kms_key_id)
export VAULT_ROLE_ARN=$(terraform output -raw vault_server_role_arn)
```

#### 6.2 Helm - Vault
```bash
# Create namespace
kubectl create namespace vault

# Install cert-manager para TLS
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create TLS certificate (cert-manager)
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: vault-tls
  namespace: vault
spec:
  secretName: vault-tls
  issuerRef:
    name: ca-issuer
    kind: ClusterIssuer
  dnsNames:
  - vault
  - vault.vault
  - vault.vault.svc
  - vault.vault.svc.cluster.local
  - "*.vault-internal"
EOF
```

### 7. Rotação Automática de Credenciais

#### 7.1 MongoDB Dynamic Credentials

**Configuração Vault:**
```bash
# Habilitar database secrets engine
vault secrets enable database

# Configurar MongoDB connection
vault write database/config/mongodb-orchestrator \
    plugin_name=mongodb-database-plugin \
    allowed_roles="orchestrator-dynamic" \
    connection_url="mongodb://{{username}}:{{password}}@mongodb:27017/admin" \
    username="vault-admin" \
    password="vault-admin-password"

# Criar role com TTL 1h
vault write database/roles/mongodb-orchestrator \
    db_name=mongodb-orchestrator \
    creation_statements='{ "db": "neural_hive_orchestration", "roles": [{ "role": "readWrite" }] }' \
    default_ttl="1h" \
    max_ttl="24h"
```

**Renovação Automática:**
- Threshold: 80% do TTL (configurável via `vault_db_credentials_renewal_threshold`)
- Background task monitora expiry
- Novas credenciais buscadas automaticamente
- **Limitação:** Connection pool do MongoDB não é atualizado automaticamente

#### 7.2 Kafka SASL Credentials

**Configuração Vault:**
```bash
# Armazenar credenciais Kafka no KV v2
vault kv put secret/orchestrator/kafka \
    username="orchestrator-kafka-user" \
    password="generated-password" \
    ttl=3600

vault kv put secret/worker/kafka \
    username="worker-kafka-user" \
    password="generated-password" \
    ttl=3600
```

**Renovação Automática:**
- Threshold: 80% do TTL
- Background task monitora expiry
- Novas credenciais buscadas automaticamente
- **Limitação:** Kafka producer não é recriado automaticamente

#### 7.3 PostgreSQL Dynamic Credentials

**Já Implementado** (ver seção 2.1)

---

### 8. Health Checks

#### 8.1 Vault Connectivity

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-23T10:00:00Z",
  "checks": {
    "vault": {
      "status": "healthy",
      "enabled": true
    },
    "redis": {
      "available": true,
      "circuit_breaker_state": "closed"
    }
  }
}
```

**Fail-Closed Behavior:**
- Se `vault.failOpen: false` e Vault unhealthy → `/health` retorna `unhealthy`
- Kubernetes readiness probe falha → pod removido do service
- Garante que apenas pods com Vault funcional recebem tráfego

**Fail-Open Behavior:**
- Se `vault.failOpen: true` e Vault unhealthy → `/health` retorna `healthy`
- Pod continua operando com credenciais estáticas
- **Apenas para desenvolvimento**

---

### 9. Testes

#### 9.1 Testes de Rotação

**Localização:** `tests/integration/test_vault_*_rotation.py`

**Cobertura:**
- ✅ Renovação no threshold (80% TTL)
- ✅ Não renovação antes do threshold
- ✅ Renovação imediata em caso de expiração
- ✅ Fallback para credenciais estáticas em fail-open
- ✅ Fail-closed quando vault_fail_open=false

**Executar:**
```bash
pytest tests/integration/test_vault_postgres_rotation.py -v
pytest tests/integration/test_vault_mongodb_rotation.py -v
pytest tests/integration/test_vault_kafka_rotation.py -v
```

#### 9.2 Testes E2E

**Cenário:** Rotação de credenciais durante execução de workflow

1. Iniciar workflow Temporal
2. Aguardar 80% do TTL de credenciais PostgreSQL
3. Verificar renovação automática
4. Validar que workflow continua executando sem erros
5. Verificar métricas de renovação

---

### 10. Métricas de Rotação

**Novas Métricas:**
```
orchestrator_vault_credentials_fetched_total{credential_type, status}
orchestrator_vault_renewal_task_runs_total{status}
service_registry_vault_credentials_fetched_total{credential_type, status}
```

**Alertas Recomendados:**
```yaml
- alert: VaultCredentialRenewalFailed
  expr: rate(orchestrator_vault_renewal_task_runs_total{status="error"}[5m]) > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Falha na renovação de credenciais Vault"
    description: "Renovação de credenciais falhou por 5 minutos"

- alert: VaultCredentialExpiringSoon
  expr: (vault_credential_expiry_seconds - time()) < 300
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "Credencial Vault expirando em < 5min"
```

---

### 11. Runbook Operacional

#### 11.1 Habilitar Vault em Produção

**Pré-requisitos:**
1. Vault Server instalado e inicializado
2. SPIRE Server e Agents instalados
3. Terraform module `vault-ha` aplicado
4. Secrets configurados no Vault

**Passos:**

1. **Configurar Vault Policies:**
```bash
# Orchestrator Dynamic
vault policy write orchestrator-dynamic - <<EOF
path "secret/data/orchestrator/*" {
  capabilities = ["read"]
}
path "database/creds/temporal-orchestrator" {
  capabilities = ["read"]
}
path "database/creds/mongodb-orchestrator" {
  capabilities = ["read"]
}
EOF

# Worker Agents
vault policy write worker-agents - <<EOF
path "secret/data/worker/*" {
  capabilities = ["read", "create", "update"]
}
EOF

# Service Registry
vault policy write service-registry - <<EOF
path "secret/data/service-registry/*" {
  capabilities = ["read"]
}
EOF
```

2. **Configurar Kubernetes Auth:**
```bash
vault auth enable kubernetes

vault write auth/kubernetes/config \
    kubernetes_host="https://kubernetes.default.svc:443" \
    kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
    token_reviewer_jwt=@/var/run/secrets/kubernetes.io/serviceaccount/token

# Criar roles
vault write auth/kubernetes/role/orchestrator-dynamic \
    bound_service_account_names=orchestrator-dynamic \
    bound_service_account_namespaces=neural-hive-orchestration \
    policies=orchestrator-dynamic \
    ttl=1h

vault write auth/kubernetes/role/worker-agents \
    bound_service_account_names=worker-agents \
    bound_service_account_namespaces=neural-hive-execution \
    policies=worker-agents \
    ttl=1h

vault write auth/kubernetes/role/service-registry \
    bound_service_account_names=service-registry \
    bound_service_account_namespaces=neural-hive-registry \
    policies=service-registry \
    ttl=1h
```

3. **Configurar Database Secrets Engine:**
```bash
# PostgreSQL (Temporal)
vault secrets enable database

vault write database/config/temporal-orchestrator \
    plugin_name=postgresql-database-plugin \
    allowed_roles="temporal-orchestrator" \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/temporal?sslmode=require" \
    username="vault-admin" \
    password="$POSTGRES_VAULT_PASSWORD"

vault write database/roles/temporal-orchestrator \
    db_name=temporal-orchestrator \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; \
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h"

# MongoDB
vault write database/config/mongodb-orchestrator \
    plugin_name=mongodb-database-plugin \
    allowed_roles="orchestrator-dynamic" \
    connection_url="mongodb://{{username}}:{{password}}@mongodb:27017/admin" \
    username="vault-admin" \
    password="$MONGODB_VAULT_PASSWORD"

vault write database/roles/mongodb-orchestrator \
    db_name=mongodb-orchestrator \
    creation_statements='{ "db": "neural_hive_orchestration", "roles": [{ "role": "readWrite" }] }' \
    default_ttl="1h" \
    max_ttl="24h"
```

4. **Armazenar Secrets Estáticos:**
```bash
# Kafka credentials
vault kv put secret/orchestrator/kafka \
    username="orchestrator-kafka-user" \
    password="$KAFKA_ORCHESTRATOR_PASSWORD"

vault kv put secret/worker/kafka \
    username="worker-kafka-user" \
    password="$KAFKA_WORKER_PASSWORD"

# Redis passwords
vault kv put secret/orchestrator/redis \
    password="$REDIS_PASSWORD"

vault kv put secret/service-registry/redis \
    password="$REDIS_PASSWORD"

# etcd credentials
vault kv put secret/service-registry/etcd \
    username="service-registry" \
    password="$ETCD_PASSWORD"
```

5. **Atualizar Helm Values:**
```bash
# Orchestrator Dynamic
helm upgrade orchestrator-dynamic ./helm-charts/orchestrator-dynamic \
    --set vault.enabled=true \
    --set vault.failOpen=false \
    --set environment=production

# Worker Agents
helm upgrade worker-agents ./helm-charts/worker-agents \
    --set vault.enabled=true \
    --set vault.failOpen=false

# Service Registry
helm upgrade service-registry ./helm-charts/service-registry \
    --set vault.enabled=true \
    --set vault.failOpen=false
```

6. **Validar Health Checks:**
```bash
# Orchestrator Dynamic
kubectl exec -it orchestrator-dynamic-0 -- curl http://localhost:8000/health | jq '.checks.vault'

# Worker Agents
kubectl exec -it worker-agents-0 -- curl http://localhost:8080/health | jq '.checks.vault'
```

7. **Monitorar Métricas:**
```bash
# Verificar renovações de credenciais
kubectl port-forward svc/prometheus 9090:9090
# Abrir http://localhost:9090
# Query: rate(orchestrator_vault_renewal_task_runs_total[5m])
```

#### 11.2 Troubleshooting

**Problema:** Vault health check falha

**Diagnóstico:**
```bash
# Verificar conectividade
kubectl exec -it orchestrator-dynamic-0 -- curl -k https://vault.vault.svc.cluster.local:8200/v1/sys/health

# Verificar logs
kubectl logs orchestrator-dynamic-0 | grep vault

# Verificar service account token
kubectl exec -it orchestrator-dynamic-0 -- cat /var/run/secrets/kubernetes.io/serviceaccount/token
```

**Solução:**
- Verificar NetworkPolicy permite egress para namespace `vault`
- Verificar Vault Server está healthy
- Verificar Kubernetes auth configurado corretamente

---

**Problema:** Credenciais não renovam automaticamente

**Diagnóstico:**
```bash
# Verificar logs de renovação
kubectl logs orchestrator-dynamic-0 | grep renew

# Verificar métricas
curl http://orchestrator-dynamic:9090/metrics | grep vault_renewal
```

**Solução:**
- Verificar TTL das credenciais > 5 minutos
- Verificar threshold configurado corretamente (default: 0.2 = 80%)
- Verificar background task está rodando

---

**Problema:** Pods não iniciam com Vault habilitado

**Diagnóstico:**
```bash
# Verificar eventos
kubectl describe pod orchestrator-dynamic-0

# Verificar logs de inicialização
kubectl logs orchestrator-dynamic-0 --previous
```

**Solução:**
- Se `vault.failOpen: false`, pod não inicia se Vault indisponível
- Verificar Vault Server está healthy
- Temporariamente usar `vault.failOpen: true` para debug (apenas dev)

---

### 12. Limitações Conhecidas

1. **Connection Pool Não Atualizado Automaticamente:**
   - MongoDB e PostgreSQL connection pools não são recriados após renovação
   - Conexões existentes continuam usando credenciais antigas até expiração
   - **Mitigação:** TTL longo (1h) permite que conexões sejam recicladas naturalmente

2. **Kafka Producer Não Recriado:**
   - Producer Kafka não é recriado após renovação de SASL credentials
   - **Mitigação:** Restart do pod após renovação (via rolling update)

3. **Vault Indisponibilidade:**
   - Com `failOpen: false`, pods não iniciam se Vault indisponível
   - **Mitigação:** Garantir alta disponibilidade do Vault (3 replicas, Raft storage)

---

### 13. Próximos Passos (Fora do Escopo)

1. **Recreação Automática de Connection Pools:**
   - Implementar hot-reload de credenciais
   - Requer coordenação com lifecycle dos clientes

2. **Vault Agent Sidecar:**
   - Usar Vault Agent para injeção automática de secrets
   - Simplifica renovação (Agent gerencia)

3. **External Secrets Operator:**
   - Sincronizar secrets do Vault para Kubernetes Secrets
   - Facilita integração com aplicações existentes
