# Handoff Document - Fase 2.4-2.13 Execution Gaps

**Para:** Claude Code (AI Agent)
**De:** Product Owner
**Data:** 2026-04-06
**Epic:** EXE-001 a EXE-009

---

## Resumo Executivo

Este epic consolida todos os gaps da Fase 2.4-2.13 (Execução) do Neural Hive-Mind. A fase está atualmente em 94.6% de completude, com 9 componentes necessitando de refinamentos para atingir 100%.

### Status dos Componentes

| Componente | Completude | Gap Principal | Prioridade |
|------------|-----------|---------------|------------|
| Analyst Agents | 85% | Testes integração multi-source | High |
| MCP Tool Catalog | 94.8% | Corner cases validação | Medium |
| Self-Healing Engine | 94% | Recovery multi-pod | High |
| Worker Agents | 100% | Refinamentos coordenação | Low |
| Queen Agent | 100% | Validação partição rede | Medium |
| Scout Agent | 100% | Linguagens edge cases | Low |
| Optimizer Agents | 100% | Validação auto-apply | Medium |
| Code Forge | 100% | IaC multi-cloud edge | Low |
| Execution Tickets | 100% | Idempotency races | Low |

---

## Como Usar Esta Spec

### 1. Leia os Documentos em Ordem

```
1. spec-lite.md           (5 minutos) - Visão geral
2. spec.md                (15 minutos) - Requisitos completos
3. sub-specs/tickets.md   (20 minutos) - Backlog detalhado
4. sub-specs/roadmap.md   (10 minutos) - Timeline
5. sub-specs/technical-spec.md (30 minutos) - Detalhes técnicos
```

### 2. Comece pelo Sprint 1

O primeiro sprint foca nos dois componentes mais críticos:
- **EXE-001:** Analyst Agents (85% → 100%)
- **EXE-002:** MCP Tool Catalog (94.8% → 100%)

### 3. Siga o Workflow Agent OS

```bash
# Para começar a implementação:
/create-spec

# Para executar tarefas:
/execute-tasks

# Para revisão de código:
/code-review
```

---

## Quick Start - Sprint 1

### Ticket 1: EXE-001-01 - Testes Integração Multi-Source

**Arquivo:** `services/analyst-agents/tests/integration/test_multi_source_aggregation.py`

**O que fazer:**
1. Criar testes de integração para agregação multi-fonte
2. Cobrir cenários de falha em fontes individuais
3. Validar consistência do Data Fusion Engine

**Critérios de aceite:**
- [ ] 5+ testes de integração implementados
- [ ] Todos os testes passando
- [ ] Cobertura >80% para código de agregação

### Ticket 2: EXE-001-02 - Edge Cases PostgreSQL

**Arquivo:** `services/analyst-agents/src/clients/postgresql_client.py`

**O que fazer:**
1. Implementar timeout configurável por query
2. Adicionar retry logic com exponential backoff
3. Connection pool validation

**Critérios de aceite:**
- [ ] Timeout configurável via settings
- [ ] Retry com backoff implementado
- [ ] Testes de timeout passando

---

## Comandos Úteis

### Setup do Ambiente

```bash
cd /home/jimy/NHM/Neural-Hive-Mind

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -e libraries/python/neural_hive_domain
pip install -e libraries/python/neural_hive_specialists
pip install -e services/analyst-agents
pip install -e services/mcp-tool-catalog

# Run tests
pytest services/analyst-agents/tests/
pytest services/mcp-tool-catalog/tests/
```

### Linting e Formatação

```bash
# Linting
ruff check services/analyst-agents/src/
ruff check services/mcp-tool-catalog/src/

# Formatação
black services/analyst-agents/src/
black services/mcp-tool-catalog/src/

# Type checking
mypy services/analyst-agents/src/
mypy services/mcp-tool-catalog/src/
```

### Testes Específicos

```bash
# Unit tests
pytest services/analyst-agents/tests/unit/ -v

# Integration tests
pytest services/analyst-agents/tests/integration/ -v

# E2E tests
pytest tests/e2e/test_execution_layer_complete.py -v

# Coverage
pytest --cov=services/analyst-agents/src --cov-report=html
```

---

## Estrutura de Diretórios

```
services/
├── analyst-agents/
│   ├── src/
│   │   ├── api/
│   │   ├── clients/
│   │   │   └── postgresql_client.py  # MODIFICAR
│   │   ├── services/
│   │   │   └── analytics_engine.py
│   │   └── models/
│   └── tests/
│       ├── unit/
│       └── integration/
│           └── test_multi_source_aggregation.py  # CRIAR
├── mcp-tool-catalog/
│   ├── src/
│   │   └── services/
│   │       ├── schema_validator.py  # MODIFICAR
│   │       └── security_validator.py  # MODIFICAR
│   └── tests/
│       ├── unit/
│       └── integration/
└── self-healing-engine/
    ├── src/
    │   └── services/
    │       ├── recovery_orchestrator.py  # MODIFICAR
    │       └── degradation_manager.py  # CRIAR
    └── tests/
        └── chaos/
            └── test_multi_failure_scenarios.py  # CRIAR
```

---

## Padrões a Seguir

### 1. Testes

```python
import pytest
from unittest.mock import AsyncMock, patch

class TestMultiSourceAggregation:
    """Testes para agregação multi-fonte."""

    @pytest.mark.asyncio
    async def test_aggregate_mongodb_postgresql_sources(self):
        """Testa agregação de MongoDB e PostgreSQL."""
        # Arrange
        analytics = AnalyticsEngine()

        # Act
        result = await analytics.aggregate_sources([...])

        # Assert
        assert result.total_records > 0
        assert result.sources_count == 2
```

### 2. Logging

```python
import structlog

logger = structlog.get_logger(__name__)

logger.info(
    "multi_source_aggregation_started",
    sources_count=len(sources),
    source_types=[s.type for s in sources],
)
```

### 3. Error Handling

```python
from services.analyst_agents.src.exceptions import (
    AggregationError,
    SourceTimeoutError,
)

try:
    result = await analytics.aggregate(sources)
except SourceTimeoutError as e:
    logger.warning("source_timeout", source=e.source, timeout=e.timeout)
    # Fallback logic
except AggregationError as e:
    logger.error("aggregation_failed", error=str(e))
    raise
```

---

## Configuração de Variáveis de Ambiente

### Criar arquivo `.env.test`:

```bash
# Analyst Agents
ANALYST_MULTI_SOURCE_TIMEOUT=30
ANALYST_QUERY_RETRY_MAX=3
ANALYST_FUSION_ENGINE_MAX_SOURCES=10

# MCP Tool Catalog
MCP_SCHEMA_VALIDATION_STRICT=true
MCP_PII_DETECTION_ENABLED=true

# Self-Healing
SELF_HEALING_CHAOS_ENABLED=false
SELF_HEALING_DEGRADATION_CPU_THRESHOLD=80
```

---

## Métricas e Observabilidade

### Métricas a Expor

```python
from prometheus_client import Counter, Histogram

# Analyst Agents
aggregation_duration = Histogram(
    'analyst_aggregation_duration_seconds',
    'Tempo de agregação multi-source',
    ['source_type']
)

aggregation_errors = Counter(
    'analyst_aggregation_errors_total',
    'Erros de agregação',
    ['error_type']
)

# MCP Tool Catalog
schema_validation_duration = Histogram(
    'mcp_schema_validation_duration_seconds',
    'Tempo de validação de schema'
)

security_violations = Counter(
    'mcp_security_violations_total',
    'Violações de segurança detectadas',
    ['violation_type']
)
```

---

## Checklist de Handoff

### Antes de Começar

- [ ] Virtual environment ativado
- [ ] Dependências instaladas
- [ ] Variáveis de ambiente configuradas
- [ ] Branch criada: `feat/EXE-001-analyst-mcp-gaps`

### Durante Implementação

- [ ] Seguir padrões de código existentes
- [ ] Escrever testes antes da implementação (TDD)
- [ ] Commits pequenos e frequentes
- [ ] Mensagens de commit following conventional commits

### Antes de Pr

- [ ] Todos os testes passando
- [ ] Linting sem erros
- [ ] Cobertura >80%
- [ ] Documentação atualizada
- [ ] Self-review do PR

---

## Suporte e Dúvidas

### Documentos de Referência

- `docs/feature-map.md` - Visão geral de features
- `docs/ANALISE_CONSOLIDADA_AGENTES_2026-03-31.md` - Análise detalhada
- `CLAUDE.md` - Regras do projeto

### Contatos

- Tech Lead: [Disponível no Slack]
- ML Engineer: [Disponível no Slack]
- DevOps Engineer: [Disponível no Slack]

---

## Próximos Passos Imediatos

1. **Revisar** `spec-lite.md` para visão geral
2. **Ler** `spec.md` para requisitos completos
3. **Estudar** `sub-specs/tickets.md` para backlog detalhado
4. **Criar** branch `feat/EXE-001-analyst-mcp-gaps`
5. **Começar** pelo ticket EXE-001-01

---

## Notas Importantes

1. **Documentar sempre:** Cada modificação deve vir com documentação
2. **Testes primeiro:** TDD é obrigatório para novas funcionalidades
3. **Não quebrar:** Não modificar código que já funciona sem testes
4. **Commits descritivos:** Usar conventional commits
5. **Pedir review:** PRs pequenos são mais fáceis de revisar

---

**Good luck!** 🚀
