# Design: Fase 2 - Finalização

**Data:** 2026-03-27
**Status:** Design Aprovado
**Componentes:** Architect Agent, Software Engineering Pipeline

---

## Visão Geral

Este documento especifica os dois componentes em falta para conclusão da Fase 2 (Orquestração e Coordenação de Swarm):

1. **Architect Agent** - Sistema híbrido de planejamento arquitetural e validação contínua
2. **Software Engineering Pipeline** - Integração completa de CI/CD com inteligência

---

## 1. Architect Agent

### 1.1 Propósito

Agente especializado em arquitetura de software que atua em duas fases:
- **Planejamento**: Antes da geração de código, propõe arquitetura baseada em requisitos
- **Validação**: Após implementação, valida conformidade com princípios arquiteturais

### 1.2 Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    Architect Agent                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   Design     │  │   Validate   │  │    Evolution         │ │
│  │   Planner    │  │    Engine    │  │    Tracker           │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘ │
│         │                 │                     ▲               │
│         └─────────────────┴─────────────────────┘               │
│                           │                                     │
│                    Input: CognitivePlans + Scout Insights      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Componentes

#### Design Planner
Recebe `CognitivePlan` do STE e propõe arquitetura de alto nível.

**Entrada:**
```json
{
  "plan_id": "cp-123",
  "intent": "create_user_management_microservice",
  "requirements": {
    "scale": "high",
    "consistency": "strong",
    "latency_p99_ms": 200
  }
}
```

**Saída:**
```json
{
  "plan_id": "arch-456",
  "architecture_type": "microservices",
  "components": [
    {"name": "user-api", "stack": "python/fastapi", "replicas": 3},
    {"name": "user-db", "stack": "postgresql", "ha": true}
  ],
  "patterns": ["repository", "cqrs", "event_sourcing"],
  "rationale": "Microservices para escala independente; CQRS para separar leitura/escrita"
}
```

#### Validate Engine
Consome insights do Scout Agent e valida contra princípios SOLID/clean architecture.

**Análises:**
- Responsabilidade única (SRP)
- Acoplamento (dependências cíclicas)
- Coesão (métodos por classe)
- Complexidade (cicloomática)
- Padrões detectados (via Scout)

**Saída:**
```json
{
  "report_id": "val-789",
  "repo_url": "github.com/org/repo",
  "health_score": 72,
  "violations": [
    {"type": "srp", "severity": "high", "location": "UserService.py:145", "description": "Classe com 15 responsabilidades"},
    {"type": "coupling", "severity": "medium", "location": "OrderController.py", "description": "Depende de 12 classes"}
  ],
  "suggestions": [
    {"priority": 1, "description": "Separar UserService em UserService, AuthAdapter, ProfileRepository"}
  ]
}
```

#### Evolution Tracker
Mantém histórico de decisões arquiteturais e detecta drift.

**Funcionalidades:**
- Versionamento de planos arquiteturais
- Comparação planejado vs implementado
- Alertas de divergência

### 1.4 API REST

```
POST   /api/v1/architect/plan
       Body: { cognitive_plan_id, requirements_override }
       Response: ArchitecturePlan

GET    /api/v1/architect/plan/{plan_id}
       Response: ArchitecturePlan completo

POST   /api/v1/architect/validate
       Body: { repo_url, branch, rules }
       Response: ValidationReport

GET    /api/v1/architect/health/{repo_url}
       Response: { health_score, trend, top_violations }

POST   /api/v1/architect/evolve
       Body: { plan_id, new_requirements }
       Response: EvolutionSuggestion
```

### 1.5 Integrações

| Fonte | Tipo | Uso |
|-------|------|-----|
| STE | Kafka | Consumir `cognitive.plans.created` |
| Scout Agents | HTTP | Buscar insights (padrões, dependências) |
| Code Forge | HTTP | Sobrescrever templates com decisões arquiteturais |
| MongoDB | Sync | Persistir ArchitecturePlan, ValidationReport |

---

## 2. Software Engineering Pipeline

### 2.1 Propósito

Sistema completo de CI/CD com geração automática de pipelines, orquestração de deploys e inteligência para detecção de anomalias.

### 2.2 Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│           Software Engineering Pipeline                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  Pipeline    │  │  Pipeline    │  │   Pipeline           │ │
│  │  Generator   │  │ Orchestrator │  │   Intelligence       │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘ │
│         │                 │                     │               │
│         └─────────────────┴─────────────────────┘               │
│                           │                                     │
│                    Output: CI/CD + Deploy                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Componentes

#### Pipeline Generator
Analisa stack do projeto e gera pipelines CI/CD.

**Suporte:**
- GitHub Actions (.github/workflows/*.yml)
- GitLab CI (.gitlab-ci.yml)
- Jenkins (Jenkinsfile)
- Tekton (Pipeline YAML)

**Detecção automática de stack:**
- Python (requirements.txt, pyproject.toml)
- Node.js (package.json)
- Java (pom.xml, build.gradle)
- Go (go.mod)
- Dockerfile, docker-compose.yml

**Saída gerada:**
```yaml
# .github/workflows/neural-hive-generated.yml
name: Neural Hive CI/CD
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: ruff check .
  test:
    strategy:
      matrix: { python-version: ["3.11", "3.12"] }
    steps:
      - run: pytest --cov=src
  security:
    steps:
      - run: trivy fs .
  deploy:
    needs: [lint, test, security]
    steps:
      - run: helm upgrade ...
```

#### Pipeline Orchestrator
Orquestra deploys completos com gates.

**Estágios:**
1. **Pre-flight**: Validações (versão, secrets)
2. **Build**: Container image, SBOM
3. **Test**: Unit, integration, E2E
4. **Security**: SAST (Trivy), SCA (Snyk)
5. **Staging**: Deploy em ambiente staging
6. **Approval**: Gate manual/configurável
7. **Production**: Deploy em produção

**GitOps Integration:**
- ArgoCD: Application creation + sync + health check
- Flux CD: Kustomization/Helm release + reconciliation
- Fallback: kubectl apply

**Auto-rollback:**
- Health check falha → rollback automático
- Métricas degradam → rollback automático
- Alertas configuráveis (SLA, error rate)

#### Pipeline Intelligence
Monitora e otimiza pipelines.

**Funcionalidades:**
- Detecção de testes flaky (falham intermitentemente)
- Análise de dependências problemáticas
- Sugestões de cache e paralelização
- Alertas preditivos (degradação gradual)

**Métricas coletadas:**
- Duração por stage
- Taxa de sucesso/falha
- Testes mais lentos
- Dependências que mais falham

### 2.4 API REST

```
POST   /api/v1/pipeline/generate
       Body: { repo_url, provider, overrides }
       Response: PipelineManifest

GET    /api/v1/pipeline/templates
       Response: [{ name, description, template }]

POST   /api/v1/pipeline/deploy
       Body: { repo_url, git_sha, environment }
       Response: DeployRun

GET    /api/v1/pipeline/status/{run_id}
       Response: { status, stage, logs_url }

POST   /api/v1/pipeline/rollback/{run_id}
       Response: RollbackStatus

GET    /api/v1/pipeline/insights
       Query: repo_url, timeframe
       Response: InsightsReport

GET    /api/v1/pipeline/anomalies
       Query: repo_url, severity
       Response: Anomaly[]
```

### 2.5 Integrações

| Destino | Tipo | Uso |
|---------|------|-----|
| Code Forge | HTTP | Buscar código gerado |
| GitHub | API | Criar workflows, PRs, dispatch workflows |
| GitLab | API | Criar pipelines, trigger jobs |
| Jenkins | API | Criar jobs, trigger builds |
| ArgoCD | API | Application CRUD, sync, operations |
| Flux CD | kubectl | Kustomization reconciliation |
| MongoDB | Sync | PipelineRun, Insights, Anomaly |
| Prometheus | Query | Métricas de produção para rollback |

---

## 3. Fluxos End-to-End

### 3.1 Fluxo: Novo Projeto

```
1. User Intent → Gateway → STE
2. STE → CognitivePlan { "create_microservice": "user-api" }
3. CognitivePlan (Kafka) → Architect Agent
4. Architect Agent → DesignPlan:
   - Arquitetura: microservices (Python/FastAPI)
   - Banco: PostgreSQL com HA
   - Padrões: Repository, CQRS, Event Sourcing
5. DesignPlan → Code Forge (sobrescreve templates)
6. Code Forge → Código gerado (alinhado com arquitetura)
7. Código → Pipeline Generator
8. Generator → GitHub Actions workflow (CI + CD)
9. Commit → Pipeline Orchestrator
10. Orchestrator: lint → test → build → security → staging
11. Aprovação manual → production
12. Deploy → Architect Agent (Validate)
13. Validate → ValidationReport (health score atualizado)
```

### 3.2 Fluxo: Refatoração

```
1. Scout Agent → Signal: "UserService tem complexidade 25"
2. Signal (Kafka) → Architect Agent (Validate Engine)
3. Validate Engine → ValidationReport:
   - Violation: SRP (15 responsabilidades)
   - Suggestion: Separar em UserService + AuthAdapter + ProfileRepository
4. Sugestão → Code Forge (refatoração)
5. Refatoração → Pipeline Orchestrator
6. Deploy → Validation passou (score 72 → 89)
```

### 3.3 Fluxo: Pipeline Intelligence

```
1. Pipeline falha: integration/auth_test (3x seguidas)
2. Pipeline Intelligence → Anomaly detectada
3. Análise: Test flaky (race condition)
4. Alerta → Slack
5. Sugestão: "Adicionar retry, mock API externa"
6. Deploy recente em produção? Sim → Auto-rollback
```

---

## 4. Estrutura de Dados

### ArchitecturePlan
```json
{
  "plan_id": "arch-123",
  "cognitive_plan_id": "cp-456",
  "architecture_type": "microservices|monolith|serverless",
  "components": [
    {"name": "user-api", "stack": "python/fastapi", "replicas": 3},
    {"name": "user-db", "stack": "postgresql", "ha": true}
  ],
  "patterns": ["repository", "cqrs", "event_sourcing"],
  "rationale": "Microservices para escala independente",
  "created_at": "2026-03-27T10:00:00Z",
  "updated_at": "2026-03-27T12:00:00Z"
}
```

### ValidationReport
```json
{
  "report_id": "val-789",
  "repo_url": "github.com/org/repo",
  "branch": "main",
  "health_score": 72,
  "trend": "up|down|stable",
  "violations": [
    {"type": "srp", "severity": "high", "location": "UserService.py:145", "description": "..."}
  ],
  "suggestions": [
    {"priority": 1, "description": "Separar responsabilidades", "effort": "L"}
  ],
  "created_at": "2026-03-27T11:00:00Z"
}
```

### PipelineRun
```json
{
  "run_id": "pipe-001",
  "repo_url": "github.com/org/repo",
  "git_sha": "abc123",
  "status": "running|success|failed|rolled_back",
  "stage": "build|test|security|staging|production",
  "stages_completed": ["lint", "build"],
  "started_at": "2026-03-27T11:00:00Z",
  "finished_at": null,
  "rollback_reason": null
}
```

---

## 5. Estrutura de Diretórios

```
services/
├── architect-agent/
│   ├── src/
│   │   ├── main.py
│   │   ├── planners/
│   │   │   ├── __init__.py
│   │   │   └── design_planner.py
│   │   ├── validators/
│   │   │   ├── __init__.py
│   │   │   ├── validate_engine.py
│   │   │   └── rules.py
│   │   ├── evolution/
│   │   │   ├── __init__.py
│   │   │   └── tracker.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── router.py
│   │   ├── consumers/
│   │   │   ├── __init__.py
│   │   │   └── cognitive_plan_consumer.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py
│   │   └── config/
│   │       └── settings.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── e2e/
│   ├── helm/architect-agent/
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── README.md
│
└── software-engineering-pipeline/
    ├── src/
    │   ├── main.py
    │   ├── generators/
    │   │   ├── __init__.py
    │   │   ├── base.py
    │   │   ├── github_actions.py
    │   │   ├── gitlab_ci.py
    │   │   ├── jenkins.py
    │   │   └── tekton.py
    │   ├── orchestrators/
    │   │   ├── __init__.py
    │   │   └── pipeline_orchestrator.py
    │   ├── intelligence/
    │   │   ├── __init__.py
    │   │   ├── anomaly_detector.py
    │   │   ├── flaky_test_detector.py
    │   │   └── optimzier.py
    │   ├── clients/
    │   │   ├── __init__.py
    │   │   ├── github_client.py
    │   │   ├── gitlab_client.py
    │   │   ├── argocd_client.py
    │   │   └── flux_client.py
    │   ├── api/
    │   │   ├── __init__.py
    │   │   └── router.py
    │   ├── models/
    │   │   ├── __init__.py
    │   │   └── schemas.py
    │   └── config/
    │       └── settings.py
    ├── tests/
    │   ├── unit/
    │   ├── integration/
    │   └── e2e/
    ├── helm/software-engineering-pipeline/
    │   ├── Chart.yaml
    │   ├── values.yaml
    │   └── templates/
    ├── Dockerfile
    ├── requirements.txt
    └── README.md
```

---

## 6. Testes

### Architect Agent
- **Unit**: DesignPlanner, ValidateEngine, EvolutionTracker
- **Integration**: Kafka consumer, Scout API, MongoDB
- **E2E**: CognitivePlan → ArchitecturePlan → Code Forge
- **Meta**: 80% cobertura

### Software Engineering Pipeline
- **Unit**: Generators (GitHub, GitLab, Jenkins, Tekton), Orchestrator stages, Intelligence algorithms
- **Integration**: GitHub/GitLab API, ArgoCD/Flux clients
- **E2E**: Code → Pipeline → Deploy → Validate
- **Meta**: 80% cobertura

---

## 7. Métricas Prometheus

### Architect Agent
```
architect_plans_created_total{architecture_type}
architect_validation_duration_seconds{phase}
architect_health_score{repo_url}
architect_violations_detected_total{severity, type}
architect_suggestions_applied_total{priority}
architect_drift_detected_total{repo_url}
```

### Software Engineering Pipeline
```
pipeline_runs_total{status, stage}
pipeline_duration_seconds{stage, provider}
pipeline_anomalies_detected_total{type, severity}
pipeline_rollback_total{reason, environment}
pipeline_flaky_tests_total{test_name, repo_url}
pipeline_insights_generated_total{type}
pipeline_deploy_success_rate{environment}
```

---

## 8. Considerações

### Performance
- Architect Agent: Cache para planos similares (TTL 1h)
- Pipeline Intelligence: Batch queries ao Prometheus (5min)

### Segurança
- Orchestrator: Validar permissões antes de deploy (RBAC)
- Secrets: Usar Kubernetes Secrets, variáveis de ambiente
- Code Forge: Validar assinaturas de artefatos

### Resiliência
- Retry em chamadas externas (GitHub, ArgoCD, Scout)
- Circuit breaker para APIs externas
- Graceful degradation se LLM indisponível

### Multi-tenant
- Isolamento de planos/pipelines por organização
- Rate limiting por tenant
- Quotas por organização

---

## Aprovação

Design aprovado em 2026-03-27.
Próximo passo: Criar specs de implementação via writing-plans skill.
