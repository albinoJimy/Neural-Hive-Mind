# MCP Tool Catalog - Guia do Desenvolvedor

## Introdução

Este guia explica como integrar o MCP Tool Catalog em seus serviços.

## Instalação

### Via REST API (Recomendado)

```python
from src.clients.mcp_tool_catalog_client import MCPToolCatalogClient

client = MCPToolCatalogClient("http://mcp-tool-catalog:8080")
```

### Via Kafka

```python
from src.clients.kafka_producer import KafkaProducer
from src.clients.kafka_consumer import KafkaConsumer

producer = KafkaProducer(bootstrap_servers="kafka:9092")
consumer = KafkaConsumer(topic="mcp.tool.selection.responses")
```

## Casos de Uso

### 1. Seleção de Ferramentas para Pipeline CI/CD

```python
response = await client.request_tool_selection(
    ticket_id="ci-001",
    artifact_type="CODE",
    language="python",
    complexity_score=0.7,
    required_categories=["ANALYSIS", "VALIDATION", "AUTOMATION"],
    constraints={
        "max_execution_time_ms": 300000,  # 5 min
        "max_cost_score": 0.5,  # Preferir open-source
        "min_reputation_score": 0.8
    },
    context={
        "framework": "fastapi",
        "test_framework": "pytest",
        "ci_platform": "github-actions"
    }
)

# Usar ferramentas selecionadas
for tool in response.selected_tools:
    print(f"Use {tool.tool_name} for {tool.category}")
```

### 2. Validação Dinâmica de Artefatos

```python
# Selecionar ferramentas de validação
response = await client.request_tool_selection(
    required_categories=["VALIDATION"],
    preferred_tools=["pytest-001", "checkov-001"]
)

# Executar validações
from src.services.tool_executor import ToolExecutor

executor = ToolExecutor()
for selected_tool in response.selected_tools:
    tool = await client.get_tool(selected_tool.tool_id)
    result = await executor.execute_tool(
        tool=tool,
        execution_params={"artifact_path": "/path/to/artifact"},
        context={"working_dir": "/tmp"}
    )

    # Enviar feedback
    await client.send_tool_feedback(
        tool_id=tool.tool_id,
        success=result.success,
        execution_time_ms=result.execution_time_ms
    )
```

### 3. Geração de Código com IA

```python
response = await client.request_tool_selection(
    required_categories=["GENERATION"],
    constraints={"max_cost_score": 0.9},  # Permitir ferramentas pagas
    preferred_tools=["github-copilot-001", "openai-codex-001"]
)

# Usar ferramenta selecionada
generation_tool = response.selected_tools[0]
if generation_tool.tool_name == "GitHub Copilot":
    # Usar Copilot API
    pass
elif generation_tool.tool_name == "OpenAI Codex":
    # Usar OpenAI API
    pass
```

## Boas Práticas

### 1. Sempre Enviar Feedback

```python
# ✅ BOM
result = await executor.execute_tool(tool, params, context)
await client.send_tool_feedback(tool.tool_id, result.success, result.execution_time_ms)

# ❌ RUIM
result = await executor.execute_tool(tool, params, context)
# Sem feedback - reputation score não é atualizado
```

### 2. Usar Cache Inteligentemente

```python
# Mesmo request_id = cache hit
response1 = await client.request_tool_selection(request_id="req-001", ...)
response2 = await client.request_tool_selection(request_id="req-001", ...)  # Cache hit

# Diferente request_id = cache miss
response3 = await client.request_tool_selection(request_id="req-002", ...)  # Cache miss
```

### 3. Tratar Timeouts do Algoritmo Genético

```python
response = await client.request_tool_selection(...)

if response.selection_method == "HEURISTIC":
    # GA timeout - ferramentas selecionadas por heurística
    logger.warning("GA timeout, using heuristic selection")
elif response.selection_method == "GENETIC_ALGORITHM":
    # GA convergiu
    logger.info(f"GA converged in {response.generations_evolved} generations")
```

### 4. Validar Disponibilidade de Ferramentas

```python
for tool in response.selected_tools:
    tool_descriptor = await client.get_tool(tool.tool_id)

    if not tool_descriptor.is_healthy:
        logger.warning(f"Tool {tool.tool_name} is unhealthy, skipping")
        continue

    # Executar ferramenta
    result = await executor.execute_tool(tool_descriptor, ...)
```

## Troubleshooting

### Problema: GA sempre timeout

**Solução**: Reduzir `GA_MAX_GENERATIONS` ou aumentar `GA_TIMEOUT_SECONDS`.

```bash
kubectl set env deployment/mcp-tool-catalog GA_MAX_GENERATIONS=50
kubectl set env deployment/mcp-tool-catalog GA_TIMEOUT_SECONDS=60
```

### Problema: Cache hit rate baixo

**Solução**: Aumentar TTL do cache Redis.

```bash
kubectl set env deployment/mcp-tool-catalog REDIS_CACHE_TTL_SECONDS=7200  # 2h
```

### Problema: Ferramentas unhealthy

**Solução**: Verificar disponibilidade de adapters (CLI tools instalados, Docker disponível, APIs acessíveis).

```bash
kubectl exec -it mcp-tool-catalog-xxx -- which trivy
kubectl exec -it mcp-tool-catalog-xxx -- docker version
```

## Referências

- [MCP Tool Catalog Complete](MCP_TOOL_CATALOG_COMPLETE.md)
- [Tool Adapters Guide](../services/mcp-tool-catalog/TOOL_ADAPTERS_GUIDE.md)
- [API Documentation](../services/mcp-tool-catalog/README.md#api-rest)
