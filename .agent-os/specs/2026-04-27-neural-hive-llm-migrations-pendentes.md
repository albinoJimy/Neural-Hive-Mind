# neural_hive_llm - Serviços Para Migração

**Data:** 2026-04-27
**Status:** ✅ MIGRAÇÃO 100% COMPLETA (9/9 serviços)

---

## Serviços Migrados ✅

| Serviço | Wrapper | Arquivos Migrados | Testes |
|---------|---------|-------------------|--------|
| code-forge | `src/clients/llm_client_wrapper.py` | 1 | ✅ |
| architect-agent | `src/planners/llm_client_wrapper.py` | 4 | ✅ 107 |
| requirements-engineering | `src/clients/llm_client_wrapper.py` | 6 | ✅ 34 |
| documentation-generation | `src/clients/llm_client_wrapper.py` | 5 | ✅ 45 |
| approval-gateway | `src/clients/llm_client_wrapper.py` | 1 | ✅ 74 |
| doc-ingestion | `src/clients/llm_client_wrapper.py` | 1 | ✅ 185 |
| data-migration | `src/clients/llm_client_wrapper.py` | 1 | ✅ 329 |
| knowledge-graph-rag | `src/knowledge_graph_rag/clients/llm_client_wrapper.py` | 1 | ✅ 96 |
| test-generation | `src/clients/llm_client_wrapper.py` | 1 | ✅ 48 |

---

## Resumo Final

**Total de Serviços Migrados:** 9
**Total de Arquivos Migrados:** ~21
**Total de Testes Passando:** 918+

---

## FASE 1: architect-agent ✅ (100%)

**Arquivos migrados:**
- ✅ `src/recommenders/tech_stack.py` - Migrado para `neural_hive_llm.LLMClient`
- ✅ `src/planners/design_planner.py` - Removida dependência `AsyncOpenAI`
- ✅ `src/generators/architecture_diagram_generator.py` - Migrado para `neural_hive_llm.LLMClient`
- ✅ `src/identifiers/bounded_contexts.py` - Migrado para `neural_hive_llm.LLMClient`

**Testes:** ✅ 107 testes passando

---

## FASE 2: requirements-engineering ✅ (100%)

**Arquivos migrados:**
- ✅ `src/services/requirements_engineer.py`
- ✅ `src/services/user_story_generator.py`
- ✅ `src/services/acceptance_criteria_generator.py`
- ✅ `src/services/ui_ux_designer.py`
- ✅ `src/services/data_model_designer.py`
- ✅ `src/services/api_designer.py`

**Testes:** ✅ 34 testes passando

---

## FASE 3: documentation-generation ✅ (100%)

**Arquivos migrados:**
- ✅ `src/services/diagram_generator.py`
- ✅ `src/generators/api_docs_generator.py`
- ✅ `src/services/readme_generator.py`
- ✅ `src/services/code_doc_generator.py`
- ✅ `src/services/architecture_docs_generator.py`

**Testes:** ✅ 45 testes passando

---

## FASE 4: Outros serviços ✅ (100%)

### approval-gateway ✅
- ✅ `src/services/approval_gateway.py`
- **Testes:** ✅ 74 passando

### doc-ingestion ✅
- ✅ `src/services/entity_extractor.py`
- **Testes:** ✅ 185 unitários passando

### data-migration ✅
- ✅ `src/services/schema_mapper.py`
- **Testes:** ✅ 329 passando

---

## FASE 5: Serviços Adicionais ✅ (100%)

### knowledge-graph-rag ✅
- ✅ `src/knowledge_graph_rag/services/knowledge_graph_rag.py`
- ✅ `src/knowledge_graph_rag/clients/llm_client_wrapper.py` (criado)
- **Nota:** Embeddings ainda usam `AsyncOpenAI` diretamente (não suportado pelo neural_hive_llm)
- **Testes:** ✅ 96 passando

### test-generation ✅
- ✅ `src/services/test_generator.py`
- ✅ `src/clients/llm_client_wrapper.py` (criado)
- **Testes:** ✅ 48 passando

---

---

## Serviços Para Migrar (Prioridade Média)

### requirements-engineering (7 arquivos)

| Arquivo | Provider |
|---------|----------|
| `src/services/requirements_engineer.py` | OpenAI |
| `src/services/user_story_generator.py` | OpenAI |
| `src/services/acceptance_criteria_generator.py` | OpenAI |
| `src/services/ui_ux_designer.py` | OpenAI |
| `src/services/data_model_designer.py` | OpenAI |
| `src/services/api_designer.py` | OpenAI |

**Ação:** Criar wrapper e migrar todos

---

### documentation-generation (5 arquivos)

| Arquivo | Provider |
|---------|----------|
| `src/services/diagram_generator.py` | OpenAI |
| `src/generators/api_docs_generator.py` | OpenAI |
| `src/services/readme_generator.py` | OpenAI |
| `src/services/code_doc_generator.py` | OpenAI |
| `src/services/architecture_docs_generator.py` | OpenAI |

**Ação:** Criar wrapper e migrar todos

---

## Serviços Para Migrar (Prioridade Baixa)

### approval-gateway (1 arquivo)

| Arquivo | Provider |
|---------|----------|
| `src/services/approval_gateway.py` | OpenAI |

### doc-ingestion (1 arquivo)

| Arquivo | Provider |
|---------|----------|
| `src/services/entity_extractor.py` | Anthropic, OpenAI |

### data-migration (1 arquivo)

| Arquivo | Provider |
|---------|----------|
| `src/services/schema_mapper.py` | OpenAI, Anthropic |

---

## Plano de Migração

### Fase 1: architect-agent (completo)
- [ ] Migrar recommenders/tech_stack.py
- [ ] Migrar planners/design_planner.py
- [ ] Migrar generators/architecture_diagram_generator.py
- [ ] Migrar identifiers/bounded_contexts.py

### Fase 2: requirements-engineering
- [ ] Criar `src/clients/llm_client_wrapper.py`
- [ ] Migrar todos os 7 arquivos

### Fase 3: documentation-generation
- [ ] Criar `src/clients/llm_client_wrapper.py`
- [ ] Migrar todos os 5 arquivos

### Fase 4: Outros serviços ✅
- [x] approval-gateway ✅
- [x] doc-ingestion ✅
- [x] data-migration ✅

---

## Resumo Final

**Total de Serviços Migrados:** 7 (incluindo code-forge que já estava parcialmente migrado)
**Total de Arquivos Migrados:** ~19
**Total de Testes Passando:** 774+

**Padrão Aplicado:**
1. Criar `src/clients/llm_client_wrapper.py` com wrapper OpenAI-compatível
2. Importar `LLMClient` do wrapper em vez de `AsyncOpenAI` do OpenAI
3. Usar `generate(messages=[...], model=...)` em vez de `chat.completions.create(...)`
4. Acessar resposta via `response.choices[0].message["content"]` (dict)
5. Atualizar mocks nos testes para usar o novo padrão

**Serviços Restantes (NÃO no escopo original):**
- ~~`knowledge-graph-rag`~~ ✅ MIGRADO
- ~~`test-generation`~~ ✅ MIGRADO

**Limitações Conhecidas:**
- `knowledge-graph-rag/embeddings/openai_embedder.py` ainda usa `AsyncOpenAI` diretamente porque `neural_hive_llm` ainda não suporta a API de embeddings. Isso foi documentado no código.

---

## Benefícios da Migração

1. **Código centralizado** - menos duplicação
2. **Observabilidade** - métricas unificadas
3. **Custos** - tracking por serviço
4. **Resilience** - retry + circuit breaker
5. **Flexibilidade** - trocar provider sem mudar código

---

**Total de Serviços Para Migrar: 6**
**Total de Arquivos: ~20**

---

*Gerado por Claude Code em 2026-04-27*
