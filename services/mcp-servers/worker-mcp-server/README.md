# Worker MCP Server

Servidor MCP (Model Context Protocol) para execução distribuída e compensações saga no Neural Hive Mind.

## Descrição

O Worker MCP Server fornece ferramentas para:

- **execute_task**: Executar tarefas específicas (query, transform, validate, etc.)
- **check_dependencies**: Verificar dependências do workflow via Service Registry
- **monitor_progress**: Monitorar progresso de execução em tempo real
- **handle_compensation**: Executar compensações (saga pattern) para rollbacks
- **report_status**: Reportar status de execução ao Orchestrator

## Tecnologias

- **FastMCP**: Framework oficial MCP
- **httpx**: Cliente HTTP async
- **Service Registry**: Descoberta de serviços
- **Worker Agents**: Execução distribuída
- **Orchestrator**: Coordenação de workflows

## Instalação

```bash
pip install -e .
```

## Desenvolvimento

```bash
# Instalar dependências de desenvolvimento
pip install -e ".[dev]"

# Rodar testes
pytest tests/

# Formatar código
black src/ tests/

# Linting
ruff check src/ tests/
```

## Configuração

Variáveis de ambiente (prefixo `WORKER_MCP_`):

- `service_name`: Nome do serviço (padrão: worker-mcp-server)
- `service_version`: Versão (padrão: 1.0.0)
- `log_level`: Nível de log (padrão: INFO)
- `port`: Porta HTTP (padrão: 3013)
- `worker_agent_host`: Host do Worker Agents (padrão: worker-agents)
- `worker_agent_port`: Porta do Worker Agents (padrão: 8005)
- `orchestrator_host`: Host do Orchestrator (padrão: orchestrator-dynamic)
- `orchestrator_port`: Porta do Orchestrator (padrão: 8003)
- `service_registry_host`: Host do Service Registry (padrão: service-registry)
- `service_registry_port`: Porta do Service Registry (padrão: 8007)
- `execution_timeout`: Timeout de execução em segundos (padrão: 300)

## Docker

```bash
docker build -t worker-mcp-server .
docker run -p 3013:3013 worker-mcp-server
```

## Testes TDD

Este servidor segue TDD rigoroso:

1. **RED**: Testes escritos antes da implementação
2. **GREEN**: Código mínimo para passar nos testes
3. **REFACTOR**: Melhoria contínua da qualidade

```bash
# 24 testes cobrindo todas as ferramentas
pytest tests/test_worker_tools_tdd.py -v
```

## Integração

### Worker Agents

O servidor se comunica com o Worker Agents via HTTP para:

- **POST /api/v1/execute**: Executar tarefas
- **GET /api/v1/executions/{id}**: Consultar progresso
- **POST /api/v1/compensate**: Executar compensações

### Orchestrator

Status updates são enviados ao Orchestrator via:

- **POST /api/v1/status/report**: Reportar status de execução

### Service Registry

Verificação de dependências via:

- **GET /api/v1/services/{name}/health**: Health check de serviço

## Padrão Saga

As compensações seguem o padrão Saga para transações distribuídas:

1. **rollback**: Desfazer operação executada
2. **retry**: Tentar novamente com backoff exponencial
3. **compensating_action**: Executar ação compensatória
4. **manual_intervention**: Requerer intervenção humana

## Licença

MIT
