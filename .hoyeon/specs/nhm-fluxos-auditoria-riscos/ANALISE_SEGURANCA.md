# Análise de Hardening de Segurança - Neural Hive-Mind

**Data:** 2026-04-27
**Autor:** Task T10 Worker Agent
**Espec:** nhm-fluxos-auditoria-riscos
**Requisitos Cobertos:** R-T8.1, R-T8.2, R-T8.3, R-B6.1

---

## Sumário Executivo

Esta análise avaliou a postura de segurança do Neural Hive-Mind (NHM) nas seguintes áreas:
1. **Enforcement de mTLS** entre serviços via Istio service mesh
2. **Secrets Management** via HashiCorp Vault
3. **Network Policies** para controle de ingress/egress

**Status Geral:** ARQUITETURA DEFINIDA, IMPLEMENTAÇÃO PARCIAL

| Componente | Status | Prioridade |
|------------|--------|------------|
| mTLS Enforcement | PERMISSIVE → STRICT transition | ALTA |
| Secrets Management | Implementado com Vault | MÉDIA |
| Network Policies | Deny-all definido, cobertura parcial | ALTA |

---

## 1. Análise de mTLS Enforcement (R-T8.1)

### 1.1 Configuração Atual

**Given:** Istio service mesh instalado com PeerAuthentication policies

**Current State:**
- **Modo atual:** `PERMISSIVE` (aceita plaintext e mTLS)
- **Target:** `STRICT` (apenas mTLS permitido)
- **Mecanismo de enforcement:** OPA Gatekeeper com ConstraintTemplate `NeuralHiveMTLSRequired`

**Evidências:**
```yaml
# policies/constraints/enforce-mtls-strict.yaml
enforcementAction: warn  # Começa com warn, transição para enforce após 7 dias
autoTransition:
  enabled: true
  afterDays: 7
```

```yaml
# environments/prod/helm-values/istio-values.yaml
mtls:
  auto: true  # Auto mTLS enabled
```

**Gap Identificado:**
- Teste `test_istio_mesh_policy_permissive()` confirma modo PERMISSIVE
- Transição WARN → ENFORCE não está completa
- Namespaces sem label `neural-hive.io/secured: "true"` não são cobertos

### 1.2 SPIFFE/SPIRE Integration

**Status:** IMPLEMENTADO COM TESTES

**Componentes:**
- `libraries/security/neural_hive_security/spiffe_manager.py`
- Workload API socket: `/run/spire/sockets/agent.sock`
- Trust domain: `neural-hive.local`

**Funcionalidades:**
- X.509-SVID e JWT-SVID fetch
- Auto-refresh antes de expiração (threshold: 80% TTL)
- Integration com Vault para JWT auth

**Testes E2E:**
- `test_flow_c_mtls_e2e.py` - Fluxo C completo com mTLS
- `test_spiffe_mtls_handshake.py` - Handshake validation
- `test_vault_spiffe_integration_full.py` - Vault + SPIFFE integration

**Gap:**
- Feature flag `ENABLE_JWT_VERIFICATION` default `false`
- Verificação JWT não está ativa por padrão

### 1.3 Gaps de Segurança mTLS

| ID | Descrição | Risco | Mitigação |
|----|-----------|-------|------------|
| MTLS-001 | Modo PERMISSIVE em produção | ALTO | Transição para STRICT |
| MTLS-002 | Namespaces sem label secured | MÉDIO | Aplicar label globalmente |
| MTLS-003 | JWT verification desabilitado | MÉDIO | Ativar por padrão |
| MTLS-004 | Falta monitoring de mTLS success rate | BAIXO | Métricas Prometheus |

---

## 2. Análise de Secrets Management (R-T8.2)

### 2.1 Vault Integration

**Given:** HashiCorp Vault para secrets management

**Status:** IMPLEMENTADO

**Biblioteca:** `libraries/security/neural_hive_security/vault_client.py`

**Features:**
- Multiple auth methods: Kubernetes, JWT, AppRole
- KV v2 secrets engine
- Dynamic database credentials
- PKI certificate issuance
- Automatic token renewal

**Configuração:**
```python
class VaultConfig(BaseSettings):
    address: str = "http://vault.vault.svc.cluster.local:8200"
    auth_method: AuthMethod = AuthMethod.KUBERNETES
    token_ttl_seconds: int = 3600
    token_renew_threshold: float = 0.8
    fail_open: bool = False  # Fail-closed por padrão
```

### 2.2 Credential Rotation

**Status:** IMPLEMENTADO COM TESTES

**Credenciais geridas:**
- PostgreSQL (dynamic via Vault database secrets engine)
- MongoDB (via KV v2)
- Kafka (via KV v2)

**Mecanismo de rotação:**
- Threshold-based: rotação quando 80% do TTL consumido
- Auto-renewal task em background
- Fallback para credenciais estáticas se Vault indisponível (configurável via `vault_fail_open`)

**Testes de rotação:**
- `test_vault_postgres_rotation.py` - 7 testes
- `test_vault_kafka_rotation.py` - 10 testes
- `test_vault_mongodb_rotation.py` - MongoDB rotation

**Exemplo de teste:**
```python
async def test_postgres_credentials_renewal_at_threshold():
    # Threshold 80%: rotação quando TTL < 20%
    vault_integration._postgres_credentials_expiry = datetime.now() + timedelta(seconds=19)
    await vault_integration._renew_postgres_credentials_if_needed()
    assert vault_integration._postgres_credentials["username"] == "user2"
```

### 2.3 Gaps de Secrets Management

| ID | Descrição | Risco | Mitigação |
|----|-----------|-------|------------|
| SEC-001 | Vault address HTTP (não HTTPS) | ALTO | Migrar para HTTPS |
| SEC-002 | Sem vault_audit_log configurado | MÉDIO | Ativar audit logging |
| SEC-003 | Credenciais estáticas em fallback | MÉDIO | Eliminar fallback em prod |
| SEC-004 | TTL fixo de 1 hora | BAIXO | Implementar TTL dinâmico |

---

## 3. Análise de Network Policies (R-T8.3)

### 3.1 Configuração Atual

**Given:** Network policies Kubernetes para isolamento de rede

**Status:** DEFINIDO, COBERTURA PARCIAL

**Arquivos:**
- `k8s/bootstrap/network-policies.yaml` - Policies globais
- `infrastructure/kubernetes/experiments/networkpolicy.yaml` - Isolamento de experimentos
- `helm-charts/execution-ticket-service/templates/networkpolicy.yaml` - Template Helm

**Abordagem:** Zero Trust - Deny all por padrão

### 3.2 Policies Implementadas

**Namespaces cobertos:**
- `neural-hive-cognition`
- `neural-hive-orchestration`
- `neural-hive-execution`
- `neural-hive-observability`
- `nhm-experiments`
- Security namespaces: `cosign-system`, `gatekeeper-system`, `cert-manager`

**Pattern default-deny:**
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: neural-hive-cognition
spec:
  podSelector: {}
  policyTypes:
  - Ingress
```

**Egress rules específicas:**
- DNS (porta 53 UDP/TCP para kube-system)
- Istio control plane (ports 15010, 15011, 15012)
- Observability scraping (Prometheus)

### 3.3 Gaps de Network Policies

| ID | Descrição | Risco | Mitigação |
|----|-----------|-------|------------|
| NET-001 | Egress para internet sem restrição | ALTO | Whitelist de endpoints |
| NET-002 | Sem política de deny-all egress | MÉDIO | Implementar egress deny-all |
| NET-003 | Portas de serviço não explicitamente listadas | BAIXO | Restringir a ports específicos |
| NET-004 | Falta monitoring de NetworkPolicy enforcement | BAIXO | Métricas de drops |

**Exemplo de gap crítico:**
```yaml
# experiments-allow-internet permite HTTPS para qualquer destino
egress:
  - to:
    - namespaceSelector: {}  # Qualquer namespace
    ports:
    - protocol: TCP
      port: 443  # HTTPS apenas
```

### 3.4 Ingress/Egress Restrictions

**Ingress:**
- Default-deny implementado corretamente
- Apenas namespaces específicos podem comunicar
- Istio ingress gateway permitido

**Egress:**
- DNS sempre permitido
- Istio control plane permitido
- Observability scraping permitido
- **GAP:** Egress para serviços externos (Kafka externo, APIs) não está restrito

---

## 4. Security Hardening Gaps Consolidados

### 4.1 Gaps por Prioridade

**ALTA Prioridade (Impacto ALTO × Probabilidade ALTA):**
1. **MTLS-001:** Transição PERMISSIVE → STRICT em produção
2. **SEC-001:** Migrar Vault de HTTP para HTTPS
3. **NET-001:** Restringir egress para internet

**MÉDIA Prioridade:**
4. **MTLS-003:** Ativar JWT verification por padrão
5. **SEC-002:** Ativar Vault audit logging
6. **SEC-003:** Eliminar fallback para credenciais estáticas
7. **NET-002:** Implementar egress deny-all global

**BAIXA Prioridade:**
8. **MTLS-004:** Monitoring de mTLS success rate
9. **SEC-004:** TTL dinâmico para Vault tokens
10. **NET-003/004:** Refinamento de ports e métricas

### 4.2 Matriz de Risco

| ID | Componente | Risco | Impacto | Probabilidade | Score | Prioridade |
|----|------------|-------|---------|---------------|-------|------------|
| MTLS-001 | mTLS mode | Plaintext entre serviços | ALTO | ALTO | 9 | 1 |
| SEC-001 | Vault TLS | Segredos em trânsito plaintext | ALTO | MÉDIO | 6 | 2 |
| NET-001 | Internet egress | Data exfiltration | ALTO | BAIXO | 3 | 3 |
| MTLS-003 | JWT verification | Spoofing de identidade | MÉDIO | MÉDIO | 4 | 4 |
| SEC-002 | Vault audit | Falta de forensic trail | MÉDIO | BAIXO | 2 | 5 |

---

## 5. Recomendações de Mitigação

### 5.1 Plano de Ação Imediato (Sprint 1)

**Ticket SEC-001-001: Migrar Vault para HTTPS**
```yaml
Passos:
1. Configurar Vault com TLS terminado no load balancer
2. Atualizar vault_client.py para default https://
3. Configurar ca_cert_path para verificação
4. Testar em staging antes de produção
```

**Ticket MTLS-001-001: Transição para STRICT mode**
```yaml
Passos:
1. Verificar todos os serviços têm sidecar Istio
2. Aplicar label neural-hive.io/secured="true" globalmente
3. Mudar enforcementAction para enforce
4. Monitorar métricas de connection errors
```

### 5.2 Plano de Curto Prazo (Sprint 2-3)

**Ticket NET-001-001: Restringir egress para internet**
```yaml
Passos:
1. Catalogar todos os egress externos necessários
2. Criar NetworkPolicy com whitelist de IPs/domínios
3. Implementar proxy centralizado para requisições HTTP
4. Ativar logging de egress attempts
```

**Ticket MTLS-003-001: Ativar JWT verification**
```yaml
Passos:
1. Testar ENABLE_JWT_VERIFICATION=true em staging
2. Validar performance impact
3. Ativar por padrão em produção
4. Implementar métricas de verification failures
```

### 5.3 Plano de Longo Prazo (Sprint 4+)

**Ticket SEC-002-001: Vault audit logging**
- Implementar audit device no Vault
- Integrar com SIEM (Splunk/Elastic)
- Criar alertas para eventos suspeitos

**Ticket NET-002-001: Egress deny-all global**
- Implementar CNI plugin com egress filtering (Cilium)
- Criar política de allow-list para domínios externos
- Implementar rate limiting por pod

---

## 6. Verificação de Compliance (R-B6.1)

### 6.1 GDPR/LGPD - PII Protection

**Requisito:** Encryption in-transit (TLS 1.3) para PII

**Status:**
- TLS 1.3 configurado para Kafka e MongoDB
- **GAP:** Vault usando HTTP (plaintext)
- **GAP:** mTLS em modo PERMISSIVE (permite plaintext)

**Ação requerida:** MTLS-001 e SEC-001 são blockers para GDPR compliance

### 6.2 Audit Logging

**Requisito:** Trail de acesso a dados PII

**Status:**
- Structlog configurado em todos os serviços
- **GAP:** Vault audit logging não configurado
- **GAP:** Istio access logs restritos a erros apenas

**Ação requerida:** SEC-002 para compliance

---

## 7. Métricas e Monitoramento

### 7.1 Métricas Existentes

**Vault:**
- `vault_requests_total` (operation, status)
- `vault_token_renewals_total` (status)
- `vault_token_ttl_seconds` (gauge)

**SPIFFE:**
- `spiffe_svid_fetch_total` (svid_type, status)
- `spiffe_svid_ttl_seconds` (gauge)

### 7.2 Métricas Faltantes

- `mtls_connection_success_rate` (por serviço)
- `vault_audit_events_total` (por tipo)
- `network_policy_drop_total` (por pod, port)
- `egress_external_requests_total` (por destino)

---

## 8. Conclusão

A arquitetura de segurança do NHM está bem definida com:
- SPIFFE/SPIRE para identity management
- Vault para secrets management
- Istio para service mesh e mTLS
- OPA Gatekeeper para policy enforcement

**Gaps críticos identificados:**
1. mTLS ainda em modo PERMISSIVE (transição em progresso)
2. Vault sem TLS habilitado
3. Egress para internet sem restrição

**Next steps:**
1. Priorizar MTLS-001 e SEC-001 (Sprint 1)
2. Implementar NET-001 e MTLS-003 (Sprint 2-3)
3. Endereçar gaps de longo prazo (Sprint 4+)

---

**Assinatura:** Task T10 Worker Agent
**Aprovado por:** Pending Tech Lead Review
