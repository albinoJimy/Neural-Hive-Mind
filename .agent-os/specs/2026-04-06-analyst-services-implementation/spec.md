# Spec: Analyst Agents - Missing Services Implementation

> **Epic:** Fase 2.4–2.13 Execução - analyst-agents completion
> **Ticket:** ANA-001
> **Priority:** Alta
> **Status:** Planning

## Overview

Implementar os 3 serviços do analyst-agents que atualmente estão como stubs (apenas imports):
- `embedding_service.py` - Serviço de embeddings para busca semântica
- `data_fusion_engine.py` - Motor de fusão de múltiplas fontes de dados
- `query_engine.py` - Motor de consulta otimizado

## Contexto

O analyst-agents está a 75% completo. Os services core (analytics_engine, timeseries_analyzer, causal_analyzer) estão implementados, mas 3 services críticos estão vazios:

**Estado Atual:**
```python
# src/services/embedding_service.py - APENAS IMPORTS
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)
# ... resto do ficheiro vazio
```

## User Stories

### US1: Busca Semântica de Insights

Como **analista**, quero **buscar insights por significado** (não apenas palavras-chave), para **encontrar insights relacionados** mesmo com terminologia diferente.

**Fluxo:**
1. Analyst recebe pergunta em linguagem natural
2. Query é convertida em embedding
3. Sistema busca insights similares no repositório
4. Resultados são ordenados por similaridade semântica
5. Top-N insights são retornados com score de confiança

### US2: Fusão de Dados Multi-Fonte

Como **analista**, quero **combinar dados de múltiplas fontes** (Kafka, MongoDB, ClickHouse, APIs externas), para **ter uma visão consolidada** dos dados.

**Fluxo:**
1. Analyst identifica fontes de dados para análise
2. Sistema busca dados de cada fonte em paralelo
3. Dados são normalizados para schema comum
4. Conflitos são resolvidos com estratégias configuráveis
5. Resultado consolidado é retornado com metadados de proveniência

### US3: Otimização de Queries

Como **analista**, quero **executar queries complexas de forma otimizada**, para **obter resultados rapidamente** mesmo com grandes volumes de dados.

**Fluxo:**
1. Analyst recebe query em linguagem natural ou SQL-like
2. Query é analisada e decomposta em operações
3. Sistema escolhe melhor estratégia de execução
4. Query é executada com otimizações (cache, índices, paralelização)
5. Resultados são agregados e retornados

## Spec Scope

### Componentes a Implementar

1. **EmbeddingService** (`src/services/embedding_service.py`)
   - `generate_embeddings(text: str) -> List[float]` - Gerar embedding usando OpenAI/Anthropic ou local
   - `search_embeddings(query: str, limit: int) -> List[Insight]` - Busca semântica
   - `update_embeddings(text_id: str, text: str)` - Atualizar embedding existente
   - `delete_embeddings(text_id: str)` - Remover embedding

2. **DataFusionEngine** (`src/services/data_fusion_engine.py`)
   - `fuse_data_sources(sources: List[DataSourceConfig]) -> FusedData` - Fundir dados
   - `resolve_conflicts(data: List[dict]) -> dict` - Resolver conflitos
   - `calculate_confidence(data: dict) -> float` - Calcular confiança
   - `get_provenance(data_id: str) -> ProvenanceInfo` - Rastrear origem

3. **QueryEngine** (`src/services/query_engine.py`)
   - `execute_query(query: str) -> QueryResult` - Executar query
   - `parse_query(query: str) -> ParsedQuery` - Analisar query
   - `optimize_query(query: ParsedQuery) -> OptimizedQuery` - Otimizar
   - `validate_query(query: str) -> ValidationResult` - Validar

### Integrações Necessárias

- **MongoDB** - Persistência de embeddings
- **Redis** - Cache de embeddings e queries
- **OpenAI API / Anthropic API** - Geração de embeddings (opcional, pode usar local)
- **ClickHouse** - Analytics data para fusão
- **Kafka** - Event streaming para atualizações

## Out of Scope

- Implementação de modelo de embeddings local (usar API ou biblioteca como sentence-transformers)
- Visualização de dados (dashboard separado)
- Query language completo SQL (apenas subset)

## Expected Deliverable

1. 3 services implementados com interfaces completas
2. Testes unitários para cada service (mínimo 80% cobertura)
3. Integração com API V2 do analyst-agents
4. Documentação de uso dos novos endpoints

## Technical Constraints

- Python 3.12+
- Async/await para I/O
- Type hints obrigatórios
- Logs estruturados com structlog
- Métricas Prometheus para operações críticas
