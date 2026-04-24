# neural_hive_llm

Biblioteca centralizada de LLM clients para Neural Hive Mind - abstração unificada para múltiplos provedores (OpenAI, Anthropic, Local/Ollama).

## Status

- **Versão:** 0.1.0
- **Status:** Estável - pronta para produção
- **Migrações:** code-forge e architect-agent migrados

## Características

- **Multi-provider:** OpenAI, Anthropic, Local/Ollama
- **Async/await:** Totalmente assíncrono com streaming
- **Resilience:** Retry automático com exponential backoff
- **Observabilidade:** OpenTelemetry, Prometheus, structlog
- **Type-safe:** Type hints completos com Pydantic
- **Zero código duplicado:** ~500 linhas eliminadas dos serviços

## Instalação

```bash
# Básico (apenas http client para providers locais)
pip install neural-hive-llm

# Com OpenAI
pip install neural-hive-llm[openai]

# Com Anthropic
pip install neural-hive-llm[anthropic]

# Com todos os providers
pip install neural-hive-llm[all]
```

## Quick Start

### OpenAI

```python
from neural_hive_llm import LLMClient, LLMProvider

client = LLMClient(
    provider=LLMProvider.OPENAI,
    api_key="sk-...",
    model="gpt-4"
)
await client.start()

response = await client.generate(
    prompt="Explique microserviços",
    system_prompt="Você é um arquiteto sênior",
    temperature=0.7
)

print(response.text)              # Texto gerado
print(response.total_tokens)      # Contagem de tokens
print(response.estimated_cost_usd)  # Custo estimado

await client.stop()
```

### Anthropic

```python
client = LLMClient(
    provider=LLMProvider.ANTHROPIC,
    api_key="sk-ant-...",
    model="claude-3-opus-20240229"
)
await client.start()
response = await client.generate("Explique GraphQL")
await client.stop()
```

### Local/Ollama

```python
client = LLMClient(
    provider=LLMProvider.LOCAL,
    base_url="http://localhost:11434",
    model="llama2"
)
await client.start()
response = await client.generate("Explike Kubernetes")
await client.stop()
```

## Streaming

```python
async for chunk in client.generate_stream(
    prompt="Escreva um poema sobre IA",
    system_prompt="Você é um poeta"
):
    print(chunk, end="", flush=True)
```

## Configuração via Ambiente

```bash
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4
export LLM_MAX_RETRIES=3
export LLM_TIMEOUT_SECONDS=60
```

```python
from neural_hive_llm import get_llm_settings, LLMClient

settings = get_llm_settings()
client = LLMClient(settings=settings)
```

## Métricas Prometheus

A biblioteca exporta automaticamente:

- `llm_generation_duration_seconds{provider, model}` - Histograma de latência
- `llm_requests_total{provider, model, status}` - Contador de requisições
- `llm_token_usage_total{provider, model, service}` - Tokens consumidos
- `llm_cost_usd_total{provider, model, service}` - Custo em USD

## Exceções

```python
from neural_hive_llm.exceptions import (
    LLMTimeoutError,
    LLMRateLimitError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMCircuitBreakerOpenError
)

try:
    response = await client.generate(prompt="...")
except LLMRateLimitError:
    logger.warning("Rate limit exceeded")
except LLMTimeoutError:
    logger.error("LLM request timeout")
```

## Serviços Migramos

| Serviço | Status | Wrapper | Testes |
|---------|--------|---------|--------|
| code-forge | ✅ Migrado | `llm_client_wrapper.py` | `test_llm_client_migration.py` |
| architect-agent | ✅ Migrado | `llm_client_wrapper.py` | `test_llm_client_migration.py` |

## Guia de Migração

Para migrar seu serviço para `neural_hive_llm`, consulte:

- [Migration Guide](docs/MIGRATION_GUIDE.md) - Instruções detalhadas
- [Exemplos](examples/) - Código de exemplo

## Testes

```bash
# Unit tests (sem credenciais)
pytest tests/ -m "not integration"

# Integration tests (requer credenciais ou Ollama local)
export OPENAI_API_KEY=sk-...
pytest tests/ -m integration

# Testes de migração específicos
pytest services/code-forge/tests/unit/test_clients/test_llm_client_migration.py
pytest services/architect-agent/tests/unit/test_planners/test_llm_client_migration.py
```

## Desenvolvimento

```bash
# Instalar dependências de desenvolvimento
pip install -e ".[dev]"

# Rodar testes
pytest

# Linting
ruff check .
black .

# Type checking
mypy neural_hive_llm/
```

## Licença

MIT
