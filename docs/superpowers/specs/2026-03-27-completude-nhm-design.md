# Design Document — Neural Hive-Mind Completude Implementation

**Data:** 2026-03-27
**Status:** Approved
**Escopo:** Implementação das 4 prioridades críticas identificadas na análise de completude

---

## Resumo Executivo

Este documento define o design para implementar as 4 prioridades críticas do Neural Hive-Mind:

1. **Segurança Crítica** (4h) — JWT hardcoded e CORS wildcard
2. **Testes Coverage** (40h) — Aumentar de 10,81% → 70%
3. **Completude Funcional** (80h) — Worker/Scout Agents + MCP integration
4. **Operacional** (16h) — Limpeza, pinning, multi-stage build

**Estratégia:** Phase 1 sequencial (Segurança) → Phase 2 paralela (3 agents)

---

## Arquitetura da Solução

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: Segurança Crítica (Sessão Atual)                  │
│  Services: gateway-intencoes                                │
│  Executor: Agent Principal                                  │
│  Duration: 4 horas                                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: Execução Paralela                                 │
│                                                             │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ Agent A      │  │ Agent B          │  │ Agent C      │  │
│  │ Testes (40h) │  │ Completude (80h) │  │ Ops (16h)    │  │
│  │ p02-testes   │  │ p03-completude   │  │ p04-operac   │  │
│  └──────────────┘  └──────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Segurança Crítica

### Objetivo
Remover credenciais hardcoded e configurar CORS adequadamente.

### Serviços Afetados
- `services/gateway-intencoes/`

### Mudanças

#### 1. JWT Secret via Environment Variable
**Arquivo:** `src/security/auth.py`
**De:**
```python
payload = jwt.decode(token, "secret", algorithms=["HS256"])
```
**Para:**
```python
jwt_secret = settings.jwt_secret_key
payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
```

#### 2. CORS Configuration
**Arquivo:** `src/config/settings.py`
**De:**
```python
allowed_origins: List[str] = Field(default=["*"])
jwt_secret_key: str = Field(default="your-secret-key")
```
**Para:**
```python
allowed_origins: List[str] = Field(..., description="CORS allowed origins (comma-separated)")
jwt_secret_key: str = Field(..., description="JWT secret key")

@validator('allowed_origins', pre=True)
def parse_cors_origins(cls, v):
    if isinstance(v, str):
        return [origin.strip() for origin in v.split(',')]
    return v
```

#### 3. Startup Validation
Adicionar validação no startup que lança `SettingsError` se variáveis obrigatórias faltarem.

#### 4. Environment Template
Criar `.env.example`:
```bash
# Security
JWT_SECRET_KEY=change-me-in-production
CORS_ORIGINS=http://localhost:3000,https://example.com
```

### Critérios de Sucesso
- ✅ Zero credenciais hardcoded
- ✅ CORS configurado via environment
- ✅ Startup validation funcional
- ✅ Todos testes passam

---

## Phase 2: Execução Paralela

### Agent A: Testes Coverage (40h)

#### Objetivo
Aumentar cobertura de testes de 10,81% → 70% em módulos críticos.

#### Módulos Alvo
| Módulo | Cobertura Atual | Alvo |
|--------|-----------------|------|
| drift_monitoring | 0,00% | 70% |
| observability | 0,00% | 70% |
| compliance | 13,36% | 70% |
| semantic_pipeline | 15,43% | 70% |
| feedback | 21,11% | 70% |
| explainability | 21,46% | 70% |

#### Tasks Principais
1. Baseline de cobertura por módulo
2. Escrever testes unitários para cada módulo alvo
3. Dividir `e2e-tests.yml.disabled` em 6 suites menores (< 30min cada)
4. Implementar mutation testing com `mutmut`
5. Gerar relatório final

### Agent B: Completude Funcional (80h)

#### Objetivo
Transformar stubs em funcionalidades reais.

#### B.1 Worker Agents (40h)
**Arquivo:** `services/worker-agents/src/executors/`

| Executor | Status | Integração Real |
|----------|--------|-----------------|
| BUILD | Stub | Code Forge |
| DEPLOY | Stub | ArgoCD/Flux |
| TEST | Stub | GitHub Actions |
| VALIDATE | Stub | OPA Gatekeeper |
| EXECUTE | Stub | Docker/K8s |
| QUERY | Stub | MongoDB/Redis |
| TRANSFORM | Stub | Pandas/Spark |
| COMPENSATE | Stub | Rollback real |

**Mudança chave:** Remover fallbacks `simulated=True`.

#### B.2 Scout Agents (20h)
**Arquivo:** `services/scout-agents/src/`

- Implementar Kafka consumer real
- Implementar Service Registry gRPC client
- Implementar Pheromone client
- Substituir heurísticas por modelos ML

#### B.3 Code Forge MCP (15h)
**Arquivos:** `services/code-forge/src/pipeline/`

- Modificar `template_selector.py` para usar MCP Tool Catalog
- Modificar `code_composer.py` para usar MCP tools
- Modificar `validator.py` para usar MCP validation

#### B.4 Proto Compilation (5h)
- Compilar protos do analyst-agents
- Compilar protos do optimizer-agents

### Agent C: Operacional (16h)

#### Objetivo
Higiene de repositório e build optimization.

#### Tasks
1. Remover arquivos órfãos (crane, =0.42b0, etc.)
2. Arquivar relatórios históricos em `docs/archive/`
3. Converter `requirements.txt` ranges para versões exatas
4. Criar `requirements.frozen` em todos os serviços
5. Implementar multi-stage Dockerfile no gateway-intencoes

---

## Coordenação entre Agents

### Regras

1. **Sequência:** Phase 1 → Phase 2
2. **Branches:** `feat/pXX-[nome]`
3. **Merge order:** Agent A → B → C
4. **Conflitos:** Resolver via chat + `docs/superpowers/COORDENACAO.md`

### Checkpoint Final
- Todos testes passam
- Sem conflitos pendentes
- Review conjunto

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Conflito de arquivos | Média | Moderado | COORDENACAO.md |
| Agent B excede 80h | Alta | Alto | Revisar no 40h |
| Testes E2E falham | Média | Alto | Suites menores |
| Deps não pinned | Baixa | Moderado | requirements.frozen |

---

## Cronograma

| Semana | Phase | Agent | Horas |
|--------|-------|-------|-------|
| 1 | Phase 1 | Principal | 4h |
| 1-2 | Phase 2 | Agent A (Testes) | 40h |
| 1-3 | Phase 2 | Agent B (Completude) | 80h |
| 1 | Phase 2 | Agent C (Ops) | 16h |

**Total:** ~140h (~3.5 semanas)

---

## Critérios de Aceite

### Phase 1
- ✅ Zero credenciais hardcoded
- ✅ CORS configurado via env
- ✅ Startup validation funcional

### Phase 2
- ✅ Cobertura ≥ 70% em módulos críticos
- ✅ Worker Agents executam tarefas reais
- ✅ Scout Agents consomem eventos reais
- ✅ MCP integration aplicada
- ✅ Repositório limpo + deps pinned

---

## Próximos Passos

1. Criar 4 plans em `docs/superpowers/plans/`
2. Executar Phase 1 (sessão atual)
3. Dispatch 3 parallel agents para Phase 2
4. Review final e merge
