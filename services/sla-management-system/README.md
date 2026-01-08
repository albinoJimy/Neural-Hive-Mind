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

## Status

**✅ PRODUCTION READY - v1.0.0**

Completado em: 2025-01-15

Todos os componentes core implementados e testados.

## Estrutura do Projeto

```
services/sla-management-system/
├── Dockerfile                      # Build multi-stage ✅
├── requirements.txt                # Dependências Python ✅
├── IMPLEMENTATION_NOTES.md         # Notas técnicas ✅
├── DEPLOYMENT_GUIDE.md             # Guia de deployment ✅
├── OPERATIONAL_RUNBOOK.md          # Runbook operacional ✅
├── README.md                       # Este arquivo ✅
└── src/
    ├── config/
    │   └── settings.py             # Configurações Pydantic ✅
    ├── models/
    │   ├── slo_definition.py       # SLODefinition, SLIQuery ✅
    │   ├── error_budget.py         # ErrorBudget, BurnRate ✅
    │   └── freeze_policy.py        # FreezePolicy, FreezeEvent ✅
    ├── clients/
    │   ├── prometheus_client.py    # Cliente Prometheus API ✅
    │   ├── postgresql_client.py    # Cliente PostgreSQL ✅
    │   ├── redis_client.py         # Cliente Redis ✅
    │   ├── kafka_producer.py       # Producer Kafka ✅
    │   └── alertmanager_client.py  # Cliente Alertmanager ✅
    ├── services/
    │   ├── budget_calculator.py    # Cálculo de budgets ✅
    │   ├── policy_enforcer.py      # Enforcement de políticas ✅
    │   └── slo_manager.py          # Gestão de SLOs ✅
    ├── api/
    │   ├── slos.py                 # Endpoints SLOs ✅
    │   ├── budgets.py              # Endpoints budgets ✅
    │   ├── policies.py             # Endpoints políticas ✅
    │   └── webhooks.py             # Webhook Alertmanager ✅
    ├── observability/
    │   └── metrics.py              # Métricas Prometheus ✅
    ├── operator/
    │   └── main.py                 # Kubernetes operator ✅
    └── main.py                     # Entry point ✅
```

## Componentes Principais

### 1. SLO Definition Manager ✅ COMPLETO
Gerencia definições de SLOs:
- Importação de alertas Prometheus existentes
- Sincronização com CRDs Kubernetes
- CRUD via API REST (src/api/slos.py - 7 endpoints)
- Validação de queries PromQL

### 2. Error Budget Calculator ✅ COMPLETO
Calcula error budgets em tempo real:
- Query de SLIs no Prometheus
- Cálculo de budget total, consumido e restante
- Burn rates para janelas de 1h, 6h, 24h
- Classificação: NORMAL, ELEVATED, FAST, CRITICAL
- Persistência PostgreSQL + cache Redis
- Publicação de eventos Kafka

### 3. Policy Enforcement Engine ✅ COMPLETO
Enforça políticas de congelamento:
- Avaliação automática baseada em budgets
- Aplicação de annotations Kubernetes
- Freeze/unfreeze de namespaces, serviços ou global
- Integração com ArgoCD/Tekton para bloqueio de deploys

### 4. Alertmanager Integration ✅ COMPLETO
Processa alertas de SLO:
- Webhook receiver para notificações (src/api/webhooks.py)
- Correlação com budgets atuais
- Incremento de contadores de violação
- Trigger automático de políticas

### 5. Kubernetes Operator ✅ COMPLETO
Reconciliação de CRDs (src/operator/main.py):
- `SLODefinition`: Definições declarativas de SLOs
- `SLAPolicy`: Políticas de congelamento
- Sincronização bidirecional com PostgreSQL
- Atualização de status dos CRDs
- Reconciliação periódica (5 minutos)

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

## API Endpoints ✅ IMPLEMENTADOS

**Total**: 21 endpoints funcionais

### SLOs (7 endpoints)
- `POST /api/v1/slos`: Criar SLO ✅
- `GET /api/v1/slos/{slo_id}`: Buscar SLO ✅
- `GET /api/v1/slos`: Listar SLOs ✅
- `PUT /api/v1/slos/{slo_id}`: Atualizar SLO ✅
- `DELETE /api/v1/slos/{slo_id}`: Deletar SLO ✅
- `POST /api/v1/slos/{slo_id}/test`: Testar query SLO ✅
- `POST /api/v1/slos/import/alerts`: Importar de alertas Prometheus ✅

### Budgets (6 endpoints)
- `GET /api/v1/budgets/{slo_id}`: Buscar budget ✅
- `GET /api/v1/budgets`: Listar budgets ✅
- `POST /api/v1/budgets/{slo_id}/recalculate`: Forçar recálculo ✅
- `GET /api/v1/budgets/{slo_id}/history`: Histórico de budgets ✅
- `GET /api/v1/budgets/summary`: Resumo agregado ✅
- `GET /api/v1/budgets/{slo_id}/burn-rate`: Calcular burn rate ✅

### Políticas (7 endpoints)
- `POST /api/v1/policies`: Criar política ✅
- `GET /api/v1/policies/{policy_id}`: Buscar política ✅
- `GET /api/v1/policies`: Listar políticas ✅
- `PUT /api/v1/policies/{policy_id}`: Atualizar política ✅
- `DELETE /api/v1/policies/{policy_id}`: Deletar política ✅
- `GET /api/v1/policies/freezes/active`: Freezes ativos ✅
- `POST /api/v1/policies/freezes/{event_id}/resolve`: Resolver freeze ✅
- `GET /api/v1/policies/freezes/history`: Histórico de freezes ✅

### Webhooks (1 endpoint)
- `POST /webhooks/alertmanager`: Receber alertas do Alertmanager ✅

**Documentação**: `/docs` (OpenAPI/Swagger UI)

## CRDs ✅ IMPLEMENTADOS

**Definições**: `k8s/crds/slodefinition-crd.yaml`, `k8s/crds/slapolicy-crd.yaml`

### SLODefinition
```yaml
apiVersion: neural-hive.io/v1
kind: SLODefinition
metadata:
  name: orchestrator-latency-slo
  namespace: neural-hive-orchestration
spec:
  name: "Orchestrator Dynamic - P95 Latency"
  description: "95th percentile latency for orchestration workflows should be under 200ms"
  sloType: LATENCY
  serviceName: orchestrator-dynamic
  component: workflow-execution
  layer: orquestracao
  target: 0.999
  windowDays: 30
  sliQuery:
    metricName: neural_hive_orchestration_duration_seconds
    query: |
      histogram_quantile(0.95,
        sum(rate(neural_hive_orchestration_duration_seconds_bucket{
          service="orchestrator-dynamic"
        }[5m])) by (le)
      ) * 1000 < 200
    aggregation: avg
  enabled: true
status:
  synced: true
  lastSyncTime: "2025-01-15T10:00:00Z"
  sloId: "uuid-here"
  currentSLI: 0.9995
  budgetRemaining: 85.2
  budgetStatus: HEALTHY
```

**Ver exemplos**: `examples/sla-management-system/example-slo-*.yaml`

### SLAPolicy
```yaml
apiVersion: neural-hive.io/v1
kind: SLAPolicy
metadata:
  name: orchestration-freeze-policy
  namespace: neural-hive-orchestration
spec:
  name: "Orchestration Layer Freeze Policy"
  description: "Bloqueia deployments na camada de orquestração quando error budget está abaixo de 20%"
  scope: NAMESPACE
  target: neural-hive-orchestration
  actions:
    - BLOCK_DEPLOY
    - ALERT_ONLY
  triggerThresholdPercent: 20
  autoUnfreeze: true
  unfreezeThresholdPercent: 50
  enabled: true
status:
  synced: true
  lastSyncTime: "2025-01-15T10:00:00Z"
  policyId: "uuid-here"
  activeFreezes: 0
```

**Ver exemplos**: `examples/sla-management-system/example-policy-*.yaml`

## Deployment

**Helm Chart**: `helm-charts/sla-management-system/` ✅

### Instalação Rápida

```bash
# Script automatizado (recomendado)
./scripts/deploy/deploy-sla-management-system.sh

# Com opções
./scripts/deploy/deploy-sla-management-system.sh --values custom-values.yaml --namespace meu-namespace

# Dry-run
./scripts/deploy/deploy-sla-management-system.sh --dry-run
```

### Instalação Manual via Helm

```bash
# 1. Instalar CRDs
kubectl apply -f k8s/crds/slodefinition-crd.yaml
kubectl apply -f k8s/crds/slapolicy-crd.yaml

# 2. Criar tópicos Kafka
kubectl apply -f k8s/kafka-topics/sla-topics.yaml

# 3. Instalar chart
helm install sla-management-system ./helm-charts/sla-management-system \
  --namespace neural-hive-monitoring \
  --create-namespace \
  --values helm-charts/sla-management-system/values.yaml
```

### Validação

```bash
# Executar validação completa
./scripts/validation/validate-sla-management-system.sh

# Com relatório
./scripts/validation/validate-sla-management-system.sh --report validation.json
```

**Documentação Completa**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

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

## Dependency Injection Pattern

### Visão Geral

O SLA Management System utiliza **Dependency Injection** do FastAPI com um padrão híbrido:

- **Produção**: Overrides configurados no `lifespan` do `main.py`
- **Fallback**: Funções de dependency acessam módulo `main` diretamente (para compatibilidade)
- **Testes**: Overrides manuais com mocks

### Arquitetura de DI

```
┌─────────────────────────────────────────────────────────┐
│              main.py (lifespan context)                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │ async def lifespan(app: FastAPI):                │  │
│  │   # Startup                                      │  │
│  │   1. Inicializar clientes e serviços            │  │
│  │      - prometheus_client, postgresql_client     │  │
│  │      - budget_calculator, policy_enforcer       │  │
│  │   2. Configurar app.dependency_overrides        │  │
│  │      - slos.get_slo_manager                     │  │
│  │      - budgets.get_budget_calculator            │  │
│  │   yield                                         │  │
│  │   # Shutdown                                    │  │
│  │   3. Fechar conexões                            │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ↓
┌─────────────────────────────────────────────────────────┐
│                API Routers (policies.py)                │
│  ┌──────────────────────────────────────────────────┐  │
│  │ def get_policy_enforcer() -> PolicyEnforcer:     │  │
│  │     from .. import main                          │  │
│  │     if main.policy_enforcer is None:             │  │
│  │         raise HTTPException(503, "Not init")     │  │
│  │     return main.policy_enforcer                  │  │
│  │                                                   │  │
│  │ @router.get("/freezes/active")                   │  │
│  │ async def get_active_freezes(                    │  │
│  │     enforcer: PolicyEnforcer = Depends(get_...)  │  │
│  │ ):                                               │  │
│  │     # Usa instância injetada                     │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Dependências Configuradas

#### API de SLOs (`src/api/slos.py`)

| Função de Dependency | Serviço Injetado | Uso |
|---------------------|------------------|-----|
| `get_slo_manager()` | `SLOManager` | Gestão de SLOs |

#### API de Budgets (`src/api/budgets.py`)

| Função de Dependency | Serviço Injetado | Uso |
|---------------------|------------------|-----|
| `get_budget_calculator()` | `BudgetCalculator` | Cálculo de budgets |
| `get_postgresql_client()` | `PostgreSQLClient` | Persistência |
| `get_prometheus_client()` | `PrometheusClient` | Queries de métricas |

#### API de Políticas (`src/api/policies.py`)

| Função de Dependency | Serviço Injetado | Uso |
|---------------------|------------------|-----|
| `get_policy_enforcer()` | `PolicyEnforcer` | Enforcement de políticas |
| `get_postgresql_client()` | `PostgreSQLClient` | Persistência |

#### API de Webhooks (`src/api/webhooks.py`)

| Função de Dependency | Serviço Injetado | Uso |
|---------------------|------------------|-----|
| `get_slo_manager()` | `SLOManager` | Busca de SLOs |
| `get_budget_calculator()` | `BudgetCalculator` | Cálculo de budgets |
| `get_policy_enforcer()` | `PolicyEnforcer` | Avaliação de políticas |
| `get_postgresql_client()` | `PostgreSQLClient` | Persistência |

### Padrão Híbrido (Fallback)

As funções de dependency têm um **fallback** que acessa o módulo `main` diretamente:

```python
# src/api/policies.py
def get_policy_enforcer() -> PolicyEnforcer:
    """
    Returns the PolicyEnforcer instance from application state.

    In production, this is overridden via FastAPI dependency_overrides in main.py.
    This fallback accesses the module-level singleton directly.
    """
    from .. import main
    if main.policy_enforcer is None:
        raise HTTPException(
            status_code=503,
            detail="PolicyEnforcer not initialized. Service is starting up."
        )
    return main.policy_enforcer
```

**Vantagens**:
- Funciona mesmo sem overrides (útil para testes rápidos)
- Retorna erro 503 claro se serviço não inicializou
- Compatível com padrão de overrides do FastAPI

### Exemplo de Uso em Testes

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

def test_list_policies_with_mock():
    from src.api import policies

    # Criar app de teste
    app = FastAPI()
    app.include_router(policies.router)

    # Criar mock do PostgreSQL
    mock_pg = MagicMock()
    mock_pg.list_policies = AsyncMock(return_value=[])

    # Configurar override
    app.dependency_overrides[policies.get_postgresql_client] = lambda: mock_pg

    # Testar endpoint
    client = TestClient(app)
    response = client.get('/api/v1/policies')

    assert response.status_code == 200
    assert response.json()['total'] == 0
```

### Configuração em Produção

Em produção, os overrides são configurados no `lifespan` do `main.py`:

```python
# services/sla-management-system/src/main.py (linhas 179-210)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # ... inicializar serviços ...

    # Configurar dependency overrides
    app.dependency_overrides[slos.get_slo_manager] = override_slo_manager
    app.dependency_overrides[budgets.get_budget_calculator] = override_budget_calculator
    # ... outros overrides ...

    yield

    # Shutdown
    # ... fechar conexões ...
```

### Troubleshooting

#### Erro: "HTTPException 503: PolicyEnforcer not initialized"

**Causa**: Endpoint foi chamado antes do `lifespan` completar inicialização.

**Solução**:
1. Verificar que o serviço iniciou completamente (logs: `"sla_management_system_started"`)
2. Usar endpoint `/ready` para verificar readiness
3. Em testes, sempre configurar overrides manualmente

#### Erro: "AttributeError: 'NoneType' object has no attribute 'list_policies'"

**Causa**: Serviço global (`postgresql_client`) é `None` quando override é chamado.

**Solução**:
1. Verificar ordem de inicialização no `lifespan` (serviços antes de overrides)
2. Verificar que conexões foram estabelecidas com sucesso
3. Checar logs de erro durante inicialização

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

## Monitoramento ✅ IMPLEMENTADO

- **Dashboard Grafana**: `monitoring/dashboards/sla-management-system.json` (7 rows, 25+ panels)
- **Alertas Prometheus**: `monitoring/alerts/sla-management-system-alerts.yaml` (12+ alertas)
- **ServiceMonitor**: Integração automática com Prometheus Operator
- **Metrics Endpoint**: :9090/metrics (20+ métricas customizadas)
- **Logs**: Structured logging (JSON) via structlog

**Dashboard URL**: https://grafana.neural-hive.io/d/sla-management-system

## Operações

### Comandos Úteis

```bash
# Ver SLOs
kubectl get slodefinitions --all-namespaces

# Ver políticas
kubectl get slapolicies --all-namespaces

# Ver freezes ativos
curl http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000/api/v1/policies/freezes/active

# Verificar health
curl http://sla-management-system.neural-hive-monitoring.svc.cluster.local:8000/health

# Ver logs
kubectl logs -n neural-hive-monitoring -l app.kubernetes.io/name=sla-management-system -f
```

**Runbook Completo**: [OPERATIONAL_RUNBOOK.md](OPERATIONAL_RUNBOOK.md)

## Arquivos de Infraestrutura

### Kubernetes
- **CRDs**: `k8s/crds/slodefinition-crd.yaml`, `k8s/crds/slapolicy-crd.yaml`
- **Kafka Topics**: `k8s/kafka-topics/sla-topics.yaml`

### Helm Chart
- **Chart**: `helm-charts/sla-management-system/`
  - Chart.yaml, values.yaml
  - 14 templates (deployment, service, operator, rbac, hpa, etc.)

### Monitoring
- **Alertas**: `monitoring/alerts/sla-management-system-alerts.yaml`
- **Alertmanager Config**: `monitoring/alertmanager/sla-webhook-config.yaml`
- **Dashboard**: `monitoring/dashboards/sla-management-system.json`

### Scripts
- **Deploy**: `scripts/deploy/deploy-sla-management-system.sh`
- **Validação**: `scripts/validation/validate-sla-management-system.sh`

### Exemplos
- **SLOs**: `examples/sla-management-system/example-slo-*.yaml` (3 exemplos)
- **Policies**: `examples/sla-management-system/example-policy-*.yaml` (3 exemplos)

## Referências

### Documentação
- [README Principal](README.md)
- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Operational Runbook](OPERATIONAL_RUNBOOK.md)
- [Implementation Notes](IMPLEMENTATION_NOTES.md)

### Documentos do Projeto
- [Documento 05 - Observabilidade](../../docs/documento-05-observabilidade-completa-neural-hive.md)
- [Documento 08 - Fase 2](../../docs/documento-08-fase2-orquestrador-dinamico.md)
- [SLO Alerting Guide](../../docs/observability/slos-alerting-guide.md)

### Recursos Relacionados
- [Alertas SLO Existentes](../../monitoring/alerts/slo-alerts.yaml)
- [Dashboard SLO/Error Budgets](../../monitoring/dashboards/slos-error-budgets.json)

## Licença

Propriedade do projeto Neural Hive-Mind.
