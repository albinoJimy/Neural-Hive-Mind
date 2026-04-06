# Spec Tasks

> Spec: INFRA-006 - SLA Alerts Integration
> Status: Planning

## Tasks

- [ ] 1. Implementar SlackClient
    - [ ] 1.1 Criar `src/clients/slack_client.py`
    - [ ] 1.2 Implementar `send_message()` com webhook
    - [ ] 1.3 Adicionar suporte para blocks
    - [ ] 1.4 Adicionar retry com tenacity
    - [ ] 1.5 Escrever testes unitários

- [ ] 2. Implementar PagerDutyClient
    - [ ] 2.1 Criar `src/clients/pagerduty_client.py`
    - [ ] 2.2 Implementar `trigger_alert()` (Events API v2)
    - [ ] 2.3 Implementar `acknowledge_alert()`
    - [ ] 2.4 Implementar `resolve_alert()`
    - [ ] 2.5 Adicionar retry com tenacity
    - [ ] 2.6 Escrever testes unitários

- [ ] 3. Implementar SLAAlertConsumer
    - [ ] 3.1 Criar `src/consumers/sla_alert_consumer.py`
    - [ ] 3.2 Implementar `start()` com AIOKafkaConsumer
    - [ ] 3.3 Implementar `consume()` loop de processamento
    - [ ] 3.4 Implementar `_dispatch_critical()` (PagerDuty + Slack)
    - [ ] 3.5 Implementar `_dispatch_warning()` (Slack apenas)
    - [ ] 3.6 Implementar formatação de blocks Slack
    - [ ] 3.7 Escrever testes unitários

- [ ] 4. Adicionar configurações
    - [ ] 4.1 Adicionar `enable_sla_alert_consumer` em settings.py
    - [ ] 4.2 Adicionar `slack_webhook_url` em settings.py
    - [ ] 4.3 Adicionar `pagerduty_routing_key` em settings.py
    - [ ] 4.4 Adicionar `sla_alerts_topics` em settings.py
    - [ ] 4.5 Adicionar valores defaults e documentação

- [ ] 5. Integrar no main.py
    - [ ] 5.1 Adicionar startup event para iniciar consumer
    - [ ] 5.2 Adicionar shutdown event para parar consumer
    - [ ] 5.3 Condicionar à flag `enable_sla_alert_consumer`

- [ ] 6. Escrever testes E2E
    - [ ] 6.1 Testar alerta crítico → PagerDuty + Slack
    - [ ] 6.2 Testar alerta warning → Slack apenas
    - [ ] 6.3 Testar retry em falha de envio
    - [ ] 6.4 Testar formatação de blocks Slack
    - [ ] 6.5 Testar integração Kafka end-to-end

- [ ] 7. Adicionar métricas Prometheus
    - [ ] 7.1 Implementar `sla_alerts_received_total` (Counter)
    - [ ] 7.2 Implementar `sla_notifications_sent_total` (Counter)
    - [ ] 7.3 Implementar `sla_notification_failures_total` (Counter)
    - [ ] 7.4 Implementar `sla_notification_latency_seconds` (Histogram)
    - [ ] 7.5 Validar métricas em `/metrics`

- [ ] 8. Documentação
    - [ ] 8.1 Documentar setup de Slack webhook
    - [ ] 8.2 Documentar setup de PagerDuty integration key
    - [ ] 8.3 Criar runbook de troubleshooting
    - [ ] 8.4 Atualizar MEMORY.md

- [ ] 9. Deploy e validação
    - [ ] 9.1 Configurar webhooks em staging
    - [ ] 9.2 Deploy em staging
    - [ ] 9.3 Testar alertas reais em staging
    - [ ] 9.4 Configurar webhooks em produção
    - [ ] 9.5 Deploy em produção
    - [ ] 9.6 Monitorar notificações por 48h

- [ ] 10. Integração com sla-management-system (opcional)
    - [ ] 10.1 Avaliar integração via gRPC como alternativa
    - [ ] 10.2 Testar comunicação bidirecional
    - [ ] 10.3 Documentar arquitetura híbrida
