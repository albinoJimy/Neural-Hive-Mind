# EPIC-201: Multi-Source Aggregation

**ID:** EPIC-201
**Status:** Pending
**Priority:** P1 - Alta
**Effort:** L (3 semanas)
**Related Service:** analyst-agents

---

## Resumo Executivo

Completar a feature de multi-source aggregation em analyst-agents. Hoje o serviço tem conectores para 3 das 4 fontes principais (MongoDB, ClickHouse, Neo4j) mas falta PostgreSQL, e a consolidação de dados é apenas agregação de resultados separados, sem verdadeira fusão de dados. Completude atual: ~40%.

---

## Análise Técnica

### Componentes Existentes

| Fonte | Cliente | Status | Gap |
|-------|---------|--------|-----|
| MongoDB | mongodb_client.py | ✅ 100% | Não integrado no QueryEngine |
| PostgreSQL | - | ❌ 0% | **NÃO EXISTE** |
| ClickHouse | clickhouse_client.py | ✅ 100% | Integrado |
| Neo4j | neo4j_client.py | ✅ 100% | Integrado |
| Elasticsearch | elasticsearch_client.py | ✅ Extra | Funcional |
| Prometheus | prometheus_client.py | ✅ Extra | Funcional |

### consolidate_results() Atual

```python
# ATUAL (muito básico)
def consolidate_results(self, results: Dict) -> Dict:
    consolidated = {}
    for source, result in results.items():
        consolidated[source] = result.get('data', {})
    return consolidated  # Apenas dict separado por fonte
```

**Limitações:**
- Não faz join/cross-source correlation
- Não normaliza esquemas diferentes
- Não trata conflitos de dados
- Não agrega temporalmente

---

## Ticket EPIC-201-01: Criar PostgreSQL Client

**ID:** TICKET-EPIC-201-01
**Priority:** Alta
**Effort:** S (3 dias)

### Tasks

- [ ] 201.01 Criar `src/clients/postgresql_client.py`
- [ ] 201.02 Implementar conexao async com asyncpg
- [ ] 201.03 Implementar `execute_query()` com parametros
- [ ] 201.04 Implementar `get_insights()` - insights do PostgreSQL
- [ ] 201.05 Implementar `get_analyst_actions()` - ações registradas
- [ ] 201.06 Implementar `get_feature_usage()` - uso de features
- [ ] 201.07 Adicionar configuracao em settings.py
- [ ] 201.08 Adicionar variaveis de ambiente (.env.test)
- [ ] 201.09 Criar tests/test_postgresql_client.py
- [ ] 201.10 Testar conexao e queries

### Schema PostgreSQL Esperado

```sql
-- Insights de analistas
CREATE TABLE analyst_insights (
    id UUID PRIMARY KEY,
    plan_id VARCHAR(255),
    analyst_type VARCHAR(50),
    insight_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    INDEX idx_plan_id (plan_id),
    INDEX idx_analyst_type (analyst_type)
);

-- Ações de analistas
CREATE TABLE analyst_actions (
    id UUID PRIMARY KEY,
    insight_id UUID REFERENCES analyst_insights(id),
    action_type VARCHAR(50),
    action_data JSONB,
    executed_at TIMESTAMP WITH TIME ZONE
);
```

### Critérios de Aceite
- [ ] PostgreSQLClient criado com asyncpg
- [ ] Conexao testada com banco real
- [ ] Queries executando corretamente
- [ ] Testes passando

---

## Ticket EPIC-201-02: Criar Data Fusion Engine

**ID:** TICKET-EPIC-201-02
**Priority:** Alta
**Effort:** XL (1 semana)

### Tasks

- [ ] 202.01 Criar `src/services/data_fusion_engine.py`
- [ ] 202.02 Implementar `normalize_schema()` - normaliza dados das fontes
- [ ] 202.03 Implementar `align_temporal()` - alinha timestamps
- [ ] 202.04 Implementar `join_sources()` - cross-source joins
- [ ] 202.05 Implementar `resolve_conflicts()` - conflitos de dados
- [ ] 202.06 Implementar `enrich_with_context()` - enriquecimento
- [ ] 202.07 Criar `src/models/aggregated_result.py`
- [ ] 202.08 Implementar `AggregatedResult` model
- [ ] 202.09 Criar tests/test_data_fusion_engine.py
- [ ] 202.10 Testar fusão com 2 fontes
- [ ] 202.11 Testar fusão com 4 fontes
- [ ] 202.12 Testar resolução de conflitos

### Arquitetura DataFusionEngine

```python
class DataFusionEngine:
    async def fuse_multi_source(
        self, 
        results: Dict[str, Any],
        query_spec: QuerySpec
    ) -> AggregatedResult:
        # 1. Normalizar esquemas
        normalized = await self.normalize_schema(results)
        
        # 2. Alinhar temporalmente
        aligned = await self.align_temporal(normalized, query_spec.time_range)
        
        # 3. Join cross-source
        joined = await self.join_sources(aligned, query_spec.join_keys)
        
        # 4. Resolver conflitos
        resolved = await self.resolve_conflicts(joined)
        
        # 5. Enriquecer
        enriched = await self.enrich_with_context(resolved)
        
        return AggregatedResult(
            sources=list(results.keys()),
            data=enriched,
            fusion_metadata=...
        )
```

### Critérios de Aceite
- [ ] DataFusionEngine criado
- [ ] Normalização de esquemas funcionando
- [ ] Alinhamento temporal funcionando
- [ ] Cross-source joins funcionando
- [ ] Testes com 2, 3, 4 fontes passando

---

## Ticket EPIC-201-03: Integrar Data Fusion no QueryEngine

**ID:** TICKET-EPIC-201-03
**Priority:** Alta
**Effort:** M (4 dias)

### Tasks

- [ ] 203.01 Modificar `src/services/query_engine.py`
- [ ] 203.02 Adicionar PostgreSQLClient no construtor
- [ ] 203.03 Integrar DataFusionEngine
- [ ] 203.04 Refatorar `consolidate_results()` para usar DataFusionEngine
- [ ] 203.05 Adicionar `join_sources()` - novo método
- [ ] 203.06 Adicionar `correlate_metrics()` - correlação cross-source
- [ ] 203.07 Atualizar `src/main.py` - inicializar PostgreSQLClient
- [ ] 203.08 Passar PostgreSQLClient para QueryEngine
- [ ] 203.09 Testar query multi-source completo
- [ ] 203.10 Testar com 4 fontes simultâneas

### QueryEngine Refatorado

```python
class QueryEngine:
    def __init__(
        self,
        mongodb_client,        # NOVO
        postgresql_client,     # NOVO
        clickhouse_client,
        neo4j_client,
        elasticsearch_client,
        prometheus_client,
        redis_client,
        data_fusion_engine     # NOVO
    ):
        self.postgresql_client = postgresql_client
        self.data_fusion_engine = data_fusion_engine
        # ...

    async def query_multi_source(self, query_spec: Dict) -> AggregatedResult:
        # Consultar todas as fontes em paralelo
        results = await self._query_all_sources(query_spec)
        
        # Usar DataFusionEngine para verdadeira fusão
        fused = await self.data_fusion_engine.fuse_multi_source(
            results, 
            query_spec
        )
        
        return fused
```

### Critérios de Aceite
- [ ] PostgreSQLClient integrado
- [ ] DataFusionEngine integrado
- [ ] `consolidate_results()` refatorado
- [ ] Query com 4 fontes funcionando
- [ ] Testes passando

---

## Ticket EPIC-201-04: Nova API Multi-Source

**ID:** TICKET-EPIC-201-04
**Priority:** Média
**Effort:** M (4 dias)

### Tasks

- [ ] 204.01 Criar `src/api/multi_source.py`
- [ ] 204.02 Implementar `POST /api/v1/analytics/query-multi-source`
- [ ] 204.03 Implementar `POST /api/v1/analytics/cross-source-analysis`
- [ ] 204.04 Implementar `GET /api/v1/analytics/sources/status`
- [ ] 204.05 Adicionar schemas de request/response
- [ ] 204.06 Documentar endpoints no OpenAPI
- [ ] 204.07 Criar tests/test_multi_source_api.py
- [ ] 204.08 Testar endpoints com Mock
- [ ] 204.09 Testar integração E2E

### Endpoints API

```python
# POST /api/v1/analytics/query-multi-source
{
    "sources": ["mongodb", "postgresql", "clickhouse", "neo4j"],
    "query": {
        "plan_id": "xxx",
        "time_range": {"start": "2026-03-01", "end": "2026-03-31"},
        "join_keys": ["plan_id", "timestamp"],
        "metrics": ["latency", "throughput", "error_rate"]
    },
    "fusion_options": {
        "normalize_schema": true,
        "align_temporal": true,
        "resolve_conflicts": "latest_wins"
    }
}

# Response:
{
    "sources": ["mongodb", "postgresql", "clickhouse", "neo4j"],
    "fused_data": {
        "plan_metrics": {...},
        "temporal_aligned": {...},
        "cross_correlations": {...}
    },
    "fusion_metadata": {
        "sources_count": 4,
        "records_total": 1500,
        "conflicts_resolved": 5
    }
}
```

### Critérios de Aceite
- [ ] API multi-source criada
- [ ] Endpoints respondendo corretamente
- [ ] OpenAPI documentado
- [ ] Testes E2E passando

---

## Resumo do Epic

| Ticket | Descrição | Effort | Deliverables |
|--------|-----------|--------|--------------|
| EPIC-201-01 | PostgreSQL Client | 3 dias | 1 cliente + tests |
| EPIC-201-02 | Data Fusion Engine | 1 semana | 1 engine + tests |
| EPIC-201-03 | Integração QueryEngine | 4 dias | QueryEngine refatorado |
| EPIC-201-04 | Nova API Multi-Source | 4 dias | 3 endpoints + docs |
| **TOTAL** | | **3 semanas** | **4 fontes funcionando** |

---

## Arquitetura Final

```
                    ┌─────────────────────────────────────┐
                    │        API Layer (FastAPI)          │
                    │  /api/v1/analytics/query-multi-source│
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │         QueryEngine                 │
                    │  - query_multi_source()             │
                    │  - correlate_metrics()              │
                    └─────────────────┬───────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼─────────┐   ┌────────▼────────┐   ┌────────▼────────┐
    │  Data Fusion      │   │ Source Adapters │   │  Source Clients │
    │  Engine           │   │ (normalize)     │   │  - MongoDB      │
    │  - normalize      │   │                 │   │  - PostgreSQL   │
    │  - align_temporal │   │                 │   │  - ClickHouse   │
    │  - join_sources   │   │                 │   │  - Neo4j        │
    └───────────────────┘   └─────────────────┘   └─────────────────┘
```

---

## Handoff para Claude Code

```
@~/.agent-os/instructions/execute-tasks.md

Epic: EPIC-201 - Multi-Source Aggregation
Spec: .agent-os/specs/2026-03-31-sprint2-features-incompletas/
```
