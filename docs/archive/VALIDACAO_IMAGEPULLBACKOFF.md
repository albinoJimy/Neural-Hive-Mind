# Validação da Correção de ImagePullBackOff

**Data**: 2025-11-15
**Status**: Correção Implementada - Aguardando Validação

---

## 1. Problema Original

### Componentes Afetados
Quatro componentes críticos do cluster Kubernetes apresentavam estado **ImagePullBackOff**:

1. **worker-agents** (namespace: neural-hive-execution)
2. **specialist-business** (namespace: specialist-business)
3. **consensus-engine** (namespace: consensus-engine)
4. **memory-layer-api** (namespace: memory-layer-api)

### Sintomas Observados
```bash
kubectl get pods -A | grep -E '(worker-agents|specialist-business|consensus-engine|memory-layer-api)'
```

Resultado esperado antes da correção:
- Pods em estado `ImagePullBackOff` ou `ErrImagePull`
- Eventos indicando falha ao pull de imagens
- Componentes indisponíveis para processamento

---

## 2. Causa Raiz

Foram identificadas **três causas principais**:

### 2.1. Build Script Incompleto
**Arquivo**: `build-fase1-componentes.sh`

**Problema**: O script construía apenas 3 das 5 imagens necessárias:
- ✓ semantic-translation-engine
- ✓ consensus-engine
- ✓ memory-layer-api
- ✗ **worker-agents** (AUSENTE)
- ✗ **specialist-business** (AUSENTE)

### 2.2. Inconsistência de Nomenclatura
**Problema**: Discrepância entre nomes de imagens construídas e esperadas pelos Helm charts:

| Componente | Build Script Criava | Helm Chart Esperava |
|------------|---------------------|---------------------|
| consensus-engine | `neural-hive-mind/consensus-engine:1.0.0` | `077878370245.dkr.ecr.us-east-1.amazonaws.com/dev/consensus-engine:1.0.7` (prod) |
| memory-layer-api | `neural-hive-mind/memory-layer-api:1.0.0` | `077878370245.dkr.ecr.us-east-1.amazonaws.com/dev/memory-layer-api:1.0.7` (prod) |
| worker-agents | N/A (não construída) | `neural-hive/worker-agents:1.0.0` |
| specialist-business | N/A (não construída) | `neural-hive/specialist-business:local` |

### 2.3. Scripts de Importação Incompletos
**Arquivos**: `import-images-to-containerd.sh` e `push-images-to-cluster.sh`

**Problema**: Scripts processavam apenas as 3 imagens do build script original, não incluindo worker-agents e specialist-business.

---

## 3. Solução Implementada

### 3.1. Alterações em Scripts de Build/Deploy

#### `build-fase1-componentes.sh`
**Linhas 49-55**: Adicionados 2 novos componentes ao array:
```bash
declare -A COMPONENTS=(
    ["semantic-translation-engine"]="neural-hive-mind/semantic-translation-engine"
    ["consensus-engine"]="neural-hive-mind/consensus-engine"
    ["memory-layer-api"]="neural-hive-mind/memory-layer-api"
    ["worker-agents"]="neural-hive-mind/worker-agents"              # NOVO
    ["specialist-business"]="neural-hive-mind/specialist-business"  # NOVO
)
```

#### `import-images-to-containerd.sh`
**Linhas 19-25**: Expandido array de imagens:
```bash
IMAGES=(
    "neural-hive-mind/semantic-translation-engine:1.0.0"
    "neural-hive-mind/memory-layer-api:1.0.0"
    "neural-hive-mind/consensus-engine:1.0.0"
    "neural-hive-mind/worker-agents:1.0.0"              # NOVO
    "neural-hive-mind/specialist-business:1.0.0"        # NOVO
)
```

#### `push-images-to-cluster.sh`
**Linhas 24-30**: Expandido array associativo:
```bash
declare -A IMAGES=(
    ["semantic-translation-engine"]="neural-hive-mind/semantic-translation-engine:1.0.0"
    ["memory-layer-api"]="neural-hive-mind/memory-layer-api:1.0.0"
    ["consensus-engine"]="neural-hive-mind/consensus-engine:1.0.0"
    ["worker-agents"]="neural-hive-mind/worker-agents:1.0.0"              # NOVO
    ["specialist-business"]="neural-hive-mind/specialist-business:1.0.0"  # NOVO
)
```

#### `deploy-fase1-componentes-faltantes.sh`
**Linhas 23-29**: Adicionados 2 componentes + lógica de namespace:
```bash
COMPONENTS=(
    "semantic-translation-engine"
    "consensus-engine"
    "memory-layer-api"
    "worker-agents"          # NOVO
    "specialist-business"    # NOVO
)

# Linhas 37-45: Mapeamento de namespace correto
case "$COMPONENT" in
    "worker-agents")
        NAMESPACE="neural-hive-execution"
        ;;
    "specialist-business")
        NAMESPACE="specialist-business"
        ;;
esac
```

### 3.2. Alterações em Helm Charts

#### `helm-charts/worker-agents/values.yaml`
**Linhas 1-4**: Atualizado para deployment remoto (produção):
```yaml
image:
  repository: 077878370245.dkr.ecr.us-east-1.amazonaws.com/neural-hive-mind/worker-agents
  tag: 1.0.7
  pullPolicy: IfNotPresent
```

#### `helm-charts/worker-agents/values-local.yaml`
**Linhas 7-10**: Atualizado para deployment local:
```yaml
image:
  repository: neural-hive-mind/worker-agents  # Era: sem repository definido
  tag: 1.0.0
  pullPolicy: Never                           # Era: IfNotPresent
```

#### `helm-charts/specialist-business/values-local.yaml`
**Linhas 7-10**: Alinhado com build script (já estava correto):
```yaml
image:
  repository: neural-hive-mind/specialist-business
  tag: 1.0.0
  pullPolicy: Never
```

#### `helm-charts/consensus-engine/values-local.yaml`
**Linhas 7-10**: Adicionado repository override (já estava correto):
```yaml
image:
  repository: neural-hive-mind/consensus-engine
  pullPolicy: Never
  tag: "1.0.0"
```

#### `helm-charts/memory-layer-api/values-local.yaml`
**Linhas 7-10**: Adicionado repository override e tag (já estava correto):
```yaml
image:
  repository: neural-hive-mind/memory-layer-api
  tag: "1.0.0"
  pullPolicy: Never
```

#### `helm-charts/semantic-translation-engine/values-local.yaml`
**Linhas 7-10**: Atualizado para incluir repository e tag completos:
```yaml
image:
  repository: neural-hive-mind/semantic-translation-engine  # NOVO
  tag: 1.0.0                                               # NOVO
  pullPolicy: Never                                         # Era: IfNotPresent
```

---

## 4. Comandos de Validação

### 4.1. Verificar Imagens no Docker Local
```bash
# Verificar todas as 5 imagens foram construídas
docker images | grep neural-hive-mind | grep 1.0.0

# Esperado:
# neural-hive-mind/semantic-translation-engine   1.0.0
# neural-hive-mind/consensus-engine              1.0.0
# neural-hive-mind/memory-layer-api              1.0.0
# neural-hive-mind/worker-agents                 1.0.0
# neural-hive-mind/specialist-business           1.0.0
```

### 4.2. Verificar Imagens no Containerd
```bash
# Listar imagens importadas no namespace k8s.io
sudo ctr -n k8s.io images ls | grep neural-hive-mind

# Esperado: Todas as 5 imagens listadas com tag 1.0.0
```

### 4.3. Verificar Status dos Pods
```bash
# Verificar pods dos 4 componentes afetados
kubectl get pods -A | grep -E '(worker-agents|specialist-business|consensus-engine|memory-layer-api)'

# Esperado: Todos pods em estado Running (não ImagePullBackOff)
```

### 4.4. Verificar Eventos de ImagePull
```bash
# Verificar eventos recentes de pull de imagem
kubectl get events -A --sort-by='.lastTimestamp' | grep -i image | tail -20

# Esperado: Mensagens "Successfully pulled image" ou nenhum erro de pull
```

### 4.5. Verificar Logs dos Pods
```bash
# Worker Agents
kubectl logs -n neural-hive-execution deployment/worker-agents --tail=50

# Specialist Business
kubectl logs -n specialist-business deployment/specialist-business --tail=50

# Consensus Engine
kubectl logs -n consensus-engine deployment/consensus-engine --tail=50

# Memory Layer API
kubectl logs -n memory-layer-api deployment/memory-layer-api --tail=50

# Esperado: Logs de inicialização sem erros de imagem
```

### 4.6. Verificar Descrição dos Pods
```bash
# Verificar eventos e condições do pod
kubectl describe pod -n neural-hive-execution -l app=worker-agents
kubectl describe pod -n specialist-business -l app=specialist-business
kubectl describe pod -n consensus-engine -l app=consensus-engine
kubectl describe pod -n memory-layer-api -l app=memory-layer-api

# Esperado: Events sem "Failed to pull image" ou "Back-off pulling image"
```

---

## 5. Critérios de Sucesso

A validação será considerada **bem-sucedida** quando:

### ✅ Checklist de Validação

- [ ] **Build**: Todas as 5 imagens construídas localmente (verificar com `docker images`)
- [ ] **Import**: Todas as 5 imagens presentes no containerd (verificar com `ctr images ls`)
- [ ] **Pods Running**: Todos os 4 componentes em estado `Running` com `READY 1/1`
- [ ] **Zero Restarts**: Contadores de restart em `0` ou baixos (sem crash loops)
- [ ] **Eventos Limpos**: Sem eventos de `ImagePullBackOff` ou `ErrImagePull` nos últimos 10 minutos
- [ ] **Logs Saudáveis**: Logs dos pods mostram inicialização bem-sucedida
- [ ] **ImagePullPolicy**: Todos os values-local.yaml com `pullPolicy: Never`
- [ ] **Repository Correto**: Todos os values-local.yaml apontando para `neural-hive-mind/*`

### Comando de Validação Rápida
```bash
# Executa todas as verificações essenciais
echo "=== IMAGENS NO DOCKER ==="
docker images | grep neural-hive-mind | grep 1.0.0 | wc -l  # Deve retornar 5

echo "=== IMAGENS NO CONTAINERD ==="
sudo ctr -n k8s.io images ls | grep neural-hive-mind | wc -l  # Deve retornar 5

echo "=== STATUS DOS PODS ==="
kubectl get pods -A | grep -E '(worker-agents|specialist-business|consensus-engine|memory-layer-api)' | grep -v Running | wc -l  # Deve retornar 0

echo "=== EVENTOS DE IMAGEPULL RECENTES ==="
kubectl get events -A --sort-by='.lastTimestamp' | grep -i imagepull | tail -10
```

---

## 6. Troubleshooting

### Problema: Pod ainda em ImagePullBackOff após correção

**Possíveis Causas**:
1. Imagem não foi importada no containerd
2. Nome da imagem não corresponde ao esperado
3. imagePullPolicy não está como `Never`
4. Cache do Kubernetes ainda tentando pull remoto

**Soluções**:
```bash
# 1. Verificar imagem no containerd do node
sudo ctr -n k8s.io images ls | grep <nome-componente>

# 2. Reimportar imagem se necessário
./import-images-to-containerd.sh

# 3. Verificar values do Helm chart
helm get values <componente> -n <namespace>

# 4. Forçar recriação do pod
kubectl delete pod -n <namespace> -l app=<componente>
kubectl rollout restart deployment/<componente> -n <namespace>
```

### Problema: Imagem no containerd mas pod não inicia

**Verificar**:
```bash
# Ver eventos detalhados do pod
kubectl describe pod -n <namespace> <pod-name>

# Verificar se a tag corresponde
kubectl get deployment <componente> -n <namespace> -o yaml | grep image:
```

**Solução**:
```bash
# Se tag estiver errada, atualizar values-local.yaml e re-deploy
helm upgrade --install <componente> ./helm-charts/<componente> \
    --namespace <namespace> \
    --values ./helm-charts/<componente>/values-local.yaml
```

### Problema: "image not found" mesmo com pullPolicy: Never

**Causa**: A imagem pode estar no namespace default do containerd ao invés de k8s.io

**Solução**:
```bash
# Verificar em qual namespace a imagem está
sudo ctr namespaces ls
sudo ctr -n default images ls | grep neural-hive-mind
sudo ctr -n k8s.io images ls | grep neural-hive-mind

# Se estiver no namespace errado, exportar e reimportar
sudo ctr -n default images export /tmp/image.tar neural-hive-mind/<componente>:1.0.0
sudo ctr -n k8s.io images import /tmp/image.tar
```

---

## 7. Próximos Passos (Após Validação Bem-Sucedida)

Uma vez que os 4 componentes estejam em estado `Running`:

### 7.1. Fase 2: Redistribuição de Pods
- Redistribuir pods entre worker nodes para balanceamento
- Verificar limites de recursos e ajustar se necessário
- Documentado em: `CHECKLIST_GOVERNANCE_DEPLOYMENT.md`

### 7.2. Fase 3: Credenciais MongoDB/MLflow
- Corrigir autenticação do specialist-business com MongoDB
- Configurar credenciais MLflow para modelos
- Referência: `helm-charts/specialist-business/values-local.yaml` linhas 118-120

### 7.3. Fase 4: Limpeza de Pods Órfãos
- Identificar e remover pods órfãos de deployments antigos
- Validar que apenas pods gerenciados estão rodando
- Comando: `kubectl get pods -A --field-selector status.phase=Failed`

### 7.4. Teste End-to-End
```bash
# Executar teste completo da Fase 1
./tests/phase1-end-to-end-test.sh --continue-on-error

# Verificar resultados em:
# - logs/e2e-test-<timestamp>/
# - RESULTADO_TESTE_E2E.txt
```

---

## 8. Histórico de Alterações

| Data | Versão | Autor | Descrição |
|------|--------|-------|-----------|
| 2025-11-15 | 1.0 | Claude Code | Criação inicial - Documentação da correção de ImagePullBackOff |

---

## 9. Referências

### Arquivos Modificados
- `build-fase1-componentes.sh` (mantém IMAGE_TAG variável)
- `import-images-to-containerd.sh` (atualizado com IMAGE_TAG variável e docker image inspect)
- `push-images-to-cluster.sh` (atualizado com IMAGE_TAG variável e docker image inspect)
- `deploy-fase1-componentes-faltantes.sh`
- `helm-charts/worker-agents/values.yaml` (revertido para registry remoto)
- `helm-charts/worker-agents/values-local.yaml` (atualizado com image completa)
- `helm-charts/specialist-business/values-local.yaml` (verificado)
- `helm-charts/consensus-engine/values-local.yaml` (verificado)
- `helm-charts/memory-layer-api/values-local.yaml` (verificado)
- `helm-charts/semantic-translation-engine/values-local.yaml` (atualizado com image completa)

### Dockerfiles Validados
- `services/worker-agents/Dockerfile`
- `services/specialist-business/Dockerfile`
- `services/semantic-translation-engine/Dockerfile`
- `services/consensus-engine/Dockerfile`
- `services/memory-layer-api/Dockerfile`

### Documentação Relacionada
- `PHASE1_TESTING_GUIDE.md` - Guia de testes da Fase 1
- `CHECKLIST_GOVERNANCE_DEPLOYMENT.md` - Checklist de governança
- `DEPLOYMENT_EKS_GUIDE.md` - Guia de deployment em EKS
- `COMANDOS_UTEIS.md` - Comandos úteis do cluster

---

**Nota**: Este documento deve ser atualizado com os resultados da validação após a execução dos scripts de build, import e deploy.
