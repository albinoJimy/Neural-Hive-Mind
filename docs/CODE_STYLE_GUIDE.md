# Neural-Hive-Mind - Code Style Guide

**Versão:** 1.0.0
**Data:** 2026-04-01
**Status:** Ativo

---

## 1. Nomenclatura de Código

### 1.1 Classes
- **Padrão:** PascalCase
- **Exemplos:** `AnalystAgentGrpcClient`, `MongoDBClient`, `PheromoneClient`

### 1.2 Funções e Variáveis
- **Padrão:** snake_case
- **Exemplos:** `generate_insight`, `query_insights`, `health_check`

### 1.3 Constantes
- **Padrão:** UPPER_SNAKE_CASE
- **Exemplos:** `MAX_RETRIES`, `BASE_BACKOFF_SECONDS`

### 1.4 Clientes gRPC
- **Padrão:** `{Service}GrpcClient` (NUNCA `GRPCClient` em maiúsculas)
- **Exemplos:**
  - ✅ `AnalystAgentGrpcClient`
  - ✅ `QueenAgentGrpcClient`
  - ✅ `OptimizerGrpcClient`
  - ❌ `AnalystAgentGRPCClient`

### 1.5 Nomes de Arquivos
- **Python:** `kebab-case` para módulos, `snake_case` para scripts
- **Exemplos:** `analyst-agent-grpc-client.py`, `queen_agent_grpc_client.py`

---

## 2. APIs REST

### 2.1 Endpoint Padrão
- **Prefixo de versionamento:** `/api/v1/`
- **Formato:** kebab-case
- **Exemplos:**
  - ✅ `/api/v1/active-learning/metrics`
  - ✅ `/api/v1/insights/query`
  - ❌ `/api/v1/activeLearning/metrics`

### 2.2 Health Checks
- **Padrão:** `/health` para o endpoint principal
- **Sub-endpoints:**
  - `/health/live` - Liveness probe
  - `/health/ready` - Readiness probe
  - `/health/startup` - Startup probe
- **Resposta Padrão:**
  ```json
  {
    "status": "SERVING" | "NOT_SERVING",
    "timestamp": "2026-04-01T12:00:00Z",
    "details": {}
  }
  ```

---

## 3. Tópicos Kafka

### 3.1 Padrão de Nomes
- **Formato:** `{domain}.{event}`
- **Regra:** Usar pontos como separadores, kebab-case para palavras compostas
- **Exemplos:**
  - ✅ `cognitive.plans.created`
  - ✅ `sla.violations`
  - ✅ `ml.model-drift-detected`
  - ✅ `execution.tickets`
  - ✅ `approval-feedback`
  - ❌ `evolution.feedback.topic` (redundante)
  - ❌ `exploration-signals` (deveria ser `exploration.signals`)

### 3.2 Tópicos DLQ (Dead Letter Queue)
- **Prefixo:** `dlq.`
- **Exemplo:** `dlq.cognitive.plans.created`

### 3.3 Tópicos por Domínio

| Domínio | Prefixo | Exemplos |
|---------|---------|----------|
| Cognitive | `cognitive.` | `cognitive.plans.created`, `cognitive.decisions` |
| SLA | `sla.` | `sla.violations`, `sla.budgets`, `sla.freeze.events` |
| ML | `ml.` | `ml.model-drift-detected`, `ml.prediction` |
| Execution | `execution.` | `execution.tickets`, `execution.results` |
| Insights | `insights.` | `insights.generated`, `insights.query` |
| Optimization | `optimization.` | `optimization.applied`, `optimization.results` |
| Experiments | `experiments.` | `experiments.requests`, `experiments.results` |

---

## 4. Variáveis de Ambiente

### 4.1 Prefixos
- **Infraestrutura partilhada:** `NHM_{SERVICE}_`
- **Serviço específico:** `{SERVICE}_` (sem NHM prefix)
- **Exemplos:**
  - `NHM_KAFKA_BOOTSTRAP_SERVERS`
  - `NHM_MONGODB_URL`
  - `CONSENSUS_ENGINE_PORT`

### 4.2 Nomes de Variáveis
- **Padrão:** UPPER_SNAKE_CASE
- **Exemplos:**
  - `KAFKA_BOOTSTRAP_SERVERS`
  - `MONGODB_URL`
  - `REDIS_URL`
  - `TEMPORAL_HOST`

---

## 5. Logging

### 5.1 Biblioteca
- **Padrão:** `structlog` (obrigatório)
- ❌ `logging` padrão do Python

### 5.2 Formato de Logs
```python
logger.info(
    'event_name',
    field1=value1,
    field2=value2,
)
```

### 5.3 Níveis de Log
- `debug` - Informação detalhada para debugging
- `info` - Eventos normais de operação
- `warning` - Algo inesperado mas não crítico
- `error` - Erro que afeta uma operação
- `critical` - Erro que afeta o sistema inteiro

### 5.4 Contexto Obrigatório
- `correlation_id` - Para tracing distribuído
- `span_id` - Para tracing distribuído
- `service_name` - Nome do serviço
- `environment` - Ambiente (dev/staging/prod)

---

## 6. Type Hints

### 6.1 Obrigatoriedade
- **Funções públicas:** Obrigatório
- **Funções privadas:** Recomendado para funções críticas

### 6.2 Formato
```python
async def generate_insight(
    insight_type: str,
    title: str,
    summary: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    ...
```

### 6.3 Imports de Tipos
```python
from typing import Optional, Dict, List, Any, Tuple
```

---

## 7. Docstrings

### 7.1 Formato
- **Padrão:** Google Style
- **Obrigatório para:** Classes, métodos públicos, funções privadas críticas

### 7.2 Exemplo
```python
def generate_insight(
    insight_type: str,
    title: str,
    summary: str
) -> Optional[Dict[str, Any]]:
    """Solicitar geração de insight ao Analyst Agent.

    Args:
        insight_type: Tipo de insight (e.g., 'trend', 'anomaly')
        title: Título do insight
        summary: Resumo do insight

    Returns:
        Dicionário com insight gerado ou None em caso de erro

    Raises:
        ConnectionError: Quando não há conexão com o serviço
    """
    ...
```

---

## 8. Tratamento de Erros

### 8.1 Exceções Centralizadas
- **Base:** `NeuralHiveError`
- **Especializações:**
  - `ValidationError`
  - `ConfigurationError`
  - `ConnectionError`
  - `TimeoutError`

### 8.2 Retry com Backoff
- **Biblioteca:** `tenacity`
- **Padrão:**
```python
@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError))
)
async def call_external_service():
    ...
```

---

## 9. Docker

### 9.1 Imagens Base
- **Python:** `python:3.12-slim`
- **Observabilidade:** `ghcr.io/albinojimy/neural-hive-mind/python-observability-base:1.2.7`

### 9.2 Non-Root User
```dockerfile
RUN groupadd -r {service} && useradd -r -g {service} -u 1000 {service}
USER {service}
```

### 9.3 Health Check
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

---

## 10. Kubernetes

### 10.1 Namespaces
- **Padrão:** `nhm-{env}`
- **Exemplos:**
  - `nhm-dev`
  - `nhm-staging`
  - `nhm-prod`

### 10.2 Resource Limits
```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"
```

---

## 11. Git

### 11.1 Branches
- **Padrão:** `feat/TICKET-{ID}-{descricao}`
- **Exemplo:** `feat/NHM-123-adicionar-health-check`

### 11.2 Commits
- **Padrão:** Conventional Commits
- **Formato:** `{type}: {description}`
- **Tipos:**
  - `feat` - Nova funcionalidade
  - `fix` - Correção de bug
  - `refactor` - Refatoração
  - `docs` - Documentação
  - `test` - Testes
  - `chore` - Tarefas de manutenção

---

## 12. Pre-commit Hooks (Recomendado)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.0
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

---

**Changelog:**
- 2026-04-01 - Versão inicial (v1.0.0)
