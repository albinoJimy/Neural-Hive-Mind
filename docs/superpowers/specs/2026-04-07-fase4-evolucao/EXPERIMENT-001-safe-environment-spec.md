# EXPERIMENT-001: Ambiente Isolado para Experimentos

**Data:** 2026-04-07
**Prioridade:** ALTA
**Estimativa:** L (2-3 semanas)

---

## Metadata

| Campo | Valor |
|-------|-------|
| Componente | Safe Experimentation Environment |
| Localização | infrastructure/kubernetes/experiments/ |
| Status Atual | PARCIAL (40%) |
| Status Alvo | IMPLEMENTADO (95%+) |

---

## 1. Validação Funcionalidade

### 1.1 Funcionalidade Esperada

Baseado na especificação da Fase 4, o componente deve:
- Prover ambiente Kubernetes isolado para experimentos
- Implementar quotas de recursos (CPU, memory, pods)
- Aplicar políticas de rede (network policies)
- Isolar secrets e configurações
- Permitir escalabilidade independente

### 1.2 Funcionalidade Implementada

**Atual:**
- Namespaces K8s genéricos existem (não específicos para experimentos)
- Algumas quotas definidas (não específicas)
- Isolamento básico através de namespaces

**Gaps Identificados:**
- ❌ Namespace dedicado para experimentos não existe
- ❌ Quotas específicas para experimentos não definidas
- ❌ Network policies para isolamento de experimentos
- ❌ Secret management específico para experimentos
- ❌ Resource limits por tipo de experimento

### 1.3 Gaps de Funcionalidade

- [ ] EXPERIMENT-001-01: Criar namespace `experiments` dedicado
- [ ] EXPERIMENT-001-02: Definir ResourceQuota para experiments
- [ ] EXPERIMENT-001-03: Criar NetworkPolicy para isolamento
- [ ] EXPERIMENT-001-04: Implementar LimitRange para pods
- [ ] EXPERIMENT-001-05: Criar RoleBinding para acesso específico
- [ ] EXPERIMENT-001-06: Isolar secrets por ambiente de experimento

---

## 2. Validação Testes

### 2.1 Cobertura Unitária

**Atual:** N/A

**Gaps:**
- [ ] EXPERIMENT-001-07: Testar criação de namespace
- [ ] EXPERIMENT-001-08: Testar aplicação de quotas
- [ ] EXPERIMENT-001-09: Testar network policies
- [ ] EXPERIMENT-001-10: Testar resource limits

### 2.2 Cobertura Integração

**Gaps:**
- [ ] EXPERIMENT-001-11: Teste E2E de deploy de experimento em namespace isolado
- [ ] EXPERIMENT-001-12: Teste de limites de recursos (OOM, CPU throttling)
- [ ] EXPERIMENT-001-13: Teste de isolamento de rede

---

## 3. Validação Integração

### 3.1 Dependências Externas

| Serviço | Método | Status |
|---------|--------|--------|
| Kubernetes API | client-go | ⚠️ Parcial |
| Prometheus | metrics | ✅ |
| Kafka | events | ⚠️ Parcial |

### 3.2 Gaps de Integração

- [ ] EXPERIMENT-001-14: Integração com ExperimentationEngine para criar namespace dinamicamente
- [ ] EXPERIMENT-001-15: Notificação Kafka quando experimento é criado/destruído
- [ ] EXPERIMENT-001-16: Métricas Prometheus de resource usage por namespace

---

## 4. Validação Observabilidade

### 4.1 Métricas Prometheus

**Gaps:**
- [ ] EXPERIMENT-001-17: `experiment_namespace_cpu_usage`
- [ ] EXPERIMENT-001-18: `experiment_namespace_memory_usage`
- [ ] EXPERIMENT-001-19: `experiment_pod_count`
- [ ] EXPERIMENT-001-20: `experiment_resource_quota_exceeded`

### 4.2 Tracing OpenTelemetry

**Gaps:**
- [ ] EXPERIMENT-001-21: Spans para criação/destruição de namespace
- [ ] EXPERIMENT-001-22: Spans para aplicação de políticas

### 4.3 Logging Structlog

**Gaps:**
- [ ] EXPERIMENT-001-23: Logs estruturados para operações de namespace
- [ ] EXPERIMENT-001-24: Logs de eventos de quota

---

## 5. Validação Documentação

### 5.1 Documentação Técnica

| Doc | Existe | Localização |
|-----|--------|-------------|
| README | ❌ | — |
| Arquitetura | ❌ | — |
| Runbooks | ❌ | — |

### 5.2 Gaps de Documentação

- [ ] EXPERIMENT-001-25: README com instruções de uso
- [ ] EXPERIMENT-001-26: Diagrama de arquitetura de isolamento
- [ ] EXPERIMENT-001-27: Runbook de troubleshooting de quotas
- [ ] EXPERIMENT-001-28: Guia de boas práticas para experimentos

---

## 6. Tickets Decompostos

### EXPERIMENT-001-01: Criar namespace `experiments` dedicado

**Tipo:** feature
**Estimativa:** XS (1 dia)

**Descrição:**
Criar namespace Kubernetes dedicado para experimentos com configuração base.

**Acceptance Criteria:**
- [ ] Namespace `nhm-experiments` criado
- [ ] Labels aplicados: `environment=experiments`, `managed-by=nhm`
- [ ] Annotations para documentação
- [ ] Teste de criação/destruição
- [ ] Documentação no README

---

### EXPERIMENT-001-02: Definir ResourceQuota para experiments

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Implementar ResourceQuota específico para limitar recursos consumidos por experimentos.

**Acceptance Criteria:**
- [ ] ResourceQuota `experiments-quota` criado
- [ ] Limits: CPU=8, Memory=16Gi, Pods=20, PersistentVolumeClaims=5
- [ ] Configuração via Helm values
- [ ] Testes de limit enforcement
- [ ] Documentação de como ajustar quotas

---

### EXPERIMENT-001-03: Criar NetworkPolicy para isolamento

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Implementar NetworkPolicy para isolar tráfego de experimentos.

**Acceptance Criteria:**
- [ ] NetworkPolicy `experiments-deny-all` criada
- [ ] Regras seletivas para comunicação necessária
- [ ] Isolamento de egress para Internet
- [ ] Testes de conectividade
- [ ] Documentação de regras

---

### EXPERIMENT-001-04: Implementar LimitRange para pods

**Tipo:** feature
**Estimativa:** S (2-3 dias)

**Descrição:**
Implementar LimitRange para garantir defaults de recursos para pods de experimentos.

**Acceptance Criteria:**
- [ ] LimitRange `experiments-limits` criado
- [ ] Defaults: CPU=100m, Memory=128Mi
- [ ] Max: CPU=2, Memory=4Gi
- [ ] Testes de aplicação de limits
- [ ] Documentação de valores

---

### EXPERIMENT-001-05: Criar RoleBinding para acesso específico

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Implementar RBAC específico para controle de acesso ao namespace de experimentos.

**Acceptance Criteria:**
- [ ] Role `experiments-admin` criada
- [ ] Role `experiments-viewer` criada
- [ ] RoleBindings para grupos apropriados
- [ ] ServiceAccount para experiment pods
- [ ] Testes de permissões
- [ ] Documentação de RBAC

---

### EXPERIMENT-001-06: Isolar secrets por ambiente de experimento

**Tipo:** feature
**Estimativa:** M (1 semana)

**Descrição:**
Implementar segregação de secrets específicos para experimentos.

**Acceptance Criteria:**
- [ ] Secrets específicos no namespace experiments
- [ ] External Secrets Operator integrado
- [ ] Rotação automática de secrets
- [ ] Testes de acesso a secrets
- [ ] Documentação de gerenciamento

---

## 7. Resumo Executivo

**Completude Atual:** 40%
**Completude Alvo:** 95%
**Gaps Totais:** 28
**Tickets Propostos:** 6 (acima) + 22 (detalhados nos gaps)
**Estimativa Total:** L (2-3 semanas)

**Dependências:**
- Cluster Kubernetes com capacidade
- Helm 3+
- kubectl configurado

**Riscos:**
- Complexidade de network policies pode impactar debugging
- Quotas muito restritivas podem impedir experimentos válidos

**Mitigações:**
- Começar com quotas permissivas e ajustar com base em métricas
- Network policies com modo "audit" inicialmente
- Documentação clara de como solicitar aumento de quotas
