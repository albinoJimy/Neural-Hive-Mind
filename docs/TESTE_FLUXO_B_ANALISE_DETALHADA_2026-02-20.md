# Análise Profunda - Problema de Consumo Kafka pelo STE

**Data:** 2026-02-20
**INTENT_ID:** `efb4b6d9-1e12-467c-8cc3-4343d6514a9c`
**Status:** 🔴 PROBLEMA IDENTIFICADO

## Resumo Executivo

O Gateway de Intenções envia mensagens com sucesso para o Kafka, mas o Semantic Translation Engine (STE) não as está consumindo. Há **1 mensagem em LAG** na partição 1 do tópico `intentions.security`.

---

## Fluxo da Mensagem

### 1. Gateway de Intenções → Kafka ✅

```
2026-02-20T19:53:31.115303 - send_intent CHAMADO
2026-02-20T19:53:31.115588 - Preparando publicação (topic=intentions.security)
2026-02-20T19:53:31.179492 - Intenção enviada para Kafka
```

**Status:** ✅ Mensagem publicada com sucesso

### 2. Kafka - Armazenamento ✅

```
Topic: intentions.security (4 partições)
Partition: 1
Offset: 25 (LOG-END-OFFSET)
```

**Status:** ✅ Mensagem armazenada

### 3. STE - Consumo ❌

```
GROUP: semantic-translation-engine
TOPIC: intentions.security
PARTITION: 1
CURRENT-OFFSET: 24
LOG-END-OFFSET: 25
LAG: 1 ❌
```

**Status:** ❌ Mensagem NÃO consumida

---

## Arquitetura de Tópicos

### Descoberta Crítica: DOIS tópicos similares!

| Com HÍFEN | Com PONTO |
|-----------|-----------|
| `intentions-security` (3 partições) | `intentions.security` (4 partições) |

**Gateway e STE usam:** `intentions.security` (com ponto)

---

## Status do Consumer Group

```
semantic-translation-engine intentions.security       1    24    25    1    rdkafka-3e61447a... /10.244.2.131
```

- **Consumer-ID:** `rdkafka-3e61447a-fdb2-4020-a9fb-eb52f8ba78b8`
- **Host:** `10.244.2.131` → Pod `semantic-translation-engine-697685645f-s8ccc`
- **LAG:** 1 mensagem pendente

### Assignments do Pod s8ccc (startup):

```
assignments=['intentions.business:2', 'intentions.business:3',
             'intentions.infrastructure:2', 'intentions.infrastructure:3',
             'intentions.security:2',  ← Apenas partição 2
             'intentions.technical:3', 'intentions.technical:4',
             'intentions.technical:5']
```

**PROBLEMA:** O pod s8ccc tem a partição 1 atribuída no consumer group, mas só recebeu a partição 2 nos assignments!

---

## Health Check dos Pods STE

### Pod npxjd (18h running)
```
Kafka consumer saudável: 'Consumer ativo (último poll há 0.3s, 0 msgs processadas)'
```

### Pod s8ccc (16m running)
```
Kafka consumer saudável: 'Consumer ativo (último poll há 0.7s, 0 msgs processadas)'
```

**Ambos os pods estão polling mas não processam mensagens!**

---

## Diagnóstico

### Causa Provável: **Rebalanceamento Incompleto**

Quando o pod `s8ccc` foi adicionado ao consumer group (16 minutos atrás), ocorreu um rebalanceamento. No entanto:

1. A partição 1 ficou atribuída ao consumer `rdkafka-3e61447a...` (pod s8ccc)
2. Mas o consumer só recebeu assignments para outras partições (security:2, não security:1)
3. Resultado: Partição 1 está "órfã" - atribuída mas sem consumidor ativo

### Possíveis Causas Secundárias:

1. **Race condition no rebalanceamento:** O pod pode ter perdido a partição durante o rebalance
2. **Configuração de assignment:** `assignment` strategy pode estar incorreta
3. **Bug no confluent-kafka:** Problema conhecido com assignments em múltiplos consumers

---

## Resolução

### Opção 1: Reiniciar o pod (Recomendado)

```bash
kubectl delete pod -n neural-hive semantic-translation-engine-697685645f-s8ccc
```

Isso forçará um novo rebalanceamento e o consumidor poderá receber a partição 1 corretamente.

### Opção 2: Resetar offset

```bash
kubectl exec -n kafka neural-hive-kafka-broker-0 -- bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group semantic-translation-engine \
  --reset-offset \
  --to-earliest \
  --topic intentions.security:1 \
  --execute
```

### Opção 3: Aumentar replicas e reduzir (forçar rebalance)

```bash
kubectl scale deployment -n neural-hive semantic-translation-engine --replicas=3
# Aguardar estabilização
kubectl scale deployment -n neural-hive semantic-translation-engine --replicas=2
```

---

## Verificação

Após a resolução, verificar:

```bash
# 1. Verificar LAG
kubectl exec -n kafka neural-hive-kafka-broker-0 -- bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group semantic-translation-engine | grep intentions.security

# 2. Enviar nova mensagem de teste
curl -X POST http://gateway-intencoes.neural-hive.svc.cluster.local:8080/intentions \
  -H "Content-Type: application/json" \
  -d '{"text": "teste de consumo", "language": "pt-BR"}'

# 3. Verificar logs do STE
kubectl logs -n neural-hive semantic-translation-engine-xxx | grep "Message received"
```

---

## Conclusão

O problema **NÃO** é de:
- ❌ Configuração de tópicos (tópicos existem)
- ❌ Gateway não enviando (enviou com sucesso)
- ❌ STE não inicializado (consumer está ativo)

O problema **É** de:
- ✅ Rebalanceamento de consumer group deixando partição "órfã"
- ✅ Consumer assigned mas sem mensagens sendo entregues

---

## Anexos

### Configuração STE:

```python
KAFKA_TOPICS=["intentions.business","intentions.technical",
              "intentions.infrastructure","intentions.security"]
KAFKA_CONSUMER_GROUP_ID=semantic-translation-engine
KAFKA_AUTO_OFFSET_RESET=earliest
```

### Trace ID da mensagem:
```
trace_id=ccfe08a89c21bcd199fb4559e616293c
intent_id=efb4b6d9-1e12-467c-8cc3-4343d6514a9c
```
