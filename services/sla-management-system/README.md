# SLA Management System

Sistema de gerenciamento de SLOs, cálculo de error budgets e enforcement de políticas de congelamento de deploy para o Neural Hive-Mind.

## Visão Geral

O SLA Management System é responsável por:
- Gerenciar definições de SLOs (Service Level Objectives) para todos os serviços do Neural Hive-Mind
- Calcular error budgets em tempo real baseado em métricas do Prometheus
- Monitorar burn rates e prever esgotamento de budget
- Enforçar políticas de congelamento de deploy quando budgets críticos
- Integrar com Alertmanager para processar violações de SLO
- Publicar eventos de budget e freeze no Kafka para coordenação com outros agentes

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                  SLA Management System                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────────────────────────┐  │
│  │ FastAPI      │    │ Kubernetes Operator (Kopf)       │  │
│  │              │    │                                  │  │
│  │ REST API     │    │  ┌────────────────────────────┐ │  │
│  │ • /slos      │    │  │ CRD Handlers               │ │  │
│  │ • /budgets   │    │  │ • SLODefinition            │ │  │
│  │ • /policies  │    │  │ • SLAPolicy                │ │  │
│  │ • /webhooks  │    │  │                            │ │  │
│  └──────────────┘    │  │ Enforcement                │ │  │
│                       │  │ • Annotations              │ │  │
│  ┌──────────────┐    │  │ • Freeze/Unfreeze          │ │  │
│  │ Services     │    │  └────────────────────────────┘ │  │
│  │              │    └──────────────────────────────────┘  │
│  │ • Budget     │                                           │
│  │   Calculator │    ┌──────────────────────────────────┐  │
│  │ • Policy     │    │ Background Tasks                 │  │
│  │   Enforcer   │    │                                  │  │
│  │ • SLO        │    │  • Periodic Budget Calculation   │  │
│  │   Manager    │    │  • Policy Evaluation             │  │
│  └──────────────┘    │  • Cache Refresh                 │  │
│                       └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                        │                   │
         ↓                        ↓                   ↓
    Prometheus              PostgreSQL            Redis Cache
    (SLIs)                 (Persistence)         (Budgets)
         │                        │                   │
         ↓                        ↓                   ↓
    Alertmanager            Kafka Bus            Kubernetes API
    (Webhooks)              (Events)             (Annotations)
```

## Tecnologias

- **FastAPI**: Framework web para API REST
- **Kopf**: Framework para Kubernetes operators em Python
- **asyncpg**: Cliente PostgreSQL assíncrono
- **redis**: Cliente Redis Cluster para cache
- **aiokafka**: Cliente Kafka assíncrono
- **httpx**: Cliente HTTP assíncrono para Prometheus/Alertmanager
- **prometheus-client**: Exportação de métricas
- **pydantic**: Validação de dados e configuração

## Estrutura do Projeto

```
services/sla-management-system/
├── Dockerfile                      # Build multi-stage
├── requirements.txt                # Dependências Python
├── IMPLEMENTATION_NOTES.md         # Notas técnicas
├── README.md                       # Este arquivo
└── src/
    ├── config/
    │   └── settings.py             # Configurações Pydantic
    ├── models/
    │   ├── slo_definition.py       # SLODefinition, SLIQuery
    │   ├── error_budget.py         # ErrorBudget, BurnRate
    │   └── freeze_policy.py        # FreezePolicy, FreezeEvent
    ├── clients/
    │   ├── prometheus_client.py    # Cliente Prometheus API
    │   ├── postgresql_client.py    # Cliente PostgreSQL
    │   ├── redis_client.py         # Cliente Redis
    │   ├── kafka_producer.py       # Producer Kafka
    │   └── alertmanager_client.py  # Cliente Alertmanager
    ├── services/
    │   ├── budget_calculator.py    # Cálculo de budgets
    │   ├── policy_enforcer.py      # Enforcement de políticas (TODO)
    │   └── slo_manager.py          # Gestão de SLOs (TODO)
    ├── api/
    │   ├── slos.py                 # Endpoints SLOs (TODO)
    │   ├── budgets.py              # Endpoints budgets (TODO)
    │   ├── policies.py             # Endpoints políticas (TODO)
    │   └── webhooks.py             # Webhook Alertmanager (TODO)
    ├── observability/
    │   └── metrics.py              # Métricas Prometheus (TODO)
    ├── operator/
    │   └── main.py                 # Kubernetes operator (TODO)
    └── main.py                     # Entry point (TODO)
```

## Componentes Principais

### 1. SLO Definition Manager
Gerencia definições de SLOs:
- Importação de alertas Prometheus existentes
- Sincronização com CRDs Kubernetes
- CRUD via API REST
- Validação de queries PromQL

### 2. Error Budget Calculator
Calcula error budgets em tempo real:
- Query de SLIs no Prometheus
- Cálculo de budget total, consumido e restante
- Burn rates para janelas de 1h, 6h, 24h
- Classificação: NORMAL, ELEVATED, FAST, CRITICAL
- Persistência PostgreSQL + cache Redis
- Publicação de eventos Kafka

### 3. Policy Enforcement Engine
Enforça políticas de congelamento:
- Avaliação automática baseada em budgets
- Aplicação de annotations Kubernetes
- Freeze/unfreeze de namespaces, serviços ou global
- Integração com ArgoCD/Tekton para bloqueio de deploys

### 4. Alertmanager Integration
Processa alertas de SLO:
- Webhook receiver para notificações
- Correlação com budgets atuais
- Incremento de contadores de violação
- Trigger automático de políticas

### 5. Kubernetes Operator
Reconciliação de CRDs:
- `SLODefinition`: Definições declarativas de SLOs
- `SLAPolicy`: Políticas de congelamento
- Sincronização bidirecional com PostgreSQL
- Atualização de status dos CRDs

## Configuração

### Variáveis de Ambiente

#### Prometheus
- `PROMETHEUS__URL`: URL do Prometheus (default: `http://prometheus-server.monitoring.svc.cluster.local:9090`)
- `PROMETHEUS__TIMEOUT_SECONDS`: Timeout para queries (default: `30`)
- `PROMETHEUS__MAX_RETRIES`: Retries em caso de falha (default: `3`)

#### PostgreSQL
- `POSTGRESQL__HOST`: Host do PostgreSQL
- `POSTGRESQL__PORT`: Porta (default: `5432`)
- `POSTGRESQL__DATABASE`: Nome do database (default: `sla_management`)
- `POSTGRESQL__USER`: Usuário
- `POSTGRESQL__PASSWORD`: Senha
- `POSTGRESQL__POOL_MIN_SIZE`: Tamanho mínimo do pool (default: `2`)
- `POSTGRESQL__POOL_MAX_SIZE`: Tamanho máximo do pool (default: `10`)

#### Redis
- `REDIS__CLUSTER_NODES`: Lista de nodes Redis (JSON array)
- `REDIS__PASSWORD`: Senha (opcional)
- `REDIS__CACHE_TTL_SECONDS`: TTL para budgets (default: `60`)

#### Kafka
- `KAFKA__BOOTSTRAP_SERVERS`: Lista de brokers Kafka (JSON array)
- `KAFKA__BUDGET_TOPIC`: Tópico de budgets (default: `sla.budgets`)
- `KAFKA__FREEZE_TOPIC`: Tópico de freeze (default: `sla.freeze.events`)
- `KAFKA__VIOLATIONS_TOPIC`: Tópico de violações (default: `sla.violations`)

#### Alertmanager
- `ALERTMANAGER__URL`: URL do Alertmanager (default: `http://alertmanager.monitoring.svc.cluster.local:9093`)
- `ALERTMANAGER__WEBHOOK_PATH`: Path do webhook (default: `/webhooks/alertmanager`)

#### Calculator
- `CALCULATOR__CALCULATION_INTERVAL_SECONDS`: Intervalo de cálculo (default: `30`)
- `CALCULATOR__ERROR_BUDGET_WINDOW_DAYS`: Janela de cálculo (default: `30`)
- `CALCULATOR__BURN_RATE_FAST_THRESHOLD`: Threshold fast burn (default: `14.4`)
- `CALCULATOR__BURN_RATE_SLOW_THRESHOLD`: Threshold slow burn (default: `6`)

#### Policy
- `POLICY__FREEZE_THRESHOLD_PERCENT`: % para acionar freeze (default: `20`)
- `POLICY__AUTO_UNFREEZE_ENABLED`: Auto-descongelar (default: `true`)
- `POLICY__UNFREEZE_THRESHOLD_PERCENT`: % para descongelar (default: `50`)

## Métricas Prometheus

O serviço exporta 20+ métricas:

### Cálculos
- `sla_calculations_total`: Total de cálculos executados
- `sla_calculation_duration_seconds`: Duração dos cálculos

### Error Budgets
- `sla_budget_remaining_percent`: Budget restante por SLO
- `sla_budget_consumed_percent`: Budget consumido
- `sla_budget_status`: Status (0=HEALTHY, 1=WARNING, 2=CRITICAL, 3=EXHAUSTED)
- `sla_burn_rate`: Taxa de consumo por janela

### Freezes
- `sla_freezes_active`: Número de freezes ativos
- `sla_freezes_activated_total`: Total de freezes acionados
- `sla_freezes_resolved_total`: Total de freezes resolvidos
- `sla_freeze_duration_seconds`: Duração dos freezes

### SLOs e Violações
- `sla_slos_total`: Total de SLOs definidos
- `sla_slo_violations_total`: Total de violações

### Integrações
- `sla_prometheus_queries_total`: Queries ao Prometheus
- `sla_kafka_events_published_total`: Eventos publicados no Kafka
- `sla_alertmanager_webhooks_received_total`: Webhooks recebidos

## API Endpoints (Planejados)

### SLOs
- `POST /api/v1/slos`: Criar SLO
- `GET /api/v1/slos/{slo_id}`: Buscar SLO
- `GET /api/v1/slos`: Listar SLOs
- `PUT /api/v1/slos/{slo_id}`: Atualizar SLO
- `DELETE /api/v1/slos/{slo_id}`: Deletar SLO
- `POST /api/v1/slos/{slo_id}/test`: Testar query SLO
- `POST /api/v1/slos/import/alerts`: Importar de alertas Prometheus

### Budgets
- `GET /api/v1/budgets/{slo_id}`: Buscar budget
- `GET /api/v1/budgets`: Listar budgets
- `POST /api/v1/budgets/{slo_id}/recalculate`: Forçar recálculo
- `GET /api/v1/budgets/{slo_id}/history`: Histórico de budgets
- `GET /api/v1/budgets/summary`: Resumo agregado
- `GET /api/v1/budgets/{slo_id}/burn-rate`: Calcular burn rate

### Políticas
- `POST /api/v1/policies`: Criar política
- `GET /api/v1/policies/{policy_id}`: Buscar política
- `GET /api/v1/policies`: Listar políticas
- `PUT /api/v1/policies/{policy_id}`: Atualizar política
- `DELETE /api/v1/policies/{policy_id}`: Deletar política
- `GET /api/v1/policies/freezes/active`: Freezes ativos
- `POST /api/v1/policies/freezes/{event_id}/resolve`: Resolver freeze
- `GET /api/v1/policies/freezes/history`: Histórico de freezes

### Webhooks
- `POST /webhooks/alertmanager`: Receber alertas do Alertmanager

## CRDs (Planejados)

### SLODefinition
```yaml
apiVersion: neural-hive.io/v1
kind: SLODefinition
metadata:
  name: bus-latency-slo
spec:
  name: "Neural Hive Bus Latency"
  sloType: LATENCY
  serviceName: message-bus
  layer: orquestracao
  target: 0.999
  windowDays: 30
  sliQuery:
    metricName: neural_hive_barramento_duration_seconds
    query: "histogram_quantile(0.95, sum(rate(neural_hive_barramento_duration_seconds_bucket[5m])) by (le)) * 1000"
```

### SLAPolicy
```yaml
apiVersion: neural-hive.io/v1
kind: SLAPolicy
metadata:
  name: orchestration-freeze-policy
spec:
  name: "Orchestration Freeze Policy"
  scope: NAMESPACE
  target: neural-hive-orchestration
  actions:
    - BLOCK_DEPLOY
    - ALERT_ONLY
  triggerThresholdPercent: 20
  autoUnfreeze: true
  unfreezeThresholdPercent: 50
```

## Deployment

### Helm
```bash
helm install sla-management-system ./helm-charts/sla-management-system \
  --namespace neural-hive-monitoring \
  --create-namespace \
  --values values-production.yaml
```

### Script de Deploy
```bash
./scripts/deploy/deploy-sla-management-system.sh
```

## Desenvolvimento Local

### Pré-requisitos
- Python 3.11+
- PostgreSQL 14+
- Redis Cluster
- Kafka
- Prometheus
- Alertmanager

### Setup
```bash
cd services/sla-management-system
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Testes
```bash
pytest tests/ -v
```

## Integrações Operacionais

### Prometheus
- **Fonte de SLIs**: Consulta métricas `neural_hive_*` para calcular SLIs
- **Query range**: Janelas de 30 dias para error budgets
- **Retry**: 3 tentativas com backoff exponencial

### Alertmanager
- **Webhook receiver**: POST /webhooks/alertmanager
- **Processamento**: Filtra alertas com label `slo=...`
- **Correlação**: Busca SLO, budget atual, avalia políticas

### Kafka
- **Tópicos**:
  - `sla.budgets`: Atualizações de budgets
  - `sla.freeze.events`: Eventos de freeze/unfreeze
  - `sla.violations`: Violações de SLO
- **Headers**: event_type, service_name, severity

### Kubernetes
- **Annotations**: `neural-hive.io/sla-freeze`, `neural-hive.io/freeze-policy-id`
- **Scope**: Namespace, Service (Deployment/StatefulSet), Global
- **Enforcement**: Via Kubernetes operator

## Escalabilidade e Resiliência

- **Autoscaling**: HPA com 2-10 réplicas baseado em CPU/memória
- **Cache Redis**: Reduz carga no PostgreSQL, TTL 60s
- **Background tasks**: Cálculos assíncronos não bloqueantes
- **Retry logic**: Exponential backoff para integrações externas
- **Graceful degradation**: Continua operando se Redis falhar

## Segurança

- **mTLS**: Comunicação entre serviços
- **RBAC**: Operator com permissões mínimas (CRDs, annotations)
- **Secrets**: Credenciais em Kubernetes Secrets
- **Auditoria**: Todos os eventos persistidos no PostgreSQL

## Monitoramento

- **Dashboard Grafana**: `sla-management-system.json` (7 rows, 21 panels)
- **Alertas**: 12 alertas para saúde do sistema
- **Traces**: OpenTelemetry para todas as operações
- **Logs**: Structured logging (JSON) via structlog

## Próximos Passos

### Prioridade ALTA
1. Completar service layer (PolicyEnforcer, SLOManager)
2. Implementar API layer (4 routers, 21 endpoints)
3. Entry point (main.py)
4. Kubernetes operator (Kopf handlers)
5. CRDs (SLODefinition, SLAPolicy)

### Prioridade MÉDIA
6. Helm charts completo
7. Scripts de deploy e validação
8. Testes unitários e integração

### Prioridade BAIXA
9. Dashboard Grafana
10. Documentação operacional
11. Modelos preditivos de burn rate
12. UI web para gestão

## Referências

- [SLO Alerting Guide](../../docs/observability/slos-alerting-guide.md)
- [Documento 05 - Observabilidade](../../docs/documento-05-observabilidade-completa-neural-hive.md)
- [Documento 08 - Fase 2](../../docs/documento-08-fase2-orquestrador-dinamico.md)
- [Alertas SLO Existentes](../../monitoring/alerts/slo-alerts.yaml)
- [Dashboard SLO/Error Budgets](../../monitoring/dashboards/slos-error-budgets.json)

## Licença

Propriedade do projeto Neural Hive-Mind.
