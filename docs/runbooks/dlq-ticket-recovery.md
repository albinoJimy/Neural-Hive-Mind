# Runbook: Recuperacao de Tickets do DLQ

## Visao Geral

Este runbook descreve procedimentos para processar execution tickets que foram enviados para o Dead Letter Queue (DLQ) apos multiplas falhas de processamento.

## Quando Usar

- **Alerta:** `FlowCDLQMessagesAccumulating` disparado
- **Sintoma:** Tickets nao sendo processados apos multiplas tentativas
- **Impacto:** Tarefas do Flow C nao executadas, SLA em risco

## Diagnostico

### 1. Verificar Mensagens no DLQ

```bash
# Contar mensagens no DLQ (MongoDB)
kubectl exec -it mongodb-xxx -- mongosh

use neural_hive
db.execution_tickets_dlq.countDocuments({})

# Listar ultimas 10 mensagens
db.execution_tickets_dlq.find().sort({processed_at: -1}).limit(10).pretty()
```

### 2. Analisar Razoes de Falha

```bash
# Agrupar por tipo de erro
db.execution_tickets_dlq.aggregate([
  {
    $group: {
      _id: "$dlq_metadata.error_type",
      count: { $sum: 1 },
      examples: { $push: "$ticket_id" }
    }
  },
  { $sort: { count: -1 } }
])

# Agrupar por task_type
db.execution_tickets_dlq.aggregate([
  {
    $group: {
      _id: "$task_type",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

### 3. Verificar Metricas Prometheus

```promql
# Total de mensagens no DLQ
sum(worker_agent_dlq_messages_total)

# Taxa de envio para DLQ
rate(worker_agent_dlq_messages_total[5m])

# Distribuicao de retries
histogram_quantile(0.95, rate(worker_agent_ticket_retry_count_bucket[10m]))
```

## Resolucao

### Cenario 1: Falha Transitoria (ex: timeout, network error)

**Acao:** Republicar tickets no topico principal

```bash
# Script de republicacao
kubectl exec -it worker-agents-xxx -- python3 << 'EOF'
import asyncio
from pymongo import MongoClient
from confluent_kafka import Producer
import json

async def republish_tickets():
    # Conectar MongoDB
    mongo = MongoClient('mongodb://mongodb:27017')
    db = mongo['neural_hive']

    # Buscar tickets com erros transitorios
    tickets = db.execution_tickets_dlq.find({
        'dlq_metadata.error_type': {'$in': ['TimeoutError', 'ConnectionError', 'NetworkError']}
    })

    # Configurar producer Kafka
    producer = Producer({
        'bootstrap.servers': 'kafka:9092',
        'acks': 'all'
    })

    republished = 0
    for ticket in tickets:
        # Remover metadata DLQ
        ticket.pop('dlq_metadata', None)
        ticket.pop('processed_at', None)
        ticket.pop('processed_at_ms', None)
        ticket.pop('_id', None)

        # Resetar status para PENDING
        ticket['status'] = 'PENDING'

        # Publicar no topico principal
        producer.produce(
            topic='execution.tickets',
            key=ticket['ticket_id'].encode('utf-8'),
            value=json.dumps(ticket).encode('utf-8')
        )

        republished += 1

    producer.flush()
    print(f"Republicados {republished} tickets")

asyncio.run(republish_tickets())
EOF
```

### Cenario 2: Erro de Configuracao (ex: ArgoCD unreachable)

**Acao:** Corrigir configuracao e republicar

```bash
# 1. Identificar problema
kubectl logs worker-agents-xxx | grep -A 5 "dlq_message_received"

# 2. Corrigir (exemplo: ArgoCD credentials)
kubectl edit secret argocd-credentials -n neural-hive

# 3. Restart workers
kubectl rollout restart deployment worker-agents -n neural-hive

# 4. Republicar tickets (usar script acima)
```

### Cenario 3: Erro de Codigo (ex: bug no executor)

**Acao:** Corrigir codigo, deploy, republicar

```bash
# 1. Identificar bug nos logs
kubectl logs worker-agents-xxx | grep -B 10 "dlq_message_received"

# 2. Corrigir codigo localmente
# 3. Build e push nova imagem
# 4. Deploy nova versao
kubectl set image deployment/worker-agents worker-agents=neural-hive/worker-agents:v1.0.10

# 5. Aguardar rollout
kubectl rollout status deployment/worker-agents

# 6. Republicar tickets
```

### Cenario 4: Ticket Invalido (ex: schema invalido)

**Acao:** Marcar como nao recuperavel

```bash
# Mover para colecao de tickets invalidos
db.execution_tickets_invalid.insertMany(
  db.execution_tickets_dlq.find({
    'dlq_metadata.error_type': 'ValidationError'
  }).toArray()
)

# Remover do DLQ
db.execution_tickets_dlq.deleteMany({
  'dlq_metadata.error_type': 'ValidationError'
})
```

## Prevencao

### 1. Monitorar Retry Count

```promql
# Alerta quando p95 de retries > 2
histogram_quantile(0.95, rate(worker_agent_ticket_retry_count_bucket[10m])) > 2
```

### 2. Aumentar Timeout se Necessario

```yaml
# helm-charts/worker-agents/values.yaml
config:
  taskTimeoutMultiplier: 2.0  # Aumentar de 1.5 para 2.0
```

### 3. Aumentar Max Retries se Falhas Transitorias

```yaml
# helm-charts/worker-agents/values.yaml
kafka:
  dlq:
    maxRetriesBeforeDLQ: 5  # Aumentar de 3 para 5
```

## Escalacao

- **< 10 mensagens DLQ:** Investigar e resolver
- **10-50 mensagens DLQ:** Escalar para SRE
- **> 50 mensagens DLQ:** Incident critico, escalar para Engineering Lead

## Referencias

- [Kafka DLQ Strategy](../KAFKA_DLQ_STRATEGY.md)
- [Worker Agents Troubleshooting](./worker-agents-troubleshooting.md)
- [Flow C Integration](../PHASE2_FLOW_C_INTEGRATION.md)
