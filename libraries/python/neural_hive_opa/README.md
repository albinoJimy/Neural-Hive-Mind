# neural_hive_opa

Biblioteca Python padronizada para integração com Open Policy Agent (OPA) no Neural Hive Mind.

## Status

✅ **Biblioteca Core Completa** - 109 testes passando

## Instalação

```bash
pip install neural-hive-opa
```

## Uso Básico

```python
from neural_hive_opa import OPAClient, OPAConfig

# Configuração
config = OPAConfig(
    opa_url="http://opa:8181",
    opa_cache_ttl_seconds=300,
    opa_timeout_seconds=5
)

# Cliente
client = OPAClient(config)
await client.initialize()

# Avaliação de política
result = await client.evaluate(
    policy_path="neuralhive/authz",
    input_data={"user": "alice", "action": "read", "resource": "data1"}
)

# Fechar conexão
await client.close()
```

## Features

- ✅ Connection pooling (aiohttp)
- ✅ Cache LRU com TTL
- ✅ Circuit breaker manual
- ✅ Batch evaluation
- ✅ Métricas Prometheus
- ✅ Retry com tenacity
- ✅ FastAPI middleware
- ✅ Policy bundle management

## Requisitos

- Python >= 3.12
- aiohttp >= 3.9.0
- pydantic >= 2.0.0
- cachetools >= 5.3.0
- structlog >= 24.0.0
- tenacity >= 8.2.0
- prometheus-client >= 0.19.0

## Serviços Integrados

1. ✅ Orchestrator-Dynamic - wrapper via `src/policies/opa_client.py`
2. ✅ Queen-Agent - wrapper via `src/clients/opa_client.py`
3. ✅ Worker-Agents - wrapper via `src/clients/opa_client.py`
4. ✅ Guard-Agents - wrapper via `src/clients/opa_client.py`
5. ✅ Architect-Agent - wrapper via `src/validators/opa_client.py`

## Métricas Prometheus

As seguintes métricas são exportadas:

- `opa_evaluations_total` (counter) - Total de avaliações OPA
- `opa_evaluation_duration_ms` (histogram) - Duração das avaliações
- `opa_cache_hits_total` (counter) - Cache hits
- `opa_cache_misses_total` (counter) - Cache misses
- `opa_circuit_breaker_state` (gauge) - Estado do circuit breaker
- `opa_batch_evaluations_total` (counter) - Total de avaliações em batch

## Middleware FastAPI

```python
from fastapi import FastAPI
from neural_hive_opa.middleware import OPAAuthorizationMiddleware

app = FastAPI()

app.add_middleware(
    OPAAuthorizationMiddleware,
    opa_url="http://opa:8181",
    policy_path="neuralhive/authz"
)
```

## Policy Bundle Management

```python
from neural_hive_opa.bundles import PolicyBundleManager

manager = PolicyBundleManager(opa_url="http://opa:8181")
await manager.download_bundle()
await manager.reload_policies()
```

## Desenvolvimento

```bash
# Instalar dependências de desenvolvimento
pip install -e ".[dev]"

# Rodar testes
pytest

# Formatar código
black .
ruff check .
```

## Licença

MIT
