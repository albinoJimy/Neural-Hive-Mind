# Spec: OPA Gatekeeper - Instalação

**ID:** FASE0-002
**Status:** Planning
**Estimativa:** 8 dias (2 instalação + 5 policies + 1 enforcement)

---

## 1. Objetivo

Instalar OPA Gatekeeper para governance Kubernetes via policy-as-code, garantindo que apenas configurações conformes sejam aplicadas ao cluster Neural-Hive-Mind.

---

## 2. Contexto Atual

**Cluster:** Kubernetes v1.29.15, 38 namespaces

**Estado:**
- ❌ Gatekeeper namespace existe mas vazio (sem pods)
- ✅ Helm values existem em `environments/dev/helm-values/opa-gatekeeper-values.yaml`
- ✅ Istio sendo instalado (pré-requisito para policies de rede)

**Dependências:**
- Istio Service Mesh (FASE0-001) - para mTLS em policies de rede
- Prometheus - para métricas do Gatekeeper

---

## 3. Abordagem: Audit-First Framework

### 3.1 Fase 1: Instalação em Audit Mode (2 dias)

**Tasks:**
- [ ] 1.1 Adicionar repositório Gatekeeper Helm
- [ ] 1.2 Instalar Gatekeeper com valores dev/prod
- [ ] 1.3 Configurar `validatingWebhookFailurePolicy: Ignore`
- [ ] 1.4 Validar webhook registration
- [ ] 1.5 Verificar pods running (controller + audit)

**Artefatos:**
- `helm/gatekeeper/values.yaml` - Values atualizados

### 3.2 Fase 2: Definição de Policies (3 dias)

**Constraint Templates:**
- [ ] 2.1 `K8sRequiredLabels` - Garante labels obrigatórios
- [ ] 2.2 `K8sAllowedRepos` - Restringe image registries
- [ ] 2.3 `K8sDisallowAnonymous` - Bloqueia anonymous access
- [ ] 2.4 `K8sResourceQuota` - Limita recursos por namespace
- [ ] 2.5 `K8sContainerLimits` - Exige resource limits

**Constraints por Namespace:**
- [ ] 2.6 `neural-have`: Labels `app`, `component`, `part-of`
- [ ] 2.7 `production`: Resource quotas strictos
- [ ] 2.8 `kafka`: Security contexts restritos

**Artefatos:**
- `gatekeeper/constraints/` - Constraint templates
- `gatekeeper/constraints/constraints.yaml` - Constraints específicas

### 3.3 Fase 3: Ativação Gradual (2 dias)

**Tasks:**
- [ ] 3.1 Analisar violations coletadas em audit mode
- [ ] 3.2 Corrigir violations críticas
- [ ] 3.3 Mudar `validatingWebhookFailurePolicy` para Fail
- [ ] 3.4 Ativar constraints uma por vez
- [ ] 3.5 Monitorar e ajustar conforme necessário

**Artefatos:**
- `docs/runbooks/gatekeeper-enforcement.md` - Runbook de ativação

---

## 4. Configurações Técnicas

### 4.1 Helm Values

```yaml
gatekeeper:
  replicas: 2
  auditPodCount: 1
  controllerManager:
    resources:
      limits: { cpu: "1000m", memory: "1Gi" }
  audit:
    resources:
      limits: { cpu: "500m", memory: "512Mi" }
  enableMetrics: true
  metricsBackends: ["prometheus"]
  validatingWebhookFailurePolicy: Ignore  # Começa ignore
```

### 4.2 Constraint Template Example

```yaml
apiVersion: templates.gatekeeper.sh/v1
kind: ConstraintTemplate
metadata:
  name: k8srequiredlabels
spec:
  crd:
    spec:
      names:
        - kind: K8sRequiredLabels
  targets:
    - target: admission.k8s.io/v1
      rego: |
        package k8srequiredlabels
        violation[{"msg": msg}] {
          required := input.parameters.labels
          provided := input.review.object.metadata.labels
          missing := [label for label in required
            if not provided[label]]
          count(missing) > 0
          msg := sprintf("Missing required labels: %v", missing)
        }
```

### 4.3 Constraint Example

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
    namespaces: ["neural-hive"]
  parameters:
    repos:
      - "ghcr.io/albinojimy/neural-hive-mind"
      - "gcr.io/distroless"
```

---

## 5. Critérios de Aceitação

### Instalação
- [ ] Gatekeeper controller manager running (2/2 pods)
- [ ] Gatekeeper audit pod running
- [ ] Webhook configurado e registered
- [ ] Mutating webhook desabilitado (não precisamos)

### Audit Mode
- [ ] Audit mode coletando violations sem bloquear
- [ ] Logs de violations visíveis em Prometheus
- [ ] Relatório de violações gerado

### Enforcement
- [ ] Validating webhook ativo sem breaking changes
- [ ] Constraints aplicadas sem bloquear operações normais
- [ ] Testes de CI/CD falham em configs inválidas

### Observabilidade
- [ ] Métricas Gatekeeper exportadas para Prometheus
- [ ] Dashboards Grafana configurados
- [ ] Alertas configurados para violations

---

## 6. Testes

### Unitários
- [ ] Teste instalação Gatekeeper em cluster de teste
- [ ] Teste constraint template syntax
- [ ] Teste constraint evaluation

### Integração
- [ ] Teste webhook bloqueando configs inválidas
- [ ] Teste CI/CD integration

### E2E
- [ ] Teste deployment completo com policies ativas
- [ ] Teste rollback de configuração inválida

---

## 7. Dependências

- Kubernetes v1.29+ ✓
- Helm 3.x ✓
- Prometheus ✓
- Istio Service Mesh (FASE0-001) ✓

---

## 8. Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Policy bloqueia deploy crítico | Audit mode primeiro, exemptions key namespaces |
| Performance degradation | Timeout configurado, réplicas adequadas |
| False positives em policies | Review periódico, rollback mecanismo |
| OPA queries lentas | Test queries antes de aplicar |

---

**Fim da Spec**
