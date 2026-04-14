# Spec: SEC-001-HEADERS - Security Headers Middleware

**Epic:** Security Headers para Todos os Serviços
**Data:** 2026-04-14
**Prioridade:** P0 (Crítica)
**Estimativa:** 2-3 dias

---

## 1. Objetivo

Implementar middleware de segurança compartilhado para adicionar headers de segurança HTTP em todos os serviços FastAPI do Neural Hive Mind.

---

## 2. Headers a Implementar

| Header | Valor | Propósito |
|--------|-------|-----------|
| X-Content-Type-Options | nosniff | Prevenir MIME-sniffing |
| X-Frame-Options | DENY | Prevenir clickjacking |
| Content-Security-Policy | default-src 'self' | Prevenir XSS |
| Strict-Transport-Security | max-age=31536000 | Forçar HTTPS |
| X-XSS-Protection | 1; mode=block | Proteção XSS extra |

---

## 3. Abordagem de Implementação

### 3.1 Criar Middleware SecurityHeaders

**Arquivo:** `/libraries/security/neural_hive_security/security_headers.py`

```python
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.base import Request as StarletteRequest

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware para adicionar headers de segurança"""

    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "X-XSS-Protection": "1; mode=block",
        })
        return response
```

### 3.2 Integrar em Serviços FastAPI

**Modelo de integração:**

```python
from neural_hive_security.security_headers import SecurityHeadersMiddleware

app = FastAPI()
app.add_middleware(SecurityHeadersMiddleware)
```

---

## 4. Tickets (Decomposição)

| Ticket | Descrição | Estimativa |
|--------|-----------|------------|
| SEC-001-01 | Criar middleware SecurityHeaders | 0.5 dia |
| SEC-001-02 | Integrar em serviços core (8 serviços) | 1 dia |
| SEC-001-03 | Integrar em serviços especialistas (5 serviços) | 0.5 dia |
| SEC-001-04 | Testar security headers | 0.5 dia |

### Serviços Core:

1. gateway-intencoes
2. consensus-engine
3. semantic-translation-engine
4. orchestrator-dynamic
5. approval-service
6. worker-agents
7. queen-agent
8. service-registry

### Serviços Especialistas:

1. specialist-architecture
2. specialist-business
3. specialist-technical
4. specialist-behavior
5. specialist-evolution

---

## 5. Critérios de Aceite

- [ ] Middleware `SecurityHeadersMiddleware` criado
- [ ] Todos os 13 serviços usam o middleware
- [ ] Headers configurados corretamente
- [ ] Testes automatizados validam headers
- [ ] Documentação atualizada

---

## 6. Testes

```python
# tests/unit/test_security_headers.py

def test_security_headers_middleware():
    """Testa middleware adiciona headers corretos"""
    middleware = SecurityHeadersMiddleware(app)

    async def call_next(request):
        return Response(content="OK", status_code=200)

    response = await middleware.dispatch(mock_request, call_next)
    
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
```

```bash
# Teste manual
curl -I http://service:8000/health
# Deve mostrar os headers de segurança
```

---

## 7. Handoff para Implementação

**Branch:** `feat/SEC-001-headers`

**Comandos:**
```bash
git checkout -b feat/SEC-001-headers

# Criar middleware
# ... libraries/security/neural_hive_security/security_headers.py

# Integrar em cada serviço
# ... modificar main.py de cada serviço

# Testes
pytest tests/unit/test_security_headers.py

# Commit
git add .
git commit -m "feat(sec): implement security headers middleware"
```

---

**Spec criada para:** SEC-001-HEADERS
**Data:** 2026-04-14
