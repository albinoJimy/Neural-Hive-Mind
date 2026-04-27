# Spec: neural_hive_llm - Biblioteca Centralizada de LLM Clients

> **Status:** ✅ 100% COMPLETO
> **Prioridade:** ALTA
> **Estimativa:** 7 dias (56 horas) - CONCLUÍDO
> **Epic:** IA/ML Professionalization
>
> **Entregues:**
> - Biblioteca `neural_hive_llm` (3.450 linhas)
> - 65 testes unitários passando
> - Migrations: code-forge ✅, architect-agent ✅

---

## Overview

Criar uma biblioteca Python centralizada `neural_hive_llm` para abstração de múltiplos provedores LLM (OpenAI, Anthropic, Local/Ollama), eliminando ~500 linhas de código duplicado entre `code-forge` e `architect-agent`.

**Contexto Crítico:** A validação profunda do codebase revelou que drift detection, feature extraction profissional e auto-retrain **JÁ EXISTEM** e estão bem implementados. O único gap real é a biblioteca central de LLMs.

---

## User Stories

### US-1: Code Forge Migration
Como desenvolvedor do **code-forge**, quero migrar para `neural_hive_llm` mantendo todas as funcionalidades atuais (streaming, retries, múltiplos providers).

### US-2: Architect Agent Migration  
Como desenvolvedor do **architect-agent**, quero usar `neural_hive_llm` para adicionar suporte a novos providers sem modificar código do serviço.

### US-3: Novo Serviço
Como desenvolvedor criando um **novo serviço NHM**, quero uma biblioteca simples para integrar LLMs sem estudar implementações existentes.

### US-4: Operador ML
Como operador responsável por **custos de LLM**, quero métricas centralizadas de token usage e custos por serviço/provedor.

---

## Scope

### Incluído
- Multi-provider abstração (OpenAI, Anthropic, Local/Ollama)
- `generate()`, `generate_stream()`, `generate_batch()`
- Retry automático com exponential backoff (tenacity)
- Token counting e estimativa de custos
- Circuit breaker (via `neural_hive_resilience`)
- Observabilidade (OpenTelemetry, Prometheus, structlog)
- Pydantic Settings para configuração

### Excluído
- Fine-tuning de modelos
- Embeddings (já existe em `neural_hive_specialists`)
- RAG / Vector DB operations
- Prompt templates management
- Function calling (v1.1)

---

## Requisitos Funcionais

### RF-1: API Principal

```python
from neural_hive_llm import LLMClient, LLMProvider, LLMResponse

# Inicialização
client = LLMClient(
    provider=LLMProvider.OPENAI,
    api_key="sk-...",
    model="gpt-4"
)
await client.start()

# Geração
response = await client.generate(
    prompt="Explique microserviços",
    system_prompt="Você é um arquiteto sênior",
    temperature=0.7,
    max_tokens=1000
)

# Response
print(response.text)              # Texto gerado
print(response.total_tokens)      # Contagem de tokens
print(response.estimated_cost_usd)  # Custo estimado
print(response.latency_ms)        # Latência

# Streaming
async for chunk in client.generate_stream(prompt="..."):
    print(chunk, end="")

# Batch
responses = await client.generate_batch(
    prompts=["prompt1", "prompt2", "prompt3"],
    temperature=0.5
)

await client.stop()
```

### RF-2: Configuração via Pydantic

```python
from neural_hive_llm import get_llm_settings

# Via variáveis de ambiente (prefixo LLM_)
# LLM_PROVIDER=openai
# LLM_API_KEY=sk-...
# LLM_MODEL=gpt-4
# LLM_MAX_RETRIES=3

settings = get_llm_settings()
client = LLMClient(settings=settings)
```

### RF-3: Exceções

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
    # Rate limit - retry automático já tentou
    logger.warning("Rate limit exceeded")
except LLMTimeoutError:
    # Timeout configurável (default 60s)
    logger.error("LLM request timeout")
```

### RF-4: Métricas Prometheus

```python
# Métricas automaticamente registradas
# llm_generation_duration_seconds{provider, model}
# llm_requests_total{provider, model, status}
# llm_token_usage_total{provider, model, service}
# llm_cost_usd_total{provider, model, service}
```

---

## Arquitetura

```
libraries/python/neural_hive_llm/
├── neural_hive_llm/
│   ├── __init__.py                 # Exportações públicas
│   ├── config.py                   # LLMSettings, get_llm_settings()
│   ├── client.py                   # LLMClient principal
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseProvider (ABC)
│   │   ├── openai_provider.py      # OpenAI
│   │   ├── anthropic_provider.py   # Anthropic
│   │   └── local_provider.py       # Ollama/local
│   ├── resilience.py               # Retry + circuit breaker
│   ├── token_counter.py            # Token counting e custos
│   ├── observability.py            # Tracing, metrics, logging
│   ├── exceptions.py               # Exceções customizadas
│   └── models.py                   # Pydantic models
├── tests/
│   ├── conftest.py
│   ├── test_client.py
│   ├── test_providers/
│   └── integration/
├── README.md
└── pyproject.toml
```

---

## Tickets (Decomposição)

### EPIC-1: Fundação da Biblioteca

#### TICKET-1.1: Estrutura de Módulos Base
- [ ] Criar diretório `libraries/python/neural_hive_llm/`
- [ ] Criar `pyproject.toml` com dependências
- [ ] Criar estrutura de pacotes `__init__.py`
- [ ] Configurar pytest, ruff, black
- **Estimativa:** 2 horas

#### TICKET-1.2: Models e Exceptions
- [ ] Criar `models.py` com `LLMResponse`, `LLMProvider` (Enum)
- [ ] Criar `exceptions.py` com exceções hierárquicas
- [ ] Criar `config.py` com `LLMSettings` (Pydantic)
- [ ] Testes unitários para validação Pydantic
- **Estimativa:** 3 horas

#### TICKET-1.3: BaseProvider (ABC)
- [ ] Criar `providers/base.py` com `BaseProvider` ABC
- [ ] Definir métodos: `generate()`, `generate_stream()`, `healthcheck()`
- [ ] Type hints em todos os métodos
- [ ] Docstrings Google style
- **Estimativa:** 2 horas

### EPIC-2: Implementação de Providers

#### TICKET-2.1: OpenAI Provider
- [ ] Implementar `providers/openai_provider.py`
- [ ] Lazy import de `openai` SDK
- [ ] Suporte a system_prompt + user messages
- [ ] Streaming assíncrono
- [ ] Token counting via SDK
- [ ] Testes unitários (mock) + integração (real)
- **Estimativa:** 6 horas

#### TICKET-2.2: Anthropic Provider
- [ ] Implementar `providers/anthropic_provider.py`
- [ ] Lazy import de `anthropic` SDK
- [ ] Suporte a system parameter separado
- [ ] Streaming assíncrono
- [ ] Token counting via SDK
- [ ] Testes unitários (mock) + integração (real)
- **Estimativa:** 6 horas

#### TICKET-2.3: Local/Ollama Provider
- [ ] Implementar `providers/local_provider.py`
- [ ] HTTP client via httpx
- [ ] Endpoint `/api/generate` do Ollama
- [ ] Streaming (opcional para v1)
- [ ] Testes com container Ollama local
- **Estimativa:** 4 horas

### EPIC-3: Resilience e Observabilidade

#### TICKET-3.1: Retry Logic
- [ ] Implementar `resilience.py` com tenacity
- [ ] Configuração: max_retries, base_delay, max_delay
- [ ] Retry para: RateLimitError, timeout, 5xx
- [ ] Log de cada tentativa
- **Estimativa:** 3 horas

#### TICKET-3.2: Circuit Breaker
- [ ] Integrar com `neural_hive_resilience.CircuitBreaker`
- [ ] Configuração: failure_threshold, recovery_timeout
- [ ] Exceção `LLMCircuitBreakerOpenError`
- [ ] Testes de state transitions
- **Estimativa:** 4 horas

#### TICKET-3.3: Token Counter e Custos
- [ ] Implementar `token_counter.py`
- [ ] Tabela de preços configurável (OpenAI, Anthropic)
- [ ] Cálculo de custo por requisição
- [ ] Métricas Prometheus de tokens e custos
- **Estimativa:** 3 horas

#### TICKET-3.4: Observabilidade
- [ ] Integrar OpenTelemetry tracing
- [ ] Span `llm.generate` com attributes
- [ ] Histogram `llm_generation_duration_seconds`
- [ ] Counter `llm_requests_total`
- [ ] Structlog com contexto
- **Estimativa:** 4 horas

### EPIC-4: Client Principal

#### TICKET-4.1: LLMClient
- [ ] Implementar `client.py` com `LLMClient`
- [ ] Strategy pattern para seleção de provider
- [ ] Métodos: `generate()`, `generate_stream()`, `generate_batch()`
- [ ] `start()` e `stop()` para lifecycle
- [ ] Testes unitários completos
- **Estimativa:** 6 horas

#### TICKET-4.2: Settings Integration
- [ ] `get_llm_settings()` singleton
- [ ] Validação cruzada (api_key se != local)
- [ ] Suporte a múltiplos ambientes
- [ ] Testes de configuração
- **Estimativa:** 2 horas

### EPIC-5: Migração de Serviços

#### TICKET-5.1: Migrar code-forge
- [ ] Adicionar dependência `neural-hive-llm`
- [ ] Remover `src/clients/llm_client.py` (408 linhas)
- [ ] Atualizar imports
- [ ] Manter `generate_code()` como wrapper
- [ ] Testes de regressão
- **Estimativa:** 4 horas

#### TICKET-5.2: Migrar architect-agent
- [ ] Adicionar dependência `neural-hive-llm`
- [ ] Remover `src/planners/llm_client.py` (123 linhas)
- [ ] Atualizar imports
- [ ] Manter `_get_default_response()` como fallback
- [ ] Testes de regressão
- **Estimativa:** 3 horas

### EPIC-6: Testes e Documentação

#### TICKET-6.1: Testes Unitários
- [ ] Cobertura > 80% em todos os módulos
- [ ] Fixtures para mocks de providers
- [ ] Testes de retry, circuit breaker, token counting
- **Estimativa:** 6 horas

#### TICKET-6.2: Testes de Integração
- [ ] Testes reais contra OpenAI (marcado `@pytest.mark.integration`)
- [ ] Testes reais contra Anthropic
- [ ] Testes com Ollama local
- [ ] CI/CD para rodar apenas com credenciais
- **Estimativa:** 4 horas

#### TICKET-6.3: Documentação
- [ ] README.md com exemplos de uso
- [ ] Docstrings Google style em todos os métodos públicos
- [ ] Migration guide para code-forge/architect-agent
- [ ] Changelog para versionamento
- **Estimativa:** 4 horas

---

## Critérios de Sucesso

- [ ] Migração completa de code-forge e architect-agent
- [ ] Cobertura de testes > 80%
- [ ] Zero regressões em funcionalidades LLM
- [ ] Latência P95 < 2s mantida
- [ ] Métricas Prometheus visíveis no Grafana
- [ ] Documentação 100% completa

---

## Dependencies

**Internal:**
- `neural_hive_observability` - Logging e tracing
- `neural_hive_resilience` - Circuit breaker

**External:**
- `pydantic>=2.0` - Settings e models
- `pydantic-settings` - Environment config
- `openai>=1.40.0` - OpenAI SDK
- `anthropic>=0.40.0` - Anthropic SDK
- `httpx>=0.28.0` - HTTP client
- `tenacity>=8.0` - Retry logic
- `structlog` - Logging
- `opentelemetry-api` - Tracing
- `prometheus-client` - Metrics

---

## Handoff para Claude Code

### Comando Inicial
```
@execute-tasks
Epic: neural_hive_llm Library
Spec: .agent-os/specs/2026-04-24-neural-hive-llm/spec.md
```

### Ordem de Execução
1. EPIC-1 → EPIC-2 → EPIC-3 → EPIC-4 → EPIC-5 → EPIC-6
2. Cada ticket deve ter testes antes de prosseguir
3. Commits após cada EPIC completo

### Branch Strategy
```
feat/neural-hive-llm-library
├── epic-1-foundation
├── epic-2-providers
├── epic-3-resilience
├── epic-4-client
├── epic-5-migration
└── epic-6-tests-docs
```

---

## Conclusão

Esta spec define uma biblioteca **pragmática e implementável** que consolida a funcionalidade LLM do NHM. A validação profunda revelou que todos os outros componentes ML críticos já existem - este é o único gap real.

**Próximo Passo:** Executar `@execute-tasks` com esta spec.
