# Code Forge

Plataforma de geração automática de código e artefatos IaC.

## 🔧 Integração MCP Tool Catalog

O Code Forge integra-se com o MCP Tool Catalog para seleção dinâmica de ferramentas de geração e validação.

### Fluxo de Integração

1. **Template Selection (Subpipeline 1)**
   - Calcula `complexity_score` baseado em tarefas, dependências e risk_band
   - Envia `ToolSelectionRequest` para MCP Tool Catalog
   - Recebe ferramentas selecionadas via algoritmo genético
   - Mapeia ferramentas para `generation_method` (LLM, HYBRID, TEMPLATE, HEURISTIC)

2. **Code Composition (Subpipeline 2)**
   - Usa `generation_method` do contexto para decidir estratégia
   - Armazena `mcp_selection_id` e `mcp_tools_used` nos metadados do artefato

3. **Validation (Subpipeline 3)**
   - Executa apenas ferramentas VALIDATION selecionadas pelo MCP
   - Envia feedback de execução para MCP Tool Catalog

### Configuração

```yaml
MCP_TOOL_CATALOG_HOST: mcp-tool-catalog
MCP_TOOL_CATALOG_PORT: 8080
```

### Graceful Degradation

Se MCP Tool Catalog estiver indisponível:
- Template Selector usa fallback para templates estáticos
- Code Composer usa geração baseada em templates
- Validator executa todas as ferramentas configuradas

### Métricas

- `code_forge_mcp_selection_requests_total{status}` - Total de requisições MCP
- `code_forge_mcp_selection_duration_seconds` - Duração de seleção
- `code_forge_mcp_tools_selected_total{category}` - Ferramentas selecionadas
- `code_forge_mcp_feedback_sent_total{status}` - Feedback enviado

## LLM Configuration

Code Forge supports multiple LLM providers for code generation:

### Supported Providers

| Provider | Models | API Key Format | Notes |
|----------|--------|----------------|-------|
| **OpenAI** | `gpt-4`, `gpt-3.5-turbo`, `gpt-4-turbo` | `sk-proj-...` | Official SDK, streaming support |
| **Anthropic** | `claude-3-opus-20240229`, `claude-3-sonnet-20240229` | `sk-ant-...` | Official SDK, streaming support |
| **Local (Ollama)** | `codellama:7b`, `llama2`, `mistral` | N/A | No API key required |

### Configuration

Set environment variables:

```bash
LLM_PROVIDER=openai  # or anthropic, local
LLM_API_KEY=sk-proj-your-key-here
LLM_MODEL=gpt-4
LLM_ENABLED=true
```

### Retry Logic

- **Automatic retry:** 3 attempts with exponential backoff (2s, 4s, 8s)
- **Rate limits:** Automatically retried
- **Timeout:** 60 seconds per request
- **Fallback:** If LLM fails, pipeline falls back to HEURISTIC generation

### Streaming Mode

Enable streaming for progressive code generation:

```python
result = await llm_client.generate_code(
    prompt="Create a FastAPI service",
    constraints={"language": "python"},
    stream=True  # Enable streaming
)
```

### Cost Optimization

- Use `gpt-3.5-turbo` for simple tasks (10x cheaper than GPT-4)
- Use `claude-3-sonnet` for balanced cost/quality
- Use local Ollama for development/testing (free)

### Troubleshooting

**Error: `openai_api_key_missing`**
- Set `LLM_API_KEY` environment variable

**Error: `openai_sdk_not_installed`**
- Run: `pip install openai anthropic`

**Error: `openai_rate_limit`**
- Wait for retry (automatic)
- Check API quota at https://platform.openai.com/usage
