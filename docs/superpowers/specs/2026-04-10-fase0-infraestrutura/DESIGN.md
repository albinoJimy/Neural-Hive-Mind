# Design: Fase 0 - Infraestrutura Gaps

**Data:** 2026-04-10
**Autor:** Claude Code + Superpowers
**Status:** Design Aprovado

---

## 1. Overview

Este documento consolida as especificações para fechar os 3 gaps críticos identificados na Fase 0 - Infraestrutura do Neural-Hive-Mind:

1. **Istio Service Mesh** - Instalação com mTLS STRICT em rollout incremental
2. **OPA Gatekeeper** - Policy-as-code com abordagem audit-first
3. **Redis Cluster** - Migração zero-downtime para cluster mode com TLS

**Status Atual do Cluster:**
- Kubernetes v1.29.15 self-hosted (5 nós)
- 38 namespaces, 48 pods running
- Redis Operator instalado (mas single pod)
- Gatekeeper namespace vazio (sem pods)
- Istio não instalado

---

## 2. Estratégia de Implementação

### 2.1 Ordem de Execução

```
┌─────────────────────────────────────────────────────────────┐
│  WAVE 1: Istio Base (mTLS foundation)                       │
│  - Instala Istio control plane + ingress gateway              │
│  - Configura mTLS permissive (allow mutual TLS)             │
│  - Rollout incremental por namespace                          │
│  Estimativa: 2 dias instalação + 7 dias rollout              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  WAVE 2: OPA Gatekeeper (governance foundation)            │
│  - Instala Gatekeeper em modo audit-only                     │
│  - Define constraint templates básicas                        │
│  - Ativa enforcement gradualmente                            │
│  Estimativa: 2 dias instalação + 5 dias policies            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  WAVE 3: Redis Cluster (remove SPOF)                         │
│  - Deploy Redis Cluster via Operator existente                │
│  - Migra dados com zero downtime                             │
│  - Configura TLS e cluster validation                        │
│  Estimativa: 3 dias cluster + 3 dias migração                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Racionale

1. **Istio primeiro** - Estabelece a base de segurança (mTLS) antes de adicionar políticas restritivas
2. **Gatekeeper depois** - Precisa de mTLS funcionando para policies de segurança de rede
3. **Redis por último** - Remove SPOF crítico, mas pode ser feito sem afetar tráfego aplicacional

---

## 3. Gap 1: Istio Service Mesh

### 3.1 Objetivo

Instalar e configurar Istio Service Mesh com mTLS STRICT para garantir comunicação segura entre todos os serviços do Neural-Hive-Mind.

### 3.2 Abordagem: Rollout Incremental

**Fase 1: Instalação Base (2 dias)**
- Instalar Istio via Helm com values dev/prod existentes
- Configurar IngressGateway (LoadBalancer)
- Instalar Prometheus, Grafana, Jaeger integrados
- Validar que control plane está healthy

**Fase 2: Rollout por Namespace (7 dias)**
- Lista de namespaces em ordem de prioridade:
  1. `neural-hive` - Core services (gateway, orchestrator, etc.)
  2. `approval`, `neural-hive-orchestration` - Serviços críticos
  3. `kafka`, `redis-cluster` - Infraestrutura de dados
  4. `observability` - Monitoring e tracing
  5. Demais namespaces - Rollout final

**Fase 3: Ativação mTLS STRICT (2 dias)**
- Começa com `PERMISSIVE` mode
- Valida comunicação entre serviços
- Migra para `STRICT` mode gradualmente

### 3.3 Arquitetura Técnica

```
                    ┌──────────────────────┐
                    │  IngressGateway      │
                    │  (LoadBalancer)       │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │   Istiod (Pilot)     │
                    │   Control Plane       │
                    └───────────┬──────────┘
                                │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    ┌────▼────┐         ┌─────▼─────┐      ┌─────▼─────┐
    │ neural- │         │  kafka   │      │  redis    │
    │ hive    │         │          │      │  cluster  │
    │         │         │          │      │           │
    └─────────┘         └───────────┘      └───────────┘
     (mTLS)               (mTLS)              (mTLS)
```

### 3.4 Configurações Chave

**Istio Operator:**
```yaml
istiod:
  replicaCount: 2  # HA para prod
  env:
    PILOT_ENABLE_WORKLOAD_ENTRY_AUTOREGISTRATION: true

global:
  proxy:
    autoInject: enabled
    logLevel: info  # debug para dev

meshConfig:
  mtls:
    mode: PERMISSIVE  # Começa permissive, migra para STRICT
```

**Namespaces:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: neural-hive
  labels:
    istio-injection: enabled
    istio.io_rev: "default"
```

### 3.5 Critérios de Aceitação

- [ ] Istio control plane running (2 replicas)
- [ ] IngressGateway acessível via LoadBalancer
- [ ] Todos os namespaces core com sidecar injection
- [ ] mTLS mode PERMISSIVE validado
- [ ] mTLS mode STRICT ativado após validação
- [ ] Zero downtime de serviços durante rollout
- [ ] Dashboards Grafana observáveis

### 3.6 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|-------------|---------|------------|
| Sidecar injection falha | Média | Alto | Teste em namespace isolado primeiro |
| Performance degradation | Média | Alto | Resource quotas configuradas |
| Configuração mTLS quebra comms | Alta | Crítico | Rollback com PERMISSIVE mode |
| Certificado expira | Baixa | Médio | Cert-manager integrado |

---

## 4. Gap 2: OPA Gatekeeper

### 4.1 Objetivo

Instalar OPA Gatekeeper para governance Kubernetes via policy-as-code, garantindo que apenas configurações conformes são aplicadas ao cluster.

### 4.2 Abordagem: Audit-First Framework

**Fase 1: Instalação em Audit Mode (2 dias)**
- Instalar Gatekeeper via Helm com values dev/prod
- Configurar `validatingWebhookFailurePolicy: Ignore`
- Criar constraint templates básicos
- Coletar violations durante X dias

**Fase 2: Definição de Policies (3 dias)**
- Constraint templates: K8sRequiredLabels, K8sAllowedRepos, K8sDisallowAnonymous
- Constraints específicas por namespace
- Integração com CI/CD para validação pré-deploy

**Fase 3: Ativação Gradual (2 dias)**
- Mudar para `validatingWebhookFailurePolicy: Fail`
- Ativar constraints uma por vez
- Monitorar e ajustar conforme necessário

### 4.3 Arquitetura Técnica

```
┌──────────────────────────────────────────────────────────┐
│  Kubernetes API Server                                    │
│                                                              │
│  ┌──────────────────────────────────────────────────┐   │
│  │   Admission Webhook (ValidatingWebhook)          │   │
│  │                                                    │   │
│  │   ┌────────────────────────────────────────────┐ │   │
│  │   │  Gatekeeper Controller Manager             │ │   │
│  │   │  - Evaluates constraints                 │ │   │
│  │   │  - Queries OPA for decisions             │ │   │
│  │   └────────────────────────────────────────────┘ │   │
│  │                                                    │   │
│  │   ┌────────────────────────────────────────────┐ │   │
│  │   │  Gatekeeper Audit                          │ │   │
│  │   │  - Logs violations                         │ │   │
│  │   └────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  OPA Policy Engine│
                    │  (embedded pods)   │
                    └────────────────────┘
```

### 4.4 Configurações Chave

**Helm Values:**
```yaml
gatekeeper:
  replicas: 2  # HA para prod
  auditPodCount: 1
  controllerManager:
    resources:
      limits: { cpu: "1000m", memory: "1Gi" }
  audit:
    resources:
      limits: { cpu: "500m", memory: "512Mi" }
  enableMetrics: true
  metricsBackends: ["prometheus"]
```

**Constraint Template Example:**
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

### 4.5 Critérios de Aceitação

- [ ] Gatekeeper controller manager running (2 replicas)
- [ ] Gatekeeper audit pod running
- [ ] Webhook configurado e registered
- [ ] Constraint templates criados (K8sRequiredLabels, etc)
- [ ] Audit mode coletando violations
- [ ] Validating webhook ativado sem breaking changes
- [ ] Métricas Prometheus exportadas

### 4.6 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|-------------|---------|------------|
| Policy bloqueia deploy crítico | Alta | Crítico | Audit mode primeiro, exemptions key namespaces |
| Performance degradation | Baixa | Médio | Timeout configurado, replicas adequadas |
| False positives em policies | Média | Alto | Review periódico, rollback mecanismo |
| OPA queries lentas | Baixa | Médio | Test queries antes de aplicar |

---

## 5. Gap 3: Redis Cluster

### 5.1 Objetivo

Migrar de Redis single pod para Redis Cluster com TLS, eliminando SPOF e habilitando criptografia em trânsito.

### 5.2 Abordagem: Zero Downtime Migration

**Fase 1: Preparação (1 dia)**
- Valida Redis Operator instalado e funcional
- Cria backup dos dados actuais
- Configura DNS para Redis Cluster (service discovery)

**Fase 2: Deploy Redis Cluster (3 dias)**
- Deploy Redis Cluster com 6 masters (3 nodes x 2 replicas)
- Configura passwords TLS e CA
- Valida cluster health

**Fase 3: Migração Zero Downtime (3 dias)**
- Configura aplicação para usar novo Redis Cluster endpoint
- Utiliza sync tool para replicar dados em tempo real
- Switch DNS gradual para novo cluster
- Valida aplicação funcionando corretamente
- Remove pod antigo

### 5.3 Arquitetura Técnica

```
┌────────────────────────────────────────────────────────┐
│  Application Layer                                      │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐      │
│  │ Gateway     │  │ Orchestrator│  │  Analyst    │      │
│  │ (client)    │  │ (client)    │  │ (client)    │      │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘      │
│         │                │                │            │
│         └────────────────┴────────────────┴            │
│                        │                             │
│                ┌───────▼────────┐                     │
│                │  Redis Cluster  │                     │
│                │  6 masters      │                     │
│                │  3 nodes        │                     │
│                │  TLS enabled    │                     │
│                └─────────────────┘                     │
│                        │                             │
│                ┌───────▼────────┐                     │
│                │  Redis Old     │                     │
│                │  (single pod)   │                     │
│                └─────────────────┘                     │
│                  (migration phase)                       │
└────────────────────────────────────────────────────────┘
```

### 5.4 Configurações Chave

**Redis Cluster via Helm:**
```yaml
redis-cluster:
  enabled: true
  image:
    repository: redis
    tag: 7.2.4-alpine
  master:
    replicas: 3
  replication:
    replicas: 2
  tls:
    mode: mutual
    auth: true
    ca: |
      -----BEGIN CERTIFICATE-----
      ...
      -----END CERTIFICATE-----
```

**Service Discovery:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: redis-cluster
spec:
  clusterIP: None
  ports:
  - port: 6379
    targetPort: 6379
```

### 5.5 Critérios de Aceitação

- [ ] Redis Cluster running (6 pods across 3 nodes)
- [ ] TLS habilitado e validado
- [ ] Cluster health OK (redis-cli --cluster check)
- [ ] Dados migrados do pod antigo
- [ ] Aplicações conectando ao novo endpoint
- [ ] Pod antigo removido
- [ ] Zero downtime de aplicações

### 5.6 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|-------------|---------|------------|
| Dados perdidos na migração | Média | Crítico | Backup completo antes, sync tool |
| Aplicação não compatível com cluster mode | Média | Alto | Teste em staging, fallback para single |
| Performance degradation | Baixa | Médio | Resource quotas, monitoring |
| Certificados TLS expiram | Baixa | Alto | Cert-manager ou rotação manual |

---

## 6. Dependências Entre Gaps

```
┌─────────────┐
│   Istio     │  ← Foundation para mTLS
└──────┬──────┘
       │
       ├──→ Gatekeeper precisa de mTLS para policies de rede
       └──→ Redis Cluster precisa de mTLS para comunicação segura
```

### 6.1 Bloqueios

| Gap | Bloqueia | Desbloqueado por |
|-----|----------|------------------|
| Istio | Gatekeeper, Redis | Instalação completa |
| Gatekeeper | Redis | Istio mTLS running |
| Redis Cluster | - | Istio e Gatekeeper OK |

---

## 7. Estimativas de Esforço

| Gap | Instalação | Configuração | Testes | Total |
|-----|------------|--------------|--------|-------|
| Istio | 2 dias | 7 dias rollout | 2 dias | **11 dias** |
| Gatekeeper | 2 dias | 5 dias policies | 1 dia | **8 dias** |
| Redis Cluster | 3 dias | 3 dias migração | 2 dias | **8 dias** |
| **Total** | **7 dias** | **15 dias** | **5 dias** | **27 dias** (~4 semanas) |

---

## 8. Critérios de Sucesso

- ✅ Istio instalado com mTLS STRICT activado
- ✅ Gatekeeper enforced com policies ativas
- ✅ Redis Cluster rodando com TLS
- ✅ Zero downtime de aplicações
- ✅ Documentação criada para operação
- ✅ Playbooks de runbook para incidentes

---

**Fim do Design**
