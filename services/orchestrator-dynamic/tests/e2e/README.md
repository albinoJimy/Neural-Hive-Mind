# Testes E2E Vault+SPIFFE

Testes de integração completa entre Vault (secrets management, dynamic credentials, PKI) e SPIFFE/SPIRE (workload identity, SVIDs).

## Pré-requisitos

- Docker e Docker Compose
- Python 3.12+
- Acesso às bibliotecas `neural-hive-security` e `neural-hive-domain`

## 19 Cenários de Teste

### Autenticação (4)
1. Kubernetes Auth com SA Token válido
2. Kubernetes Auth com SA Token expirado
3. JWT Auth com SPIFFE SVID válido
4. JWT Auth com SPIFFE SVID expirado

### Secret Management (4)
5. Leitura de segredo KV v2 existente
6. Leitura de segredo KV v2 inexistente (404)
7. Escrita de segredo KV v2 com permissão
8. Escrita de segredo KV v2 sem permissão (403)

### Dynamic Credentials (3)
9. Geração de credenciais PostgreSQL
10. Renovação de credenciais antes da expiração
11. Rotação de credenciais por lease expiry

### SVID Operations (5)
12. Fetch JWT-SVID com audience específico
13. Fetch X.509-SVID com parsing de certificado
14. Background refresh antes da expiração
15. Cache hit/miss para JWT-SVID
16. Trust bundle JWKS parsing

### PKI Operations (2)
17. Emissão de certificado via PKI engine
18. Recuperação de CA chain do PKI engine

### Fail Modes (2)
19. Comportamento fail-open quando Vault indisponível
20. Comportamento fail-closed quando Vault indisponível

### Observabilidade (2)
21. Métricas de requests Vault são registradas
22. Logs estruturados são emitidos

### Integração Orchestrator (3)
23. Credenciais PostgreSQL via OrchestratorVaultClient
24. URI MongoDB via OrchestratorVaultClient
25. Senha Redis via OrchestratorVaultClient

## Execução

### Modo 1: Com Docker Compose (Recomendado)

```bash
# 1. Subir infraestrutura
cd services/orchestrator-dynamic
docker-compose -f tests/e2e/docker-compose.e2e up -d

# 2. Aguardar serviços ficarem prontos
docker-compose -f tests/e2e/docker-compose.e2e logs -f

# 3. Executar testes dentro do container
docker-compose -f tests/e2e/docker-compose.e2e exec test-runner \
    pytest tests/e2e/test_vault_spiffe_e2e.py -v

# 4. Limpeza
docker-compose -f tests/e2e/docker-compose.e2e down -v
```

### Modo 2: Local com Vault/SPIRE existentes

```bash
# 1. Exportar variáveis de ambiente
export VAULT_ADDR="http://localhost:8200"
export VAULT_TOKEN="seu-token-aqui"
export RUN_VAULT_SPIFFE_E2E="true"

# 2. Executar testes
pytest services/orchestrator-dynamic/tests/e2e/test_vault_spiffe_e2e.py -v
```

### Modo 3: Apenas com Mocks (Sem infraestrutura)

```bash
# Testes com mocks (não requer Vault/SPIRE)
pytest services/orchestrator-dynamic/tests/e2e/test_vault_spiffe_e2e.py -v
```

## Scripts Auxiliares

### setup_vault.sh
Configura Vault para testes:
- Habilita Kubernetes e JWT auth
- Configura secrets engines (KV v2, Database, PKI)
- Cria policies RBAC
- Escreve segredos de teste

### setup_spire.sh
Configura SPIRE Server:
- Gera certificados CA
- Configura trust domain
- Configura workload API

### configure_policies.sh
Cria policies RBAC:
- `orchestrator-policy`: Permissões completas para orchestrator
- `readonly-policy`: Apenas leitura
- `admin-policy`: Permissões totais

## Estrutura

```
tests/e2e/
├── docker-compose.e2e.yml      # Infraestrutura de teste
├── Dockerfile.e2e              # Imagem do test runner
├── scripts/
│   ├── setup_vault.sh         # Setup Vault
│   ├── setup_spire.sh         # Setup SPIRE
│   ├── configure_policies.sh  # Policies RBAC
│   └── spire_agent.conf       # Config do SPIRE Agent
├── fixtures/
│   └── vault_spire_setup.py   # Fixtures pytest
└── test_vault_spiffe_e2e.py   # 25 testes E2E
```

## Variáveis de Ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `VAULT_ADDR` | http://localhost:8200 | Endpoint Vault |
| `VAULT_TOKEN` | dev-root-token | Token Vault (dev mode) |
| `VAULT_ROLE` | orchestrator | Role Kubernetes/JWT |
| `VAULT_AUTH_PATH` | kubernetes | Path do auth method |
| `VAULT_AUTH_METHOD` | kubernetes | Método de auth |
| `VAULT_FAIL_OPEN` | false | Fail-open em erros |
| `SPIFFE_WORKLOAD_API_SOCKET` | unix:///run/spire/sockets/agent.sock | Socket SPIRE |
| `SPIFFE_TRUST_DOMAIN` | neural-hive.local | Trust domain |
| `SPIFFE_JWT_AUDIENCE` | vault.neural-hive.local | Audience JWT |
| `RUN_VAULT_SPIFFE_E2E` | false | Habilita testes reais |

## Troubleshooting

### Vault não inicia
```bash
# Ver logs
docker-compose -f tests/e2e/docker-compose.e2e logs vault

# Ver health
curl http://localhost:8200/v1/sys/health
```

### SPIRE Agent não conecta
```bash
# Ver socket
docker-compose -f tests/e2e/docker-compose.e2e exec spire-agent \
    ls -la /run/spire/sockets/

# Ver logs
docker-compose -f tests/e2e/docker-compose.e2e logs spire-agent
```

### Testes pulados
Se testes aparecem como `SKIPPED`, verifique:
- `RUN_VAULT_SPIFFE_E2E=true` está exportado
- Serviços estão rodando (`docker ps`)
- Vault está saudável

## Cobertura

Atual: 25 cenários de teste cobrindo:
- Autenticação Kubernetes/JWT
- KV v2 secrets (read/write)
- Database dynamic credentials
- PKI certificate issuance
- SPIFFE JWT-SVID/X.509-SVID
- Fail-open/fail-closed
- Métricas e logging
- Integração OrchestratorVaultClient
