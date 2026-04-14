# Configuração AlertManager - Próximos Passos

**Data:** 2026-04-13
**Status:** AlertManager operacional, configuração webhook necessita persistência

## Estado Atual

### Funcionando
- ✅ Prometheus a recolher métricas de 13 serviços NHM
- ✅ Alertas Prometheus configurados (14 regras)
- ✅ Webhook-Logger operacional e a receber POSTs
- ✅ Istio mTLS resolvido (modo PERMISSIVE)

### Problema Identificado
- ❌ Configuração do AlertManager (receivers webhook) não persiste através de restarts
- ❌ Helm upgrade com configuração customizada falhou
- ❌ CRD `AlertmanagerConfig` v1alpha1 não suporta `webhook_configs`

## Soluções Possíveis

### Opção 1: Helm Values com SecretTemplate (RECOMENDADO)

Atualizar o release helm com valores que incluem a configuração do webhook-logger:

```yaml
alertmanager:
  alertmanagerSpec:
    # Configuração via config map
    configMaps:
      - webhook-logger-alertmanager-config
```

**Prós:** Persiste através de upgrades
**Contras:** Requer teste completo do helm chart

### Opção 2: Sidecar Init Container

Adicionar um init container ao StatefulSet do AlertManager que copia a configuração:

```yaml
initContainers:
- name: setup-webhook-config
  image: busybox
  command:
  - /bin/sh
  - -c
  - |
    cat > /etc/alertmanager/config_webhook.yaml <<'EOF'
    route:
      receiver: default-receiver
      ...
    EOF
```

**Prós:** Funciona imediatamente
**Contras:** Modifica recursos gerenciados pelo helm

### Opção 3: External AlertManager (SIMPLES)

Criar um AlertManager separado fora do helm chart kube-prometheus-stack:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: Alertmanager
metadata:
  name: nhm-alertmanager
  namespace: observability
spec:
  replicas: 1
  config: |
    route:
      receiver: webhook-logger
    receivers:
    - name: webhook-logger
      webhook_configs:
      - url: http://webhook-logger.observability.svc:8080/alerts
```

**Prós:** Controle total da configuração
**Contras:** Duplicação de recursos, complexidade adicional

### Opção 4: Slack Integration (ALTERNATIVA)

Configurar Slack como receiver e usar webhook do Slack:

```yaml
receivers:
- name: 'slack-critical'
  slack_configs:
  - api_url: 'https://hooks.slack.com/SERVER/WEBHOOK'
    channel: '#nhm-alerts'
```

**Prós:** Nativamente suportado pelo AlertmanagerConfig
**Contras:** Requer configuração do Slack

## Configuração webhook-logger Atual

### Endpoints Disponíveis

| Endpoint | Propósito |
|----------|-----------|
| POST /alerts | Todos os alertas |
| POST /critical | Alertas críticos |
| POST /warning | Alertas de warning |
| POST /nhm | Alertas NHM específicos |
| GET /health | Health check |
| GET /metrics | Métricas Prometheus |

### Formato de Alerta (AlertManager)

```json
[
  {
    "labels": {
      "alertname": "ServiceDown",
      "severity": "critical",
      "namespace": "neural-hive"
    },
    "annotations": {
      "summary": "Service X is down",
      "description": "Detailed description"
    },
    "status": "firing"
  }
]
```

## Configuração Recomendada

Para implementar a Opção 3 (External Alertmanager), criar:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: Alertmanager
metadata:
  name: neural-hive-alertmanager
  namespace: observability
  labels:
    alertmanager: neural-hive
spec:
  replicas: 1
  resources:
    requests:
      cpu: 50m
      memory: 128Mi
    limits:
      cpu: 200m
      memory: 256Mi
  config:
    global:
      resolve_timeout: 5m

    route:
      receiver: 'default-receiver'
      group_by:
      - namespace
      - alertname
      - severity
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 12h
      routes:
      - match:
        - severity: critical
        receiver: 'critical-receiver'
        continue: true
      - match:
        - severity: warning
        receiver: 'warning-receiver'
        continue: true
      - match:
        - alertname: "Watchdog|InfoInhibitor"
        receiver: 'null'

    receivers:
    - name: 'default-receiver'
      webhook_configs:
      - url: 'http://webhook-logger.observability.svc.cluster.local:8080/alerts'
        send_resolved: true

    - name: 'critical-receiver'
      webhook_configs:
      - url: 'http://webhook-logger.observability.svc.cluster.local:8080/critical'
        send_resolved: true

    - name: 'warning-receiver'
      webhook_configs:
      - url: 'http://webhook-logger.observability.svc.cluster.local:8080/warning'
        send_resolved: true

    - name: 'null'
```

## Passos Imediatos

1. **Testar envio de alerta real:** Desligar um pod e verificar se o alerta dispara
2. **Verificar Prometheus → AlertManager:** Confirmar que alertas chegam ao AlertManager
3. **Configurar receiver webhook:** Implementar uma das soluções acima
4. **Teste end-to-end:** Verificar fluxo completo Prometheus → AlertManager → Webhook-Logger

## Comandos Úteis

### Verificar alertas no Prometheus
```bash
kubectl exec -n observability prometheus-neural-hive-prometheus-kub-prometheus-0 \
  -c prometheus -- wget -qO- 'http://localhost:9090/api/v1/alerts'
```

### Verificar alertas no AlertManager
```bash
kubectl exec -n observability alertmanager-neural-hive-prometheus-kub-alertmanager-0 \
  -- wget -qO- 'http://localhost:9093/api/v2/alerts'
```

### Testar webhook-logger diretamente
```bash
kubectl run -n observability test-alert --image=curlimages/curl:latest --rm -i --restart=Never -- \
  curl -X POST -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"test","severity":"warning"}}]' \
  http://webhook-logger.observability.svc.cluster.local:8080/warning
```

### Verificar logs do webhook-logger
```bash
kubectl logs -n observability -l app.kubernetes.io/name=webhook-logger
```

---

**Próxima Ação:** Implementar uma das soluções acima para persistir a configuração do webhook-logger no AlertManager.
