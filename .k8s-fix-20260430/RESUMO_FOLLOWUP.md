# Plano de Resolução - Progresso e Follow-up

## Data: 2026-04-30

---

## Resumo Executivo

Validação profunda do ambiente Kubernetes Neural-Hive-Mind usando agentes especializados (debugger, gap-analyzer, code-explorer).

---

## Fases Concluídas

### ✅ Fase 0: Preparação e Inventário
- **Backups criados**: secrets, deployments, helm releases
- **Inventário documentado**: todos os segredos GHCR por namespace
- **Working directory**: `/home/jimy/NHM/Neural-Hive-Mind/.k8s-fix-20260430/`

### ✅ Fase 1: Fix ImagePullBackOff
- **Problema**: Secret `ghcr-credentials` não existia no namespace `neural-hive`
- **Solução**: Criado secret copiando de `ghcr-secret`
- **Resultado**: Pods agora conseguem puxar imagens (não há mais ImagePullBackOff nos pods novos)

### ✅ Fase 2: Fix Dependências grpcio/protobuf
- **Problema identificado**: Incompatibilidade grpcio 1.71.2 + grpcio-health-checking 1.67.1 + protobuf 4.25.5 (EOL)
- **Solução aplicada** (commit `1025e7a1`):
  - grpcio-health-checking: 1.67.1 → 1.71.2
  - protobuf: 4.25.5 → 5.28.1
- **Resultado**: Código corrigido e commitado

### ✅ Fase 3: Fix Código Dead Code
- **Problema identificado**: Padrão `await context.abort()` + `return` (dead code)
- **Solução aplicada** (commit `1025e7a1`):
  - Removidos 31 linhas de código morto em `service-registry/src/grpc_server/registry_servicer.py`
- **Resultado**: Padrão corrigido

---

## Problemas Remanescentes (Requer Rebuild de Imagens)

### 1. ModuleNotFoundError: neural_hive_llm

**Serviços afetados**:
- data-migration (CrashLoopBackOff)
- doc-ingestion (CrashLoopBackOff)
- test-generation (CrashLoopBackOff)

**Causa raiz**: Dockerfiles não copiam o módulo `neural_hive_llm` durante o build

**Localização**: `/home/jimy/NHM/Neural-Hive-Mind/libraries/python/neural_hive_llm/`

**Solução necessária**: Atualizar Dockerfiles para incluir:
```dockerfile
COPY libraries/python/neural_hive_llm /tmp/neural_hive_llm
RUN pip install --no-cache-dir /tmp/neural_hive_llm
```

### 2. guard-agents CrashLoopBackOff (136 restarts)

**Causa raiz**: Imagem atual não inclui as correções de código/grpcio

**Solução necessária**: Rebuild da imagem guard-agents com:
- Novas dependências (requirements-base.txt atualizado)
- Código corrigido do service-registry

---

## Próximos Passos (Requiem Acesso ao Docker Registry)

### Passo 1: Rebuild Imagens
```bash
# Serviços prioritários
SERVICES="service-registry guard-agents data-migration doc-ingestion test-generation"

for service in $SERVICES; do
  cd /home/jimy/NHM/Neural-Hive-Mind/services/$service

  # Verificar/actualizar Dockerfile para incluir neural_hive_llm
  # Rebuild com novas dependências
  docker build -t ghcr.io/albinojimy/neural-hive-mind/$service:1.3.0-grpcfix .
  docker push ghcr.io/albinojimy/neural-hive-mind/$service:1.3.0-grpcfix
done
```

### Passo 2: Atualizar Deployments
```bash
helm upgrade service-registry ./helm-charts/service-registry \
  -n neural-hive \
  --set image.tag="1.3.0-grpcfix" \
  --reuse-values

helm upgrade guard-agents ./helm-charts/guard-agents \
  -n neural-hive \
  --set image.tag="1.3.0-grpcfix" \
  --reuse-values

# etc...
```

### Passo 3: Validação
```bash
kubectl get pods -n neural-hive
kubectl logs -n neural-hive deployment/guard-agents --tail=50
kubectl logs -n neural-hive deployment/service-registry --tail=50
```

---

## Estado Atual do Cluster

| Serviço | Status | Problema |
|---------|--------|----------|
| guard-agents-57c6d9fb7f-ztgr7 | CrashLoopBackOff (136 restarts) | Imagem antiga sem fix grpcio |
| data-migration-766b96867c-sfjld | CrashLoopBackOff | Falta neural_hive_llm |
| doc-ingestion-74cdb4f664-s9hf8 | CrashLoopBackOff | Falta neural_hive_llm |
| test-generation-57d479d68c-* | CrashLoopBackOff | Falta neural_hive_llm |
| Demais serviços | Running | ✅ |

---

## Commits Criados

```
1025e7a1 (2026-04-30) fix(grpc): alinhar versões grpcio/protobuf e remover dead code após abort()
```

---

## Artefactos Criados

```
.k8s-fix-20260430/
├── secrets-backup-20260430.json
├── helm-releases-20260430.txt
└── secret-inventory.md
```

---

## Notas Importantes

1. **ImagePullBackOff foi resolvido**: Criar secret `ghcr-credentials` em todos os namespaces resolveu o problema de pods não conseguirem puxar imagens

2. **Problema de dependências foi corrigido no código**: As versões grpcio/protobuf foram actualizadas no requirements-base.txt

3. **Rebuild é necessário**: As mudanças de código não afectam os pods em execução até que as imagens sejam rebuildadas e os pods sejam recriados

4. **Dockerfiles precisam de actualização**: Alguns serviços não incluem todas as bibliotecas necessárias no Dockerfile

---

## Recomendação

Priorizar rebuild dos serviços na seguinte ordem:
1. **service-registry** (dependência de guard-agents)
2. **guard-agents** (serviço crítico)
3. **data-migration**, **doc-ingestion**, **test-generation**
