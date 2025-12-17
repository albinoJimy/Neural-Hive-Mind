# Guia de Gerenciamento de Secrets - Fase 2

Este guia documenta a estratégia de gerenciamento de secrets para os serviços da Fase 2 do Neural Hive Mind, incluindo criação, validação, rotação e integração com HashiCorp Vault.

## Índice

- [Visão Geral](#visão-geral)
- [Secrets por Serviço](#secrets-por-serviço)
- [Início Rápido](#início-rápido)
- [Modo Secrets Estáticos](#modo-secrets-estáticos)
- [Integração com Vault](#integração-com-vault)
- [External Secrets Operator](#external-secrets-operator)
- [Rotação de Secrets](#rotação-de-secrets)
- [Troubleshooting](#troubleshooting)

## Visão Geral

A Fase 2 introduz 13 novos serviços em 8 namespaces, cada um requerendo secrets Kubernetes para credenciais de banco de dados, tokens de API e autenticação de serviços.

### Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Gerenciamento de Secrets - 3 Modos                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────────┐      │
│  │  static        │  │  vault-agent    │  │  external-secrets    │      │
│  │  (Dev/Staging) │  │  (Sidecar)      │  │  (GitOps)            │      │
│  └───────┬────────┘  └───────┬─────────┘  └──────────┬───────────┘      │
│          │                   │                       │                   │
│          ▼                   ▼                       ▼                   │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────────┐      │
│  │  K8s Secrets   │  │ Secret + Vault  │  │  ExternalSecret CR   │      │
│  │  (stringData)  │  │ Annotations     │  │  → K8s Secret        │      │
│  └───────┬────────┘  └───────┬─────────┘  └──────────┬───────────┘      │
│          │                   │                       │                   │
│          └───────────────────┴───────────────────────┘                   │
│                              │                                           │
│                              ▼                                           │
│                  ┌──────────────────────┐                                │
│                  │  Variáveis de Amb.   │                                │
│                  │   do Pod (envFrom)   │                                │
│                  └──────────────────────┘                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Modos Disponíveis

| Modo | Descrição | Uso Recomendado |
|------|-----------|-----------------|
| `static` | Gera K8s Secrets com valores placeholder | Desenvolvimento, Staging, CI/CD |
| `vault-agent` | Gera Secrets com anotações Vault Agent Injector | Produção com sidecar injection |
| `external-secrets` | Gera ExternalSecret CRs para External Secrets Operator | GitOps (ArgoCD, Flux) |

## Secrets por Serviço

### Tabela de Referência Completa

| Serviço | Namespace | Nome do Secret | Chaves |
|---------|-----------|----------------|--------|
| **orchestrator-dynamic** | neural-hive-orchestration | orchestrator-dynamic-secrets | POSTGRES_USER, POSTGRES_PASSWORD, MONGODB_URI, REDIS_PASSWORD, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD |
| **execution-ticket-service** | neural-hive-orchestration | execution-ticket-service-secrets | POSTGRES_PASSWORD, MONGODB_URI, JWT_SECRET_KEY |
| **queen-agent** | neural-hive-queen | queen-agent-secrets | MONGODB_URI, REDIS_CLUSTER_NODES, REDIS_PASSWORD, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD |
| **worker-agents** | neural-hive-execution | worker-agents-secrets | KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD, ARGOCD_TOKEN, JENKINS_TOKEN, SONARQUBE_TOKEN, SNYK_TOKEN |
| **code-forge** | neural-hive-execution | code-forge-secrets | POSTGRES_USER, POSTGRES_PASSWORD, MONGODB_URI, REDIS_PASSWORD, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD, GIT_USERNAME, GIT_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY |
| **service-registry** | neural-hive-registry | service-registry-secrets | REDIS_PASSWORD, ETCD_USERNAME, ETCD_PASSWORD |
| **scout-agents** | neural-hive-estrategica | scout-agents-secrets | KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD, REDIS_PASSWORD |
| **analyst-agents** | neural-hive-estrategica | analyst-agents-secrets | MONGODB_URI, REDIS_PASSWORD, NEO4J_PASSWORD, CLICKHOUSE_PASSWORD, ELASTICSEARCH_PASSWORD |
| **optimizer-agents** | neural-hive-estrategica | optimizer-agents-secrets | MONGODB_URI, REDIS_PASSWORD, MLFLOW_TRACKING_TOKEN |
| **guard-agents** | neural-hive-resilience | guard-agents-secrets | MONGODB_PASSWORD, REDIS_PASSWORD, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD |
| **self-healing-engine** | neural-hive-resilience | self-healing-engine-secrets | MONGODB_PASSWORD, REDIS_PASSWORD, KAFKA_SASL_PASSWORD, PAGERDUTY_API_KEY, SLACK_WEBHOOK_URL |
| **sla-management-system** | neural-hive-monitoring | sla-management-system-secrets | POSTGRES_USER, POSTGRES_PASSWORD, REDIS_PASSWORD, PROMETHEUS_BEARER_TOKEN |
| **mcp-tool-catalog** | neural-hive-mcp | mcp-tool-catalog-secrets | MONGODB_URI, REDIS_PASSWORD, KAFKA_SASL_USERNAME, KAFKA_SASL_PASSWORD, GITHUB_TOKEN, GITLAB_TOKEN |

### Resumo por Namespace

| Namespace | Serviços | Total de Secrets |
|-----------|----------|------------------|
| neural-hive-orchestration | orchestrator-dynamic, execution-ticket-service | 2 |
| neural-hive-queen | queen-agent | 1 |
| neural-hive-execution | worker-agents, code-forge | 2 |
| neural-hive-registry | service-registry | 1 |
| neural-hive-estrategica | scout-agents, analyst-agents, optimizer-agents | 3 |
| neural-hive-resilience | guard-agents, self-healing-engine | 2 |
| neural-hive-monitoring | sla-management-system | 1 |
| neural-hive-mcp | mcp-tool-catalog | 1 |
| **Total** | **13 serviços** | **13 secrets** |

## Início Rápido

### Pré-requisitos

Antes de executar os scripts de secrets, certifique-se de ter as seguintes ferramentas instaladas:

- **kubectl** - CLI do Kubernetes configurado com acesso ao cluster
- **openssl** - Para geração de senhas aleatórias (usado pelo script de criação)
- **base64** - Para codificação/decodificação de valores de secrets

```bash
# Verificar instalação
kubectl version --client
openssl version
base64 --version
```

### 1. Criar Namespaces (Obrigatório)

**IMPORTANTE:** Os namespaces devem ser criados antes dos secrets. O script de criação de secrets **não cria namespaces automaticamente** - ele apenas valida e emite warnings se o namespace não existir.

```bash
# Criar todos os namespaces da Fase 2 com ResourceQuotas, LimitRanges e NetworkPolicies
kubectl apply -f k8s/bootstrap/namespaces-phase2.yaml
```

### 2. Criar Secrets (Desenvolvimento)

```bash
# Modo static para desenvolvimento (valores placeholder gerados automaticamente)
./scripts/create-phase2-secrets.sh --mode static --environment dev

# Modo vault-agent para produção com Vault Agent Injector
./scripts/create-phase2-secrets.sh --mode vault-ag ent --environment production

# Modo external-secrets para GitOps (ArgoCD/Flux)
./scripts/create-phase2-secrets.sh --mode external-secrets --environment production
```

### 3. Validar Secrets

```bash
./scripts/validate-phase2-secrets.sh
```

### 4. Deploy dos Serviços

```bash
# Deploy de serviço individual
helm upgrade --install orchestrator-dynamic helm-charts/orchestrator-dynamic/

# Ou deploy de todos os serviços da Fase 2
for service in orchestrator-dynamic execution-ticket-service queen-agent \
               worker-agents code-forge service-registry scout-agents \
               analyst-agents optimizer-agents guard-agents \
               self-healing-engine sla-management-system mcp-tool-catalog; do
  helm upgrade --install $service helm-charts/$service/
done
```

## Estrutura Centralizada de Serviços

O script `create-phase2-secrets.sh` utiliza uma estrutura centralizada (`PHASE2_SERVICES`) como fonte única de verdade para todos os serviços e seus secrets.

### Formato da Definição

```bash
# Format: "namespace|secret-name|key1,key2,key3|vault-path"
"neural-hive-orchestration|orchestrator-dynamic-secrets|POSTGRES_USER,POSTGRES_PASSWORD,MONGODB_URI|secret/orchestrator-dynamic"
```

### Adicionar Novo Serviço

Para adicionar um novo serviço à Fase 2:

1. Edite `scripts/create-phase2-secrets.sh` e adicione entrada no array `PHASE2_SERVICES`
2. Execute o script: `./scripts/create-phase2-secrets.sh`
3. Atualize o `validate-phase2-secrets.sh` correspondente (ou regenere)

### Integração com Helm Charts

Os Helm charts usam `secretKeyRef` para referenciar os secrets criados:

```yaml
# helm-charts/<service>/values.yaml
secrets:
  existingSecret: "<service>-secrets"
  postgresPasswordKey: POSTGRES_PASSWORD
  mongodbUriKey: MONGODB_URI
```

## Modo Secrets Estáticos

Para ambientes de desenvolvimento e staging, use secrets estáticos com valores placeholder gerados automaticamente.

### Gerar Secrets Estáticos

```bash
# Desenvolvimento
./scripts/create-phase2-secrets.sh --mode static --environment dev

# Staging
./scripts/create-phase2-secrets.sh --mode static --environment staging

# Dry-run (gerar apenas arquivos sem aplicar)
./scripts/create-phase2-secrets.sh --mode static --environment dev --dry-run --output-dir ./secrets
```

### Criação Manual de Secret

Se precisar criar um secret específico manualmente:

```bash
# Criar orchestrator-dynamic-secrets
kubectl create secret generic orchestrator-dynamic-secrets \
  --namespace=neural-hive-orchestration \
  --from-literal=POSTGRES_USER=orchestrator \
  --from-literal=POSTGRES_PASSWORD=$(openssl rand -hex 16) \
  --from-literal=MONGODB_URI="mongodb://admin:password@mongodb-headless:27017/orchestrator" \
  --from-literal=REDIS_PASSWORD=$(openssl rand -hex 16) \
  --from-literal=KAFKA_SASL_USERNAME=orchestrator \
  --from-literal=KAFKA_SASL_PASSWORD=$(openssl rand -hex 16)
```

### Visualizar Conteúdo dos Secrets

```bash
# Listar secrets no namespace
kubectl get secrets -n neural-hive-orchestration

# Visualizar chaves do secret
kubectl get secret orchestrator-dynamic-secrets -n neural-hive-orchestration -o jsonpath='{.data}' | jq

# Decodificar valor específico
kubectl get secret orchestrator-dynamic-secrets -n neural-hive-orchestration \
  -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d
```

## Integração com Vault

Para ambientes de produção, use HashiCorp Vault para gerenciamento centralizado de secrets.

### Pré-requisitos

1. Servidor Vault implantado e acessível
2. Vault CLI instalado e autenticado
3. Engine de secrets KV habilitado em `secret/`

### Popular Secrets no Vault

```bash
# Definir endereço do Vault
export VAULT_ADDR=https://vault.example.com

# Autenticar
vault login

# Popular secrets
./scripts/vault-populate-secrets.sh

# Modo dry-run
DRY_RUN=true ./scripts/vault-populate-secrets.sh
```

### Criar Secrets com Vault Agent Injector

```bash
./scripts/create-phase2-secrets.sh --mode vault-agent --environment production
```

Isso cria secrets com anotações do Vault Agent Injector:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: orchestrator-dynamic-secrets
  namespace: neural-hive-orchestration
  annotations:
    vault.hashicorp.com/agent-inject: "true"
    vault.hashicorp.com/role: "orchestrator-dynamic"
    vault.hashicorp.com/agent-inject-secret-postgres_password: "secret/data/orchestrator-dynamic/postgres"
```

### Políticas do Vault

Criar políticas apropriadas para cada serviço:

```hcl
# orchestrator-dynamic-policy.hcl
path "secret/data/orchestrator-dynamic/*" {
  capabilities = ["read"]
}

path "secret/metadata/orchestrator-dynamic/*" {
  capabilities = ["list"]
}
```

Aplicar a política:

```bash
vault policy write orchestrator-dynamic orchestrator-dynamic-policy.hcl
```

## External Secrets Operator

Para sincronização de secrets compatível com GitOps a partir do Vault.

### Gerar ExternalSecrets para GitOps

```bash
# Gerar ExternalSecret CRs para produção
./scripts/create-phase2-secrets.sh --mode external-secrets --environment production

# Dry-run para GitOps (gera arquivos para commit no repo)
./scripts/create-phase2-secrets.sh --mode external-secrets --environment production \
  --dry-run --output-dir ./gitops/secrets
```

Os arquivos gerados podem ser commitados no repositório GitOps para deploy via ArgoCD ou Flux.

### Pré-requisitos

1. External Secrets Operator instalado no cluster
2. ClusterSecretStore configurado para Vault

### Criar ClusterSecretStore

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.example.com"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "external-secrets"
          serviceAccountRef:
            name: "external-secrets"
            namespace: "external-secrets"
```

### Exemplo de ExternalSecret

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: orchestrator-dynamic-secrets
  namespace: neural-hive-orchestration
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: orchestrator-dynamic-secrets
    creationPolicy: Owner
  data:
    - secretKey: POSTGRES_PASSWORD
      remoteRef:
        key: secret/orchestrator-dynamic/postgres
        property: password
    - secretKey: MONGODB_URI
      remoteRef:
        key: secret/orchestrator-dynamic/mongodb
        property: uri
```

## Rotação de Secrets

### Rotação Manual

1. Gerar novas credenciais
2. Atualizar Vault (se estiver usando)
3. Atualizar secret Kubernetes
4. Reiniciar pods afetados

```bash
# 1. Gerar nova senha
NEW_PASSWORD=$(openssl rand -hex 16)

# 2. Atualizar Vault
vault kv put secret/orchestrator-dynamic/postgres password="${NEW_PASSWORD}"

# 3. Atualizar secret Kubernetes
kubectl patch secret orchestrator-dynamic-secrets -n neural-hive-orchestration \
  -p="{\"stringData\":{\"POSTGRES_PASSWORD\":\"${NEW_PASSWORD}\"}}"

# 4. Reiniciar pods
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

### Rotação Automática com External Secrets

O External Secrets Operator sincroniza automaticamente os secrets baseado no `refreshInterval`:

```yaml
spec:
  refreshInterval: 1h  # Verificar atualizações a cada hora
```

### Rotação de Credenciais de Banco de Dados

Para bancos de dados que suportam credenciais dinâmicas:

```bash
# Configurar engine de secrets de banco de dados do Vault
vault secrets enable database

vault write database/config/mongodb \
    plugin_name=mongodb-database-plugin \
    allowed_roles="orchestrator-dynamic" \
    connection_url="mongodb://{{username}}:{{password}}@mongodb-headless:27017/admin"

vault write database/roles/orchestrator-dynamic \
    db_name=mongodb \
    creation_statements='{"db": "orchestrator", "roles": [{"role": "readWrite"}]}' \
    default_ttl="1h" \
    max_ttl="24h"
```

## Troubleshooting

### Problemas Comuns

#### 1. ImagePullBackOff por Falta de Secret de Registry

**Sintoma:** Pods falham com `ImagePullBackOff`

**Solução:**
```bash
# Criar secret de registry
kubectl create secret docker-registry regcred \
  --docker-server=your-registry.com \
  --docker-username=your-user \
  --docker-password=your-password \
  --namespace=neural-hive-orchestration
```

#### 2. Pod CrashLoopBackOff por Falta de Secrets

**Sintoma:** Pod crasha com erros de variáveis de ambiente

**Diagnóstico:**
```bash
# Verificar logs do pod
kubectl logs -n neural-hive-orchestration deployment/orchestrator-dynamic

# Verificar se secret existe
kubectl get secret orchestrator-dynamic-secrets -n neural-hive-orchestration

# Validar chaves do secret
./scripts/validate-phase2-secrets.sh --verbose
```

**Solução:**
```bash
# Recriar secrets
./scripts/create-phase2-secrets.sh --mode static --environment dev
```

#### 3. Conexão Recusada ao Banco de Dados

**Sintoma:** Serviço não consegue conectar ao MongoDB/PostgreSQL

**Diagnóstico:**
```bash
# Decodificar e verificar string de conexão
kubectl get secret orchestrator-dynamic-secrets -n neural-hive-orchestration \
  -o jsonpath='{.data.MONGODB_URI}' | base64 -d

# Testar conectividade a partir de um pod de debug
kubectl run -it --rm debug --image=mongo:6 -n neural-hive-orchestration -- \
  mongosh "mongodb://..." --eval "db.runCommand('ping')"
```

#### 4. Injeção do Vault Agent Não Funcionando

**Sintoma:** Secrets não injetados no modo produção

**Diagnóstico:**
```bash
# Verificar logs do sidecar Vault Agent
kubectl logs -n neural-hive-orchestration deployment/orchestrator-dynamic -c vault-agent

# Verificar anotações
kubectl get deployment orchestrator-dynamic -n neural-hive-orchestration -o yaml | grep -A10 annotations
```

**Solução:**
```bash
# Verificar se role do Vault existe
vault read auth/kubernetes/role/orchestrator-dynamic

# Verificar service account
kubectl get serviceaccount orchestrator-dynamic -n neural-hive-orchestration
```

### Comandos de Validação

```bash
# Validação completa
./scripts/validate-phase2-secrets.sh

# Verificar namespace específico
kubectl get secrets -n neural-hive-orchestration

# Verificar dados do secret
kubectl get secret orchestrator-dynamic-secrets -n neural-hive-orchestration -o yaml

# Testar variáveis de ambiente do pod
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- env | grep -E '^(POSTGRES|MONGODB|REDIS|KAFKA)'
```

### Pod de Debug

Criar um pod de debug para testar conectividade:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: secrets-debug
  namespace: neural-hive-orchestration
spec:
  containers:
    - name: debug
      image: busybox
      command: ["sleep", "3600"]
      envFrom:
        - secretRef:
            name: orchestrator-dynamic-secrets
  restartPolicy: Never
```

```bash
# Aplicar e acessar o pod
kubectl apply -f - <<EOF
# ... spec do pod acima
EOF

kubectl exec -it secrets-debug -n neural-hive-orchestration -- sh
# Dentro do pod: echo $POSTGRES_PASSWORD
```

## Boas Práticas

1. **Nunca commit secrets no Git** - Use `.gitignore` para arquivos de secrets gerados
2. **Use senhas únicas** - Cada serviço deve ter suas próprias credenciais
3. **Rotacione regularmente** - Configure rotação automática para produção
4. **Audite acessos** - Habilite logging de auditoria do Vault para produção
5. **Privilégio mínimo** - Cada serviço deve acessar apenas seus próprios secrets
6. **Valide antes do deploy** - Sempre execute `validate-phase2-secrets.sh` antes de fazer deploy

## Documentação Relacionada

- [Guia de Operações Vault SPIFFE](security/VAULT_SPIFFE_OPERATIONS_GUIDE.md)
- [Troubleshooting Vault SPIFFE](security/VAULT_SPIFFE_TROUBLESHOOTING.md)
- [Status de Implementação da Fase 2](../PHASE2_IMPLEMENTATION_STATUS.md)
- [Guia de Deployment](../DEPLOYMENT_GUIDE.md)
