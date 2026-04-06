# Fase 2.3 - Integrações: Gaps Críticos Consolidados

**Data:** 2026-04-05
**Status Global:** 61% Completo
**Bloqueadores:** 4 tickets críticos identificados

---

## Resumo Executivo

A Fase 2.3 (Integrações Avançadas) está implementada a 61%, com 3 de 4 componentes principais funcionais. No entanto, 4 gaps críticos bloqueiam o rollout para produção:

| Gap | Prioridade | Impacto | Esforço | Ticket |
|-----|------------|---------|---------|--------|
| ML Preditivo Orphaned | P0 | Auto-scaling inoperacional | 8-10 dias | INFRA-011 |
| Testes E2E Vault/SPIFFE | P0 | Risco de outage | 2-3 dias | QA-005 |
| Vulnerabilidade JWT | P0 | Token substitution attacks | 7 dias | SEC-008 |
| Docs migração etcd→Redis | P1 | Confusão operacional | 1-2 dias | OPS-003 |

**Total Effort:** 18-22 dias de desenvolvimento

---

## Matriz de Implementação Atual

| Componente | Código | Testes | Integração | Score |
|------------|:------:|:------:|:----------:|:-----:|
| Service Registry | 95% | 70% | 95% | **90%** ✅ |
| Vault/SPIFFE | 90% | 0% | 70% | **65%** ⚠️ |
| Feromônios Digitais | 95% | 50% | 95% | **85%** ✅ |
| ML Preditivo | 85% | 80% | **0%** | **40%** ❌ |

---

## Detalhes dos Gaps Críticos

### 1. INFRA-011: LoadPredictor Integration

**Problema:** 1.573 LOC de código ML com 383 testes, mas **zero integração** com serviços.

```
grep -r "from neural_hive_ml import" /services/
# 0 ocorrências
```

**Evidência:**
- `LoadPredictor` em `libraries/python/neural_hive_ml/predictive_models/load_predictor.py` (651 linhas)
- Placeholder `load_predictor: LoadPredictor | None = None` em `intelligent_scheduler.py:62`
- `use_synthetic_data=True` em `_load_historical_data()` (dados falsos)

**Solução:**
1. Criar factory para LoadPredictor no Orchestrator
2. Implementar wrapper com cache Redis (TTL=5min)
3. Enricher ResourceAllocator com `predicted_load_pct`
4. Adicionar métricas Prometheus

**Epic Decomposition:**
- Task 1: Configuração e setup (1 dia)
- Task 2: Inicialização do LoadPredictor (1 dia)
- Task 3: API de previsão de carga (2 dias)
- Task 4: Detecção de bottlenecks (1 dia)
- Task 5: Integração IntelligentScheduler (2 dias)
- Task 6: Enriquecimento ResourceAllocator (1 dia)
- Task 7: Métricas e observabilidade (1 dia)
- Task 8: Testes de integração (1 dia)
- Task 9: Documentação (1 dia)

**Critérios de Aceite:**
- [ ] LoadPredictor inicializado no startup
- [ ] `predict_load(60)` com latência <500ms
- [ ] Bottlenecks detectados até 2h antes
- [ ] Métricas `orchestrator_load_forecast_*` registadas
- [ ] 20+ testes unitários + 5+ integração + 2+ E2E

---

### 2. QA-005: Vault/SPIFFE E2E Tests

**Problema:** Arquivo `/services/orchestrator-dynamic/tests/e2e/test_vault_spiffe_e2e.py` existe mas **está vazio**.

```
wc -l /services/orchestrator-dynamic/tests/e2e/test_vault_spiffe_e2e.py
0 test_vault_spiffe_e2e.py
```

**Evidência:**
- SPIFFE Manager: 577 linhas com JWT-SVID, X.509-SVID, cache, refresh
- Vault Client: 442 linhas com auth methods, token renewal
- 7 testes actuais com 100% mocks

**Solução:**
19 cenários de teste E2E agrupados em 7 categorias:

| Categoria | Cenários | Prioridade |
|-----------|-----------|------------|
| Autenticação | 4 (K8s SA token, JWT SPIFFE) | Alta |
| Secret Management | 4 (KV v2 read/write) | Alta |
| Dynamic Credentials | 3 (PostgreSQL creds) | Média |
| SVID Operations | 5 (JWT/X.509 fetch, refresh) | Alta |
| PKI Operations | 2 (Issue cert, CA chain) | Baixa |
| Fail Modes | 2 (Fail-open/closed) | Média |
| Observabilidade | 2 (Metrics, logging) | Baixa |

**Epic Decomposition:**
- Task 1: Docker Compose infrastructure (0.5 dia)
- Task 2: Vault setup scripts (0.5 dia)
- Task 3: SPIRE setup scripts (0.5 dia)
- Task 4: Pytest fixtures reais (0.5 dia)
- Task 5: Testes autenticação (0.5 dia)
- Task 6: Testes segredos (0.5 dia)
- Task 7: Testes credenciais dinâmicas (0.5 dia)
- Task 8: Testes SVID (0.5 dia)
- Task 9: Testes PKI (0.5 dia)
- Task 10: Testes observabilidade (0.5 dia)
- Task 11: Documentação (0.5 dia)
- Task 12: Execução e validação (0.5 dia)

**Critérios de Aceite:**
- [ ] 19 testes E2E passando
- [ ] Docker Compose funcional (Vault + SPIRE + PostgreSQL)
- [ ] Fixtures substituem mocks
- [ ] Relatório cobertura 100% fluxos críticos

---

### 3. SEC-008: JWT Trust Bundle Validation

**Problema:** `get_trust_bundle_keys()` retorna dict mas **não valida assinatura JWT**.

```python
# spiffe_manager.py:488-495
def get_trust_bundle_keys(self) -> Dict[str, str]:
    """Get parsed public keys from trust bundle for JWT validation"""
    return self._trust_bundle_keys.copy()  # ❌ Retornado mas NÃO usado!
```

**Evidência:**
- Vulnerabilidade em `auth_interceptor.py:213-224`
- `jwt.decode()` usa `public_key` não validada
- Risco: token substitution attacks

**Solução:**

**Arquitetura Proposta:**
```
SPIFFE Manager
    ↓
JWKValidator (novo) - Valida estrutura RFC 7517
    ↓
JWTVerifier (novo) - Verifica assinatura com trust bundle
    ↓
KeyCache (melhoria) - TTL 5min, invalidação
    ↓
Auth Interceptor - Usa apenas chaves validadas
```

**Epic Decomposition:**
- Task 1: JWKValidator com testes (1 dia)
- Task 2: JWTVerifier com testes (1 dia)
- Task 3: KeyCache melhoria (0.5 dia)
- Task 4: Auth interceptor update (1 dia)
- Task 5: Testes segurança (2 dias)
- Task 6: Métricas e logging (0.5 dia)
- Task 7: Documentação (0.5 dia)
- Task 8: Deploy gradativo (0.5 dia)

**Critérios de Aceite:**
- [ ] JWKValidator valida estrutura RFC 7517
- [ ] JWTVerifier verifica assinatura
- [ ] Token substitution attacks bloqueados
- [ ] 30+ testes segurança passando
- [ ] Métricas `jwt_verification_*` registadas
- [ ] Feature flag para rollout seguro

---

### 4. OPS-003: etcd→Redis Migration Documentation

**Problema:** `EtcdClient` é alias para `RedisRegistryClient`, mas configs usam nomes `ETCD_*`.

```python
# main.py:181-187
# Nota: EtcdClient é agora um alias para RedisRegistryClient
self.etcd_client = EtcdClient(
    cluster_nodes=self.settings.ETCD_ENDPOINTS,  # ← Espera Redis endpoints!
    prefix=self.settings.ETCD_PREFIX,
    password=redis_password,
    timeout=self.settings.ETCD_TIMEOUT_SECONDS,
)
```

**Evidência:**
- Comentário no values.yaml: "Apesar do nome 'etcd', agora usa Redis"
- Confusão operacional
- Risco de data loss em upgrade

**Solução:**

**Estratégia de 3 Fases:**

| Versão | Fase | Descrição |
|--------|------|-----------|
| v1.3.0 | Backward Compatibility | Suportar ambos `ETCD_*` e `REGISTRY_REDIS_*` |
| v1.4.0 | Migration | Atualizar Helm charts, migration guide |
| v1.6.0 | Cleanup | Remover `ETCD_*` deprecated |

**Epic Decomposition:**
- Task 1: Renomear configs em settings.py (0.5 dia)
- Task 2: Atualizar main.py para usar RedisRegistryClient (0.5 dia)
- Task 3: Remover alias EtcdClient (0.5 dia)
- Task 4: Atualizar Helm charts (0.5 dia)
- Task 5: Criar migration guide (1 dia)
- Task 6: Criar rollback plan (0.5 dia)
- Task 7: Criar validation checklist (0.5 dia)

**Critérios de Aceite:**
- [ ] Configs renomeadas (`REGISTRY_REDIS_*`)
- [ ] Alias `EtcdClient` removido
- [ ] Migration guide completo
- [ ] Rollback plan documentado
- [ ] Validation checklist operacional

---

## Timeline Consolidada

### Sprint 1 (Semana 1)
**Foco: Infraestrutura crítica**

| Ticket | Tasks | Dias |
|--------|-------|------|
| OPS-003 | Tasks 1-7 (documentação migração) | 1-2 |
| QA-005 | Tasks 1-4 (Docker + fixtures) | 1-2 |

### Sprint 2 (Semana 2)
**Foco: Segurança e testes**

| Ticket | Tasks | Dias |
|--------|-------|------|
| QA-005 | Tasks 5-12 (testes E2E) | 1-2 |
| SEC-008 | Tasks 1-4 (JWKValidator + JWTVerifier) | 2-3 |

### Sprint 3 (Semana 3)
**Foco: Integração ML**

| Ticket | Tasks | Dias |
|--------|-------|------|
| SEC-008 | Tasks 5-8 (testes segurança + deploy) | 2 |
| INFRA-011 | Tasks 1-4 (config + inicialização + API) | 3 |

### Sprint 4 (Semana 4)
**Foco: Finalização**

| Ticket | Tasks | Dias |
|--------|-------|------|
| INFRA-011 | Tasks 5-9 (integração + métricas + docs) | 3 |
| Todos | Validação final e handoff | 2 |

**Total:** 18-22 dias (~4 semanas)

---

## Branches e Git Workflow

### Estrutura de Branches

```bash
# Branches principais
feat/INFRA-011-loadpredictor-integration
feat/QA-005-vault-spiffe-e2e-tests
feat/SEC-008-jwt-trust-bundle-validation
feat/OPS-003-etcd-redis-migration-docs

# Branch de integração (final)
feat/FASE-2.3-final-integration
```

### Estratégia de Merge

1. **Merge individual:** Cada branch faz PR para main
2. **Code review:** Obrigatório para todos os tickets
3. **Testes:** CI/CD executa testes completos
4. **Deploy sequencial:** Ordem recomendada:
   - OPS-003 (documentação, sem risco)
   - QA-005 (testes, sem breaking changes)
   - SEC-008 (segurança, feature flag)
   - INFRA-011 (integração, mais complexo)

---

## Dependências e Blockers

### Grafo de Dependências

```
OPS-003 ──────────────────────────────┐
                                      │
QA-005 ───────────────────────────────┤
                                      │
SEC-008 ──────────────────────────────┤
                                  ┌───┴───┐
                                  │       │
                            INFRA-011   FASE-2.3-COMPLETE
```

### Blockers

| Ticket | Bloqueado por | Motivo |
|--------|---------------|--------|
| INFRA-011 | Nenhum | Pode iniciar imediatamente |
| QA-005 | Nenhum | Infraestrutura Docker independente |
| SEC-008 | Nenhum | Biblioteca isolada |
| OPS-003 | Nenhum | Apenas documentação |

---

## Métricas de Sucesso

### Técnicas

| Métrica | Target | Medição |
|---------|--------|---------|
| LoadPredictor latency | P95 <500ms | Prometheus |
| Forecast accuracy | MAPE <15% | MLflow |
| JWT verification latency | P99 <10ms | Prometheus |
| E2E test pass rate | 100% | Pytest |
| Code coverage | >80% | pytest-cov |

### Negócio

| Métrica | Target | Medição |
|---------|--------|---------|
| SLA violations | -20% | Alerts |
| Throughput | +15% | Metrics |
| Auto-scaling efficiency | >90% | Logs |
| Security incidents | 0 | Audit log |

---

## Handoff para Implementação

### Checklist de Pré-Implementação

- [ ] Specs revisadas por Tech Lead
- [ ] Estimativas aprovadas por Product Owner
- [ ] Dependências externas verificadas (MLflow, SPIRE)
- [ ] Ambientes de testes disponíveis (staging)
- [ ] Acesso a Vault/SPIRE configurado

### Artefactos Prontos

- [x] Spec INFRA-011 (detalhada com TDD tasks)
- [x] Spec QA-005 (19 cenários E2E)
- [x] Spec SEC-008 (arquitetura de segurança)
- [x] Spec OPS-003 (estratégia migração 3 fases)

### Próximos Passos Imediatos

1. **Comenzar com OPS-003** (menor risco, apenas documentação)
2. **Paralelo: QA-005 setup** (Docker Compose infrastructure)
3. **Code review SEC-008** (validar arquitetura de segurança)
4. **Sprint planning INFRA-011** (decompor em dias/horas)

---

## Referências

### Código Fonte

| Componente | Path |
|------------|------|
| LoadPredictor | `/libraries/python/neural_hive_ml/predictive_models/load_predictor.py` |
| SPIFFE Manager | `/libraries/security/neural_hive_security/spiffe_manager.py` |
| Vault Client | `/libraries/security/neural_hive_security/vault_client.py` |
| IntelligentScheduler | `/services/orchestrator-dynamic/src/scheduler/intelligent_scheduler.py` |
| Service Registry | `/services/service-registry/` |

### Documentação

| Documento | Path |
|-----------|------|
| Fase 2.3 Roadmap | `/docs/specs/FASE-2-3-INTEGRACOES.md` |
| Feature Map | `/docs/feature-map.md` |
| Testes E2E | `/tests/phase2-mcp-integration-test.sh` |

---

**Status:** Ready for Implementation
**Next Action:** Criar branch `feat/OPS-003-etcd-redis-migration-docs` e iniciar Task 1
