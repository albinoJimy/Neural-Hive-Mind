# Vault Policies - Neural Hive-Mind

## Visão Geral

Este documento contém templates de políticas HCL para cada serviço do Neural Hive-Mind, exemplos de comandos Vault CLI, e procedimentos de testing.

## Estrutura de Políticas

Cada serviço possui:
1. **KV Secrets**: Acesso read-only a `secret/data/<service>/*`
2. **Database Credentials**: Acesso read a `database/creds/<service>` para credenciais dinâmicas
3. **PKI**: Acesso create/update a `pki/issue/neural-hive-services` para emissão de certificados
4. **Transit** (opcional): Acesso encrypt/decrypt para serviços que precisam de criptografia

## Templates de Políticas

### 1. orchestrator-dynamic-policy.hcl

```hcl
# KV Secrets - Read-only
path "secret/data/orchestrator-dynamic/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/orchestrator-dynamic/*" {
  capabilities = ["list"]
}

# Database Credentials - Dynamic
path "database/creds/orchestrator-dynamic" {
  capabilities = ["read"]
}

# PKI - Certificate Issuance
path "pki/issue/neural-hive-services" {
  capabilities = ["create", "update"]
}

# Transit - Encryption (opcional)
path "transit/encrypt/orchestrator-dynamic" {
  capabilities = ["update"]
}

path "transit/decrypt/orchestrator-dynamic" {
  capabilities = ["update"]
}
```

### 2. worker-agents-policy.hcl

```hcl
# KV Secrets - Read-only
path "secret/data/worker-agents/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/worker-agents/*" {
  capabilities = ["list"]
}

# Database Credentials - Dynamic
path "database/creds/worker-agents" {
  capabilities = ["read"]
}

# PKI - Certificate Issuance
path "pki/issue/neural-hive-services" {
  capabilities = ["create", "update"]
}

# Execution Credentials - Dynamic (para tasks)
path "secret/data/execution/*" {
  capabilities = ["read"]
}
```

### 3. service-registry-policy.hcl

```hcl
# KV Secrets - Read-only
path "secret/data/service-registry/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/service-registry/*" {
  capabilities = ["list"]
}

# Database Credentials - Dynamic
path "database/creds/service-registry" {
  capabilities = ["read"]
}

# PKI - Certificate Issuance
path "pki/issue/neural-hive-services" {
  capabilities = ["create", "update"]
}
```

## Comandos Vault CLI

### Criar Políticas

```bash
# Orchestrator Dynamic
vault policy write orchestrator-dynamic orchestrator-dynamic-policy.hcl

# Worker Agents
vault policy write worker-agents worker-agents-policy.hcl

# Service Registry
vault policy write service-registry service-registry-policy.hcl
```

### Listar Políticas

```bash
vault policy list
```

### Ler Política

```bash
vault policy read orchestrator-dynamic
```

### Atualizar Política

```bash
vault policy write orchestrator-dynamic orchestrator-dynamic-policy-v2.hcl
```

### Deletar Política

```bash
vault policy delete orchestrator-dynamic
```

## Configuração de Roles Kubernetes

### Criar Role para Orchestrator

```bash
vault write auth/kubernetes/role/orchestrator-dynamic \
  bound_service_account_names=orchestrator-dynamic \
  bound_service_account_namespaces=neural-hive-orchestration \
  policies=orchestrator-dynamic \
  ttl=1h
```

### Criar Role para Worker Agents

```bash
vault write auth/kubernetes/role/worker-agents \
  bound_service_account_names=worker-agents \
  bound_service_account_namespaces=neural-hive-execution \
  policies=worker-agents \
  ttl=1h
```

### Criar Role para Service Registry

```bash
vault write auth/kubernetes/role/service-registry \
  bound_service_account_names=service-registry \
  bound_service_account_namespaces=neural-hive-registry \
  policies=service-registry \
  ttl=1h
```

## Testing de Políticas

### 1. Criar Token de Teste

```bash
# Token com policy orchestrator-dynamic
vault token create -policy=orchestrator-dynamic -ttl=1h

# Salvar token
export TEST_TOKEN=<token-gerado>
```

### 2. Testar Acesso a KV Secrets

```bash
# Deve funcionar (read)
VAULT_TOKEN=$TEST_TOKEN vault kv get secret/orchestrator-dynamic/mongodb

# Deve falhar (write não permitido)
VAULT_TOKEN=$TEST_TOKEN vault kv put secret/orchestrator-dynamic/test key=value
```

### 3. Testar Acesso a Database Credentials

```bash
# Deve funcionar
VAULT_TOKEN=$TEST_TOKEN vault read database/creds/orchestrator-dynamic
```

### 4. Testar Emissão de Certificado PKI

```bash
# Deve funcionar
VAULT_TOKEN=$TEST_TOKEN vault write pki/issue/neural-hive-services \
  common_name=orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local \
  ttl=24h
```

### 5. Testar Acesso Negado

```bash
# Deve falhar (acesso a outro serviço)
VAULT_TOKEN=$TEST_TOKEN vault kv get secret/worker-agents/config
```

## Best Practices

### 1. Princípio do Menor Privilégio
- Cada serviço deve ter acesso apenas aos secrets necessários
- Usar `bound_service_account_names` e `bound_service_account_namespaces` para restringir roles
- TTL curto para tokens (1h recomendado)

### 2. Rotação de Secrets
- Usar Database Secrets Engine para credenciais dinâmicas (rotação automática)
- Configurar `max_ttl` para forçar renovação periódica
- Implementar graceful rotation nos serviços (aceitar credenciais antigas por período de transição)

### 3. Auditoria
- Habilitar audit device para rastrear acessos:
  ```bash
  vault audit enable file file_path=/vault/logs/audit.log
  ```
- Monitorar logs de audit para acessos suspeitos
- Alertar em caso de falhas de autenticação repetidas

### 4. Segregação de Ambientes
- Usar namespaces Vault diferentes para dev/staging/prod
- Políticas separadas por ambiente
- Roles Kubernetes com `bound_service_account_namespaces` específicos

## Troubleshooting

### Erro: "permission denied"

1. Verificar se policy está associada ao role:
   ```bash
   vault read auth/kubernetes/role/orchestrator-dynamic
   ```

2. Verificar se ServiceAccount está correto:
   ```bash
   kubectl get sa orchestrator-dynamic -n neural-hive-orchestration
   ```

3. Testar login manual:
   ```bash
   JWT=$(kubectl exec -n neural-hive-orchestration <pod> -- cat /var/run/secrets/kubernetes.io/serviceaccount/token)
   vault write auth/kubernetes/login role=orchestrator-dynamic jwt=$JWT
   ```

### Erro: "invalid JWT"

1. Verificar se Kubernetes auth está configurado:
   ```bash
   vault read auth/kubernetes/config
   ```

2. Verificar se token reviewer JWT está válido:
   ```bash
   vault write auth/kubernetes/config \
     kubernetes_host=https://kubernetes.default.svc.cluster.local:443 \
     kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
   ```

## Referências

- [Vault Policies Documentation](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [Kubernetes Auth Method](https://developer.hashicorp.com/vault/docs/auth/kubernetes)
- [Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [PKI Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/pki)
