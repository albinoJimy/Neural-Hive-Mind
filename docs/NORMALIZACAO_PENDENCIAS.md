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

| Namespace | Serviço | Imagem Atual | Status |
|-----------|---------|--------------|--------|
| fluxo-a | gateway-intencoes | `37.60.241.150:30500/gateway-intencoes:1.0.9` | ⚠️ Namespace obsoleto |
| neural-hive-execution | worker-agents | `ghcr.io/albinojimy/neural-hive-mind/worker-agents:2056771` | ✅ **MIGRADO** |

### Riscos

1. **Disponibilidade**: Registry local pode ficar indisponível
2. **Segurança**: Imagens não verificadas/assinadas
3. **Consistência**: Diferentes fontes de imagens no cluster

### 2.1 Bug Identificado na Imagem GHCR do worker-agents

**Data:** 2026-01-31
**Status:** ✅ CORRIGIDO

Ao tentar migrar `worker-agents` para GHCR, foi identificado um bug na imagem:

```
ModuleNotFoundError: No module named 'neural_hive_resilience'
```

**Causa Raiz Identificada:** A flag `--chown=worker-agent:worker-agent` estava faltando no comando COPY do Dockerfile (linha 36). Os pacotes eram copiados com ownership `root:root`, mas o container rodava como usuário `worker-agent`, impedindo a leitura dos módulos.

**Correção Aplicada:** Adicionado `--chown=worker-agent:worker-agent` ao COPY em `services/worker-agents/Dockerfile`:

```dockerfile
# Antes (QUEBRADO):
COPY --from=builder /root/.local /home/worker-agent/.local

# Depois (CORRIGIDO):
COPY --from=builder --chown=worker-agent:worker-agent /root/.local /home/worker-agent/.local
```

### 2.2 Outros Dockerfiles com Mesmo Bug

Durante a análise, identificamos e corrigimos o mesmo problema em outros serviços:

| Serviço | Status | Arquivo |
|---------|--------|---------|
| worker-agents | ✅ Corrigido | `services/worker-agents/Dockerfile` |
| approval-service | ✅ Corrigido | `services/approval-service/Dockerfile` |
| semantic-translation-engine | ✅ Corrigido | `services/semantic-translation-engine/Dockerfile` |
| self-healing-engine | ⚠️ Funciona (usa chown -R como fallback) | `services/self-healing-engine/Dockerfile` |
| sla-management-system | ⚠️ Funciona (usa chown -R como fallback) | `services/sla-management-system/Dockerfile` |

### Solução Recomendada

```bash
# 1. Rebuildar imagens corrigidas
gh workflow run build-and-push-ghcr.yml -f services="worker-agents"
gh workflow run build-and-push-ghcr.yml -f services="approval-service"
gh workflow run build-and-push-ghcr.yml -f services="semantic-translation-engine"

# 2. Então migrar worker-agents para GHCR
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

### Análise Detalhada (2026-01-31)

| Atributo | Valor |
|----------|-------|
| Idade do namespace | 71 dias |
| Pod restart | 2d16h atrás (provável reinício do node) |
| Imagem | `37.60.241.150:30500/gateway-intencoes:1.0.9` |
| Ingress/Istio | Nenhum configurado |
| Tráfego detectado | Apenas health checks do kubelet |
| Service exposto | ClusterIP apenas (não acessível externamente) |

### Recomendação: **REMOVER**

O namespace aparenta estar abandonado:
- Sem ingress = sem tráfego externo
- Sem VirtualService = sem mesh traffic
- Logs mostram apenas probes de saúde
- Versão muito antiga (1.0.9 vs produção)

```bash
# Backup antes de remover (opcional)
kubectl get all -n fluxo-a -o yaml > /tmp/fluxo-a-backup.yaml

# Remover namespace
kubectl delete namespace fluxo-a
```

**AGUARDANDO CONFIRMAÇÃO DO TIME**

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
- [x] **Análise profunda do bug `neural_hive_resilience`** - Causa raiz: falta de `--chown` no COPY do Dockerfile
- [x] **Correção de 3 Dockerfiles** com bug de permissões:
  - `services/worker-agents/Dockerfile`
  - `services/approval-service/Dockerfile`
  - `services/semantic-translation-engine/Dockerfile`

## Próximos Passos

1. [x] ~~**BLOQUEADO** - Corrigir dependência `neural_hive_resilience` no worker-agents~~ **CORRIGIDO**
2. [x] ~~Rebuildar imagens corrigidas via CI/CD~~ **BUILD #21545285452 SUCESSO**
3. [x] ~~Após rebuild, migrar worker-agents de registry legado para GHCR~~ **MIGRADO (tag: 2056771)**
4. [ ] Decidir com o time sobre namespace `fluxo-a` (remover ou atualizar)
5. [x] ~~Decidir estratégia de tagging (SHA vs Semver automático)~~ **IMPLEMENTADO**
   - CI/CD agora extrai versão do values.yaml automaticamente
   - Tags criadas em push para main: latest, SHA, branch, e versão do values.yaml
6. [x] ~~Atualizar documentação de testes~~ **CORRIGIDO** - namespaces atualizados em PLANO_TESTE_MANUAL_FLUXOS_A_C.md
7. [~] Fazer helm upgrade para aplicar labels padrão
   - ✅ consensus-engine atualizado (rev 2)
   - ⚠️ gateway-intencoes: **Requer refatoração do chart**
     - Múltiplos nil pointers: `schemaRegistry.tls`, `observability.jaeger`, `observability.neuralHive`, `config.rateLimit`, `config.security`
     - O chart foi criado com valores obrigatórios que a release atual não possui
     - Solução: Refatorar templates para usar checks de nil ou atualizar values da release
   - ⚠️ Deployments manuais (approval-service, opa, worker-agents em neural-hive): não gerenciados por Helm

---

## Métricas Atuais

| Métrica | Valor | Status |
|---------|-------|--------|
| ReplicaSets órfãos | 0 | ✅ |
| Pods terminados | 0 | ✅ |
| revisionHistoryLimit configurado | 100% | ✅ |
| Namespaces com labels | 5/5 | ✅ |
| Imagens em registry legado | 1 | ⚠️ (apenas gateway-intencoes em fluxo-a) |
| Deployments com `latest` | 10 | ⚠️ |
| Labels completos em deployments | 75% | ⚠️ |
| worker-agents migrado para GHCR | Sim | ✅ |
