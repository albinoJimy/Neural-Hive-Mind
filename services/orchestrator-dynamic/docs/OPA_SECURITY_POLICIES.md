# OPA Security Policies - Neural Hive-Mind Orchestrator

## Visão Geral

O Orchestrator Dynamic implementa **4 políticas OPA** para governança e compliance:

1. **Resource Limits** - Limites de recursos e capacidades
2. **SLA Enforcement** - Enforcement de SLAs e QoS
3. **Feature Flags** - Controle dinâmico de features
4. **Security Constraints** - Segurança, isolamento e compliance

## Security Constraints Policy

### Domínios de Segurança

#### 1. Tenant Isolation
Previne acesso cross-tenant a dados e recursos.

**Regras:**
- `cross_tenant_access`: Valida que tenant_id está na whitelist
- `tenant_data_leakage`: Previne vazamento de dados entre tenants

**Exemplo de violação:**
```json
{
  "policy": "security_constraints",
  "rule": "cross_tenant_access",
  "severity": "critical",
  "msg": "Tenant tenant-unauthorized não está na whitelist"
}
```

#### 2. Authentication
Valida autenticação via SPIFFE JWT-SVID ou OAuth2.

**Regras:**
- `missing_authentication`: JWT token ausente quando SPIFFE habilitado
- `invalid_jwt`: JWT com estrutura inválida
- `expired_token`: Token expirado

**Configuração:**
```yaml
security:
  spiffe_enabled: true
  trust_domain: neural-hive.local
```

#### 3. Authorization (RBAC)
Enforce controle de acesso baseado em roles.

**Roles disponíveis:**
- `admin`: Acesso total a todas as capabilities
- `developer`: code_generation, testing, validation
- `viewer`: Apenas leitura

**Exemplo de configuração:**
```yaml
rbac_roles:
  user@example.com:
    - developer
  admin@example.com:
    - admin
```

#### 4. Data Governance
Compliance com GDPR, LGPD, HIPAA.

**Regras:**
- `pii_handling_violation`: Dados com PII devem ter classificação "confidential"
- `data_residency_violation`: Dados devem estar em regiões permitidas
- `retention_policy_violation`: Retenção de dados conforme política

**Classificações de dados:**
- `public`: Dados públicos
- `internal`: Dados internos
- `confidential`: Dados confidenciais (PII, PHI)
- `restricted`: Dados restritos (segredos, credenciais)

#### 5. Rate Limiting
Previne abuse e garante fair usage.

**Regras:**
- `tenant_rate_limit_exceeded`: Tenant excedeu limite configurado
- `global_rate_limit_exceeded`: Sistema excedeu limite global

**Configuração:**
```yaml
tenant_rate_limits:
  tenant-premium: 200
  tenant-standard: 100
global_rate_limit: 1000
default_tenant_rate_limit: 100
```

## Testes

### Testes Unitários
```bash
# Executar todos os testes
opa test policies/rego/orchestrator/ -v

# Executar teste específico
opa test policies/rego/orchestrator/tests/security_constraints_test.rego -v

# Com coverage
opa test policies/rego/orchestrator/ --coverage --format=json
```

### Testes E2E
```bash
# Executar testes E2E de segurança
pytest tests/e2e/test_04_opa_policies.py::test_opa_security_tenant_isolation -v
pytest tests/e2e/test_04_opa_policies.py::test_opa_security_missing_authentication -v
pytest tests/e2e/test_04_opa_policies.py::test_opa_security_insufficient_permissions -v
```

### Script de Validação
```bash
# Validar todas as políticas
./scripts/validation/validate_opa_policies.sh
```

## Métricas

### Prometheus Metrics

| Métrica | Tipo | Descrição |
|---------|------|-----------|
| `orchestration_security_violations_total` | Counter | Total de violações de segurança |
| `orchestration_security_authentication_failures_total` | Counter | Falhas de autenticação |
| `orchestration_security_authorization_denials_total` | Counter | Negações de autorização |
| `orchestration_security_tenant_isolation_violations_total` | Counter | Violações de isolamento |
| `orchestration_security_data_governance_violations_total` | Counter | Violações de governança |
| `orchestration_security_rate_limit_exceeded_total` | Counter | Rate limits excedidos |

### Grafana Dashboard

Dashboard: **Orchestrator OPA Policy Enforcement & Security Compliance**

**Painéis de segurança:**
1. Security Violations by Type
2. Authentication Failures
3. Authorization Denials by Tenant
4. Tenant Isolation Violations (com alertas)
5. Data Governance Compliance (gauge)
6. Rate Limit Exceeded by Tenant

## Troubleshooting

### Violação de Tenant Isolation
```bash
# Verificar logs
kubectl logs -n neural-hive-orchestration deployment/orchestrator-dynamic | grep "cross_tenant_access"

# Verificar métricas
curl -s http://prometheus:9090/api/v1/query?query=orchestration_security_tenant_isolation_violations_total
```

### Falhas de Autenticação
```bash
# Verificar se SPIFFE está habilitado
kubectl get configmap orchestrator-config -n neural-hive-orchestration -o yaml | grep spiffe_enabled

# Verificar logs de JWT
kubectl logs -n neural-hive-orchestration deployment/orchestrator-dynamic | grep "jwt_token"
```

### Rate Limiting
```bash
# Verificar rate limits configurados
kubectl get configmap orchestrator-config -n neural-hive-orchestration -o yaml | grep rate_limit

# Verificar Redis para contadores
kubectl exec -n neural-hive-orchestration redis-0 -- redis-cli GET "rate_limit:tenant-123"
```

## Referências

- [OPA Documentation](https://www.openpolicyagent.org/docs/latest/)
- [Rego Language Reference](https://www.openpolicyagent.org/docs/latest/policy-language/)
- [SPIFFE/SPIRE Integration](../../../docs/security/SPIFFE_INTEGRATION.md)
- [Multi-Tenancy Guide](../../../docs/architecture/MULTI_TENANCY.md)
