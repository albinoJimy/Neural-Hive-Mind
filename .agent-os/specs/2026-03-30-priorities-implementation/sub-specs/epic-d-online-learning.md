# Sub-Spec: Epic D - Integração Online Learning

## Objetivo

Integrar o código de Online Learning (isolado em ml_pipelines) ao approval-service para permitir aprendizado contínuo dos modelos ML com feedback em produção.

## Componentes

### 1. Consumer Kafka de Feedback (NOVO)
**Arquivo:** `services/approval-service/src/consumers/feedback_consumer.py`

**Funcionalidades:**
- Consumir tópico `specialist_feedback` (Kafka)
- Parsear mensagens Avro
- Enviar para `IncrementalLearner`

```python
class FeedbackConsumer:
    async def consume_feedback(self):
        """Consome feedback do Kafka e envia para Online Learning."""
        consumer = AIOKafkaConsumer(
            "specialist_feedback",
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="online-learning-group",
            auto_offset_reset="earliest"
        )

        async for msg in consumer:
            try:
                feedback = self._parse_avro(msg.value)
                await self.online_learning_service.process_feedback(feedback)
            except Exception as e:
                logger.error(f"Error processing feedback: {e}")
                await self._send_to_dlq(msg, e)
```

### 2. Online Learning Service (NOVO)
**Arquivo:** `services/approval-service/src/services/online_learning_service.py`

**Funcionalidades:**
- Wrapper para `IncrementalLearner` de ml_pipelines
- partial_fit periódico
- Model checkpoint
- Métricas Prometheus

```python
class OnlineLearningService:
    def __init__(self, incremental_learner: IncrementalLearner):
        self.learner = incremental_learner
        self.feedback_buffer = []
        self.buffer_size = 100  # partial_fit a cada 100 feedbacks

    async def process_feedback(self, feedback: SpecialistFeedback):
        """Processa feedback e acumula no buffer."""
        self.feedback_buffer.append(feedback)

        if len(self.feedback_buffer) >= self.buffer_size:
            await self._partial_fit()

    async def _partial_fit(self):
        """Executa partial_fit com feedback acumulado."""
        X, y = self._prepare_training_data(self.feedback_buffer)
        self.learner.partial_fit(X, y)
        self.feedback_buffer.clear()
        await self._save_checkpoint()

    async def _save_checkpoint(self):
        """Salva checkpoint do modelo."""
        model_path = f"/tmp/model_checkpoint_{int(time.time())}.pkl"
        joblib.dump(self.learner.model, model_path)

        # TODO: Upload para MLflow
```

### 3. Scheduler de Retreino (NOVO)
**Arquivo:** `services/approval-service/src/schedulers/retraining_scheduler.py`

**Funcionalidades:**
- Agendamento de retreino (diário/semanal)
- Trigger por drift detection
- Shadow validation antes de deploy
- Rollback automático se F1 cair

```python
class RetrainingScheduler:
    async def schedule_retraining(self):
        """Scheduler de retreino automático."""
        while True:
            try:
                # 1. Verificar se há drift
                drift_detected = await self._check_drift()

                if drift_detected:
                    # 2. Retreinar modelo
                    await self._retrain_model()

                    # 3. Shadow validation
                    shadow_score = await self._shadow_validate()

                    # 4. Deploy se score melhor
                    if shadow_score > self.current_score:
                        await self._deploy_model()
                    else:
                        logger.warning("New model worse, keeping current")

                # Agendar próximo ciclo (diário)
                await asyncio.sleep(24 * 60 * 60)

            except Exception as e:
                logger.error(f"Error in retraining: {e}")
                await asyncio.sleep(60 * 60)  # Retry em 1 hora
```

### 4. Integração no Approval Service
**Arquivo:** `services/approval-service/src/main.py`

**Modificação:** Adicionar startup do consumer e scheduler

```python
@app.on_event("startup")
async def startup_event():
    ...
    # Iniciar Online Learning
    if settings.ENABLE_ONLINE_LEARNING:
        app.state.feedback_consumer = FeedbackConsumer()
        app.state.retraining_scheduler = RetrainingScheduler()
        asyncio.create_task(app.state.feedback_consumer.consume_feedback())
        asyncio.create_task(app.state.retraining_scheduler.schedule_retraining())

@app.on_event("shutdown")
async def shutdown_event():
    ...
    # Parar Online Learning
    if hasattr(app.state, "feedback_consumer"):
        await app.state.feedback_consumer.stop()
```

## Tópico Kafka

**Tópico:** `specialist_feedback`
**Schema:** Avro (já definido em libraries/python/neural_hive_specialists/)
**Mensagens por dia:** Estimado 100-1000 (depende do volume)

## Testes

```python
@pytest.mark.asyncio
@pytest.mark.kafka
async def test_feedback_consumer_integration(kafka_producer):
    """Testa consumo de feedback do Kafka."""
    # Given: feedback no tópico
    feedback = sample_specialist_feedback()
    await kafka_producer.send("specialist_feedback", feedback.to_avro())

    # When: consumer processa
    await feedback_consumer._process_single_message()

    # Then: feedback enviado para learner
    assert len(online_learning_service.feedback_buffer) == 1

@pytest.mark.asyncio
async def test_partial_fit():
    """Testa partial_fit com feedback."""
    # Given: learner com 100 feedbacks
    learner = IncrementalLearner()
    service = OnlineLearningService(learner)

    for _ in range(100):
        await service.process_feedback(sample_feedback())

    # Then: partial_fit executado
    assert service.feedback_buffer == []  # Buffer limpo

@pytest.mark.asyncio
async def test_shadow_validation():
    """Testa shadow validation antes de deploy."""
    # Given: novo modelo treinado
    new_model = train_new_model()

    # When: shadow validation
    shadow_score = await retraining_scheduler._shadow_validate(new_model)

    # Then: score calculado
    assert 0 <= shadow_score <= 1
```

## Verificação

```bash
# Verificar consumer consumindo
kubectl logs -f approval-service | grep "FeedbackConsumer"

# Verificar buffer de feedback
# (logs devem mostrar tamanho do buffer)

# Verificar partial_fit
# (logs devem mostrar "Executing partial_fit")

# Verificar checkpoint
ls -lh /tmp/model_checkpoint_*.pkl

# Testar modelo atualizado
curl -X POST http://approval-service/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "test"}'
```

## Configuração

```python
# services/approval-service/src/config/settings.py
ENABLE_ONLINE_LEARNING: bool = Field(default=False)
ONLINE_LEARNING_BUFFER_SIZE: int = Field(default=100)
ONLINE_LEARNING_RETRAINING_INTERVAL_HOURS: int = Field(default=24)
```
