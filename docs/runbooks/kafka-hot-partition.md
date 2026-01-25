# Runbook: Kafka Hot Partition

## Alerta

**Nome:** `KafkaHotPartitionDetected`
**Severidade:** Warning
**Componente:** Kafka
**Tópico:** `execution.tickets`

## Descrição

Uma partition do tópico `execution.tickets` está recebendo mais de 2x a média de mensagens, indicando possível hot partition.

## Diagnóstico

### 1. Verificar Distribuição Atual

```bash
python scripts/kafka/analyze_partition_distribution.py \
  --topic execution.tickets \
  --bootstrap-servers kafka.neural-hive.svc.cluster.local:9092 \
  --time-window 3600
```

**Saída Esperada:**
```
📊 Analisando tópico: execution.tickets
   Partitions: 12
   Janela de tempo: 3600s

📈 Distribuição por Partition:
Partition  Mensagens    %        Bytes        Keys Únicas     Status
--------------------------------------------------------------------------------
0          850          8.50%    425000       45              ✅ OK
1          920          9.20%    460000       48              ✅ OK
2          2100         21.00%   1050000      12              🔥 HOT
...
```

### 2. Identificar Causa da Hot Partition

```bash
kubectl exec -n kafka kafka-0 -- \
  kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets \
  --partition 2 \
  --from-beginning \
  --max-messages 100 \
  --property print.key=true \
  --property key.separator="|" \
  | cut -d'|' -f1 \
  | sort | uniq -c | sort -rn | head -20
```

## Causas Comuns

### Causa 1: Burst de Tickets de um Único Plan (ESPERADO)

**Sintoma:** Hot partition com muitas mensagens do mesmo `plan_id`

**Rationale:** Comportamento esperado! Tickets do mesmo plan devem ir para a mesma partition (data locality).

**Ação:** Nenhuma ação necessária

**Validação:**
- Verificar que hot partition tem apenas 1-2 plan_ids dominantes
- Verificar que outras partitions estão balanceadas
- Verificar que CV geral < 50%

### Causa 2: Hash Collision (RARO)

**Sintoma:** Múltiplos plans diferentes indo para a mesma partition

**Ação:**
1. Aumentar número de partitions (12 → 24)
2. Rebalancear consumer groups

```bash
kubectl patch kafkatopic execution-tickets -n kafka --type merge -p '{"spec":{"partitions":24}}'
kubectl rollout restart deployment/worker-agents -n orchestration
```

### Causa 3: Plan ID Não Distribuído (BUG)

**Sintoma:** Todos os plans têm plan_id com mesmo prefixo ou padrão

**Ação:**
1. Verificar código de geração de plan_id
2. Corrigir para usar UUID v4
3. Deploy da correção

## Ações Corretivas

### Ação 1: Monitorar e Aguardar (Burst Esperado)

Se hot partition é causada por burst de um único plan:

```bash
watch -n 30 'python scripts/kafka/analyze_partition_distribution.py \
  --topic execution.tickets \
  --bootstrap-servers kafka.neural-hive.svc.cluster.local:9092 \
  --time-window 300'
```

**Expectativa:** Hot partition deve resolver em 10-30min após burst terminar.

### Ação 2: Aumentar Partitions (Hash Collision)

```bash
# 1. Aumentar partitions
kubectl patch kafkatopic execution-tickets -n kafka --type merge -p '{"spec":{"partitions":24}}'

# 2. Verificar rebalanceamento
kubectl get kafkatopic -n kafka execution-tickets -o yaml

# 3. Reiniciar consumers para rebalancear
kubectl rollout restart deployment/worker-agents -n orchestration

# 4. Validar distribuição após 10min
python scripts/kafka/analyze_partition_distribution.py \
  --topic execution.tickets \
  --bootstrap-servers kafka.neural-hive.svc.cluster.local:9092 \
  --time-window 600
```

## Validação

### Critérios de Sucesso

- Nenhuma partition > 2x média
- Coeficiente de variação < 50%
- Hot partitions < 5% do total
- Alerta `KafkaHotPartitionDetected` não dispara por 1h

### Queries de Validação

```promql
# Verificar que hot partition foi resolvida
(
  rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m])
  /
  avg(rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m]))
) < 2

# Verificar CV
(
  stddev(rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m]))
  /
  avg(rate(neural_hive_kafka_partition_messages_total{topic="execution.tickets"}[5m]))
) < 0.5
```

## Prevenção

### Monitoramento Proativo

1. **Dashboard:** Monitorar dashboard Kafka Partitions diariamente
2. **Alertas:** Configurar alertas para CV > 40% (antes de 50%)
3. **Análise Semanal:** Executar script de análise semanalmente

### Testes de Carga

```bash
pytest tests/performance/test_kafka_partitioning.py -v
```

## Referências

- [Estratégia de Particionamento](../KAFKA_PARTITIONING_STRATEGY.md)
- [Dashboard Kafka Partitions](https://grafana.neural-hive.io/d/kafka-partitions)
- [Alertas Kafka](../../monitoring/alerts/kafka-partitioning-alerts.yaml)

## Escalação

- **L1:** Platform Team (monitorar e diagnosticar)
- **L2:** SRE Team (ações corretivas)
- **L3:** Data Engineering Team (mudanças arquiteturais)

---

**Última Atualização:** 2026-01-25
**Autor:** Platform Team
