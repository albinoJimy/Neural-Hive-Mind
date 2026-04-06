# Spec Requirements Document

> Spec: SLA Alerts Integration
> Created: 2026-04-06
> Status: Planning
> Epic: INFRA-006

## Overview

Implementar integração bidirecional entre o `orchestrator-dynamic` e o `sla-management-system` para alertas SLA, permitindo que o orchestrator receba notificações externas (Slack, PagerDuty) baseadas em violações e alertas proativos, complementando o sistema de publicação de alertas já existente no Kafka.

## User Stories

### Como SRE, quero receber alertas Slack para violações SLA

Como SRE, quero receber notificações no Slack quando um workflow exceder seu deadline ou consumir todo o error budget, para que possa tomar ações corretivas rapidamente e minimizar impacto nos usuários.

**Workflow:**
1. Workflow no orchestrator excede deadline ou error budget
2. AlertManager publica evento no Kafka (`sla.violations` ou `sla.alerts`)
3. SLA Management System consume evento e aciona AlertDispatcher
4. AlertDispatcher envia notificação para Slack webhook
5. SRE recebe mensagem no canal `#sla-alerts` com detalhes

### Como On-Call Engineer, quero alertas PagerDuty para casos críticos

Como On-Call Engineer, quero ser notificado via PagerDuty para incidentes críticos (error budget < 20%, deadline excedido > 5 min), para que possa responder imediatamente e degradar graciosamente o serviço se necessário.

**Workflow:**
1. Alerta com severidade CRITICAL é gerado
2. PagerDuty é acionado via Events API v2
3. On-Call recebe página no celular
4. Incidente é criado automaticamente com contexto completo

## Spec Scope

1. **Consumer Kafka SLA Alerts** — Implementar consumer no `orchestrator-dynamic` para processar alertas vindos do `sla-management-system`
2. **Clientes Slack e PagerDuty** — Criar clientes dedicados para envio de notificações
3. **Integração gRPC SLA** — Alternativa ao Kafka: consumir alertas via gRPC do `sla-management-system`
4. **Testes E2E** — Validar fluxo completo: violação → Kafka → Dispatcher → Slack/PagerDuty
5. **Documentação** — Guia de configuração de webhooks e operação

## Out of Scope

- Reimplementação do AlertDispatcher (já existe no sla-management-system)
- Autenticação OAuth para Slack (usando webhooks)
- Email real (aiosmtplib) — considerado implementação futura
- Interface UI para gerenciar regras de alerta

## Expected Deliverable

1. `SLAAlertConsumer` no `orchestrator-dynamic` consumindo tópicos `sla.alerts` e `sla.violations`
2. `SlackClient` e `PagerDutyClient` com retry e circuit breaker
3. Configurações em `settings.py` para webhooks e routing keys
4. Testes E2E validando notificações reais (com mock servers)
5. Métricas Prometheus: `sla_alerts_received`, `sla_notifications_sent`, `sla_notification_failures`
6. Documentação de setup de Slack/PagerDuty

## Tech Stack

- **Linguagem:** Python 3.12+
- **Framework:** FastAPI + aiokafka
- **Integrações:** Slack Webhook, PagerDuty Events API v2
- **Observabilidade:** Prometheus metrics
- **Testes:** pytest + pytest-asyncio + aioresponses

## Dependencies

**Serviços existentes:**
- `sla-management-system` - AlertEngine + AlertDispatcher já implementados
- `orchestrator-dynamic` - Serviço onde consumer será adicionado

**Kafka topics:**
- `sla.alerts` - Alertas proativos
- `sla.violations` - Violações formais

## References

- `services/sla-management-system/src/services/alert_dispatcher.py` - Dispatcher implementado
- `services/orchestrator-dynamic/src/sla/alert_manager.py` - Publicação de alertas atual
- `monitoring/alertmanager/alertmanager-slack-pagerduty-config.yaml` - Config exemplo
