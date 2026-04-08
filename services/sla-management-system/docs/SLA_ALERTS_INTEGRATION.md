# SLA Alerts Integration

## Visão Geral

O sistema de alertas SLA permite notificar equipas sobre violações e eventos críticos relacionados a SLOs (Service Level Objectives). O sistema consome mensagens Kafka e despacha notificações para Slack e PagerDuty.

## Componentes

### 1. SlackClient (`src/clients/slack_client.py`)

Cliente para envio de notificações via Slack Incoming Webhooks.

**Features:**
- Envio de mensagens simples
- Suporte para blocks (formatação rica)
- Suporte para attachments (color coding)
- Retry automático com tenacity
- Formatação especializada para alertas SLA

**Configuração:**
```bash
SLACK__WEBHOOK_URL=https://hooks.slack.com/services/T/B/X
```

**Uso:**
```python
from src.clients.slack_client import SlackClient

client = SlackClient(webhook_url="https://hooks.slack.com/services/...")
await client.connect()

await client.send_sla_alert(
    alert_id="sla-123",
    severity="critical",
    title="SLA Violation",
    message="Error budget exceeded",
    service_name="api-gateway",
    slo_id="slo-1",
    error_budget_remaining=10.0,
)
```

### 2. PagerDutyClient (`src/clients/pagerduty_client.py`)

Cliente para envio de eventos via PagerDuty Events API v2.

**Features:**
- Trigger, acknowledge e resolve alerts
- Suporte para custom details
- Retry automático
- Dedup keys para evitar duplicação

**Configuração:**
```bash
PAGERDUTY__ROUTING_KEY=your-integration-key-here
PAGERDUTY__API_URL=https://events.pagerduty.com/v2/enqueue
```

**Uso:**
```python
from src.clients.pagerduty_client import PagerDutyClient

client = PagerDutyClient(routing_key="your-routing-key")
await client.connect()

await client.send_sla_alert(
    alert_id="sla-123",
    severity="critical",
    title="SLA Violation",
    message="Error budget exceeded",
    service_name="api-gateway",
)
```

### 3. SLAAlertConsumer (`src/consumers/sla_alert_consumer.py`)

Consumer Kafka para processamento de alertas SLA.

**Responsabilidades:**
- Consumir mensagens dos tópicos `sla.alerts` e `sla.violations`
- Despachar para Slack (todas as severidades)
- Despachar para PagerDuty (critical/emergency apenas)
- Registrar métricas Prometheus

**Configuração:**
```bash
ENABLE_SLA_ALERT_CONSUMER=true
SLA_ALERTS_TOPICS=["sla.alerts", "sla.violations"]
CONSUMER_GROUP_ID=sla-alert-consumer
AUTO_OFFSET_RESET=latest
```

**Formato de Mensagem:**
```json
{
  "alert_id": "sla-critical-001",
  "severity": "critical",
  "title": "SLA Critical Violation",
  "message": "Error budget exceeded for api-gateway",
  "service_name": "api-gateway",
  "slo_id": "slo-api-availability",
  "error_budget_remaining": 5.0,
  "details": {
    "threshold": 99.9,
    "current_value": 99.2,
    "window": "30d"
  }
}
```

**Severidades Suportadas:**
- `emergency`: Alerta crítico máximo (PagerDuty + Slack)
- `critical`: Alerta crítico (PagerDuty + Slack)
- `warning`: Aviso (Slack apenas)
- `info`: Informação (Slack apenas)

## Métricas Prometheus

O sistema expõe as seguintes métricas:

### Alertas Recebidos
```
sla_alerts_received_total{severity, topic}
```
Total de alertas SLA recebidos via Kafka.

### Notificações Enviadas
```
sla_notifications_sent_total{channel, severity, status}
```
Total de notificações enviadas por canal e severidade.

### Falhas de Notificação
```
sla_notification_failures_total{channel, severity, error_type}
```
Total de falhas no envio de notificações.

### Latência de Notificação
```
sla_notification_latency_seconds{channel, severity}
```
Histograma de latência desde receção até envio.

## Setup de Slack Webhook

1. Aceda a https://api.slack.com/apps
2. Crie uma nova app "From scratch"
3. Navigate para "Incoming Webhooks"
4. Ative "Activate Incoming Webhooks"
5. Clique em "Add New Webhook to Workspace"
6. Selecione o canal onde os alertas serão enviados
7. Copie a Webhook URL

## Setup de PagerDuty Integration

1. Aceda a https://pagerduty.com
2. Navegue para "Configuration" → "Services"
3. Crie um novo service ou edite um existente
4. Em "Integrations", adicione "Events API v2"
5. Copie o "Integration Key" (Routing Key)

## Troubleshooting

### Alertas não chegam ao Slack

**Sintoma:** Mensagens Kafka são consumidas mas nada aparece no Slack.

**Diagnóstico:**
```bash
# Verificar logs do consumer
kubectl logs -f deployment/sla-management-system | grep "slack_dispatch_failed"

# Verificar métricas de envio
curl http://sla-management-system:8000/metrics | grep sla_notifications_sent
```

**Possíveis Causas:**
1. Webhook URL inválida ou incorreta
2. Slack rate limiting (muitas mensagens)
3. Webhook foi revogado

**Resolução:**
1. Verificar `SLACK__WEBHOOK_URL` nas configurações
2. Testar webhook manualmente:
```bash
curl -X POST https://hooks.slack.com/services/T/B/X \
  -H 'Content-Type: application/json' \
  -d '{"text": "Test message"}'
```

### PagerDuty não cria incidentes

**Sintoma:** Alertas críticos chegam ao Slack mas não ao PagerDuty.

**Diagnóstico:**
```bash
# Verificar logs
kubectl logs -f deployment/sla-management-system | grep "pagerduty_dispatch_failed"

# Verificar métricas
curl http://sla-management-system:8000/metrics | grep sla_notification_failures
```

**Possíveis Causas:**
1. Routing key inválida
2. Service não configurado corretamente no PagerDuty
3. Severidade não é "critical" ou "emergency"

**Resolução:**
1. Verificar `PAGERDUTY__ROUTING_KEY`
2. Testar Events API manualmente:
```bash
curl -X POST https://events.pagerduty.com/v2/enqueue \
  -H 'Content-Type: application/json' \
  -d '{
    "routing_key": "YOUR_KEY",
    "event_action": "trigger",
    "payload": {
      "summary": "Test alert",
      "severity": "critical",
      "source": "test-service"
    },
    "dedup_key": "test-001"
  }'
```

### Consumer Kafka não inicia

**Sintoma:** Logs mostram "Unable to bootstrap from kafka:9092"

**Diagnóstico:**
```bash
# Verificar conectividade
kubectl exec -it deployment/sla-management-system -- nc -zv neural-hive-kafka-kafka-bootstrap.kafka 9092

# Verificar tópicos existentes
kubectl exec -it neural-hive-kafka-kafka-0 -- kafka-topics.sh --bootstrap-server localhost:9092 --list
```

**Resolução:**
1. Criar tópicos se não existirem:
```bash
kubectl exec -it neural-hive-kafka-kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic sla.alerts --partitions 3 --replication-factor 2

kubectl exec -it neural-hive-kafka-kafka-0 -- kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic sla.violations --partitions 3 --replication-factor 2
```

### Latência alta nas notificações

**Sintoma:** Alertas demoram muito tempo a chegar após violação.

**Diagnóstico:**
```bash
# Verificar histograma de latência
curl http://sla-management-system:8000/metrics | grep sla_notification_latency_seconds
```

**Possíveis Causas:**
1. Slack/PagerDuty com lentidão
2. Timeout muito alto no HTTP client
3. Network congestion

**Resolução:**
1. Ajustar `timeout_seconds` nas configurações dos clientes
2. Verificar latência de rede para Slack/PagerDuty

## Perguntas Frequentes (FAQ)

**Q: Porquê PagerDuty apenas para critical/emergency?**
A: Para evitar "alert fatigue". Apenas alertas que requerem intervenção imediata devem criar incidentes.

**Q: Posso customizar as mensagens Slack?**
A: Sim, o método `send_sla_alert` aceita `blocks` e `attachments` para formatação customizada.

**Q: O que acontece se Slack/PagerDuty estiver down?**
A: O sistema tem retry automático configurado. Após 3 tentativas falhadas, o erro é logged e o consumer continua processando outras mensagens.

**Q: Como testar localmente sem Slack/PagerDuty?**
A: Deixe `SLACK__WEBHOOK_URL` e `PAGERDUTY__ROUTING_KEY` vazios. O consumer funcionará mas não enviará notificações.

## Referências

- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
- [PagerDuty Events API v2](https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTgw-events-api-v2-overview)
- [Prometheus Metrics](https://prometheus.io/docs/practices/naming/)
