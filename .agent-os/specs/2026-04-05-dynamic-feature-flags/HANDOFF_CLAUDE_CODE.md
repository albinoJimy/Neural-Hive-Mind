# HANDOFF - Claude Code Implementation

> Spec: Dynamic Feature Flags
> Epic: INFRA-003
> Data: 2026-04-05

## Status: Ready for Implementation

Esta spec está pronta para implementação. Execute `/execute-tasks` para começar.

## Estrutura de Arquivos Criada

```
.agent-os/specs/2026-04-05-dynamic-feature-flags/
├── spec.md                    # Especificação completa (overview, user stories, scope)
├── spec-lite.md               # Resumo executivo para contexto AI
├── tasks.md                   # Decomposição em 12 tasks principais
├── HANDOFF_CLAUDE_CODE.md     # Este arquivo
└── sub-specs/
    ├── technical-spec.md      # Especificação técnica detalhada
    ├── database-schema.md     # Schema MongoDB e Redis
    └── api-spec.md            # Especificação REST API completa
```

## Implementação - Guia Rápido

### 1. Criar Serviço

```bash
# Criar estrutura do serviço
mkdir -p services/feature-flag-service/src/{models,services,api,routes,database,observability}
cd services/feature-flag-service
```

### 2. Dependências (requirements.txt)

```txt
# Core
fastapi==0.109.0
pydantic==2.6.0
pydantic-settings==2.1.0
uvicorn[standard]==0.27.0

# Database
motor==3.3.2
redis[hiredis]==5.0.1

# OPA
httpx==0.26.0

# Observability
prometheus-client==0.19.0
opentelemetry-instrumentation-fastapi==0.45b0
structlog==24.1.0

# Testing
pytest==8.0.0
pytest-asyncio==0.23.4
pytest-cov==4.0.0
httpx==0.26.0
```

### 3. Ordem de Implementação

Siga a ordem em `tasks.md`:

**Fase 1: Foundation** (Tasks 1-3)
- Domain Models (FeatureFlag, Condition, RolloutStrategy)
- MongoDB Repository
- Redis Cache Manager

**Fase 2: Core Logic** (Tasks 4-5)
- FeatureFlagService
- RolloutEngine

**Fase 3: API Layer** (Task 6)
- REST API endpoints

**Fase 4: Integration** (Task 7)
- OPA integration (data.external)

**Fase 5: Observability** (Tasks 8-9)
- Prometheus metrics
- Admin UI (opcional)

**Fase 6: Validation** (Tasks 10-12)
- Integration tests
- Documentation
- Deploy

### 4. Variáveis de Ambiente

```bash
# .env.example
FEATURE_FLAG_SERVICE_PORT=8080
REDIS_CLUSTER_NODES=redis-cluster.redis.svc.cluster.local:6379
REDIS_PASSWORD=${REDIS_PASSWORD}
MONGODB_URI=mongodb+srv://...
MONGODB_DATABASE=feature_flags
OPA_URL=http://opa.opa.svc.cluster.local:8181
```

### 5. Configuração OPA

Adicionar em `policies/rego/orchestrator/`:

```rego
# feature_flags_dynamic.rego
package neuralhive.orchestrator.feature_flags_dynamic

import data.external.flags

flags_from_cache := flags.get_all()

# Ver documentação completa em sub-specs/technical-spec.md
```

### 6. Testes

```bash
# Unit tests
pytest services/feature-flag-service/tests/unit/ -v

# Integration tests
pytest services/feature-flag-service/tests/integration/ -v

# E2E com docker-compose
docker-compose -f docker-compose.feature-flags.yml up -d
pytest services/feature-flag-service/tests/e2e/ -v
```

## Pontos de Atenção

### Críticos

1. **Hash Consistency**: O hash determinístico Python e OPA devem usar EXATAMENTE a mesma lógica
2. **Redis SPOF**: Implementar fallback para default values se Redis indisponível
3. **Cache Invalidation**: Sempre invalidar cache após update/delete

### Importantes

1. **OPA Latency**: Cache local no OPA bundle pode reduzir latência
2. **TTL Balance**: 60s é bom compromisso entre consistência e performance
3. **Metrics**: Garantir que Prometheus não vaze dados sensíveis

## Checklist de Implementação

Antes de marcar como completo:

- [ ] Todos os modelos Pydantic criados com validação
- [ ] Repository com CRUD completo funcional
- [ ] Redis cache com TTL e invalidação
- [ ] RolloutEngine com todas as estratégias
- [ ] API REST com 10+ endpoints testados
- [ ] OPA policy atualizada e testada
- [ ] Métricas Prometheus visíveis
- [ ] 80%+ cobertura de testes
- [ ] Documentação OpenAPI gerada
- [ ] Deploy para staging validado

## Próximos Passos

1. Executar `/execute-tasks` para iniciar implementação
2. Criar branch: `feat/INFRA-003-dynamic-feature-flags`
3. Seguir tasks.md em ordem
4. Commitar por task concluída
5. Criar PR ao completar todos os tasks

## Referências

- Especificação atual: `policies/rego/orchestrator/feature_flags.rego`
- Configurações: `services/orchestrator-dynamic/src/config/settings.py`
- Documentação: `docs/FEATURE_FLAGS_GUIDE.md`

## Contato

Para dúvidas durante implementação, consultar:
- Technical Spec: `sub-specs/technical-spec.md`
- API Spec: `sub-specs/api-spec.md`
- Database Schema: `sub-specs/database-schema.md`

---

**Gerado em:** 2026-04-05
**Status:** ✅ Ready for Implementation
**Epic:** INFRA-003
