# Testes E2E - Fluxo de Aprovação

Testes end-to-end para validação do fluxo de aprovação do Semantic Translation Engine.

## Cenários Cobertos

### 1. Fluxo Destrutivo Completo
- Intent com operação destrutiva (delete em produção)
- Detecção automática de operação destrutiva
- Bloqueio para aprovação humana
- Aprovação e publicação para execução

### 2. Fluxo de Rejeição
- Intent destrutivo detectado e bloqueado
- Rejeição com motivo documentado
- Plano **não** publicado para execução

### 3. Decomposição Avançada
- Pattern matching para intents complexos
- Task splitting com preservação de dependências
- Validação de dependências entre entidades

### 4. Validação de Métricas
- Métricas Prometheus registradas corretamente
- Contadores de detecção destrutiva
- Histogramas de processamento

### 5. Cenários de Falha
- MongoDB indisponível
- Dados de plano inválidos
- Plano não encontrado no ledger

## Pré-requisitos

### Ambiente Local (Mocks)
```bash
pip install pytest pytest-asyncio httpx
```

### Ambiente Completo (Infraestrutura Real)
- Kafka cluster acessível
- MongoDB cluster acessível
- Approval Service rodando
- Semantic Translation Engine rodando

## Execução

### Usando o Script
```bash
# Testes rápidos (sem infraestrutura)
./run_approval_flow_tests.sh --quick

# Todos os testes E2E
./run_approval_flow_tests.sh --all

# Apenas testes destrutivos
./run_approval_flow_tests.sh --destructive

# Apenas testes de métricas
./run_approval_flow_tests.sh --metrics

# Apenas cenários de falha
./run_approval_flow_tests.sh --failures

# Modo verbose
./run_approval_flow_tests.sh --quick --verbose
```

### Usando pytest Diretamente
```bash
cd services/semantic-translation-engine

# Todos os testes E2E
pytest tests/e2e/test_approval_flow.py -v

# Filtrar por marker
pytest tests/e2e/test_approval_flow.py -m "e2e and approval_flow" -v

# Excluir testes lentos
pytest tests/e2e/test_approval_flow.py -m "e2e and not slow" -v

# Teste específico
pytest tests/e2e/test_approval_flow.py::TestDestructiveIntentApprovalFlow -v
```

## Variáveis de Ambiente

| Variável | Descrição | Default |
|----------|-----------|---------|
| `KAFKA_BOOTSTRAP` | Endereço do Kafka | `neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092` |
| `MONGODB_URI` | URI do MongoDB | `mongodb://mongodb-cluster.mongodb-cluster.svc.cluster.local:27017` |
| `MONGODB_DATABASE` | Banco de dados | `neural_hive` |
| `APPROVAL_SERVICE_URL` | URL do Approval Service | `http://approval-service.neural-hive-orchestration.svc.cluster.local:8000` |
| `STE_METRICS_URL` | URL de métricas do STE | `http://semantic-translation-engine.neural-hive-orchestration.svc.cluster.local:8000` |

## Markers Disponíveis

| Marker | Descrição |
|--------|-----------|
| `e2e` | Testes end-to-end |
| `approval_flow` | Testes do fluxo de aprovação |
| `destructive` | Testes de operações destrutivas |
| `metrics` | Testes de métricas Prometheus |
| `failure_scenarios` | Testes de cenários de falha |
| `slow` | Testes que levam mais de 30s |

## Estrutura de Arquivos

```
tests/e2e/
├── __init__.py
├── README.md
├── run_approval_flow_tests.sh
└── test_approval_flow.py
```

## Troubleshooting

### Testes Pulados
Se testes são pulados com mensagem "helpers não disponíveis":
- Verifique se `tests/e2e/utils/kafka_helpers.py` existe
- Verifique se `tests/e2e/utils/database_helpers.py` existe

### Conexão Kafka Falha
- Verifique variável `KAFKA_BOOTSTRAP`
- Confirme que o cluster Kafka está rodando
- Use `kubectl get pods -n neural-hive-kafka`

### Conexão MongoDB Falha
- Verifique variável `MONGODB_URI`
- Confirme que o cluster MongoDB está rodando
- Use `kubectl get pods -n mongodb-cluster`

### Approval Service Indisponível
- Verifique variável `APPROVAL_SERVICE_URL`
- Confirme que o serviço está rodando
- Use `kubectl get pods -n neural-hive-orchestration`
