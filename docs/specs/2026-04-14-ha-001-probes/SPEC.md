# Spec: HA-001-PROBES - Kubernetes Probes

**Epic:** Health Endpoints para Todos os Serviços
**Data:** 2026-04-14
**Prioridade:** P0 (Crítica)
**Estimativa:** 3-5 dias
**Status:** ✅ COMPLETO

---

## 1. Objetivo

Implementar health endpoints (/health, /health/deep, /health/startup) em todos os serviços do Neural Hive Mind que atualmente não os possuem, e configurar liveness/readiness/startup probes nos deployments Kubernetes.

---

## 2. Serviços Alvo (15+ Serviços)

### Serviços SEM health endpoint:

| Serviço | Path | HealthChecker Interno? |
|---------|------|------------------------|
| consensus-engine | `/services/consensus-engine/` | ✅ Sim (sem rota HTTP) |
| semantic-translation-engine | `/services/semantic-translation-engine/` | ✅ Sim (sem rota HTTP) |
| worker-agents | `/services/worker-agents/` | ❌ Não |
| scout-agents | `/services/scout-agents/` | ❌ Não |
| specialist-architecture | `/services/specialist-architecture/` | ❌ Não |
| specialist-business | `/services/specialist-business/` | ❌ Não |
| specialist-technical | `/services/specialist-technical/` | ❌ Não |
| specialist-behavior | `/services/specialist-behavior/` | ❌ Não |
| specialist-evolution | `/services/specialist-evolution/` | ❌ Não |

### Serviços COM health endpoint (referência):

- `/services/optimizer-agents/src/api/health.py` - **MODELO COMPLETO**

---

## 3. Abordagem de Implementação

### 3.1 Criar Middleware Compartilhado

**Arquivo:** `/libraries/python/neural_hive_api/health.py`

```python
from fastapi import APIRouter
from typing import Dict, Any
import time

class HealthChecker:
    """Health checker compartilhado para todos os serviços"""

    def __init__(self, service_name: str, version: str = "1.0.0"):
        self.service_name = service_name
        self.version = version
        self.start_time = time.time()

    async def check_health(self) -> Dict[str, Any]:
        """Health check básico"""
        return {
            "status": "healthy",
            "service": self.service_name,
            "version": self.version,
            "timestamp": time.time()
        }

    async def check_deep(self) -> Dict[str, Any]:
        """Deep health check com dependências"""
        health = await self.check_health()
        health["dependencies"] = await self._check_dependencies()
        return health

    async def check_startup(self) -> Dict[str, Any]:
        """Startup check - retorna True se serviço pronto"""
        elapsed = time.time() - self.start_time
        return {
            "status": "starting" if elapsed < 30 else "ready",
            "service": self.service_name,
            "elapsed_seconds": elapsed
        }

    async def _check_dependencies(self) -> Dict[str, str]:
        """Verificar dependências (override por cada serviço)"""
        return {}

def create_health_router(service_name: str, version: str = "1.0.0") -> APIRouter:
    """Cria router de health para um serviço"""
    router = APIRouter()
    health_checker = HealthChecker(service_name, version)

    @router.get("/health")
    async def health():
        return await health_checker.check_health()

    @router.get("/health/deep")
    async def deep_health():
        return await health_checker.check_deep()

    @router.get("/health/startup")
    async def startup():
        return await health_checker.check_startup()

    return router
```

### 3.2 Implementar por Serviço

#### Para consensus-engine:

**Arquivo:** `/services/consensus-engine/src/api/health.py`

```python
from fastapi import APIRouter
from neural_hive_api.health import create_health_router

router = APIRouter()
health_router = create_health_router("consensus-engine", "1.0.0")

# Montar health_router no main app
```

**Modificar:** `/services/consensus-engine/src/main.py`
- Importar e montar `health_router`

#### Para semantic-translation-engine:

**Arquivo:** `/services/semantic-translation-engine/src/api/health.py`

#### Para specialist services:

**Padrão:** `/services/specialist-{tipo}/src/api/health.py`

### 3.3 Configurar Kubernetes Probes

**Modelo de deployment:**

```yaml
spec:
  containers:
  - name: service
    ports:
    - containerPort: 8000
    livenessProbe:
      httpGet:
        path: /health
        port: 8000
      initialDelaySeconds: 30
      periodSeconds: 10
      timeoutSeconds: 5
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /health
        port: 8000
      initialDelaySeconds: 10
      periodSeconds: 5
      timeoutSeconds: 3
      failureThreshold: 3
    startupProbe:
      httpGet:
        path: /health/startup
        port: 8000
      initialDelaySeconds: 0
      periodSeconds: 5
      timeoutSeconds: 3
      failureThreshold: 30
```

---

## 4. Tickets (Decomposição)

| Ticket | Descrição | Serviços | Estimativa |
|--------|-----------|----------|------------|
| HA-001-01 | Criar middleware health compartilhado | neural_hive_api | 0.5 dia |
| HA-001-02 | Adicionar /health no consensus-engine | consensus-engine | 0.5 dia |
| HA-001-03 | Adicionar /health no semantic-translation-engine | semantic-translation-engine | 0.5 dia |
| HA-001-04 | Adicionar /health no worker-agents | worker-agents | 0.5 dia |
| HA-001-05 | Adicionar /health no scout-agents | scout-agents | 0.5 dia |
| HA-001-06 | Adicionar /health em specialist services (5) | specialists | 1 dia |
| HA-001-07 | Configurar probes nos deployments K8s | k8s/ | 0.5 dia |

---

## 5. Critérios de Aceite

- [x] Middleware `neural_hive_api/health.py` criado
- [x] Todos os 9 serviços alvo têm /health endpoint
- [x] livenessProbe configurado para todos
- [x] readinessProbe configurado para todos
- [x] startupProbe configurado para serviços de inicialização lenta
- [x] Testes automatizados criados
- [x] Documentação atualizada

## 5.1 Serviços Implementados

| Serviço | Health Endpoint | Probes K8s | Status |
|---------|-----------------|------------|--------|
| consensus-engine | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| semantic-translation-engine | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| worker-agents | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| scout-agents | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| specialist-architecture | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| specialist-business | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| specialist-technical | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| specialist-behavior | `/health`, `/ready` | ✅ | ✅ COMPLETO |
| specialist-evolution | `/health`, `/ready` | ✅ | ✅ COMPLETO |

---

## 6. Testes

```python
# tests/integration/test_health_endpoints.py

@pytest.mark.parametrize("service", [
    "consensus-engine",
    "semantic-translation-engine",
    "worker-agents",
    "scout-agents",
    "specialist-architecture",
])
async def test_health_endpoint(service):
    """Testa health endpoint responde 200"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{service}:8000/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
```

---

## 7. Handoff para Implementação

**Branch:** `feat/HA-001-probes`

**Comandos:**
```bash
git checkout -b feat/HA-001-probes

# Implementar middleware
mkdir -p libraries/python/neural_hive_api/
# ... criar health.py

# Implementar por serviço
# ... para cada serviço alvo

# Testes
pytest tests/integration/test_health_endpoints.py

# Commit
git add .
git commit -m "feat(ha): implement health endpoints for all services"
```

---

**Spec criada para:** HA-001-PROBES
**Data:** 2026-04-14
