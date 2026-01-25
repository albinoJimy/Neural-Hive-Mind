# Worker Agents

## Visão Geral

Worker Agents são executores distribuídos responsáveis por consumir Execution Tickets do Kafka, coordenar dependências, executar tarefas e reportar resultados. Implementam o lado de execução do Fluxo C da arquitetura Neural Hive-Mind.

### Responsabilidades

1. **Consumir Execution Tickets** do Kafka `execution.tickets`
2. **Registrar-se no Service Registry** com capabilities, telemetria e health status
3. **Executar tarefas** via executors específicos por task_type
4. **Coordenar dependências** verificando status de tickets predecessores
5. **Garantir SLAs** respeitando timeouts, max_retries e deadlines
6. **Acionar compensações** em caso de falha (criar compensation tickets)
7. **Reportar feedback** ao Orchestrator via Kafka `execution.results` e API
8. **Integrar com Istio** (mTLS), OpenTelemetry (tracing), Prometheus (metrics)
9. **Health checks periódicos** enviando heartbeats ao Service Registry

### Status

Executores agora integram serviços reais (Code Forge, OPA/Trivy) e publicam resultados em Avro. Fallbacks simulados permanecem ativos para evitar quebra do fluxo quando integrações externas estiverem indisponíveis.

### Real Executors
- **Build**: usa CodeForge `/api/v1/pipelines` com polling e validação de artifacts (SBOM/assinatura). Configurar `CODE_FORGE_URL` e `CODE_FORGE_TIMEOUT_SECONDS`.
- **Deploy**: integra com ArgoCD (Application + sync + health check). Habilitar `ARGOCD_ENABLED=true` e fornecer token via Secret `argocd-token`.
- **Test**: suporta subprocess ou GitHub Actions/Jenkins (`provider` no ticket). Token GitHub via Secret `github-token`.
- **Validate**: orquestra OPA, Trivy, SonarQube, Snyk, Checkov; agrega violações e métricas.
- Métricas Prometheus adicionadas para cada executor (taxa, duração, chamadas externas) e dashboard em `monitoring/grafana/dashboards/worker-agents-executors.json`.

### Executors

- **ExecuteExecutor**: Integra com Code Forge para geração de código com polling do status.
- **BuildExecutor**: Dispara pipelines CI/CD no Code Forge e retorna artifacts/SBOM/assinatura.
- **TestExecutor**: Suporta múltiplos providers (GitHub Actions, GitLab CI, Jenkins, Local, Simulação) com parsing de relatórios JUnit XML, Cobertura e LCOV.
- **ValidateExecutor**: Valida políticas via OPA e roda SAST com Trivy (quando habilitado).
- **DeployExecutor**: Integra com ArgoCD e Flux CD para deploy GitOps completo com health polling. Fallback simulado quando GitOps indisponivel.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Worker Agent                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐         ┌─────────────────┐          │
│  │ Kafka        │────────→│ Execution       │          │
│  │ Consumer     │         │ Engine          │          │
│  │ (tickets)    │         └─────────────────┘          │
│  └──────────────┘                   │                   │
│                                      ↓                   │
│  ┌──────────────┐         ┌─────────────────┐          │
│  │ Service      │         │ Dependency      │          │
│  │ Registry     │←────────│ Coordinator     │          │
│  │ Client       │         └─────────────────┘          │
│  └──────────────┘                   │                   │
│                                      ↓                   │
│  ┌──────────────┐         ┌─────────────────┐          │
│  │ Execution    │←────────│ Task Executor   │          │
│  │ Ticket       │         │ Registry        │          │
│  │ Client       │         └─────────────────┘          │
│  └──────────────┘                   │                   │
│                           ┌──────────┴──────────┐       │
│  ┌──────────────┐         │                     │       │
│  │ Kafka        │         │  5 Executors:       │       │
│  │ Producer     │←────────│  - BUILD            │       │
│  │ (results)    │         │  - DEPLOY           │       │
│  └──────────────┘         │  - TEST             │       │
│                           │  - VALIDATE         │       │
│  ┌──────────────┐         │  - EXECUTE          │       │
│  │ HTTP Server  │         └─────────────────────┘       │
│  │ (health,     │                                        │
│  │  metrics)    │                                        │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## Kafka Integration

- **Consumer** (`execution.tickets`): Avro via Schema Registry (`execution-ticket.avsc`).
- **Producer** (`execution.results`): Avro via Schema Registry (`execution-result.avsc`) com fallback JSON se Schema Registry estiver indisponível.
- **Schema Registry**: URL configurável via `KAFKA_SCHEMA_REGISTRY_URL`.

Fluxo:
```
execution.tickets (Kafka) -> Execution Engine -> Executors -> Code Forge / OPA / Trivy -> Result Producer -> execution.results (Kafka)
```

## Tecnologias

- **FastAPI** - REST API para health/metrics
- **confluent-kafka + Schema Registry** - Consumer/Producer Avro
- **grpcio** - Cliente gRPC para Service Registry
- **httpx** - Clientes HTTP (Execution Ticket Service, OPA, Code Forge)
- **temporalio** - (Opcional) Activity workers
- **Prometheus** - Métricas
- **OpenTelemetry** - Distributed tracing
- **structlog** - Logging estruturado
- **Python 3.11+**

## Estrutura do Projeto

```
services/worker-agents/
├── Dockerfile              # Multi-stage build
├── requirements.txt        # Dependências Python
├── src/
│   ├── main.py            # Entry point principal
│   ├── config/            # Configurações
│   │   └── settings.py
│   ├── clients/           # Clientes de integração
│   │   ├── service_registry_client.py
│   │   ├── execution_ticket_client.py
│   │   ├── kafka_ticket_consumer.py
│   │   ├── kafka_result_producer.py
│   │   ├── argocd_client.py
│   │   ├── flux_client.py
│   │   ├── github_actions_client.py
│   │   ├── gitlab_ci_client.py
│   │   └── jenkins_client.py
│   ├── engine/            # Lógica de execução
│   │   ├── execution_engine.py
│   │   └── dependency_coordinator.py
│   ├── executors/         # Executores por task_type
│   │   ├── base_executor.py
│   │   ├── registry.py
│   │   ├── build_executor.py
│   │   ├── deploy_executor.py
│   │   ├── test_executor.py
│   │   ├── validate_executor.py
│   │   └── execute_executor.py
│   ├── utils/             # Utilitários
│   │   └── test_report_parser.py
│   ├── api/               # HTTP API
│   │   └── http_server.py
│   ├── models/            # Modelos Pydantic
│   │   ├── execution_ticket.py
│   │   └── execution_result.py
│   └── observability/     # Métricas e tracing
│       └── metrics.py
```

## Configuração

### Backpressure Control

O Worker Agent implementa **backpressure automático** para prevenir sobrecarga de memória quando muitos tickets chegam rapidamente.

#### Como Funciona

1. **Semaphore de Consumo**: Limita o número de tickets "in-flight" (consumidos mas não finalizados)
2. **Pause/Resume Automático**: Consumer Kafka é pausado quando threshold atingido, resumido quando capacidade disponível
3. **Tracking de In-Flight**: Rastreamento preciso de tickets em processamento via `Set[ticket_id]`

#### Configuração

```yaml
config:
  maxConcurrentTickets: 10  # Limite de tickets in-flight (default: 10)
  consumerPauseThreshold: 0.8  # Pausar quando 80% da capacidade (default: 0.8)
  consumerResumeThreshold: 0.5  # Resumir quando 50% da capacidade (default: 0.5)
```

#### Métricas

- `worker_agent_tickets_in_flight`: Gauge - Número de tickets in-flight
- `worker_agent_consumer_paused_total`: Counter - Total de pausas por backpressure
- `worker_agent_consumer_resumed_total`: Counter - Total de resumes após backpressure
- `worker_agent_consumer_pause_duration_seconds`: Histogram - Duração de pausas

#### Alertas

- **WorkerBackpressureActive** (warning): In-flight > 80% por 2 minutos
- **WorkerBackpressureCritical** (critical): In-flight = limite máximo por 5 minutos
- **WorkerConsumerPausedTooLong** (warning): Consumer pausado > 5 minutos

#### Troubleshooting

**Sintoma**: Alerta `WorkerBackpressureActive` disparado

**Causas Comuns**:
1. Carga alta sustentada (muitos tickets chegando)
2. Processamento lento (dependências lentas, I/O lento)
3. Tickets travados (deadlock, timeout)

**Ações**:
1. Verificar latência de processamento:
   ```bash
   kubectl logs -n neural-hive-execution <pod-name> | grep task_duration
   ```

2. Verificar tickets in-flight:
   ```bash
   kubectl exec -n neural-hive-execution <pod-name> -- curl localhost:9090/metrics | grep tickets_in_flight
   ```

3. Considerar aumentar `maxConcurrentTickets` se carga sustentada:
   ```yaml
   config:
     maxConcurrentTickets: 20  # Aumentar de 10 para 20
   ```

4. Considerar aumentar `maxConcurrentTasks` se processamento lento:
   ```yaml
   config:
     maxConcurrentTasks: 10  # Aumentar de 5 para 10
   ```

**Sintoma**: Alerta `WorkerBackpressureCritical` disparado

**Ações Imediatas**:
1. Verificar logs de erro:
   ```bash
   kubectl logs -n neural-hive-execution <pod-name> --tail=100 | grep -E "error|failed"
   ```

2. Verificar tickets travados:
   ```bash
   kubectl exec -n neural-hive-execution <pod-name> -- curl localhost:9090/metrics | grep active_tasks
   ```

3. Considerar restart se tickets travados:
   ```bash
   kubectl delete pod -n neural-hive-execution <pod-name>
   ```

#### Tuning

**Cenário 1: Carga Alta Sustentada**
- Aumentar `maxConcurrentTickets` (ex: 20)
- Aumentar `maxConcurrentTasks` (ex: 10)
- Aumentar replicas (HPA)

**Cenário 2: Processamento Lento**
- Otimizar executores (cache, paralelização)
- Aumentar `maxConcurrentTasks`
- Aumentar timeout de tasks

**Cenário 3: Picos de Carga**
- Manter `maxConcurrentTickets` conservador (10)
- Configurar HPA agressivo (targetCPU: 60%)
- Aumentar `consumerPauseThreshold` (ex: 0.9)

### Variáveis de Ambiente

```bash
# Identificação
SERVICE_NAME=worker-agents
NAMESPACE=neural-hive-execution
CLUSTER=production

# Capabilities
SUPPORTED_TASK_TYPES=BUILD,DEPLOY,TEST,VALIDATE,EXECUTE
MAX_CONCURRENT_TASKS=5

# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TICKETS_TOPIC=execution.tickets
KAFKA_RESULTS_TOPIC=execution.results
KAFKA_CONSUMER_GROUP_ID=worker-agents

# Service Registry
SERVICE_REGISTRY_HOST=service-registry
SERVICE_REGISTRY_PORT=50051
HEARTBEAT_INTERVAL_SECONDS=30

# Execution Ticket Service
EXECUTION_TICKET_SERVICE_URL=http://execution-ticket-service:8080

# Code Forge
CODE_FORGE_URL=http://code-forge.neural-hive-execution:8000
CODE_FORGE_ENABLED=true
CODE_FORGE_TIMEOUT_SECONDS=14400

# GitOps / ArgoCD
ARGOCD_URL=https://argocd.example.com
ARGOCD_TOKEN=your-argocd-token
ARGOCD_ENABLED=false

# GitOps / Flux CD
FLUX_ENABLED=false
FLUX_NAMESPACE=flux-system
FLUX_KUBECONFIG_PATH=
FLUX_TIMEOUT_SECONDS=600

# OPA / Validation
OPA_URL=http://opa.neural-hive-governance:8181
OPA_ENABLED=true
OPA_TOKEN=                                # Token Bearer para autenticacao OPA (opcional)
OPA_TIMEOUT_SECONDS=30                    # Timeout para requisicoes OPA
OPA_VERIFY_SSL=true                       # Verificar certificado SSL do OPA
OPA_RETRY_ATTEMPTS=3                      # Numero de tentativas em caso de falha
OPA_RETRY_BACKOFF_BASE_SECONDS=2          # Base para exponential backoff em segundos
OPA_RETRY_BACKOFF_MAX_SECONDS=60          # Maximo de backoff em segundos
OPA_POLL_INTERVAL_SECONDS=5               # Intervalo de polling para bundle activation
OPA_POLL_TIMEOUT_SECONDS=300              # Timeout total para polling de bundle

# SAST
TRIVY_ENABLED=true
TRIVY_TIMEOUT_SECONDS=300

# Test Execution
TEST_EXECUTION_TIMEOUT_SECONDS=600
TEST_RETRY_ATTEMPTS=3
ALLOWED_TEST_COMMANDS=pytest,npm test,go test,mvn test

# GitHub Actions
GITHUB_ACTIONS_ENABLED=false
GITHUB_API_URL=https://api.github.com
GITHUB_TOKEN=your-github-token
GITHUB_ACTIONS_TIMEOUT_SECONDS=900

# GitLab CI
GITLAB_CI_ENABLED=false
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your-gitlab-token
GITLAB_TIMEOUT_SECONDS=900
GITLAB_TLS_VERIFY=true

# Jenkins
JENKINS_ENABLED=false
JENKINS_URL=https://jenkins.example.com
JENKINS_USER=your-jenkins-user
JENKINS_TOKEN=your-jenkins-token
JENKINS_TIMEOUT_SECONDS=600
JENKINS_TLS_VERIFY=true

# Test Report Parsing
JUNIT_XML_ENABLED=true
COVERAGE_REPORT_ENABLED=true

# Temporal (opcional)
ENABLE_TEMPORAL_ACTIVITIES=false

# Observabilidade
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4317
PROMETHEUS_PORT=9090
HTTP_PORT=8080
LOG_LEVEL=INFO
```

## Deployment

### Via Script

```bash
./scripts/deploy/deploy-worker-agents.sh
```

### Via Helm

```bash
helm upgrade --install worker-agents \
  ./helm-charts/worker-agents \
  --namespace neural-hive-execution \
  --create-namespace
```

### Pré-requisitos

- Kafka cluster rodando
- Service Registry rodando
- Execution Ticket Service rodando
- Orchestrator Dynamic rodando
- Tópico `execution.tickets` criado
- Tópico `execution.results` criado
- Schema Registry disponível
- Code Forge acessível (para BUILD/EXECUTE)
- OPA/Trivy configurados (para VALIDATE)

## GitOps Integration

O DeployExecutor suporta integracao com ArgoCD e Flux CD para deployments GitOps.

### ArgoCD

Para habilitar integracao com ArgoCD:

```bash
ARGOCD_ENABLED=true
ARGOCD_URL=https://argocd.example.com
ARGOCD_TOKEN=your-argocd-token
```

Exemplo de ticket DEPLOY com ArgoCD:

```json
{
  "ticket_id": "deploy-123",
  "task_type": "DEPLOY",
  "parameters": {
    "provider": "argocd",
    "deployment_name": "my-app",
    "namespace": "production",
    "repo_url": "https://github.com/org/gitops-repo",
    "chart_path": "charts/my-app",
    "revision": "main",
    "image": "registry/my-app:v1.0.0",
    "replicas": 3,
    "sync_strategy": "auto",
    "timeout_seconds": 600,
    "poll_interval": 5
  }
}
```

### Flux CD

Para habilitar integracao com Flux CD:

```bash
FLUX_ENABLED=true
FLUX_NAMESPACE=flux-system
FLUX_KUBECONFIG_PATH=/path/to/kubeconfig  # Opcional, usa in-cluster se vazio
FLUX_TIMEOUT_SECONDS=600
```

Exemplo de ticket DEPLOY com Flux:

```json
{
  "ticket_id": "deploy-456",
  "task_type": "DEPLOY",
  "parameters": {
    "provider": "flux",
    "deployment_name": "my-app",
    "namespace": "production",
    "source_name": "my-git-repo",
    "path": "./deploy/production",
    "interval": "5m",
    "prune": true,
    "timeout_seconds": 600
  }
}
```

### Selecao de Provider

O executor seleciona o provider com base em:

1. `parameters.provider` - Se especificado ('argocd', 'flux')
2. Disponibilidade do cliente (ArgoCD ou Flux client inicializado)
3. Fallback para ArgoCD legado (via URL direta)
4. Fallback para simulacao (quando nenhum GitOps disponivel)

### Metricas GitOps

- `worker_agent_argocd_api_calls_total{method,status}` - Chamadas API ArgoCD
- `worker_agent_flux_api_calls_total{method,status}` - Chamadas API Flux
- `worker_agent_deploy_tasks_executed_total{status}` - Deploys executados
- `worker_agent_deploy_duration_seconds{stage}` - Duracao por etapa

## TEST Executor Integration

O TestExecutor suporta multiplos providers de CI para execucao de testes.

### Providers Suportados

- **GitHub Actions**: Dispara workflows e coleta resultados de artefatos
- **GitLab CI**: Dispara pipelines e coleta test reports nativos
- **Jenkins**: Dispara builds e coleta JUnit reports
- **Local**: Executa comandos de teste via subprocess
- **Simulacao**: Fallback quando nenhum provider esta disponivel

### GitHub Actions

Para habilitar integracao com GitHub Actions:

```bash
GITHUB_ACTIONS_ENABLED=true
GITHUB_API_URL=https://api.github.com
GITHUB_TOKEN=your-github-token
GITHUB_ACTIONS_TIMEOUT_SECONDS=900
```

Exemplo de ticket TEST com GitHub Actions:

```json
{
  "ticket_id": "test-123",
  "task_type": "TEST",
  "parameters": {
    "test_provider": "github_actions",
    "repository": "owner/repo",
    "workflow_id": "test.yml",
    "ref": "main",
    "inputs": {"debug": "true"}
  }
}
```

### GitLab CI

Para habilitar integracao com GitLab CI:

```bash
GITLAB_CI_ENABLED=true
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your-gitlab-token
GITLAB_TIMEOUT_SECONDS=900
```

Exemplo de ticket TEST com GitLab CI:

```json
{
  "ticket_id": "test-456",
  "task_type": "TEST",
  "parameters": {
    "test_provider": "gitlab_ci",
    "project_id": 12345,
    "ref": "main",
    "variables": {"CI_DEBUG": "true"}
  }
}
```

### Jenkins

Para habilitar integracao com Jenkins:

```bash
JENKINS_ENABLED=true
JENKINS_URL=https://jenkins.example.com
JENKINS_USER=your-jenkins-user
JENKINS_TOKEN=your-jenkins-token
JENKINS_TIMEOUT_SECONDS=600
```

Exemplo de ticket TEST com Jenkins:

```json
{
  "ticket_id": "test-789",
  "task_type": "TEST",
  "parameters": {
    "test_provider": "jenkins",
    "job_name": "my-test-job",
    "parameters": {"BRANCH": "main", "TEST_SUITE": "unit"}
  }
}
```

### Local

Para execucao local de testes:

```json
{
  "ticket_id": "test-local",
  "task_type": "TEST",
  "parameters": {
    "test_provider": "local",
    "command": "pytest",
    "working_dir": "/app/tests",
    "args": ["-v", "--cov=src"]
  }
}
```

### Selecao de Provider

O executor seleciona o provider com base em:

1. `parameters.test_provider` - Se especificado
2. Disponibilidade do cliente (GitHub Actions, GitLab CI ou Jenkins inicializado)
3. Fallback para execucao local (se comando permitido)
4. Fallback para simulacao (quando nenhum provider disponivel)

### Parsing de Relatorios

O executor suporta parsing automatico de relatorios:

- **JUnit XML**: Relatórios de testes no formato JUnit/xUnit
- **Cobertura XML**: Relatórios de cobertura no formato Cobertura
- **LCOV**: Relatórios de cobertura no formato LCOV

Habilite o parsing via variaveis de ambiente:

```bash
JUNIT_XML_ENABLED=true
COVERAGE_REPORT_ENABLED=true
```

### Retry Logic

O executor implementa retry com backoff exponencial:

- **Tentativas**: Configuravel via `TEST_RETRY_ATTEMPTS` (padrao: 3)
- **Backoff**: 2s, 4s, 8s... ate 60s maximo
- **Erros transientes**: Conexao, timeout, rate limiting

### Metricas de Testes

- `worker_agent_test_tasks_executed_total{status,suite}` - Testes executados
- `worker_agent_test_duration_seconds{suite}` - Duracao dos testes
- `worker_agent_tests_passed_total{suite}` - Testes aprovados
- `worker_agent_tests_failed_total{suite}` - Testes reprovados
- `worker_agent_test_coverage_percent{suite}` - Cobertura percentual
- `worker_agent_github_actions_api_calls_total{method,status}` - Chamadas GitHub Actions
- `worker_agent_gitlab_ci_api_calls_total{method,status}` - Chamadas GitLab CI
- `worker_agent_jenkins_api_calls_total{method,status}` - Chamadas Jenkins
- `worker_agent_test_report_parsing_total{format,status}` - Parsing de relatorios
- `worker_agent_coverage_report_parsing_total{format,status}` - Parsing de cobertura

## EXECUTE Executor Integration

O ExecuteExecutor suporta multiplos runtimes para execucao generica de comandos e tarefas.

### Runtimes Suportados

- **Kubernetes Jobs**: Execucao isolada em Jobs K8s com resource limits e security context
- **Docker**: Execucao em containers Docker com CPU/memory limits e network isolation
- **AWS Lambda**: Execucao serverless via Lambda com billing metrics
- **Local**: Execucao via subprocess com sandboxing e whitelist de comandos
- **Code Forge**: Integracao para geracao de codigo com polling de status
- **Simulation**: Fallback simulado quando nenhum runtime disponivel

### Kubernetes Jobs

Para habilitar execucao via Kubernetes Jobs:

```bash
K8S_JOBS_ENABLED=true
K8S_JOBS_NAMESPACE=neural-hive-execution
K8S_JOBS_TIMEOUT_SECONDS=600
K8S_JOBS_SERVICE_ACCOUNT=worker-agent-executor
```

Exemplo de ticket EXECUTE com K8s:

```json
{
  "ticket_id": "exec-123",
  "task_type": "EXECUTE",
  "parameters": {
    "runtime": "k8s",
    "command": ["python", "-c", "print('hello')"],
    "image": "python:3.11-slim",
    "cpu_limit": "1000m",
    "memory_limit": "512Mi",
    "timeout_seconds": 300
  }
}
```

### Docker

Para habilitar execucao via Docker:

```bash
DOCKER_ENABLED=true
DOCKER_BASE_URL=unix:///var/run/docker.sock
DOCKER_TIMEOUT_SECONDS=600
DOCKER_DEFAULT_CPU_LIMIT=1.0
DOCKER_DEFAULT_MEMORY_LIMIT=512m
```

Exemplo de ticket EXECUTE com Docker:

```json
{
  "ticket_id": "exec-456",
  "task_type": "EXECUTE",
  "parameters": {
    "runtime": "docker",
    "command": ["node", "script.js"],
    "image": "node:18-alpine",
    "cpu_limit": 2.0,
    "memory_limit": "1g",
    "network_mode": "bridge"
  }
}
```

### AWS Lambda

Para habilitar execucao via Lambda:

```bash
LAMBDA_ENABLED=true
LAMBDA_REGION=us-east-1
LAMBDA_FUNCTION_NAME=neural-hive-executor
LAMBDA_ACCESS_KEY=your-access-key
LAMBDA_SECRET_KEY=your-secret-key
```

Exemplo de ticket EXECUTE com Lambda:

```json
{
  "ticket_id": "exec-789",
  "task_type": "EXECUTE",
  "parameters": {
    "runtime": "lambda",
    "command": "echo",
    "args": ["hello", "world"],
    "function_name": "neural-hive-executor"
  }
}
```

### Local

Para execucao local via subprocess:

```bash
LOCAL_RUNTIME_ENABLED=true
LOCAL_RUNTIME_TIMEOUT_SECONDS=300
LOCAL_RUNTIME_WORKING_DIR=/tmp/neural-hive-execution
LOCAL_RUNTIME_ALLOWED_COMMANDS=python,python3,node,bash,sh
LOCAL_RUNTIME_ENABLE_SANDBOX=true
```

Exemplo de ticket EXECUTE local:

```json
{
  "ticket_id": "exec-local",
  "task_type": "EXECUTE",
  "parameters": {
    "runtime": "local",
    "command": "python",
    "args": ["-c", "print('hello')"],
    "working_dir": "/tmp/workspace",
    "env_vars": {"DEBUG": "true"}
  }
}
```

### Selecao de Runtime

O executor seleciona o runtime com base em:

1. `parameters.runtime` - Se especificado ('k8s', 'docker', 'lambda', 'local')
2. `DEFAULT_RUNTIME` - Runtime padrao configurado
3. `RUNTIME_FALLBACK_CHAIN` - Cadeia de fallback (ex: 'k8s,docker,local,simulation')
4. Disponibilidade do cliente (runtime client inicializado)
5. Fallback final para simulacao

### Fallback Chain

O executor implementa fallback automatico entre runtimes:

- Se K8s falha -> tenta Docker
- Se Docker falha -> tenta Local
- Se Local falha -> usa Simulation
- Metricas de fallback registradas em `execute_runtime_fallbacks_total`

### Resource Limits

Suporte a resource limits por runtime:

**Kubernetes Jobs:**
- `cpu_request`, `cpu_limit` (ex: '100m', '1000m')
- `memory_request`, `memory_limit` (ex: '128Mi', '512Mi')

**Docker:**
- `cpu_limit` (float, ex: 1.0, 2.0)
- `memory_limit` (string, ex: '512m', '1g')

### Security

**Kubernetes Jobs:**
- Security context: runAsNonRoot=true, readOnlyRootFilesystem=true
- Service account configuravel
- Network policies aplicadas

**Docker:**
- Network isolation (bridge, host, none)
- User mapping configuravel

**Local:**
- Whitelist de comandos permitidos
- Working directory isolation
- Environment variables sanitizadas
- Process tree killing (SIGTERM -> SIGKILL)

### Metricas EXECUTE

- `worker_agent_execute_tasks_executed_total{status}` - Tarefas executadas
- `worker_agent_execute_duration_seconds{runtime}` - Duracao por runtime
- `worker_agent_execute_runtime_fallbacks_total{from_runtime,to_runtime}` - Fallbacks
- `worker_agent_docker_executions_total{status}` - Execucoes Docker
- `worker_agent_docker_execution_duration_seconds{stage}` - Duracao Docker
- `worker_agent_k8s_jobs_executed_total{status}` - Jobs K8s executados
- `worker_agent_k8s_job_duration_seconds{stage}` - Duracao K8s Jobs
- `worker_agent_lambda_invocations_total{status}` - Invocacoes Lambda
- `worker_agent_lambda_duration_seconds` - Duracao Lambda
- `worker_agent_lambda_billed_duration_seconds` - Duracao cobrada Lambda
- `worker_agent_local_executions_total{status}` - Execucoes locais
- `worker_agent_local_execution_duration_seconds` - Duracao local

## Desenvolvimento Local

### Setup

```bash
cd services/worker-agents
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Execução

```bash
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export SERVICE_REGISTRY_HOST=localhost
export EXECUTION_TICKET_SERVICE_URL=http://localhost:8080

python -m src.main
```

## Testing

- Unit tests: `pytest tests/`
- Kafka + Schema Registry integration: `RUN_KAFKA_INTEGRATION_TESTS=1 pytest tests/test_kafka_ticket_consumer_avro.py tests/test_result_producer_avro.py`
- Requisitos de integração: Kafka, Schema Registry e Code Forge/OPA opcionais para executors reais.

## Métricas Prometheus

### Lifecycle
- `worker_agent_startup_total` - Inicializações
- `worker_agent_registered_total` - Registros no Service Registry
- `worker_agent_heartbeat_total{status}` - Heartbeats enviados
- `worker_agent_deregistered_total` - Deregistros

### Tickets
- `worker_agent_tickets_consumed_total{task_type}` - Tickets consumidos
- `worker_agent_tickets_processing_total{task_type}` - Tickets em processamento
- `worker_agent_tickets_completed_total{task_type}` - Tickets concluídos
- `worker_agent_tickets_failed_total{task_type,error_type}` - Tickets falhados
- `worker_agent_active_tasks` - Tarefas ativas
- `worker_agent_task_duration_seconds{task_type}` - Duração de execução

### Dependencies
- `worker_agent_dependency_checks_total{result}` - Verificações de dependências
- `worker_agent_dependency_wait_duration_seconds` - Tempo de espera

### Retries
- `worker_agent_task_retries_total{task_type,attempt}` - Tentativas de retry
- `worker_agent_tasks_cancelled_total` - Tarefas canceladas

### API & Kafka
- `worker_agent_ticket_api_calls_total{method,status}` - Chamadas à API
- `worker_agent_results_published_total{status}` - Resultados publicados

## Monitoramento

### Dashboard Grafana

Dashboard disponível em `observability/grafana/dashboards/worker-agents-execution.json`

### Queries PromQL Úteis

```promql
# Taxa de sucesso
sum(rate(worker_agent_tickets_completed_total[5m]))
/
sum(rate(worker_agent_tickets_consumed_total[5m]))

# Duração P95 por task_type
histogram_quantile(0.95,
  rate(worker_agent_task_duration_seconds_bucket[5m])
)

# Tarefas ativas
sum(worker_agent_active_tasks)
```

## Troubleshooting

### Consumer não conecta ao Kafka

```bash
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=worker-agents | grep kafka
```

### Registro no Service Registry falha

```bash
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=worker-agents | grep registration
```

### Tickets não são processados

```bash
# Verificar consumer lag
kubectl exec -n kafka kafka-0 -- kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --group worker-agents
```

### Dependências não são resolvidas

```bash
kubectl logs -n neural-hive-execution -l app.kubernetes.io/name=worker-agents | grep dependency
```

## Roadmap

### Fase 2.6 - Executores Reais
- Integrar com Code Forge para BUILD executor
- Integrar com ArgoCD/Flux para DEPLOY executor
- Executar pipelines CI/CD reais (GitLab CI, Tekton)
- Validar artefatos com SBOM e Sigstore

### Fase 2.7 - Temporal Integration
- Implementar Temporal activities para workflows complexos
- Suportar execução distribuída de tarefas longas
- Integrar com compensation workflows

### Fase 3 - Edge Execution
- Suportar execução em edge nodes
- Implementar data locality para workloads edge
- Advanced retry strategies com circuit breakers

## Referências

- [Arquitetura de Orquestração](../../docs/observability/services/orquestracao.md)
- [Execution Ticket Schema](../../schemas/execution-ticket/execution-ticket.avsc)
- [Service Registry](../service-registry/README.md)
- [Execution Ticket Service](../execution-ticket-service/README.md)
