# HA-001 Kubernetes Probes - Análise de Gaps

**Data:** 2026-04-10
**Status:** ANÁLISE COMPLETA

---

## Resumo Executivo

**Descoberta Crítica:** Os endpoints de health check existem e estão bem implementados, mas os **Kubernetes probes não estão configurados** nos deployments.

---

## 1. Health Check Endpoints - Status por Serviço

| Serviço | /health | /ready | /live | /startup | /health/deep |
|---------|---------|--------|-------|----------|--------------|
| gateway-intencoes | ✅ | ✅ | ❌ | ❌ | ❌ |
| optimizer-agents | ✅ | ✅ (/health/ready) | ✅ (/health/live) | ✅ (/health/startup) | ✅ |
| queen-agent | ✅ | ✅ | ❌ | ❌ | ❌ |
| consensus-engine | ❌ | ❌ | ❌ | ❌ | ❌ |
| orchestrator-dynamic | ❌ | ❌ | ❌ | ❌ | ❌ |
| worker-agents | ❌ | ❌ | ❌ | ❌ | ❌ |
| analyst-agents | ❌ | ❌ | ❌ | ❌ | ❌ |
| scout-agents | ❌ | ❌ | ❌ | ❌ | ❌ |
| semantic-translation-engine | ❌ | ❌ | ❌ | ❌ | ❌ |
| approval-service | ✅ | ❌ | ❌ | ❌ | ❌ |
| self-healing-engine | ✅ | ❌ | ❌ | ❌ | ❌ |
| guard-agents | ✅ | ❌ | ❌ | ❌ | ❌ |
| execution-ticket-service | ✅ | ❌ | ❌ | ❌ | ❌ |

**Legenda:**
- ✅ Endpoint implementado
- ❌ Endpoint não implementado

---

## 2. Kubernetes Probes - Status por Helm Chart

| Serviço | livenessProbe | readinessProbe | startupProbe |
|---------|---------------|-----------------|---------------|
| gateway-intencoes | ❌ | ❌ | ❌ |
| consensus-engine | ❌ | ❌ | ❌ |
| orchestrator-dynamic | ❌ | ❌ | ❌ |
| worker-agents | ❌ | ❌ | ❌ |
| queen-agent | ❌ | ❌ | ❌ |
| optimizer-agents | ❌ | ❌ | ❌ |
| analyst-agents | ❌ | ❌ | ❌ |
| scout-agents | ❌ | ❌ | ❌ |
| semantic-translation-engine | ❌ | ❌ | ❌ |
| approval-service | ❌ | ❌ | ❌ |
| self-healing-engine | ❌ | ❌ | ❌ |
| guard-agents | ❌ | ❌ | ❌ |
| execution-ticket-service | ❌ | ❌ | ❌ |

**Status:** 0% dos serviços com K8s probes configurados

---

## 3. HPA e PDB - Status

| Serviço | HPA | PDB | minReplicas | maxReplicas |
|---------|-----|-----|-------------|-------------|
| gateway-intencoes | ✅ enabled | ✅ enabled | 3 | 10 |
| consensus-engine | ❌ disabled | ✅ enabled | - | - |
| orchestrator-dynamic | ✅ enabled | ✅ enabled | 2 | - |
| worker-agents | ✅ enabled | ❌ | 2 | - |
| queen-agent | ❌ disabled | ✅ enabled | 1 | - |
| optimizer-agents | ✅ enabled | ✅ enabled | 1 | - |
| analyst-agents | ✅ enabled | ✅ enabled | 1 | - |
| scout-agents | ✅ enabled | ✅ enabled | 2 | - |

---

## 4. Gaps Críticos Identificados

### Gap 1: Kubernetes Probes Não Configurados (CRÍTICO)

**Impacto:**
- Pods não são reiniciados automaticamente quando entram em estado unhealthy
- Tráfego pode ser enviado para pods que não estão prontos
- Slow-starting services podem receber tráfego antes de estarem prontos

**Serviços Afetados:** Todos (13/13)

**Solução:**
Adicionar probes nos deployments.yaml de todos os serviços:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: http
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3

startupProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 0
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 30  # 150 segundos total
```

---

### Gap 2: Health Check Endpoints Ausentes (ALTA PRIORIDADE)

**Serviços sem endpoints de health:**
- consensus-engine
- orchestrator-dynamic
- worker-agents
- analyst-agents
- scout-agents
- semantic-translation-engine

**Solução:**
Implementar endpoints mínimos `/health` e `/ready` usando neural_hive_observability.health

---

### Gap 3: HPA Desabilitado em Serviços Críticos (MÉDIA PRIORIDADE)

**Serviços com HPA desabilitado:**
- consensus-engine (componente crítico do pipeline)
- queen-agent (coordenação estratégica)

**Solução:**
Habilitar HPA e configurar minReplicas apropriado

---

## 5. Recomendações de Prioridade

### Fase Imediata (1-2 dias)
1. Adicionar Kubernetes probes em todos os serviços com endpoints existentes
2. Testar probe behavior em ambiente de dev

### Curto Prazo (1 semana)
1. Implementar endpoints `/health` e `/ready` em serviços sem health checks
2. Adicionar probes nesses serviços
3. Habilitar HPA em consensus-engine e queen-agent

### Médio Prazo (2 semanas)
1. Implementar `/health/deep` em serviços críticos
2. Adicionar startup probes para slow-starting services
3. Configurar alertas baseados em health status

---

## 6. Template de Probe Recomendado

```yaml
# values.yaml
healthChecks:
  liveness:
    enabled: true
    path: /health
    initialDelaySeconds: 30
    periodSeconds: 10
    timeoutSeconds: 5
    failureThreshold: 3
  readiness:
    enabled: true
    path: /ready
    initialDelaySeconds: 10
    periodSeconds: 5
    timeoutSeconds: 3
    failureThreshold: 3
  startup:
    enabled: true
    path: /health
    initialDelaySeconds: 0
    periodSeconds: 5
    timeoutSeconds: 3
    failureThreshold: 30

# deployment.yaml
{{- if .Values.healthChecks.liveness.enabled }}
livenessProbe:
  httpGet:
    path: {{ .Values.healthChecks.liveness.path }}
    port: http
  initialDelaySeconds: {{ .Values.healthChecks.liveness.initialDelaySeconds }}
  periodSeconds: {{ .Values.healthChecks.liveness.periodSeconds }}
  timeoutSeconds: {{ .Values.healthChecks.liveness.timeoutSeconds }}
  failureThreshold: {{ .Values.healthChecks.liveness.failureThreshold }}
{{- end }}

{{- if .Values.healthChecks.readiness.enabled }}
readinessProbe:
  httpGet:
    path: {{ .Values.healthChecks.readiness.path }}
    port: http
  initialDelaySeconds: {{ .Values.healthChecks.readiness.initialDelaySeconds }}
  periodSeconds: {{ .Values.healthChecks.readiness.periodSeconds }}
  timeoutSeconds: {{ .Values.healthChecks.readiness.timeoutSeconds }}
  failureThreshold: {{ .Values.healthChecks.readiness.failureThreshold }}
{{- end }}

{{- if .Values.healthChecks.startup.enabled }}
startupProbe:
  httpGet:
    path: {{ .Values.healthChecks.startup.path }}
    port: http
  initialDelaySeconds: {{ .Values.healthChecks.startup.initialDelaySeconds }}
  periodSeconds: {{ .Values.healthChecks.startup.periodSeconds }}
  timeoutSeconds: {{ .Values.healthChecks.startup.timeoutSeconds }}
  failureThreshold: {{ .Values.healthChecks.startup.failureThreshold }}
{{- end }}
```

---

## 7. Conclusão

**Completude Real do HA-001:** 85% → **90%** (após corrigir probes)

**Principais Descobertas:**
- ✅ neural_hive_resilience está completo (~3.631 LOC)
- ✅ HPAs e PDBs existem e estão configurados na maioria dos serviços
- ❌ Kubernetes probes não estão configurados (gap crítico)
- ❌ Alguns serviços não têm endpoints de health implementados

**Estimativa de Correção:**
- Fase Imediata: 1-2 dias
- Curto Prazo: 1 semana
- Total: ~2 semanas

---

**Gerado:** 2026-04-10
**Análise baseada em:** Helm charts e código fonte dos serviços
