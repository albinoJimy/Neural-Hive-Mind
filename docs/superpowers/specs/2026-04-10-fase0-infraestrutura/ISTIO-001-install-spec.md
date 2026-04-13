# Spec: Istio Service Mesh - Instalação

**ID:** FASE0-001
**Status:** Planning
**Estimativa:** 11 dias (2 instalação + 7 rollout + 2 mTLS strict)

---

## 1. Objetivo

Instalar e configurar Istio Service Mesh com mTLS STRICT para garantir comunicação segura entre todos os serviços do Neural-Hive-Mind, usando estratégia de rollout incremental.

---

## 2. Contexto Atual

**Cluster:** Kubernetes v1.29.15 self-hosted, 5 nós, 38 namespaces

**Estado:**
- ❌ Istio NÃO instalado
- ✅ Helm values existem em `environments/dev/helm-values/istio-values.yaml`
- ✅ OTEL Collector, Prometheus, Jaeger rodando em `observability`

**Serviços críticos:** gateway-intencoes, approval-service, orchestrator-dynamic, consensus-engine, etc.

---

## 3. Abordagem: Rollout Incremental

### 3.1 Fase 1: Instalação Base (2 dias)

**Tasks:**
- [ ] 1.1 Adicionar repositório Istio Helm
- [ ] 1.2 Instalar Istio base (istiod, ingress gateway, pilot)
- [ ] 1.3 Configurar integração com observabilidade existente
- [ ] 1.4 Validar control plane health
- [ ] 1.5 Testar namespace dummy com sidecar injection

**Artefatos:**
- `helm/istio-base/values.yaml` - Istio base values
- `helm/istio-base/install.sh` - Script de instalação

### 3.2 Fase 2: Rollout por Namespace (7 dias)

**Ordem de namespaces:**
1. `neural-hive` - Core services (gateway, orchestrator, etc.)
2. `approval`, `neural-hive-orchestration`
3. `kafka`, `redis-cluster`, `mongodb-cluster`
4. `observability`, `keycloak`
5. `neural-hive-mcp`, `neural-hive-mind`
6. Demais namespaces

**Tasks por namespace:**
- [ ] 2.1 Adicionar label `istio-injection=enabled`
- [ ] 2.2 Adicionar label `istio.io_rev: default`
- [ ] 2.3 Rollout deployments para reinjectar pods
- [ ] 2.4 Validar comunicação entre pods
- [ ] 2.5 Verificar métricas Prometheus

**Artefatos:**
- `scripts/istio-rollout.sh` - Script automatizado
- `docs/runbooks/istio-rollover.md` - Runbook de operação

### 3.3 Fase 3: Ativação mTLS STRICT (2 dias)

**Tasks:**
- [ ] 3.1 Validar modo PERMISSIVE funcionando
- [ ] 3.2 Identificar serviços que precisam de ajuste
- [ ] 3.3 Mudar meshConfig para STRICT mode
- [ ] 3.4 Testar comunicação entre serviços
- [ ] 3.5 Configurar cert-manager para certificados mTLS

**Artefatos:**
- `helm/istio-base/mtls-strict.yaml` - Config mTLS STRICT

---

## 4. Configurações Técnicas

### 4.1 Istio Base Values

```yaml
global:
  proxy:
    autoInject: enabled
    logLevel: info
  tracer:
    zipkin:
      address: otel-collector.observability.svc.cluster.local:9411

istiod:
  replicaCount: 2
  env:
    PILOT_ENABLE_WORKLOAD_ENTRY_AUTOREGISTRATION: true

meshConfig:
  mtls:
    mode: PERMISSIVE  # Começa permissive
```

### 4.2 Namespace Labels

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: neural-hive
  labels:
    istio-injection: enabled
    istio.io_rev: "default"
```

### 4.3 mTLS STRICT Config

```yaml
meshConfig:
  mtls:
    mode: STRICT
  automtls:
    allowedNamespaces:
      - neural-hive
      - kafka
      - redis-cluster
```

---

## 5. Critérios de Aceitação

### Instalação
- [ ] Istiod control plane running (2/2 pods ready)
- [ ] IngressGateway com LoadBalancer IP
- [ ] Prometheus adapter configurado
- [ ] Jaeger tracing integrado

### Rollout
- [ ] Todos os namespaces core com sidecar injection
- [ ] 100% dos pods com Envoy sidecar
- [ ] Zero downtime durante rollout

### mTLS
- [ ] mTLS mode PERMISSIVE validado
- [ ] mTLS mode STRICT ativado
- [ ] Comunicação entre serviços funcionando
- [ ] Certificados mTLS configurados

### Observabilidade
- [ ] Dashboards Grafana visíveis
- [ ] Métricas Istio exportadas
- [ ] Traces em Jaeger visíveis

---

## 6. Testes

### Unitários
- [ ] Teste instalação Istio em cluster de teste
- [ ] Teste sidecar injection

### Integração
- [ ] Teste comunicação pod-to-pod com mTLS
- [ ] Teste rollout namespace sem downtime

### E2E
- [ ] Teste fluxo completo gateway → backend com Istio
- [ ] Teste Observabilidade (traces, metrics)

---

## 7. Dependências

- Kubernetes v1.29+ ✓
- Helm 3.x ✓
- OTEL Collector ✓
- Prometheus ✓
- Jaeger ✓

---

## 8. Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Sidecar injection falha | Teste em namespace isolado |
| Performance degradation | Resource quotas configuradas |
| Configuração mTLS quebra comms | Rollback com PERMISSIVE |
| Certificados expiram | Cert-manager integrado |

---

**Fim da Spec**
