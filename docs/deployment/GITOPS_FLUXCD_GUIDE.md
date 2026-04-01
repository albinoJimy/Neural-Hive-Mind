# GitOps com FluxCD - Neural Hive-Mind

## Visão Geral

Este documento descreve a implementação de GitOps contínuo usando FluxCD para o projeto Neural Hive-Mind, substituindo os deploys manuais via `workflow_dispatch`.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GitHub Repository                              │
│                    (albinoJimy/Neural-Hive-Mind)                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ Git Push (main/develop)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         GitHub Actions (CI)                             │
│                     Build & Push to GHCR                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ New Image Tag
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FluxCD (Cluster K8s)                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   Source     │  │  Kustomize   │  │    Helm      │                  │
│  │  Controller  │→ │  Controller  │→ │  Controller  │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
│  ┌──────────────┐  ┌──────────────┐                                        │
│  │    Image     │  │  Notification│                                        │
│  │  Controller  │  │  Controller  │                                        │
│  └──────────────┘  └──────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ GitOps Sync
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Kubernetes Cluster                                   │
│  Infrastructure → Services → Specialists → Agents                        │
└─────────────────────────────────────────────────────────────────────────┘
```

## Componentes FluxCD

### 1. Source Controller
- **Função:** Monitora o repositório Git e busca atualizações
- **Intervalo:** 30s (dev) / 1m (prod)
- **GitRepository:** `neural-hive-mind`

### 2. Kustomize Controller
- **Função:** Aplica manifestos Kubernetes ao cluster
- **Kustomizations:**
  - `infrastructure`: Infraestrutura base (observabilidade, segurança)
  - `core-services`: Serviços core (Gateway, STE, Consensus, etc.)
  - `specialists`: Especialistas (Business, Technical, Architecture, etc.)
  - `agents`: Agentes (Worker, Scout, Guard, Analyst)

### 3. Helm Controller
- **Função:** Gerencia releases Helm
- **Recursos:** `HelmRelease` para cada serviço

### 4. Image Controller
- **Função:** Monitora registro de containers (GHCR)
- **ImageRepositories:** Configuradas para cada serviço
- **ImagePolicies:** Define qual tag usar (semver, alphabetical, etc.)

### 5. Image Update Automation
- **Função:** Atualiza o Git com novas tags de imagem
- **Intervalo:** 30 minutos
- **Estratégia:** Setters (marcadores nos manifests)

## Estrutura de Diretórios

```
infrastructure/fluxcd/
├── clusters/
│   ├── prod/                              # Ambiente de Produção
│   │   ├── flux-system/
│   │   │   └── gotk-components.yaml       # Componentes FluxCD
│   │   ├── infrastructure/
│   │   │   └── kustomization.yaml         # Infraestrutura base
│   │   ├── services/
│   │   │   ├── gateway-intencoes.yaml     # HelmRelease Gateway
│   │   │   ├── consensus-engine.yaml
│   │   │   └── ...
│   │   ├── specialists/
│   │   │   ├── business-specialist.yaml
│   │   │   ├── technical-specialist.yaml
│   │   │   └── ...
│   │   └── agents/
│   │       ├── worker-agents.yaml
│   │       ├── scout-agents.yaml
│   │       └── ...
│   └── dev/                               # Ambiente de Desenvolvimento
│       └── (mesma estrutura do prod)
└── README.md                              # Este documento
```

## Instalação

### Pré-requisitos

1. **kubectl** - Cliente Kubernetes
2. **flux CLI** - Instalado automaticamente pelo script
3. **Acesso ao cluster** - Kubeconfig configurado
4. **Chave SSH** - Para acesso ao repositório Git

### Passo 1: Configurar Segredos

```bash
# Criar chave SSH específica para FluxCD
ssh-keygen -t ed25519 -f ~/.ssh/id_rsa_flux -C "fluxcd@neural-hive-mind"

# Adicionar chave pública ao GitHub
cat ~/.ssh/id_rsa_flux.pub
# Copiar para: GitHub Settings → SSH Keys → Add New

# Configurar credenciais do GHCR
export GHCR_USERNAME="albinojimy"
export GHCR_PASSWORD="<github-pat>"
```

### Passo 2: Executar Script de Instalação

```bash
cd /home/jimy/NHM/Neural-Hive-Mind

# Instalar no ambiente de produção
./scripts/deploy/install-fluxcd.sh prod

# Ou instalar no ambiente de desenvolvimento
./scripts/deploy/install-fluxcd.sh dev
```

### Passo 3: Verificar Instalação

```bash
# Verificar componentes FluxCD
flux check

# Listar Kustomizations
flux get kustomizations --all-namespaces

# Listar HelmReleases
flux get helmreleases --all-namespaces

# Monitorar syncs em tempo real
flux get kustomizations --watch
```

## Fluxo de Deploy Automatizado

### Deploy Automático (CI/CD + GitOps)

1. **Developer faz push** para branch `main` ou `develop`
2. **GitHub Actions (CI)** builda imagem e push para GHCR
3. **FluxCD** detecta nova tag no ImageRepository
4. **ImagePolicy** seleciona a tag (ex: `>=1.0.0`)
5. **ImageUpdateAutomation** atualiza o Git
6. **Kustomize/Helm Controller** aplica as mudanças
7. **Cluster** executa rollout gradual

### Deploy Manual Via Git

Para fazer deploy manual sem novo build:

```bash
# 1. Atualizar tag no HelmRelease
cd infrastructure/fluxcd/clusters/prod/services
vim gateway-intencoes.yaml
# Alterar: tag: "1.0.0" → tag: "1.1.0"

# 2. Commit e push
git add gateway-intencoes.yaml
git commit -m "feat: deploy gateway-intencoes v1.1.0"
git push origin main

# 3. FluxCD sincroniza automaticamente
flux reconcile kustomization neural-hive-mind --with-source
```

### Deploy Manual Via CLI

Para forçar sync imediato:

```bash
# Sincronizar todos os recursos
flux reconcile source git neural-hive-mind
flux reconcile kustomization --all

# Sincronizar kustomization específica
flux reconcile kustomization core-services

# Sincronizar HelmRelease específico
flux reconcile helmrelease gateway-intencoes
```

## Configuração de Automação de Imagem

### ImageRepository

Define qual registro do Docker monitorar:

```yaml
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageRepository
metadata:
  name: gateway-intencoes
  namespace: flux-system
spec:
  image: ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes
  interval: 5m  # Verifica a cada 5 minutos
  secretRef:
    name: ghcr-credentials  # Credenciais para registry privado
```

### ImagePolicy

Define qual versão/tag usar:

```yaml
# SemVer - usa versão mais recente dentro do range
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImagePolicy
metadata:
  name: gateway-intencoes-semver
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: gateway-intencoes
  policy:
    semver:
      range: ">=1.0.0"
```

### Marcador de Automação (Setter)

No HelmRelease, usar o marcador para auto-update:

```yaml
values:
  image:
    tag: "1.0.0" # {"$imagepolicy": "flux-system:gateway-intencoes-semver"}
```

## Operações

### Monitoramento

```bash
# Status geral dos componentes FluxCD
flux get sources all
flux get kustomizations
flux get helmreleases

# Logs de um controller específico
flux logs source-controller
flux logs kustomize-controller

# Eventos recentes
flux events --for kustomization
```

### Troubleshooting

```bash
# Verificar se um recurso está sincronizado
flux get kustomization infrastructure

# Suspender sincronização
flux suspend kustomization core-services

# Retomar sincronização
flux resume kustomization core-services

# Recuperar de estado degradado
flux reconcile kustomization --all

# Verificar saúde de um HelmRelease
flux get helmrelease gateway-intencoes
flux logs helm-controller --filter kind=HelmRelease
```

### Rollback

```bash
# Opção 1: Via Git (recomendado)
git revert <commit-hash>
git push origin main
flux reconcile kustomization --all

# Opção 2: Via Helm (emergência)
helm rollback gateway-intencoes -n neural-hive

# Opção 3: Suspendendo FluxCD e usando kubectl
flux suspend kustomization core-services
kubectl set image deployment/gateway-intencoes \
  gateway-intencoes=ghcr.io/...:previous-tag -n neural-hive
flux resume kustomization core-services
```

## Segurança

### RBAC

FluxCD é instalado com permissões mínimas necessárias:

- Namespace: `flux-system`
- ServiceAccount: `flux-system/helm-controller`
- ClusterRole: `cluster-admin` (pode ser reduzido)

### Segredos

- **SSH Key:** Acesso ao repositório Git
- **GHCR Credentials:** Pull de imagens privadas
- **SOPS GPG:** Descriptografia de segredos

### Network Policies

FluxCD respeita Network Policies configuradas:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-flux-system
  namespace: flux-system
spec:
  podSelector: {}
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 443  # GitHub API
```

## Melhores Práticas

### 1. Branch Strategy

- `main`: Produção, sincronizado automaticamente
- `develop`: Desenvolvimento, sincronizado automaticamente
- `feat/*`: Feature branches, não sincronizados

### 2. Versionamento de Imagens

- **Produção:** Usar SemVer (`>=1.0.0`, `>=2.0.0`)
- **Desenvolvimento:** Usar `latest` ou `main` branch

### 3. Health Checks

Configure health checks para todos os serviços:

```yaml
healthChecks:
  - apiVersion: apps/v1
    kind: Deployment
    name: gateway-intencoes
    namespace: neural-hive
```

### 4. Pruning

Habilitar pruning para remover recursos não mais declarados:

```yaml
spec:
  prune: true  # Remove recursos não mais no Git
```

### 5. Dependencies

Definir dependências entre Kustomizations:

```yaml
spec:
  dependsOn:
    - name: infrastructure
```

## Migração do workflow_dispatch

### Antes (Manual)

```yaml
# .github/workflows/deploy-to-cluster.yml
on:
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [development, staging, production]
```

**Problemas:**
- Deploy manual obrigatório
- Sem rastreabilidade Git
- Difficult rollback
- Não é verdadeiro GitOps

### Depois (Automático)

```yaml
# FluxCD sincroniza automaticamente
# Push para main → Deploy automático em prod
# Push para develop → Deploy automático em dev
```

**Benefícios:**
- Deploy automático
- Rastreabilidade Git completa
- Rollback via `git revert`
- Verdadeiro GitOps

## Referências

- [FluxCD Documentation](https://fluxcd.io/docs/)
- [FluxCD Image Automation](https://fluxcd.io/docs/components/image/)
- [Helm Controller Guide](https://fluxcd.io/docs/components/helm/helmreleases/)

## Support

Para problemas ou dúvidas:

1. Verificar logs: `flux logs <controller>`
2. Verificar status: `flux get kustomizations`
3. Consultar documentação oficial do FluxCD
4. Abrir issue no repositório do projeto
