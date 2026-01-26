# Guia de Rebuild e Deploy com Kaniko

Este documento descreve o processo de rebuild e deploy de serviços Neural Hive-Mind usando Kaniko para builds in-cluster.

## Visao Geral

O processo de rebuild e deploy usando Kaniko permite construir imagens Docker diretamente no cluster Kubernetes, sem necessidade de Docker daemon local ou acesso externo a registries.

### Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLUXO DE REBUILD/DEPLOY                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Maquina Local]                    [Cluster Kubernetes]                    │
│                                                                             │
│  ┌─────────────┐    kubectl cp      ┌─────────────────────────────┐        │
│  │  Codigo     │ ─────────────────► │  PVC: kaniko-build-context  │        │
│  │  Fonte      │                    │  (5Gi - ReadWriteMany)      │        │
│  └─────────────┘                    └──────────────┬──────────────┘        │
│                                                    │                        │
│                                                    ▼                        │
│                                     ┌─────────────────────────────┐        │
│                                     │  Pod: kaniko-context-loader │        │
│                                     │  (monta PVCs)               │        │
│                                     └──────────────┬──────────────┘        │
│                                                    │                        │
│                                                    ▼                        │
│                                     ┌─────────────────────────────┐        │
│                                     │  Jobs Kaniko (paralelos)    │        │
│                                     │  - Lê codigo do PVC         │        │
│                                     │  - Build sem Docker daemon  │        │
│                                     │  - Push para registry       │        │
│                                     └──────────────┬──────────────┘        │
│                                                    │                        │
│                                                    ▼                        │
│                                     ┌─────────────────────────────┐        │
│                                     │  Registry Interno           │        │
│                                     │  docker-registry:5000       │        │
│                                     └──────────────┬──────────────┘        │
│                                                    │                        │
│                                                    ▼                        │
│                                     ┌─────────────────────────────┐        │
│                                     │  Deployments Atualizados    │        │
│                                     │  (rolling update)           │        │
│                                     └─────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Pre-requisitos

1. **Acesso ao cluster Kubernetes** com kubectl configurado
2. **Namespace `neural-hive`** criado
3. **Registry interno** (`docker-registry`) rodando no cluster
4. **StorageClass** para PVCs (preferencialmente NFS para ReadWriteMany)

## Estrutura de Arquivos

```
k8s/kaniko/
├── pvc-build-context.yaml      # PVCs para codigo e cache
├── configmap-build-config.yaml # Configuracoes de build
├── pod-context-loader.yaml     # Pod para receber codigo
└── job-kaniko-template.yaml    # Template de Job Kaniko

scripts/kaniko/
├── sync-code-to-pvc.sh         # Sincroniza codigo para PVC
├── kaniko-build.sh             # Executa builds com Kaniko
└── rebuild-and-deploy.sh       # Orquestrador completo
```

## Servicos Suportados

| Servico | Namespace | Dockerfile |
|---------|-----------|------------|
| analyst-agents | neural-hive | services/analyst-agents/Dockerfile |
| code-forge | neural-hive | services/code-forge/Dockerfile |
| execution-ticket-service | neural-hive | services/execution-ticket-service/Dockerfile |
| explainability-api | neural-hive | services/explainability-api/Dockerfile |
| gateway-intencoes | neural-hive | services/gateway-intencoes/Dockerfile |
| guard-agents | neural-hive | services/guard-agents/Dockerfile |
| mcp-tool-catalog | neural-hive | services/mcp-tool-catalog/Dockerfile |
| memory-layer-api | neural-hive | services/memory-layer-api/Dockerfile |
| orchestrator-dynamic | neural-hive | services/orchestrator-dynamic/Dockerfile |
| queen-agent | neural-hive | services/queen-agent/Dockerfile |
| scout-agents | neural-hive | services/scout-agents/Dockerfile |
| self-healing-engine | neural-hive | services/self-healing-engine/Dockerfile |
| service-registry | neural-hive | services/service-registry/Dockerfile |
| sla-management-system | neural-hive | services/sla-management-system/Dockerfile |

## Comandos Rapidos

### Rebuild e Deploy Completo

```bash
# Rebuild e deploy de todos os servicos modificados
./scripts/kaniko/rebuild-and-deploy.sh -t 1.0.8

# Com mais paralelismo
./scripts/kaniko/rebuild-and-deploy.sh -t 1.0.8 -p 5

# Dry-run (simulacao)
./scripts/kaniko/rebuild-and-deploy.sh -t 1.0.8 --dry-run
```

### Operacoes Individuais

```bash
# Apenas sincronizar codigo
./scripts/kaniko/sync-code-to-pvc.sh full

# Apenas build (codigo ja sincronizado)
./scripts/kaniko/kaniko-build.sh all -t 1.0.8

# Build de servico especifico
./scripts/kaniko/kaniko-build.sh build gateway-intencoes -t 1.0.8

# Verificar status
./scripts/kaniko/kaniko-build.sh status

# Ver logs de build
./scripts/kaniko/kaniko-build.sh logs gateway-intencoes
```

## Fluxo Detalhado

### Fase 1: Configuracao da Infraestrutura

```bash
# Aplicar PVCs e ConfigMaps
kubectl apply -f k8s/kaniko/pvc-build-context.yaml
kubectl apply -f k8s/kaniko/configmap-build-config.yaml
kubectl apply -f k8s/kaniko/pod-context-loader.yaml

# Aguardar PVCs
kubectl get pvc -n neural-hive | grep kaniko
```

### Fase 2: Sincronizacao de Codigo

```bash
# Sincronizacao completa
./scripts/kaniko/sync-code-to-pvc.sh full

# Sincronizacao incremental (apenas modificados)
./scripts/kaniko/sync-code-to-pvc.sh incremental

# Verificar conteudo
./scripts/kaniko/sync-code-to-pvc.sh status
```

### Fase 3: Build com Kaniko

```bash
# Build paralelo de todos
./scripts/kaniko/kaniko-build.sh all -t 1.0.8 -p 3

# Build sequencial (mais facil de debugar)
./scripts/kaniko/kaniko-build.sh sequential -t 1.0.8

# Build de servicos especificos
./scripts/kaniko/kaniko-build.sh parallel \
    -s "gateway-intencoes,queen-agent,orchestrator-dynamic" \
    -t 1.0.8
```

### Fase 4: Deploy

```bash
# Atualizar deployments (feito automaticamente pelo rebuild-and-deploy.sh)
# Ou manualmente:
kubectl set image deployment/gateway-intencoes \
    gateway-intencoes=docker-registry.registry.svc.cluster.local:5000/gateway-intencoes:1.0.8 \
    -n neural-hive

# Rolling restart
kubectl rollout restart deployment/gateway-intencoes -n neural-hive

# Verificar status
kubectl rollout status deployment/gateway-intencoes -n neural-hive
```

## Troubleshooting

### Build Falhou

```bash
# Ver logs do Job
kubectl logs -n neural-hive -l app=kaniko-build,service=<nome-servico>

# Ver descricao do Job
kubectl describe job kaniko-build-<nome-servico> -n neural-hive

# Limpar jobs falhos e tentar novamente
./scripts/kaniko/kaniko-build.sh cleanup
./scripts/kaniko/kaniko-build.sh build <nome-servico> -t 1.0.8
```

### PVC nao tem espaco

```bash
# Verificar uso do PVC
kubectl exec kaniko-context-loader -n neural-hive -- df -h /context

# Limpar cache
kubectl exec kaniko-context-loader -n neural-hive -- rm -rf /cache/*
```

### Dockerfile nao encontrado

```bash
# Verificar se o codigo foi sincronizado
kubectl exec kaniko-context-loader -n neural-hive -- ls -la /context/services/

# Resincronizar
./scripts/kaniko/sync-code-to-pvc.sh full
```

### Registry inacessivel

```bash
# Verificar se registry esta rodando
kubectl get pods -n registry

# Testar conectividade
kubectl run --rm -it test-registry --image=alpine:3.18 -n neural-hive -- \
    wget -qO- http://docker-registry.registry.svc.cluster.local:5000/v2/_catalog
```

## Configuracoes Avancadas

### Variaveis de Ambiente

```bash
# Namespace customizado
NAMESPACE=meu-namespace ./scripts/kaniko/rebuild-and-deploy.sh -t 1.0.8

# Registry customizado
REGISTRY_URL=meu-registry:5000 ./scripts/kaniko/kaniko-build.sh all -t 1.0.8

# Timeout de build maior
WAIT_TIMEOUT=900 ./scripts/kaniko/kaniko-build.sh all -t 1.0.8
```

### Recursos do Job Kaniko

Editar `k8s/kaniko/job-kaniko-template.yaml` para ajustar:

```yaml
resources:
  limits:
    memory: "4Gi"   # Aumentar para builds grandes
    cpu: "2"
  requests:
    memory: "2Gi"
    cpu: "1"
```

### Cache de Build

O cache do Kaniko e persistido no PVC `kaniko-cache`. Para limpar:

```bash
kubectl exec kaniko-context-loader -n neural-hive -- rm -rf /cache/*
```

## Integracao com CI/CD

### Exemplo GitLab CI

```yaml
rebuild-deploy:
  stage: deploy
  script:
    - ./scripts/kaniko/rebuild-and-deploy.sh -t $CI_COMMIT_TAG --skip-sync
  only:
    - tags
```

### Exemplo GitHub Actions

```yaml
jobs:
  rebuild-deploy:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v3
      - name: Rebuild and Deploy
        run: |
          ./scripts/kaniko/rebuild-and-deploy.sh -t ${{ github.ref_name }}
```

## Metricas e Monitoramento

Os Jobs Kaniko geram labels que podem ser usados para monitoramento:

```bash
# Jobs ativos
kubectl get jobs -n neural-hive -l app=kaniko-build

# Pods de build
kubectl get pods -n neural-hive -l app=kaniko-build

# Metricas via Prometheus (se configurado)
# kaniko_build_duration_seconds
# kaniko_build_success_total
# kaniko_build_failure_total
```

## Referencias

- [Kaniko Documentation](https://github.com/GoogleContainerTools/kaniko)
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
