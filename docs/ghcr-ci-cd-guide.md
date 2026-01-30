# Guia de CI/CD com GitHub Container Registry (GHCR)

Este documento descreve o processo de build e deploy de servicos Neural Hive-Mind usando GitHub Actions e GitHub Container Registry.

## Visao Geral

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUXO CI/CD COM GHCR                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [GitHub Repository]                                                        │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────┐                                                        │
│  │   Push/PR       │                                                        │
│  │   Trigger       │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │              GitHub Actions Runner (7GB RAM)                    │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │       │
│  │  │ Build Svc 1 │  │ Build Svc 2 │  │ Build Svc N │  (paralelo) │       │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │       │
│  │         │                │                │                     │       │
│  │         └────────────────┼────────────────┘                     │       │
│  │                          ▼                                      │       │
│  │                   ┌─────────────┐                               │       │
│  │                   │ Push GHCR   │                               │       │
│  │                   └─────────────┘                               │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                          │                                                  │
│                          ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │              GitHub Container Registry (ghcr.io)                │       │
│  │                                                                 │       │
│  │  ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:latest  │       │
│  │  ghcr.io/albinojimy/neural-hive-mind/queen-agent:sha-abc123    │       │
│  │  ghcr.io/albinojimy/neural-hive-mind/...                       │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                          │                                                  │
│                          ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                    Kubernetes Cluster                           │       │
│  │                                                                 │       │
│  │  ┌───────────────┐                                              │       │
│  │  │ ghcr-secret   │  (imagePullSecrets)                         │       │
│  │  └───────┬───────┘                                              │       │
│  │          │                                                      │       │
│  │          ▼                                                      │       │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │       │
│  │  │  Deployment   │  │  Deployment   │  │  Deployment   │       │       │
│  │  │  gateway      │  │  queen-agent  │  │  ...          │       │       │
│  │  └───────────────┘  └───────────────┘  └───────────────┘       │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Vantagens

| Aspecto | GHCR | Registry Interno |
|---------|------|------------------|
| **Build Resources** | 7GB RAM, 2 CPU | Limitado pelo cluster |
| **Paralelismo** | Ate 6 jobs simultaneos | Sequencial (PVC RWO) |
| **Cache** | Persistente entre builds | Volatil |
| **Disponibilidade** | 99.9% SLA | Depende do cluster |
| **Custo** | Gratuito (repos publicos) | Infraestrutura propria |
| **Seguranca** | GHCR tokens, packages scope | Registry interno |

## Configuracao Inicial

### 1. Criar Personal Access Token (PAT)

1. Acesse https://github.com/settings/tokens
2. Clique em "Generate new token (classic)"
3. Selecione os escopos:
   - `read:packages` - para pull de imagens
   - `write:packages` - para push de imagens
   - `delete:packages` - opcional
4. Copie o token gerado

### 2. Configurar Secrets no Repositorio

Acesse: Settings > Secrets and variables > Actions

| Secret | Descricao |
|--------|-----------|
| `KUBECONFIG` | Kubeconfig do cluster (base64) |
| `SLACK_WEBHOOK_URL` | (Opcional) Webhook para notificacoes |

### 3. Configurar Secret no Cluster

O secret deve ser criado em **cada namespace** que executa deployments:

```bash
# Lista de namespaces comuns
NAMESPACES=("gateway" "neural-hive" "neural-hive-specialists" "mlflow")

for NS in "${NAMESPACES[@]}"; do
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=<GITHUB_USERNAME> \
    --docker-password=<GITHUB_TOKEN> \
    -n $NS --dry-run=client -o yaml | kubectl apply -f -
done
```

**Ou usando o script:**

```bash
./scripts/ghcr/setup-ghcr-secret.sh \
  -u <GITHUB_USERNAME> \
  -t <GITHUB_TOKEN> \
  -n gateway,neural-hive,neural-hive-specialists,mlflow
```

**Verificação:**

```bash
# Verificar em todos namespaces
kubectl get secret ghcr-secret --all-namespaces

# Verificar deployment específico
kubectl get deployment gateway-intencoes -n gateway -o yaml | grep -A2 imagePullSecrets
```

### 4. Migrar Deployments (Opcional)

```bash
# Ver status atual
./scripts/ghcr/migrate-to-ghcr.sh --status

# Migrar com dry-run
./scripts/ghcr/migrate-to-ghcr.sh --dry-run

# Migrar de verdade
./scripts/ghcr/migrate-to-ghcr.sh -t latest
```

## Workflows Disponiveis

### build-and-push-ghcr.yml

Build e push de imagens para GHCR.

**Triggers:**
- Push para `main` ou `develop`
- Pull Request para `main` ou `develop`
- Manual (workflow_dispatch)

**Uso Manual:**
```
Actions > Build and Push to GHCR > Run workflow
  - services: gateway-intencoes,queen-agent (ou vazio para todos)
  - version_tag: 1.0.8 (ou latest)
  - skip_tests: false
```

### deploy-to-cluster.yml

Deploy automatico apos build bem-sucedido.

**Triggers:**
- Apos workflow "Build and Push to GHCR" completar com sucesso
- Manual (workflow_dispatch)

**Uso Manual:**
```
Actions > Deploy to Cluster > Run workflow
  - environment: development/staging/production
  - services: gateway-intencoes,queen-agent (ou vazio para todos)
  - image_tag: latest (ou sha-xxx)
  - dry_run: false
```

## Comandos Uteis

### Verificar Imagens no GHCR

```bash
# Listar pacotes do usuario
gh api /users/<USERNAME>/packages?package_type=container

# Listar tags de uma imagem
gh api /users/<USERNAME>/packages/container/neural-hive-mind%2Fgateway-intencoes/versions
```

### Pull Manual de Imagem

```bash
# Login
echo $GITHUB_TOKEN | docker login ghcr.io -u <USERNAME> --password-stdin

# Pull
docker pull ghcr.io/<USERNAME>/neural-hive-mind/gateway-intencoes:latest
```

### Verificar no Cluster

```bash
# Verificar secret
kubectl get secret ghcr-secret -n neural-hive -o yaml

# Testar pull
kubectl run test-pull --rm -it --restart=Never \
  --image=ghcr.io/<USERNAME>/neural-hive-mind/gateway-intencoes:latest \
  --overrides='{"spec":{"imagePullSecrets":[{"name":"ghcr-secret"}]}}' \
  -n neural-hive -- echo "Pull OK"

# Verificar deployment
kubectl get deployment gateway-intencoes -n neural-hive -o yaml | grep image
```

## Estrutura de Arquivos

```
.github/workflows/
├── build-and-push-ghcr.yml    # Build e push para GHCR
└── deploy-to-cluster.yml      # Deploy automatico

k8s/secrets/
└── ghcr-registry-secret.yaml  # Template do secret

scripts/ghcr/
├── setup-ghcr-secret.sh       # Setup do secret no cluster
└── migrate-to-ghcr.sh         # Migracao de deployments
```

## Troubleshooting

### Erro: "unauthorized" no pull

1. Verificar se o secret existe:
   ```bash
   kubectl get secret ghcr-secret -n neural-hive
   ```

2. Verificar se o token tem permissao `read:packages`

3. Verificar se a imagem existe no GHCR:
   ```bash
   gh api /users/<USERNAME>/packages/container/neural-hive-mind%2F<SERVICE>/versions
   ```

### Erro: "manifest unknown" 

A imagem ou tag nao existe no GHCR. Verificar:
1. Se o build foi executado com sucesso
2. Se a tag esta correta
3. Se o push foi feito (PRs nao fazem push)

### Build falha por timeout

Aumentar o timeout no workflow ou reduzir o paralelismo:
```yaml
strategy:
  max-parallel: 4  # Reduzir de 6 para 4
```

### Deploy falha por kubeconfig

1. Verificar se o secret `KUBECONFIG` esta configurado
2. Gerar kubeconfig base64:
   ```bash
   cat ~/.kube/config | base64 -w0
   ```
3. Atualizar o secret no GitHub

## Rollback

### Via Script

```bash
./scripts/ghcr/migrate-to-ghcr.sh --rollback
```

### Via kubectl

```bash
# Rollback para versao anterior
kubectl rollout undo deployment/gateway-intencoes -n neural-hive

# Ou especificar imagem do registry interno
kubectl set image deployment/gateway-intencoes \
  gateway-intencoes=37.60.241.150:30500/gateway-intencoes:1.1.5 \
  -n neural-hive
```

## Proximos Passos

1. **Configurar Signed Commits** - Garantir integridade do codigo
2. **Adicionar SBOM** - Software Bill of Materials para supply chain security
3. **Implementar Canary Deploys** - Deploys graduais com Argo Rollouts
4. **Adicionar Smoke Tests** - Testes pos-deploy automaticos
