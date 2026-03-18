# Self-Healing Engine

Serviço de autorecuperação para Neural Hive Mind. Detecta incidentes automaticamente e executa playbooks de remediação.

## Funcionalidades

- **Detecção de Incidentes**
  - Deadlocks em workflows (sem progresso por 30+ min)
  - Memory leaks em pods (>90% por 5+ min)
  - Health checks de serviços
  - Kafka consumer lag

- **Remediação Automática**
  - 5 playbooks pré-configurados
  - Validação OPA antes de executar ações
  - Circuit Breaker para serviços externos
  - Rastreamento de MTTR

- **Observabilidade**
  - Métricas Prometheus (`/metrics`)
  - 11 painéis Grafana
  - Health endpoints: `/health/live`, `/health/ready`

## Arquitetura

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Kafka Events   │────▶│ RemediationConsumer│────▶│ PlaybookExecutor│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │                         │
                                ▼                         ▼
                        ┌──────────────┐          ┌──────────────┐
                        │ DetectionSvc │          │ HealthMonitor │
                        └──────────────┘          └──────────────┘
                                │                         │
                                ▼                         ▼
                        ┌──────────────────────────────────────┐
                        │        Circuit Breaker              │
                        │   (ETS, Orchestrator, OPA)         │
                        └──────────────────────────────────────┘
```

## Deploy Kubernetes

```bash
# Aplicar manifests
kubectl apply -f kubernetes/

# Verificar deploy
kubectl rollout status deployment/self-healing-engine -n neural-hive-orchestration

# Verificar logs
kubectl logs -f deployment/self-healing-engine -n neural-hive-orchestration
```

## Deploy via Helm

```bash
# Instalar
helm install self-healing-engine ./helm/self-healing-engine \
  --namespace neural-hive-orchestration \
  --create-namespace

# Upgrade
helm upgrade self-healing-engine ./helm/self-healing-engine \
  --namespace neural-hive-orchestration \
  --set image.tag=v1.0.0

# Uninstall
helm uninstall self-healing-engine -n neural-hive-orchestration
```

## Configuração

### Variáveis de Ambiente

```bash
# Serviços Externos
KAFKA_BOOTSTRAP_SERVERS=kafka.kafka.svc.cluster.local:9092
MONGODB_URL=mongodb://mongodb:27017/neural_hive
OPA_HOST=opa.neural-hive-governance.svc.cluster.local

# Circuit Breaker
EXECUTION_TICKET_CIRCUIT_BREAKER_THRESHOLD=5
EXECUTION_TICKET_CIRCUIT_BREAKER_RESET_SECONDS=60

# Chaos Engineering
CHAOS_ENABLED=false
CHAOS_MAX_CONCURRENT_EXPERIMENTS=2
```

### Playbooks

Playbooks são armazenados no ConfigMap `self-healing-engine-playbooks`:

- `ticket_timeout_recovery.yaml` - Realloca tickets com timeout
- `deadlock_recovery.yaml` - Detecta e resolve deadlocks
- `database_connection_recovery.yaml` - Recupera conexões MongoDB
- `memory_leak_detection.yaml` - Detecta pods com memory leak
- `kafka_lag_recovery.yaml` - Recupera lag excessivo

## Métricas

### Principais Métricas

```
self_healing_detection_events_total{incident_type, severity, detected_by}
self_healing_remediation_events_total{incident_type, playbook_id, outcome}
self_healing_mttr_seconds_current{incident_type, severity}
self_healing_circuit_breaker_state{service_name}
self_healing_kafka_consumer_lag_total{consumer_group, topic}
self_healing_service_health_status{service_name}
```

### Query PromQL - MTTR por Tipo

```promql
histogram_quantile(0.95,
  rate(self_healing_mttr_seconds_bucket[5m])
)
```

## Testes

```bash
# Unitários
pytest tests/ -v

# Com cobertura
pytest tests/ --cov=src --cov-report=html

# Integração (requer Docker Compose)
docker-compose -f /path/to/docker-compose.test-self-healing.yml up -d
pytest tests/integration/ -v
```

## Dashboard Grafana

Importar `dashboards/self-healing-dashboard.json` no Grafana.

Painéis disponíveis:
- Detecções por Hora
- Taxa de Sucesso de Remediação
- MTTR por Severidade
- Circuit Breaker States
- Kafka Consumer Lag
- Status de Saúde dos Serviços

## Dependências

- Python 3.12+
- FastAPI
- aiokafka
- motor (MongoDB async)
- prometheus-client
- kubernetes (python-client)

## Licença

Apache-2.0
