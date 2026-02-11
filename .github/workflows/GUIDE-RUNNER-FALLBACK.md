# Guia de Migração: Auto Fallback para Self-Hosted Runner

## Objetivo

Configurar workflows para usar **GitHub-hosted runners prioritariamente**, com **fallback automático** para self-hosted quando esgotar limite de minutos.

## Como Funciona

```
┌─────────────────────────────────────────────────────────────────────┐
│ Workflow Triggered                                           │
│      ↓                                                          │
│ Job: select-runner (reutilizável)                              │
│      ↓                                                          │
│  Verifica: GitHub-hosted disponível?                             │
│      ↓               ↘                                        │
│  Sim               Não (Rate limit)                             │
│      ↓                   ↓                                       │
│ ubuntu-latest      self-hosted:neural-hive                         │
│      └───────────────────┘                                       │
│      ↓                                                          │
│ Job Principal: build/test (usa runner selecionado)               │
└─────────────────────────────────────────────────────────────────────┘
```

## Migração Passo a Passo

### ANTES (Workflow Típico Atual)
```yaml
name: build-gateway
on: push
jobs:
  build:
    runs-on: [self-hosted, neural-hive]  # ← Sempre self-hosted
    steps:
      - uses: actions/checkout@v4
      # ... build steps
```

### DEPOIS (Com Auto Fallback)
```yaml
name: build-gateway
on: push
jobs:
  # ← NOVO: Job de seleção de runner
  select-runner:
    uses: ./.github/workflows/_runner-select.yml
    secrets: inherit

  # ← MODIFICADO: Usa runner selecionado
  build:
    needs: select-runner
    runs-on: ${{ needs.select-runner.outputs.selected-runner }}
    steps:
      - uses: actions/checkout@v4
      # ... build steps (igual antes)
```

## Workflows que Devem Ser Migraos

### Prioridade ALTA (usam muito self-hosted)

- `build-gateway.yml`
- `test-specialists.yml`
- `ml-integration-tests.yml`
- `performance-test.yml`
- `online-learning-pipeline.yml`
- `dependency-audit.yml`
- `test-mcp-tool-catalog.yml`
- `validate-*.yml`

### Prioridade MÉDIA

- `deploy-after-build.yml`
- `deploy-to-cluster.yml`
- `rebuild-and-deploy-services.yml`

### Podem Manter GitHub-hosted Apenas

- Workflows rápidos (< 2 minutos)
- Workflows que não exigem self-hosted

## Exemplo Completo: Migrando build-gateway.yml

### Arquivo Original (.github/workflows/build-gateway.yml)
```yaml
name: Build Gateway

on:
  push:
    paths:
      - 'libraries/gateway/**'
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE: neural-hive-gateway

jobs:
  build:
    runs-on: [self-hosted, neural-hive]
    outputs:
      image: ${{ steps.meta.outputs.tags }}
      sha: ${{ steps.meta.outputs.sha }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      # ... resto do workflow
```

### Arquivo Migrao
```yaml
name: Build Gateway

on:
  push:
    paths:
      - 'libraries/gateway/**'
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE: neural-hive-gateway

jobs:
  # ← NOVO: Seleção automática de runner
  select-runner:
    name: Select Runner
    uses: ./.github/workflows/_runner-select.yml
    secrets: inherit

  # ← MODIFICADO: Adiciona 'needs' e muda 'runs-on'
  build:
    name: Build Gateway Image
    needs: select-runner
    runs-on: ${{ needs.select-runner.outputs.selected-runner }}
    outputs:
      image: ${{ steps.meta.outputs.tags }}
      sha: ${{ steps.meta.outputs.sha }}
    steps:
      - name: Show Runner Type
        run: |
          echo "🎯 Running on: ${{ needs.select-runner.outputs.runner-type }}"
          echo "🏷️  Runner: ${{ needs.select-runner.outputs.selected-runner }}"

      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      # ... resto do workflow IGUAL antes
```

## Configuração de Rate Limit

O GitHub Actions tem limites de minutos por mês:
- **Free**: 2000 minutos/mês
- **Pro**: 10,000 minutos/mês
- **Team**: 50,000 minutos/mês

O sistema de fallback é mais útil quando:
- ✅ Você está chegando perto do limite
- ✅ Tem runs longos (build, testes E2E)
- ✅ Múltiplos PRs/commits simultâneos

## Estratégia de Priorização

| Situação | Runner Priorizado | Justificativa |
|-----------|-------------------|---------------|
| Primeiro push do dia | ubuntu-latest | GitHub-hosted está descansado |
| PR de revisão | ubuntu-latest | Rápido e isolado |
| Build principal | ubuntu-latest → self-hosted | Se demorar, próximo usa self-hosted |
| Testes E2E longos | self-hosted | Economiza minutos |
| Deploy | self-hosted | Já está usando |
| Workflow_dispatch manual | self-hosted | Usuário quer executar local |

## Comandos Úteis

```bash
# Ver minutos usados no mês atual
gh api /user/booking 2>/dev/null | jq '.usage_minutes'

# Ver runners disponíveis
gh runner list

# Verificar se self-hosted está online
gh api /orgs/jimysoares76/actions/runners 2>/dev/null | jq '.runners[] | select(.name=="local-neural-hive-runner") | {name, status, busy}'
```

## Troubleshooting

### Workflow falha com "undefined outputs"

Problema: Job principal tenta acessar outputs do job de seleção antes dele existir.

Solução: Verifique se o nome do job de seleção está correto no `needs:`

### Runner sempre executa no ubuntu-latest

Problema: O job de seleção não está sendo executado primeiro.

Solução: Verifique se o workflow está usando `needs:` corretamente.

### Self-hosted nunca é selecionado

Problema: O sistema sempre usa ubuntu-latest.

Solução: Ajuste a lógica em `_runner-select.yml` ou adicione inputs customizados.
