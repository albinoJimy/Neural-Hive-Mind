# Testes E2E - Neural Hive-Mind Fluxo C

## Visão Geral
Suite de testes end-to-end para validar o Fluxo C completo (Intent → Deploy).

## Pré-requisitos
- Cluster Kubernetes local (Kind/Minikube/Docker Desktop)
- Python 3.11+
- kubectl configurado

## Instalação
```bash
pip install -r tests/requirements-test.txt
```

## Executar Testes

### Todos os testes
```bash
pytest tests/e2e/
```

### Teste específico
```bash
pytest tests/e2e/test_02_happy_path.py::test_complete_flow_c_happy_path
```

### Apenas testes rápidos (excluir slow)
```bash
pytest tests/e2e/ -m "not slow"
```

### Com paralelização
```bash
pytest tests/e2e/ -n 4
```

## Estrutura
- `test_01_setup_validation.py`: Validação de infraestrutura
- `test_02_happy_path.py`: Fluxo completo Intent→Deploy
- `test_03_avro_serialization.py`: Validação Avro
- `test_04_opa_policies.py`: Enforcement OPA
- `test_05_ml_predictions.py`: Predições ML
- `test_06_failure_scenarios.py`: Retry, compensação, autocura
- `test_07_performance.py`: Latência e throughput

## Fixtures
Fixtures compartilhadas em `fixtures/`:
- `kubernetes.py`: Interação com K8s
- `kafka.py`: Producers/consumers Avro
- `databases.py`: MongoDB, PostgreSQL, Redis
- `services.py`: Clientes HTTP/gRPC

## Troubleshooting

### Testes falhando com timeout
- Aumentar timeout em `pytest.ini`: `timeout = 1200`
- Verificar que cluster K8s está saudável: `kubectl get pods --all-namespaces`

### Kafka não acessível
- Verificar port-forward: `kubectl port-forward -n neural-hive-kafka svc/kafka 9092:9092`

### MongoDB não acessível
- Verificar pods: `kubectl get pods -n mongodb-cluster`

## Diagrama de Arquitetura dos Testes
```mermaid
graph TD
    A[pytest] --> B[conftest.py]
    B --> C[Fixtures K8s]
    B --> D[Fixtures Kafka]
    B --> E[Fixtures Databases]
    B --> F[Fixtures Services]

    C --> G[test_namespace]
    C --> H[port_forward_manager]
    C --> I[k8s_client]

    D --> J[avro_producer]
    D --> K[avro_consumer]
    D --> L[test_kafka_topics]

    E --> M[mongodb_client]
    E --> N[redis_client]
    E --> O[postgres_connection]

    F --> P[gateway_client]
    F --> Q[orchestrator_client]
    F --> R[temporal_client]

    S[test_02_happy_path.py] --> P
    S --> J
    S --> M
    S --> Q

    T[test_04_opa_policies.py] --> Q
    T --> I

    U[test_06_failure_scenarios.py] --> I
    U --> M
    U --> R
```

## Tabela de Cobertura de Testes

| Cenário | Arquivo | Testes | Duração Estimada | Prioridade |
|---------|---------|--------|------------------|------------|
| **Setup** | test_01_setup_validation.py | 8 | 2-3 min | 🔴 Crítica |
| **Happy Path** | test_02_happy_path.py | 1 (10 etapas) | 5-10 min | 🔴 Crítica |
| **Avro** | test_03_avro_serialization.py | 5 | 3-5 min | 🔴 Crítica |
| **OPA** | test_04_opa_policies.py | 5 | 5-8 min | 🟡 Alta |
| **ML** | test_05_ml_predictions.py | 6 | 10-15 min | 🟡 Alta |
| **Falhas** | test_06_failure_scenarios.py | 6 | 15-20 min | 🟡 Alta |
| **Performance** | test_07_performance.py | 6 | 20-30 min | 🟢 Média |
| **Total** | - | **37 testes** | **60-90 min** | - |

## Critérios de Sucesso
- Cobertura >80% nos serviços críticos (Orchestrator, Service Registry, Execution Ticket Service, Worker Agents)
- Taxa de sucesso >95% no CI/CD
- Suite completa executa em <90 minutos
- SLOs validados: Intent→Deploy p95 < 4h; Enforcement OPA; Predições ML; Autocura <90s
