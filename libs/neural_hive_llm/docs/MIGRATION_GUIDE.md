# Guia de Migração para neural_hive_llm

Este guia ajuda a migrar serviços existentes que usam clientes LLM próprios para a biblioteca centralizada `neural_hive_llm`.

## Visão Geral

A biblioteca `neural_hive_llm` fornece:
- Interface unificada para OpenAI, Anthropic e Local (Ollama)
- Retry automático com exponential backoff
- Token counting e estimativa de custos
- Circuit breaker integrado
- Observabilidade completa (OpenTelemetry, Prometheus, structlog)
- Type safety total

## Migração do code-forge

### Antes (implementação própria)

```python
from src.clients.llm_client import LLMClient, LLMProvider

client = LLMClient(
    provider=LLMProvider.OPENAI,
    api_key="sk-...",
    model_name="gpt-4",
)
await client.start()

result = await client.generate_code(
    prompt="Create a FastAPI service",
    constraints={"language": "python", "framework": "fastapi"},
    temperature=0.2,
)

await client.stop()
```

### Depois (usando neural_hive_llm)

A migração mantém a mesma API através de um wrapper:

```python
# O código existente continua funcionando!
from src.clients.llm_client import LLMClient, LLMProvider

client = LLMClient(
    provider=LLMProvider.OPENAI,
    api_key="sk-...",
    model_name="gpt-4",
)
await client.start()

result = await client.generate_code(
    prompt="Create a FastAPI service",
    constraints={"language": "python", "framework": "fastapi"},
    temperature=0.2,
)

await client.stop()
```

### Mudanças internas

- `src/clients/llm_client.py` agora re-exporta de `llm_client_wrapper.py`
- `llm_client_wrapper.py` usa `neural_hive_llm.LLMClient` internamente
- A API pública `generate_code()` é mantida para compatibilidade

### Passos para migrar

1. **Adicionar dependência:**

```bash
# Em requirements.txt ou pyproject.toml
../../libs/neural_hive_llm
```

2. **Atualizar imports (se necessário):**

```python
# Antigo (ainda funciona)
from src.clients.llm_client import LLMClient

# Novo (uso direto da biblioteca)
from neural_hive_llm import LLMClient, LLMProvider
```

3. **Testar regressão:**

```bash
cd services/code-forge
pytest tests/unit/test_clients/test_llm_client_migration.py
```

## Migração do architect-agent

### Antes (implementação própria)

```python
from src.planners.llm_client import LLMClient

client = LLMClient()
response = await client.generate(
    prompt="Design a microservice architecture",
    system_prompt="You are an expert architect."
)
```

### Depois (usando neural_hive_llm)

```python
# A API permanece a mesma
from src.planners.llm_client import LLMClient

client = LLMClient()
response = await client.generate(
    prompt="Design a microservice architecture",
    system_prompt="You are an expert architect."
)
```

### Mudanças internas

- `src/planners/llm_client.py` agora re-exporta de `llm_client_wrapper.py`
- `llm_client_wrapper.py` usa `neural_hive_llm.LLMClient` internamente
- O método `_get_default_response()` é mantido como fallback

## API neural_hive_llm

### Inicialização

```python
from neural_hive_llm import LLMClient, LLMProvider

# Via parâmetros diretos
client = LLMClient(
    provider=LLMProvider.OPENAI,
    api_key="sk-...",
    model="gpt-4",
)
await client.start()

# Via settings (variáveis de ambiente)
from neural_hive_llm import get_llm_settings

settings = get_llm_settings(provider=LLMProvider.OPENAI, api_key="sk-...")
client = LLMClient(settings=settings)
await client.start()
```

### Geração simples

```python
response = await client.generate(
    prompt="Explique microserviços",
    system_prompt="Você é um arquiteto sênior",
    temperature=0.7,
    max_tokens=1000,
)

print(response.text)              # Texto gerado
print(response.total_tokens)      # Contagem de tokens
print(response.estimated_cost_usd)  # Custo estimado
print(response.latency_ms)        # Latência em ms
```

### Streaming

```python
async for chunk in client.generate_stream(
    prompt="Conte uma história",
    temperature=0.8,
):
    print(chunk.text, end="")
```

### Batch

```python
prompts = ["O que é Python?", "O que é FastAPI?", "O que é Docker?"]
responses = await client.generate_batch(
    prompts=prompts,
    temperature=0.5,
    max_tokens=100,
)

for response in responses:
    print(f"{response.text[:100]}...")
```

### Context Manager

```python
async with LLMClient(provider=LLMProvider.OPENAI, api_key="sk-...") as client:
    response = await client.generate("Olá!")
    print(response.text)
# Cliente é parado automaticamente
```

## Variáveis de Ambiente

```bash
# Configuração via ambiente
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4
export LLM_MAX_RETRIES=3
export LLM_TIMEOUT_SECONDS=60
export LLM_TEMPERATURE=0.7
export LLM_MAX_TOKENS=2048
```

## Exceções

```python
from neural_hive_llm.exceptions import (
    LLMError,                    # Base exception
    LLMTimeoutError,             # Timeout de requisição
    LLMRateLimitError,           # Rate limit excedido
    LLMInvalidRequestError,      # Requisição inválida
    LLMProviderError,            # Erro do provider
    LLMCircuitBreakerOpenError,  # Circuit breaker aberto
    LLMConfigurationError,       # Erro de configuração
)

try:
    response = await client.generate("Test")
except LLMRateLimitError:
    # Rate limit - retry automático já tentou
    logger.warning("Rate limit exceeded")
except LLMTimeoutError:
    # Timeout configurável
    logger.error("Request timeout")
except LLMError as e:
    # Outros erros
    logger.error(f"LLM error: {e}")
```

## Métricas Prometheus

A biblioteca registra automaticamente métricas:

```python
# Tempo de geração
llm_generation_duration_seconds{provider="openai",model="gpt-4"}

# Contagem de requisições
llm_requests_total{provider="openai",model="gpt-4",status="success"}

# Uso de tokens
llm_token_usage_total{provider="openai",model="gpt-4",service="code-forge"}

# Custo em USD
llm_cost_usd_total{provider="openai",model="gpt-4",service="code-forge"}
```

## Configuração por Provider

### OpenAI

```python
client = LLMClient(
    provider=LLMProvider.OPENAI,
    api_key="sk-...",
    model="gpt-4",  # ou gpt-3.5-turbo
    base_url="https://api.openai.com/v1",  # opcional
)
```

### Anthropic

```python
client = LLMClient(
    provider=LLMProvider.ANTHROPIC,
    api_key="sk-ant-...",
    model="claude-3-opus-20240229",  # ou outros modelos Claude
    base_url="https://api.anthropic.com/v1",  # opcional
)
```

### Local (Ollama)

```python
client = LLMClient(
    provider=LLMProvider.LOCAL,
    base_url="http://localhost:11434",  # ou "http://ollama:11434"
    model="llama2",  # ou "mistral", "neural-chat", etc.
)
```

## Testes

### Unitários (mock)

```python
from unittest.mock import AsyncMock, patch

async def test_generate():
    with patch("neural_hive_llm.providers.openai_provider.OpenAIProvider") as mock:
        mock_instance = AsyncMock()
        mock_instance.generate = AsyncMock(return_value=LLMResponse(text="Hello"))
        mock.return_value = mock_instance

        client = LLMClient(provider=LLMProvider.OPENAI, api_key="sk-...")
        await client.start()

        response = await client.generate("Say hello")
        assert response.text == "Hello"
```

### Integração (requer credenciais)

```python
import pytest

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_openai():
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("No API key")

    client = LLMClient(provider=LLMProvider.OPENAI, api_key=api_key)
    await client.start()

    response = await client.generate("Say hello")
    assert len(response.text) > 0

    await client.stop()
```

## Checklist de Migração

- [ ] Adicionar dependência `neural-hive-llm` ao requirements.txt/pyproject.toml
- [ ] Criar wrapper mantendo API existente (se necessário)
- [ ] Atualizar imports no código do serviço
- [ ] Configurar variáveis de ambiente
- [ ] Criar testes de regressão
- [ ] Testar localmente com todos os providers
- [ ] Executar testes de integração
- [ ] Verificar métricas no Prometheus/Grafana
- [ ] Atualizar documentação do serviço

## Troubleshooting

### Erro: "api_key é obrigatório"

**Solução:** Configure `LLM_API_KEY` ou passe `api_key` explicitamente.

### Erro: "Provider não suportado"

**Solução:** Use `LLMProvider.OPENAI`, `LLMProvider.ANTHROPIC`, ou `LLMProvider.LOCAL`.

### Erro: "Cliente não inicializado"

**Solução:** Chame `await client.start()` antes de usar `generate()`.

### Timeout em requisições

**Solução:** Aumente `LLM_TIMEOUT_SECONDS` ou passe `timeout_seconds` no construtor.

### Rate limit

**Solução:** O retry automático já tenta 3 vezes. Para aumentar, configure `LLM_MAX_RETRIES`.

## Suporte

Para problemas ou dúvidas:
- GitHub: https://github.com/albinoJimy/Neural-Hive-Mind
- Docs: `libs/neural_hive_llm/README.md`
- Exemplos: `libs/neural_hive_llm/examples/`
