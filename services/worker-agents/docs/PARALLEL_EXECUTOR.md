# Parallel Executor - Execução Paralela Avançada

## Visão Geral

O `ParallelExecutor` é um componente avançado do Worker Agents que permite execução paralela eficiente de múltiplos Execution Tickets com suporte a:

- **Filas de Prioridade**: CRITICAL, HIGH, MEDIUM, LOW
- **Batch Processing**: Agrupamento automático de tickets do mesmo tipo
- **Coordenação de Dependências**: Execução respeitando grafos de dependência
- **Limites de Concorrência**: Global e por task_type
- **Processor Workers**: Múltiplos workers processando filas concorrentemente

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    Parallel Executor                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐                                           │
│  │ CRITICAL Queue│ ┐                                        │
│  └──────────────┘  │                                        │
│  ┌──────────────┐  │                                        │
│  │ HIGH Queue   │  │ Priority Queues                        │
│  └──────────────┘  │ (4 níveis)                              │
│  ┌──────────────┐  │                                        │
│  │ MEDIUM Queue │  │                                        │
│  └──────────────┘  │                                        │
│  ┌──────────────┐  │                                        │
│  │ LOW Queue    │ ┘                                        │
│  └──────────────┘                                           │
│         ↓                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │      Processor Workers (N)          │                   │
│  └──────────────────────────────────────┘                   │
│         ↓                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │    Global Semaphore (max_parallel)   │                   │
│  └──────────────────────────────────────┘                   │
│         ↓                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │    Type Semaphores (by task_type)    │                   │
│  └──────────────────────────────────────┘                   │
│         ↓                                                    │
│  ┌──────────────────────────────────────┐                   │
│  │       ExecutionEngine                │                   │
│  └──────────────────────────────────────┘                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Uso Básico

### Execução Paralela Simples

```python
from src.engine.parallel_executor import ParallelExecutor, ParallelExecutionConfig

# Configurar
config = ParallelExecutionConfig(
    max_parallel_tasks=10,
    enable_batching=True,
    batch_size=5,
    enable_priority_queue=True
)

executor = ParallelExecutor(config, execution_engine, metrics)

# Executar tickets independentes em paralelo
tickets = [
    {'ticket_id': 't1', 'task_type': 'BUILD', 'parameters': {}},
    {'ticket_id': 't2', 'task_type': 'BUILD', 'parameters': {}},
    {'ticket_id': 't3', 'task_type': 'DEPLOY', 'parameters': {}},
]

results = await executor.execute_parallel_independent(tickets)
# [t1, t2, t3] executados concorrentemente
```

### Submissão com Prioridade

```python
# Ticket crítico será processado antes
await executor.submit_ticket(
    ticket={'ticket_id': 'urgent', 'task_type': 'DEPLOY', 'parameters': {}},
    priority=TaskPriority.CRITICAL
)

# Tickets normais
await executor.submit_ticket(normal_ticket, TaskPriority.MEDIUM)
await executor.submit_ticket(background_ticket, TaskPriority.LOW)
```

### Execução com Dependências

```python
tickets = [
    {'ticket_id': 'base', 'task_type': 'BUILD', 'parameters': {}},
    {'ticket_id': 'app', 'task_type': 'BUILD', 'parameters': {}},
    {'ticket_id': 'deploy', 'task_type': 'DEPLOY', 'parameters': {}},
]

dependency_graph = {
    'base': [],
    'app': ['base'],      # app depende de base
    'deploy': ['app'],    # deploy depende de app
}

results = await executor.execute_with_dependencies(tickets, dependency_graph)
# Executa: base → app → deploy (paralelismo onde possível)
```

### Processor Workers Contínuos

```python
# Iniciar processadores que consomem filas continuamente
await executor.start(num_workers=4)

# Submeter tickets para as filas
for ticket in tickets:
    await executor.submit_ticket(ticket, TaskPriority.HIGH)

# Processadores executam automaticamente
# Aguardar ou cancelar conforme necessário
await executor.stop(timeout_seconds=30)
```

## Configuração

### ParallelExecutionConfig

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| `max_parallel_tasks` | int | 10 | Limite global de tarefas paralelas |
| `max_parallel_by_type` | Dict[str, int] | {} | Limites específicos por task_type |
| `enable_batching` | bool | True | Habilita agrupamento de tickets |
| `batch_size` | int | 5 | Tamanho máximo do batch |
| `batch_timeout_seconds` | float | 1.0 | Timeout para formar batch |
| `enable_priority_queue` | bool | True | Habilita filas de prioridade |

### TaskPriority

| Prioridade | Valor | Uso |
|------------|-------|-----|
| `CRITICAL` | 1 | Compensations, SLA críticos |
| `HIGH` | 2 | User-facing, timeout curto |
| `MEDIUM` | 3 | Batch jobs, processamento normal |
| `LOW` | 4 | Background, cleanup |

## Métricas Prometheus

### Executor Paralelo

- `worker_agent_parallel_tickets_submitted_total{task_type, priority}` - Tickets submetidos
- `worker_agent_parallel_ticket_duration_seconds{task_type}` - Duração de execução
- `worker_agent_parallel_tickets_failed_total{task_type, error_type}` - Falhas
- `worker_agent_parallel_batch_duration_seconds` - Duração de batches
- `worker_agent_parallel_queue_size{priority}` - Tamanho das filas
- `worker_agent_parallel_active_tasks_by_type{task_type}` - Tarefas ativas por tipo

### Exemplo de Queries PromQL

```promql
# Throughput de processamento paralelo
rate(worker_agent_parallel_tickets_submitted_total[5m])

# Duração P95 por tipo
histogram_quantile(0.95,
  rate(worker_agent_parallel_ticket_duration_seconds_bucket[5m])
)

# Tamanho médio da fila CRITICAL
avg(worker_agent_parallel_queue_size{priority="CRITICAL"})
```

## Casos de Uso

### 1. Pipeline CI/CD Paralelo

```python
# Builds paralelos de múltiplos componentes
build_tickets = [
    {'ticket_id': f'build-{comp}', 'task_type': 'BUILD', 'parameters': {...}}
    for comp in ['frontend', 'backend', 'worker']
]

results = await executor.execute_parallel_independent(build_tickets)
# 3 builds executados simultaneamente
```

### 2. Deploy Multi-Região

```python
# Deploys paralelos para múltiplas regiões
deploy_tickets = [
    {'ticket_id': f'deploy-{region}', 'task_type': 'DEPLOY',
     'parameters': {'region': region, ' replicas': 3}}
    for region in ['us-east', 'us-west', 'eu-west']
]

results = await executor.execute_parallel_independent(deploy_tickets)
```

### 3. Validações Paralelas

```python
# Múltiplas validações simultâneas
validation_tickets = [
    {'ticket_id': 'val-opa', 'task_type': 'VALIDATE',
     'parameters': {'validation_type': 'policy'}},
    {'ticket_id': 'val-sast', 'task_type': 'VALIDATE',
     'parameters': {'validation_type': 'sast'}},
    {'ticket_id': 'val-sec', 'task_type': 'VALIDATE',
     'parameters': {'validation_type': 'security'}},
]

results = await executor.execute_parallel_independent(validation_tickets)
```

### 4. Workflow com Dependências

```python
# Pipeline: build → test → deploy
tickets = [
    {'ticket_id': 'build', 'task_type': 'BUILD', 'parameters': {}},
    {'ticket_id': 'unit-test', 'task_type': 'TEST', 'parameters': {}},
    {'ticket_id': 'integration-test', 'task_type': 'TEST', 'parameters': {}},
    {'ticket_id': 'deploy-staging', 'task_type': 'DEPLOY', 'parameters': {}},
]

deps = {
    'build': [],
    'unit-test': ['build'],
    'integration-test': ['build'],  # paralelo com unit-test
    'deploy-staging': ['unit-test', 'integration-test'],
}

results = await executor.execute_with_dependencies(tickets, deps)
# build → [unit-test, integration-test] → deploy-staging
```

## Boas Práticas

### 1. Limites de Concorrência

```python
# Limitar globalmente
config = ParallelExecutionConfig(max_parallel_tasks=20)

# Limitar por tipo (I/O-bound vs CPU-bound)
config = ParallelExecutionConfig(
    max_parallel_tasks=20,
    max_parallel_by_type={
        'BUILD': 5,      # CPU-intensive
        'TEST': 10,      # Mixed
        'DEPLOY': 3,     # I/O-intensive
        'VALIDATE': 15,  # I/O-bound
    }
)
```

### 2. Priorização Apropriada

```python
# CRITICAL: Compensações, rollbacks
await executor.submit_ticket(compensation_ticket, TaskPriority.CRITICAL)

# HIGH: User requests, interativos
await executor.submit_ticket(user_deploy, TaskPriority.HIGH)

# MEDIUM: Batch jobs normais
await executor.submit_ticket(batch_report, TaskPriority.MEDIUM)

# LOW: Cleanup, logs
await executor.submit_ticket(log_cleanup, TaskPriority.LOW)
```

### 3. Batch Processing

```python
# Para muitos tickets pequenos, habilitar batching
config = ParallelExecutionConfig(
    enable_batching=True,
    batch_size=10,
    batch_timeout_seconds=0.5
)

# Tickets são agrupados automaticamente por task_type
await executor.submit_batch(many_tickets)
```

### 4. Timeouts

```python
# Sempre definir timeout para operações em lote
results = await executor.execute_parallel_independent(
    tickets,
    timeout_seconds=300.0  # 5 minutos máximo
)
```

## Troubleshooting

### Filas Crescendo Infinitamente

**Sintoma:** `parallel_queue_size` aumenta continuamente.

**Causas:**
1. Processadores não conseguem acompanhar a taxa de chegada
2. Deadlock em dependências
3. Timeout muito alto em tickets

**Soluções:**
- Aumentar `num_workers`
- Aumentar `max_parallel_tasks`
- Revisar timeouts
- Verificar métricas de `parallel_active_tasks_by_type`

### Alto Uso de Memória

**Sintoma:** Uso de memória cresce com execução paralela.

**Causas:**
- `max_parallel_tasks` muito alto
- Tickets com payloads grandes
- Memory leak em executores

**Soluções:**
- Reduzir paralelismo
- Implementar streaming para payloads grandes
- Profile de memória dos executores

### Dependências Travadas

**Sintoma:** Tickets pendentes com dependências satisfeitas.

**Causas:**
- Ciclo no grafo de dependências
- Falha em não reportar status corretamente

**Soluções:**
- Verificar aciclicidade do grafo
- Garantir atualização de status mesmo em erro
- Usar timeout em `execute_with_dependencies`

## Roadmap

### Próximas Melhorias

- [ ] Dynamic priority adjustment baseado em SLA
- [ ] Work stealing entre processadores
- [ ] Adaptive batching baseado em load
- [ ] Integration with Kubernetes batch API
- [ ] Distributed execution (multi-node)
