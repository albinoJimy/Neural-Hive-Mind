# AlertManager Webhook Integration - Completo

**Data:** 2026-04-13
**Status:** ✅ FUNCIONAL

## Implementação Completa

### Componentes Criados

1. **AlertManager Customizado** (`neural-hive-alertmanager`)
   - Tipo: Alertmanager CR (Prometheus Operator v0.29.0)
   - Configuração: Webhook receivers para /alerts, /critical, /warning
   - Serviço: ClusterIP no port 9093
   - Pod: `alertmanager-neural-hive-alertmanager-0` (3/3 Running)

2. **webhook-logger Service**
   - Deployment: Python 3.12-slim container
   - Endpoints:
     - POST /alerts - Todos os alertas
     - POST /critical - Alertas críticos
     - POST /warning - Alertas de warning
     - GET /health - Health check
     - GET /metrics - Métricas Prometheus
   - Logs estruturados com timestamp e contexto

3. **Prometheus Configuration**
   - AlertManager primário: `neural-hive-prometheus-kub-alertmanager` (default)
   - AlertManager customizado: `neural-hive-alertmanager` (webhook integration)
   - Service discovery configurado via Prometheus CR

### Configuração de Roteamento

```yaml
route:
  receiver: default-receiver
  group_by: [namespace, alertname, severity]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 12h
  routes:
  - match:
      severity: critical
    receiver: critical-receiver
    continue: true
  - match:
      severity: warning
    receiver: warning-receiver
    continue: true
  - match_re:
      alertname: "QueenAgentDown|WorkerAgentDown|OrchestratorDown"
    receiver: nhm-critical-receiver

receivers:
- name: default-receiver
  webhook_configs:
  - url: http://webhook-logger.observability.svc.cluster.local:8080/alerts
- name: critical-receiver
  webhook_configs:
  - url: http://webhook-logger.observability.svc.cluster.local:8080/critical
- name: warning-receiver
  webhook_configs:
  - url: http://webhook-logger.observability.svc.cluster.local:8080/warning
- name: nhm-critical-receiver
  webhook_configs:
  - url: http://webhook-logger.observability.svc.cluster.local:8080/critical
```

### Ficheiros Criados

| Ficheiro | Propósito |
|----------|-----------|
| `k8s/observability/neural-hive-alertmanager.yaml` | AlertManager CR + Secret + Service |
| `monitoring/alertmanager/webhook-logger/deployment-v5.yaml` | webhook-logger deployment |
| `docs/ALERTMANAGER_NEXT_STEPS.md` | Documentação de troubleshooting |

### Fluxo Completo Testado

```
┌─────────────────┐
│  Prometheus     │
│  (Regras)       │
└────────┬────────┘
         │
         ├──────────────────┐
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌──────────────────────┐
│  Default        │  │  Custom              │
│  AlertManager   │  │  AlertManager        │
│  (helm managed) │  │  + webhook configs   │
└─────────────────┘  └──────────┬───────────┘
                                │
                                ▼
                      ┌──────────────────────┐
                      │  webhook-logger      │
                      │  /alerts             │
                      │  /critical           │
                      │  /warning            │
                      └──────────────────────┘
```

### Métricas de Operação

**Alertas processados (instantâneo):**
- 62 alertas ativos no AlertManager customizado
- 51 → warning-receiver (/warning)
- 10 → default-receiver (/alerts)
- 1 → critical-receiver (/critical)

**Timing de notificação:**
- `group_wait: 30s` - Tempo de espera antes de enviar o primeiro alerta
- `group_interval: 5m` - Intervalo entre grupos de alertas
- `repeat_interval: 12h` - Reenvio de alertas ativos

### Resolução de Problemas

1. **Istio mTLS** - Alterado para PERMISSIVE
   - Ficheiro: `k8s/observability/istio-permissive-metrics.yaml`
   - Permite scraping de métricas entre namespaces

2. **YAML Syntax** - Match format corrigido
   - `match:` usa dicionário, não lista
   - `match_re:` para regex patterns

3. **Service Selector** - Pod labels fixed
   - Pod: `alertmanager: neural-hive-alertmanager`
   - Service: Selector atualizado para match

### Próximos Passos Opcionais

1. **Integração com Notificações Externas**
   - Modificar webhook-logger para re-enviar para Slack/Discord
   - Adicionar autenticação API

2. **Dashboard de Alertas**
   - Grafana dashboard para visualizar alertas recebidos
   - Métricas do webhook-logger (alerts_received_total)

3. **Runbooks Automation**
   - Acionar runbooks automaticamente baseado em alertas críticos
   - Integração com Approval Service para decisões humanas

### Comandos Úteis

```bash
# Ver alertas no AlertManager
kubectl exec -n observability alertmanager-neural-hive-alertmanager-0 \
  --container alertmanager -- wget -qO- 'http://localhost:9093/api/v2/alerts' | jq .

# Ver logs do webhook-logger
kubectl logs -n observability -l app.kubernetes.io/name=webhook-logger -f

# Testar webhook-logger diretamente
kubectl run -n observability test-alert --image=curlimages/curl:latest --rm -i --restart=Never -- \
  curl -X POST -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"test","severity":"warning"}}]' \
  http://webhook-logger.observability.svc.cluster.local:8080/warning

# Ver estado do AlertManager
kubectl get alertmanager -n observability neural-hive-alertmanager -o yaml
```

---

**Estado:** ✅ Produzindo alertas funcionais
**Última verificação:** 2026-04-13 21:06 UTC
