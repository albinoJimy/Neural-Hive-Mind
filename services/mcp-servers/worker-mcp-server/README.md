# Worker MCP Server

Servidor MCP (Model Context Protocol) para execução distribuída e compensações saga no Neural Hive Mind.

## Descrição

O Worker MCP Server fornece uma camada de abstração sobre o Worker Agents, permitindo que orquestradores e outros serviços coordenem execuções distribuídas através do protocolo MCP da Anthropic. Implementa o padrão Saga para compensações automáticas em caso de falhas.

## Funcionalidades

- **execute_task**: Executar tarefas específicas (query, transform, validate, code_generation, data_processing)
- **check_dependencies**: Verificar dependências do workflow via Service Registry
- **monitor_progress**: Monitorar progresso de execução em tempo real
- **handle_compensation**: Executar compensações (saga pattern) para rollbacks distribuídos
- **report_status**: Reportar status de execução ao Orchestrator

## Arquitetura

```
                    ┌─────────────────────────────────────┐
                    │         Orchestrator Dynamic         │
                    │        (Temporal Workflows)          │
                    └─────────────────┬───────────────────┘
                                      │
                                      │ MCP Protocol
                                      │
                    ┌─────────────────▼───────────────────┐
                    │         Worker MCP Server           │
                    │          (Porta 3013)                │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │           Worker Agents              │
                    │          (Porta 8005)                │
                    └─────────────────────────────────────┘
```

## Tecnologias

- **FastMCP**: Framework oficial MCP da Anthropic
- **FastAPI**: Servidor HTTP com suporte a async/await
- **httpx**: Cliente HTTP async
- **structlog**: Logging estruturado
- **pydantic**: Validação de dados e configurações

## Instalação

### Requisitos

- Python 3.10+
- Poetry ou pip
- Acesso ao Worker Agents (porta 8005)
- Acesso ao Service Registry (porta 8007)
- Acesso ao Orchestrator Dynamic (porta 8003)

### Via pip

```bash
cd services/mcp-servers/worker-mcp-server
pip install -e .
```

### Via Poetry

```bash
cd services/mcp-servers/worker-mcp-server
poetry install
```

### Dependências de Desenvolvimento

```bash
pip install -e ".[dev]"
```

Isso instala:
- pytest e pytest-asyncio para testes
- pytest-cov para cobertura de código
- ruff para linting
- black para formatação
- mypy para verificação de tipos

## Configuração

### Variáveis de Ambiente

Todas as variáveis usam o prefixo `WORKER_MCP_`:

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `SERVICE_NAME` | Nome do serviço | worker-mcp-server |
| `SERVICE_VERSION` | Versão do serviço | 1.0.0 |
| `LOG_LEVEL` | Nível de log (DEBUG, INFO, WARNING, ERROR) | INFO |
| `PORT` | Porta HTTP | 3013 |
| `WORKER_AGENT_HOST` | Host do Worker Agents | worker-agents |
| `WORKER_AGENT_PORT` | Porta do Worker Agents | 8005 |
| `ORCHESTRATOR_HOST` | Host do Orchestrator | orchestrator-dynamic |
| `ORCHESTRATOR_PORT` | Porta do Orchestrator | 8003 |
| `SERVICE_REGISTRY_HOST` | Host do Service Registry | service-registry |
| `SERVICE_REGISTRY_PORT` | Porta do Service Registry | 8007 |
| `EXECUTION_TIMEOUT` | Timeout de execução (segundos) | 300 |

### Exemplo de Arquivo .env

```bash
WORKER_MCP_SERVICE_NAME=worker-mcp-server
WORKER_MCP_SERVICE_VERSION=1.0.0
WORKER_MCP_LOG_LEVEL=INFO
WORKER_MCP_PORT=3013

WORKER_MCP_WORKER_AGENT_HOST=worker-agents
WORKER_MCP_WORKER_AGENT_PORT=8005

WORKER_MCP_ORCHESTRATOR_HOST=orchestrator-dynamic
WORKER_MCP_ORCHESTRATOR_PORT=8003

WORKER_MCP_SERVICE_REGISTRY_HOST=service-registry
WORKER_MCP_SERVICE_REGISTRY_PORT=8007

WORKER_MCP_EXECUTION_TIMEOUT=300
```

## Uso

### Executar Localmente

```bash
python -m src.main
```

O servidor estará disponível em `http://localhost:3013`

### Endpoints HTTP

- `GET /health` - Health check do servidor
- `GET /ready` - Verifica se o servidor está pronto para receber requisições
- `POST /mcp` - Endpoint JSON-RPC 2.0 para protocolo MCP

## API das Ferramentas

### 1. execute_task

Executa uma tarefa específica via Worker Agent.

**Parâmetros:**
- `task_id` (str, obrigatório): ID da tarefa
- `workflow_id` (str, obrigatório): ID do workflow
- `executor_type` (str, obrigatório): Tipo de executor
  - Valores válidos: `query`, `transform`, `validate`, `code_generation`, `data_processing`
- `parameters` (dict, opcional): Parâmetros da tarefa

**Retorno:**
```python
{
    "execution_id": "exec-123",
    "status": "pending",
    "task_id": "task-456",
    "workflow_id": "workflow-789"
}
```

**Exemplo de Uso:**
```python
result = await execute_task(
    task_id="task-456",
    workflow_id="workflow-789",
    executor_type="query",
    parameters={"query": "SELECT * FROM users"}
)
```

### 2. check_dependencies

Verifica se dependências do workflow estão satisfeitas via Service Registry.

**Parâmetros:**
- `workflow_id` (str, obrigatório): ID do workflow
- `dependencies` (list[str], obrigatório): Lista de dependências

**Retorno:**
```python
{
    "satisfied": true,
    "missing": [],
    "workflow_id": "workflow-789"
}
```

**Exemplo de Uso:**
```python
result = await check_dependencies(
    workflow_id="workflow-789",
    dependencies=["database", "cache", "api-gateway"]
)
```

### 3. monitor_progress

Monitora o progresso de uma execução de tarefa.

**Parâmetros:**
- `execution_id` (str, obrigatório): ID da execução

**Retorno:**
```python
{
    "execution_id": "exec-123",
    "status": "in_progress",
    "progress_percent": 45,
    "logs": ["Step 1: Query execution started", "Step 2: Fetching data"]
}
```

**Exemplo de Uso:**
```python
progress = await monitor_progress(execution_id="exec-123")
```

### 4. handle_compensation

Executa compensação (transação saga) para execução falhada.

**Parâmetros:**
- `execution_id` (str, obrigatório): ID da execução falhada
- `original_task_id` (str, obrigatório): ID da tarefa original
- `compensation_type` (str, obrigatório): Tipo de compensação
  - Valores válidos: `rollback`, `retry`, `compensating_action`, `manual_intervention`

**Retorno:**
```python
{
    "success": true,
    "compensation_id": "comp-456",
    "execution_id": "exec-123",
    "status": "completed"
}
```

**Exemplo de Uso:**
```python
result = await handle_compensation(
    execution_id="exec-123",
    original_task_id="task-456",
    compensation_type="rollback"
)
```

### 5. report_status

Reporta status de execução ao Orchestrator.

**Parâmetros:**
- `execution_id` (str, obrigatório): ID da execução
- `task_id` (str, obrigatório): ID da tarefa
- `workflow_id` (str, obrigatório): ID do workflow
- `status` (str, obrigatório): Status da execução
  - Valores válidos: `pending`, `in_progress`, `completed`, `failed`, `cancelled`
- `output` (dict, opcional): Output da execução

**Retorno:**
```python
{
    "success": true,
    "execution_id": "exec-123"
}
```

**Exemplo de Uso:**
```python
result = await report_status(
    execution_id="exec-123",
    task_id="task-456",
    workflow_id="workflow-789",
    status="completed",
    output={"result": "Dados processados com sucesso"}
)
```

## Integração com Outros Serviços

### Worker Agents

O servidor se comunica com o Worker Agents via HTTP:

- `POST /api/v1/execute` - Executar tarefas
- `GET /api/v1/executions/{id}` - Consultar progresso
- `POST /api/v1/compensate` - Executar compensações

### Orchestrator Dynamic

Status updates são enviados ao Orchestrator via:

- `POST /api/v1/status/report` - Reportar status de execução

### Service Registry

Verificação de dependências via:

- `GET /api/v1/services/{name}/health` - Health check de serviço

## Padrão Saga para Compensações

As compensações seguem o padrão Saga para transações distribuídas:

1. **rollback**: Desfazer operação executada
   - Usado para reverter mudanças de estado
   - Exemplo: Deletar registros criados

2. **retry**: Tentar novamente com backoff exponencial
   - Usado para falhas transitórias
   - Exemplo: Nova tentativa de chamada de API

3. **compensating_action**: Executar ação compensatória
   - Usado quando rollback direto não é possível
   - Exemplo: Enviar notificação de cancelamento

4. **manual_intervention**: Requerer intervenção humana
   - Usado para casos não recuperáveis automaticamente
   - Exemplo: Discrepância de dados que requer análise

## Desenvolvimento

### Configurar Ambiente de Desenvolvimento

```bash
# Clonar o repositório
git clone https://github.com/albinoJimy/Neural-Hive-Mind.git
cd Neural-Hive-Mind/services/mcp-servers/worker-mcp-server

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Instalar dependências
pip install -e ".[dev]"

# Configurar variáveis de ambiente
cp .env.test .env
```

### Executar Testes

```bash
# Todos os testes
pytest tests/ -v

# Testes com cobertura
pytest tests/ --cov=src --cov-report=html

# Testes específicos
pytest tests/test_worker_tools_tdd.py -v
pytest tests/test_integration.py -v
```

### Linting e Formatação

```bash
# Verificar problemas de linting
ruff check src/ tests/

# Formatar código automaticamente
black src/ tests/

# Verificar tipos
mypy src/
```

### Estrutura do Projeto

```
worker-mcp-server/
├── src/
│   └── worker_mcp_server/
│       ├── __init__.py
│       ├── main.py           # Entry point
│       ├── server.py         # Configuração do servidor MCP
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py   # Configurações Pydantic
│       └── tools/
│           ├── __init__.py
│           └── worker_tools.py  # Implementação das ferramentas
├── tests/
│   ├── conftest.py           # Fixtures compartilhadas
│   ├── test_worker_tools_tdd.py  # Testes TDD das ferramentas
│   └── test_integration.py   # Testes de integração
├── helm/
│   └── worker-mcp-server/    # Chart Helm para Kubernetes
├── Dockerfile                # Imagem Docker
├── requirements.txt          # Dependências
├── pyproject.toml           # Configuração do projeto
└── README.md                # Este arquivo
```

## Docker

### Build da Imagem

```bash
# A partir do diretório services/mcp-servers/
docker build -f worker-mcp-server/Dockerfile -t worker-mcp-server:1.0.0 .
```

### Executar Container

```bash
docker run -d \
  --name worker-mcp-server \
  -p 3013:3013 \
  -e WORKER_MCP_WORKER_AGENT_HOST=worker-agents \
  -e WORKER_MCP_SERVICE_REGISTRY_HOST=service-registry \
  worker-mcp-server:1.0.0
```

## Kubernetes (Helm)

### Instalar Chart

```bash
helm install worker-mcp-server ./helm/worker-mcp-server \
  --namespace neural-hive-mind \
  --values ./helm/worker-mcp-server/values.yaml
```

### Upgrade

```bash
helm upgrade worker-mcp-server ./helm/worker-mcp-server \
  --namespace neural-hive-mind \
  --values ./helm/worker-mcp-server/values.yaml
```

## Testes TDD

Este servidor segue TDD rigoroso (Red-Green-Refactor):

1. **RED**: Testes escritos antes da implementação
2. **GREEN**: Código mínimo para passar nos testes
3. **REFACTOR**: Melhoria contínua da qualidade

```bash
# 24+ testes cobrindo todas as ferramentas
pytest tests/test_worker_tools_tdd.py -v
```

Cobertura de testes:
- 5 ferramentas MCP com testes unitários
- Testes de integração E2E
- Mocks para isolar dependências externas

## Monitoramento e Observabilidade

### Health Checks

- `GET /health` - Verifica saúde do serviço
- `GET /ready` - Verifica se o serviço está pronto

### Logs

O servidor usa `structlog` para logs estruturados em formato JSON:

```json
{
  "event": "execute_task_called",
  "task_id": "task-456",
  "workflow_id": "workflow-789",
  "executor_type": "query",
  "level": "info",
  "timestamp": "2026-04-04T10:30:00Z"
}
```

### Métricas (Prometheus)

Métricas disponíveis em `/metrics`:
- `mcp_requests_total` - Total de requisições MCP
- `mcp_request_duration_seconds` - Duração das requisições
- `worker_executions_total` - Total de execuções de tarefas
- `worker_compensations_total` - Total de compensações

## Troubleshooting

### Erro: Connection refused ao Worker Agent

**Problema:** Servidor não consegue conectar ao Worker Agent.

**Solução:**
1. Verificar se Worker Agent está rodando: `curl http://worker-agents:8005/health`
2. Verificar variáveis de ambiente `WORKER_MCP_WORKER_AGENT_HOST` e `WORKER_MCP_WORKER_AGENT_PORT`
3. Verificar conectividade de rede

### Erro: Timeout na execução

**Problema:** Tarefa demora mais que o timeout configurado.

**Solução:**
1. Aumentar `WORKER_MCP_EXECUTION_TIMEOUT`
2. Verificar se a tarefa está bloqueada
3. Monitorar progresso com `monitor_progress`

### Erro: Compensation failed

**Problema:** Compensação não pode ser executada.

**Solução:**
1. Verificar logs detalhados do Worker Agent
2. Tentar `compensation_type=retry` antes de `rollback`
3. Para casos críticos, usar `compensation_type=manual_intervention`

## Licença

MIT

## Contribuindo

Este projeto faz parte do Neural Hive Mind. Para contribuir:

1. Fork o repositório
2. Crie uma branch: `git checkout -b feat/minha-feature`
3. Faça commit das mudanças: `git commit -am 'Add nova feature'`
4. Push para a branch: `git push origin feat/minha-feature`
5. Abra um Pull Request

## Suporte

Para issues e perguntas:
- GitHub Issues: https://github.com/albinoJimy/Neural-Hive-Mind/issues
- Documentação Neural Hive Mind: `/docs`
