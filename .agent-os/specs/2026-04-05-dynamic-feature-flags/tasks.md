# Spec Tasks

## Tasks

- [ ] 1. FeatureFlag Domain Models - Definir schema de dados
  - [ ] 1.1 Write tests for FeatureFlag model
  - [ ] 1.2 Implementar FeatureFlag model (id, name, enabled, rollout_strategy, conditions)
  - [ ] 1.3 Implementar RolloutStrategy models (percentage, whitelist, canary)
  - [ ] 1.4 Implementar Condition models (namespace, tenant, risk_band)
  - [ ] 1.5 Verificar todos os testes passam

- [ ] 2. FeatureFlag Repository - Persistência em MongoDB
  - [ ] 2.1 Write tests for FeatureFlagRepository
  - [ ] 2.2 Implementar CRUD básico (create, read, update, delete)
  - [ ] 2.3 Implementar query by name e by status
  - [ ] 2.4 Implementar batch operations
  - [ ] 2.5 Verificar todos os testes passam

- [ ] 3. Redis Cache Layer - Cache distribuído para avaliações
  - [ ] 3.1 Write tests for FlagCacheManager
  - [ ] 3.2 Implementar get_flag() com cache hit/miss
  - [ ] 3.3 Implementar set_flag() com TTL configurável
  - [ ] 3.4 Implementar invalidate_flag() e invalidate_all()
  - [ ] 3.5 Implementar cache warming on startup
  - [ ] 3.6 Verificar todos os testes passam

- [ ] 4. FeatureFlagService - Lógica de negócio
  - [ ] 4.1 Write tests for FeatureFlagService
  - [ ] 4.2 Implementar create_flag() com validação
  - [ ] 4.3 Implementar update_flag() com invalidação de cache
  - [ ] 4.4 Implementar delete_flag() com cleanup
  - [ ] 4.5 Implementar evaluate_flag() com rollout logic
  - [ ] 4.6 Implementar list_flags() com filtros
  - [ ] 4.7 Verificar todos os testes passam

- [ ] 5. RolloutStrategy Engine - Estratégias de rollout
  - [ ] 5.1 Write tests for RolloutStrategyEngine
  - [ ] 5.2 Implementar percentage_rollout() (hash-based deterministic)
  - [ ] 5.3 Implementar whitelist_strategy() (tenant/namespace allowlist)
  - [ ] 5.4 Implementar canary_strategy() (host-based)
  - [ ] 5.5 Implementar gradual_rollout() (ramp up over time)
  - [ ] 5.6 Verificar todos os testes passam

- [ ] 6. REST API - FastAPI endpoints
  - [ ] 6.1 Write tests for FeatureFlagController
  - [ ] 6.2 Implementar POST /api/v1/feature-flags (create)
  - [ ] 6.3 Implementar GET /api/v1/feature-flags (list)
  - [ ] 6.4 Implementar GET /api/v1/feature-flags/{id} (get)
  - [ ] 6.5 Implementar PUT /api/v1/feature-flags/{id} (update)
  - [ ] 6.6 Implementar DELETE /api/v1/feature-flags/{id} (delete)
  - [ ] 6.7 Implementar POST /api/v1/feature-flags/{id}/toggle (toggle)
  - [ ] 6.8 Implementar GET /api/v1/feature-flags/evaluate (evaluate)
  - [ ] 6.9 Implementar POST /api/v1/feature-flags/batch (batch update)
  - [ ] 6.10 Verificar todos os testes passam

- [ ] 7. OPA Integration - Atualizar policy para usar Redis
  - [ ] 7.1 Write tests para integração OPA+Redis
  - [ ] 7.2 Implementar data.external.http no OPA para consultar Redis
  - [ ] 7.3 Atualizar feature_flags.rego para usar dados dinâmicos
  - [ ] 7.4 Implementar fallback para valores default se Redis indisponível
  - [ ] 7.5 Verificar todos os testes E2E passam

- [ ] 8. Metrics & Observability - Prometheus + Grafana
  - [ ] 8.1 Write tests para metrics collector
  - [ ] 8.2 Implementar FeatureFlagMetrics (toggle_count, eval_latency, cache_hit_ratio)
  - [ ] 8.3 Expor metrics em /metrics endpoint
  - [ ] 8.4 Criar dashboard Grafana (JSON)
  - [ ] 8.5 Configurar alertas Prometheus (latência > 100ms)
  - [ ] 8.6 Verificar métricas visíveis no Grafana

- [ ] 9. Admin UI - Dashboard básico
  - [ ] 9.1 Write tests para UI endpoints
  - [ ] 9.2 Implementar GET /admin/feature-flags (dashboard HTML)
  - [ ] 9.3 Implementar JS para toggle interativo
  - [ ] 9.4 Implementar visualização de métricas
  - [ ] 9.5 Verificar UI funcional

- [ ] 10. Integration Tests - E2E com docker-compose
  - [ ] 10.1 Testar CRUD completo via API
  - [ ] 10.2 Testar rollout gradual com OPA
  - [ ] 10.3 Testar invalidação de cache
  - [ ] 10.4 Testar fallback se Redis indisponível
  - [ ] 10.5 Testar métricas Prometheus
  - [ ] 10.6 Verificar todos os testes E2E passam

- [ ] 11. Documentation - API docs e operação
  - [ ] 11.1 Gerar OpenAPI spec (FastAPI auto)
  - [ ] 11.2 Criar FEATURE_FLAGS_DYNAMIC_GUIDE.md
  - [ ] 11.3 Criar runbook para operação (CREATE, UPDATE, ROLLBACK)
  - [ ] 11.4 Atualizar FEATURE_FLAGS_GUIDE.md com nova integração
  - [ ] 11.5 Criar HELM chart para deploy

- [ ] 12. Deploy & Validation
  - [ ] 12.1 Configurar variáveis de ambiente (.env.example)
  - [ ] 12.2 Deploy para staging (Helm)
  - [ ] 12.3 Validar funcionalidade E2E em staging
  - [ ] 12.4 Configurar monitoring dashboards
  - [ ] 12.5 Handoff document (HANDOFF_CLAUDE_CODE.md)

## Effort Estimation

| Task | Effort | Notes |
|------|--------|-------|
| 1. Domain Models | M | Pydantic models com validação |
| 2. Repository | M | Motor async, índices MongoDB |
| 3. Redis Cache | L | Cluster mode, TTL, warming |
| 4. FeatureFlagService | L | Core lógica, rollback logic |
| 5. Rollout Engine | XL | Deterministic hash, time-based |
| 6. REST API | M | FastAPI, OpenAPI auto |
| 7. OPA Integration | L | data.external, fallback |
| 8. Metrics | M | Prometheus counters/gauges |
| 9. Admin UI | S | HTML+JS básico, SPA simples |
| 10. Integration Tests | L | Docker compose, OPA container |
| 11. Documentation | M | OpenAPI, runbooks |
| 12. Deploy | M | Helm, monitoring |

**Total Effort:** ~8-10 semanas (2 sprints)

## Dependencies

**Blocks:**
- INFRA-002 (OPA Policy Bundle) - deve ser completado primeiro

**Blocked by:**
- Nenhum (pode começar imediatamente)

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Redis SPOF | Fallback para default values |
| Cache inconsistency | TTL curto (60s) + invalidation |
| OPA latency | Cache local no OPA bundle |
| Flag zombie accumulation | Alertas métricas + dashboard |
