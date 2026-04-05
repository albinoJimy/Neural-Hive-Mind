# Spec Tasks

- [ ] 1. Criar estrutura base do Rate Limit Middleware
  - [ ] 1.1 Escrever testes para extração de contexto (tenant/user/endpoint)
  - [ ] 1.2 Criar arquivo `src/middleware/rate_limit_middleware.py`
  - [ ] 1.3 Implementar `RateLimitMiddleware.__init__` com injeção de dependências
  - [ ] 1.4 Implementar `RateLimitMiddleware.dispatch` com lógica de rate limiting
  - [ ] 1.5 Adicionar headers `RateLimit-*` nas respostas
  - [ ] 1.6 Retornar HTTP 429 com `Retry-After` quando excedido
  - [ ] 1.7 Verificar todos os testes passam

- [ ] 2. Implementar Redis Distributed Backend
  - [ ] 2.1 Escrever testes para operações atômicas Redis
  - [ ] 2.2 Criar arquivo `src/clients/rate_limit_redis.py`
  - [ ] 2.3 Implementar `RedisTokenBucketBackend` com operações básicas
  - [ ] 2.4 Implementar Lua script `refill_and_acquire` (evitar race conditions)
  - [ ] 2.5 Adicionar TTL automático para chaves não utilizadas
  - [ ] 2.6 Verificar todos os testes passam

- [ ] 3. Estender Pydantic Settings para Rate Limiting
  - [ ] 3.1 Escrever testes para novas configurações
  - [ ] 3.2 Adicionar campos `rate_limit_*` em `src/config/settings.py`
  - [ ] 3.3 Implementar validação de `rate_limit_tier_limits` (JSON schema)
  - [ ] 3.4 Adicionar validator para `burst_multiplier` (max 5.0)
  - [ ] 3.5 Verificar todos os testes passam

- [x] 4. Implementar Métricas Prometheus
  - [x] 4.1 Escrever testes para métricas Prometheus
  - [x] 4.2 Criar arquivo `src/observability/rate_limit_metrics.py`
  - [x] 4.3 Implementar Counter `rate_limit_requests_total`
  - [x] 4.4 Implementar Histogram `rate_limit_wait_duration_seconds`
  - [x] 4.5 Implementar Gauge `rate_limit_tokens_remaining`
  - [x] 4.6 Implementar Counter `rate_limit_throttle_total`
  - [x] 4.7 Registrar métricas no registry Prometheus existente
  - [x] 4.8 Verificar todas as métricas são expostas em `/metrics`

- [x] 5. Implementar Configuração por Endpoint
  - [x] 5.1 Escrever testes para configuração por endpoint
  - [x] 5.2 Criar arquivo `src/config/rate_limit_config.py`
  - [x] 5.3 Definir `RateLimitConfig` dataclass (capacity, refill_rate, burst_multiplier)
  - [x] 5.4 Implementar `ENDPOINT_RATE_LIMITS` dict com endpoints padrão
  - [x] 5.5 Implementar lógica de lookup de config por (method, path)
  - [x] 5.6 Adicionar fallback para default config se endpoint não listado
  - [x] 5.7 Verificar todos os testes passam

- [x] 6. Integrar Middleware no main.py
  - [x] 6.1 Escrever testes de integração com FastAPI app
  - [x] 6.2 Modificar `src/main.py` para importar middleware
  - [x] 6.3 Adicionar inicialização do middleware em `lifespan` context manager
  - [x] 6.4 Adicionar feature flag `enable_rate_limiting` no settings
  - [x] 6.5 Verificar que middleware funciona com feature flag enabled/disabled
  - [x] 6.6 Verificar todos os testes passam

- [ ] 7. Escrever Testes de Integração
  - [ ] 7.1 Criar `tests/integration/test_rate_limit_integration.py`
  - [ ] 7.2 Testar fluxo completo: request -> middleware -> Redis -> response
  - [ ] 7.3 Testar tier limits (premium/basic/free)
  - [ ] 7.4 Testar burst behavior
  - [ ] 7.5 Testar concorrência (múltiplas requests mesma chave)
  - [ ] 7.6 Testar TTL expiration
  - [ ] 7.7 Verificar todos os testes passam

- [ ] 8. Escrever Testes E2E
  - [ ] 8.1 Criar `tests/e2e/test_rate_limit_e2e.py`
  - [ ] 8.2 Testar com Docker Compose (Redis real)
  - [ ] 8.3 Testar limites tenant-level
  - [ ] 8.4 Testar limites user-level
  - [ ] 8.5 Testar limites endpoint-level
  - [ ] 8.6 Testar métricas Prometheus expostas
  - [ ] 8.7 Testar recuperação após throttle
  - [ ] 8.8 Verificar todos os testes passam

- [x] 9. Criar Documentação de Deploy
  - [x] 9.1 Criar `docs/RATE_LIMITING_DEPLOY.md`
  - [x] 9.2 Documentar variáveis de ambiente
  - [x] 9.3 Documentar exemplo de configuração por tier
  - [x] 9.4 Documentar comandos para verificar métricas
  - [x] 9.5 Adicionar troubleshooting guide
  - [x] 9.6 Incluir exemplos de queries Prometheus

- [ ] 10. Verificar Completude e Qualidade
  - [ ] 10.1 Executar `ruff check .` (linting)
  - [ ] 10.2 Executar `black .` (formatação)
  - [ ] 10.3 Executar `pytest` (todos os testes)
  - [ ] 10.4 Verificar cobertura de testes > 80%
  - [ ] 10.5 Verificar que não há segredos no código
  - [ ] 10.6 Preparar para commit
