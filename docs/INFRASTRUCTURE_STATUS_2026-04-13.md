# Neural-Hive-Mind - Estado da Infraestrutura

**Data:** 2026-04-13
**Cluster:** Kubernetes v1.29.15 (self-hosted, 38 namespaces)

## Resumo Executivo

Stack de observabilidade completo implementado. Issues infraestrutura crítica identificados e parcialmente resolvidos.

## Componentes Operacionais

### Observabilidade (100%)
- ✅ Prometheus v3.8.1 - 39 regras, 25 ServiceMonitors
- ✅ Grafana - 27 Dashboards NHM
- ✅ AlertManager (Dual setup) - Default + Webhook integration
- ✅ Webhook-logger - Recebendo alertas em /alerts, /critical, /warning
- ✅ OpenTelemetry Collector - Tracing ativo

### Serviços Core (100%)
| Serviço | Status | Notas |
|---------|--------|-------|
| gateway-intencoes | ✅ Running | |
| consensus-engine | ✅ Running | RBAC issue resolvido (OPA disabled) |
| approval-service | ✅ Running | |
| queen-agent | ✅ Running | |
| worker-agents | ✅ Running | |
| analyst-agents | ✅ Running | |
| optimizer-agents | ✅ Running | |
| guard-agents | ✅ Running | |
| service-registry | ✅ Running | |
| orchestrator-dynamic | ✅ Running | |
| execution-ticket | ✅ Running | |
| memory-layer-api | ✅ Running | |
| explainability-api | ✅ Running | |
| feedback-collection | ✅ Running | |

### Infraestrutura de Dados
| Componente | Status | Notas |
|------------|--------|-------|
| Kafka (Strimzi) | ✅ Running | Namespace: kafka |
| Redis Cluster | ✅ Running | 5 pods, auth: nhm_redis_2026 |
| MongoDB | ✅ Running | |
| Neo4j | ✅ Running | |
| Keycloak | ✅ Running | 2/2 replicas |

## Problemas Recentes Resolvidos

### 1. OPA Gatekeeper Blocking
**Problema:** Consensus-engine bloqueado por constraint `must-have-app-label`
**Resolução:** Adicionado `app: consensus-engine` ao pod template
**Data:** 2026-04-13 21:12 UTC

### 2. Redis Authentication
**Problema:** `redis.exceptions.AuthenticationError: Authentication required`
**Causa:** Redis cluster reconfigurado com autenticação
**Resolução:**
- Criado secret `redis-password` no namespace neural-hive
- Configurado `REDIS_PASSWORD: nhm_redis_2026` no configmap
- Mantido `REDIS_SSL_ENABLED: false` (SSL timeout)

### 3. Istio mTLS Blocking Metrics
**Problema:** PeerAuthentication STRICT bloqueava scraping
**Resolução:** Alterado para PERMISSIVE mode
**Ficheiro:** `k8s/observability/istio-permissive-metrics.yaml`

## Issues Resolvidos (2026-04-13)

### Consensus-Engine RBAC Issue
**Problema:** Queen-agent retornando `RBAC: access denied` ao consensus-engine
**Causa:** OPA (Open Policy Agent) configurado no queen-agent estava a bloquear chamadas
**Resolução:** Desabilitado OPA temporariamente via ConfigMap
**Documentação:** `docs/CONSENSUS_ENGINE_RBAC_ISSUE.md`

## Configurações Importantes

### Redis Cluster
- **Endpoint:** `neural-hive-cache.redis-cluster.svc.cluster.local:6379`
- **Password:** `nhm_redis_2026`
- **SSL:** Disabled (para ligações internas)
- **TLS:** Available via certificados em `redis-cluster/redis-tls`

### AlertManager Endpoints
```
http://webhook-logger.observability.svc.cluster.local:8080/
├── /alerts    (todos os alertas)
├── /critical  (severity=critical)
├── /warning   (severity=warning)
└── /health    (health check)
```

### Gatekeeper Constraints
- `must-have-app-label` - Requer labels `app` e `app.kubernetes.io/name`
- Namespaces: neural-hive, default
- Afeta: Pod, Deployment, StatefulSet, DaemonSet

## Documentação Relacionada

- `docs/OBSERVABILITY_FINAL_STATE.md` - Observabilidade completa
- `docs/ALERTMANAGER_IMPLEMENTATION_COMPLETE.md` - AlertManager webhook
- `docs/ISTIO_MTLS_METRICS_RESOLUTION.md` - mTLS resolution
- `docs/OBSERVABILITY_IMPLEMENTATION_SUMMARY.md` - Resumo implementação

## Comandos Úteis

```bash
# Ver estado dos pods consensus-engine
kubectl get pod -n neural-hive -l app.kubernetes.io/name=consensus-engine

# Ver logs do consensus-engine
kubectl logs -n neural-hive -l app.kubernetes.io/name=consensus-engine -c consensus-engine -f

# Ver alertas no AlertManager
kubectl exec -n observability alertmanager-neural-hive-alertmanager-0 \
  -c alertmanager -- wget -qO- 'http://localhost:9093/api/v2/alerts' | jq .

# Ver logs do webhook-logger
kubectl logs -n observability -l app.kubernetes.io/name=webhook-logger -f

# Testar Redis connection
kubectl exec -n redis-cluster redis-cluster-0 -- redis-cli -a nhm_redis_2026 ping

# Ver Gatekeeper constraints
kubectl get k8srequiredlabels -A
```

---

**Atualizado:** 2026-04-13 21:35 UTC
**Última resolução:** RBAC issue entre consensus-engine e queen-agent (OPA disabled)
