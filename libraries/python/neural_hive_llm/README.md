# neural_hive_llm

Biblioteca Neural Hive-Mind para clientes LLM centralizados.

## Overview

`neural_hive_llm` fornece uma interface unificada para múltiplos provedores LLM (OpenAI, Anthropic, Ollama/local) com:

- **Multi-provider suporte**: OpenAI, Anthropic, e modelos locais (Ollama)
- **Retry automático**: Com exponential backoff configurável
- **Circuit breaker**: Proteção contra falhas cascata
- **Observabilidade**: OpenTelemetry tracing e métricas Prometheus
- **Token counting**: Contagem de tokens e cálculo de custos

## Instalação

```bash
# Básico (apenas provedor local)
pip install neural-hive-llm

# Com OpenAI
pip install neural-hive-llm[openai]

# Com Anthropic
pip install neural-hive-llm[anthropic]

# Com todos os provedores
pip install neural-hive-llm[all]
```

## Uso Rápido

```python
import asyncio
from neural_hive_llm import LLMClient, LLMProvider

async def main():
    # Inicializar cliente
    client = LLMClient(
        provider=LLMProvider.OPENAI,
        api_key="sk-...",
        model="gpt-4o",
    )
    await client.start()

    # Gerar texto
    response = await client.generate(
        prompt="Explique o padrão Circuit Breaker",
        system_prompt="Você é um engenheiro de software sênior",
        temperature=0.7,
        max_tokens=500,
    )

    print(response.text)
    print(f"Tokens: {response.total_tokens}")
    print(f"Custo: ${response.estimated_cost_usd:.6f}")
    print(f"Latência: {response.latency_ms:.0f}ms")

    await client.stop()

asyncio.run(main())
```

## Configuração via Variáveis de Ambiente

```bash
# .env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
LLM_MAX_RETRIES=3
LLM_TIMEOUT=60
```

```python
from neural_hive_llm import get_llm_settings, LLMClient

settings = get_llm_settings()
client = LLMClient(settings=settings)
```

## Streaming

```python
async for chunk in client.generate_stream(
    prompt="Conte uma história curta",
):
    print(chunk.delta, end="", flush=True)
```

## Batch Processing

```python
prompts = [
    "O que é microserviços?",
    "O que é serverless?",
    "O que é kubernetes?",
]

responses = await client.generate_batch(prompts, temperature=0.5)

for i, resp in enumerate(responses):
    print(f"Resposta {i+1}: {resp.text[:100]}...")
```

## Métricas Prometheus

A biblioteca expõe automaticamente métricas:

- `llm_generation_duration_seconds` - Histograma de duração
- `llm_requests_total` - Contador de requisições
- `llm_tokens_total` - Contador de tokens (input/output)
- `llm_cost_usd_total` - Custo total em USD

## Exceções

```python
from neural_hive_llm.exceptions import (
    LLMRateLimitError,
    LLMTimeoutError,
    LLMProviderError,
)

try:
    response = await client.generate(prompt="...")
except LLMRateLimitError as e:
    print(f"Rate limit: {e.retry_after}s")
except LLMTimeoutError as e:
    print(f"Timeout após {e.timeout_seconds}s")
except LLMProviderError as e:
    print(f"Erro provedor: {e}")
```

## Licença

MIT
