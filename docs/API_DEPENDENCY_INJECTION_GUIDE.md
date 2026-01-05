# Guia de Dependency Injection para APIs FastAPI

Este documento descreve o padrão de injeção de dependências utilizado nas APIs FastAPI do Neural-Hive-Mind.

## Padrão Recomendado

### 1. Definir Funções de Dependency no Módulo da API

```python
from fastapi import Depends

def get_service() -> ServiceType:
    """Dependency para injetar ServiceType."""
    raise NotImplementedError("ServiceType dependency not configured")
```

### 2. Usar Depends() nos Endpoints

```python
@router.get("/endpoint")
async def endpoint(service: ServiceType = Depends(get_service)):
    result = await service.do_something()
    return result
```

### 3. Configurar Overrides no main.py (startup)

```python
from src.api import module

def override_service():
    return service_instance

app.dependency_overrides[module.get_service] = override_service
```

## Serviços Implementados

| Serviço | Status | Arquivo |
|---------|--------|---------|
| SLA Management System | ✅ Implementado | `services/sla-management-system/src/api/policies.py` |
| Optimizer Agents | ✅ Implementado | `services/optimizer-agents/src/api/optimizations.py`, `experiments.py` |

## Exemplo Completo

### Arquivo API (api/optimizations.py)

```python
from fastapi import APIRouter, Depends
from src.clients.mongodb_client import MongoDBClient

router = APIRouter(prefix="/api/v1/optimizations")

# Funções de dependency
def get_mongodb_client() -> MongoDBClient:
    raise NotImplementedError("MongoDBClient dependency not configured")

@router.get("")
async def list_optimizations(
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
):
    optimizations = await mongodb_client.list_optimizations()
    return {"optimizations": optimizations}
```

### Arquivo Main (main.py)

```python
from fastapi import FastAPI
from src.api import optimizations

app = FastAPI()
app.include_router(optimizations.router)

# Variáveis globais (inicializadas no startup)
mongodb_client = None

async def startup():
    global mongodb_client
    mongodb_client = MongoDBClient(...)
    await mongodb_client.connect()

    # Configurar dependency overrides
    def override_mongodb_client():
        return mongodb_client

    app.dependency_overrides[optimizations.get_mongodb_client] = override_mongodb_client

app.add_event_handler("startup", startup)
```

## Anti-Padrões a Evitar

### ❌ Variáveis Globais com Optional

```python
# EVITAR
mongodb_client: Optional[MongoDBClient] = None

@router.get("")
async def list_optimizations():
    if not mongodb_client:
        raise HTTPException(status_code=503)
    ...
```

### ❌ Funções set_dependencies() Manuais

```python
# EVITAR
def set_dependencies(mongodb: MongoDBClient):
    global mongodb_client
    mongodb_client = mongodb
```

### ❌ Checks Manuais nos Endpoints

```python
# EVITAR
@router.get("")
async def list_optimizations():
    if not mongodb_client:
        raise HTTPException(status_code=503, detail="Not initialized")
```

## Vantagens do Padrão dependency_overrides

1. **Testabilidade**: Fácil mockar dependências em testes
2. **Clareza**: Dependências explícitas na assinatura do endpoint
3. **Consistência**: Padrão nativo do FastAPI
4. **Segurança**: FastAPI garante que dependências estão disponíveis

## Testes com dependency_overrides

```python
from fastapi.testclient import TestClient
from src.api import optimizations

def test_list_optimizations():
    app = FastAPI()
    app.include_router(optimizations.router)

    mock_mongodb = MagicMock()
    mock_mongodb.list_optimizations = AsyncMock(return_value=[])

    app.dependency_overrides[optimizations.get_mongodb_client] = lambda: mock_mongodb

    client = TestClient(app)
    response = client.get("/api/v1/optimizations")
    assert response.status_code == 200
```
