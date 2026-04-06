# Handoff para Claude Code

> Spec: INFRA-006 - SLA Alerts Integration
> Status: Ready for Implementation
> Data: 2026-04-06

## Resumo

Implementar integração de alertas SLA no `orchestrator-dynamic` para receber notificações externas (Slack, PagerDuty) baseadas em violações e alertas proativos gerados pelo `sla-management-system`.

**Arquitetura:**
```
┌─────────────────────────┐
│  orchestrator-dynamic   │
│  - Publica alertas      │──┐
└─────────────────────────┘  │ Kafka
                             ▼
┌─────────────────────────┐  │
│   sla-management-system │◄─┘
│  - AlertEngine           │
│  - AlertDispatcher       │──┐
└─────────────────────────┘  │ Slack/PagerDuty
                             ▼
                      ┌──────────────┐
                      │ Notifications │
                      └──────────────┘
```

## Arquivos a Criar

### 1. `services/orchestrator-dynamic/src/clients/slack_client.py`

Cliente Slack com webhook HTTP (ver technical-spec.md para implementação completa)

### 2. `services/orchestrator-dynamic/src/clients/pagerduty_client.py`

Cliente PagerDuty Events API v2 (ver technical-spec.md para implementação completa)

### 3. `services/orchestrator-dynamic/src/consumers/sla_alert_consumer.py`

Consumer Kafka para alertas SLA (ver technical-spec.md para implementação completa)

## Arquivos a Modificar

### 1. `services/orchestrator-dynamic/src/config/settings.py`

Adicionar:
```python
# SLA Alerts Integration
enable_sla_alert_consumer: bool = Field(
    default=True,
    description="Habilitar consumer de alertas SLA"
)
slack_webhook_url: str = Field(
    default="",
    description="Webhook URL para Slack (vazio = desabilitado)"
)
pagerduty_routing_key: str = Field(
    default="",
    description="Routing key para PagerDuty Events API v2"
)
sla_alerts_topics: list[str] = Field(
    default=["sla.alerts", "sla.violations"],
    description="Tópicos Kafka para consumir alertas SLA"
)
```

### 2. `services/orchestrator-dynamic/src/main.py`

Adicionar startup/shutdown events:
```python
# Startup
@app.on_event("startup")
async def startup_sla_alert_consumer():
    if config.enable_sla_alert_consumer and config.slack_webhook_url:
        from src.consumers.sla_alert_consumer import SLAAlertConsumer

        app.state.sla_alert_consumer = SLAAlertConsumer()
        await app.state.sla_alert_consumer.start()
        asyncio.create_task(app.state.sla_alert_consumer.consume())

# Shutdown
@app.on_event("shutdown")
async def shutdown_sla_alert_consumer():
    if hasattr(app.state, "sla_alert_consumer"):
        await app.state.sla_alert_consumer.stop()
```

## Testes

**Arquivo:** `services/orchestrator-dynamic/tests/e2e/test_sla_alerts_e2e.py`

Executar:
```bash
pytest tests/e2e/test_sla_alerts_e2e.py -v
```

## Deploy

1. Configurar webhooks:
```bash
# Slack
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T000/B000/XXXX"

# PagerDuty
export PAGERDUTY_ROUTING_KEY="INTEGRATION_KEY_HERE"
```

2. Deploy:
```bash
kubectl rollout restart deployment/orchestrator-dynamic
```

3. Testar alerta manual:
```bash
# Publicar alerta de teste no Kafka
kafka-console-producer --broker-list kafka:9092 --topic sla.alerts << EOF
{
  "alert_id": "test-123",
  "title": "Test Alert",
  "severity": "WARNING",
  "workflow_id": "orch-test"
}
EOF
```

## Critérios de Sucesso

- [x] Consumer Kafka inicia sem erros
- [x] Alertas CRITICAL → PagerDuty + Slack
- [x] Alertas WARNING → Slack apenas
- [x] Retry em falhas de envio (3 tentativas)
- [x] Métricas Prometheus expostas
- [x] Formatação de blocks Slack correta

## Riscos

| Risco | Mitigação |
|-------|-----------|
| Slack/PD down | Retry + circuit breaker; alerta se >50% falhas |
| Kafka consumer lag | Monitor lag; alerta se >1000 mensagens |
| Webhook expirado | Monitor HTTP 4xx; rotação de credenciais |

## Referências

- `services/sla-management-system/src/services/alert_dispatcher.py` - Dispatcher de referência
- `services/orchestrator-dynamic/src/sla/alert_manager.py` - Publicação atual
- `monitoring/alertmanager/alertmanager-slack-pagerduty-config.yaml` - Config exemplo
