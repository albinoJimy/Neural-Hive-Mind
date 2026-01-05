# Guia de Observabilidade - Worker Agents

Este documento descreve a instrumentação de observabilidade do serviço Worker Agents, incluindo métricas Prometheus, spans OpenTelemetry e dashboards Grafana.

## Visão Geral

Worker Agents está totalmente instrumentado com:
- **Métricas Prometheus**: 30+ métricas cobrindo lifecycle, execução, dependências, Kafka e operações de API
- **OpenTelemetry tracing**: Tracing distribuído com spans customizados para execução de tickets
- **Dashboard Grafana**: Dashboard pré-construído com 21 painéis organizados em 6 seções

## Métricas Prometheus

### Métricas de Lifecycle

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `worker_agent_startup_total` | Counter | - | Total de inicializações do Worker Agent |
| `worker_agent_registered_total` | Counter | - | Total de registros no Service Registry |
| `worker_agent_heartbeat_total` | Counter | `status` | Total de heartbeats enviados |
| `worker_agent_deregistered_total` | Counter | - | Total de deregistros do Service Registry |

### Métricas de Tickets e Execução

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `worker_agent_tickets_consumed_total` | Counter | `task_type` | Tickets consumidos do Kafka |
| `worker_agent_tickets_processing_total` | Counter | `task_type` | Tickets em processamento |
| `worker_agent_tickets_completed_total` | Counter | `task_type` | Tickets concluídos com sucesso |
| `worker_agent_tickets_failed_total` | Counter | `task_type`, `error_type` | Tickets falhados |
| `worker_agent_active_tasks` | Gauge | - | Número atual de tarefas ativas |
| `worker_agent_task_duration_seconds` | Histogram | `task_type` | Duração de execução de tarefas |
| `worker_agent_task_retries_total` | Counter | `task_type`, `attempt` | Tentativas de retry |
| `worker_agent_tasks_cancelled_total` | Counter | - | Tarefas canceladas durante shutdown |

### Métricas de Dependências

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `worker_agent_dependency_checks_total` | Counter | `result` | Resultados de verificação de dependências (success/failed/timeout) |
| `worker_agent_dependency_wait_duration_seconds` | Histogram | - | Tempo de espera por dependências |

### Métricas de Chamadas API

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `worker_agent_ticket_api_calls_total` | Counter | `method`, `status` | Chamadas ao Execution Ticket Service |
| `worker_agent_ticket_status_updates_total` | Counter | `status` | Atualizações de status de tickets |
| `worker_agent_ticket_tokens_obtained_total` | Counter | - | Tokens JWT obtidos para tickets |

### Métricas Kafka

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `worker_agent_kafka_consumer_initialized_total` | Counter | - | Inicializações do consumer Kafka |
| `worker_agent_kafka_producer_initialized_total` | Counter | - | Inicializações do producer Kafka |
| `worker_agent_kafka_consumer_errors_total` | Counter | `error_type` | Erros do consumer por tipo |
| `worker_agent_kafka_producer_errors_total` | Counter | - | Erros do producer |
| `worker_agent_results_published_total` | Counter | `status` | Resultados publicados no Kafka |

### Métricas de Executores

| Métrica | Tipo | Labels | Descrição |
|---------|------|--------|-----------|
| `worker_agent_executors_registered_total` | Counter | `task_type` | Executores registrados |
| `worker_agent_build_tasks_executed_total` | Counter | `status` | Execuções de tarefas BUILD |
| `worker_agent_build_duration_seconds` | Histogram | `stage` | Duração de etapas de build |
| `worker_agent_build_artifacts_generated_total` | Counter | `type` | Artefatos de build gerados |
| `worker_agent_deploy_tasks_executed_total` | Counter | `status` | Execuções de tarefas DEPLOY |
| `worker_agent_deploy_duration_seconds` | Histogram | `stage` | Duração de etapas de deploy |
| `worker_agent_deploy_rollbacks_total` | Counter | `reason` | Operações de rollback |
| `worker_agent_test_tasks_executed_total` | Counter | `status`, `suite` | Execuções de tarefas TEST |
| `worker_agent_test_duration_seconds` | Histogram | `suite` | Duração de suítes de teste |
| `worker_agent_tests_passed_total` | Counter | `suite` | Testes aprovados |
| `worker_agent_tests_failed_total` | Counter | `suite` | Testes reprovados |
| `worker_agent_test_coverage_percent` | Gauge | `suite` | Percentual de cobertura de testes |
| `worker_agent_validate_tasks_executed_total` | Counter | `status`, `tool` | Execuções de tarefas VALIDATE |
| `worker_agent_validate_duration_seconds` | Histogram | `tool` | Duração de validações |
| `worker_agent_validate_violations_total` | Counter | `severity`, `tool` | Violações de validação |

## Spans OpenTelemetry

### Span de Execução de Ticket

O span principal que envolve a execução do ticket é criado em `ExecutionEngine._execute_ticket()`:

```python
tracer = get_tracer()
with tracer.start_as_current_span("ticket_execution") as span:
    span.set_attribute("neural.hive.ticket_id", ticket_id)
    span.set_attribute("neural.hive.task_type", task_type)
    span.set_attribute("neural.hive.plan_id", ticket.get('plan_id', ''))
    span.set_attribute("neural.hive.intent_id", ticket.get('intent_id', ''))
```

**Atributos do Span:**

| Atributo | Descrição |
|----------|-----------|
| `neural.hive.ticket_id` | Identificador único do ticket |
| `neural.hive.task_type` | Tipo de tarefa (BUILD, DEPLOY, TEST, VALIDATE, EXECUTE) |
| `neural.hive.plan_id` | Identificador do plano de execução |
| `neural.hive.intent_id` | Identificador da intenção original |
| `error` | Definido como `true` em caso de falha |
| `error.type` | Categoria do erro (dependency, execution_error, timeout) |

## Dashboard Grafana

O dashboard Worker Agents está localizado em `monitoring/dashboards/worker-agents.json` com UID `worker-agents-dashboard`.

### Seções do Dashboard

1. **Lifecycle & Health** - Contagem de startups, tarefas ativas, taxa de heartbeats
2. **Tickets & Execution** - Taxa de consumo, conclusão vs falhas, percentis de duração, retries
3. **Dependencies** - Resultados de verificação, percentis de tempo de espera
4. **Kafka Integration** - Resultados publicados, erros de consumer/producer
5. **API Calls** - Taxa de chamadas API de tickets, taxa de atualizações de status
6. **Executors** - Executores registrados, cancelamentos de tarefas

### Acessando o Dashboard

1. Abra o Grafana na URL configurada
2. Navegue para Dashboards → Browse
3. Pesquise por "Worker Agents - Execution Layer"
4. Ou acesse diretamente via UID: `/d/worker-agents-dashboard`

## Queries Prometheus Úteis

### Taxa de Sucesso de Tarefas

```promql
sum(rate(worker_agent_tickets_completed_total[5m])) /
(sum(rate(worker_agent_tickets_completed_total[5m])) + sum(rate(worker_agent_tickets_failed_total[5m])))
```

### Duração Média de Tarefa por Tipo

```promql
histogram_quantile(0.50,
  sum(rate(worker_agent_task_duration_seconds_bucket[5m])) by (le, task_type)
)
```

### Taxa de Falha de Verificação de Dependências

```promql
sum(rate(worker_agent_dependency_checks_total{result="failed"}[5m])) /
sum(rate(worker_agent_dependency_checks_total[5m]))
```

### Taxa de Erro do Consumer Kafka

```promql
sum(rate(worker_agent_kafka_consumer_errors_total[5m])) by (error_type)
```

### Tarefas Ativas ao Longo do Tempo

```promql
worker_agent_active_tasks
```

### Taxa de Retry por Tipo de Tarefa

```promql
sum(rate(worker_agent_task_retries_total[5m])) by (task_type)
```

## Troubleshooting

### Alta Taxa de Falha de Tarefas

1. Verifique `worker_agent_tickets_failed_total` pelo label `error_type`
2. Procure erros `dependency` indicando falhas upstream
3. Verifique `execution_error` para problemas específicos da tarefa
4. Revise erros `timeout` para violações de SLA

### Timeouts de Dependências

1. Monitore `worker_agent_dependency_checks_total{result="timeout"}`
2. Verifique `worker_agent_dependency_wait_duration_seconds` P99
3. Confirme que tarefas upstream estão concluindo dentro do tempo esperado
4. Revise a configuração de `dependency_check_max_attempts` e `dependency_check_interval_seconds`

### Problemas com Kafka

1. Monitore `worker_agent_kafka_consumer_errors_total` e `worker_agent_kafka_producer_errors_total`
2. Verifique conectividade com Schema Registry
3. Valide credenciais SASL se usando autenticação
4. Revise conectividade com broker e permissões de tópicos

### Altas Taxas de Retry

1. Verifique `worker_agent_task_retries_total` pelo label `attempt`
2. Revise logs específicos da tarefa para causa raiz
3. Valide disponibilidade de serviços externos (CodeForge, ArgoCD, etc.)
4. Verifique restrições de recursos (memória, CPU, rede)

## Localizações da Instrumentação

| Componente | Arquivo | Métricas Inicializadas |
|------------|---------|------------------------|
| WorkerAgentMetrics | `src/observability/metrics.py` | Todas as definições de métricas |
| ExecutionTicketClient | `src/clients/execution_ticket_client.py` | Chamadas API, atualizações de status, tokens |
| KafkaTicketConsumer | `src/clients/kafka_ticket_consumer.py` | Init do consumer, consumo, erros |
| KafkaResultProducer | `src/clients/kafka_result_producer.py` | Init do producer, publicação, erros |
| DependencyCoordinator | `src/engine/dependency_coordinator.py` | Verificações de dependências, tempo de espera |
| TaskExecutorRegistry | `src/executors/registry.py` | Registros de executores |
| ExecutionEngine | `src/engine/execution_engine.py` | Processamento de tickets, spans OpenTelemetry |
| main.py | `src/main.py` | Wiring de métricas, init de observabilidade |

## Configuração

A observabilidade é configurada via variáveis de ambiente:

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `OTEL_EXPORTER_ENDPOINT` | Endpoint do collector OpenTelemetry | `http://localhost:4317` |
| `OTEL_SERVICE_NAME` | Nome do serviço para traces | `worker-agents` |
| `PROMETHEUS_PORT` | Porta para endpoint /metrics | `8000` |

## Documentação Relacionada

- [OBSERVABILITY_DEPLOYMENT.md](./OBSERVABILITY_DEPLOYMENT.md) - Configuração de deployment
- [SECRETS_MANAGEMENT_GUIDE.md](./SECRETS_MANAGEMENT_GUIDE.md) - Integração com Vault para credenciais
- [security-operations-guide.md](./security-operations-guide.md) - Procedimentos de operações de segurança
