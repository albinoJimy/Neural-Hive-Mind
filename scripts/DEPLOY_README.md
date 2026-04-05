# Scripts de Deploy Automatizado - Neural Hive Mind

Esta suite de scripts fornece automatizacao completa para deploy e rollback de servicos do Neural Hive Mind em ambientes Kubernetes.

## Scripts Disponiveis

| Script | Proposito |
|--------|-----------|
| `deploy-staging.sh` | Deploy automatizado de servicos |
| `rollback-staging.sh` | Rollback automatizado para versao anterior |
| `validate-deployment.py` | Validacao pos-deploy |

## Pre-requisitos

- Docker (para build de imagens)
- kubectl (configurado para o cluster alvo)
- Helm 3.x
- Python 3.10+ (para validacao)
- jq (para processamento de JSON)

## Instalacao

Os scripts ja estao incluidos no projeto em `/scripts/`. Certifique-se de que tem permissao de execucao:

```bash
chmod +x scripts/deploy-staging.sh
chmod +x scripts/rollback-staging.sh
chmod +x scripts/validate-deployment.py
```

## Uso

### Deploy de Servicos

```bash
# Deploy basico para staging
./scripts/deploy-staging.sh --env staging --services queen-mcp-server

# Deploy de multiplos servicos
./scripts/deploy-staging.sh --services queen-mcp-server,worker-mcp-server,analyst-mcp-server

# Deploy com versao especifica
./scripts/deploy-staging.sh --services queen-mcp-server --version v1.2.3

# Deploy para producao (requer confirmacao)
./scripts/deploy-staging.sh --env production --services queen-mcp-server

# Deploy com auto-confirmacao (para CI/CD)
./scripts/deploy-staging.sh --services queen-mcp-server --yes

# Deploy simulado (dry-run)
./scripts/deploy-staging.sh --services queen-mcp-server --dry-run
```

### Rollback de Servicos

```bash
# Rollback para versao anterior
./scripts/rollback-staging.sh --services queen-mcp-server

# Rollback para revisao especifica
./scripts/rollback-staging.sh --services queen-mcp-server --revision 2

# Rollback forçado (ignora health checks falhando)
./scripts/rollback-staging.sh --services queen-mcp-server --force

# Rollback em producao
./scripts/rollback-staging.sh --env production --services queen-mcp-server
```

### Validacao de Deployment

```bash
# Validar servico apos deploy
./scripts/validate-deployment.py --env staging --services queen-mcp-server

# Validar todos os servicos
./scripts/validate-deployment.py --all --timeout 300

# Validacao detalhada
./scripts/validate-deployment.py --services queen-mcp-server --verbose

# Salvar relatorio em JSON
./scripts/validate-deployment.py --all --output-json deployment-report.json
```

## Servicos Disponiveis

### MCP Servers
- `queen-mcp-server` - Coordenacao estrategica
- `worker-mcp-server` - Execucao de tarefas
- `analyst-mcp-server` - Analise profunda
- `architect-mcp-server` - Arquitetura de solucoes
- `guard-mcp-server` - Validacao e seguranca
- `code-forge-mcp-server` - Geracao de codigo
- `healer-mcp-server` - Auto-recuperacao
- `execution-mcp-server` - Gestao de execucao
- `scout-mcp-server` - Exploracao e descoberta

### Core Services
- `queen-agent` - Supervisor e coordenacao
- `worker-agents` - Execucao distribuida
- `analyst-agents` - Insights multi-fonte
- `scout-agents` - Deteccao e exploracao
- `guard-agents` - Seguranca
- `consensus-engine` - Consenso entre especialistas
- `orchestrator-dynamic` - Orquestracao de workflows

## Flags de Seguranca

### Para Staging
- Deploy e rollback executados com confirmacao (a menos que `--yes` seja usado)
- Health checks sao executados por padrao
- Logs detalhados sao salvos em `logs/deploy/`

### Para Producao
- **Confirmacao explicita obrigatorio** (a menos que `--yes` seja usado)
- Timeout de health check: 300 segundos (5 minutos)
- Snapshots sao salvos automaticamente antes do rollback
- Logs sao preservados para auditoria

## Fluxo de Deploy

```
1. Pre-requisitos (docker, kubectl, helm)
   |
2. Build de imagens Docker (opcional)
   |
3. Helm upgrade/install
   |
4. Wait for pods ready
   |
5. Health checks
   |
6. Relatorio de resultados
```

## Fluxo de Rollback

```
1. Snapshot do estado atual
   |
2. Historico de revisoes Helm
   |
3. Confirmacao de rollback
   |
4. Helm rollback
   |
5. Wait for pods ready
   |
6. Validacao pos-rollback
   |
7. Relatorio de resultados
```

## Logs e Relatorios

### Deploy
- **Localizacao:** `logs/deploy/deploy-YYYYMMDD-HHMMSS.log`
- **Conteudo:** Comandos executados, output completo, erros

### Rollback
- **Localizacao:** `logs/rollback/rollback-YYYYMMDD-HHMMSS.log`
- **Snapshot:** `logs/rollback/snapshot-<env>-YYYYMMDD-HHMMSS.txt`

### Validacao
- **Console:** Output formatado com cores
- **JSON:** `--output-json` para relatorio estruturado

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy to Staging

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Configure kubectl
        run: |
          aws eks update-kubeconfig --name neural-hive-staging --region us-east-1

      - name: Deploy services
        run: |
          ./scripts/deploy-staging.sh \
            --env staging \
            --services queen-mcp-server,worker-mcp-server \
            --yes

      - name: Validate deployment
        run: |
          ./scripts/validate-deployment.py \
            --env staging \
            --services queen-mcp-server,worker-mcp-server \
            --timeout 600
```

## Troubleshooting

### Pods nao ficam prontos

```bash
# Ver pods
kubectl get pods -n staging

# Ver logs de um pod especifico
kubectl logs -n staging <pod-name> --tail=100

# Descrever pod para ver eventos
kubectl describe pod -n staging <pod-name>
```

### Helm release em estado falho

```bash
# Ver status do release
helm status <release-name> -n staging

# Ver historico de revisoes
helm history <release-name> -n staging

# Rollback para revisao anterior
./scripts/rollback-staging.sh --services <service-name>
```

### Timeout no health check

```bash
# Aumentar timeout
./scripts/deploy-staging.sh --services queen-mcp-server --timeout 600

# Pular health checks
./scripts/deploy-staging.sh --services queen-mcp-server --skip-health-checks
```

## Seguranca

1. **Nunca fazer commit** de credenciais ou secrets
2. **Usar variaveis de ambiente** para dados sensiveis
3. **Helm secrets** devem estar em `values-secrets.yaml` (gitignored)
4. **Producao requer confirmacao** explicita
5. **Logs sao salvos** para auditoria e troubleshooting

## Boas Praticas

1. **Testar em staging primeiro** antes de producao
2. **Usar versionamento semantico** (v1.2.3)
3. **Monitorar logs** durante o deploy
4. **Ter plano de rollback** preparado
5. **Validar apos deploy** usando validate-deployment.py
6. **Manter documentacao atualizada** para novos servicos

## Suporte

Para problemas ou questoes:
- Ver logs em `logs/deploy/` ou `logs/rollback/`
- Use `--verbose` para output detalhado
- Consulte README.md do projeto para contexto geral
