# Gatekeeper Audit Mode - Guia Operacional

**Data:** 2026-04-11
**Componente:** OPA Gatekeeper
**Status:** Audit Mode (não-bloqueante)

---

## 1. O que é Audit Mode?

O **Audit Mode** é o estado inicial do Gatekeeper onde as políticas são **avaliadas mas não aplicadas**. Isso permite:

- Coletar violações sem bloquear operações
- Entender o estado atual de conformidade do cluster
- Criar e testar policies antes de enforcement
- Identificar workloads que precisam de ajuste

### Comportamento

| Operação | Audit Mode | Enforcement Mode |
|----------|------------|-------------------|
| Criar pod violando política | ✅ Permitido | ❌ Bloqueado |
| Deploy sem labels obrigatórias | ✅ Permitido | ❌ Bloqueado |
| Registrar violação | ✅ Sim | ✅ Sim |
| Exportar métricas | ✅ Sim | ✅ Sim |

---

## 2. Configuração Atual

**Helm Values:** `helm/gatekeeper/values.yaml`

```yaml
replicas: 2
auditPodCount: 1
validatingWebhookFailurePolicy: Ignore  # KEY: Ignore violações no admission
enableDeleteOperations: false
```

**ValidatingWebhookConfiguration:** `failurePolicy: Ignore`

---

## 3. Constraint Templates Ativos

| Template | Propósito |
|----------|-----------|
| `K8sRequiredLabels` | Garante labels obrigatórios |
| `K8sAllowedRepos` | Restringe image registries |
| `K8sDisallowAnonymous` | Bloqueia anonymous access |
| `K8sContainerLimits` | Exige resource limits |
| `K8sResourceQuota` | Limita recursos por namespace |

---

## 4. Consultar Violações

### 4.1 Lista todas as violações

```bash
kubectl get constraints -A
kubectl get violation -A
```

### 4.2 Violações por constraint

```bash
# Ver detalhes de uma violação específica
kubectl describe k8srequiredlabelsViolations neural-hive-required-labels

# Listar violações em formato JSON
kubectl get violation -o json
```

### 4.3 Script automatizado

```bash
./scripts/gatekeeper-analyze-violations.sh
```

Saída esperada:
```
=== Gatekeeper Violations Report ===
Timestamp: 2026-04-11 10:30:00

Total Violations: 47
- K8sRequiredLabels: 23
- K8sAllowedRepos: 12
- K8sContainerLimits: 8
- K8sDisallowAnonymous: 4

Top Violating Namespaces:
- neural-hive: 18
- kafka: 12
- observability: 8
- default: 9
```

---

## 5. Análise de Violações

### 5.1 Classificação de Severidade

| Severidade | Descrição | Ação |
|------------|-----------|------|
| **Crítica** | Security issue, anonymous access | Imediata |
| **Alta** | Sem resource limits, registry não aprovado | 24h |
| **Média** | Labels faltando, config inconsistente | 48h |
| **Baixa** | Labels opcionais, documentation | 7 dias |

### 5.2 Exemplo de Análise

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabelsViolations
metadata:
  name: neural-hive-required-labels
spec:
  violationCount: 18
  totalViolations: 18
  violations:
    - enforcementAction: dryrun
      kind: Pod
      message: 'Missing required labels: app, component'
      name: redis-old-66b84474ff-tv686
      namespace: neural-hive
```

---

## 6. Corrigir Violações

### 6.1 Manual

```bash
# Adicionar labels a um pod existente
kubectl label pod redis-old-66b84474ff-tv686 app=redis component=cache -n neural-hive
```

### 6.2 Script automatizado

```bash
./scripts/gatekeeper-fix-violations.sh --dry-run
./scripts/gatekeeper-fix-violations.sh --apply
```

### 6.3 Exemplos de correções

**Problema:** Container sem resource limits

```yaml
# ANTES (violação)
spec:
  containers:
    - name: app
      image: nginx:latest
```

```yaml
# DEPOIS (conforme)
spec:
  containers:
    - name: app
      image: nginx:latest
      resources:
        limits:
          cpu: "500m"
          memory: "512Mi"
        requests:
          cpu: "250m"
          memory: "256Mi"
```

**Problema:** Imagem de registry não aprovado

```yaml
# ANTES (violação)
image: myapp:latest  # registry não especificado
```

```yaml
# DEPOIS (conforme)
image: ghcr.io/albinojimy/neural-hive-mind/myapp:latest
```

---

## 7. Checklist para Enforcement

Antes de migrar para Enforcement Mode:

### Pré-requisitos

- [ ] Zero violações críticas
- [ ] < 10 violações altas
- [ ] Testes validados em staging
- [ ] Runbook de rollback preparado
- [ ] Equipe notificada

### Validação

- [ ] Executar `./scripts/gatekeeper-analyze-violations.sh`
- [ ] Revisar cada violação remanescente
- [ ] Documentar exemptions se necessário
- [ ] Testar deploy em staging

---

## 8. Transição para Enforcement

Quando estiver pronto para bloquear violações:

```bash
# 1. Ativar enforcement
./scripts/gatekeeper-enable-enforcement.sh

# 2. Verificar mudança
kubectl get validatingwebhookconfigurations gatekeeper-validating-webhook-configuration \
  -o jsonpath='{.webhooks[0].failurePolicy}'

# Deve retornar: Fail
```

Ver runbook completo: `docs/runbooks/gatekeeper-enforcement.md`

---

## 9. Métricas e Monitoramento

### Méas Prometheus disponíveis

```
gatekeeper_constraints{action="audit", status="active"}
gatekeeper_violations{constraint_name="neural-hive-required-labels"}
gatekeeper_audit_duration_seconds_bucket
```

### Dashboard Grafana

Importar: `helm/gatekeeper/prometheus-dashboard.json`

---

## 10. Troubleshooting

### Problema: Nenhuma violação aparece

```bash
# Verificar se audit pod está rodando
kubectl get pods -n gatekeeper-system -l control-plane=audit-controller

# Ver logs
kubectl logs -n gatekeeper-system -l control-plane=audit-controller --tail=100
```

### Problema: Violações não atualizam

```bash
# Restart audit pod
kubectl rollout restart deployment gatekeeper-audit -n gatekeeper-system

# Aguardar reconciliação
kubectl wait --for=condition=ready pod -l control-plane=audit-controller -n gatekeeper-system
```

---

## 11. Exemplos Práticos

### Exemplo 1: Criar nova constraint em audit mode

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8sdisallowlatesttag
spec:
  crd:
    spec:
      names:
        kind: K8sDisallowLatestTag
  targets:
    - target: admission.k8s.io/v1
      rego: |
        package k8sdisallowlatesttag
        violation[{"msg": msg}] {
          input.review.object.kind == "Pod"
          input.review.object.spec.containers[i].image == "latest"
          msg := "Containers with image tag 'latest' are not allowed"
        }
```

### Exemplo 2: Criar exemption temporária

```yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sAllowedRepos
metadata:
  name: neural-hive-allowed-repos
spec:
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Pod"]
    namespaces:
      - neural-hive
    # Exemption específica
    excludedNamespaces:
      - temp-testing  # namespace temporário
  parameters:
    repos:
      - "ghcr.io/albinojimy/neural-hive-mind"
```

---

**Fim do Guia Audit Mode**

Para migração para Enforcement: `docs/runbooks/gatekeeper-enforcement.md`
