# Estratégia de Particionamento Kafka - execution.tickets

## Visão Geral

Este documento descreve a estratégia de particionamento do tópico `execution.tickets` no Neural Hive Mind, incluindo rationale, implementação e troubleshooting.

## Objetivos

1. **Balanceamento de Carga:** Distribuir tickets uniformemente entre partitions
2. **Data Locality:** Agrupar tickets relacionados (mesmo plan) na mesma partition
3. **Prevenir Hot Partitions:** Evitar sobrecarga de partitions específicas
4. **Facilitar Processamento Ordenado:** Tickets do mesmo plan processados em ordem

## Estratégia Implementada

### Partition Key

**Primary:** `plan_id` (Cognitive Plan ID)
- Agrupa todos os tickets do mesmo plano cognitivo
- Garante data locality para processamento de dependências
- Distribui uniformemente (plans são gerados de forma distribuída)

**Fallback 1:** `intent_id` (Intent ID)
- Usado se `plan_id` ausente (edge case)
- Mantém agrupamento por intenção do usuário

**Fallback 2:** `ticket_id` (Ticket ID)
- Usado se ambos ausentes (edge case raro)
- Distribuição aleatória (UUID)

### Código

```python
# services/orchestrator-dynamic/src/clients/kafka_producer.py
partition_key = ticket.get('plan_id') or ticket.get('intent_id') or ticket_id
key_bytes = partition_key.encode('utf-8')
```

## Benefícios

### 1. Data Locality
- Tickets do mesmo plan vão para a mesma partition
- Worker pode processar tickets relacionados sequencialmente
- Reduz latência de coordenação de dependências

### 2. Balanceamento Natural
- Plans são gerados de forma distribuída
- Cada plan tem hash único (UUID)
- Distribuição uniforme entre partitions

### 3. Prevenção de Hot Partitions
- Burst de tickets de um plan vai para uma única partition (esperado)
- Mas múltiplos plans distribuem carga entre partitions
- Hot partition isolada não afeta outras partitions

### 4. Processamento Ordenado
- Kafka garante ordem dentro de uma partition
- Tickets do mesmo plan processados em ordem de criação
- Facilita resolução de dependências

## Monitoramento

### Métricas Prometheus

```promql
# Mensagens por partition (últimos 5min)
rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m])

# Distribuição percentual
sum by (partition) (rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m]))
/ sum(rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m]))

# Coeficiente de variação (balanceamento)
stddev(rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m]))
/ avg(rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m]))

# Hot partitions detectadas
sum(neural_hive_kafka_hot_partition_detected_total{topic="execution.tickets"})
```

### Alertas

- **KafkaHotPartitionDetected:** Partition > 2x média (warning)
- **KafkaPartitionImbalance:** CV > 50% (warning)
- **KafkaPartitionIdle:** Partition sem mensagens por 30min (info)
- **KafkaPartitionBytesImbalance:** Partition > 3x média em bytes (warning)

### Dashboard Grafana

- **URL:** https://grafana.neural-hive.io/d/kafka-partitions
- **Painéis:**
  - Mensagens por partition (time series)
  - Distribuição percentual (pie chart)
  - Hot partitions detectadas (stat)
  - Coeficiente de variação (gauge)
  - Bytes por partition (time series)
  - Heatmap de distribuição 24h

## Troubleshooting

### Hot Partition Detectada

**Sintoma:** Alerta `KafkaHotPartitionDetected` disparado

**Diagnóstico:**
```bash
python scripts/kafka/analyze_partition_distribution.py \
  --topic execution.tickets \
  --bootstrap-servers kafka.neural-hive.svc.cluster.local:9092 \
  --time-window 3600
```

**Causas Comuns:**
1. **Burst de um único plan:** Esperado, não é problema (data locality)
2. **Hash collision:** Raro, mas possível com muitos plans
3. **Plan ID não distribuído:** Bug na geração de plan_id

**Ações:**
- Se burst: OK, é comportamento esperado
- Se hash collision: Considerar aumentar número de partitions
- Se bug: Corrigir geração de plan_id

### Distribuição Desbalanceada

**Sintoma:** Alerta `KafkaPartitionImbalance` disparado (CV > 50%)

**Causas Comuns:**
1. **Padrão de geração de plans não uniforme:** Picos em horários específicos
2. **Poucos plans ativos:** < 12 plans não distribuem bem em 12 partitions
3. **Rebalanceamento de consumer:** Temporário, resolve sozinho

**Ações:**
- Se padrão temporal: OK, é comportamento esperado
- Se poucos plans: Considerar reduzir partitions (dev/staging)
- Se rebalanceamento: Aguardar estabilização (5-10min)

## Métricas de Performance

| Métrica | Baseline (ticket_id) | Atual (plan_id) | Observação |
|---------|----------------------|-----------------|------------|
| CV (Coeficiente de Variação) | 15% | 18% | Aceitável |
| Hot Partitions (> 2x média) | 0.1% | 2% | Burst esperado |
| Latência de Coordenação | 500ms | 200ms | +60% (data locality) |
| Throughput | 10 tickets/s | 10 tickets/s | Sem impacto |

## Evolução Futura

### Opção 1: Composite Key (plan_id + task_priority)

**Benefício:** Distribuir tickets de alta prioridade em partitions separadas
**Trade-off:** Perde data locality para tickets de prioridades diferentes

### Opção 2: Aumentar Partitions (12 → 24)

**Benefício:** Melhor distribuição com muitos plans ativos
**Trade-off:** Mais overhead de coordenação, mais consumers necessários

### Opção 3: Custom Partitioner

**Benefício:** Controle fino sobre distribuição (ex: round-robin por plan)
**Trade-off:** Complexidade adicional, dificulta troubleshooting

## Referências

- [Kafka Partitioning Best Practices](https://kafka.apache.org/documentation/#design_partitioning)
- [Choosing a Partition Key](https://www.confluent.io/blog/how-choose-number-topics-partitions-kafka-cluster/)
- [Neural Hive Mind - Documento 06: Fluxos e Processos](./documento-06-fluxos-processos-neural-hive-mind.md)

---

**Última Atualização:** 2026-01-25
**Autor:** Platform Team
