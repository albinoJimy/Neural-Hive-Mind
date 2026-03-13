# Testes E2E - Neural Hive-Mind

Suite completa de testes end-to-end para validar o pipeline cognitivo.

## Pré-requisitos

### 1. Serviços Rodando

Todos os serviços devem estar rodando e acessíveis:

```bash
# Verificar pods (Kubernetes)
kubectl get pods -n neural-hive-mind

# Port forwards (desenvolvimento)
kubectl port-forward -n neural-hive-mend svc/gateway-intencoes 8000:8000 &
kubectl port-forward -n neural-hive-mend svc/semantic-translation-engine 8001:8001 &
kubectl port-forward -n neural-hive-mend svc/consensus-engine 8002:8002 &
kubectl port-forward -n neural-hive-mend svc/approval-service 8003:8003 &
kubectl port-forward -n neural-hive-mend svc/kafka-0 9092:9092 &
```

### 2. Dependências Python

```bash
pip install pytest pytest-asyncio httpx confluent-kafka kubernetes
```

### 3. Variáveis de Ambiente

```bash
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export GATEWAY_URL=http://localhost:8000
export APPROVAL_SERVICE_URL=http://localhost:8003
export CODE_FORGE_URL=http://localhost:8004
export E2E_TIMEOUT_SECONDS=300
```

## Execução dos Testes

### Todos os Testes

```bash
pytest tests/e2e/ -v --asyncio-mode=auto
```

### Teste Específico

```bash
# Fluxo completo
pytest tests/e2e/test_full_intent_to_code.py::test_intent_to_code_full_flow -v

# Stress test
pytest tests/e2e/test_load_correlation_id.py::test_correlation_id_under_load -v

# Saga compensation
pytest tests/e2e/test_workflow_compensation.py::test_build_deploy_failure_rollback -v
```

### Por Categoria (Marker)

```bash
# Apenas E2E básico
pytest tests/e2e/ -v -m e2e

# Apenas stress tests
pytest tests/e2e/ -v -m stress

# Apenas Saga
pytest tests/e2e/ -v -m saga
```

### Paralelo (requer pytest-xdist)

```bash
pip install pytest-xdist
pytest tests/e2e/ -v -n auto
```

## Suites de Teste

### 1. test_full_intent_to_code.py

Valida o pipeline cognitivo completo:

- `test_intent_to_code_full_flow` - Fluxo completo com validações
- `test_correlation_id_propagation` - FASE 1: propagação de correlation_id
- `test_w3c_traceparent_format` - FASE 5: formato W3C traceparent
- `test_concurrent_intentions` - 50 intenções concorrentes

### 2. test_load_correlation_id.py

Valida propagação sob carga:

- `test_correlation_id_under_load` - 100 requisições concorrentes
- `test_sustained_load_correlation_id` - Carga por 1-5 minutos
- `test_correlation_id_not_swapped` - Detecta swap de IDs entre requisições

### 3. test_workflow_compensation.py

Valida compensação Saga (FASE 4):

- `test_build_deploy_failure_rollback` - Deploy falha → rollback build
- `test_approval_revert_on_failure` - Execução falha → revert approval
- `test_cascading_compensation` - Multi-falha → compensação em cascata

## Resultados Esperados

| Teste | Sucesso Indica |
|-------|----------------|
| `test_intent_to_code_full_flow` | Pipeline cognitivo funcional |
| `test_correlation_id_under_load` | FASE 1: correlation_id consistente |
| `test_w3c_traceparent_format` | FASE 5: tracing propagado |
| `test_build_deploy_failure_rollback` | FASE 4: compensação Saga funciona |

## Troubleshooting

### "No services running"

Verificar se os pods estão rodando:

```bash
kubectl get pods -n neural-hive-mind
```

### "Kafka connection refused"

Verificar port forward do Kafka:

```bash
kubectl port-forward -n neural-hive-mend svc/kafka-0 9092:9092
```

### "Timeout waiting for Cognitive Plan"

Pode indicar problema no STE ou Consensus Engine:

```bash
kubectl logs -n neural-hive-mend -l app=semantic-translation-engine
kubectl logs -n neural-hive-mend -l app=consensus-engine
```

### "correlation_id mismatch"

Indica bug na propagação (FASE 1). Verificar logs do serviço específico.

## Relatórios

Gerar relatório HTML:

```bash
pytest tests/e2e/ --html=e2e-report.html --self-contained-html
```

Gerar relatório JUnit (para CI/CD):

```bash
pytest tests/e2e/ --junitxml=e2e-results.xml
```
