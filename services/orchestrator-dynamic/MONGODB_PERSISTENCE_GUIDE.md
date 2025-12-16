# MongoDB Persistence Guide

Guia detalhado da camada de persistência MongoDB do **orchestrator-dynamic** para auditoria, observabilidade e autocura.

## Overview
- Objetivo: registrar validações (C1), resultados consolidados (C5), incidentes de autocura (Fluxo E) e buffers de telemetria para retry.
- Benefícios: trilha de auditoria para compliance, debugging mais rápido, insumos para analytics/SLA e resiliência na entrega de telemetria.

## Collections

### validation_audit
- **Schema:** `plan_id`, `validation_result` (objeto completo), `workflow_id`, `timestamp`, `hash`
- **Índices:** `plan_id`, `workflow_id`, `timestamp`, composto `(plan_id, timestamp)`
- **Uso:** histórico de validações para rastrear regressões e padrões de falha.

### workflow_results
- **Schema:** `workflow_id` (usado como `_id`), `plan_id`, `intent_id`, `status`, `metrics`, `tickets_summary`, `sla_status`, `consolidated_at`
- **Índices:** `workflow_id` (único), `plan_id`, `status`, `consolidated_at`, composto `(status, consolidated_at)`
- **Uso:** base para analytics de performance, SLA tracking e debugging de workflows.

### incidents
- **Schema:** `workflow_id`, `type`, `details`, `timestamp`, `severity`
- **Índices:** `workflow_id`, `type`, `severity`, `timestamp`, composto `(severity, timestamp)`
- **Uso:** aciona autocura e análises de falhas recorrentes.

### telemetry_buffer
- **Schema:** `correlation` (inclui `workflow_id`/`plan_id`/`intent_id`), `metrics`, `timestamp`, `source`, `buffered_at`, `retry_count`
- **Índices:** `workflow_id`, `buffered_at`, `retry_count`, composto `(retry_count, buffered_at)`
- **Uso:** garantir entrega de telemetria quando Kafka/observabilidade estiverem indisponíveis.

## Retry Strategy
- Decorators `tenacity` com `stop_after_attempt(retry_max_attempts)` e `wait_exponential(multiplier=retry_backoff_coefficient, min=retry_initial_interval_ms/1000, max=retry_max_interval_ms/1000)`.
- Padrão atual: 3 tentativas com backoff exponencial (1s → 2s → 4s, máx 60s).
- Retentativas somente para `PyMongoError`; demais exceções são logadas imediatamente.
- Logs estruturados de retry facilitam correlação com métricas de disponibilidade do MongoDB.

## Fail-Open Behavior
- Persistência não bloqueia orquestração: falhas registram `*_persist_failed` e o fluxo segue.
- Justificativa: evitar parar workflows críticos por falhas de auditoria/telemetria.
- Monitorar falhas por logs e métricas; ajustar estratégia se for necessário fail-closed em rotas específicas.

## Monitoring and Observability
- Logs estruturados em todas as operações: `validation_audit_saved`, `workflow_result_saved`, `incident_saved`, `telemetry_buffered`.
- Consultas úteis:
  - Validações por status: `db.validation_audit.aggregate([{ $group: { _id: "$validation_result.valid", total: { $sum: 1 } } }])`
  - Workflows com violações SLA: `db.workflow_results.find({ "sla_status.violations_count": { $gt: 0 } })`
  - Incidentes críticos recentes: `db.incidents.find({ severity: "CRITICAL" }).sort({ timestamp: -1 }).limit(20)`
  - Telemetria com retry: `db.telemetry_buffer.find({ retry_count: { $gt: 0 } })`

## Maintenance
- Avaliar TTL indexes para buffers/validações antigas (não habilitado por padrão).
- Estratégia de backup: priorizar `workflow_results` e `incidents` para pós-mortem e compliance.
- Verificar saúde de índices periodicamente (`db.collection.getIndexes()`); reconstruir se necessário.

## Troubleshooting
- **MongoDB indisponível:** logs `mongodb_client_not_initialized` ou `*_persist_failed`; verificar URI/credenciais e rede.
- **Retries excessivos:** revisar métricas do cluster e latência; ajustar `retry_*` conforme carga.
- **Índices ausentes:** recriar via `_create_indexes` ou comandos manuais; quedas de performance indicam varredura full-scan.

## Examples
- Buscar histórico de validações de um plano: `db.validation_audit.find({ plan_id: "<plan>" }).sort({ timestamp: -1 })`
- Listar workflows com status `FAILED`: `db.workflow_results.find({ status: "FAILED" })`
- Agrupar incidentes por tipo: `db.incidents.aggregate([{ $group: { _id: "$type", total: { $sum: 1 } } }])`
- Exportar telemetria buffered para reprocessamento: iterar sobre `telemetry_buffer` e reenviar para Kafka/observability.

## Migration Guide
- Compatibilidade retroativa: fail-open mantém Fluxo C funcionando mesmo sem MongoDB.
- Para atualizar: aplicar deploy com nova versão, validar conectividade MongoDB e checar criação de índices.
- Checklist: variáveis `MONGODB_URI`/`MONGODB_DATABASE` definidas; permissões de escrita nas quatro coleções; dashboards/alertas ajustados para novos logs.
