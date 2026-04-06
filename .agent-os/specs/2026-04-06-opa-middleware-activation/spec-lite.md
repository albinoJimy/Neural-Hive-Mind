# Spec Summary (Lite)

Ativar o `OPAAuthorizationMiddleware` da biblioteca `neural_hive_opa` no serviço `orchestrator-dynamic`, adicionando uma camada de autorização centralizada via OPA para todas as requisições HTTP da API REST. O middleware já está completamente implementado e testado na biblioteca — esta spec foca apenas na sua ativação e configuração no serviço.

**Key changes:**
1. Adicionar `app.add_middleware(OPAAuthorizationMiddleware)` em `main.py`
2. Configurar flags em `settings.py` (`enable_opa_authorization`, policy path, timeouts)
3. Criar política OPA `neuralhive/orchestrator/authz` para endpoints REST
4. Validar via testes: autorização, negação, cache, circuit breaker, fail-closed

**Success criteria:**
- Requisições sem autenticação são negadas (403)
- Requisições autorizadas passam com latência < 50ms (com cache)
- Falha do OPA resulta em HTTP 503 (fail-closed)
- Métricas Prometheus expostas em `/metrics`
