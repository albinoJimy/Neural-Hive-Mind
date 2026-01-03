# Política de Versionamento de Imagens

Este documento descreve a política de versionamento semântico para imagens Docker no projeto Neural Hive-Mind.

## Visão Geral

Todas as imagens Docker **DEVEM** usar tags de versão semântica. O uso de tags `:latest` é **proibido** em manifests de produção para garantir:

- **Reprodutibilidade**: Deployments podem ser reproduzidos de forma confiável
- **Segurança no Rollback**: Fácil rollback para versões específicas conhecidas
- **Auditabilidade**: Rastreamento claro de qual versão está rodando onde
- **Segurança**: Prevenir mudanças inesperadas de se propagarem

## Matriz de Versões

| Serviço | Versão Atual | Fonte |
|---------|--------------|-------|
| orchestrator-dynamic | 1.2.0 | helm-charts/orchestrator-dynamic/values.yaml |
| gateway-intencoes | 1.1.2 | helm-charts/gateway-intencoes/values.yaml |
| specialist-business | 1.0.8 | services/specialist-business/pyproject.toml |
| specialist-base | 1.0.0 | base-images/VERSIONS.md |
| neural-hive-ml-training | 1.0.7 | scripts/build.sh |
| neural-hive-ml-monitoring | 1.0.7 | scripts/build.sh |
| neural-hive-mind/pipelines | 1.0.7 | scripts/build.sh |
| curlimages/curl | 8.5.0 | Imagem externa |

## Fontes de Versionamento

### Helm Charts
Fonte primária para deployments versionados. Versão definida em `values.yaml`:

```yaml
image:
  repository: 37.60.241.150:30500/orchestrator-dynamic
  tag: "1.2.0"
```

### pyproject.toml
Para serviços Python, a versão é definida na configuração do projeto:

```toml
[tool.poetry]
version = "1.0.8"
```

### scripts/build.sh
Versão padrão do projeto para imagens ML e pipelines:

```bash
VERSION="${VERSION:-1.0.7}"
```

## Build com Versões Semânticas

### Serviço Individual
```bash
./scripts/build.sh --service orchestrator-dynamic --version 1.2.1
```

### Todos os Serviços
```bash
./scripts/build-all-optimized-services.sh --version 1.0.8
```

### Imagens de ML Training
```bash
docker build -t neural-hive-ml-training:1.0.7 -f ml_pipelines/Dockerfile.training .
```

## Atualizando Versões em Arquivos YAML

Ao lançar uma nova versão:

1. **Atualizar Helm Chart values.yaml**:
   ```yaml
   image:
     tag: "1.2.1"  # Versão atualizada
   ```

2. **Atualizar arquivos YAML standalone**:
   ```bash
   # Exemplo: Atualizar todas as referências de specialist-base
   sed -i 's/specialist-base:1.0.0/specialist-base:1.0.1/g' k8s/cronjobs/*.yaml
   ```

3. **Validar mudanças**:
   ```bash
   ./scripts/validate-image-tags.sh
   ```

## Validação

### Validação Pré-commit
Execute antes de commitar mudanças:
```bash
./scripts/validate-image-tags.sh
```

### Validação do Cluster
Verificar pods em execução para tags `:latest`:
```bash
./scripts/validate-image-tags.sh --cluster
```

### Validação de Existência em Registries
Verificar se as imagens configuradas existem nos registries:
```bash
./scripts/validate-image-tags.sh --registry
```

Esta opção valida que cada imagem na lista de imagens esperadas existe no seu respectivo registry:
- **Docker Hub**: Usa `docker manifest inspect`
- **AWS ECR**: Usa `aws ecr describe-images`
- **Registry Interno**: Usa a API HTTP do registry

### Validação CI/CD
O workflow do GitHub Actions `.github/workflows/validate-infrastructure.yml` verifica automaticamente:
1. Tags `:latest` em manifests (proibidas)
2. Existência das imagens esperadas nos registries

## Registries de Imagens

| Registry | Propósito |
|----------|-----------|
| 37.60.241.150:30500 | Registry interno (cluster Kubernetes) |
| docker.io/neural-hive | Imagens públicas Docker Hub |
| 077878370245.dkr.ecr.us-east-1.amazonaws.com | AWS ECR para produção |

### Padrão de Uso por Ambiente

| Ambiente | Registry | Exemplo |
|----------|----------|---------|
| **Desenvolvimento Local** | 37.60.241.150:30500 | `37.60.241.150:30500/gateway-intencoes:1.2.1` |
| **Produção AWS** | ECR | `077878370245.dkr.ecr.us-east-1.amazonaws.com/dev/consensus-engine:1.2.0` |
| **Imagens Base/Terceiros** | Docker Hub | `ghcr.io/mlflow/mlflow:v2.9.2` |

### Serviços por Registry (Atual)

**Registry Interno (37.60.241.150:30500)**:
- gateway-intencoes, memory-layer-api, mcp-tool-catalog
- optimizer-agents, worker-agents, scout-agents, guard-agents, analyst-agents
- orchestrator-dynamic, code-forge, service-registry, execution-ticket-service
- sla-management-system, self-healing-engine, explainability-api, queen-agent
- MCP servers (trivy, sonarqube, ai-codegen)

**AWS ECR**:
- consensus-engine, semantic-translation-engine
- specialist-business, specialist-technical, specialist-behavior
- specialist-evolution, specialist-architecture

> **Nota**: Especialistas e serviços cognitivos usam ECR por conterem modelos ML maiores.

### Verificando Existência de Imagens

```bash
# Registry interno
curl -s http://37.60.241.150:30500/v2/orchestrator-dynamic/tags/list | jq

# Docker Hub
docker manifest inspect docker.io/neural-hive/gateway-intencoes:1.1.2

# ECR
aws ecr describe-images \
  --repository-name neural-hive-mind/pipelines \
  --region us-east-1 \
  --image-ids imageTag=1.0.7
```

## Diretrizes para Bump de Versão

### Versão Patch (x.x.X)
- Correções de bugs
- Patches de segurança
- Melhorias menores

### Versão Minor (x.X.0)
- Novas features (compatíveis com versões anteriores)
- Mudanças de API não-breaking

### Versão Major (X.0.0)
- Mudanças breaking
- Atualizações de arquitetura maiores
- Mudanças de API incompatíveis

## Imagens Externas

Para imagens de terceiros, sempre fixar em versões específicas:

| Imagem | Versão Fixada | Notas |
|--------|---------------|-------|
| curlimages/curl | 8.5.0 | Release estável |
| python | 3.11-slim | Base para serviços |
| node | 20-alpine | Ferramentas de build |

## Troubleshooting

### Encontrando Referências `:latest`
```bash
grep -r "image:.*:latest" k8s/ helm-charts/ --include="*.yaml"
```

### Verificando Imagens de Pods no Cluster
```bash
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}' | grep latest
```

### Forçar Pull de Versão Específica
```bash
kubectl set image deployment/orchestrator-dynamic \
  orchestrator-dynamic=37.60.241.150:30500/orchestrator-dynamic:1.2.0 \
  --record
```

## Atualizando a Lista de Verificação de Imagens

Quando novas versões de imagens são introduzidas, a lista de imagens esperadas deve ser atualizada em **dois locais**:

### 1. Script de Validação Local

Edite `scripts/validate-image-tags.sh` e atualize o array `EXPECTED_IMAGES`:

```bash
# Expected images list - update this when introducing new versions
# Format: REGISTRY_TYPE|REPOSITORY|TAG
# REGISTRY_TYPE: dockerhub, ecr, internal
EXPECTED_IMAGES=(
    "dockerhub|curlimages/curl|8.5.0"
    "ecr|neural-hive-mind/pipelines|1.0.7"
    "ecr|neural-hive-ml-training|1.0.7"
    "ecr|neural-hive-ml-monitoring|1.0.7"
    # Adicione novas imagens aqui
)
```

### 2. Workflow de CI/CD

Edite `.github/workflows/validate-infrastructure.yml` e atualize o array `EXPECTED_IMAGES` no step "Validate image existence in registries":

```yaml
EXPECTED_IMAGES=(
  "dockerhub|curlimages/curl|8.5.0"
  "ecr|neural-hive-mind/pipelines|1.0.7"
  # Adicione novas imagens aqui
)
```

### Formato das Entradas

Cada entrada segue o formato: `REGISTRY_TYPE|REPOSITORY|TAG`

| Registry Type | Descrição | Exemplo |
|---------------|-----------|---------|
| `dockerhub` | Imagens do Docker Hub | `dockerhub|python|3.11-slim` |
| `ecr` | AWS Elastic Container Registry | `ecr|neural-hive-mind/service|1.0.0` |
| `internal` | Registry interno do cluster | `internal|orchestrator-dynamic|1.2.0` |

### Processo de Atualização

1. **Build e push** da nova versão da imagem para o registry apropriado
2. **Atualize** a Matriz de Versões no início deste documento
3. **Atualize** o array `EXPECTED_IMAGES` em ambos os locais
4. **Teste localmente** com `./scripts/validate-image-tags.sh --registry`
5. **Commit** as mudanças e crie um PR

### Exemplo: Atualizando uma Versão

Para atualizar `neural-hive-ml-training` de `1.0.7` para `1.0.8`:

```bash
# 1. Build e push da nova imagem
docker build -t neural-hive-ml-training:1.0.8 -f ml_pipelines/Dockerfile.training .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 077878370245.dkr.ecr.us-east-1.amazonaws.com
docker tag neural-hive-ml-training:1.0.8 077878370245.dkr.ecr.us-east-1.amazonaws.com/neural-hive-ml-training:1.0.8
docker push 077878370245.dkr.ecr.us-east-1.amazonaws.com/neural-hive-ml-training:1.0.8

# 2. Atualize EXPECTED_IMAGES em scripts/validate-image-tags.sh
# 3. Atualize EXPECTED_IMAGES em .github/workflows/validate-infrastructure.yml
# 4. Atualize a Matriz de Versões neste documento

# 5. Valide localmente
./scripts/validate-image-tags.sh --registry
```
