# Design: HA-001-PROBES - Kubernetes Probes

**Data:** 2026-04-14
**Epic:** Health Endpoints para Todos os Serviços
**Status:** Design Atualizado
**Autor:** Claude (superpowers:brainstorming)

---

## 1. Análise de Estado Atual

### 1.1 O Que JÁ EXISTE

**Biblioteca Compartilhada:**
- `neural_hive_observability.health` - HealthChecker completo com checks de Database, Kafka, Redis, Memory, Custom

**Health Endpoints Implementados:**

| Serviço | `/health` | `/ready` | `/health/startup` | `/health/live` | Outros |
|---------|----------|----------|-------------------|----------------|--------|
| optimizer-agents | ✅ | ✅ | ✅ | ✅ | `/health/deep` |
| guard-agents | ✅ | ✅ | ✅ | ❌ | - |
| consensus-engine | ✅ | ✅ | ❌ | ❌ | - |
| semantic-translation-engine | ✅ | ✅ | ❌ | ❌ | - |
| worker-agents | ✅ | ✅ | ❌ | ❌ | `/metrics` |
| scout-agents | ❌ | ✅ (como `/health/ready`) | ❌ | ✅ (`/health/live`) | `/metrics` |
| specialist-architecture | ✅ | ✅ | ❌ | ❌ | `/status`, `/metrics` |
| specialist-business | ✅ | ✅ | ❌ | ❌ | `/status`, `/metrics` |
| specialist-technical | ✅ | ✅ | ❌ | ❌ | `/status`, `/metrics` |
| specialist-behavior | ✅ | ✅ | ❌ | ❌ | `/status`, `/metrics` |
| specialist-evolution | ✅ | ✅ | ❌ | ❌ | `/status`, `/metrics` |
| queen-agent | ✅ | ✅ | ❌ | ❌ | - |
| self-healing-engine | ✅ | ✅ | ❌ | ❌ | - |
| analyst-agents | ✅ | ✅ | ❌ | ❌ | - |
| execution-ticket-service | ✅ | ✅ | ❌ | ❌ | - |

**Kubernetes Probes Configuradas:**

| Serviço | `livenessProbe` | `readinessProbe` | `startupProbe` |
|---------|----------------|------------------|----------------|
| consensus-engine | ✅ | ✅ | ❌ |
| worker-agents | ✅ | ✅ | ❌ |
| optimizer-agents | ✅ | ✅ | ❌ |
| scout-agents | ? | ? | ❌ |

---

## 2. Problema Identificado

**O spec original estava desatualizado:**
- Todos os serviços JÁ têm `/health` e `/ready` endpoints
- A maioria JÁ tem livenessProbe e readinessProbe configuradas

**O que realmente falta:**
1. **Endpoint `/health/startup`** - Apenas 2 de 13 serviços têm
2. **startupProbe no Kubernetes** - Nenhum serviço tem

**Por que isso é crítico:**
- Sem `/health/startup`, serviços com inicialização lenta podem ser mortos pelo livenessProbe antes de terminarem o startup
- Sem startupProbe, Kubernetes não sabe quanto tempo esperar para o serviço ficar pronto

---

## 3. Solução Proposta

### 3.1 Adicionar `/health/startup` Endpoint

**Modelo de referência:** `optimizer-agents/src/api/health.py`

```python
class StartupResponse(BaseModel):
    status: str
    service: str
    version: str
    started_at: str

@router.get("/health/startup", response_model=StartupResponse)
async def startup_check():
    """Startup probe - retorna started/starting"""
    settings = get_settings()
    return StartupResponse(
        status="started",
        service=settings.service_name,
        version=settings.service_version,
        started_at=datetime.now(timezone.utc).isoformat()
    )
```

**Serviços que precisam adicionar:**
- consensus-engine
- semantic-translation-engine
- worker-agents
- scout-agents
- specialist-* (5 serviços)
- queen-agent
- self-healing-engine
- analyst-agents
- execution-ticket-service

### 3.2 Adicionar startupProbe nos Helm Charts

**Modelo de referência:** Template em `k8s/templates/service-health-template.yaml`

```yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: http
    scheme: HTTP
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  successThreshold: 1
  failureThreshold: 6  # Allow up to 60 seconds for startup
```

**Todos os helm charts precisam adicionar.**

---

## 4. Padronização de Endpoints

### 4.1 Especificação Padronizada

| Endpoint | Propósito | Response Esperado |
|----------|-----------|-------------------|
| `/health` | Liveness - processo vivo? | `{"status": "healthy", "service": "...", "version": "..."}` |
| `/ready` | Readiness - pronto para tráfego? | `{"ready": true, "checks": {...}}` |
| `/health/startup` | Startup - inicialização completa? | `{"status": "started", "service": "...", "version": "..."}` |

### 4.2 Valores de Status

- **`/health`**: `healthy`, `unhealthy`, `degraded`
- **`/ready`**: `ready: true`, `ready: false`
- **`/health/startup`**: `started`, `starting`

---

## 5. Implementação

### 5.1 Criar Helper Compartilhado

**Arquivo:** `libraries/python/neural_hive_observability/neural_hive_observability/health_endpoints.py`

```python
"""
Helper para criar endpoints de health padronizados.
"""
from fastapi import APIRouter
from datetime import datetime, timezone
from typing import Any

def create_startup_endpoint(service_name: str, version: str):
    """Cria endpoint /health/startup padronizado"""
    
    async def startup_check():
        return {
            "status": "started",
            "service": service_name,
            "version": version,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
    
    return startup_check
```

### 5.2 Tasks de Implementação

| Ticket | Descrição | Serviços | Estimativa |
|--------|-----------|----------|------------|
| HA-001-01 | Adicionar `/health/startup` no consensus-engine | consensus-engine | 0.5 dia |
| HA-001-02 | Adicionar `/health/startup` no semantic-translation-engine | semantic-translation-engine | 0.5 dia |
| HA-001-03 | Adicionar `/health/startup` no worker-agents | worker-agents | 0.5 dia |
| HA-001-04 | Adicionar `/health/startup` no scout-agents | scout-agents | 0.5 dia |
| HA-001-05 | Adicionar `/health/startup` em specialist services (5) | specialists | 1 dia |
| HA-001-06 | Adicionar `/health/startup` em serviços core (4) | queen, self-healing, analyst, execution-ticket | 1 dia |
| HA-001-07 | Adicionar startupProbe nos helm charts (todos) | helm/ | 1 dia |

---

## 6. Testes

### 6.1 Validação de Endpoints

```python
@pytest.mark.parametrize("service", [
    "consensus-engine",
    "semantic-translation-engine",
    "worker-agents",
    "scout-agents",
])
async def test_startup_endpoint(service):
    """Verifica que /health/startup responde corretamente"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://{service}:8000/health/startup")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["started", "starting"]
        assert "service" in data
        assert "version" in data
```

### 6.2 Validação Kubernetes

```bash
# Verificar startupProbe configurada
kubectl get deployment <service> -o jsonpath='{.spec.template.spec.containers[0].startupProbe}'

# Verificar pods iniciando corretamente
kubectl describe pod <pod-name> | grep -A 5 "Events"
```

---

## 7. Critérios de Aceite

- [ ] Todos os 13 serviços têm endpoint `/health/startup`
- [ ] Todos os helm charts têm `startupProbe` configurada
- [ ] Testes automatizados passando
- [ ] Documentação atualizada

---

## 8. Próximos Passos

1. Criar helper compartilhado em `neural_hive_observability`
2. Implementar `/health/startup` em cada serviço
3. Adicionar `startupProbe` nos helm charts
4. Criar testes automatizados
5. Atualizar documentação

---

**Design finalizado em:** 2026-04-14
**Próximo passo:** Criar plano de implementação
