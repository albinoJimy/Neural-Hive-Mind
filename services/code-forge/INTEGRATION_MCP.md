# Guia de Integração MCP - Code Forge

Este documento descreve as modificações necessárias para integrar o Code Forge com o MCP Tool Catalog Service.

## Arquivos Criados

### Novos Clientes

1. **`src/clients/mcp_tool_catalog_client.py`** ✅ CRIADO
   - Cliente REST para MCP Tool Catalog
   - Métodos: `request_tool_selection()`, `get_tool()`, `send_tool_feedback()`

2. **`src/clients/llm_client.py`** ✅ CRIADO
   - Cliente para LLMs (OpenAI, Anthropic, Ollama)
   - Métodos: `generate_code()`, `validate_code()`, `calculate_confidence()`

## Modificações Necessárias

### 1. Template Selector (`src/services/template_selector.py`)

**Adicionar após linha 16:**

```python
from ..clients.mcp_tool_catalog_client import MCPToolCatalogClient

class TemplateSelector:
    def __init__(self, git_client: GitClient, redis_client: RedisClient, mcp_client: MCPToolCatalogClient = None):
        self.git_client = git_client
        self.redis_client = redis_client
        self.template_registry = TemplateRegistry()
        self.mcp_client = mcp_client  # NOVO
```

**Modificar método `select()` após linha 30:**

```python
async def select(self, context: PipelineContext) -> Template:
    ticket = context.ticket
    params = ticket.parameters

    logger.info('template_selection_started', ticket_id=ticket.ticket_id)

    # === NOVO: Solicitar seleção de ferramentas via MCP ===
    if self.mcp_client:
        try:
            # Calcular complexity_score
            complexity_score = self._calculate_complexity_score(context)

            # Construir ToolSelectionRequest
            mcp_request = {
                "request_id": str(uuid.uuid4()),
                "ticket_id": ticket.ticket_id,
                "plan_id": ticket.plan_id,
                "intent_id": ticket.intent_id,
                "decision_id": ticket.decision_id,
                "correlation_id": ticket.correlation_id,
                "trace_id": context.trace_id,
                "span_id": context.span_id,
                "artifact_type": params.get('artifact_type', 'CODE'),
                "language": params.get('language', 'python'),
                "complexity_score": complexity_score,
                "required_categories": ["GENERATION", "VALIDATION"],  # Mínimo
                "constraints": {
                    "max_execution_time_ms": 300000,  # 5 min
                    "max_cost_score": 0.8,
                    "min_reputation_score": 0.6
                },
                "context": params
            }

            # Chamar MCP Tool Catalog
            mcp_response = await self.mcp_client.request_tool_selection(mcp_request)

            if mcp_response:
                # Armazenar ferramentas selecionadas no contexto
                context.mcp_selection_id = mcp_response.get("response_id")
                context.selected_tools = mcp_response.get("selected_tools", [])

                # Determinar generation_method baseado em ferramentas
                generation_method = self._map_tools_to_generation_method(context.selected_tools)

                logger.info('mcp_tools_selected',
                    selection_id=context.mcp_selection_id,
                    tools_count=len(context.selected_tools),
                    generation_method=generation_method)

        except Exception as e:
            logger.error('mcp_selection_failed', error=str(e))
            # Fallback para template normal
    # === FIM NOVO ===

    # Restante do código original...
```

**Adicionar novos métodos:**

```python
def _calculate_complexity_score(self, context: PipelineContext) -> float:
    """Calcula complexity_score baseado em tarefas, dependências, risk_band."""
    ticket = context.ticket

    # Simplificado - pode ser mais sofisticado
    num_tasks = len(ticket.parameters.get('tasks', []))
    num_dependencies = len(ticket.dependencies)
    risk_band = context.metadata.get('risk_band', 'LOW')

    risk_scores = {'LOW': 0.2, 'MEDIUM': 0.5, 'HIGH': 0.8, 'CRITICAL': 1.0}

    complexity = (
        (min(num_tasks / 20.0, 1.0) * 0.4) +
        (min(num_dependencies / 50.0, 1.0) * 0.3) +
        (risk_scores.get(risk_band, 0.2) * 0.3)
    )

    return min(complexity, 1.0)

def _map_tools_to_generation_method(self, selected_tools: List[Dict]) -> str:
    """Mapeia ferramentas selecionadas para GenerationMethod."""
    tool_names = [t.get('tool_name', '').lower() for t in selected_tools]

    # Verificar se há ferramentas LLM
    llm_tools = ['github copilot', 'openai codex', 'tabnine']
    has_llm = any(llm in name for name in tool_names for llm in llm_tools)

    # Verificar se há ferramentas de template
    template_tools = ['cookiecutter', 'yeoman', 'openapi generator']
    has_template = any(tmpl in name for name in tool_names for tmpl in template_tools)

    if has_llm and has_template:
        return "HYBRID"
    elif has_llm:
        return "LLM"
    elif has_template:
        return "TEMPLATE"
    else:
        return "HEURISTIC"
```

### 2. Code Composer (`src/services/code_composer.py`)

**Adicionar após linha 9:**

```python
from ..clients.llm_client import LLMClient
from ..clients.mcp_tool_catalog_client import MCPToolCatalogClient
# Integração com Analyst Agents para RAG
from ..clients.analyst_agents_client import AnalystAgentsClient  # CRIAR

class CodeComposer:
    def __init__(self, mongodb_client: MongoDBClient, llm_client: LLMClient = None,
                 analyst_client: AnalystAgentsClient = None, mcp_client: MCPToolCatalogClient = None):
        self.mongodb_client = mongodb_client
        self.llm_client = llm_client  # NOVO
        self.analyst_client = analyst_client  # NOVO
        self.mcp_client = mcp_client  # NOVO
```

**Modificar método `compose()` após linha 29:**

```python
async def compose(self, context: PipelineContext):
    template = context.selected_template
    ticket = context.ticket

    logger.info('code_composition_started', template_id=template.template_id)

    # === NOVO: Verificar generation_method das ferramentas MCP ===
    generation_method = getattr(context, 'generation_method', 'TEMPLATE')

    if generation_method in ['LLM', 'HYBRID'] and self.llm_client and self.analyst_client:
        # Geração com LLM + RAG
        code_content = await self._generate_with_llm(context)
        confidence_score = await self.llm_client.calculate_confidence(code_content, {})
        metadata = {
            'generation_method': generation_method,
            'llm_model': self.llm_client.model_name,
            'confidence_score': confidence_score
        }
    elif generation_method == 'HEURISTIC':
        # Geração via regras determinísticas
        code_content = self._generate_heuristic(ticket.parameters)
        metadata = {'generation_method': 'HEURISTIC'}
    else:
        # Geração via template (original)
        code_content = self._generate_python_microservice(ticket.parameters)
        metadata = {'generation_method': 'TEMPLATE'}
    # === FIM NOVO ===

    # Restante do código original (salvar, criar artifact)...

    # Adicionar metadados MCP ao artifact
    if hasattr(context, 'selected_tools'):
        artifact.metadata['mcp_tools_used'] = [t['tool_id'] for t in context.selected_tools]

    # Enviar feedback para MCP
    if self.mcp_client and hasattr(context, 'selected_tools'):
        for tool in context.selected_tools:
            if tool['category'] == 'GENERATION':
                await self.mcp_client.send_tool_feedback(
                    tool['tool_id'],
                    success=True,
                    metadata={'artifact_id': artifact_id}
                )
```

**Adicionar novos métodos:**

```python
async def _generate_with_llm(self, context: PipelineContext) -> str:
    """Gera código usando LLM + RAG."""
    ticket = context.ticket

    # 1. Buscar templates similares via RAG (Analyst Agents)
    rag_context = await self._build_rag_context(ticket)

    # 2. Construir prompt estruturado
    prompt = self._build_llm_prompt(ticket, rag_context)

    # 3. Chamar LLM
    constraints = {
        'language': ticket.parameters.get('language', 'python'),
        'framework': ticket.parameters.get('framework', ''),
        'patterns': ticket.parameters.get('patterns', [])
    }

    result = await self.llm_client.generate_code(prompt, constraints, temperature=0.2)

    if result:
        code = result['code']

        # 4. Validar sintaxe
        is_valid = await self.llm_client.validate_code(code, constraints['language'])

        if is_valid:
            logger.info('llm_code_generated_successfully',
                confidence=result['confidence_score'],
                tokens=result.get('prompt_tokens', 0) + result.get('completion_tokens', 0))
            return code

    # Fallback para template
    logger.warning('llm_generation_failed_fallback_to_template')
    return self._generate_python_microservice(ticket.parameters)

async def _build_rag_context(self, ticket) -> Dict:
    """Busca templates similares via Analyst Agents."""
    # Gerar embedding da descrição do ticket
    query_text = f"{ticket.parameters.get('description', '')} {ticket.parameters.get('language', '')}"

    # Chamar Analyst Agents embedding service
    embedding = await self.analyst_client.get_embedding(query_text)

    # Buscar templates similares
    similar_templates = await self.analyst_client.find_similar_templates(embedding, top_k=5)

    # Buscar padrões arquiteturais do Neo4j
    architectural_patterns = await self.analyst_client.get_architectural_patterns(
        ticket.parameters.get('domain', 'TECHNICAL')
    )

    return {
        'similar_templates': similar_templates,
        'architectural_patterns': architectural_patterns
    }

def _build_llm_prompt(self, ticket, rag_context: Dict) -> str:
    """Constrói prompt estruturado para LLM."""
    similar_templates = rag_context.get('similar_templates', [])
    patterns = rag_context.get('architectural_patterns', [])

    prompt = f"""Generate a {ticket.parameters.get('artifact_type', 'microservice')} in {ticket.parameters.get('language', 'Python')}.

Requirements:
{ticket.parameters.get('description', 'No description provided')}

Similar Templates (for reference):
{chr(10).join([f"- {t.get('name', 'Unknown')}: {t.get('description', '')}" for t in similar_templates[:3]])}

Architectural Patterns to follow:
{chr(10).join([f"- {p}" for p in patterns[:5]])}

Generate production-ready code with:
- Proper error handling
- Type hints and docstrings
- Unit tests
- Logging and observability hooks
"""

    return prompt

def _generate_heuristic(self, parameters: Dict) -> str:
    """Geração via regras determinísticas."""
    # Implementar regras baseadas em parâmetros
    # Simplificado - pode ser sofisticado
    return self._generate_python_microservice(parameters)
```

### 3. Validator (`src/services/validator.py`)

**Modificações similares** para usar ferramentas VALIDATION dinamicamente.

Ver arquivo `VALIDATOR_MCP_INTEGRATION.md` para detalhes completos.

## Próximos Passos

1. ✅ Criar novos clientes (MCP, LLM, Analyst Agents)
2. ⏳ Modificar Template Selector conforme acima
3. ⏳ Modificar Code Composer conforme acima
4. ⏳ Modificar Validator para validação dinâmica
5. ⏳ Criar Kubernetes manifests (Kafka topics, Helm charts)
6. ⏳ Criar scripts de deploy e validação
7. ⏳ Criar teste end-to-end

## Observações

- Todas as modificações são **backward compatible**
- Se MCP client não disponível, código usa comportamento original (template mock)
- Fallbacks robustos em todos os pontos de integração
- Métricas e logs para observabilidade completa
