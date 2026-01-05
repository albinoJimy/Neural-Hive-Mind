# Secrets Management Guide - Neural Hive Mind

## Visão Geral

Este guia documenta as melhores práticas para gestão de secrets em ambientes de produção do Neural Hive Mind. Os valores placeholders `CHANGEME_PRODUCTION_PASSWORD` presentes nos arquivos `values.yaml` dos specialists **NÃO devem ser usados em produção** e existem apenas para facilitar desenvolvimento local.

**⚠️ IMPORTANTE**: Nunca commite senhas reais no repositório Git. Use sempre uma solução de gestão de secrets apropriada para produção.

## Politicas de Seguranca Obrigatorias

O Neural Hive-Mind implementa **validacao automatica em tempo de inicializacao** para garantir configuracoes seguras em producao:

### Validacoes Automaticas

| Servico | Configuracao | Regra | Acao em Violacao |
|---------|--------------|-------|------------------|
| `orchestrator-dynamic` | `VAULT_FAIL_OPEN` | Deve ser `false` em producao | Falha na inicializacao |
| `orchestrator-dynamic` | `REDIS_PASSWORD` | Nao pode ser vazio em producao | Falha na inicializacao |
| `service-registry` | `REDIS_PASSWORD` | Nao pode ser vazio em producao | Falha na inicializacao |

### Ambientes Reconhecidos

As validacoes sao ativadas quando `ENVIRONMENT` esta configurado como:
- `production`
- `prod`

Em ambientes `development`, `dev`, `staging`, as validacoes sao relaxadas para facilitar desenvolvimento local.

### Exemplo de Erro de Validacao

```bash
# Tentativa de iniciar orchestrator-dynamic em producao com vault_fail_open=true
$ ENVIRONMENT=production VAULT_FAIL_OPEN=true python -m src.main

pydantic_core._pydantic_core.ValidationError: 1 validation error for OrchestratorSettings
vault_fail_open
  vault_fail_open=True nao e permitido em ambiente production.
  Configure VAULT_FAIL_OPEN=false ou ENVIRONMENT=development.
  Em producao, o servico deve falhar se Vault estiver indisponivel (fail-closed).
```

### Como Corrigir

**Opcao 1: Configurar corretamente para producao**
```bash
export ENVIRONMENT=production
export VAULT_FAIL_OPEN=false
export REDIS_PASSWORD="$(openssl rand -base64 32)"
```

**Opcao 2: Usar External Secrets Operator (Recomendado)**
```yaml
# k8s/external-secrets/orchestrator-secrets.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: orchestrator-dynamic-secrets
spec:
  secretStoreRef:
    name: aws-secrets-manager
  data:
  - secretKey: redis_password
    remoteRef:
      key: neural-hive/redis-password
```

## Por que Nao Usar Secrets Inline?

1. **Segurança**: Senhas em plain text no Git podem vazar
2. **Auditabilidade**: Difícil rastrear quem acessou/modificou secrets
3. **Rotação**: Rotacionar senhas requer rebuild/redeploy de charts
4. **Compliance**: Viola políticas de segurança corporativas e regulatórias (SOC2, ISO 27001, LGPD)

## Configuração do Flag secrets.create

Todos os Helm charts dos specialists incluem um flag `secrets.create` que controla se o Helm criará ou não o recurso Secret do Kubernetes:

```yaml
# helm-charts/specialist-*/values.yaml
secrets:
  create: true  # Padrão: true (Helm cria o Secret)
  mongodbUri: "mongodb://..."
  neo4jPassword: "..."
  redisPassword: ""
```

**Quando usar `secrets.create=true` (padrão)**:
- ✅ Desenvolvimento local
- ✅ Ambientes de teste sem External Secrets Operator
- ✅ Quando gerenciar secrets manualmente via `kubectl create secret`

**Quando usar `secrets.create=false`**:
- ✅ Ao usar External Secrets Operator
- ✅ Ao usar Sealed Secrets
- ✅ Quando um controller externo gerencia o Secret

⚠️ **IMPORTANTE**: Se `secrets.create=false`, você **DEVE** garantir que o Secret seja criado por outro meio (ExternalSecret, SealedSecret, ou `kubectl create secret`) **ANTES** de fazer deploy do specialist. Caso contrário, os pods ficarão em estado `CreateContainerConfigError`.

## Opções de Gestão de Secrets

### Opção A: External Secrets Operator (Recomendada)

O [External Secrets Operator](https://external-secrets.io/) sincroniza secrets de provedores externos (AWS Secrets Manager, Azure Key Vault, HashiCorp Vault, GCP Secret Manager) para Kubernetes Secrets.

#### Vantagens
- ✅ Integração nativa com cloud providers
- ✅ Rotação automática de secrets
- ✅ Auditoria centralizada
- ✅ Suporta múltiplos backends

#### Instalação

```bash
# Instalar External Secrets Operator via Helm
helm repo add external-secrets https://charts.external-secrets.io
helm repo update

helm install external-secrets \
  external-secrets/external-secrets \
  -n external-secrets-system \
  --create-namespace \
  --set installCRDs=true
```

#### Configuração para AWS Secrets Manager

**1. Criar Secret no AWS Secrets Manager**

```bash
# MongoDB URI
aws secretsmanager create-secret \
  --name neural-hive/mongodb-uri \
  --secret-string "mongodb://root:SECURE_PASSWORD@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin" \
  --region us-west-2

# Neo4j Password
aws secretsmanager create-secret \
  --name neural-hive/neo4j-password \
  --secret-string "SECURE_NEO4J_PASSWORD" \
  --region us-west-2

# JWT Secret (opcional)
aws secretsmanager create-secret \
  --name neural-hive/jwt-secret-key \
  --secret-string "$(openssl rand -base64 64)" \
  --region us-west-2
```

**2. Criar SecretStore**

```yaml
# k8s/external-secrets/secret-store.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-manager
  namespace: neural-hive-specialists
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-west-2
      auth:
        # Usar IAM Role for Service Account (IRSA) - recomendado
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
```

**3. Criar ExternalSecret**

```yaml
# k8s/external-secrets/external-secret-mongodb.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: specialist-mongodb-secret
  namespace: neural-hive-specialists
spec:
  refreshInterval: 1h  # Sincronizar a cada 1 hora
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: specialist-business-secret  # Nome do K8s Secret criado
    creationPolicy: Owner
  data:
  - secretKey: mongodb_uri
    remoteRef:
      key: neural-hive/mongodb-uri
  - secretKey: neo4j_password
    remoteRef:
      key: neural-hive/neo4j-password
  - secretKey: jwt_secret_key
    remoteRef:
      key: neural-hive/jwt-secret-key
```

**4. Aplicar no Cluster**

```bash
kubectl apply -f k8s/external-secrets/secret-store.yaml
kubectl apply -f k8s/external-secrets/external-secret-mongodb.yaml

# Verificar que secret foi criado
kubectl get secret specialist-business-secret -n neural-hive-specialists -o yaml
```

**5. Desabilitar Criação de Secret pelo Helm**

Para evitar conflitos entre o Helm Chart e o External Secrets Operator, desabilite a criação do Secret nativo pelo Helm:

```yaml
# helm-charts/specialist-business/values.yaml
secrets:
  # Desabilitar criação de Secret pelo Helm quando usando External Secrets Operator
  create: false
  # Valores serão sobrescritos pelo ExternalSecret
  # Manter placeholders para documentação
  mongodbUri: ""  # Gerenciado por ExternalSecret
  neo4jPassword: ""  # Gerenciado por ExternalSecret
  jwtSecretKey: ""  # Gerenciado por ExternalSecret
```

**6. Deploy do Helm Chart**

```bash
# Deploy com secrets.create=false para evitar conflitos
helm upgrade --install specialist-business \
  ./helm-charts/specialist-business \
  -n neural-hive-specialists \
  --set secrets.create=false
```

⚠️ **IMPORTANTE**: Quando `secrets.create=false`, o Helm Chart **NÃO** criará o recurso Secret. O ExternalSecret Operator será o único responsável por gerenciar o Secret. Certifique-se de que o ExternalSecret está criando o Secret antes de fazer deploy do specialist.

#### Configuração para Azure Key Vault

```yaml
# k8s/external-secrets/secret-store-azure.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: azure-key-vault
  namespace: neural-hive-specialists
spec:
  provider:
    azurekv:
      vaultUrl: "https://neural-hive-vault.vault.azure.net"
      authType: ManagedIdentity
      identityId: "/subscriptions/SUBSCRIPTION_ID/resourcegroups/RG_NAME/providers/Microsoft.ManagedIdentity/userAssignedIdentities/IDENTITY_NAME"
```

#### Configuração para HashiCorp Vault

```yaml
# k8s/external-secrets/secret-store-vault.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: hashicorp-vault
  namespace: neural-hive-specialists
spec:
  provider:
    vault:
      server: "https://vault.example.com"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "neural-hive-role"
```

### Opção B: Sealed Secrets (Para GitOps)

[Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) permite commitar secrets criptografados no Git.

#### Instalação

```bash
# Instalar Sealed Secrets Controller
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm install sealed-secrets sealed-secrets/sealed-secrets -n kube-system

# Instalar kubeseal CLI
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/kubeseal-0.24.0-linux-amd64.tar.gz
tar -xvzf kubeseal-0.24.0-linux-amd64.tar.gz
sudo install -m 755 kubeseal /usr/local/bin/kubeseal
```

#### Uso

```bash
# Criar secret normal
kubectl create secret generic specialist-business-secret \
  --from-literal=mongodb_uri="mongodb://root:SECURE_PASSWORD@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin" \
  --from-literal=neo4j_password="SECURE_NEO4J_PASSWORD" \
  --dry-run=client -o yaml > secret.yaml

# Criptografar com kubeseal
kubeseal -f secret.yaml -w sealed-secret.yaml \
  --controller-namespace kube-system \
  --controller-name sealed-secrets

# Commitar sealed-secret.yaml no Git (SEGURO)
git add sealed-secret.yaml
git commit -m "chore: add sealed secrets for production"

# Aplicar no cluster
kubectl apply -f sealed-secret.yaml -n neural-hive-specialists

# Controller automaticamente decripta para Secret nativo
kubectl get secret specialist-business-secret -n neural-hive-specialists

# Deploy do Helm Chart com secrets.create=false
helm upgrade --install specialist-business \
  ./helm-charts/specialist-business \
  -n neural-hive-specialists \
  --set secrets.create=false
```

⚠️ **Nota**: Quando usar Sealed Secrets, defina `secrets.create=false` no `values.yaml` para evitar que o Helm Chart crie um Secret conflitante. O SealedSecret Controller será responsável por criar e gerenciar o Secret.

### Opção C: kubectl create secret (Apenas Desenvolvimento Local)

Para ambientes de desenvolvimento local (não produção):

```bash
kubectl create secret generic specialist-business-secret \
  --from-literal=mongodb_uri="mongodb://root:local-dev-password@mongodb.mongodb-cluster.svc.cluster.local:27017/neural_hive?authSource=admin" \
  --from-literal=neo4j_password="local-dev-password" \
  --from-literal=jwt_secret_key="local-dev-jwt-key-at-least-32-chars" \
  -n neural-hive-specialists
```

⚠️ **Não use esta opção em produção!** Secrets criados via kubectl não são auditados, versionados, ou rastreáveis.

## Secrets Necessários por Specialist

Cada specialist requer os seguintes secrets:

| Secret Key         | Descrição                                          | Obrigatório | Exemplo                                                                 |
|--------------------|----------------------------------------------------|-------------|-------------------------------------------------------------------------|
| `mongodb_uri`      | URI completa do MongoDB com credenciais            | ✅ Sim       | `mongodb://root:PASSWORD@mongodb.svc.cluster.local:27017/neural_hive?authSource=admin` |
| `neo4j_password`   | Senha do usuário Neo4j                             | ✅ Sim       | `secure-neo4j-password-here`                                            |
| `redis_password`   | Senha do Redis Cluster (se habilitado AUTH)       | ⚠️ Opcional  | `secure-redis-password-here`                                            |
| `jwt_secret_key`   | Chave secreta para assinatura JWT (min 32 chars)  | ⚠️ Opcional* | `base64-encoded-secret-key-min-32-chars`                                |

**\*Opcional**: JWT é opcional se `config.enableJwtAuth=false` no `values.yaml`.

## Rotação de Secrets

### Com External Secrets Operator

1. **Atualizar secret no provedor externo** (AWS Secrets Manager, Azure Key Vault, etc.)

   ```bash
   # AWS Secrets Manager
   aws secretsmanager update-secret \
     --secret-id neural-hive/mongodb-uri \
     --secret-string "mongodb://root:NEW_PASSWORD@mongodb.svc.cluster.local:27017/neural_hive?authSource=admin"
   ```

2. **Aguardar sincronização automática** (definido por `refreshInterval` no ExternalSecret, padrão 1h)

3. **Restart dos pods** (para carregar novo secret)

   ```bash
   kubectl rollout restart deployment specialist-business -n neural-hive-specialists
   kubectl rollout restart deployment specialist-technical -n neural-hive-specialists
   kubectl rollout restart deployment specialist-behavior -n neural-hive-specialists
   kubectl rollout restart deployment specialist-evolution -n neural-hive-specialists
   kubectl rollout restart deployment specialist-architecture -n neural-hive-specialists
   ```

### Com Sealed Secrets

1. **Criar novo sealed secret** com nova senha
2. **Aplicar sealed secret** (sobrescreve o anterior)
3. **Restart dos pods**

### Rotação Zero-Downtime

Para rotação sem downtime, use múltiplas credenciais simultâneas:

1. Criar nova credencial no MongoDB/Neo4j **sem deletar a antiga**
2. Atualizar secret com nova credencial
3. Restart gradual dos pods (graças ao `RollingUpdate`)
4. Após confirmação, deletar credencial antiga

## Troubleshooting

### Erro: "Authentication failed"

**Sintoma**: Pods falham com erro `MongoServerError: Authentication failed` ou `Neo4jAuthenticationError`

**Diagnóstico**:

```bash
# Verificar se secret existe
kubectl get secret specialist-business-secret -n neural-hive-specialists

# Verificar conteúdo do secret (base64 encoded)
kubectl get secret specialist-business-secret -n neural-hive-specialists -o jsonpath='{.data.mongodb_uri}' | base64 -d
```

**Solução**:
- Verificar que senha no secret corresponde à senha real do MongoDB/Neo4j
- Verificar que URI está correta (incluindo `authSource=admin` para MongoDB)

### Erro: "Secret not found"

**Sintoma**: Pods ficam em `CreateContainerConfigError` com erro `secret "specialist-business-secret" not found`

**Diagnóstico**:

```bash
# Listar secrets no namespace
kubectl get secrets -n neural-hive-specialists
```

**Solução**:
- Criar secret manualmente via kubectl (desenvolvimento) ou
- Verificar que ExternalSecret está criando o secret corretamente:

  ```bash
  kubectl get externalsecret specialist-mongodb-secret -n neural-hive-specialists
  kubectl describe externalsecret specialist-mongodb-secret -n neural-hive-specialists
  ```

### Erro: "Secret key not found"

**Sintoma**: Pods falham com erro `couldn't find key mongodb_uri in Secret`

**Solução**: Verificar que chaves no secret correspondem às esperadas pelo deployment:
- `mongodb_uri` (não `mongodbUri` ou `MONGODB_URI`)
- `neo4j_password` (não `neo4jPassword`)
- `jwt_secret_key` (não `jwtSecretKey`)

```bash
# Verificar chaves do secret
kubectl get secret specialist-business-secret -n neural-hive-specialists -o jsonpath='{.data}' | jq 'keys'
```

## Checklist de Seguranca para Producao

Antes de fazer deploy em producao, verifique:

- [ ] **Validacoes automaticas passando**: Servicos iniciam sem erros de validacao de configuracao
- [ ] `VAULT_FAIL_OPEN=false` em orchestrator-dynamic (fail-closed em producao)
- [ ] `REDIS_PASSWORD` configurado em orchestrator-dynamic e service-registry
- [ ] `ENVIRONMENT=production` configurado corretamente em todos os servicos
- [ ] Secrets sao gerenciados via External Secrets Operator ou Sealed Secrets (nao inline no values.yaml)
- [ ] ✅ Flag `secrets.create=false` está configurado nos values.yaml quando usar External Secrets ou Sealed Secrets
- [ ] ✅ ExternalSecret ou SealedSecret está criando o Secret **ANTES** do deploy do specialist
- [ ] ✅ Senhas seguem política de complexidade da organização (min 16 chars, letras, números, símbolos)
- [ ] ✅ JWT secret key tem no mínimo 32 caracteres
- [ ] ✅ Secrets no Git estão criptografados (Sealed Secrets) ou não commitados (External Secrets)
- [ ] ✅ RBAC está configurado para limitar acesso aos secrets (apenas ServiceAccount do specialist)
- [ ] ✅ Auditoria de acesso aos secrets está habilitada (AWS CloudTrail, Azure Monitor, etc.)
- [ ] ✅ Rotação de secrets está agendada (ex: a cada 90 dias)
- [ ] ✅ Backup de secrets está configurado (importante para disaster recovery)
- [ ] ✅ `readOnlyRootFilesystem: false` está justificado (necessário para `/app/mlruns` volume)
- [ ] ✅ Network policies restringem tráfego de egress dos pods (evitar exfiltração de secrets)

## Referências

- [External Secrets Operator Documentation](https://external-secrets.io/)
- [Sealed Secrets GitHub](https://github.com/bitnami-labs/sealed-secrets)
- [Kubernetes Secrets Best Practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [Azure Key Vault Best Practices](https://learn.microsoft.com/en-us/azure/key-vault/general/best-practices)
- [HashiCorp Vault Production Hardening](https://developer.hashicorp.com/vault/tutorials/operations/production-hardening)

## Suporte

Para dúvidas ou problemas com secrets management:
1. Consultar logs dos pods: `kubectl logs <pod-name> -n neural-hive-specialists`
2. Consultar eventos do namespace: `kubectl get events -n neural-hive-specialists --sort-by='.lastTimestamp'`
3. Verificar documentação do provedor de secrets (AWS, Azure, Vault)
4. Abrir issue no repositório com logs e configuração (sem incluir senhas!)
