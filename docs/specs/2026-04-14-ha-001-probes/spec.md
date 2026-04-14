# Spec: HA-001-PROBES - Kubernetes Startup Probes

**Epic:** Kubernetes Startup Probes para Todos os Serviços
**Data:** 2026-04-14
**Prioridade:** P1 (Importante)
**Estimativa:** 3-4 dias

---

## 1. Objetivo

Adicionar endpoint `/health/startup` e configurar `startupProbe` no Kubernetes para todos os serviços FastAPI do Neural Hive Mind, prevenindo que serviços com inicialização lenta sejam mortos prematuramente pelo livenessProbe.

---

## 2. Problema

**Estado Atual:**
- 13 serviços têm `/health` e `/ready` endpoints ✅
- Apenas 2 serviços têm `/health/startup` (optimizer-agents, guard-agents)
- Nenhum serviço tem `startupProbe` configurada no Kubernetes

**Risco:**
- Serviços com inicialização lenta podem ser mortos pelo livenessProbe antes de terminarem o startup
- Kubernetes não sabe quanto tempo esperar para o serviço ficar pronto

---

## 3. Solução

### 3.1 Adicionar `/health/startup` Endpoint

**Modelo:**
```python
@app.get("/health/startup")
async def startup_check():
    return {
        "status": "started",
        "service": "service-name",
        "version": "1.0.0",
        "started_at": datetime.now(timezone.utc).isoformat()
    }
```

### 3.2 Adicionar startupProbe no Kubernetes

```yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 6  # 60s total
```

---

## 4. Serviços (11 que precisam de /health/startup)

| # | Serviço | Porta | Status Atual |
|---|---------|-------|--------------|
| 1 | consensus-engine | 8002 | ❌ Precisa |
| 2 | semantic-translation-engine | 8001 | ❌ Precisa |
| 3 | worker-agents | 8005 | ❌ Precisa |
| 4 | scout-agents | 8100 | ❌ Precisa |
| 5 | queen-agent | 8006 | ❌ Precisa |
| 6 | self-healing-engine | 8106 | ❌ Precisa |
| 7 | analyst-agents | 8107 | ❌ Precisa |
| 8 | execution-ticket-service | 8108 | ❌ Precisa |
| 9 | specialist-architecture | 8101 | ❌ Precisa |
| 10 | specialist-business | 8102 | ❌ Precisa |
| 11 | specialist-technical | 8103 | ❌ Precisa |
| 12 | specialist-behavior | 8104 | ❌ Precisa |
| 13 | specialist-evolution | 8105 | ❌ Precisa |

**Já têm:** optimizer-agents, guard-agents ✅

---

## 5. Tickets (Decomposição)

| Ticket | Descrição | Estimativa |
|--------|-----------|------------|
| HA-001-01 | Criar helper em neural_hive_observability | 0.5 dia |
| HA-001-02 | Adicionar /health/startup em serviços core (5) | 1 dia |
| HA-001-03 | Adicionar /health/startup em specialist services (5) | 1 dia |
| HA-001-04 | Adicionar /health/startup em serviços restantes (3) | 0.5 dia |
| HA-001-05 | Adicionar startupProbe nos helm charts | 0.5 dia |
| HA-001-06 | Testes E2E | 0.5 dia |

---

## 6. Critérios de Aceite

- [ ] Todos os 13 serviços têm endpoint `/health/startup`
- [ ] Todos os helm charts têm `startupProbe` configurada
- [ ] Testes automatizados passando
- [ ] Documentação atualizada

---

**Spec criada para:** HA-001-PROBES
**Data:** 2026-04-14
