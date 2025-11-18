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
