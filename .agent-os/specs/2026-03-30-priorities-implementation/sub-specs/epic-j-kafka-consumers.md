# Sub-Spec: Epic J - Consumers para Tópicos Kafka Órfãos

## Objetivo

Criar 5 consumers para tópicos Kafka que têm producer mas não têm consumer, fechando gaps de integração.

## Tópicos e Consumers

### 1. insights.analyzed
**Consumer:** `services/orchestrator-dynamic/src/consumers/insights_consumer.py`
**Producer:** Analyst Agents (`insights_producer.py`)
**Tópico:** `insights.analyzed`
**Schema:** Avro

**Funcionalidades:**
- Consumir insights analisados
- Enriquecer cognitive plans com insights
- Armazenar no MongoDB para histórico

```python
class InsightsConsumer:
    async def consume_insights(self):
        """Consome insights do Analyst Agents."""
        consumer = AIOKafkaConsumer(
            "insights.analyzed",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="orchestrator-insights-group",
            value_deserializer=AvroDeserializer(schema_url)
        )

        async for msg in consumer:
            try:
                insight = self._parse_insight(msg.value)
                await self._enrich_plan(insight)
                await self._save_to_history(insight)
            except Exception as e:
                logger.error(f"Error processing insight: {e}")
                await self._send_to_dlq(msg)
```

### 2. exploration-signals
**Consumer:** `services/scout-agents/src/consumers/signal_consumer.py`
**Producer:** Scout Agents
**Tópico:** `exploration-signals`
**Schema:** Avro

**Funcionalidades:**
- Consumir sinais de exploração
- Feedback loop para Scout Agents
- Ajustar prioridade de exploração

```python
class SignalConsumer:
    async def consume_signals(self):
        """Consome sinais de exploração do Scout Agents."""
        consumer = AIOKafkaConsumer(
            "exploration-signals",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="scout-signals-group"
        )

        async for msg in consumer:
            signal = msg.value
            # Processar sinal e ajustar prioridade
            await self._adjust_exploration_priority(signal)
```

### 3. security-incidents
**Consumer:** `services/guard-agents/src/consumers/incident_feedback_consumer.py`
**Producer:** Guard Agents
**Tópico:** `security-incidents`
**Schema:** Avro

**Funcionalidades:**
- Consumir incidentes de segurança
- Feedback loop para Guard Agents
- Ajustar políticas de segurança

```python
class IncidentFeedbackConsumer:
    async def consume_incidents(self):
        """Consome incidentes de segurança para feedback loop."""
        consumer = AIOKafkaConsumer(
            "security-incidents",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="guard-incidents-group"
        )

        async for msg in consumer:
            incident = msg.value
            # Processar incident e ajustar políticas
            await self._adjust_security_policies(incident)
```

### 4. strategic.decisions
**Consumer:** `services/orchestrator-dynamic/src/consumers/strategic_decision_consumer.py`
**Producer:** Queen Agent (`strategic_decision_producer.py`)
**Tópico:** `strategic.decisions`
**Schema:** Avro

**Funcionalidades:**
- Consumir decisões estratégicas
- Atualizar orchestration workflow
- Persistir para histórico

```python
class StrategicDecisionConsumer:
    async def consume_decisions(self):
        """Consome decisões estratégicas do Queen Agent."""
        consumer = AIOKafkaConsumer(
            "strategic.decisions",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="orchestrator-strategic-group"
        )

        async for msg in consumer:
            decision = msg.value
            # Atualizar workflow
            await self._update_workflow(decision)
            # Persistir
            await self._save_decision(decision)
```

### 5. optimization.applied
**Consumer:** `services/optimizer-agents/src/consumers/optimization_feedback_consumer.py`
**Producer:** Optimizer Agents
**Tópico:** `optimization.applied`
**Schema:** Avro

**Funcionalidades:**
- Consumir otimizações aplicadas
- Feedback loop para Optimizer Agents
- Ajustar estratégias de otimização

```python
class OptimizationFeedbackConsumer:
    async def consume_optimizations(self):
        """Consome otimizações aplicadas para feedback loop."""
        consumer = AIOKafkaConsumer(
            "optimization.applied",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="optimizer-feedback-group"
        )

        async for msg in consumer:
            optimization = msg.value
            # Processar resultado
            await self._process_result(optimization)
            # Ajustar estratégias
            await self._adjust_strategies(optimization)
```

## Integração no main.py

Cada consumer deve ser iniciado no startup do serviço:

```python
@app.on_event("startup")
async def startup_event():
    ...
    # Iniciar consumers (se configurado)
    if settings.ENABLE_INSIGHTS_CONSUMER:
        app.state.insights_consumer = InsightsConsumer()
        asyncio.create_task(app.state.insights_consumer.consume_insights())
```

## Testes

```python
@pytest.mark.asyncio
@pytest.mark.kafka
async def test_insights_consumer(kafka_producer):
    """Testa consumo de insights."""
    # Given: insight no tópico
    insight = sample_insight()
    await kafka_producer.send("insights.analyzed", insight.to_avro())

    # When: consumer processa
    await insights_consumer._process_single_message()

    # Then: insight persistido
    saved = await mongodb.insights_history.find_one({"insight_id": insight.id})
    assert saved is not None
```

## Verificação

```bash
# Verificar consumers consumindo
kubectl logs -f orchestrator-dynamic | grep "InsightsConsumer"
kubectl logs -f scout-agents | grep "SignalConsumer"
kubectl logs -f guard-agents | grep "IncidentFeedbackConsumer"
kubectl logs -f orchestrator-dynamic | grep "StrategicDecisionConsumer"
kubectl logs -f optimizer-agents | grep "OptimizationFeedbackConsumer"

# Verificar tópicos com consumers
kafka-console-consumer --bootstrap-server localhost:9092 --topic insights.analyzed --from-beginning
```
