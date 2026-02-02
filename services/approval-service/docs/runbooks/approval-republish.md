# Runbook: Republicacao de Planos Aprovados

## Visao Geral

Este runbook documenta procedimentos para diagnosticar e resolver problemas relacionados a republicacao de planos aprovados no sistema Neural Hive.

## Alertas Relacionados

- `ApprovalRepublishHighFailureRate`
- `ApprovalRepublishKafkaErrors`
- `ApprovalRepublishHighLatency`
- `ApprovalRepublishForcedPending`
- `ApprovalRepublishMissingCognitivePlan`
- `ApprovalSagaHighCompensationRate`
- `ApprovalAutoRepublishFailures`

---

## ApprovalRepublishHighFailureRate

### Descricao
Taxa de falhas em republicacao esta acima do limite aceitavel (10%).

### Diagnostico

1. Verificar logs do approval-service:
   ```bash
   kubectl logs -l app=approval-service --tail=100 | grep -i republish
   ```

2. Verificar metricas de falha por motivo:
   ```promql
   sum by (failure_reason) (increase(approval_republish_failures_total[1h]))
   ```

3. Verificar estado do Kafka:
   ```bash
   kafka-consumer-groups.sh --bootstrap-server $KAFKA_BROKERS --describe --group approval-service
   ```

### Resolucao

- **Se `kafka_error`**: Ver secao ApprovalRepublishKafkaErrors
- **Se `not_found`**: Verificar se planos estao sendo deletados incorretamente
- **Se `not_approved`**: Verificar se usuarios estao tentando republicar planos pendentes
- **Se `no_cognitive_plan`**: Ver secao ApprovalRepublishMissingCognitivePlan

---

## ApprovalRepublishKafkaErrors

### Descricao
Erros de conexao ou publicacao no Kafka durante republicacao.

### Diagnostico

1. Verificar conectividade com Kafka:
   ```bash
   nc -zv $KAFKA_HOST $KAFKA_PORT
   ```

2. Verificar logs do producer:
   ```bash
   kubectl logs -l app=approval-service --tail=100 | grep -i kafka
   ```

3. Verificar status dos brokers:
   ```bash
   kafka-broker-api-versions.sh --bootstrap-server $KAFKA_BROKERS
   ```

4. Verificar topicos:
   ```bash
   kafka-topics.sh --bootstrap-server $KAFKA_BROKERS --describe --topic neural-hive.approval-response
   ```

### Resolucao

1. Se broker indisponivel:
   - Verificar status do cluster Kafka
   - Escalar brokers se necessario
   - Verificar recursos (CPU/memoria/disco)

2. Se problema de autenticacao:
   - Verificar credenciais no secret
   - Renovar certificados se necessario

3. Se topico nao existe:
   ```bash
   kafka-topics.sh --bootstrap-server $KAFKA_BROKERS --create --topic neural-hive.approval-response --partitions 6 --replication-factor 3
   ```

---

## ApprovalRepublishHighLatency

### Descricao
Operacoes de republicacao estao demorando mais que o esperado (>2s p95).

### Diagnostico

1. Verificar latencia por etapa:
   ```promql
   histogram_quantile(0.95, sum(rate(approval_republish_duration_seconds_bucket[5m])) by (le))
   ```

2. Verificar latencia do MongoDB:
   ```promql
   histogram_quantile(0.95, sum(rate(mongodb_operation_duration_seconds_bucket{operation="find"}[5m])) by (le))
   ```

3. Verificar latencia do Kafka:
   ```promql
   histogram_quantile(0.95, sum(rate(kafka_producer_request_latency_bucket[5m])) by (le))
   ```

### Resolucao

1. Se MongoDB lento:
   - Verificar indices na collection `approvals`
   - Verificar recursos do cluster MongoDB
   - Considerar read preference mais proximo

2. Se Kafka lento:
   - Verificar carga nos brokers
   - Ajustar `batch.size` e `linger.ms`
   - Verificar replicacao

3. Se ambos normais:
   - Verificar recursos do pod approval-service
   - Escalar horizontalmente se necessario

---

## ApprovalRepublishForcedPending

### Descricao
Usuarios estao republicando planos com `force=true` em alta frequencia.

### Diagnostico

1. Identificar usuarios fazendo republicacoes forcadas:
   ```bash
   kubectl logs -l app=approval-service | grep "Republicacao forcada"
   ```

2. Verificar estado dos planos sendo republicados:
   ```javascript
   db.approvals.find({status: {$ne: "approved"}}).count()
   ```

### Resolucao

1. Investigar por que planos nao estao com status aprovado
2. Verificar se ha falhas no fluxo de aprovacao
3. Se necessario, corrigir status inconsistentes:
   ```javascript
   db.approvals.updateMany(
     {status: "pending", approved_at: {$exists: true}},
     {$set: {status: "approved"}}
   )
   ```

---

## ApprovalRepublishMissingCognitivePlan

### Descricao
Planos marcados como aprovados mas sem cognitive_plan associado.

### Severidade
**CRITICA** - Indica corrupcao de dados.

### Diagnostico

1. Identificar planos afetados:
   ```javascript
   db.approvals.find({
     status: "approved",
     $or: [
       {cognitive_plan: null},
       {cognitive_plan: {$exists: false}}
     ]
   })
   ```

2. Verificar logs de quando os planos foram criados/aprovados

### Resolucao

1. **Imediato**: Desabilitar republicacao para planos sem cognitive_plan
2. **Investigacao**: Identificar causa raiz da corrupcao
3. **Recuperacao**: Se possivel, recuperar cognitive_plan do ledger cognitivo:
   ```javascript
   // Para cada plan_id afetado
   const ledgerEntry = await ledgerClient.getPlanById(planId);
   if (ledgerEntry && ledgerEntry.cognitive_plan) {
     await db.approvals.updateOne(
       {plan_id: planId},
       {$set: {cognitive_plan: ledgerEntry.cognitive_plan}}
     );
   }
   ```

---

## ApprovalSagaHighCompensationRate

### Descricao
Sagas de aprovacao estao falhando e executando compensacao com alta frequencia.

### Diagnostico

1. Verificar logs de compensacao:
   ```bash
   kubectl logs -l app=semantic-translation-engine | grep "compensacao"
   ```

2. Verificar metricas de saga:
   ```promql
   sum by (reason) (increase(neural_hive_approval_saga_compensations_total[1h]))
   ```

3. Verificar DLQ:
   ```bash
   kafka-console-consumer.sh --bootstrap-server $KAFKA_BROKERS --topic neural-hive.approval-dlq --from-beginning --max-messages 10
   ```

### Resolucao

1. Ver secao ApprovalRepublishKafkaErrors
2. Verificar se ha retries suficientes na saga
3. Processar mensagens da DLQ manualmente se necessario

---

## ApprovalAutoRepublishFailures

### Descricao
Falhas em republicacao automatica no Semantic Translation Engine.

### Diagnostico

1. Verificar logs do STE:
   ```bash
   kubectl logs -l app=semantic-translation-engine | grep -i "republish"
   ```

2. Verificar estado do consumer:
   ```bash
   kafka-consumer-groups.sh --bootstrap-server $KAFKA_BROKERS --describe --group ste-approval-processor
   ```

### Resolucao

1. Verificar conectividade entre STE e Kafka
2. Reiniciar consumer se necessario
3. Verificar se ha mensagens travadas no offset

---

## Procedimentos de Republicacao Manual

### Via API REST

```bash
# Republicacao simples
curl -X POST "https://api.neuralhive.io/api/v1/approvals/{plan_id}/republish" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"

# Republicacao forcada
curl -X POST "https://api.neuralhive.io/api/v1/approvals/{plan_id}/republish" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"force": true, "comments": "Reprocessando apos falha de Kafka"}'
```

### Via Script de Lote

```python
import asyncio
import aiohttp

async def republish_batch(plan_ids: list, token: str):
    async with aiohttp.ClientSession() as session:
        for plan_id in plan_ids:
            async with session.post(
                f"https://api.neuralhive.io/api/v1/approvals/{plan_id}/republish",
                headers={"Authorization": f"Bearer {token}"},
                json={"force": False, "comments": "Batch republish"}
            ) as resp:
                if resp.status == 200:
                    print(f"OK: {plan_id}")
                else:
                    print(f"FAIL: {plan_id} - {await resp.text()}")
```

---

## Contatos

- **On-call SRE**: Slack #sre-oncall
- **Team Approval**: Slack #team-approval
- **Kafka Team**: Slack #platform-kafka

---

## Historico de Revisoes

| Data | Autor | Descricao |
|------|-------|-----------|
| 2026-02-02 | Claude | Criacao inicial do runbook |
