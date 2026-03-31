# Priority Queues & Scheduler - Implementação no Orchestrator Dynamic

## Visão Geral

O Orchestrator Dynamic implementa um sistema de filas prioritárias multi-nível para escalonamento de tickets de execução. O scheduler utiliza weighted round-robin com prioridades adaptativas baseadas em SLA, risco e histórico de execução.

## Arquitetura

### Componentes Principais

```
┌─────────────────────────────────────────────────────────────────┐
│                    Priority Scheduler                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              PriorityQueues (4 níveis)                   │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ CRITICAL │ │   HIGH   │ │  NORMAL  │ │   LOW    │  │  │
│  │  │  Q=0.4   │ │  Q=0.3   │ │  Q=0.2   │ │  Q=0.1   │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  QueueManager                             │  │
│  │  - enqueue() / dequeue()                                 │  │
│  │  - requeue() / peek()                                    │  │
│  │  - get_queue_size() / re_prioritize()                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 RePrioritizer                             │  │
│  │  - Detect mudanças de prioridade                         │  │
│  │  - Mover entre filas                                     │  │
│  │  - Batch processing                                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                PreemptionManager                          │  │
│  │  - Avaliar preempção                                     │  │
│  │  - Executar compensação                                  │  │
│  │  - Rastrear histórico                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Arquivos de Implementação

| Arquivo | Propósito |
|---------|-----------|
| `src/scheduler/priority_queues.py` | PriorityQueues, PriorityLevel |
| `src/scheduler/queue_manager.py` | QueueManager |
| `src/scheduler/priority_calculator.py` | PriorityCalculator |
| `src/scheduler/reprioritizer.py` | RePrioritizer |
| `src/scheduler/sla_reprioritizer.py` | SLARePrioritizer |
| `src/scheduler/preemption.py` | PreemptionManager |
| `src/scheduler/preemption_rules.py` | PreemptionRules |
| `src/scheduler/adaptive_priority.py` | AdaptivePriorityCalculator |
| `src/scheduler/scheduler.py` | Scheduler principal |
| `src/activities/scheduler_activity.py` | Activities Temporal |

## Níveis de Prioridade

### PriorityLevel Enum

```python
class PriorityLevel(str, Enum):
    """Níveis de prioridade para tickets."""
    CRITICAL = 'CRITICAL'  # Q=0.4, max_weight=4
    HIGH = 'HIGH'          # Q=0.3, max_weight=3
    NORMAL = 'NORMAL'      # Q=0.2, max_weight=2
    LOW = 'LOW'            # Q=0.1, max_weight=1
```

### Mapeamento Risk Band → Priority

| Risk Band | Priority Base | Priority Max (com urgência) |
|-----------|---------------|-----------------------------|
| critical | CRITICAL | CRITICAL |
| high | HIGH | CRITICAL |
| normal | NORMAL | HIGH |
| low | LOW | NORMAL |

## PriorityQueues

### Estrutura de Dados

```python
class PriorityQueues:
    """Filas prioritárias multi-nível."""

    def __init__(self, config):
        self.queues = {
            PriorityLevel.CRITICAL: [],
            PriorityLevel.HIGH: [],
            PriorityLevel.NORMAL: [],
            PriorityLevel.LOW: []
        }
        self.max_sizes = {
            PriorityLevel.CRITICAL: config.critical_queue_size or 100,
            PriorityLevel.HIGH: config.high_queue_size or 500,
            PriorityLevel.NORMAL: config.normal_queue_size or 1000,
            PriorityLevel.LOW: config.low_queue_size or 2000
        }
```

### Operações

```python
def enqueue(self, ticket: Dict, priority: PriorityLevel) -> bool
def dequeue(self) -> Optional[Dict]
def peek(self, priority: PriorityLevel) -> Optional[Dict]
def get_queue_size(self, priority: PriorityLevel) -> int
def get_total_size(self) -> int
def is_empty(self, priority: PriorityLevel) -> bool
def clear(self, priority: Optional[PriorityLevel] = None)
```

## Weighted Round-Robin

### Algoritmo

```python
def weighted_round_robin(self) -> Optional[Dict]:
    """
    Seleciona próximo ticket usando weighted round-robin.

    Pesos:
    - CRITICAL: 40% (Q=0.4)
    - HIGH: 30% (Q=0.3)
    - NORMAL: 20% (Q=0.2)
    - LOW: 10% (Q=0.1)
    """
    # 1. Calcular quota base para cada fila
    # 2. Multiplicar por fator de utilização
    # 3. Selecionar fila com maior quota
    # 4. Retornar ticket da fila selecionada
```

### Exemplo de Seleção

```
Estado das filas:
  CRITICAL: 5 tickets
  HIGH: 12 tickets
  NORMAL: 8 tickets
  LOW: 20 tickets

Cálculo de quota:
  quota_c = 5 * 0.4 / max_size_c = 2.0
  quota_h = 12 * 0.3 / max_size_h = 3.6
  quota_n = 8 * 0.2 / max_size_n = 1.6
  quota_l = 20 * 0.1 / max_size_l = 2.0

Seleção: HIGH (maior quota)
```

## PriorityCalculator

### Cálculo de Score

```python
def calculate_priority_score(self, ticket: Dict) -> float:
    """
    Calcula score de prioridade [0.0, 1.0].

    Fatores:
    - risk_band: 40% (critical=1.0, high=0.75, normal=0.5, low=0.25)
    - qos: 30% (EXACTLY_ONCE=1.0, AT_LEAST_ONCE=0.7, AT_MOST_ONCE=0.4)
    - sla: 30% (urgency baseada em tempo restante)
    """
    risk_score = self._get_risk_score(ticket['risk_band'])
    qos_score = self._get_qos_score(ticket['qos'])
    sla_score = self._get_sla_urgency(ticket)

    base_score = (
        risk_score * 0.4 +
        qos_score * 0.3 +
        sla_score * 0.3
    )

    # Aplicar ajuste adaptativo
    adaptive_adjustment = self.adaptive_calculator.calculate_adaptive_adjustment(ticket)
    final_score = self.apply_adaptive_adjustment(base_score, adaptive_adjustment)

    return min(max(final_score, 0.0), 1.0)
```

### Mapeamento Score → Priority

| Score Range | Priority |
|-------------|----------|
| 0.90 - 1.00 | CRITICAL |
| 0.70 - 0.89 | HIGH |
| 0.40 - 0.69 | NORMAL |
| 0.00 - 0.39 | LOW |

## RePrioritizer

### Gatilhos de Re-priorização

```python
class RePrioritizer:
    """Gerencia re-priorização dinâmica de tickets."""

    async def on_sla_warning(self, event: Dict) -> Dict:
        """SLA entrou em warning zone (< 20% restante)."""
        ticket_id = event['ticket_id']
        urgency = event['sla_urgency']

        if urgency > 0.8:
            new_priority = 'CRITICAL'
        elif urgency > 0.5:
            new_priority = 'HIGH'
        else:
            new_priority = 'NORMAL'

        return await self._reprioritize(ticket_id, new_priority, 'sla_warning')

    async def on_risk_band_changed(self, event: Dict) -> Dict:
        """Risk band do ticket mudou."""
        old_risk = event['old_risk_band']
        new_risk = event['new_risk_band']
        ticket_id = event['ticket_id']

        new_priority = self.queue_manager.map_risk_to_priority(new_risk)
        return await self._reprioritize(ticket_id, new_priority, 'risk_band_changed')

    async def on_deadline_approaching(self, event: Dict) -> Dict:
        """Deadline se aproximando (< 60s restantes)."""
        ticket_id = event['ticket_id']
        remaining_ms = event['remaining_ms']

        if remaining_ms < 30000:  # < 30s
            new_priority = 'CRITICAL'
        else:
            new_priority = 'HIGH'

        return await self._reprioritize(ticket_id, new_priority, 'deadline_approaching')
```

### Batch Processing

```python
async def reprioritize_batch(
    self,
    tickets: List[Dict],
    batch_id: str
) -> Dict:
    """Re-prioriza lote de tickets."""
    results = {
        'batch_id': batch_id,
        'total': len(tickets),
        'reprioritized': 0,
        'unchanged': 0,
        'changes': []
    }

    for ticket in tickets:
        old_priority = ticket.get('priority', 'NORMAL')
        new_score = self.priority_calculator.calculate_priority_score(ticket)
        new_priority = self._score_to_priority(new_score)

        if new_priority != old_priority:
            await self._move_ticket(ticket, old_priority, new_priority)
            results['reprioritized'] += 1
            results['changes'].append({
                'ticket_id': ticket['ticket_id'],
                'from': old_priority,
                'to': new_priority,
                'score': new_score
            })
        else:
            results['unchanged'] += 1

    return results
```

## PreemptionManager

### Matrix de Preempção

```python
PREEMPTION_MATRIX = {
    'CRITICAL': ['HIGH', 'NORMAL', 'LOW'],  # CRITICAL pode preemptar todos
    'HIGH': ['LOW'],                         # HIGH pode preemptar apenas LOW
    'NORMAL': ['LOW'],                       # NORMAL pode preemptar apenas LOW
    'LOW': []                                # LOW não preempta ninguém
}
```

### Regras de Preempção

1. **Execution Progress**: Preempção apenas se progresso < 30%
2. **Compensatable**: Ticket deve ser compensatable
3. **Priority Matrix**: Seguir matrix de preempção
4. **Cost Threshold**: Custo de preempção < 50%

### Exemplo de Decisão

```python
def can_preempt(
    self,
    high_priority_ticket: Dict,
    low_priority_ticket: Dict
) -> PreemptionDecision:
    """Verifica se ticket de alta pode preemptar ticket de baixa."""

    # Regra 1: Verificar matrix de prioridade
    if not self._is_preemption_allowed(high_priority, low_priority):
        return PreemptionDecision.DENIED_PRIORITY_DIFF

    # Regra 2: Verificar progresso de execução
    progress = self._get_execution_progress(low_priority_ticket)
    if progress > self.max_execution_progress_pct:
        return PreemptionDecision.DENIED_EXECUTION_PROGRESS

    # Regra 3: Verificar se é compensatable
    if not self._is_compensatable(low_priority_ticket):
        return PreemptionDecision.DENIED_NOT_COMPENSATABLE

    return PreemptionDecision.ALLOWED
```

### Execução de Preempção

```python
async def preempt_ticket(
    self,
    low_priority_ticket: Dict,
    reason: str = 'priority_preemption'
) -> Dict:
    """Executa preempção de ticket."""
    # 1. Validar se pode preemptar
    decision = self._validate_preemption(low_priority_ticket)
    if decision != PreemptionDecision.ALLOWED:
        return {'status': 'DENIED', 'reason': decision.value}

    # 2. Compensar ticket
    compensation_result = await self._compensate_ticket(low_priority_ticket)
    if not compensation_result['success']:
        return {'status': 'FAILED', 'error': 'compensation_failed'}

    # 3. Re-enfileirar ticket
    requeue_result = await self._requeue_ticket(low_priority_ticket)

    return {
        'status': 'SUCCESS',
        'ticket_id': low_priority_ticket['ticket_id'],
        'compensation_ticket_id': compensation_result['compensation_ticket_id']
    }
```

## AdaptivePriorityCalculator

### Ajuste Adaptativo

```python
def calculate_adaptive_adjustment(self, ticket: Dict) -> float:
    """
    Calcula ajuste de prioridade baseado em histórico.

    Returns:
        Ajuste no intervalo [-0.2, +0.2]
    """
    history = self._get_recent_history(ticket)

    if not history:
        return 0.0

    stats = self._get_history_statistics(history)

    # Ajuste positivo para execuções lentas
    if stats['avg_execution_time_ms'] > self.execution_time_threshold:
        slow_ratio = stats['avg_execution_time_ms'] / self.execution_time_threshold
        return min(slow_ratio * 0.1, 0.2)

    # Ajuste negativo para alta taxa de falha
    if stats['failure_rate'] > self.failure_rate_threshold:
        excess = stats['failure_rate'] - self.failure_rate_threshold
        return -min(excess * 0.5, 0.2)

    # Ajuste positivo para execuções rápidas consistentes
    if stats['avg_execution_time_ms'] < self.execution_time_threshold * 0.7:
        return 0.05

    return 0.0
```

### Histórico de Execução

```python
def record_execution(
    self,
    ticket: Dict,
    execution_time_ms: int,
    status: str
) -> None:
    """Registra execução para cálculo adaptativo."""
    ticket_type = self._get_ticket_type(ticket)

    execution_record = {
        'ticket_id': ticket['ticket_id'],
        'ticket_type': ticket_type,
        'execution_time_ms': execution_time_ms,
        'status': status,
        'timestamp': self._get_timestamp()
    }

    self.execution_history.append(execution_record)
    self._cleanup_old_history()
```

## Scheduler Integration

### Fluxo de Escalonamento

```
1. Receber ticket (via Kafka ou API)
   ↓
2. Calcular prioridade inicial (PriorityCalculator)
   ↓
3. Enfileirar na fila apropriada (QueueManager.enqueue)
   ↓
4. Selecionar próximo ticket (weighted_round_robin)
   ↓
5. Verificar preempção (PreemptionManager)
   ↓
6. Executar atividade Temporal
   ↓
7. Publicar evento de conclusão
```

### Configuração

```python
class SchedulerConfig:
    """Configuração do Scheduler."""

    # Tamanhos das filas
    critical_queue_size: int = 100
    high_queue_size: int = 500
    normal_queue_size: int = 1000
    low_queue_size: int = 2000

    # Pesos de prioridade
    priority_weights: Dict[str, float] = {
        'risk': 0.4,
        'qos': 0.3,
        'sla': 0.3
    }

    # Preempção
    preemption_enabled: bool = True
    preemption_max_execution_progress_pct: float = 0.30

    # Re-priorização
    reprioritization_threshold: float = 0.15
    reprioritization_interval_ms: int = 30000  # 30s

    # Priority adaptativa
    adaptive_priority_enabled: bool = True
    adaptive_history_window_days: int = 7
    adaptive_execution_time_threshold: float = 1.5
    adaptive_failure_rate_threshold: float = 0.20
```

## Métricas

### Métricas Publicadas

```python
class SchedulerMetrics:
    # Filas
    gauge_queue_size: Gauge (por priority)
    counter_tickets_enqueued: Counter
    counter_tickets_dequeued: Counter

    # Escalonamento
    histogram_scheduling_latency: Histogram
    counter_preemptions_executed: Counter
    counter_reprioritizations: Counter

    # Performance
    histogram_ticket_execution_time: Histogram
    gauge_throughput_per_second: Gauge
```

## Testes

### Cobertura de Testes

- **Unit Tests**: 150+ testes em `tests/unit/scheduler/`
- **Integration Tests**: 35 testes em `tests/integration/`
- **Cobertura**: ~95%

### Exemplo de Teste

```python
@pytest.mark.asyncio
async def test_weighted_round_robin_selects_highest_quota():
    """Testa seleção por weighted round-robin."""
    queues = PriorityQueues(config)
    scheduler = Scheduler(queues, config)

    # Adicionar tickets
    queues.enqueue({'ticket_id': 'c1'}, PriorityLevel.CRITICAL)
    queues.enqueue({'ticket_id': 'h1'}, PriorityLevel.HIGH)
    queues.enqueue({'ticket_id': 'n1'}, PriorityLevel.NORMAL)

    # Selecionar deve respeitar quotas
    selected = scheduler.weighted_round_robin()
    assert selected is not None
    assert selected['queue'] in ['CRITICAL', 'HIGH']
```

## Monitoramento

### Health Checks

```python
async def health_check() -> Dict:
    """Health check do scheduler."""
    return {
        'status': 'healthy',
        'queues': {
            'CRITICAL': queues.get_queue_size(PriorityLevel.CRITICAL),
            'HIGH': queues.get_queue_size(PriorityLevel.HIGH),
            'NORMAL': queues.get_queue_size(PriorityLevel.NORMAL),
            'LOW': queues.get_queue_size(PriorityLevel.LOW)
        },
        'throughput': metrics.get_throughput(),
        'avg_latency': metrics.get_avg_latency()
    }
```

### Alertas

- **Queue Full**: Fila atinge 90% da capacidade
- **High Preemption Rate**: Taxa de preempção > 10%
- **Starvation Detection**: Tickets em LOW por > 30min
- **Scheduler Latency**: Latência > 1000ms

## Boas Práticas

### Design de Tickets

1. **Risk Band**: Definir risk band apropriado
2. **QoS**: Especificar requisitos de QoS
3. **Compensatable**: Marcar tickets compensatables
4. **Timeout**: Definir timeout realista

### Configuração de SLA

```python
ticket = {
    'ticket_id': 'ticket-001',
    'task_type': 'query',
    'risk_band': 'normal',  # NORMAL priority base
    'sla': {
        'timeout_ms': 300000,  # 5 minutos
        'deadline': now_ms + 300000
    },
    'qos': {
        'delivery_mode': 'AT_LEAST_ONCE',
        'consistency': 'EVENTUAL'
    },
    'compensatable': True
}
```

## Referências

- `tests/integration/test_reprioritization.py` - Testes de re-priorização
- `tests/unit/scheduler/` - Testes unitários
- `src/scheduler/` - Implementação principal
