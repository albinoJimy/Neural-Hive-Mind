# Runbook: Erros de Inicialização de Componentes

## Alerta

- **Nomes**: KafkaProducerInitializationFailed, KafkaProducerConfigNone, TemporalActivityNotRegistered, MLModelNotTrained
- **Severidade**: Critical / Warning
- **Thresholds**:
  - Component initialization status = 3 (failed)
  - Config validation errors > 0
  - Activity registration errors > 0
  - ML model training status = 0 (untrained)

## Sintomas

- Erro `'NoneType' object has no attribute 'service_name'` nos logs do Kafka Producer
- Erro `Activity function 'check_workflow_sla_proactive' is not registered` nos logs do Temporal Worker
- Erro `'RandomForestRegressor' object has no attribute 'estimators_'` nos logs do ML Predictor
- Componentes em estado de falha (status=3) por mais de 2 minutos
- Health checks retornando status degraded ou unhealthy
- Tickets não sendo publicados no Kafka
- Workflows falhando ao executar activities
- Predições ML usando fallback heurístico com baixa confiança

## Diagnóstico

### 1. Verificar status geral de inicialização

```bash
# Verificar métricas de status de componentes
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_component_initialization_status" | jq '.data.result'

# Verificar componentes em falha (status=3)
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_component_initialization_status==3" | jq '.data.result'
```

### 2. Verificar logs do Orchestrator Dynamic

```bash
# Logs gerais
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=200

# Filtrar erros de inicialização
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=500 | grep -E "initialization|service_name|not registered|estimators_"

# Logs específicos do Kafka Producer
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=200 | grep kafka_producer

# Logs específicos do Temporal Worker
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=200 | grep temporal_worker

# Logs específicos de ML
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=200 | grep -E "ml_predictor|duration_predictor|estimators_"
```

### 3. Verificar health checks

```bash
# Health check geral
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health | jq '.'

# Health check do Kafka Producer
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health/kafka-producer | jq '.'

# Health check de Temporal Activities
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health/temporal-activities | jq '.'

# Health check de ML
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health/ml | jq '.'
```

### 4. Verificar configuração

```bash
# Verificar ConfigMap
kubectl get configmap orchestrator-config -n neural-hive-orchestration -o yaml

# Verificar variáveis de ambiente do pod
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- env | grep -E "SERVICE_NAME|KAFKA|TEMPORAL|ML"

# Verificar secrets
kubectl get secret orchestrator-secrets -n neural-hive-orchestration -o yaml
```

### 5. Verificar dependências externas

```bash
# Verificar Kafka
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "from kafka import KafkaProducer; print(KafkaProducer(bootstrap_servers='kafka.kafka:9092'))"

# Verificar MongoDB
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "from pymongo import MongoClient; print(MongoClient('mongodb://mongodb.neural-hive:27017').server_info())"

# Verificar MLflow
curl -s http://mlflow.mlflow:5000/health

# Verificar Temporal
kubectl get pods -n temporal
```

### 6. Verificar métricas Prometheus específicas

```bash
# Erros de validação de config
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_kafka_producer_config_validation_errors_total" | jq '.data.result'

# Erros de circuit breaker
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_circuit_breaker_initialization_errors_total" | jq '.data.result'

# Erros de activity não registrada
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_temporal_activity_registration_errors_total" | jq '.data.result'

# Status de treinamento de modelos ML
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_ml_model_training_status" | jq '.data.result'
```

## Resolução

### Erro 1: Kafka Producer - Config None ou service_name ausente

#### Opção 1 - Validar e corrigir configuração (Recomendado)

Execute quando: Config é None ou service_name ausente

```bash
# 1. Verificar se SERVICE_NAME está definido
kubectl get configmap orchestrator-config -n neural-hive-orchestration -o yaml | grep SERVICE_NAME

# 2. Se ausente, adicionar ao ConfigMap
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"SERVICE_NAME":"orchestrator-dynamic"}}'

# 3. Reiniciar deployment
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration

# 4. Aguardar rollout
kubectl rollout status deployment/orchestrator-dynamic -n neural-hive-orchestration
```

#### Opção 2 - Desabilitar circuit breaker temporariamente

Execute quando: Problema urgente e circuit breaker não é crítico

```bash
# Desabilitar circuit breaker do Kafka Producer
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"KAFKA_CIRCUIT_BREAKER_ENABLED":"false"}}'

# Reiniciar deployment
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

#### Opção 3 - Verificar credenciais dinâmicas do Vault

Execute quando: Usando Vault para credenciais dinâmicas

```bash
# Verificar logs do Vault
kubectl logs -n vault -l app=vault --tail=100

# Verificar se Vault está healthy
kubectl exec -n vault vault-0 -- vault status

# Verificar se credenciais Kafka estão sendo geradas
kubectl exec -n vault vault-0 -- vault read database/creds/kafka-producer

# Se Vault estiver com problema, considerar fail-open
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"VAULT_FAIL_OPEN":"true"}}'
```

### Erro 2: Temporal Activity não registrada

#### Opção 1 - Adicionar activity na lista de registro (Recomendado)

Execute quando: Activity existe mas não está registrada

**Editar arquivo** `services/orchestrator-dynamic/src/workers/temporal_worker.py`:

1. Verificar import da activity (linha ~328):
```python
from activities.sla_monitoring import check_workflow_sla_proactive
```

2. Adicionar na lista de activities (linha ~404-415):
```python
activities=[
    validate_cognitive_plan,
    audit_validation,
    optimize_dag,
    generate_execution_tickets,
    allocate_resources,
    publish_ticket_to_kafka,
    consolidate_results,
    trigger_self_healing,
    publish_telemetry,
    buffer_telemetry,
    check_workflow_sla_proactive  # ADICIONAR AQUI
],
```

3. Rebuild e redeploy:
```bash
# Rebuild imagem
cd services/orchestrator-dynamic
docker build -t orchestrator-dynamic:latest .

# Push para registry
docker tag orchestrator-dynamic:latest <registry>/orchestrator-dynamic:latest
docker push <registry>/orchestrator-dynamic:latest

# Restart deployment
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

#### Opção 2 - Verificar se activity está sendo importada corretamente

```bash
# Verificar se arquivo da activity existe
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  ls -la /app/src/activities/sla_monitoring.py

# Verificar se activity está definida
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "from activities.sla_monitoring import check_workflow_sla_proactive; print(check_workflow_sla_proactive)"
```

### Erro 3: Modelo ML não treinado

#### Opção 1 - Executar treinamento manual (Recomendado)

Execute quando: Modelo não está treinado mas dados históricos existem

```bash
# Trigger treinamento via API
curl -X POST http://orchestrator-dynamic.neural-hive-orchestration:8000/api/v1/ml/train \
  -H "Content-Type: application/json" \
  -d '{
    "model_types": ["duration", "scheduling", "anomaly"],
    "force": true
  }'

# Verificar status do treinamento
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=100 | grep training

# Aguardar conclusão (pode levar 5-10 minutos)
watch -n 10 'curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/api/v1/ml/models | jq ".models[] | select(.name | contains(\"duration\"))"'
```

#### Opção 2 - Verificar dados históricos suficientes

Execute quando: Treinamento falha por falta de dados

```bash
# Verificar volume de tickets completados no MongoDB
kubectl exec -n neural-hive-orchestration deployment/orchestrator-dynamic -- \
  python -c "
from pymongo import MongoClient
client = MongoClient('mongodb://mongodb.neural-hive:27017')
db = client['neural_hive']
count = db.tickets.count_documents({'status': 'completed'})
print(f'Tickets completados: {count}')
print(f'Mínimo necessário: 100')
"

# Se insuficiente, aguardar acúmulo de dados ou reduzir threshold
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"ML_MIN_TRAINING_SAMPLES":"50"}}'
```

#### Opção 3 - Desabilitar ML temporariamente

Execute quando: Problema urgente e ML não é crítico

```bash
# Desabilitar predições ML
kubectl patch configmap orchestrator-config -n neural-hive-orchestration \
  --type merge \
  -p '{"data":{"ML_PREDICTIONS_ENABLED":"false"}}'

# Reiniciar deployment
kubectl rollout restart deployment/orchestrator-dynamic -n neural-hive-orchestration
```

#### Opção 4 - Verificar conectividade com MLflow

Execute quando: Modelo existe mas não pode ser carregado

```bash
# Verificar se MLflow está acessível
curl -s http://mlflow.mlflow:5000/health

# Verificar se modelo existe no registry
curl -s "http://mlflow.mlflow:5000/api/2.0/mlflow/registered-models/get?name=ticket-duration-predictor" | jq '.'

# Verificar versões do modelo
curl -s "http://mlflow.mlflow:5000/api/2.0/mlflow/registered-models/get-latest-versions?name=ticket-duration-predictor&stages=Production" | jq '.'

# Se MLflow estiver down, reiniciar
kubectl rollout restart deployment/mlflow -n mlflow
```

## Verificação de Recuperação

### 1. Verificar que componentes estão em estado success

```bash
# Todos os componentes devem estar em status=2 (success)
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_component_initialization_status" | jq '.data.result[] | select(.value[1] != "2")'

# Não deve retornar nenhum resultado
```

### 2. Verificar health checks

```bash
# Todos devem retornar status: healthy
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health | jq '.status'
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health/kafka-producer | jq '.status'
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health/temporal-activities | jq '.status'
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health/ml | jq '.status'
```

### 3. Verificar que não há erros de inicialização

```bash
# Não deve haver erros nos últimos 10 minutos
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=increase(neural_hive_component_initialization_total{status=\"failed\"}[10m])" | jq '.data.result'
```

### 4. Verificar que modelos ML estão treinados

```bash
# Todos os modelos devem estar em status=1 (trained)
curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_ml_model_training_status" | jq '.data.result[] | select(.value[1] != "1")'

# Não deve retornar nenhum resultado
```

### 5. Verificar que activities estão registradas

```bash
# Não deve haver activities faltando
curl -s http://orchestrator-dynamic.neural-hive-orchestration:8000/health/temporal-activities | jq '.missing_activities'

# Deve retornar array vazio: []
```

### 6. Verificar alertas no Alertmanager

```bash
# Alertas de inicialização devem estar resolvidos
curl -s http://alertmanager.monitoring:9093/api/v2/alerts?filter=alertname=~".*Initialization.*|.*NotRegistered|.*NotTrained" | jq '.[] | select(.status.state == "active")'

# Não deve retornar nenhum resultado
```

### 7. Testar funcionalidade end-to-end

```bash
# Testar publicação de ticket no Kafka
curl -X POST http://orchestrator-dynamic.neural-hive-orchestration:8000/api/v1/workflows/start \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "test-plan-001",
    "tickets": [{"id": "test-ticket-001", "task_type": "test"}]
  }'

# Verificar logs para confirmar que ticket foi publicado
kubectl logs -n neural-hive-orchestration -l app=orchestrator-dynamic --tail=50 | grep "ticket_published"
```

### 8. Monitorar métricas por 15 minutos

```bash
# Watch das métricas de inicialização
watch -n 30 'curl -s "http://prometheus.monitoring:9090/api/v1/query?query=neural_hive_component_initialization_status" | jq ".data.result[] | {component: .metric.component_name, status: .value[1]}"'
```

## Prevenção

### 1. Adicionar validação de config no construtor

**Arquivo**: `services/orchestrator-dynamic/src/clients/kafka_producer.py`

Adicionar validação no `__init__`:
```python
def __init__(self, config, sasl_username_override=None, sasl_password_override=None):
    if config is None:
        raise ValueError("Config cannot be None")
    if not hasattr(config, 'service_name') or config.service_name is None:
        raise ValueError("Config must have service_name attribute")
    
    self.config = config
    # ... resto do código
```

### 2. Implementar health check no startup probe

**Arquivo**: Deployment Kubernetes

Adicionar startup probe para validar inicialização:
```yaml
startupProbe:
  httpGet:
    path: /health/kafka-producer
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 30
```

### 3. Adicionar testes de integração

Criar testes que validam:
- Config não pode ser None
- Activities críticas estão registradas
- Modelos ML são treinados antes de uso

### 4. Implementar alertas proativos

Os alertas criados neste runbook já implementam detecção proativa.

### 5. Documentar dependências de inicialização

Diagrama de dependências:
```
Vault → Config → Kafka Producer → Circuit Breaker
MongoDB → Historical Data → ML Training → ML Predictor
Temporal Server → Temporal Client → Temporal Worker → Activities
```

### 6. Implementar retry com backoff exponencial

Para componentes críticos, implementar retry automático na inicialização.

### 7. Adicionar métricas de duração de inicialização

Monitorar tempo de inicialização para detectar degradação:
```promql
histogram_quantile(0.95, 
  rate(neural_hive_component_initialization_duration_seconds_bucket[5m])
)
```

## Referências

- **Dashboard**: https://grafana.neural-hive.local/d/component-initialization
- **Código Kafka Producer**: `services/orchestrator-dynamic/src/clients/kafka_producer.py`
- **Código Temporal Worker**: `services/orchestrator-dynamic/src/workers/temporal_worker.py`
- **Código ML Predictor**: `services/orchestrator-dynamic/src/ml/duration_predictor.py`
- **Alertas Prometheus**: `monitoring/alerts/component-initialization-alerts.yaml`
- **Métricas**: `services/orchestrator-dynamic/src/observability/metrics.py`
- **Health Checks**: `services/orchestrator-dynamic/src/main.py`
