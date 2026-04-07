# FLUXCD-001 Design: GitOps Foundation

**Data:** 2026-04-07
**Status:** Design Aprovado
**Fase:** 1 de 3 (Fundação GitOps)
**Estimativa:** M (1 semana)

---

## Resumo Executivo

Implementar fundação GitOps com FluxCD para Neural-Hive-Mind usando monorepo existente. Fase 1 foca em: criar cluster staging, adicionar Kustomizations para 8 serviços core, implementar promoção automática dev→staging, e configurar ImageUpdateAutomation.

---

## Arquitectura

### Fluxo GitOps

```
┌─────────────────────────────────────────────────────────────┐
│                    Neural-Hive-Mind Monorepo                │
├─────────────────────────────────────────────────────────────┤
│  services/              → Código fonte                      │
│  helm-charts/          → Charts Helm                        │
│  infrastructure/fluxcd/ → Manifests GitOps                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   GitHub Actions (CI)                       │
├─────────────────────────────────────────────────────────────┤
│  develop branch → Tests → Build → Push GHCR → tag:dev       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    FluxCD Clusters                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Dev         │  │ Staging     │  │ Prod        │         │
│  │ ─────────── │  │ ─────────── │  │ ─────────── │         │
│  │ Sync: 30s   │ → │ Sync: 2m    │ → │ Sync: 5m    │         │
│  │ Auto        │  │ Auto        │  │ Manual      │         │
│  │ Tag: dev    │  │ Tag: v1.2.3 │  │ Tag: exact  │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### Estrutura de Directórios

```
infrastructure/fluxcd/
├── clusters/
│   ├── dev/
│   │   ├── flux-system/
│   │   │   ├── gotk-components.yaml      ✅ Já existe
│   │   │   └── kustomization.yaml
│   │   ├── infrastructure/
│   │   │   └── kustomization.yaml        ✅ Já existe
│   │   ├── services/                     ✅ Parcial
│   │   │   ├── gateway-intencoes.yaml    ✅ Já existe
│   │   │   ├── worker-agents.yaml        ✅ Já existe
│   │   │   ├── semantic-translation-engine.yaml  ⬜ Criar
│   │   │   ├── consensus-engine.yaml     ⬜ Criar
│   │   │   ├── orchestrator-dynamic.yaml ⬜ Criar
│   │   │   ├── approval-service.yaml     ⬜ Criar
│   │   │   ├── queen-agent.yaml          ⬜ Criar
│   │   │   └── service-registry.yaml     ⬜ Criar
│   │   ├── specialists/
│   │   │   └── business-specialist.yaml  ✅ Já existe
│   │   └── agents/
│   │       └── worker-agents.yaml        ✅ Já existe
│   ├── staging/                          ⬜ CRIAR NOVO
│   │   ├── flux-system/
│   │   │   ├── gotk-components.yaml
│   │   │   └── kustomization.yaml
│   │   ├── infrastructure/
│   │   │   └── kustomization.yaml
│   │   ├── services/                     ⬜ Criar 8 Kustomizations
│   │   ├── specialists/
│   │   └── agents/
│   └── prod/
│       └── [estrutura similar, já existe parcialmente]
└── apps/
    └── base-helm-release/                ⬜ Criar template base
```

---

## Componentes

### 1. Kustomization por Serviço

Cada serviço tem uma Kustomization FluxCD que aponta para o seu Helm chart:

```yaml
# infrastructure/fluxcd/clusters/dev/services/semantic-translation-engine.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: semantic-translation-engine
  namespace: flux-system
spec:
  interval: 2m
  retryInterval: 30s
  timeout: 3m
  sourceRef:
    kind: GitRepository
    name: neural-hive-mind
  path: ./helm-charts/semantic-translation-engine
  targetNamespace: neural-hive-dev
  prune: true
  dependsOn:
    - name: infrastructure
  images:
    - name: ghcr.io/albinojimy/neural-hive-mind/semantic-translation-engine
      tag: "dev" # Substituído por ImagePolicy
```

### 2. ImageRepository e ImagePolicy

**Dev (usa tag mais recente):**
```yaml
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageRepository
metadata:
  name: semantic-translation-engine
  namespace: flux-system
spec:
  image: ghcr.io/albinojimy/neural-hive-mind/semantic-translation-engine
  interval: 1m
  secretRef:
    name: ghcr-credentials

---
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImagePolicy
metadata:
  name: semantic-translation-engine-dev
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: semantic-translation-engine
  policy:
    alphabetical:
      order: desc
```

**Staging (usa semver):**
```yaml
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImagePolicy
metadata:
  name: semantic-translation-engine-staging
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: semantic-translation-engine
  policy:
    semver:
      range: ">=1.0.0-0"
```

### 3. ImageUpdateAutomation

Atualiza automaticamente as tags de imagem no Git:

```yaml
# infrastructure/fluxcd/clusters/dev/flux-system/image-automation.yaml
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageUpdateAutomation
metadata:
  name: dev-images
  namespace: flux-system
spec:
  interval: 1m
  sourceRef:
    kind: GitRepository
    name: neural-hive-mind
  gitCommitMessage:
    prefix: "[flux-dev] "
  update:
    strategy: Setters
    paths:
      - ./infrastructure/fluxcd/clusters/dev
```

### 4. Promoção Dev→Staging

```yaml
# infrastructure/fluxcd/clusters/staging/flux-system/gotk-components.yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: neural-hive-mind
  namespace: flux-system
spec:
  interval: 1m
  url: ssh://git@github.com/albinoJimy/Neural-Hive-Mind.git
  ref:
    branch: main  # Staging usa branch main (após merge)
  secretRef:
    name: neural-hive-mind-git-ssh
  ignore: |
    /*
    !/infrastructure/fluxcd
    !/helm-charts

---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: staging-services
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: neural-hive-mind
  path: ./infrastructure/fluxcd/clusters/staging/services
  targetNamespace: neural-hive-staging
  prune: true
```

---

## Serviços Core (Fase 1)

| # | Serviço | Chart | Dev Kustomization | Staging Kustomization |
|---|---------|-------|-------------------|----------------------|
| 1 | gateway-intencoes | ✅ | ✅ Existe | ⬜ Criar |
| 2 | semantic-translation-engine | ✅ | ⬜ Criar | ⬜ Criar |
| 3 | consensus-engine | ✅ | ⬜ Criar | ⬜ Criar |
| 4 | orchestrator-dynamic | ✅ | ⬜ Criar | ⬜ Criar |
| 5 | approval-service | ✅ | ⬜ Criar | ⬜ Criar |
| 6 | worker-agents | ✅ | ✅ Existe | ⬜ Criar |
| 7 | queen-agent | ✅ | ⬜ Criar | ⬜ Criar |
| 8 | service-registry | ✅ | ⬜ Criar | ⬜ Criar |

---

## Estratégia de Promoção

### Fluxo de Branches

```
develop ──merge──> main ──tag──> production
   │                  │            │
   ▼                  ▼            ▼
  Dev               Staging       Prod
 (auto)            (auto)       (manual)
```

1. **Dev:**
   - Branch: `develop`
   - Sync: 30s
   - Tag: `dev`
   - Promoção: Automática

2. **Staging:**
   - Branch: `main`
   - Sync: 2m
   - Tag: Semver (`v1.2.3`)
   - Promoção: Automática (após merge para main)

3. **Prod:**
   - Branch: `main` + tag explícita
   - Sync: 5m
   - Tag: Exacta (ex: `v1.2.3`)
   - Promoção: Manual via Git tag

---

## Configuração por Ambiente

| Config | Dev | Staging | Prod |
|--------|-----|---------|------|
| Branch | develop | main | main (tag) |
| Sync Interval | 30s | 2m | 5m |
| Image Policy | alphabetical | semver | exact |
| Prune | true | true | true |
| Auto-promote | ✅ | ✅ | ❌ |
| Notifications | ❌ | ⬜ Fase 2 | ⬜ Fase 2 |

---

## Fases Seguintes (Fora do Scope Actual)

- **Fase 2:** Notificações Slack, Drift Detection, Testes E2E
- **Fase 3:** External Secrets, OPA Gatekeeper, Observabilidade completa

---

## Acceptance Criteria

Fase 1 está completa quando:

- [ ] Cluster staging criado em `infrastructure/fluxcd/clusters/staging/`
- [ ] 8 serviços core têm Kustomizations em dev
- [ ] 8 serviços core têm Kustomizations em staging
- [ ] ImageRepository criado para cada serviço (dev)
- [ ] ImagePolicy criado para cada serviço (dev + staging)
- [ ] ImageUpdateAutomation funcional em dev
- [ ] Promoção automática dev→staging testada
- [ ] Documentação básica (README) criada

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Sobrecarga de commits (ImageUpdateAutomation) | Interval de 1m, commit em batch |
| Conflito de Kustomizações | Usar `dependsOn` para ordenar |
| Tags incorrectas em staging | Usar semver range validado |
| Delete acidental com prune=true | Revisar diffs antes de merge |

---

**Fim do Design**
