# Guia de Validação do Timeout gRPC (Issue #2)

Este documento descreve como validar a correção do timeout gRPC no Consensus Engine.

## Background

### Problema
O timeout gRPC padrão de 5000ms (5s) era insuficiente para os Specialists, que levam ~6-8 segundos para processar devido a:
- Inferência de modelos ML (transformers/heurísticas)
- Análise de planos cognitivos complexos
- Geração de opiniões estruturadas

### Sintomas
- Todos os 5 specialists falhavam com erro de timeout gRPC
- Logs mostravam: "Timeout ao invocar especialista"
- Fluxo de consenso bloqueado completamente

### Solução
Aumentar o timeout para 15000ms (15s) nos arquivos de configuração Helm/Kubernetes.

**Nota sobre defaults**:
- O default em código (`settings.py`) permanece 5000ms para execuções locais/teste sem Kubernetes
- Em Kubernetes/produção, o valor 15000ms é injetado via ConfigMap (configurado nos Helm values)
- A env var `GRPC_TIMEOUT_MS` sobrescreve o default quando presente

## Arquivos Afetados

| Arquivo | Linha | Valor |
|---------|-------|-------|
| `environments/local/fluxo-c-config.yaml` | 46 | `grpcTimeoutMs: 15000` |
| `helm-charts/consensus-engine/values.yaml` | 52 | `grpcTimeoutMs: 15000` |
| `helm-charts/consensus-engine/values-local.yaml` | 77 | `grpcTimeoutMs: 15000` |
| `helm-charts/consensus-engine/values-local-generated.yaml` | 53 | `grpcTimeoutMs: 15000` |
| `helm-charts/consensus-engine/templates/configmap.yaml` | 31 | `GRPC_TIMEOUT_MS` |
| `services/consensus-engine/src/config/settings.py` | 59-66 | `grpc_timeout_ms` (default: 5000ms) |

## Validação Pré-Deployment

### 1. Verificar arquivos de configuração

```bash
# Verificar fluxo-c-config.yaml
grep -n "grpcTimeoutMs" environments/local/fluxo-c-config.yaml
# Esperado: 46:      grpcTimeoutMs: 15000

# Verificar values.yaml (produção)
grep -n "grpcTimeoutMs" helm-charts/consensus-engine/values.yaml
# Esperado: 52:    grpcTimeoutMs: 15000

# Verificar values-local.yaml
grep -n "grpcTimeoutMs" helm-charts/consensus-engine/values-local.yaml
# Esperado: 77:    grpcTimeoutMs: 15000

# Verificar configmap.yaml usa nome correto
grep -n "GRPC_TIMEOUT_MS" helm-charts/consensus-engine/templates/configmap.yaml
# Esperado: GRPC_TIMEOUT_MS (sem prefixo SPECIALIST_)
```

### 2. Validar template Helm

```bash
# Renderizar template e verificar valor
helm template consensus-engine helm-charts/consensus-engine \
  --values helm-charts/consensus-engine/values-local.yaml \
  | grep -A1 "GRPC_TIMEOUT_MS"
# Esperado: GRPC_TIMEOUT_MS: "15000"
```

## Deployment

### Opção A: Usando values-local.yaml (recomendado)

```bash
helm upgrade --install consensus-engine helm-charts/consensus-engine \
  --namespace consensus-orchestration \
  --create-namespace \
  --values helm-charts/consensus-engine/values-local.yaml
```

### Opção B: Usando values-local-generated.yaml

```bash
# Regenerar arquivo gerado (opcional)
bash docs/manual-deployment/scripts/12-prepare-fluxo-c-values.sh --force

# Deploy
helm upgrade --install consensus-engine helm-charts/consensus-engine \
  --namespace consensus-orchestration \
  --create-namespace \
  --values helm-charts/consensus-engine/values-local-generated.yaml
```

## Validação Pós-Deployment

### 1. Verificar ConfigMap

```bash
kubectl get configmap consensus-engine-config \
  -n consensus-orchestration \
  -o yaml | grep GRPC_TIMEOUT_MS
# Esperado: GRPC_TIMEOUT_MS: "15000"
```

### 2. Verificar variável de ambiente no pod

```bash
kubectl exec -n consensus-orchestration deployment/consensus-engine \
  -- env | grep GRPC_TIMEOUT_MS
# Esperado: GRPC_TIMEOUT_MS=15000
```

### 3. Verificar logs da aplicação

```bash
# Verificar que não há erros de timeout
kubectl logs -n consensus-orchestration deployment/consensus-engine \
  --tail=100 | grep -i "timeout"

# Verificar invocações de specialists bem-sucedidas
kubectl logs -n consensus-orchestration deployment/consensus-engine \
  --tail=100 | grep -i "especialistas invocados"
```

### 4. Testar fluxo E2E

```bash
# Enviar mensagem de teste para plans.ready
# Verificar que todos os 5 specialists respondem sem timeout
# Verificar que decisão consolidada é publicada em plans.consensus
```

## Troubleshooting

### ConfigMap mostra valor incorreto

**Causa**: Helm values não atualizados ou deploy não aplicado.

**Solução**:
```bash
# Verificar valores usados
helm get values consensus-engine -n consensus-orchestration

# Redeployar com valores corretos
helm upgrade consensus-engine helm-charts/consensus-engine \
  --namespace consensus-orchestration \
  --values helm-charts/consensus-engine/values-local.yaml
```

### Pod mostra valor incorreto

**Causa**: Pod não reiniciado após atualização do ConfigMap.

**Solução**:
```bash
# Reiniciar pods para pegar novo ConfigMap
kubectl rollout restart deployment/consensus-engine -n consensus-orchestration

# Aguardar rollout completar
kubectl rollout status deployment/consensus-engine -n consensus-orchestration
```

### Timeouts ainda ocorrem

**Causa**: Specialists com performance degradada ou timeout ainda insuficiente.

**Solução**:
1. Verificar logs dos Specialists:
   ```bash
   kubectl logs -n semantic-translation deployment/specialist-business --tail=50
   ```

2. Verificar métricas de latência dos Specialists

3. Se necessário, aumentar timeout para 20000ms ou 30000ms

### Erro de validação Pydantic

**Causa**: Nome da variável de ambiente incorreto.

**Solução**:
- ConfigMap deve usar `GRPC_TIMEOUT_MS` (não `SPECIALIST_GRPC_TIMEOUT_MS`)
- Pydantic Settings mapeia automaticamente para `grpc_timeout_ms` (case-insensitive)

## Rollback

Se ocorrerem problemas após o deploy:

```bash
# Listar histórico de releases
helm history consensus-engine -n consensus-orchestration

# Rollback para versão anterior
helm rollback consensus-engine <REVISION> -n consensus-orchestration
```

## Fluxo de Configuração

```
environments/local/fluxo-c-config.yaml (source)
         │
         ▼
12-prepare-fluxo-c-values.sh (generator)
         │
         ▼
values-local-generated.yaml (auto-generated)
         │
         ├── OU ──┐
         │        │
         ▼        ▼
values-local.yaml (manual, recomendado)
         │
         ▼
helm upgrade/install
         │
         ▼
templates/configmap.yaml (render)
         │
         ▼
ConfigMap: GRPC_TIMEOUT_MS="15000"
         │
         ▼
Pod: envFrom.configMapRef
         │
         ▼
Pydantic Settings: grpc_timeout_ms=15000
         │
         ▼
gRPC Client: timeout=15s
         │
         ▼
Specialists: processo ~6-8s ✓
```

## Referências

- Issue #2 - ALTO: Timeout gRPC insuficiente
- `services/consensus-engine/src/config/settings.py` - Definição do campo
- `helm-charts/consensus-engine/templates/configmap.yaml` - Template do ConfigMap
