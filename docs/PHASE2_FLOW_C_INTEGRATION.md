# Phase 2: Flow C Integration - Documentação Técnica

## Visão Geral

A Phase 2 implementa a integração completa do **Flow C** no Neural Hive Mind, conectando Intent → Decision → Orchestration → Execution → Code Forge → Deploy com telemetria end-to-end.

## Arquitetura

### Fluxo Completo (C1-C6)

```
┌─────────────────────────────────────────────────────────────────┐
│                        FLOW C - PHASE 2                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  C1: Validate Decision                                         │
│  │   └─ Validar campos obrigatórios da decisão consolidada    │
│  │                                                              │
│  C2: Generate Tickets                                          │
│  │   ├─ Iniciar Temporal workflow                             │
│  │   ├─ Extrair tasks do cognitive_plan                       │
│  │   └─ Criar tickets via ExecutionTicketClient              │
│  │                                                              │
│  C3: Discover Workers                                          │
│  │   ├─ Coletar capabilities dos tickets                      │
│  │   └─ Descobrir workers via ServiceRegistryClient (healthy) │
│  │                                                              │
│  C4: Assign Tickets                                            │
│  │   ├─ Round-robin assignment aos workers                    │
│  │   ├─ Despachar via WorkerAgentClient.assign_task()        │
│  │   └─ Atualizar status ticket → 'assigned'                 │
│  │                                                              │
│  C5: Monitor Execution                                         │
│  │   ├─ Polling até conclusão ou deadline SLA (4h)           │
│  │   ├─ Intervalo de 60s para pipelines longos               │
│  │   └─ Coletar resultados de tickets                        │
│  │                                                              │
│  C6: Publish Telemetry                                         │
│  │   ├─ Publicar eventos no tópico telemetry-flow-c          │
│  │   ├─ Registrar métricas Prometheus                        │
│  │   └─ Buffer Redis em caso de Kafka indisponível          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes Principais

### 1. FlowCOrchestrator

**Localização:** `libraries/neural_hive_integration/neural_hive_integration/orchestration/flow_c_orchestrator.py`

**Responsabilidades:**
- Coordenação dos steps C1-C6
- Gestão de SLA (4h deadline)
- Medição de latência por step
- Tratamento de falhas e retry

**Métricas Emitidas:**
```python
neural_hive_flow_c_duration_seconds          # Latência end-to-end
neural_hive_flow_c_steps_duration_seconds    # Latência por step
neural_hive_flow_c_success_total             # Execuções bem-sucedidas
neural_hive_flow_c_failures_total            # Falhas por razão
neural_hive_flow_c_sla_violations_total      # Violações de SLA
```

### 2. ServiceRegistryClient

**Localização:** `libraries/neural_hive_integration/neural_hive_integration/clients/service_registry_client.py`

**Funcionalidades:**
- **register_agent()**: Registra worker no Service Registry
- **discover_agents()**: Descobre workers por capabilities (filtro: status=healthy)
- **update_health()**: Heartbeat com telemetria
- **deregister_agent()**: Remove worker do registry

**Protocolo:** gRPC (proto: `services/service-registry/src/proto/service_registry.proto`)

### 3. Webhook Handler (Code Forge)

**Localização:** `services/code-forge/src/integration/generation_webhook.py`

**Segurança:**
- Validação HMAC-SHA256 com constant-time comparison
- Header: `X-Webhook-Signature: sha256=<hex>`
- Secret configurável via env `WEBHOOK_SECRET`

**Endpoint:**
```
POST /api/v1/webhooks/pipeline-completed
```

**Payload:**
```json
{
  "pipeline_id": "string",
  "artifact_id": "string",
  "ticket_id": "string",
  "status": "completed|failed|cancelled",
  "duration_ms": 1000,
  "artifacts": [...],
  "sbom": {...},
  "signature": "cosign-signature"
}
```

### 4. Telemetria Flow C

**Localização:** `libraries/neural_hive_integration/neural_hive_integration/telemetry/flow_c_telemetry.py`

**Tópico Kafka:** `telemetry-flow-c`

**Buffer Redis:**
- Métrica: `neural_hive_flow_c_telemetry_buffer_size` (Gauge)
- Incremento no buffer, decremento no flush
- TTL: 1 hora

## Contratos de Dados

### Ticket Payload

```json
{
  "plan_id": "string",
  "task_type": "code_generation",
  "required_capabilities": ["python", "fastapi"],
  "payload": {
    "ticket_id": "string",           // Adicionado na criação
    "template_id": "microservice",    // Extraído do cognitive_plan
    "parameters": {...},              // Parâmetros do template
    "description": "string"
  },
  "sla_deadline": "2024-01-01T12:00:00Z",
  "priority": 5
}
```

### Worker Task Assignment

```json
{
  "task_id": "task_ticket-001",
  "ticket_id": "ticket-001",
  "task_type": "code_generation",
  "payload": {...},
  "sla_deadline": "2024-01-01T12:00:00Z"
}
```

## Observabilidade

### Métricas Prometheus

**Flow C End-to-End:**
```promql
# p95 latency
histogram_quantile(0.95, rate(neural_hive_flow_c_duration_seconds_bucket[5m]))

# Success rate
rate(neural_hive_flow_c_success_total[10m])
/
(rate(neural_hive_flow_c_success_total[10m]) + rate(neural_hive_flow_c_failures_total[10m]))
```

**Por Step:**
```promql
# C3 Discovery latency
histogram_quantile(0.95, rate(neural_hive_flow_c_steps_duration_seconds_bucket{step="C3"}[5m]))
```

### Alertas

**Arquivo:** `monitoring/alerts/flow-c-integration-alerts.yaml`

**Alertas Configurados:**
1. `FlowCHighLatency`: p95 > 3h (warning)
2. `FlowCLowSuccessRate`: < 99% (critical)
3. `FlowCStepTimeout`: step p99 > 1h (warning)
4. `FlowCNoTicketsGenerated`: Flow sem gerar tickets (critical)
5. `FlowCWorkersUnavailable`: Nenhum worker healthy (critical)
6. `FlowCTelemetryBufferFull`: Buffer > 1000 eventos (warning)
7. `FlowCSLAViolations`: Violações de SLA detectadas (critical)
8. `FlowCWorkerDiscoveryFailures`: Taxa de erro > 10% (warning)

### Dashboard Grafana

**Arquivo:** `monitoring/dashboards/fluxo-c-orquestracao.json`

**Painéis:**
- Latência End-to-End (p95/p99) com linha SLO 4h
- Taxa de Sucesso (Gauge, threshold 99%)
- Duração por Step C1-C6 (p95)
- Workers Disponíveis e Taxa de Execução
- Buffer Telemetria
- Falhas por Razão

## SLOs Definidos

### Latência Intent → Deploy
- **Target:** < 4 horas (p95)
- **Método:** Histogram bucket tracking
- **Alerta:** p95 > 3h (warning)

### Taxa de Sucesso
- **Target:** > 99%
- **Método:** Counter success/failures ratio
- **Alerta:** < 99% por 10min (critical)

### Disponibilidade Workers
- **Target:** >= 1 worker healthy sempre
- **Método:** Service Registry agent count
- **Alerta:** count = 0 por 2min (critical)

## Deployment

### Quick Start

**Deploy Completo:**
```bash
# Deploy automático de todos os componentes Phase 2
./scripts/deploy/deploy-phase2-integration.sh

# Validar deployment
./scripts/validation/validate-phase2-integration.sh

# Teste end-to-end
./tests/phase2-flow-c-integration-test.sh
```

**Opções de Deploy:**
```bash
# Deploy sem rebuild de imagens
./scripts/deploy/deploy-phase2-integration.sh --skip-build

# Dry-run para validar antes de aplicar
./scripts/deploy/deploy-phase2-integration.sh --dry-run

# Deploy com output verbose
./scripts/deploy/deploy-phase2-integration.sh --verbose
```

### Instalação da Biblioteca

**Desenvolvimento:**
```bash
# Editable install
pip install -e libraries/neural_hive_integration
```

**Produção:**
```bash
# Build wheel
cd libraries/neural_hive_integration
./build.sh

# Publish to registry
twine upload --repository-url https://your-registry.com/pypi dist/*

# Install from registry
pip install neural_hive_integration>=1.0.0
```

### Configuração de Serviços

**Orchestrator Dynamic:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orchestrator-config
data:
  MONGODB_URI: mongodb://...
  FLOW_C_ENABLED: "true"
```

**Code Forge:**
```yaml
env:
  - name: WEBHOOK_SECRET
    valueFrom:
      secretKeyRef:
        name: code-forge-secrets
        key: webhook-secret
```

### Tópicos Kafka

**Criação:**
```bash
kubectl apply -f k8s/kafka-topics/telemetry-flow-c-topic.yaml
```

**Verificação:**
```bash
kubectl get kafkatopic telemetry-flow-c -n neural-hive-messaging
```

## Testes

### Testes Unitários

**Executar:**
```bash
cd libraries/neural_hive_integration
pytest tests/test_flow_c_orchestrator.py -v
```

**Cobertura:**
```bash
pytest tests/ --cov=neural_hive_integration --cov-report=html
```

### Teste E2E

**Executar:**
```bash
./tests/phase2-flow-c-integration-test.sh
```

**Valida:**
- Serviços Kubernetes ativos
- Tópicos Kafka criados
- Workers disponíveis
- Métricas Prometheus
- Alertas configurados
- Dashboard Grafana
- SLOs

## Troubleshooting

### Flow C não gera tickets

**Diagnóstico:**
```bash
# Verificar logs orchestrator
kubectl logs -f deployment/orchestrator-dynamic -n neural-hive-orchestration

# Verificar métricas
curl http://orchestrator-dynamic:8000/api/v1/flow-c/status
```

**Possíveis causas:**
- Cognitive plan sem tasks
- ExecutionTicketClient indisponível
- Temporal workflow falhou

### Workers não descobertos

**Diagnóstico:**
```bash
# Verificar Service Registry
kubectl logs -f deployment/service-registry -n neural-hive-orchestration

# Testar discovery manual
curl http://service-registry:50051/agents?type=worker&status=healthy
```

**Possíveis causas:**
- Workers não registrados
- Workers com status unhealthy
- Capabilities não matching

### Buffer telemetria crescendo

**Diagnóstico:**
```promql
# Verificar buffer size
neural_hive_flow_c_telemetry_buffer_size

# Verificar Kafka
kubectl get pods -n neural-hive-messaging | grep kafka
```

**Possíveis causas:**
- Kafka indisponível
- Tópico telemetry-flow-c não existe
- Permissões ACL incorretas

### Webhook HMAC falhando

**Diagnóstico:**
```bash
# Verificar secret configurado
kubectl get secret code-forge-secrets -o yaml

# Verificar logs webhook
kubectl logs -f deployment/code-forge -n neural-hive-execution | grep signature
```

**Possíveis causas:**
- WEBHOOK_SECRET não configurado
- Secret divergente entre emissor/receptor
- Formato do header incorreto

## Referências

- [Service Registry Proto](../services/service-registry/src/proto/service_registry.proto)
- [Flow C Models](../libraries/neural_hive_integration/neural_hive_integration/models/flow_c_context.py)
- [Prometheus Alerts](../monitoring/alerts/flow-c-integration-alerts.yaml)
- [Grafana Dashboard](../monitoring/dashboards/fluxo-c-orquestracao.json)

## Próximos Passos (Phase 3)

- [ ] Otimização de descoberta com cache Redis
- [ ] Circuit breaker para worker assignments
- [ ] Telemetria com OpenTelemetry spans
- [ ] Auto-scaling baseado em métricas Flow C
- [ ] Dashboard de custos por execução
