# Workflows CI/CD - Neural Hive Mind

Documentação dos workflows de CI/CD do projeto Neural Hive Mind.

## 📋 Índice

- [Build and Push to GHCR](#build-and-push-to-ghcr)
- [Política de Segurança](#política-de-segurança)
- [Como Usar](#como-usar)
- [Troubleshooting](#troubleshooting)

---

## Build and Push to GHCR

Workflow responsável por construir e publicar imagens Docker dos serviços no GitHub Container Registry (GHCR).

**Arquivo:** `build-and-push-ghcr.yml`

### Triggers

| Evento | Descrição | Push para Registry? |
|--------|-----------|---------------------|
| `push` em `main`/`develop` | Build automático após commit | ✅ Sim |
| `pull_request` | Build para validação do PR | ❌ Não |
| `workflow_dispatch` | Execução manual | ✅ Sim |

### Inputs (workflow_dispatch)

| Input | Descrição | Obrigatório | Padrão |
|-------|-----------|-------------|--------|
| `services` | Serviços específicos (separados por vírgula) | Não | (todos) |
| `version_tag` | Tag semântica (ex: v1.2.3) | Não | latest |
| `skip_tests` | Pular testes | Não | false |

---

## Política de Segurança

### Por que PRs não fazem push?

Por segurança, **Pull Requests executam build mas NÃO publicam imagens** no registry. Isso garante que:

- ✅ Código não revisado não seja publicado
- ✅ Apenas código aprovado chegue ao registry
- ✅ Validação de build aconteça antes do merge

### Fluxo de Trabalho

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Desenvolvedor  │───▶│   Pull Request  │───▶│     CI/CD       │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │  Build Imagem   │
                                              └────────┬────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │  Executa Testes │
                                              └────────┬────────┘
                                                       │
                               ❌ NÃO faz push ────────┤
                                                       │
                                              ┌────────▼────────┐
                                              │   ✅ Build OK   │
                                              └─────────────────┘

Após aprovação e merge:

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Merge PR      │───▶│   Push main     │───▶│     CI/CD       │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │  Build Imagem   │
                                              └────────┬────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │  ✅ Push GHCR   │
                                              └────────┬────────┘
                                                       │
                                              ┌────────▼────────┐
                                              │   Kubernetes    │
                                              │   Pull Imagem   │
                                              └─────────────────┘
```

---

## Como Usar

### 1. Build Automático (Push em Branch)

Ao fazer push em `main` ou `develop`, o workflow é disparado automaticamente:

```bash
git push origin main
```

**Resultado:**
- Build de todos os serviços modificados
- Push para `ghcr.io/albinojimy/neural-hive-mind/<service>:latest`
- Tags: `latest`, `<sha>`, `<branch>`

### 2. Build de Pull Request

Ao criar PR, o workflow valida o build:

```bash
gh pr create --title "Feature X" --body "Descrição"
```

**Resultado:**
- ✅ Build executado
- ✅ Testes executados
- ❌ **Sem push para registry**

### 3. Build Manual (workflow_dispatch)

#### 3.1. Via GitHub Actions UI

1. Acesse: **Actions** → **Build and Push to GHCR** → **Run workflow**
2. Preencha os inputs:
   - **Branch:** selecione a branch
   - **services:** deixe vazio (todos) ou especifique (ex: `gateway-intencoes,orchestrator-dynamic`)
   - **version_tag:** especifique versão semântica (ex: `v1.2.3`)
3. Clique em **Run workflow**

#### 3.2. Via GitHub CLI

```bash
# Build de todos os serviços com tag específica
gh workflow run build-and-push-ghcr.yml \
  --ref main \
  -f version_tag="v1.2.3"

# Build de serviço específico
gh workflow run build-and-push-ghcr.yml \
  --ref main \
  -f services="gateway-intencoes" \
  -f version_tag="v1.2.4"

# Build de múltiplos serviços
gh workflow run build-and-push-ghcr.yml \
  --ref develop \
  -f services="gateway-intencoes,orchestrator-dynamic,queen-agent" \
  -f version_tag="v2.0.0-beta.1"
```

### 4. Forçar Push de PR Aprovado

Se precisar publicar imagem de um PR **antes do merge** (após aprovação):

```bash
# Obter nome da branch do PR
PR_BRANCH=$(gh pr view 123 --json headRefName -q .headRefName)

# Disparar workflow manual na branch do PR
gh workflow run build-and-push-ghcr.yml \
  --ref "$PR_BRANCH" \
  -f services="gateway-intencoes" \
  -f version_tag="v1.2.3-rc.1"
```

---

## Troubleshooting

### ❌ Imagem não aparece no registry após PR

**Causa:** Pull Requests não fazem push por segurança.

**Solução:**
1. Faça merge do PR (recomendado)
2. Ou use `workflow_dispatch` manualmente

### ❌ Erro: "version_tag não é formato semver válido"

**Causa:** Tag fornecida não segue padrão semântico.

**Formatos válidos:**
- `v1.2.3`
- `1.2.3`
- `v2.0.0-alpha.1`
- `v1.0.0-beta.2+build.123`

**Formatos inválidos:**
- `v1.2` (falta PATCH)
- `latest-v1` (formato incorreto)
- `1.2.3.4` (muitos dígitos)

### ❌ Build não disparou após push

**Verificações:**
1. Push foi em `main` ou `develop`?
2. Arquivos modificados estão em `services/`, `libraries/`, `schemas/` ou `base-images/`?
3. Workflow está habilitado em Settings → Actions?

### ❌ Imagem não atualiza no cluster

**Causa:** `imagePullPolicy: IfNotPresent` com tag `latest`.

**Solução:**
1. Use tags específicas (SHA ou versão semântica)
2. Ou configure `imagePullPolicy: Always` para tag `latest`
3. Ou force pull: `kubectl rollout restart deployment/<service> -n neural-hive`

---

## Referências

- [GitHub Actions - Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Docker Metadata Action](https://github.com/docker/metadata-action)
- [Semantic Versioning](https://semver.org/)
- [GHCR Documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
