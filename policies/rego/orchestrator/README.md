# OPA Security Policies - JWT Validation

## Formato JWT Esperado

### Claims Obrigatórios

Todos os JWTs devem conter os seguintes claims:

| Claim | Tipo | Descrição | Exemplo |
|-------|------|-----------|---------|
| `sub` | string | SPIFFE ID do workload | `spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents` |
| `iss` | string | Issuer (SPIRE Server) | `https://spire-server.spire-system.svc.cluster.local` |
| `aud` | string ou array | Audience (serviço destino) | `orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local` |
| `exp` | int | Timestamp de expiração (Unix epoch) | `1700000000` |
| `iat` | int | Timestamp de emissão (Unix epoch) | `1699996400` |
| `tenant_id` | string | ID do tenant | `tenant-123` |
| `roles` | array | Roles do usuário/serviço | `["developer", "admin"]` |

### Exemplo de JWT Válido

```json
{
  "sub": "spiffe://neural-hive.local/ns/neural-hive-execution/sa/worker-agents",
  "iss": "https://spire-server.spire-system.svc.cluster.local",
  "aud": "orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local",
  "exp": 9999999999,
  "iat": 1700000000,
  "tenant_id": "tenant-123",
  "roles": ["developer"]
}
```

### Validações Realizadas

1. **Estrutura**: JWT deve ter 3 partes separadas por `.` (header.payload.signature)
2. **Assinatura**: Verificada usando JWKS do SPIRE Server via `io.jwt.decode_verify()`
3. **Expiração**: `exp` deve ser maior que timestamp atual
4. **Issuer**: `iss` deve corresponder ao configurado (`jwt_issuer`)
5. **Audience**: `aud` deve corresponder ao configurado (`jwt_audience`)
6. **SPIFFE ID**: `sub` deve começar com `spiffe://{trust_domain}/`
7. **Claims Obrigatórios**: `tenant_id` e `roles` devem estar presentes

## Configuração

A validação JWT é configurada via Helm values:

```yaml
config:
  opa:
    security:
      jwt_issuer: "https://spire-server.spire-system.svc.cluster.local"
      jwt_audience: "orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local"
      spiffe_trust_domain: "neural-hive.local"
      spiffe_enabled: true
```

### Configuração JWKS

O OPA é configurado para buscar automaticamente o JWKS do SPIRE Server:

```yaml
# helm-charts/orchestrator-dynamic/values.yaml
opa:
  config:
    services:
      spire-jwks:
        url: https://spire-server.spire-system.svc.cluster.local:8081
    bundles:
      spire-jwks:
        service: spire-jwks
        resource: /keys
        polling:
          min_delay_seconds: 60
          max_delay_seconds: 120
```

## Processo de Verificação

1. **Cliente obtém JWT-SVID** do SPIRE Agent via Workload API
2. **Cliente envia JWT** no header `Authorization: Bearer <jwt>`
3. **Orchestrator extrai JWT** e passa para OPA via `input.context.jwt_token`
4. **OPA valida JWT**:
   - Busca chave pública do JWKS bundle (cache de 60-120s)
   - Verifica assinatura usando `io.jwt.decode_verify()`
   - Valida issuer, audience, expiração
   - Verifica claims obrigatórios (`tenant_id`, `roles`)
5. **OPA retorna decisão** (allow/deny) com violações detalhadas

## Troubleshooting

### JWT Signature Verification Failed

**Causa**: OPA não consegue acessar JWKS do SPIRE Server.

**Solução**:
```bash
# Verificar se OPA consegue acessar SPIRE JWKS
kubectl exec -n neural-hive-orchestration deployment/opa -- \
  curl -k https://spire-server.spire-system.svc.cluster.local:8081/keys

# Verificar logs do OPA
kubectl logs -n neural-hive-orchestration deployment/opa | grep -i jwks
```

### JWT Missing Required Claims

**Causa**: JWT não contém `tenant_id` ou `roles`.

**Solução**: Atualizar SPIRE Server para incluir claims customizados no JWT-SVID.

```bash
# Verificar claims do JWT
echo "<jwt_token>" | cut -d'.' -f2 | base64 -d | jq .
```

### OPA Bundle Load Failure

**Causa**: OPA não consegue carregar bundle JWKS.

**Solução**:
```bash
# Verificar status dos bundles
kubectl exec -n neural-hive-orchestration deployment/opa -- \
  curl http://localhost:8181/v1/status

# Verificar configuração
kubectl get configmap orchestrator-dynamic-opa-config -n neural-hive-orchestration -o yaml
```

## Políticas Disponíveis

| Política | Descrição | Severidade |
|----------|-----------|------------|
| `cross_tenant_access` | Acesso entre tenants não autorizado | critical |
| `missing_authentication` | JWT ausente quando SPIFFE habilitado | critical |
| `invalid_jwt` | JWT com assinatura inválida ou estrutura incorreta | critical |
| `jwt_expired` | JWT expirado | critical |
| `jwt_invalid_issuer` | Issuer não corresponde ao esperado | high |
| `jwt_invalid_audience` | Audience não corresponde ao esperado | high |
| `jwt_invalid_spiffe_id` | SPIFFE ID com trust domain incorreto | critical |
| `jwt_missing_required_claims` | Claims obrigatórios ausentes | critical |
| `insufficient_permissions` | Usuário sem permissão para capability | high |
| `pii_handling_violation` | PII sem classificação confidential | high |
| `tenant_rate_limit_exceeded` | Rate limit do tenant excedido | medium |

## Testes

### Executar Testes Localmente

```bash
# Instalar OPA CLI
curl -L -o opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64
chmod +x opa
sudo mv opa /usr/local/bin/

# Executar todos os testes
cd policies/rego/orchestrator
opa test . -v

# Executar apenas testes de security_constraints
opa test tests/security_constraints_test.rego security_constraints.rego -v

# Validar sintaxe
opa check security_constraints.rego
```

### Testar Política Manualmente

```bash
# Criar input de teste
cat > /tmp/test_input.json << 'EOF'
{
  "resource": {
    "ticket_id": "test-123",
    "tenant_id": "tenant-123",
    "required_capabilities": ["code_generation"]
  },
  "context": {
    "jwt_token": "<your-jwt-here>",
    "user_id": "test@example.com"
  },
  "security": {
    "jwt_issuer": "https://spire-server.spire-system.svc.cluster.local",
    "jwt_audience": "orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local",
    "spiffe_trust_domain": "neural-hive.local",
    "spiffe_enabled": true
  }
}
EOF

# Avaliar política
opa eval -d security_constraints.rego -i /tmp/test_input.json \
  "data.neuralhive.orchestrator.security_constraints.result"
```

## Referências

- [OPA JWT Verification](https://www.openpolicyagent.org/docs/latest/policy-reference/#token-verification)
- [SPIFFE JWT-SVID Specification](https://github.com/spiffe/spiffe/blob/main/standards/JWT-SVID.md)
- [SPIRE JWKS Endpoint](https://spiffe.io/docs/latest/spire-about/spire-concepts/#jwks-endpoint)
- [Neural Hive Security Operations Guide](../../../docs/security-operations-guide.md)
