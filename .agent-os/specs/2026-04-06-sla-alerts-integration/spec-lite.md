# Spec Summary (Lite)

Implementar integração de alertas SLA no `orchestrator-dynamic` para receber notificações externas (Slack, PagerDuty) baseadas em violações e alertas proativos gerados pelo `sla-management-system`. O AlertDispatcher já está 95% completo — esta spec foca na integração bidirecional e consumidores Kafka.

**Key changes:**
1. Criar `SLAAlertConsumer` no `orchestrator-dynamic` para consumir `sla.alerts` e `sla.violations`
2. Implementar `SlackClient` (webhook) e `PagerDutyClient` (Events API v2)
3. Configurar webhooks e routing keys em `settings.py`
4. Testes E2E com mock servers Slack/PagerDuty

**Success criteria:**
- Alertas CRITICAL → PagerDuty é acionado
- Alertas WARNING → Slack recebe notificação
- Métricas Prometheus expostas para monitoramento
- Retry e circuit breaker para falhas de envio
