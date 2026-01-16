# Correção do Consumer Kafka do STE

> **Data:** 2026-01-16
> **Componente:** Semantic Translation Engine (STE)
> **Issue:** Consumer Kafka não processa mensagens apesar de reportar healthy

---

## Diagnóstico

### Sintoma
- Consumer group `semantic-translation-engine` mostra "no active members"
- Mensagens acumulando em tópicos `intentions.*` (LAG > 0)
- Health check reporta `kafka_consumer: true` (falso positivo)

### Evidência
```
GROUP                       TOPIC                     PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG  CONSUMER-ID
semantic-translation-engine intentions.security       1          5               6               1    -
```

### Causa Raiz

O STE usa `assign()` em vez de `subscribe()` para atribuição manual de partições (workaround para erro UNKNOWN_TOPIC_OR_PART).

**Problema:** Quando se usa `assign()`:
1. O consumer não participa do protocolo de grupo do Kafka
2. O consumer NÃO busca automaticamente os offsets commitados
3. O consumer pode iniciar em posição indefinida

O código atual faz a atribuição mas não posiciona o consumer nos offsets corretos.

---

## Solução Implementada

### Arquivo: `services/semantic-translation-engine/src/consumers/intent_consumer.py`

A correção adiciona busca explícita de offsets commitados após `assign()`:

```python
if topic_partitions:
    self.consumer.assign(topic_partitions)
    logger.info(f'Manual assignment completed: {len(topic_partitions)} partitions total')

    # CRITICAL: When using assign(), we must explicitly seek to committed offsets
    # Otherwise the consumer starts from an undefined position
    committed_offsets = self.consumer.committed(topic_partitions, timeout=10)
    for tp in committed_offsets:
        if tp.offset >= 0:
            # Seek to committed offset
            self.consumer.seek(tp)
            logger.debug(f'Seeked to committed offset {tp.offset} for {tp.topic}:{tp.partition}')
        else:
            # No committed offset, seek based on auto.offset.reset (earliest)
            tp.offset = OFFSET_STORED  # Will use auto.offset.reset policy
            logger.debug(f'No committed offset for {tp.topic}:{tp.partition}, using auto.offset.reset')

    logger.info('Consumer offsets initialized from committed positions')
```

### Melhorias Adicionais

1. **Logging de heartbeat do consumer loop** - Log a cada 60 polls para confirmar que o loop está ativo
2. **Log de recebimento de mensagem** - Log explícito quando uma mensagem é recebida
3. **Exception handling no task** - Wrapper para capturar exceções silenciosas do asyncio.create_task()

---

## Arquivos Modificados

1. `services/semantic-translation-engine/src/consumers/intent_consumer.py`
   - Adicionado seek para offsets commitados após assign()
   - Adicionado logging de heartbeat no consumer loop
   - Adicionado log de recebimento de mensagem

2. `services/semantic-translation-engine/src/main.py`
   - Adicionado wrapper de exception handling para o consumer task

---

## Deploy

### Pré-requisitos
- Docker disponível
- Acesso ao registry (37.60.241.150:30500)

### Comandos

```bash
# 1. Build da nova imagem
cd /home/jimy/NHM/Neural-Hive-Mind
docker build -t 37.60.241.150:30500/semantic-translation-engine:1.2.5-fix-consumer \
  -f services/semantic-translation-engine/Dockerfile .

# 2. Push para registry
docker push 37.60.241.150:30500/semantic-translation-engine:1.2.5-fix-consumer

# 3. Update do deployment
kubectl set image deployment/semantic-translation-engine \
  semantic-translation-engine=37.60.241.150:30500/semantic-translation-engine:1.2.5-fix-consumer \
  -n neural-hive

# 4. Aguardar rollout
kubectl rollout status deployment/semantic-translation-engine -n neural-hive

# 5. Verificar logs de inicialização
kubectl logs -n neural-hive deployment/semantic-translation-engine --tail=50 | grep -i consumer
```

### Validação

```bash
# Verificar consumer group
kubectl exec -n kafka neural-hive-kafka-broker-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group semantic-translation-engine

# Verificar processamento de mensagem
kubectl logs -n neural-hive deployment/semantic-translation-engine | \
  grep -i "Message received"
```

---

## Validação Completa

Após o deploy, re-executar o plano de teste:
- `docs/PLANO_TESTE_MANUAL_FLUXOS_A_C.md`

Resultado esperado:
- FLUXO B (STE): PASSOU - mensagens processadas, planos gerados
- FLUXO C: Executável após FLUXO B funcionar

---

## Limpeza

Após validação bem-sucedida:

```bash
# Remover ConfigMap de debug (se existir)
kubectl delete configmap ste-fix-consumer -n neural-hive --ignore-not-found
```

---

*Documento gerado durante investigação do issue crítico do pipeline E2E.*
