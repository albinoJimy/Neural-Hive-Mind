# Guia de Tool Adapters - MCP Tool Catalog

## Visão Geral

Os **Tool Adapters** são componentes responsáveis pela execução real das ferramentas MCP. Cada adapter implementa a interface `BaseToolAdapter` e fornece um método específico de integração com ferramentas externas.

## Arquitetura

```
ToolExecutor
    ├── CLIAdapter (integration_type: CLI)
    ├── RESTAdapter (integration_type: REST_API)
    ├── ContainerAdapter (integration_type: CONTAINER)
    ├── GRPCAdapter (integration_type: GRPC) [futuro]
    └── LibraryAdapter (integration_type: LIBRARY) [futuro]
```

## Adapters Implementados

### 1. CLI Adapter

**Arquivo**: `src/adapters/cli_adapter.py`

**Propósito**: Executa ferramentas via linha de comando (subprocess).

**Características**:
- Timeout configurável (padrão: 300s)
- Construção automática de comandos via parâmetros
- Suporte a environment variables e working directory
- Validação de disponibilidade via `which` ou `--version`
- Tratamento de erros com retry logic

**Exemplo de Uso**:
```python
adapter = CLIAdapter(timeout_seconds=300)

result = await adapter.execute(
    tool_id="trivy-001",
    tool_name="trivy",
    command="trivy image",
    parameters={
        "severity": "HIGH",
        "format": "json",
        "_target": "nginx:latest"  # _ prefix = positional arg
    },
    context={
        "working_dir": "/app",
        "env_vars": {"TRIVY_CACHE_DIR": "/tmp/trivy"}
    }
)

print(f"Success: {result.success}")
print(f"Output: {result.output}")
print(f"Time: {result.execution_time_ms}ms")
```

**Ferramentas Suportadas**:
- **ANALYSIS**: Trivy, Semgrep, ESLint, Pylint, Bandit, Checkov, etc.
- **TRANSFORMATION**: Black, Prettier, Terraform fmt, etc.
- **VALIDATION**: Pytest, Jest (para testes locais)

---

### 2. REST Adapter

**Arquivo**: `src/adapters/rest_adapter.py`

**Propósito**: Executa ferramentas via REST API (aiohttp).

**Características**:
- Timeout configurável (padrão: 60s)
- Retry com exponential backoff (max: 3 retries)
- Suporte a autenticação via Bearer token
- Separação de query params e body
- Headers customizados

**Exemplo de Uso**:
```python
adapter = RESTAdapter(timeout_seconds=60, max_retries=3)

result = await adapter.execute(
    tool_id="sonarqube-001",
    tool_name="sonarqube",
    command="https://sonarqube.example.com/api/measures/component",
    parameters={
        "query": {
            "component": "my-project",
            "metricKeys": "bugs,vulnerabilities"
        },
        "body": {}
    },
    context={
        "http_method": "GET",
        "auth_token": "squ_abc123...",
        "headers": {
            "Accept": "application/json"
        }
    }
)

print(f"Status: {result.exit_code}")  # HTTP status code
print(f"Response: {result.output}")
```

**Ferramentas Suportadas**:
- **ANALYSIS**: SonarQube, Snyk, Checkmarx, Veracode, Fortify
- **INTEGRATION**: GitHub API, GitLab API, Zapier webhooks

---

### 3. Container Adapter

**Arquivo**: `src/adapters/container_adapter.py`

**Propósito**: Executa ferramentas via Docker containers.

**Características**:
- Timeout configurável (padrão: 600s)
- Montagem de volumes
- Environment variables
- Network mode configurável
- Cleanup automático (--rm)
- Graceful termination com `docker kill` em caso de timeout

**Exemplo de Uso**:
```python
adapter = ContainerAdapter(timeout_seconds=600)

result = await adapter.execute(
    tool_id="trivy-container-001",
    tool_name="trivy",
    command="aquasec/trivy:latest",  # Docker image
    parameters={
        "args": ["image", "--severity", "HIGH", "nginx:latest"],
        "volumes": [
            "/var/run/docker.sock:/var/run/docker.sock",
            "/tmp/trivy:/root/.cache"
        ],
        "env": {
            "TRIVY_CACHE_DIR": "/root/.cache"
        },
        "workdir": "/app"
    },
    context={
        "network": "bridge",
        "tool_id": "trivy-container-001"
    }
)

print(f"Container output: {result.output}")
```

**Ferramentas Suportadas**:
- **ANALYSIS**: Trivy (container), Checkov (container), OWASP ZAP
- **GENERATION**: Qualquer ferramenta empacotada em container
- **VALIDATION**: Ferramentas de teste containerizadas

---

## ToolExecutor

**Arquivo**: `src/services/tool_executor.py`

**Propósito**: Orquestra a execução de ferramentas selecionando o adapter apropriado baseado no `integration_type`.

**Características**:
- Seleção automática de adapter
- Validação de disponibilidade antes da execução
- Métricas Prometheus integradas
- Suporte a execução em batch (paralela)
- Tratamento de erros robusto

**Exemplo de Uso Individual**:
```python
executor = ToolExecutor()

# Tool descriptor
tool = ToolDescriptor(
    tool_id="pytest-001",
    tool_name="pytest",
    integration_type=IntegrationType.CLI,
    # ... outros campos
)

# Executar
result = await executor.execute_tool(
    tool=tool,
    execution_params={
        "verbose": True,
        "_path": "tests/"
    },
    context={
        "working_dir": "/app/project"
    }
)
```

**Exemplo de Uso Batch**:
```python
executor = ToolExecutor()

# Múltiplas ferramentas
tools = [trivy_tool, pytest_tool, black_tool]

# Executar em paralelo
results = await executor.execute_tool_batch(
    tools=tools,
    execution_params={...},
    context={...}
)

# Resultados mapeados por tool_id
for tool_id, result in results.items():
    print(f"{tool_id}: {'✓' if result.success else '✗'}")
```

---

## ExecutionResult

**Modelo**: `src/adapters/base_adapter.py`

**Estrutura**:
```python
@dataclass
class ExecutionResult:
    success: bool                    # True se execução bem-sucedida
    output: str                      # Stdout/response body
    error: Optional[str]             # Stderr/mensagem de erro
    execution_time_ms: float         # Tempo de execução em ms
    exit_code: Optional[int]         # Exit code ou HTTP status
    metadata: Dict[str, Any]         # Metadados adicionais
```

---

## Métricas Prometheus

Os adapters registram automaticamente as seguintes métricas via `ToolExecutor`:

**Counters**:
- `mcp_tool_executions_total{tool_id, category, status}` - Total de execuções

**Histograms**:
- `mcp_tool_execution_duration_seconds{tool_id}` - Duração das execuções

**Exemplo de Query**:
```promql
# Taxa de sucesso por ferramenta
sum(rate(mcp_tool_executions_total{status="success"}[5m])) by (tool_id) /
sum(rate(mcp_tool_executions_total[5m])) by (tool_id)

# Tempo médio de execução
histogram_quantile(0.95, rate(mcp_tool_execution_duration_seconds_bucket[5m]))
```

---

## Logs Estruturados

Todos os adapters utilizam `structlog` para logs estruturados:

**Exemplo de Log**:
```json
{
  "event": "tool_execution_completed",
  "tool_id": "trivy-001",
  "tool_name": "trivy",
  "command": "trivy image --severity HIGH nginx:latest",
  "success": true,
  "execution_time_ms": 5234.56,
  "exit_code": 0,
  "timestamp": "2025-10-04T12:34:56Z"
}
```

---

## Tratamento de Erros

### 1. Timeout
- CLI/Container: Processo é terminado (`kill`)
- REST: Request é abortado

### 2. Retry Logic
- REST Adapter: 3 tentativas com exponential backoff (2^n segundos)
- CLI/Container: Sem retry automático (deve ser tratado em nível superior)

### 3. Validação de Disponibilidade
- CLI: `which <tool>` ou `<tool> --version`
- REST: Health check endpoint (se configurado)
- Container: `docker version`

---

## Integração com Genetic Selector

O fluxo completo de seleção → execução:

```
1. GeneticToolSelector.select_tools()
   ↓
2. Retorna ToolSelectionResponse com selected_tools
   ↓
3. Code Forge recebe ferramentas selecionadas
   ↓
4. ToolExecutor.execute_tool_batch(selected_tools)
   ↓
5. Cada adapter executa sua ferramenta
   ↓
6. Resultados agregados e feedback enviado ao MCP
```

---

## Próximos Passos

### Adapters Futuros (Fase 3)

1. **GRPCAdapter** (integration_type: GRPC)
   - Execução via gRPC calls
   - Suporte a streaming
   - Exemplos: Serviços internos do Neural Hive-Mind

2. **LibraryAdapter** (integration_type: LIBRARY)
   - Import dinâmico de bibliotecas Python
   - Execução in-process
   - Exemplos: NumPy, Pandas, custom libs

### Melhorias Planejadas

1. **Caching de Execuções**
   - Hash de (tool_id + parameters + context)
   - TTL configurável por ferramenta
   - Invalidação via feedback negativo

2. **Rate Limiting**
   - Limitar execuções paralelas por ferramenta
   - Queue de execuções com prioridade

3. **Sandboxing**
   - CLI Adapter: execução em container isolado
   - Resource limits (CPU, memory)

---

## Referências

- **Base Adapter**: `src/adapters/base_adapter.py`
- **CLI Adapter**: `src/adapters/cli_adapter.py`
- **REST Adapter**: `src/adapters/rest_adapter.py`
- **Container Adapter**: `src/adapters/container_adapter.py`
- **Tool Executor**: `src/services/tool_executor.py`
- **Tool Descriptor**: `src/models/tool_descriptor.py`

---

**Autor**: Neural Hive-Mind Development Team
**Data**: 2025-10-04
**Versão**: 1.0.0
