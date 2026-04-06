# Testes E2E Vault + SPIFFE

Testes de integração para Vault e SPIFFE no serviço orchestrator-dynamic.

## Estrutura

```
tests/e2e/
├── docker-compose.e2e.yml    # Ambiente Vault + SPIRE + PostgreSQL
├── scripts/
│   ├── setup_vault.sh        # Configuração Vault (KV v2, PKI, Database)
│   ├── setup_spire.sh        # Configuração SPIRE (trust domain, entries)
│   ├── spire-server.conf     # Configuração SPIRE server
│   └── spire-agent.conf      # Configuração SPIRE agent
├── fixtures/
│   └── vault_spire_setup.py  # Fixtures pytest
├── test_vault_spiffe_e2e.py  # Testes Vault + SPIFFE
└── README.md                 # Este ficheiro
```

## Serviços Configurados

| Serviço | Porta | Propósito |
|---------|-------|-----------|
| Vault | 8200 | Secrets management, PKI, Database credentials |
| SPIRE Server | 8081 | SPIFFE identity management |
| PostgreSQL | 5432 | Dynamic database credentials |
| SPIRE Agent | - | Workload API (unix socket) |

## Como Executar

### 1. Subir ambiente

```bash
cd services/orchestrator-dynamic/tests/e2e
docker-compose -f docker-compose.e2e.yml up -d
```

### 2. Configurar Vault

```bash
docker exec nhm-e2e-setup /scripts/setup_vault.sh
```

Isto configura:
- KV v2 secrets engine em `orchestrator/`
- Kubernetes auth method
- Database secrets engine para PostgreSQL
- Policies: `orchestrator`, `readonly`
- PKI secrets engine com CA interna

### 3. Configurar SPIRE

```bash
docker exec nhm-e2e-setup /scripts/setup_spire.sh
```

### 4. Executar testes

```bash
cd services/orchestrator-dynamic
RUN_VAULT_SPIFFE_E2E=true pytest tests/e2e/test_vault_spiffe_e2e.py -v
```

## Testes Implementados

### Vault (8 testes)
- `test_vault_kubernetes_authentication` - Autenticação Kubernetes
- `test_fetch_postgres_dynamic_credentials` - Credenciais dinâmicas PostgreSQL
- `test_fetch_static_secrets` - Secrets estáticos (MongoDB, Redis, Kafka)
- `test_token_renewal_before_expiration` - Renovação de token
- `test_credential_rotation` - Rotação de credenciais dinâmicas
- `test_fail_open_behavior_when_vault_unavailable` - Comportamento fail-open
- `test_fail_closed_behavior_when_vault_unavailable` - Comportamento fail-closed

### X.509-SVID (3 testes - Gap 3)
- `test_fetch_x509_svid` - Obtenção de X.509-SVID
- `test_x509_svid_refresh` - Renovação antes da expiração
- `test_x509_svid_parsing` - Validação de formato PEM e SPIFFE ID

### PKI (3 testes - Gap 4)
- `test_vault_pki_issue_certificate` - Emissão de certificados
- `test_vault_pki_ca_chain` - Validação de CA chain
- `test_vault_pki_multiple_roles` - Emissão para múltiplas roles

## Cleanup

```bash
docker-compose -f docker-compose.e2e.yml down -v
```

## Troubleshooting

### Vault não responde
```bash
docker logs nhm-e2e-vault
docker exec nhm-e2e-vault vault status
```

### SPIRE server não inicia
```bash
docker logs nhm-e2e-spire-server
# Verificar se spire-server.conf está montado corretamente
```

### Testes skipados
Alguns testes podem ser skipados se:
- `RUN_VAULT_SPIFFE_E2E=true` não está definido
- Vault/SPIRE não estão acessíveis
- Features específicas não estão habilitadas (X.509, PKI)

## Gaps Corrigidos (Ticket QA-005)

- **Gap 1**: `docker-compose.e2e.yml` criado com Vault dev mode, SPIRE server/agent, PostgreSQL
- **Gap 2**: Scripts `setup_vault.sh` e `setup_spire.sh` criados com tratamento de erros
- **Gap 3**: Testes X.509-SVID adicionados (fetch, refresh, parsing)
- **Gap 4**: Testes PKI adicionados (issue_certificate, ca_chain, multiple_roles)
