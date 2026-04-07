# Spec: Incident Timeline Generator

> Data: 2026-04-07
> Status: VALIDADO
> Serviço: explainability-api
> Componente: TemporalTracker

## Visão Geral

O Incident Timeline Generator é um componente de tracking temporal que permite analisar a evolução de decisões ao longo do tempo, fornecendo insights sobre sessões de decisão, janelas temporais e mudanças de senioridade de especialistas.

## Localização

**Implementação Principal:**
- Arquivo: `services/explainability-api/src/services/temporal_tracker.py`
- LOC: 304 linhas

**Testes:**
- Arquivo: `services/explainability-api/tests/test_temporal_tracker.py`
- LOC: 644 linhas
- Testes: 16 testes unitários

**API Endpoints:**
- Router: `services/explainability-api/src/api/routes/v3/hierarchical.py`
- Prefixo: `/api/v3/explainability`
- Endpoints temporais:
  - `GET /api/v3/explainability/{decision_id}/temporal`
  - `POST /api/v3/explainability/batch` (com include_temporal)
  - `POST /api/v3/explainability/{decision_id}/full` (com include_temporal)

## Funcionalidades Validadas

### 1. Session Analysis (Análise de Sessão)

**Método:** `get_current_session(decision_id: str)`

**Propósito:** Analisa todas as decisões pertencentes à mesma sessão (mesmo `plan_id`).

**Retorno:**
```python
{
    "session_id": "plan_123",              # ID da sessão
    "decision_count": 3,                   # Número de decisões na sessão
    "timeline": [...],                     # Lista de decisões ordenadas
    "first_decision": {...},               # Primeira decisão da sessão
    "last_decision": {...},                # Última decisão da sessão
    "duration_hours": 2.5                  # Duração em horas
}
```

**Casos de Uso:**
- Rastrear todas as decisões de um plano cognitivo
- Identificar padrões de decisão ao longo de uma sessão
- Calcular duração de sessões de decisão

**Testes Validados:**
- `test_get_current_session_with_plan_id` - Sessão com plan_id válido
- `test_get_current_session_reference_not_found` - Decisão de referência não existe
- `test_get_current_session_without_plan_id` - Decisão sem plan_id

### 2. Window Analysis (Análise de Janela Temporal)

**Método:** `get_window_analysis(days: int = 7)`

**Propósito:** Analisa decisões dentro de uma janela temporal configurável (7d, 30d).

**Retorno:**
```python
{
    "window_days": 7,                      # Tamanho da janela
    "decision_count": 25,                  # Total de decisões
    "approve_count": 20,                   # Decisões approve
    "reject_count": 5,                     # Decisões reject
    "approve_rate": 0.8,                   # Taxa de aprovação
    "daily_breakdown": {                   # Decisões por dia
        "2026-04-01": 5,
        "2026-04-02": 8,
        ...
    }
}
```

**Casos de Uso:**
- Monitorar volume de decisões por período
- Calcular taxa de aprovação trends
- Identificar padrões sazonais
- Dashboard de métricas temporais

**Testes Validados:**
- `test_get_window_analysis_7_days` - Janela de 7 dias
- `test_get_window_analysis_30_days` - Janela de 30 dias
- `test_get_window_analysis_empty` - Janela vazia
- `test_get_window_analysis_daily_breakdown` - Breakdown diário

### 3. Seniority Changes Tracking

**Método:** `get_seniority_changes(specialists: List[str], days: int = 30)`

**Propósito:** Busca mudanças de senioridade recentes para especialistas específicos.

**Retorno:**
```python
{
    "period_days": 30,                     # Período analisado
    "change_count": 3,                     # Número de mudanças
    "changes": [                           # Lista de mudanças
        {
            "specialist_id": "spec_1",
            "specialist_name": "Business Specialist",
            "domain": "BUSINESS",
            "previous_level": "mid_level",
            "new_level": "senior",
            "changed_at": "2026-04-01T10:00:00Z",
            "changed_by": "system",
            "change_reason": "performance_based"
        },
        ...
    ],
    "specialists_with_changes": ["spec_1", "spec_2"]
}
```

**Casos de Uso:**
- Auditoria de mudanças de senioridade
- Identificar especialistas promovidos/rebaixados
- Tracking de evolução de especialidade

**Testes Validados:**
- `test_get_seniority_changes_recent` - Mudanças recentes
- `test_get_seniority_changes_no_changes` - Sem mudanças
- `test_get_seniority_changes_filtered_by_specialist` - Filtro por especialistas

### 4. Seniority Distribution

**Método:** `_get_seniority_distribution(since: Optional[datetime] = None)`

**Propósito:** Calcula distribuição de senioridade desde uma data (interno).

**Retorno:**
```python
{
    "period_start": "2026-03-08T00:00:00Z",  # Início do período
    "total_count": 15,                         # Total de especialistas
    "by_level": {                              # Contagem por nível
        "trainee": 2,
        "junior": 3,
        "mid_level": 5,
        "senior": 4,
        "expert": 1
    },
    "percentages": {                           # Porcentagem por nível
        "trainee": 0.133,
        "junior": 0.2,
        "mid_level": 0.333,
        "senior": 0.267,
        "expert": 0.067
    }
}
```

**Casos de Uso:**
- Análise de maturidade da equipe
- Planejamento de capacitação
- Dashboard de distribuição de skills

**Testes Validados:**
- `test_get_seniority_distribution_all_levels` - Todos os níveis
- `test_get_seniority_distribution_with_duplicates` - Sobrescreve mudanças antigas
- `test_get_seniority_distribution_empty` - Dados vazios

### 5. Parse Cursor Helper

**Método:** `_parse_cursor(cursor)`

**Propósito:** Helper para converter cursor MongoDB em lista, removendo `_id`.

**Testes Validados:**
- `test_parse_cursor_removes_id` - Remove _id dos resultados
- `test_parse_cursor_empty` - Cursor vazio
- `test_parse_cursor_multiple_items` - Múltiplos itens

## Integrações

### 1. MongoDB

**Coleções:**
- `explainability_ledger` - Ledger de decisões
- `seniority_history` - Histórico de mudanças de senioridade

**Migration:**
- `m004_seniority_history.py` - Cria coleção e índices

**Índices Otimizados:**
```python
# specialist_id + changed_at (para histórico de um especialista)
[("specialist_id", 1), ("changed_at", -1)]

# domain + changed_at (para histórico por domínio)
[("domain", 1), ("changed_at", -1)]

# changed_at (para consultas temporais)
[("changed_at", 1)]
```

### 2. Repository Layer

**SeniorityHistoryRepository:**
- Arquivo: `src/repositories/seniority_history_repo.py`
- Métodos:
  - `save_change()` - Salva mudança de senioridade
  - `get_history()` - Busca histórico de um especialista
  - `get_recent_changes()` - Mudanças recentes de múltiplos especialistas
  - `get_by_domain()` - Mudanças por domínio

### 3. API v3 Integration

**V3ExplanationService:**
- Integra `TemporalTracker` com `HierarchicalExplainer` e `CounterfactualAnalyzer`
- Fornece endpoints REST para análise temporal

**Endpoints Disponíveis:**
```python
# Análise temporal isolada
GET /api/v3/explainability/{decision_id}/temporal

# Explicação completa (incluindo temporal)
POST /api/v3/explainability/{decision_id}/full
Body: { "include_temporal": true }

# Batch explanations (incluindo temporal)
POST /api/v3/explainability/batch
Body: {
  "decision_ids": [...],
  "include_temporal": true
}
```

## Observabilidade

### Logging

**Structured Logging (structlog):**
```python
logger.info(
    "temporal_tracker.reference_decision_not_found",
    decision_id=decision_id
)
```

**Eventos Logados:**
- `temporal_tracker.reference_decision_not_found` - Decisão de referência não encontrada
- `seniority_change_saved` - Mudança de senioridade salva

### Métricas Prometheus

**Disponíveis em V3:**
```python
# Métricas gerais de explainability
neural_hive_explainability_queries_total{query_type="temporal",status="success"}
neural_hive_explainability_query_duration_seconds{query_type="temporal"}
```

## Testes

### Cobertura de Testes

**Total de Testes:** 16 testes unitários

**Distribuição:**
- Session Analysis: 3 testes
- Window Analysis: 4 testes
- Seniority Changes: 3 testes
- Seniority Distribution: 3 testes
- Parse Cursor Helper: 3 testes

### Mocks Utilizados

**AsyncCursorMock:**
- Mock cursor MongoDB que suporta `sort()` e é async iterável
- Simula ordenação descendente por `changed_at`

**AsyncIteratorMock:**
- Mock iterator para loops `async for`

**_create_mock_mongo_client:**
- Cria mock completo do MongoDB client
- Suporta filtros por `plan_id`, `specialist_id`, `changed_at`
- Filtra dados baseado em queries

## Documentação

### Código

**Docstrings Completas:**
- Todos os métodos públicos têm docstrings Google style
- Descrição de propósito, argumentos e retornos
- Exemplos de uso em comentários

### API Documentation

**OpenAPI/Swagger:**
- Disponível via FastAPI autodoc
- Modelos Pydantic documentados
- Exemplos de request/response

### Documentação Específica

**V3 API:**
- `services/explainability-api/README_V3.md` - Documentação da API v3

## Configuração

### Variáveis de Ambiente

```bash
# Feature flag para API v3
ENABLE_V3_API=true

# MongoDB connection
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=neural_hive
```

### Feature Flags

```python
# Ativar endpoints v3
ENABLE_V3_API = os.getenv("ENABLE_V3_API", "false").lower() == "true"
```

## Status de Validação

### ✅ VALIDADO

**Implementação:** COMPLETA (304 LOC)

**Testes:** COMPLETOS (16 testes, 644 LOC)

**Integração:** COMPLETA
- MongoDB com migration M004
- Repository layer implementado
- API v3 endpoints funcionais

**Observabilidade:** COMPLETA
- Structured logging
- Métricas Prometheus

**Documentação:** COMPLETA
- Docstrings
- API docs
- README V3

## Superpoderes Confirmados

1. **Temporal Session Tracking** - Rastreia decisões do mesmo plano
2. **Window Analysis** - Analisa decisões em janelas temporais
3. **Seniority Evolution** - Tracking de mudanças de senioridade
4. **Distribution Analysis** - Calcula distribuição de senioridade
5. **API Integration** - Endpoints REST funcionais
6. **Observability** - Logging e métricas completas
7. **Test Coverage** - 16 testes unitários robustos
8. **Documentation** - Docstrings e API docs completas

## Próximos Passos

**Recomendações:**
1. ✅ Componente validado e pronto para uso
2. ✅ Testes passando
3. ✅ Integração com API v3 completa
4. ✅ Documentação completa

**Opcional (Futuro):**
- Adicionar análise de tendências (trend detection)
- Adicionar cálculo de volatilidade de senioridade
- Adicionar alertas baseados em mudanças drásticas

## Conclusão

O Incident Timeline Generator está **100% implementado e validado**, com testes completos, integração funcional e documentação abrangente. O componente está pronto para uso em produção como parte da Explainability API v3.

---

**Validado por:** Claude Code (Revalidação Fase 3)
**Data de Validação:** 2026-04-07
**Status:** ✅ APROVADO
