# Pendências de Normalização e Consistência

> Documento gerado em: 2026-01-31
> Status: Em progresso

## Resumo Executivo

Este documento descreve as pendências identificadas durante a análise de normalização, higienização e consistência do cluster Neural Hive Mind.

---

## 1. Tags de Imagem Inconsistentes

### Problema

Os `values.yaml` dos Helm charts definem tags semver (ex: `v1.2.1`), mas o CI/CD só cria essas tags quando manualmente disparado com `workflow_dispatch` e `version_tag`. Na prática, as imagens são buildadas apenas com:
- `latest`
- `<commit-sha>` (ex: `17a5a4d`)
- `<branch-name>` (ex: `main`)

### Serviços Afetados (usando `latest` em produção)

| Serviço | Tag no values.yaml | Tag real em uso |
|---------|-------------------|-----------------|
| analyst-agents | 1.2.1 | latest |
| consensus-engine | 1.2.0 | latest |
| optimizer-agents | 1.2.1 | latest |
| specialist-architecture | 1.0.7 | latest |
| specialist-behavior | 1.0.7 | latest |
| specialist-business | 1.0.7 | latest |
| specialist-evolution | 1.0.7 | latest |
| specialist-technical | 1.0.7 | latest |
| worker-agents | 1.3.4 | latest |
| opa | - | latest |

### Riscos

1. **Rastreabilidade**: Impossível saber qual versão está em produção
2. **Rollback**: Difícil reverter para versão específica
3. **Reprodutibilidade**: Builds não determinísticos

### Solução Recomendada

**Opção A: Usar Commit SHA como tag padrão (Recomendado)**

```bash
# Atualizar deployments para usar SHA ao invés de latest
kubectl set image deployment/<service> \
  <service>=ghcr.io/albinojimy/neural-hive-mind/<service>:<commit-sha> \
  -n neural-hive
```

**Opção B: Automatizar semver no CI/CD**

Modificar `.github/workflows/build-and-push-ghcr.yml` para:
1. Ler versão do `values.yaml` do serviço
2. Criar tag semver automaticamente em pushes para `main`

Exemplo de implementação:
```yaml
- name: Extract version from values.yaml
  id: version
  run: |
    VERSION=$(grep -E "^\s*tag:" helm-charts/${{ matrix.service }}/values.yaml | head -1 | awk '{print $2}' | tr -d '"')
    echo "version=v${VERSION}" >> $GITHUB_OUTPUT

- name: Build e Push
  uses: docker/build-push-action@v5
  with:
    tags: |
      ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/${{ matrix.service }}:latest
      ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/${{ matrix.service }}:${{ steps.version.outputs.version }}
      ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/${{ matrix.service }}:${{ github.sha }}
```

---

## 2. Registry Legado em Uso

### Problema

Dois deployments ainda usam o registry local antigo (`37.60.241.150:30500`) ao invés do GHCR.

### Serviços Afetados

| Namespace | Serviço | Imagem Atual | Imagem Recomendada |
|-----------|---------|--------------|-------------------|
| fluxo-a | gateway-intencoes | `37.60.241.150:30500/gateway-intencoes:1.0.9` | `ghcr.io/albinojimy/neural-hive-mind/gateway-intencoes:17a5a4d` |
| neural-hive-execution | worker-agents | `37.60.241.150:30500/worker-agents:1.3.13` | **BLOQUEADO** - ver seção 2.1 |

### Riscos

1. **Disponibilidade**: Registry local pode ficar indisponível
2. **Segurança**: Imagens não verificadas/assinadas
3. **Consistência**: Diferentes fontes de imagens no cluster

### 2.1 Bug Identificado na Imagem GHCR do worker-agents

**Data:** 2026-01-31
**Status:** BLOQUEADO

Ao tentar migrar `worker-agents` para GHCR, foi identificado um bug na imagem:

```
ModuleNotFoundError: No module named 'neural_hive_resilience'
```

**Causa:** A imagem `ghcr.io/albinojimy/neural-hive-mind/worker-agents:latest` não inclui a dependência `neural_hive_resilience`.

**Ação necessária:** Corrigir o Dockerfile ou requirements do worker-agents para incluir o módulo faltante antes de migrar.

**Arquivo a verificar:** `services/worker-agents/requirements.txt` ou `Dockerfile`

### Solução Recomendada

```bash
# 1. PRIMEIRO: Corrigir dependência no worker-agents
# Adicionar neural_hive_resilience ao requirements.txt

# 2. Rebuildar imagem
gh workflow run build-and-push-ghcr.yml -f services="worker-agents"

# 3. Então migrar
kubectl set image deployment/worker-agents \
  worker-agents=ghcr.io/albinojimy/neural-hive-mind/worker-agents:latest \
  -n neural-hive-execution
```

---

## 3. Namespace `fluxo-a` Obsoleto

### Problema

O namespace `fluxo-a` contém uma versão muito antiga do gateway (1.0.9) enquanto produção usa `17a5a4d`.

### Análise Realizada (2026-01-31)

| Atributo | Valor |
|----------|-------|
| Data de criação | 2025-11-19 (72 dias) |
| Pods ativos | 1 (gateway-intencoes) |
| Última atividade | Sem eventos recentes |
| Imagem | `37.60.241.150:30500/gateway-intencoes:1.0.9` |
| Versão vs Produção | 1.0.9 vs 17a5a4d (muito desatualizado) |

### Status

- **Namespace aparenta estar inativo/abandonado**
- **Usa registry legado**
- **Versão muito antiga**

### Recomendação

1. **Verificar se ainda é necessário** - perguntar ao time
2. **Se necessário**: Atualizar para versão atual
3. **Se não necessário**: Remover namespace

```bash
# Verificar recursos antes de remover
kubectl get all -n fluxo-a

# Remover (após confirmação)
kubectl delete namespace fluxo-a
```

---

## 4. Labels Incompletos em Deployments

### Problema

Alguns deployments têm menos labels que o padrão (10 labels).

### Deployments Afetados

| Deployment | Labels Atuais | Esperado |
|------------|---------------|----------|
| fluxo-a/gateway-intencoes | 5 | 10 |
| neural-hive-data/postgres-sla | 1 | 10 |
| neural-hive/approval-service | 4 | 10 |
| neural-hive/opa | 1 | 10 |
| neural-hive/worker-agents | 4 | 10 |

### Solução

Fazer `helm upgrade` com os charts atualizados para aplicar labels padrão.

---

## 5. Documentação de Testes Incorreta

### Problema

O arquivo `docs/PLANO_TESTE_MANUAL_FLUXOS_A_C.md` referencia o namespace `gateway-intencoes` que não existe.

### Namespaces Corretos para Testes

| Ambiente | Namespace | Uso |
|----------|-----------|-----|
| Staging | `neural-hive-staging` | Testes antes de produção |
| Produção | `neural-hive` | Ambiente de produção |
| Legado | `fluxo-a` | Não usar - obsoleto |

### Solução

Atualizar documentação para usar namespaces corretos.

---

## Ações Já Executadas

- [x] Limpeza de 260 ReplicaSets órfãos
- [x] Remoção de 3 pods terminados
- [x] Adição de `revisionHistoryLimit: 3` em todos os deployments (30 deployments)
- [x] Normalização de labels nos namespaces (5 namespaces)
- [x] Commit do template Helm com `revisionHistoryLimit`
- [x] Tentativa de migração worker-agents para GHCR (bloqueado - bug identificado)
- [x] Análise do namespace fluxo-a (aparenta estar inativo)

## Próximos Passos

1. [ ] **BLOQUEADO** - Corrigir dependência `neural_hive_resilience` no worker-agents
2. [ ] Após correção, migrar worker-agents de registry legado para GHCR
3. [ ] Decidir com o time sobre namespace `fluxo-a` (remover ou atualizar)
4. [ ] Decidir estratégia de tagging (SHA vs Semver automático)
5. [ ] Atualizar documentação de testes
6. [ ] Fazer helm upgrade para aplicar labels padrão

---

## Métricas Atuais

| Métrica | Valor | Status |
|---------|-------|--------|
| ReplicaSets órfãos | 0 | ✅ |
| Pods terminados | 0 | ✅ |
| revisionHistoryLimit configurado | 100% | ✅ |
| Namespaces com labels | 5/5 | ✅ |
| Imagens em registry legado | 2 | ⚠️ |
| Deployments com `latest` | 10 | ⚠️ |
| Labels completos em deployments | 75% | ⚠️ |
