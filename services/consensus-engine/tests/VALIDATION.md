# Validação do Pipeline PlanConsumer

## Objetivo
Documentar a validação manual e automatizada do pipeline end-to-end do PlanConsumer.

## Correções Implementadas

### 1. Métodos do SpecialistsGrpcClient
- **Antes**: `request_opinions_parallel()` e `request_opinion()` (inexistentes)
- **Depois**: `evaluate_plan_parallel()` e `evaluate_plan()` (corretos)
- **Localização**: `services/consensus-engine/src/consumers/plan_consumer.py:134, 143`

### 2. Método de Persistência MongoDB
- **Antes**: `save_decision()` (inexistente)
- **Depois**: `save_consensus_decision()` (correto)
- **Localização**: `services/consensus-engine/src/consumers/plan_consumer.py:89`

### 3. Propagação de Trace Context
- **Adicionado**: Extração de trace_id e span_id das mensagens Kafka
- **Passado para**: Ambos `evaluate_plan_parallel()` e `evaluate_plan()`
- **Localização**: `services/consensus-engine/src/consumers/plan_consumer.py:126-130`

## Testes Automatizados

### Suíte de Testes
Arquivo: `tests/test_plan_consumer_integration.py`

#### Casos de Teste

1. **test_plan_consumer_parallel_invocation_happy_path**
   - Verifica o fluxo completo end-to-end com invocação paralela
   - Confirma que specialist client é chamado corretamente
   - Verifica propagação de trace context
   - Confirma persistência no MongoDB
   - Valida enfileiramento para o producer

2. **test_plan_consumer_sequential_fallback**
   - Testa fallback para invocação sequencial
   - Verifica que todos os 5 especialistas são chamados
   - Confirma ordem e parâmetros corretos

3. **test_plan_consumer_handles_specialist_errors_gracefully**
   - Valida handling de erros parciais dos especialistas
   - Confirma que processamento continua mesmo com falhas

4. **test_plan_consumer_propagates_trace_context**
   - Testa especificamente a propagação de trace context
   - Verifica que trace_id e span_id são extraídos e passados corretamente

### Executar Testes

```bash
# Instalar dependências de teste
pip install pytest pytest-asyncio pytest-mock

# Executar todos os testes
pytest services/consensus-engine/tests/test_plan_consumer_integration.py -v

# Executar teste específico
pytest services/consensus-engine/tests/test_plan_consumer_integration.py::test_plan_consumer_parallel_invocation_happy_path -v
```

## Validação Manual

### Pré-requisitos
1. Kafka rodando e acessível
2. MongoDB rodando e acessível
3. Especialistas gRPC disponíveis (ou mocks)
4. Redis disponível

### Passos de Validação

1. **Iniciar Consensus Engine**
   ```bash
   cd services/consensus-engine
   python -m src.main
   ```

2. **Verificar Health Check**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/ready
   ```

3. **Publicar Mensagem de Teste no Kafka**
   ```bash
   # Criar tópico se necessário
   kafka-topics --create --topic plans.ready --bootstrap-server localhost:9092

   # Publicar mensagem de teste
   echo '{
     "plan_id": "test-plan-001",
     "intent_id": "test-intent-001",
     "correlation_id": "test-corr-001",
     "trace_id": "test-trace-001",
     "span_id": "test-span-001",
     "version": "1.0.0",
     "content": "Test cognitive plan"
   }' | kafka-console-producer --topic plans.ready --bootstrap-server localhost:9092
   ```

4. **Verificar Logs**
   - Procurar por: "Mensagem recebida"
   - Verificar: "Invocando especialistas"
   - Confirmar: "Decisão consolidada salva"
   - Validar: "Mensagem processada com sucesso"

5. **Consultar Decisão no MongoDB**
   ```bash
   # Via API
   curl http://localhost:8000/api/v1/decisions/by-plan/test-plan-001

   # Via MongoDB CLI
   mongo
   use neural_hive
   db.consensus_decisions.find({plan_id: "test-plan-001"})
   ```

6. **Verificar Fila de Decisões**
   - Logs devem mostrar que decisão foi enfileirada
   - DecisionProducer deve processar e publicar no Kafka

## Integração com DecisionProducer

O pipeline agora está completo:

```
Kafka (plans.ready)
  ↓
PlanConsumer.consume()
  ↓
PlanConsumer._invoke_specialists()
  ↓ (usa evaluate_plan_parallel/evaluate_plan)
SpecialistsGrpcClient
  ↓ (retorna opinions)
ConsensusOrchestrator.process_consensus()
  ↓ (retorna ConsolidatedDecision)
MongoDBClient.save_consensus_decision()
  ↓
decision_queue.put(decision)
  ↓
DecisionProducer.produce()
  ↓
Kafka (decisions.consolidated)
```

## Critérios de Sucesso

✅ PlanConsumer chama métodos corretos do SpecialistsGrpcClient
✅ Trace context é propagado corretamente
✅ Persistência usa save_consensus_decision()
✅ Decisão é enfileirada para o producer
✅ Testes automatizados cobrem o happy path
✅ Testes cobrem fallback sequencial
✅ Error handling não quebra o pipeline

## Próximos Passos

1. Executar testes em ambiente de integração com serviços reais
2. Validar latência end-to-end
3. Testar cenários de falha e retry
4. Monitorar métricas de throughput
