# Self-Healing Engine

Serviço de autorecuperação para Neural Hive Mind. Detecta incidentes automaticamente e executa playbooks de remediação.

## Funcionalidades

- **Detecção de Incidentes**
  - Deadlocks em workflows (sem progresso por 30+ min)
  - Memory leaks em pods (>90% por 5+ min)
  - Kafka consumer lag (lag excessivo)
  - Database connection (falhas de conexão)
  - Pod crash loop (restarts excessivos)

- **Remediação Automática**
  - 6 playbooks pré-configurados
  - Validação OPA antes de executar ações
  - Circuit Breaker para serviços externos
  - Rastreamento de MTTR
  - Loop de detecção contínua (configurável)

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

## Detecção Contínua

O `DetectionService` suporta loop de detecção contínua para monitoramento proativo:

```python
await detection_service.run_detection_loop(
    workflows=["workflow-1", "workflow-2"],
    pods=[("pod-1", "default"), ("pod-2", "neural-hive")],
    interval_seconds=60,
    kafka_consumer_groups=[("group-1", "topic-1")],
    database_checks=[{"service_name": "mongodb", "host": "mongodb", "port": 27017}],
    check_crash_loops=True,
)
```

### Histórico de Memória em Redis

O histórico de leituras de memória é persistido em Redis para análise de tendências:

- **TTL padrão:** 24 horas
- **Chave Redis:** `self_healing:memory_history:{pod_name}:{namespace}`
- **Estrutura:** Sorted set com timestamps como scores

### Tracing Distribuído

Todas as detecções utilizam OpenTelemetry spans para rastreamento distribuído:

```python
with _start_span("detection.kafka_lag_check") as span:
    _set_span_attr(span, "neural.hive.consumer_group", consumer_group)
    _set_span_attr(span, "neural.hive.has_lag", str(has_lag))
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
- `pod_crash_loop_recovery.yaml` - Detecta e trata pods com crash loop

> **Nota:** Todas as 5 detecções estão 100% implementadas com testes automatizados.

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
# Unitários (107 testes)
pytest tests/ -v

# Com cobertura (meta: 80%+)
pytest tests/ --cov=src --cov-report=html

# Integração (requer Docker Compose)
docker-compose -f /path/to/docker-compose.test-self-healing.yml up -d
pytest tests/integration/ -v
```

### Cobertura de Testes

| Componente | Testes | Cobertura |
|------------|--------|-----------|
| DetectionService | 40+ | 85% |
| PlaybookExecutor | 30+ | 80% |
| HealthMonitor | 20+ | 75% |
| CircuitBreaker | 17+ | 80% |

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
