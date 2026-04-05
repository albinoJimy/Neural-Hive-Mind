# Checklist de Validação - Token Bucket Rate Limiting

> Use este checklist para validar que a implementação está completa antes de criar o PR.

## Checklist de Implementação

### 1. Middleware FastAPI
- [ ] `src/middleware/rate_limit_middleware.py` criado
- [ ] Classe `RateLimitMiddleware` implementada
- [ ] `dispatch()` método extrai contexto (tenant/user/endpoint)
- [ ] Headers `RateLimit-*` adicionados nas respostas
- [ ] HTTP 429 retornado com `Retry-After` quando excedido
- [ ] Logs estruturados com contexto completo

### 2. Redis Backend
- [ ] `src/clients/rate_limit_redis.py` criado
- [ ] `RedisTokenBucketBackend` implementado
- [ ] Lua script `refill_and_acquire` funcional
- [ ] Operações atômicas (sem race conditions)
- [ ] TTL automático configurado (1h)
- [ ] Error handling para Redis down

### 3. Configurações Pydantic
- [ ] `src/config/settings.py` estendido
- [ ] `enable_rate_limiting` field adicionado
- [ ] `rate_limit_default_capacity` field adicionado
- [ ] `rate_limit_default_refill_rate` field adicionado
- [ ] `rate_limit_burst_multiplier` field adicionado
- [ ] `rate_limit_tier_limits` field (JSON) adicionado
- [ ] Validators implementados (tier config, burst max)

### 4. Métricas Prometheus
- [ ] `src/metrics/rate_limit_metrics.py` criado
- [ ] `rate_limit_requests_total` Counter implementado
- [ ] `rate_limit_wait_duration_seconds` Histogram implementado
- [ ] `rate_limit_tokens_remaining` Gauge implementado
- [ ] `rate_limit_throttle_total` Counter implementado
- [ ] Métricas visíveis em `/metrics` endpoint
- [ ] Labels corretas (tenant_id, endpoint, status)

### 5. Config por Endpoint
- [ ] `src/config/rate_limit_config.py` criado
- [ ] `RateLimitConfig` dataclass definida
- [ ] `ENDPOINT_RATE_LIMITS` dict populado
- [ ] Lookup function implementada
- [ ] Fallback para default config

### 6. Integração main.py
- [ ] `src/main.py` import middleware
- [ ] Middleware adicionado em `lifespan()`
- [ ] Feature flag verificada antes de aplicar
- [ ] Inicialização correta do Redis backend

## Checklist de Testes

### Unit Tests
- [ ] `tests/unit/test_rate_limit_middleware.py` criado
- [ ] Test: middleware permite dentro do limite
- [ ] Test: middleware nega acima do limite
- [ ] Test: usuários diferentes têm limites separados
- [ ] Test: tier override funciona
- [ ] Test: endpoint specific limit funciona
- [ ] Test: headers RateLimit-* presentes
- [ ] Test: Retry-After calculado corretamente
- [ ] **Todos os unit tests passando**

### Integration Tests
- [ ] `tests/integration/test_rate_limit_integration.py` criado
- [ ] Test: operações Redis são atômicas
- [ ] Test: refill funciona cross-request
- [ ] Test: TTL expira chaves não utilizadas
- [ ] Test: concorrência na mesma chave funciona
- [ ] **Todos os integration tests passando**

### E2E Tests
- [ ] `tests/e2e/test_rate_limit_e2e.py` criado
- [ ] Test: tenant rate limit funciona
- [ ] Test: user rate limit funciona
- [ ] Test: endpoint rate limit funciona
- [ ] Test: burst behavior (2x capacity)
- [ ] Test: métricas Prometheus visíveis
- [ ] Test: recuperação após throttle
- [ ] **Todos os E2E tests passando**

## Checklist de Qualidade

### Linting e Formatação
- [ ] `ruff check .` sem erros
- [ ] `black .` aplicado
- [ ] `mypy` (se aplicável) sem erros

### Cobertura de Testes
- [ ] Cobertura > 80% para código novo
- [ ] `pytest --cov` mostra relatório
- [ ] Sem linhas críticas sem cobertura

### Segurança
- [ ] Nenhum segredo hardcoded
- [ ] Nenhum commit com credenciais
- [ ] Variáveis sensíveis via .env apenas

### Performance
- [ ] Overhead < 5ms (p99) por request
- [ ] Benchmark executado e documentado
- [ ] Redis connection pooling configurado

## Checklist de Documentação

### Documento de Deploy
- [ ] `docs/RATE_LIMITING_DEPLOY.md` criado
- [ ] Variáveis de ambiente documentadas
- [ ] Exemplo de configuração por tier
- [ ] Comandos para verificar métricas
- [ ] Troubleshooting guide incluído
- [ ] Queries Prometheus exemplo

### Código
- [ ] Docstrings Google style em classes/métodos públicos
- [ ] Comments explicando "porquê" (não "o quê")
- [ ] Type hints em funções públicas

## Checklist de Validação Funcional

### Cenário 1: Request Permitida
```bash
# 1. Fazer request dentro do limite
curl -X POST http://localhost:8003/api/v1/workflows \
  -H "Authorization: Bearer <token>" \
  -H "X-Tenant-ID: tenant_123"

# 2. Verificar response
# Esperado: 200 OK
# Esperado: Headers RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset
```

### Cenário 2: Request Negada
```bash
# 1. Fazer muitas requests rapidamente
for i in {1..150}; do
  curl -X POST http://localhost:8003/api/v1/workflows \
    -H "Authorization: Bearer <token>" \
    -H "X-Tenant-ID: tenant_123"
done

# 2. Verificar response
# Esperado: 429 Too Many Requests
# Esperado: Header Retry-After presente
```

### Cenário 3: Métricas Prometheus
```bash
# 1. Consultar métricas
curl http://localhost:9090/metrics | grep rate_limit

# 2. Verificar métricas presentes
# Esperado: rate_limit_requests_total
# Esperado: rate_limit_wait_duration_seconds
# Esperado: rate_limit_tokens_remaining
# Esperado: rate_limit_throttle_total
```

### Cenário 4: Hierarquia de Limites
```bash
# 1. Verificar que tenant premium tem mais limites
# 2. Verificar que user individual tem limite próprio
# 3. Verificar que endpoint específico tem limite próprio
# Esperado: Cada nível respeita seu limite independentemente
```

## Checklist de Deploy

### Pre-Deploy
- [ ] Feature flag `ENABLE_RATE_LIMITING=false` em produção
- [ ] Redis cluster verificado (HA)
- [ ] Métricas Prometheus configuradas
- [ ] Dashboards Grafana criados
- [ ] Alertas configurados (alto throttle rate)

### Deploy (Fase 1 - Shadow Mode)
- [ ] Deploy com feature flag disabled
- [ ] Verificar que requests não são afetadas
- [ ] Coletar métricas baseline por 24h

### Deploy (Fase 2 - Whitelist)
- [ ] Habilitar para 10% do tráfego (whitelist tenants)
- [ ] Monitorar métricas por 24h
- [ ] Verificar que não há falsos-positivos

### Deploy (Fase 3 - Full Rollout)
- [ ] Habilitar para 100% do tráfego
- [ ] Monitorar contínuo por 1 semana
- [ ] Ajustar limites conforme necessário

## Checklist Final

- [ ] **Todos os testes passando** (unit, integration, e2e)
- [ ] **Linting sem erros** (ruff)
- [ ] **Formatação aplicada** (black)
- [ ] **Documentação completa** (deploy + código)
- [ ] **Métricas visíveis** (Prometheus)
- [ ] **Feature flag funcionando** (enable/disable)
- [ ] **Revisão de código concluída** (approval)
- [ ] **PR criado** (com template preenchido)

## Assinatura

**Implementador:** ____________________  **Data:** ________

**Reviewer:** _________________________  **Data:** ________

**Aprovador:** _______________________  **Data:** ________

---

**Nota:** Este checklist deve ser usado como guia. Adapte conforme necessário para o seu contexto.
