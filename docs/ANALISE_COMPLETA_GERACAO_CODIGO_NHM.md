# Análise Profunda: Geração de Código no Neural Hive-Mind

**Data:** 2026-03-15
**Autor:** Claude Code
**Versão:** 1.0

---

## Índice

1. [Visão Geral do Pipeline](#1-visão-geral-do-pipeline)
2. [Gateway de Intenções](#2-gateway-de-intenções-entry-point)
3. [Semantic Translation Engine](#3-semantic-translation-engine-decomposição)
4. [Consensus Engine](#4-consensus-engine-avaliação-multi-especialista)
5. [Orchestrator Dynamic](#5-orchestrator-dynamic-geração-de-tickets)
6. [Worker Agents](#6-worker-agents-execução)
7. [Code Forge](#7-code-forge-geração-de-código)
8. [Approval Service](#8-approval-service-aprovação-humana)
9. [Fluxo de Aprovação e Saga Compensation](#9-fluxo-de-aprovação-e-saga-compensation)
10. [Integração MCP Tool Catalog](#10-integração-mcp-tool-catalog)
11. [Integração gRPC Service Registry](#11-integração-grpc-service-registry)
12. [Persistência Multi-Database](#12-persistência-multi-database)
13. [Circuit Breakers e Resilience](#13-circuit-breakers-e-resilience)
14. [Exemplo End-to-End Completo](#14-exemplo-end-to-end-completo)
15. [Casos Especiais e Edge Cases](#15-casos-especiais-e-edge-cases)
16. [Detalhes dos Templates de Geração](#16-detalhes-dos-templates-de-geração-de-código)
17. [Exemplos Reais de Código Gerado](#17-exemplos-reais-de-código-gerado)
18. [Configurações e Ambientes](#18-configurações-e-ambientes)
19. [Estrutura de Deploy Kubernetes](#19-estrutura-de-deploy-kubernetes)
20. [Troubleshooting e Debugging](#20-troubleshooting-e-debugging)
21. [Guia de Operação](#21-guia-de-operação)
22. [Segurança](#22-segurança)
23. [Monitoramento e Alertas](#23-monitoramento-e-alertas)
24. [Roadmap e Evolução Futura](#24-roadmap-e-evolução-futura)
   - 24.1 Visão Geral do Roadmap NHM
   - 24.2 Fase 0: Infraestrutura Fundacional
   - 24.3 Fase 1: Processamento Cognitivo (75%)
   - 24.4 Fase 2: Orquestração (50%)
   - 24.5 Fase 3: Auto-Recuperação (25%)
   - 24.6 Fase 4: Evolução Estratégica (10%)
   - 24.7 Fase 5: Enterprise (0%)
   - 24.8 Specs Recentes
   - 24.9 Timeline Realista
   - 24.10 Riscos e Bloqueadores
   - 24.11 Dependências Externas
25. [ML Specialists - Detalhes Técnicos](#25-ml-specialists---detalhes-técnicos)
26. [Prompts LLM](#26-exemplos-de-prompts-llm)
27. [Temporal Workflow](#27-temporal-workflow---detalhes-avançados)
28. [Integrações Externas](#28-integrações-externas)
29. [Casos de Uso por Indústria](#29-casos-de-uso-por-indústria)
30. [Performance e Custos](#30-performance-e-custos)
71. [Análise Profunda do Fluxo Orchestrator Dynamic](#71-análise-profunda-do-fluxo-orchestrator-dynamic)

---

## 1. Visão Geral do Pipeline

O NHM implementa um **pipeline cognitivo distribuído** que transforma uma intenção em texto em código executável através de 7 estágios principais:

```
Intenção → Gateway → STE → Consensus → Orchestrator → Worker → Code-Forge → Código
```

### Arquitetura Cognitiva

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NEURAL HIVE-MIND COGNITIVE PIPELINE                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────┐    ┌──────────────────┐    ┌──────────────┐                  │
│  │  ACTOR   │───▶│ GATEWAY INTENÇÕES│───▶│   KAFKA      │                  │
│  │ (User)   │    │   (FastAPI)      │    │ intentions.* │                  │
│  └──────────┘    └──────────────────┘    └──────┬───────┘                  │
│                                                  │                           │
│                          ┌───────────────────────┼───────────────────┐      │
│                          ▼                       ▼                   ▼      │
│                   ┌──────────────┐      ┌─────────────┐    ┌────────────┐    │
│                   │  SEMANTIC    │      │  CONSENSUS  │    │  APPROVAL  │    │
│                   │TRANSLATION   │      │   ENGINE    │    │  SERVICE   │    │
│                   │   ENGINE     │      │  (ML+Redis) │    │  (Kafka)   │    │
│                   └──────┬───────┘      └──────┬──────┘    └──────┬─────┘    │
│                          │                     │                   │         │
│                          ▼                     ▼                   ▼         │
│                   ┌──────────────┐      ┌─────────────┐    ┌────────────┐    │
│                   │  ORCHESTRATOR│      │   CODE      │    │   WORKER   │    │
│                   │   DYNAMIC    │─────▶│   FORGE     │◀───│   AGENTS   │    │
│                   │ (Temporal)   │      │   (LLM/RAG) │    │ (Kafka)    │    │
│                   └──────────────┘      └─────────────┘    └────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Componentes Principais

| Serviço | Porta | Responsabilidade | Tecnologia |
|---------|-------|------------------|------------|
| Gateway de Intenções | 8000 | Recebe intenções HTTP | FastAPI |
| Semantic Translation Engine | 8001 | Decompõe intenção em tarefas | Python |
| Consensus Engine | 8002 | Agrega opiniões de especialistas ML | Redis + ML |
| Orchestrator Dynamic | 8003 | Gera execution tickets | Temporal |
| Approval Service | 8004 | Gerencia fluxo de aprovação | FastAPI |
| Code Forge Service | 8005 | Gera código via LLM/RAG | Python |
| Worker Agents | 8006 | Executa tickets | Kafka |
| Execution Ticket Service | 8007 | Rastreia tickets | MongoDB |

---

## 2. Gateway de Intenções (Entry Point)

**Arquivo:** `services/gateway-intencoes/`

### Função
Recebe intenções via API REST/HTTP e as publica no Kafka para processamento assíncrono.

### Modelo de Dados Principal: `IntentEnvelope`

```python
class IntentEnvelope(BaseModel):
    id: str                          # UUID único
    correlation_id: str              # Rastreamento end-to-end
    actor: Actor                     # Quem originou (humano/sistema)
    intent: Intent                   # Conteúdo da intenção
        - text: str                  # Texto da intenção
        - domain: UnifiedDomain      # Domínio (BUSINESS, TECHNICAL, SECURITY)
        - entities: List[Entity]     # Entidades extraídas
        - keywords: List[str]        # Palavras-chave
    confidence: float                # Score de confiança (0.0-1.0)
    context: Context                 # Sessão, usuário, tenant
    constraints: Constraint          # Prioridade, deadline, SLA
```

### Kafka Producer
- **Tópicos:** `intentions.{domain}` (ex: `intentions.security`)
- **Serialização:** Avro (via Schema Registry) ou JSON fallback
- **Semântica:** Exactly-once (transactional.id por pod)
- **Headers:** traceparent (W3C), correlation-id, content-type

### Arquivos Chave

| Arquivo | Função |
|---------|--------|
| `models/intent_envelope.py` | Schema Pydantic do IntentEnvelope |
| `kafka/producer.py` | Publicação transacional no Kafka |
| `pipelines/nlu_pipeline.py` | Extração de entidades e classificação |

---

## 3. Semantic Translation Engine (Decomposição)

**Arquivo:** `services/semantic-translation-engine/`

### Função
Consome intenções do Kafka e decompõe em um **Cognitive Plan** estruturado.

### Fluxo B1-B6

```python
async def process_intent(intent_envelope: Dict, trace_context: Dict):
    # B1: Validar envelope
    _validate_intent_envelope(intent_envelope)

    # B2: Semantic Parser - Enriquecer contexto
    intermediate_repr = await parser.parse(intent_envelope)

    # B3: DAG Generator - Decompor em tasks
    tasks, execution_order = dag_gen.generate(intermediate_repr)

    # B4: Risk Scorer - Avaliar risco multi-dominio
    risk_score, risk_band, risk_factors, risk_matrix, destructive = risk_scorer.score_multi_domain(...)

    # B5: Versionar e registrar plano
    cognitive_plan = _create_cognitive_plan(...)
    ledger_hash = await mongodb.append_to_ledger(cognitive_plan)

    # B6: Publicar (condicional baseado em approval)
    if requires_approval:
        await approval_producer.send_approval_request(cognitive_plan)  # Tópico: plans.approvals
    else:
        await plan_producer.send_plan(cognitive_plan)  # Tópico: plans.ready
```

### Cognitive Plan

```python
class CognitivePlan(BaseModel):
    plan_id: str
    intent_id: str
    correlation_id: str
    tasks: List[Task]              # Tasks geradas
    execution_order: List[List]   # DAG de dependências
    risk_score: float              # 0.0-1.0
    risk_band: RiskBand            # LOW, MEDIUM, HIGH, CRITICAL
    requires_approval: bool        # Se precisa de aprovação humana
    is_destructive: bool           # Se contém ops destrutivas
    status: PlanStatus             # VALIDATED, BLOCKED, etc
```

### Critérios de Aprovação

```python
requires_approval = (
    risk_score >= 0.7 or           # Risco alto
    is_destructive or              # Operações destrutivas
    risk_band in [HIGH, CRITICAL]  # Banda de risco crítica
)
```

### Arquivos Chave

| Arquivo | Função |
|---------|--------|
| `consumers/intent_consumer.py` | Consome `intentions.*` |
| `services/orchestrator.py` | Coordena fluxo B1-B6 |
| `services/dag_generator.py` | Gera DAG de tasks |
| `services/risk_scorer.py` | Avaliação de risco |
| `producers/plan_producer.py` | Publica `plans.ready` |
| `producers/approval_producer.py` | Publica `plans.approvals` |

---

## 4. Consensus Engine (Avaliação Multi-Especialista)

**Arquivo:** `services/consensus-engine/`

### Função
Agrega opiniões de 5 especialistas ML usando **Bayesian Aggregation**.

### Fluxo de Consenso

```python
async def process_consensus(cognitive_plan: Dict, specialist_opinions: List[Dict]):
    # 1. Calcular pesos dinâmicos (feromônios)
    weights = await _calculate_dynamic_weights(cognitive_plan, opinions)

    # 2. Agregação Bayesiana
    aggregated_confidence, conf_variance = bayesian.aggregate_confidence(opinions, weights)
    aggregated_risk, risk_variance = bayesian.aggregate_risk(opinions, weights)
    divergence = bayesian.calculate_divergence(opinions, aggregated_confidence, aggregated_risk)

    # 3. Voting Ensemble
    final_recommendation, vote_distribution = voting.aggregate_recommendations(opinions, weights)

    # 4. Verificar compliance
    is_compliant, violations, adaptive_thresholds = compliance.check_compliance(...)

    # 5. Consolidar decisão
    decision = ConsolidatedDecision(
        final_decision: DecisionType,      # APPROVE, REJECT, REVIEW_REQUIRED
        consensus_method: ConsensusMethod, # BAYESIAN, VOTING, UNANIMOUS
        aggregated_confidence: float,
        specialist_votes: List[SpecialistVote]
    )

    # 6. Publicar feromônios para aprendizado futuro
    await _publish_pheromones(decision, cognitive_plan, opinions)

    return decision
```

### Especialistas ML

| Especialista | Função |
|-------------|--------|
| `business-evaluator` | Viabilidade de negócio |
| `technical-evaluator` | Viabilidade técnica |
| `behavior-evaluator` | Análise de comportamento |
| `evolution-evaluator` | Manutenibilidade |
| `architecture-evaluator` | Arquitetura e padrões |

### Arquivos Chave

| Arquivo | Função |
|---------|--------|
| `services/consensus_orchestrator.py` | Coordena consenso |
| `services/bayesian_aggregator.py` | Agregação Bayesiana |
| `services/voting_ensemble.py` | Votação |
| `producers/decision_producer.py` | Publica `plans.consensus` |

---

## 5. Orchestrator Dynamic (Geração de Tickets)

**Arquivo:** `services/orchestrator-dynamic/`

### Função
Recebe Cognitive Plan (ou Approval Response) e gera **Execution Tickets** para o Worker Agents.

### Fluxo C1-C6 (Temporal Workflow)

```python
@workflow.defn
class PlanExecutionWorkflow:
    async def run(self, plan_id: str, decision: ConsolidatedDecision):
        # C1: Validar plano
        await activities.validate_plan(plan_id, decision)

        # C2: Gerar execution tickets
        tickets = await activities.generate_tickets(
            plan_id=plan_id,
            cognitive_plan=decision.cognitive_plan,
            consensus_decision=decision
        )

        # C3: Publicar tickets no Kafka
        for ticket in tickets:
            await kafka_producer.send_ticket(ticket, topic="execution.tickets")

        # C4: Aguardar conclusão (polling ou callback)
        await activities.wait_for_completion(plan_id, tickets)

        # C5: Compilar resultados
        results = await activities.compile_results(plan_id, tickets)

        # C6: Persistir e notificar
        await activities.persist_results(plan_id, results)
```

### Execution Ticket

```python
class ExecutionTicket(BaseModel):
    ticket_id: str
    plan_id: str
    intent_id: str
    correlation_id: str
    task_type: TaskType          # CODE_GENERATION, QUERY, TRANSFORM, VALIDATE
    parameters: Dict             # Parâmetros específicos da task
    dependencies: List[str]      # Tickets que devem completar antes
    sla: Dict                   # timeout, max_retries
```

### Arquivos Chave

| Arquivo | Função |
|---------|--------|
| `activities/ticket_generation.py` | Gera tickets |
| `workflows/plan_execution.py` | Workflow Temporal |
| `consumers/plan_consumer.py` | Consome `plans.ready` |
| `consumers/approval_consumer.py` | Consome `plans.approvals` |

---

## 6. Worker Agents (Execução)

**Arquivo:** `services/worker-agents/`

### Função
Consome tickets do Kafka e executa usando **executores especializados**.

### Fluxo de Execução

```python
async def process_ticket(ticket: Dict[str, Any]):
    ticket_id = ticket.get('ticket_id')

    # 1. Verificar duplicata (Redis com fallback MongoDB)
    if await _is_duplicate_ticket(ticket_id):
        return

    # 2. Criar task assíncrona
    task = asyncio.create_task(_execute_ticket(ticket))

    # 3. Executar com retry
    result = await _execute_task_with_retry(ticket)

    # 4. Verificar sucesso
    if result.get('success'):
        await ticket_client.update_ticket_status(ticket_id, 'COMPLETED')
        await result_producer.publish_result(ticket_id, 'COMPLETED', result)
        await _mark_ticket_processed(ticket_id)
    else:
        await ticket_client.update_ticket_status(ticket_id, 'FAILED', ...)
        await _clear_ticket_processing(ticket_id)
```

### Executores Disponíveis

| Executor | Task Type | Função |
|----------|-----------|--------|
| `CodeForgeExecutor` | `code_forge` | Invoca Code Forge para gerar código |
| `QueryExecutor` | `query` | Executa queries MongoDB |
| `TransformExecutor` | `transform` | Transforma dados JSON |
| `ValidateExecutor` | `validate` | Valida políticas OPA |
| `CompensateExecutor` | `compensate` | Compensação de falhas |

### Arquivos Chave

| Arquivo | Função |
|---------|--------|
| `engine/execution_engine.py` | Motor de execução |
| `executors/code_forge_executor.py` | Executor Code Forge |
| `consumers/ticket_consumer.py` | Consome `execution.tickets` |

---

## 7. Code Forge (Geração de Código)

**Arquivo:** `services/code-forge/`

### Função
Gera código efetivamente usando **Templates, LLM ou RAG**.

### Pipeline Code Forge

```python
async def execute(ticket: ExecutionTicket) -> Dict:
    # 1. Template Selector - Selecionar template base
    template = await template_selector.select(ticket.parameters)
    context.selected_template = template

    # 2. Code Composer - Gerar código
    await code_composer.compose(context)

    # 3. Dockerfile Generator - Gerar Dockerfile
    await dockerfile_gen.generate(context)

    # 4. Container Builder - Build e push
    await container_builder.build(context)

    # 5. Validator - Validações
    await validator.validate(context)

    # 6. Test Runner - Executar testes
    await test_runner.run(context)

    return {'success': True, 'artifacts': context.artifacts}
```

### Métodos de Geração de Código

```python
class CodeComposer:
    async def compose(self, context: PipelineContext):
        generation_method = context.generation_method  # LLM, RAG, TEMPLATE, HYBRID

        if generation_method == 'LLM':
            # Gera via LLM com RAG context
            code_content, confidence, method = await self._generate_via_llm(context)
        elif generation_method == 'HYBRID':
            # Template + LLM enhancement
            code_content, confidence = await self._generate_hybrid(context)
        elif generation_method == 'HEURISTIC':
            # Regras determinísticas
            code_content = self._generate_heuristic(ticket.parameters)
        else:
            # Template puro (fallback)
            code_content = self._generate_python_microservice(ticket.parameters)

        # Salvar código gerado no MongoDB
        artifact_id = await mongodb_client.save_artifact_content(code_content)

        return CodeForgeArtifact(artifact_id=artifact_id, content_uri=f'mongodb://artifacts/{artifact_id}')
```

### RAG Context

```python
async def _build_rag_context(ticket) -> dict:
    # 1. Gerar embedding do query
    embedding = await analyst_client.get_embedding(query_text)

    # 2. Buscar templates similares (busca vetorial)
    similar_templates = await analyst_client.find_similar_templates(embedding, top_k=5)

    # 3. Buscar padrões arquiteturais
    architectural_patterns = await analyst_client.get_architectural_patterns(domain)

    return {"similar_templates": similar_templates, "architectural_patterns": patterns}
```

### Arquivos Chave

| Arquivo | Função |
|---------|--------|
| `services/code_composer.py` | Gera código |
| `services/dockerfile_generator.py` | Gera Dockerfile |
| `services/container_builder.py` | Build containers |
| `services/template_selector.py` | Seleciona template |
| `clients/llm_client.py` | Cliente LLM |
| `clients/analyst_agents_client.py` | Cliente RAG |

---

## 8. Approval Service (Aprovação Humana)

**Arquivo:** `services/approval-service/`

### Função
Gerencia aprovações manuais para planos de alto risco.

### Fluxo de Aprovação

```python
# Quando STE publica no tópico de aprovação:
async def process_approval_request(approval_request: ApprovalRequest):
    await mongodb_client.save_approval_request(approval_request)

# API de aprovação:
async def approve_plan(plan_id: str, user_id: str, comments: str):
    approval = await mongodb_client.get_approval_by_plan_id(plan_id)
    decision = ApprovalDecision(plan_id=plan_id, decision='approved', approved_by=user_id, ...)

    # Atualizar MongoDB
    await mongodb_client.update_approval_decision(plan_id, decision)

    # Publicar ApprovalResponse no Kafka (Flow C Resume)
    response = ApprovalResponse(decision='approved', cognitive_plan=approval.cognitive_plan)
    await approval_response_producer.send_approval_response(response)

    # Submeter feedback ML em background
    await _submit_feedback_for_plan(plan_id, human_decision='approve', ...)
```

### Tópicos Kafka

| Tópico | Direção | Conteúdo |
|--------|---------|----------|
| `plans.approvals` | STE → Approval | ApprovalRequest (bloqueado aguardando aprovação) |
| `plans.approvals.responses` | Approval → Orchestrator | ApprovalResponse (aprovado → retoma Flow C) |

---

## 9. Fluxo de Aprovação e Saga Compensation

### Flow C Resume (Após Aprovação Humana)

```python
# services/orchestrator-dynamic/src/consumers/approval_response_consumer.py

async def consume_approval_response(response: ApprovalResponse):
    """Consume ApprovalResponse e retoma workflow"""

    if response.decision == 'approved':
        # Flow C Resume: Continuar geração de tickets
        await _resume_plan_execution(response)
    else:
        # Flow C Reject: Plano rejeitado
        await _handle_rejected_plan(response)

async def _resume_plan_execution(response: ApprovalResponse):
    """Retoma execução do plano aprovado"""

    # Extrair cognitive_plan da resposta
    cognitive_plan = response.cognitive_plan

    # Continuar de onde parou (C2: Generate Tickets)
    tickets = await activities.generate_tickets(
        plan_id=response.plan_id,
        cognitive_plan=cognitive_plan,
        consensus_decision=response.get('consensus_decision')
    )

    # Publicar tickets para Worker Agents
    for ticket in tickets:
        await kafka_producer.send_ticket(ticket, topic="execution.tickets")
```

### Saga Compensation (Rollback)

```python
# services/worker-agents/src/executors/compensate_executor.py

class CompensateExecutor(BaseExecutor):
    """Executor para compensação de operações"""

    async def execute(self, ticket: ExecutionTicket) -> Dict:
        """
        Executa compensação usando Saga pattern.

        Tipos de compensação:
        - revert_approval: Reverte aprovação manual
        - delete_artifact: Remove artefato gerado
        - mark_plan_failed: Marca plano como falhado
        - notify_user: Notifica usuário sobre falha
        """

        compensation_type = ticket.parameters.get('compensation_type')
        plan_id = ticket.parameters.get('plan_id')
        original_ticket_id = ticket.parameters.get('original_ticket_id')

        if compensation_type == 'revert_approval':
            # Chamar Approval Service para reverter
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{approval_service_url}/api/v1/approvals/{plan_id}/revert",
                    json={
                        'user_id': 'system',
                        'reason': f'Compensação para ticket falho: {original_ticket_id}',
                        'ticket_id': original_ticket_id
                    }
                )
                return {'success': response.status_code == 200, 'approval_reverted': True}

        elif compensation_type == 'delete_artifact':
            # Remover artefato do MongoDB/S3
            artifact_id = ticket.parameters.get('artifact_id')
            await mongodb_client.delete_artifact(artifact_id)
            return {'success': True, 'artifact_deleted': artifact_id}
```

### Transação Saga Completa

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SAGA TRANSACTION                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Step 1: Generate Tickets    [SUCCESS] → Compensate: Delete Tickets │
│  Step 2: Execute Ticket #1    [SUCCESS] → Compensate: Revert #1     │
│  Step 3: Execute Ticket #2    [FAILURE] → Compensate: Revert #2     │
│                                      ↓                                │
│  Step 4: COMPENSATION         ←───────┘                                │
│    - Revert Ticket #2                                                  │
│    - Revert Ticket #1                                                  │
│    - Delete Tickets                                                   │
│    - Revert Approval (se manual)                                      │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 10. Integração MCP Tool Catalog

### O que é MCP?

**MCP (Model Context Protocol)** é um protocolo que permite ao LLM acessar ferramentas externas de forma estruturada.

### Integração Code Forge + MCP

```python
# services/code-forge/src/clients/mcp_tool_catalog_client.py

class MCPToolCatalogClient:
    """Cliente para consultar ferramentas MCP disponíveis"""

    async def query_tools(
        self,
        domain: str,
        task_type: str,
        language: str
    ) -> List[Dict]:
        """
        Busca ferramentas MCP relevantes para a task

        Returns:
            Lista de ferramentas com:
            - tool_name: Nome da ferramenta
            - description: Descrição da funcionalidade
            - input_schema: Schema dos parâmetros
            - capability: Tipo de operação
        """
        response = await httpx.get(
            f"{mcp_catalog_url}/api/v1/tools/query",
            params={'domain': domain, 'task_type': task_type, 'language': language}
        )
        return response.json()['tools']

# Na geração de código:
async def compose(self, context: PipelineContext):
    # 1. Consultar MCP Tools relevantes
    mcp_tools = await mcp_client.query_tools(
        domain=ticket.parameters.get('domain'),
        task_type='code_generation',
        language=ticket.parameters.get('language', 'python')
    )

    # 2. Selecionar ferramentas (seleção baseada em相似idade)
    selected_tools = self._select_relevant_tools(mcp_tools, ticket.parameters)
    context.selected_tools = selected_tools

    # 3. Gerar código usando templates MCP
    if selected_tools:
        code_content = self._generate_with_mcp_tools(ticket.parameters, selected_tools)
    else:
        code_content = self._generate_python_microservice(ticket.parameters)
```

---

## 11. Integração gRPC (Service Registry)

### Service Registry Cliente

```python
# services/orchestrator-dynamic/src/clients/service_registry_client.py

class ServiceRegistryClient:
    """Cliente gRPC para descoberta de serviços"""

    async def discover_service(self, service_name: str) -> Optional[ServiceInstance]:
        """
        Descobre instância disponível de um serviço

        Args:
            service_name: Nome do serviço (ex: 'code-forge', 'worker-agents')

        Returns:
            ServiceInstance com endpoint gRPC e metadados
        """
        stub = self.registry_stub
        request = registry_pb2.DiscoverRequest(service_name=service_name)
        response = await stub.Discover(request)

        return ServiceInstance(
            service_name=response.service_name,
            host=response.host,
            port=response.port,
            grpc_address=f"{response.host}:{response.grpc_port}",
            metadata=json.loads(response.metadata)
        )
```

---

## 12. Persistência Multi-Database

### MongoDB (Cognitive Ledger)

```python
# services/semantic-translation-engine/src/clients/mongodb_client.py

class MongoDBClient:
    """Persistência de planos cognitivos"""

    async def append_to_ledger(self, plan: CognitivePlan) -> str:
        """
        Adiciona plano ao ledger imutável (immutable append-only log)

        O ledger armazena TODOS os planos gerados para auditoria.
        """
        ledger_entry = {
            'plan_id': plan.plan_id,
            'intent_id': plan.intent_id,
            'correlation_id': plan.correlation_id,
            'cognitive_plan': plan.dict(),
            'timestamp': datetime.utcnow(),
            'hash': self._calculate_plan_hash(plan)
        }

        result = await self.db.plan_ledger.insert_one(ledger_entry)
        return str(result.inserted_id)
```

### Redis (Pheromones + Deduplicação)

```python
# Redis é usado para 2 propósitos principais:

# 1. Feromônios (aprendizado de especialistas)
# Pheromone signals mantêm "memória" de decisões passadas
# Formato: pheromone:{specialist_type}:{domain}:{pheromone_type}
# Exemplo: pheromone:business-evaluator:SECURITY:SUCCESS

# 2. Deduplicação de tickets (idempotência)
# Formato: ticket:processing:{ticket_id} e ticket:processed:{ticket_id}
```

---

## 13. Circuit Breakers e Resilience

### Circuit Breaker Pattern

```python
# neural_hive_resilience/circuit_breaker.py (biblioteca compartilhada)

class CircuitBreaker:
    """Circuit Breaker para prevenir chamadas a serviços degradados"""

    def __init__(self, failure_threshold: int = 5, timeout_ms: int = 60000):
        self.failure_threshold = failure_threshold
        self.timeout_ms = timeout_ms
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    async def call(self, func, *args, **kwargs):
        """Executa função com proteção de circuit breaker"""

        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.timeout_ms / 1000:
                self.state = 'HALF_OPEN'
            else:
                raise CircuitBreakerError(f"Circuit breaker OPEN for {func.__name__}")

        try:
            result = await func(*args, **kwargs)

            if self.state == 'HALF_OPEN':
                self.state = 'CLOSED'
                self.failure_count = 0

            return result

        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self.state = 'OPEN'

            raise
```

### Uso no Code Forge

```python
# services/code-forge/src/clients/llm_client.py

class LLMClient:
    """Cliente LLM com Circuit Breaker"""

    def __init__(self):
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, timeout_ms=30000)

    async def generate_code(self, prompt: str, constraints: Dict) -> Dict:
        """Gera código com proteção de circuit breaker"""

        try:
            return await self.circuit_breaker.call(self._generate_code_internal, prompt, constraints)
        except CircuitBreakerError:
            # Fallback para heurística quando LLM está degradado
            logger.warning('LLM circuit breaker OPEN, using heuristic fallback')
            return self._generate_heuristic(prompt, constraints)
```

---

## 14. Exemplo End-to-End Completo

### Cenário: Criar Microserviço de Produtos

```
Input: "Criar um microserviço em Python para gerenciar produtos
com endpoints CRUD e validação de estoque"
```

### Passo a Passo

#### PASSO 1: Gateway de Intenções

```
POST /api/v1/intentions
{
  "text": "Criar um microserviço em Python para gerenciar produtos...",
  "language": "pt-BR",
  "actor": {"id": "user-123", "actor_type": "human"}
}

→ NLU Pipeline extrai entidades:
  - entities: [{"type": "artifact_type", "value": "microservice"}]
  - keywords: ["python", "produtos", "crud", "estoque"]
  - domain: BUSINESS
  - confidence: 0.92

→ Publica no Kafka: intentions.business
```

#### PASSO 2: Semantic Translation Engine

```
→ Semantic Parser enriquece contexto
→ DAG Generator cria 5 tasks:
  tasks = [
    Task(id="t1", type="code_generation", description="API FastAPI"),
    Task(id="t2", type="code_generation", description="Modelos Pydantic"),
    Task(id="t3", type="code_generation", description="Repository MongoDB"),
    Task(id="t4", type="validate", description="OPA policies"),
    Task(id="t5", type="code_generation", description="Dockerfile")
  ]

→ Risk Scorer avalia:
  risk_score = 0.35
  risk_band = "LOW"
  is_destructive = False

→ requires_approval = FALSE (risco baixo)
```

#### PASSO 3: Consensus Engine

```
→ 5 Especialistas ML avaliam o plano:

  business-evaluator:  recommendation="approve", confidence=0.88
  technical-evaluator:  recommendation="approve", confidence=0.92
  behavior-evaluator:   recommendation="approve", confidence=0.85
  evolution-evaluator:  recommendation="approve", confidence=0.89
  architecture-evaluator: recommendation="approve", confidence=0.91

→ Bayesian Aggregation:
  aggregated_confidence = 0.89
  divergence = 0.04 (baixa divergência)
  is_unanimous = TRUE

→ final_decision = APPROVE
```

#### PASSO 4: Orchestrator Dynamic

```
→ C2: Generate 5 Execution Tickets
→ Publica no Kafka: execution.tickets
```

#### PASSO 5-7: Worker → Code Forge → Resultado

```
✓ Microserviço FastAPI gerado
✓ Modelos Pydantic criados
✓ Repository MongoDB implementado
✓ Dockerfile criado
✓ Imagem construída: registry/produtos-api:1.0.0
✓ Testes passando (87% coverage)

Tempo total: ~3 minutos
```

---

## 15. Casos Especiais e Edge Cases

### Caso 1: Intenção com Risco Alto (Requer Aprovação)

```
Input: "Deletar todos os usuários do banco de dados"

→ STE: risk_score = 0.95, is_destructive = True
→ Publica em: plans.approvals
→ Usuário aprova manualmente via API
→ Flow C Resume: Gera tickets normalmente
```

### Caso 2: LLM Degradado (Circuit Breaker)

```
→ Code Forge tenta chamar LLM
→ CircuitBreakerError: LLM service OPEN (3 falhas consecutivas)
→ Fallback automático para TEMPLATE
→ Código gerado via template (confiança 0.85)
```

### Caso 3: Ticket Duplicado (Idempotência)

```
→ Worker recebe ticket tk-123
→ Verifica Redis: ticket:processing:tk-123 existe
→ Skip: "Ticket já em processamento por outro worker"
```

### Caso 4: Falha em Saga (Compensação)

```
→ tk-1: COMPLETED
→ tk-2: COMPLETED
→ tk-3: FAILED (timeout)
→ Inicia compensação:
  - Reverte tk-2
  - Reverte tk-1
  - Se foi aprovado manualmente: Reverte aprovação
```

---

## 16. Detalhes dos Templates de Geração de Código

### Estrutura de Templates

```python
class CodeTemplate(BaseModel):
    template_id: str
    name: str
    description: str
    language: str                    # python, javascript, go, etc
    framework: Optional[str]          # fastapi, express, spring-boot
    artifact_type: ArtifactCategory   # MICROSERVICE, LIBRARY, IAC_TERRAFORM

    content_template: str             # Jinja2 template string
    file_structure: Dict[str, str]    # Caminho → conteúdo

    supported_features: List[str]     # ["crud", "auth", "metrics"]
    dependencies: List[str]           # ["fastapi>=0.100.0", "pydantic>=2.0"]
```

### Template Python FastAPI CRUD

O sistema inclui templates completos para:
- FastAPI CRUD com Pydantic
- Dockerfile multi-stage
- Kubernetes manifests
- Helm charts

---

## 17. Exemplos Reais de Código Gerado

### Exemplo 1: API de Produtos (Python FastAPI)

```python
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, validator
from pymongo import MongoClient
from typing import List, Optional
import structlog

app = FastAPI(title="Produtos API", version="1.0.0")

class Produto(BaseModel):
    id: Optional[str] = None
    nome: str = Field(..., min_length=1, max_length=100)
    preco: float = Field(..., gt=0, description="Preço deve ser positivo")
    estoque: int = Field(..., ge=0, description="Estoque mínimo é zero")
    categoria: str
    ativo: bool = True

@app.post("/produtos", status_code=201)
async def criar_produto(produto: ProdutoCreate):
    """Criar novo produto"""
    # Implementação completa gerada automaticamente

@app.get("/produtos/{produto_id}")
async def buscar_produto(produto_id: str):
    """Buscar produto por ID"""
    # Implementação completa
```

---

## 18. Configurações e Ambientes

### Configuração do Code Forge

```python
class CodeForgeSettings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # LLM Configuration
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-opus-4-20250514"
    llm_timeout_seconds: int = 30

    # MCP Tool Catalog
    mcp_catalog_url: str = "http://mcp-tool-catalog:8080"

    # Container Build
    kaniko_executor_image: str = "gcr.io/kaniko-project/executor:latest"
    registry_url: str = "registry.neural-hive.local"
```

---

## 19. Estrutura de Deploy (Kubernetes)

### Helm Chart do Code Forge

```yaml
# services/code-forge/helm/code-forge/values.yaml

replicaCount: 2

image:
  repository: registry.neural-hive.local/code-forge
  tag: "1.0.0"
  pullPolicy: IfNotPresent

env:
  - name: MONGODB_URI
    value: "mongodb://mongodb:27017"
  - name: ANTHROPIC_API_KEY
    valueFrom:
      secretKeyRef:
        name: llm-secrets
        key: anthropic-api-key

service:
  type: ClusterIP
  port: 8000

resources:
  limits:
    cpu: 1000m
    memory: 2Gi
  requests:
    cpu: 500m
    memory: 1Gi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

---

## 20. Troubleshooting e Debugging

### Problemas Comuns e Soluções

| Problema | Sintoma | Diagnóstico | Solução |
|----------|---------|--------------|----------|
| Intent não processada | Gateway 202 mas STE nada consome | Tópico Kafka inexistente | Criar tópico |
| Plano preso em PENDING | Orchestrator não gera tickets | Approval pendente | Aprovar via API |
| LLM timeout | Code Forge demora >60s | LLM service degradado | Circuit breaker → TEMPLATE |
| Build falha | Kaniko exit code 1 | Recursos insuficientes | Aumentar requests.cpu |

### Debug Logging

```
# Ativar debug logging
LOG_LEVEL=DEBUG
NEURAL_HIVE_DEBUG=true

# Logs específicos por serviço
DEBUG:gateway.producer "Intent published"
DEBUG:ste.parser "Intermediate repr"
DEBUG:consensus.bayesian "Weights calculated"
DEBUG:codeforge.llm "LLM prompt"
```

---

## 21. Guia de Operação

### Startup de Todos os Serviços

```bash
#!/bin/bash
echo "=== Neural Hive-Mind Startup ==="

# 1. Infrastructure
kubectl apply -f infrastructure/mongodb/
kubectl apply -f infrastructure/redis/
kubectl apply -f infrastructure/kafka/

# 2. Core Services
kubectl apply -f services/gateway-intencoes/
kubectl apply -f services/semantic-translation-engine/
kubectl apply -f services/consensus-engine/
kubectl apply -f services/orchestrator-dynamic/

# 3. Workers
kubectl apply -f services/worker-agents/
kubectl apply -f services/code-forge/

echo "=== All services started ==="
```

### Rollout de Nova Versão

```bash
SERVICE=$1
NEW_VERSION=$2

kubectl set image deployment/$SERVICE \
  $SERVICE=registry.neural-hive.local/$SERVICE:$NEW_VERSION

kubectl rollout status deployment/$SERVICE --timeout=300s
```

---

## 22. Segurança

### Autenticação e Autorização

```python
class OAuth2Validator:
    """Validação OAuth2 via Keycloak"""

    async def validate_token(self, token: str) -> Optional[Actor]:
        # Decodificar JWT
        payload = jwt.decode(token, options={"verify_signature": False})

        # Em produção, validar com Keycloak
        if settings.oauth2_enabled:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.oauth2_introspect_url}",
                    headers={"Authorization": f"Bearer {settings.oauth2_client_secret}"},
                    params={"token": token}
                )

        return Actor(
            id=payload.get("sub"),
            actor_type=ActorType.HUMAN,
            roles=payload.get("realm_access", {}).get("roles", [])
        )
```

### Segurança no Code Forge

```python
class LicenseValidator:
    """Validação de licenças de código gerado"""

    async def validate_license(
        self,
        code_content: str,
        allowed_licenses: List[str] = None
    ) -> ValidationResult:
        """
        Licenças permitidas: MIT, Apache-2.0, BSD-3-Clause, ISC
        Licenças copyleft não permitidas: GPL, AGPL, LGPL
        """

        if allowed_licenses is None:
            allowed_licenses = ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC"]

        # Extrair imports e validar licenças
        # ...
```

---

## 23. Monitoramento e Alertas

### Métricas Prometheus Principais

```yaml
groups:
  - name: neural_hive_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning

      - alert: LLMServiceDegraded
        expr: llm_circuit_breaker_open{service="code-forge"} == 1
        for: 1m
        labels:
          severity: warning

      - alert: CodeForgeBuildFailure
        expr: rate(codeforge_build_failures_total[10m]) > 0.1
        for: 5m
        labels:
          severity: critical
```

---

## 24. Roadmap e Evolução Futura

### 24.1 Visão Geral do Roadmap NHM

O Neural Hive-Mind segue um roadmap de 6 fases estratégicas, cada uma com deliverables específicos e critérios de sucesso mensuráveis. O roadmap está documentado em `.agent-os/product/roadmap.md` e é atualizado trimestralmente.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ROADMAP NHM - STATUS ATUAL (Março 2026)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ ▓▓▓ Fase 0: Infraestrutura Fundacional (COMPLETA - 100%)                    │
│ ▓▓▓░ Fase 1: Camada de Processamento Cognitivo (75% - EM PROGRESSO)        │
│ ▓▓░░ Fase 2: Orquestração e Coordenação de Swarm (50% - EM PROGRESSO)      │
│ ▓░░░ Fase 3: Auto-Recuperação e Governança (25% - INICIADA)                 │
│ ░░░░ Fase 4: Evolução Estratégica e Aprendizado (10% - PLANEJADA)          │
│ ░░░░ Fase 5: Funcionalidades Enterprise (0% - FUTURA)                       │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 24.2 Fase 0: Infraestrutura Fundacional ✅ COMPLETA

**Status:** 100% Completa | **Período:** Q4 2025 | **Esforço:** 8 semanas

#### ✅ Deliverables Entregues

| Componente | Status | Implementação | Evidência |
|------------|--------|---------------|-----------|
| VPC Multi-Zona | ✅ | 3 AZs com sub-redes públicas/privadas | `infrastructure/terraform/network/` |
| Cluster Kubernetes | ✅ | EKS com auto-scaling, OIDC provider | `k8s/` |
| Container Registry | ✅ | ECR com vulnerability scanning | `.github/workflows/docker-build.yml` |
| Service Mesh Istio | ✅ | mTLS STRICT entre todos serviços | `infrastructure/istio/` |
| OPA Gatekeeper | ✅ | Policy engine para governança | `policies/constraint-templates/` |
| Observability Stack | ✅ | OTEL + Prometheus + Grafana + Jaeger | `observability/`, `monitoring/` |
| Gateway de Intenções | ✅ | FastAPI + ASR/NLU + OAuth2 | `services/gateway-intencoes/` |
| Redis Cluster | ✅ | Cache multi-nó com SSL/TLS | `k8s/redis/` |
| Kafka Event Bus | ✅ | Strimzi com exactly-once | `k8s/kafka/` |
| CI/CD Pipelines | ✅ | GitHub Actions workflows | `.github/workflows/` |
| Neural Hive Observability | ✅ | Biblioteca Python padronizada | `libraries/python/neural_hive_observability/` |

#### 📊 Critérios de Sucesso Atendidos

- ✅ Latência do event bus: <100ms (target: <150ms)
- ✅ 100% de recursos com tags de governança
- ✅ Gateway implantado e testado E2E

#### 📝 Lições Aprendidas

1. **Latência Kafka:** Configuração inicial com `linger.ms=5` reduziu throughput para 200 msg/s. Ajuste para `linger.ms=0` + `batch.size=32768` aumentou para 1500 msg/s.
2. **mTLS Overhead:** mTLS STRICT adicionou ~15ms de latência. OTel collector com sidecar mitigou impacto.
3. **Memory Leaks:** OTEL exporter sem batch causava memory leaks. Solução: `BatchSpanProcessor` com `max_queue_size=2048`.

---

### 24.3 Fase 1: Camada de Processamento Cognitivo 🟡 75% EM PROGRESSO

**Status:** 75% Completo | **Período:** Q1 2026 | **Esforço Estimado:** 12 semanas

#### ✅ Componentes Implementados

| Componente | Status | Implementação | Gap |
|------------|--------|---------------|-----|
| Semantic Translation Engine | ✅ | `services/semantic-translation-engine/` | - |
| Business Specialist | ✅ | `services/specialist-business/` | Modelos com ~50% confiança |
| Technical Specialist | ✅ | `services/specialist-technical/` | Modelos com ~50% confiança |
| Behavior Specialist | ✅ | `services/specialist-behavior/` | Modelos com ~50% confiança |
| Evolution Specialist | ✅ | `services/specialist-evolution/` | Modelos com ~50% confiança |
| Architecture Specialist | ✅ | `services/specialist-architecture/` | Modelos com ~50% confiança |
| Consensus Mechanism | ✅ | Bayesian Model Averaging | Degradação frequente |
| Multi-Layer Memory | 🟡 | Redis + MongoDB (parcial) | ClickHouse + Graph pendentes |
| Pheromone Protocol | ✅ | `libraries/python/neural_hive_specialists/` | - |
| Risk Scoring Engine | ✅ | `services/semantic-translation-engine/` | - |
| Explainability Generator | 🟡 | Parcialmente implementado | Explicações genéricas |

#### 🟡 Gaps Identificados

**1. Modelos ML com Baixa Confiança**
```python
# Problema: Modelos treinados com dados sintéticos
confidence = specialist.predict(features)  # Retorna ~0.5 (aleatório)

# Solução Planejada: Coleta de dados reais + retraining
# - Coletar 1000+ decisões humanas
# - Retreinar com feedback loop
# - Meta: confidence > 0.8 para decisões claras
```

**2. Knowledge Graph Não Implementado**
- Planificado: Neo4j ou JanusGraph para relacionamentos semânticos
- Atual: Apenas Redis + MongoDB
- Gap: Falta recuperação de contexto baseada em grafos
- Solução: `services/knowledge-graph/` planejado para Q2 2026

**3. ClickHouse para Long-Term Memory**
- Planificado: Memória operacional em ClickHouse
- Atual: Apenas MongoDB (limitado a 16MB por documento)
- Gap: Queries analíticas sobre históricos são lentas
- Solução: Migração de dados históricos para ClickHouse

#### 📊 Critérios de Sucesso

| Métrica | Target | Atual | Gap |
|---------|--------|-------|-----|
| Precisão intenções críticas | >90% | ~60% | -30% |
| Tempo resposta cognitiva | <400ms | ~250ms | ✅ |
| Taxa rejeição políticas | <5% | ~8% | +3% |
| Trilhas auditoria | 100% | 95% | -5% |

---

### 24.4 Fase 2: Orquestração e Coordenação de Swarm 🟡 50% EM PROGRESSO

**Status:** 50% Completo | **Período:** Q1-Q2 2026 | **Esforço Estimado:** 16 semanas

#### ✅ Componentes Implementados

| Componente | Status | Implementação | Notas |
|------------|--------|---------------|-------|
| Dynamic Orchestrator | ✅ | `services/orchestrator-dynamic/` | Temporal workflow implementado |
| SLA Management | ✅ | `services/sla-management-system/` | Circuit breakers + timeouts |
| Queen Agent | ✅ | `services/queen-agent/` | Coordenação implementada |
| Scout Agent | ✅ | `services/scout-agents/` | Exploração de caminhos |
| Worker Agent Pool | ✅ | `services/worker-agents/` | Execução + compensation |
| Guard Agent | ✅ | `services/guard-agents/` | Validação de segurança |
| Optimizer Agent | ✅ | `services/optimizer-agents/` | Otimização de performance |
| Analyst Agent | ✅ | `services/analyst-agents/` | Análise de dados |
| MCP Tool Catalog | ✅ | `services/mcp-tool-catalog/` | 87+ ferramentas indexadas |
| Service Registry | ✅ | `services/service-registry/` | gRPC discovery |

#### 🟡 Gaps Críticos

**1. MCP Integration Parcial**
```
Total de Ferramentas MCP: 87
Integradas: ~23 (26%)
Pendentes: ~64 (74%)

Status por Categoria:
┌────────────────────────┬───────┬──────────┬────────────┐
│ Categoria             │ Total │ Prontas │ Pendentes  │
├────────────────────────┼───────┼──────────┼────────────┤
│ Analysis (15)          │  15   │    8     │     7      │
│ Generation (20)        │  20   │    5     │    15      │ ⚠️
│ Transformation (18)    │  18   │    4     │    14      │ ⚠️
│ Validation (12)        │  12   │    3     │     9      │ ⚠️
│ Automation (12)        │  12   │    2     │    10      │ ⚠️
│ Integration (10)       │  10   │    1     │     9      │ ⚠️
└────────────────────────┴───────┴──────────┴────────────┘
```

**2. Code Forge Completude (Gap Crítico)**
- **Spec Atual:** `2026-03-11-code-forge-completude`
- **Progresso:** 6/6 tarefas principais completadas
- **Gap:** Approval Gate MR workflow precisa de validação E2E
- **Próximo:** Integração com GitLab/GitHub API real (não stub)

#### 📊 Critérios de Sucesso

| Métrica | Target | Atual | Gap |
|---------|--------|-------|-----|
| Throughput intenções/hora | >500 | ~120 | -380 | ⚠️ |
| Taxa reuso componentes | >60% | ~35% | -25% | ⚠️ |
| Validação E2E | ✅ | 🟡 Parcial | Deploy staging |
| Tolerância a falhas | >99% | ~95% | -4% |

**Bloqueador Principal:** Throughput limitado por:
1. Latência Code Forge (container build: ~3-5min)
2. Workers executam sequencialmente (paralelização pendente)
3. MCP tools lentas (algumas ferramentas: 10-30s)

---

### 24.5 Fase 3: Auto-Recuperação e Governança 🟠 25% INICIADA

**Status:** 25% Completo | **Período:** Q2 2026 | **Esforço Estimado:** 10 semanas

#### ✅ Componentes Iniciados

| Componente | Status | Implementação | Gap |
|------------|--------|---------------|-----|
| Self-Healing Service | 🟡 | `services/self-healing-engine/` | Apenas detector básico |
| Runbook Execution | ❌ | Não implementado | Falta motor de execução |
| Anomaly Detection | 🟡 | ML models treinados | Precisa de dados reais |
| Distributed Tracing | ✅ | OpenTelemetry completo | Correlation parcial |
| Chaos Engineering | ❌ | Não implementado | Falta suite de testes |

#### 🟠 Gaps Principais

**1. Self-Healing Semi-Implementado**
```python
# Atual: Apenas detecção
if anomaly_score > threshold:
    logger.warning("anomaly_detected", score=anomaly_score)
    # TODO: Trigger automatic remediation

# Planejado: Execução automática de runbooks
if anomaly_score > threshold:
    runbook = self.runbook_engine.match(anomaly_type)
    await runbook.execute()
```

**2. Runbooks Manuais**
- 24 runbooks documentados em `docs/runbooks/`
- Execução 100% manual
- Gap: Automatização de execução pendente

**3. Anomaly Detection sem Dados Reais**
- Modelos treinados com dados sintéticos
- False positives: ~40%
- Solução: Coletar 30 dias de dados de produção

#### 📊 Critérios de Sucesso

| Métrica | Target | Atual | Gap |
|---------|--------|-------|-----|
| Taxa sucesso auto-correção | >80% | ~10% | -70% | ⚠️ |
| MTTR (Mean Time to Recover) | <30min | ~4h | +3.5h | ⚠️ |
| Cobertura políticas críticas | 100% | ~60% | -40% | ⚠️ |
| Chaos engineering validado | ✅ | ❌ | Não executado |

---

### 24.6 Fase 4: Evolução Estratégica 🔵 10% PLANEJADA

**Status:** 10% Planejado | **Período:** Q3 2026 | **Esforço Estimado:** 12 semanas

#### 🔵 Planejamento Inicial

| Componente | Status | Planejamento | Dependências |
|------------|--------|--------------|--------------|
| Experimentation Engine | 🔵 | Design preliminar | Fase 3 completa |
| A/B Testing Framework | 🔵 | Requisitos definidos | Fase 3 completa |
| Online Learning Pipeline | 🔵 | Arquitetura definida | Dados de produção |
| Model Drift Detection | ❌ | Não iniciado | Training pipeline |
| Meta-Learning System | ❌ | Não iniciado | Experimentation Engine |

#### 🔵 Gaps de Design

**1. Experimentation Engine - Arquitetura Não Definida**
```
Componentes Necessários:
┌─────────────────────────────────────────────────────────┐
│  Hypothesis Generator  │  │  Experiment Executor  │
│  (ML-based)           │  │  (Canary deployment)   │
├─────────────────────────┼─────────────────────────────┤
│  Statistical Validator │  │  Impact Analyzer       │
│  (Significance test)   │  │  (Cost-benefit)        │
├─────────────────────────┼─────────────────────────────┤
│  Rollback Orchestrator │  │  Learning Registry     │
│  (Auto-revert)         │  │  (MLflow extension)    │
└─────────────────────────────────────────────────────────┘
```

**2. A/B Testing - Sem Design Estatístico**
- Questões em aberto:
  - Qual teste de significância? (t-test, Wilcoxon, Bayesian?)
  - Como definir sample size?
  - Como lidar com novelty effects?

#### 📊 Critérios de Sucesso (Planejados)

| Métrica | Target | Notas |
|---------|--------|-------|
| Ciclo experimentação | <4 semanas | Inclui análise estatística |
| Taxa adoção experimentos | >70% | Baseado em ROI positivo |
| Documentação experimentos | 100% | Hypothesis Library |
| Dashboard executivo | ✅ | Visual de evolução |

---

### 24.7 Fase 5: Funcionalidades Enterprise ⚪ PLANEJADA

**Status:** 0% Planejado | **Período:** Q4 2026 | **Esforço Estimado:** 16 semanas

#### ⚪ Áreas de Foco

| Área | Prioridade | Complexidade | Dependências |
|------|------------|--------------|--------------|
| Multi-Region Deployment | Alta | XL | Fase 2 completa |
| Advanced Multi-Tenancy | Alta | L | Fase 4 parcial |
| Enterprise SSO | Média | M | Fase 1 completa |
| Custom Model Fine-Tuning | Média | XL | Fase 4 completa |
| White-Label UI | Baixa | L | Design system |
| Compliance Pack | Alta | XL | Fase 3 completa |
| Cost Optimization | Média | M | Fase 4 completa |

---

### 24.8 Specs Recentes e Trabalho em Progresso

#### Março 2026: Spec Code Forge Completude

**Arquivo:** `docs/specs/2026-03-11-code-forge-completude/`

**Status:** ✅ Todas as 7 tarefas completadas

| Tarefa | Status | Entregável |
|--------|--------|-----------|
| 1. Approval Gate completo | ✅ | Commit + Push + MR funcional |
| 2. Medição precisa tempo | ✅ | `execution_time_ms` real medido |
| 3. Cleanup workspace | ✅ | Cleanup com retry implementado |
| 4. Validação licenças | ✅ | `LicenseValidator` implementado |
| 5. Test Runner JS/TS | ✅ | Executor Node.js com Jest |
| 6. Templates versionados | ✅ | Git tags para versionamento |
| 7. Testes E2E | ✅ | Suite completa passando |

**Próximos Passos:**
1. Validação em ambiente staging (GitLab real)
2. Medição de throughput com Approval Gate completo
3. Documentação de runbook para operação

#### Março 2026: Spec Worker Agent Corrections

**Arquivo:** `docs/specs/2026-03-06-correcao-worker-agent/`

**Status:** ✅ Todas as correções implementadas

| Bug | Correção | Impacto |
|-----|----------|---------|
| ExecutionEngine sempre COMPLETED | Verifica `result['success']` | Status correto |
| Parâmetros STE genéricos | Parâmetros específicos por executor | Menos erros |
| Motor 3.x compatibility | Acesso direto `client[db][collection]` | MongoDB funcionando |

**Validação:** Testes E2E passando, workflow completo funcionando

---

### 24.9 Timeline Realista (Atualizada Março 2026)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ NEURAL HIVE-MIND - TIMELINE REALISTA 2026                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Q1 2026 (JAN-MAR)                                                           │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 100%                            │
│  ✅ Fase 0 Infraestrutura                                                    │
│  🟡 Fase 1 Processamento Cognitivo (75% → 90%)                               │
│     - Re-treinar modelos com dados reais                                     │
│     - Implementar Knowledge Graph (Neo4j)                                    │
│  🟡 Fase 2 Orquestração (50% → 70%)                                          │
│     - Completar MCP tools integration (+15 ferramentas)                      │
│     - Otimizar Code Forge throughput                                         │
│                                                                               │
│  Q2 2026 (ABR-JUN)                                                           │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0%                                 │
│  🟡 Fase 1 Processamento Cognitivo (90% → 100%)                              │
│     - ClickHouse para long-term memory                                       │
│     - Explicações mais detalhadas                                            │
│  🟡 Fase 2 Orquestração (70% → 100%)                                         │
│     - Paralelização de workers                                               │
│     - Integração CI/CD completa                                              │
│  🟠 Fase 3 Auto-Recuperação (25% → 60%)                                      │
│     - Runbook Execution Engine                                               │
│     - Anomaly detection com dados reais                                      │
│     - Chaos engineering suite                                                │
│                                                                               │
│  Q3 2026 (JUL-SET)                                                           │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0%                                 │
│  🟢 Fase 3 Auto-Recuperação (60% → 100%)                                     │
│     - Taxa de auto-correção >80%                                            │
│     - MTTR <30min                                                            │
│  🔵 Fase 4 Evolução Estratégica (0% → 40%)                                  │
│     - Experimentation Engine MVP                                            │
│     - A/B Testing Framework                                                  │
│     - Online Learning Pipeline inicial                                       │
│                                                                               │
│  Q4 2026 (OUT-DEZ)                                                           │
│  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 0%                                 │
│  🔵 Fase 4 Evolução Estratégica (40% → 80%)                                  │
│     - Model Drift Detection                                                 │
│     - Incremental Deployment System                                          │
│  ⚪ Fase 5 Enterprise (0% → 30%)                                              │
│     - Multi-Region Deployment POC                                            │
│     - Enterprise SSO (SAML)                                                  │
│     - Compliance Pack (GDPR)                                                 │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 24.10 Riscos e Bloqueadores

#### 🔴 Riscos Críticos

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|------------|
| **Modelos ML não convergem** | Alta | Crítico | Coleta agressiva de dados + fine-tuning |
| **Throughput Code Forge** | Média | Alto | Paralelização + cache de builds |
| **MCP tools lentas** | Alta | Médio | Timeout agressivo + fallback |
| **Multi-Region custo** | Alta | Alto | Iniciar com 2 regiões apenas |

#### 🟡 Riscos Médios

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|------------|
| **Knowledge Graph complexidade** | Média | Médio | Começar com subgrafo específico |
| **Chaos Engineering抗拒** | Média | Médio | Gradual, começar com non-prod |
| **Enterprise SSO scope creep** | Alta | Médio | Definir escopo claro inicial |

---

### 24.11 DependênciasExternas

| Dependência | Versão Mínima | Status | Notas |
|-------------|---------------|--------|-------|
| Kubernetes | 1.28+ | ✅ | EKS/GKE suportados |
| Istio | 1.20+ | ✅ | mTLS STRICT funcionando |
| Temporal | 1.22+ | ✅ | Cluster de 3 nós |
| Kafka (Strimzi) | 0.38+ | ✅ | Exactly-once configurado |
| MongoDB | 7.0+ | ✅ | ReplicaSet 3 nós |
| Redis | 7.2+ | ✅ | Cluster SSL/TLS |
| Neo4j | 5.15+ | ❌ | Não instalado ainda |
| ClickHouse | 24.3+ | ❌ | Não instalado ainda |
| MLflow | 2.12+ | ✅ | Deploy MLflow |
| Keycloak | 25.0+ | ✅ | OAuth2 provider |

---

## 25. ML Specialists - Detalhes Técnicos

### Arquitetura dos Especialistas

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    ML SPECIALISTS ARCHITECTURE                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Cada especialista é um modelo ML treinado com:                                 │
│  - Base: Scikit-learn RandomForest + XGBoost                                    │
│  - Features: ~500 (text embeddings, metadados, contextos)                     │
│  - Output: {recommendation: approve/reject/conditional, confidence: 0.0-1.0}  │
│  - Training: Dados históricos de decisões + feedback humano                     │
│  - Versionamento: MLflow                                                       │
│                                                                                  │
│  ┌──────────────────┬──────────────────┬──────────────────┬───────────────────┐ │
│  │ Business Evaluator │ Technical Evaluator│ Behavior Evaluator│ Evolution Evaluator│ │
│  └──────────────────┴──────────────────┴──────────────────┴───────────────────┘ │
│                                  │                                             │
│  ┌─────────────────────────────────┴──────────────────────────────────────┐ │
│  │           Architecture Evaluator (Domain Expert)                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 26. Exemplos de Prompts LLM

### Prompt para Geração de Código

```python
CODE_GENERATION_PROMPT_TEMPLATE = """
You are an expert software engineer working on the Neural Hive-Mind platform.
Your task is to generate production-ready code based on the requirements below.

## Context
- Service Name: {service_name}
- Description: {description}
- Programming Language: {language}
- Framework: {framework}

## Requirements
{requirements}

## Generated Code Requirements

Your code MUST include:
1. **Type Hints**: All functions must have proper type hints
2. **Docstrings**: Google-style docstrings for all classes/functions
3. **Error Handling**: Comprehensive try-except with specific exceptions
4. **Logging**: Structured logging with context
5. **Configuration**: Environment-based configuration
6. **Health Checks**: /health endpoint for readiness/liveness probes
7. **Metrics**: Prometheus metrics exposition
8. **Testing**: Unit tests example (pytest style)

Return ONLY the complete code without markdown code blocks.
"""
```

---

## 27. Temporal Workflow - Detalhes Avançados

### Definição do Workflow

```python
@workflow.defn
class PlanExecutionWorkflow:
    """Workflow Temporal para execução de planos cognitivos"""

    @workflow.run
    async def run(
        self,
        plan_id: str,
        decision: ConsolidatedDecision
    ) -> WorkflowResult:
        """Executa workflow completo de plano"""

        # C1: Validar Plano
        validation_result = await activities.validate_plan(plan_id, decision)

        # C2: Gerar Tickets
        tickets = await activities.generate_tickets(
            plan_id=plan_id,
            cognitive_plan=decision.cognitive_plan,
            consensus_decision=decision
        )

        # C3: Publicar Tickets
        for ticket in tickets:
            await activities.publish_ticket(ticket)

        # C4-C6: Aguardar, Compilar, Persistir
        # ...

        return WorkflowResult(status="COMPLETED", results=results)
```

---

## 28. Integrações Externas

### Service Mesh (Istio)

```yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: neural-hive-mesh
spec:
  hosts:
  - "neural-hive.local"
  http:
  - match:
    - uri:
        prefix: /api/v1/intentions
    route:
    - destination:
        host: gateway-intencoes
        port:
          number: 8080
```

---

## 29. Casos de Uso por Indústria

### Caso 1: Fintech - API de Transações

```
Intenção: "Criar API para processar transações de cartão de crédito
com validação de fraude e conformidade PCI-DSS"

Fluxo:
1. Domain = FINANCE
2. Tasks: Payment API, Fraud detection, PCI-DSS validator
3. Code Forge → FastAPI + Stripe SDK + OPA policies
```

### Caso 2: Saúde - Telemedicina Platform

```
Intenção: "Criar plataforma de telemedicina com agendamento,
videochamada e prontuário eletrônico"

Fluxo:
1. Domain = HEALTHCARE
2. Risco alto (dados de saúde) → Requer aprovação manual
3. Code Forge → Appointment API, WebRTC integration, EHR with FHIR
```

---

## 30. Performance e Custos

### Tempos Típicos de Execução

| Etapa | Tempo P50 | Tempo P99 |
|-------|-----------|-----------|
| Gateway → Kafka | 50ms | 200ms |
| STE (processamento) | 1s | 5s |
| Consensus (ML) | 2s | 10s |
| Orchestrator (tickets) | 200ms | 2s |
| Code Forge (geração) | 10s | 60s |
| Container Build | 30s | 90s |
| **TOTAL** | **~45s** | **~3min** |

### Custo Infraestrutura AWS (Mensal)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    AWS INFRASTRUCTURE COST (Monthly)                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│ Component                     │ Qty │ Cost/month                                 │
│-------------------------------|-----│-------------------------------------------│
│ EKS Cluster (m5.large)        │  3  │ $360                                      │
│ Microserviços (various)       │  20 │ $720                                      │
│ MongoDB (3 replicas + EBS)    │  3  │ $750                                      │
│ Redis Cluster                 │  3  │ $390                                      │
│ Kafka (3 brokers + EBS)       │  3  │ $1,065                                    │
│ Observability (Jaeger+Prom)   │  3  │ $300                                      │
│ Anthropic Claude API          │     │ $500 (assumindo 1000 requests)           │
├───────────────────────────────┴─────┴───────────────────────────────────────────┤
│ TOTAL                        │     │ ~$4,085/month                               │
└─────────────────────────────────────────────────────────────────────────────────┘

Custo por intenção processada:
- 1000 intenções/mês = ~$4.09/intenção
- 10000 intenções/mês = ~$0.41/intenção (economia de escala)
```

---

## Tópicos Kafka (Resumo Completo)

| Tópico | Produtor | Consumidor | Conteúdo |
|--------|----------|------------|----------|
| `intentions.{domain}` | Gateway | STE | IntentEnvelope |
| `plans.ready` | STE | Orchestrator | CognitivePlan (aprovado automaticamente) |
| `plans.consensus` | Consensus | Orchestrator | ConsolidatedDecision |
| `plans.approvals` | STE | Approval Service | ApprovalRequest |
| `plans.approvals.responses` | Approval Service | Orchestrator | ApprovalResponse |
| `execution.tickets` | Orchestrator | Worker Agents | ExecutionTicket |
| `execution.results` | Worker Agents | Orchestrator | ExecutionResult |
| `pheromone.consensus` | Consensus | Redis | PheromoneSignals |

---

## Pontos de Decisão do Fluxo

| Ponto | Critério | Caminho Alternativo |
|-------|----------|---------------------|
| **STE** | `risk_score >= 0.7` ou `is_destructive` | Publica em `plans.approvals` |
| **Consensus** | `divergence > threshold` | Aplica fallback determinístico |
| **Orchestrator** | Aprovação manual pendente | Aguarda `ApprovalResponse` |
| **Worker** | Ticket duplicado detectado | Skip processamento |
| **Code Forge** | LLM falha | Fallback para template |

---

## Conclusão

O Neural Hive-Mind implementa uma arquitetura sofisticada de geração de código com:

- **Resiliência**: Circuit breakers, deduplicação two-phase (Redis/MongoDB)
- **Escalabilidade**: Kafka com partitions, Kubernetes HPA
- **Observabilidade**: OpenTelemetry tracing end-to-end
- **Segurança**: OPA para autorização, approval workflow para high-risk
- **Flexibilidade**: Multiple generation methods, multi-language support

Esta análise cobre todo o fluxo desde a intenção (`POST /api/v1/intentions/`) até o código gerado e executável.

---

## 31. Arquitetura Kafka - Detalhes de Mensageria

### Configuração dos Tópicos

```yaml
# infrastructure/kafka/topics.yaml

topics:
  intentions-security:
    partitions: 3
    replication-factor: 3
    config:
      retention.ms: 86400000  # 24 horas
      cleanup.policy: delete
      max.message.bytes: 10485760  # 10MB

  plans-ready:
    partitions: 3
    replication-factor: 3
    config:
      retention.ms: 604800000  # 7 dias
      cleanup.policy: delete
      compression.type: lz4

  plans-consensus:
    partitions: 3
    replication-factor: 3
    config:
      retention.ms: 604800000
      cleanup.policy: delete

  execution-tickets:
    partitions: 6  # Mais partições para paralelismo
    replication-factor: 3
    config:
      retention.ms: 2592000000  # 30 dias
      cleanup.policy: delete
      max.message.bytes: 5242880  # 5MB

  pheromone-consensus:
    partitions: 3
    replication-factor: 3
    config:
      retention.ms: 2592000000  # 30 dias (aprendizado ML)
      cleanup.policy: delete
      compact: true  # Habilitar log compaction
```

### Consumer Groups

```python
# Configuração de Consumer Groups por serviço

KAFKA_CONSUMER_GROUPS = {
    "semantic-translation-engine": {
        "topics": ["intentions.business", "intentions.technical", "intentions.security"],
        "group_id": "ste-consumer-group",
        "auto_offset_reset": "earliest",
        "enable_auto_commit": False,
        "max_poll_records": 10,
        "session_timeout_ms": 30000,
    },
    "consensus-engine": {
        "topics": ["plans.ready"],
        "group_id": "consensus-consumer-group",
        "auto_offset_reset": "earliest",
        "max_poll_interval_ms": 300000,
    },
    "worker-agents": {
        "topics": ["execution.tickets"],
        "group_id": "worker-consumer-group",
        "auto_offset_reset": "latest",
        "max_poll_records": 5,
        "heartbeat_interval_ms": 3000,
    },
}
```

### Semântica de Exatamente-Once

```python
# services/gateway-intencoes/src/kafka/producer.py

class TransactionalKafkaProducer:
    """Producer com semântica exactly-once"""

    def __init__(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            transactional_id=f"gateway-{os.getenv('POD_NAME', 'local')}",
            enable_idempotence=True,
            acks="all",
            max_in_flight_requests_per_connection=5,
            compression_type="lz4",
        )

    async def publish_intent(self, intent_envelope: IntentEnvelope) -> None:
        """Publica intenção com transactional semantics"""

        async with self.producer.transaction():
            # Serializar com Avro Schema Registry
            avro_bytes = await self.avro_serializer.serialize(
                topic=f"intentions.{intent_envelope.intent.domain.value}",
                data=intent_envelope.dict()
            )

            # Publicar com headers de tracing
            await self.producer.send_and_wait(
                topic=f"intentions.{intent_envelope.intent.domain.value}",
                value=avro_bytes,
                headers=[
                    ("traceparent", intent_envelope.trace_id.encode()),
                    ("correlation-id", intent_envelope.correlation_id.encode()),
                    ("content-type", "application/avro".encode()),
                ]
            )

            # Commit transação
            await self.producer.commit_transaction()
```

---

## 32. Implementação dos Executores

### BaseExecutor

```python
# services/worker-agents/src/executors/base_executor.py

class BaseExecutor(ABC):
    """Classe base para todos os executores"""

    def __init__(self):
        self.mongodb_client = MongoDBClient()
        self.redis_client = RedisClient()
        self.logger = structlog.get_logger(__name__)

    @abstractmethod
    async def execute(self, ticket: ExecutionTicket) -> Dict:
        """Executa a ticket. Deve ser implementado por subclasses."""
        pass

    async def validate_required_parameters(
        self,
        ticket_id: str,
        parameters: Dict,
        required: List[str]
    ) -> None:
        """Valida parâmetros obrigatórios"""

        missing = [p for p in required if p not in parameters]
        if missing:
            raise ExecutorValidationException(
                f"Ticket {ticket_id} missing required parameters: {missing}"
            )
```

### CodeForgeExecutor

```python
# services/worker-agents/src/executors/code_forge_executor.py

class CodeForgeExecutor(BaseExecutor):
    """Executor para tarefas de geração de código"""

    def __init__(self):
        super().__init__()
        self.code_forge_url = settings.code_forge_url
        self.timeout = settings.code_forge_timeout

    async def execute(self, ticket: ExecutionTicket) -> Dict:
        """Executa geração de código via Code Forge"""

        await self.validate_required_parameters(
            ticket.ticket_id,
            ticket.parameters,
            required=["service_name", "artifact_type", "language"]
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.code_forge_url}/api/v1/generate",
                    json={
                        "ticket_id": ticket.ticket_id,
                        "parameters": ticket.parameters,
                        "trace_context": {
                            "trace_id": ticket.trace_id,
                            "span_id": ticket.span_id,
                        }
                    }
                )
                response.raise_for_status()

                result = response.json()

                return {
                    "success": True,
                    "artifact_id": result.get("artifact_id"),
                    "image_uri": result.get("image_uri"),
                    "confidence": result.get("confidence"),
                }

        except httpx.TimeoutException:
            self.logger.error("code_forge_timeout", ticket_id=ticket.ticket_id)
            return {
                "success": False,
                "error": "Code Forge timeout",
                "error_code": "TIMEOUT"
            }

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "code_forge_http_error",
                ticket_id=ticket.ticket_id,
                status_code=e.response.status_code
            )
            return {
                "success": False,
                "error": f"Code Forge HTTP error: {e.response.status_code}",
                "error_code": "HTTP_ERROR"
            }
```

### QueryExecutor

```python
# services/worker-agents/src/executors/query_executor.py

class QueryExecutor(BaseExecutor):
    """Executor para queries MongoDB"""

    async def execute(self, ticket: ExecutionTicket) -> Dict:
        """Executa query MongoDB"""

        await self.validate_required_parameters(
            ticket.ticket_id,
            ticket.parameters,
            required=["collection"]
        )

        collection_name = ticket.parameters.get("collection")
        query = ticket.parameters.get("query", {})
        projection = ticket.parameters.get("projection", None)
        limit = ticket.parameters.get("limit", 100)

        try:
            database = ticket.parameters.get("database", "neural_hive")
            collection = self.mongodb_client.client[database][collection_name]

            cursor = collection.find(query, projection).limit(limit)
            results = await cursor.to_list(length=limit)

            return {
                "success": True,
                "count": len(results),
                "results": results,
            }

        except Exception as e:
            self.logger.error(
                "mongodb_query_failed",
                ticket_id=ticket.ticket_id,
                error=str(e)
            )
            return {
                "success": False,
                "error": str(e),
                "error_code": "MONGO_ERROR"
            }
```

### TransformExecutor

```python
# services/worker-agents/src/executors/transform_executor.py

class TransformExecutor(BaseExecutor):
    """Executor para transformações de dados"""

    async def execute(self, ticket: ExecutionTicket) -> Dict:
        """Executa transformação JSON"""

        await self.validate_required_parameters(
            ticket.ticket_id,
            ticket.parameters,
            required=["input_data", "transform_type"]
        )

        transform_type = ticket.parameters.get("transform_type")
        input_data = ticket.parameters.get("input_data")

        try:
            if transform_type == "map":
                result = self._apply_map(input_data, ticket.parameters)
            elif transform_type == "filter":
                result = self._apply_filter(input_data, ticket.parameters)
            elif transform_type == "aggregate":
                result = self._apply_aggregate(input_data, ticket.parameters)
            elif transform_type == "enrich":
                result = await self._apply_enrichment(input_data, ticket.parameters)
            else:
                raise ValueError(f"Unknown transform_type: {transform_type}")

            return {
                "success": True,
                "result": result,
                "transform_type": transform_type,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": "TRANSFORM_ERROR"
            }

    def _apply_map(self, data: List[Dict], params: Dict) -> List[Dict]:
        """Aplica transformação map"""
        mapping = params.get("mapping", {})
        return [{k: item.get(v) for k, v in mapping.items()} for item in data]

    def _apply_filter(self, data: List[Dict], params: Dict) -> List[Dict]:
        """Aplica filtro"""
        conditions = params.get("conditions", {})
        return [item for item in data if self._match_conditions(item, conditions)]
```

### ValidateExecutor

```python
# services/worker-agents/src/executors/validate_executor.py

class ValidateExecutor(BaseExecutor):
    """Executor para validações OPA"""

    def __init__(self):
        super().__init__()
        self.opa_url = settings.opa_url

    async def execute(self, ticket: ExecutionTicket) -> Dict:
        """Executa validação de política OPA"""

        await self.validate_required_parameters(
            ticket.ticket_id,
            ticket.parameters,
            required=["policy_path"]
        )

        policy_path = ticket.parameters.get("policy_path")
        input_data = ticket.parameters.get("input_data", {})

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.opa_url}/v1/data{policy_path}",
                    json={"input": input_data}
                )
                response.raise_for_status()

                opa_result = response.json()

                # Verificar se permitido
                if opa_result.get("result", {}).get("allow", False):
                    return {
                        "success": True,
                        "allowed": True,
                        "policy": policy_path,
                    }
                else:
                    return {
                        "success": True,
                        "allowed": False,
                        "policy": policy_path,
                        "reason": opa_result.get("result", {}).get("reason", "Denied by policy"),
                    }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_code": "OPA_ERROR"
            }
```

---

## 33. Padrões de Comunicação Inter-Service

### gRPC Service Definitions

```protobuf
// services/orchestrator-dynamic/proto/orchestrator.proto

syntax = "proto3";

package orchestrator;

service OrchestratorService {
  rpc GetWorkflowStatus(WorkflowStatusRequest) returns (WorkflowStatusResponse);
  rpc CancelWorkflow(CancelWorkflowRequest) returns (CancelWorkflowResponse);
  rpc ListActiveWorkflows(ListWorkflowsRequest) returns (ListWorkflowsResponse);
}

message WorkflowStatusRequest {
  string plan_id = 1;
}

message WorkflowStatusResponse {
  string plan_id = 1;
  string status = 2;  // RUNNING, COMPLETED, FAILED, CANCELLED
  int32 tickets_completed = 3;
  int32 tickets_total = 4;
  string current_activity = 5;
  int64 started_at = 6;
  int64 completed_at = 7;
}

message CancelWorkflowRequest {
  string plan_id = 1;
  string reason = 2;
}

message CancelWorkflowResponse {
  bool success = 1;
  string message = 2;
}
```

### REST API Contracts

```python
# services/code-forge/src/api/routes/generate.py

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/generate", tags=["generation"])

class CodeGenerationRequest(BaseModel):
    ticket_id: str = Field(..., description="Unique ticket identifier")
    parameters: Dict[str, Any] = Field(..., description="Generation parameters")
    trace_context: Optional[Dict[str, str]] = Field(None, description="Distributed tracing context")

    class Config:
        json_schema_extra = {
            "example": {
                "ticket_id": "tk-123",
                "parameters": {
                    "service_name": "user-management",
                    "artifact_type": "MICROSERVICE",
                    "language": "python",
                    "framework": "fastapi",
                }
            }
        }

class CodeGenerationResponse(BaseModel):
    success: bool
    artifact_id: Optional[str] = None
    image_uri: Optional[str] = None
    confidence: Optional[float] = None
    generation_method: Optional[str] = None
    error: Optional[str] = None

@router.post("/", response_model=CodeGenerationResponse, status_code=status.HTTP_200_OK)
async def generate_code(request: CodeGenerationRequest) -> CodeGenerationResponse:
    """
    Gera código baseado nos parâmetros fornecidos.

    - **ticket_id**: Identificador único do ticket
    - **parameters**: Parâmetros de geração (linguagem, framework, etc.)
    - **trace_context**: Contexto para tracing distribuído

    Retorna artefatos gerados incluindo ID e URI da imagem container.
    """
    result = await code_generation_service.generate(request)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Unknown error")
        )

    return result
```

---

## 34. Estratégias de Retry e Backoff

### Configuração de Retry Exponencial

```python
# neural_hive_resilience/retry.py

class RetryConfig(BaseSettings):
    """Configuração de retry para serviços"""

    max_attempts: int = 3
    base_delay_ms: int = 1000
    max_delay_ms: int = 30000
    multiplier: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.1

class AsyncRetry:
    """Implementação de retry com backoff exponencial"""

    def __init__(self, config: RetryConfig):
        self.config = config

    async def execute(
        self,
        func: Callable,
        *args,
        context: Optional[Dict] = None,
        **kwargs
    ) -> Any:
        """Executa função com retry"""

        last_exception = None
        delay = self.config.base_delay_ms / 1000  # Convert to seconds

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                if attempt > 1:
                    logger.info(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=self.config.max_attempts
                    )

                result = await func(*args, **kwargs)
                return result

            except Exception as e:
                last_exception = e

                # Se é o último attempt, re-raise
                if attempt >= self.config.max_attempts:
                    logger.error(
                        "retry_exhausted",
                        function=func.__name__,
                        attempts=attempt,
                        error=str(e)
                    )
                    raise

                # Calcular delay com jitter
                if self.config.jitter:
                    jitter_amount = delay * self.config.jitter_range
                    delay = delay + random.uniform(-jitter_amount, jitter_amount)

                logger.warning(
                    "retry_delay",
                    function=func.__name__,
                    attempt=attempt,
                    delay_seconds=delay,
                    error=str(e)
                )

                await asyncio.sleep(delay)

                # Exponential backoff
                delay = min(
                    delay * self.config.multiplier,
                    self.config.max_delay_ms / 1000
                )

        raise last_exception
```

---

## 35. Padrão Dead Letter Queue (DLQ)

### Configuração DLQ para Mensagens Falhas

```python
# services/worker-agents/src/consumers/dlq_handler.py

class DeadLetterQueueHandler:
    """Manipulador de DLQ para mensagens que falharam"""

    def __init__(self):
        self.dlq_producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers
        )
        self.dlq_topics = {
            "execution.tickets": "execution.tickets.dlq",
            "plans.ready": "plans.ready.dlq",
        }

    async def send_to_dlq(
        self,
        original_topic: str,
        message: bytes,
        error: Exception,
        metadata: Dict
    ) -> None:
        """Envia mensagem para DLQ"""

        dlq_topic = self.dlq_topics.get(original_topic)
        if not dlq_topic:
            logger.warning("no_dlq_topic", original_topic=original_topic)
            return

        dlq_message = {
            "original_topic": original_topic,
            "original_message": base64.b64encode(message).decode(),
            "error": str(error),
            "error_type": type(error).__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata,
            "retry_count": metadata.get("retry_count", 0) + 1,
        }

        await self.dlq_producer.send_and_wait(
            topic=dlq_topic,
            value=json.dumps(dlq_message).encode(),
            headers=[
                ("original-topic", original_topic.encode()),
                ("error-type", type(error).__name__.encode()),
            ]
        )

        logger.info(
            "sent_to_dlq",
            original_topic=original_topic,
            dlq_topic=dlq_topic,
            error=str(error)
        )
```

---

## 36. Métricas de Business Intelligence

### Métricas de Valor de Negócio

```python
# services/semantic-translation-engine/src/metrics/business_metrics.py

class BusinessMetrics:
    """Métricas de valor para o negócio"""

    @staticmethod
    def track_intent_outcome(intent_envelope: IntentEnvelope, outcome: str):
        """Rastreia resultado de intenção para métricas de negócio"""

        metrics = {
            "intent_outcome_total": 1,
            "intent_outcome_duration_seconds": time.time() - intent_envelope.timestamp,
        }

        # Labels para agregação
        labels = {
            "domain": intent_envelope.intent.domain.value,
            "outcome": outcome,  # SUCCESS, FAILED, APPROVED, REJECTED
            "actor_type": intent_envelope.actor.actor_type.value,
            "has_approval": str(intent_envelope.constraints.get("requires_approval", False)),
        }

        # Export para Prometheus
        for metric_name, value in metrics.items():
            prometheus_metrics[
                f"neural_hive_business_{metric_name}"
            ].labels(**labels).inc(value)

    @staticmethod
    def calculate_time_to_code(intent_envelope: IntentEnvelope) -> float:
        """Calcula tempo até código gerado"""

        start_time = intent_envelope.timestamp
        # Buscar timestamp de conclusão do workflow
        end_time = datetime.utcnow().timestamp()

        return end_time - start_time
```

---

## 37. Glossário de Termos

| Termo | Definição |
|-------|-----------|
| **Cognitive Plan** | Estrutura de dados contendo tasks geradas a partir de uma intenção |
| **Execution Ticket** | Unidade de trabalho executada pelo Worker Agent |
| **Pheromone** | Sinal de aprendizado armazenado no Redis para especialistas ML |
| **Saga Compensation** | Padrão de rollback para transações distribuídas |
| **Consolidated Decision** | Decisão final agregada dos especialistas ML |
| **IntentEnvelope** | Estrutura que encapsula uma intenção do usuário |
| **DAG** | Directed Acyclic Graph - Grafo de dependências das tasks |
| **Risk Band** | Classificação de risco: LOW, MEDIUM, HIGH, CRITICAL |
| **Flow C** | Fluxo principal do Orchestrator (C1-C6) |
| **Traceparent** | Header W3C para tracing distribuído |

---

## 38. Referências de Arquitetura

### Padrões Utilizados

1. **CQRS (Command Query Responsibility Segregation)**
   - Separação entre leitura e escrita
   - Implementado no Orchestrator Dynamic

2. **Event Sourcing**
   - Ledger imutável no MongoDB
   - Reconstrução de estado a partir de eventos

3. **Circuit Breaker**
   - Proteção contra cascading failures
   - Fallback automático

4. **Saga Pattern**
   - Transações distribuídas com compensação
   - Rollback em caso de falha

5. **Event-Driven Architecture**
   - Kafka como backbone de eventos
   - Desacoplamento entre serviços

6. **Workspace Pattern**
   - Temporal workflows long-running
   - Activities idempotentes

---

## 39. Comandos Úteis de Operação

### Kafka Operations

```bash
# Listar tópicos
kafka-topics.sh --bootstrap-server kafka:9092 --list

# Descrever tópico
kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic execution.tickets

# Consumir mensagens (debug)
kafka-console-consumer.sh --bootstrap-server kafka:9092 \
  --topic execution.tickets --from-beginning --max-messages 10

# Monitorar consumer lag
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group worker-consumer-group
```

### MongoDB Operations

```bash
# Conectar ao MongoDB
mongosh mongodb://mongodb:27017/neural_hive

# Contar documentos por coleção
db.intent_envelope.countDocuments()
db.execution_tickets.countDocuments({status: "COMPLETED"})

# Buscar intenções por domínio
db.intent_envelope.find({"intent.domain": "SECURITY"}).limit(10)

# Índices
db.execution_tickets.getIndexes()
db.execution_tickets.createIndex({"ticket_id": 1}, {unique: true})
db.execution_tickets.createIndex({"status": 1, "created_at": -1})
```

### Redis Operations

```bash
# Conectar ao Redis
redis-cli -h redis

# Verificar chaves de ticket
KEYS ticket:*

# Ver feromônios
KEYS pheromone:*

# Limpar tickets processados antigos
EVAL "local keys = redis.call('KEYS', 'ticket:processed:*') \
      for i=1,#keys,5000 do redis.call('DEL', keys[i]) end \
      return #keys" 0
```

---

## 40. Diagrama de Sequência Completo

```
┌─────────┐    ┌──────────┐    ┌─────────┐    ┌──────────┐    ┌───────────┐
│  User   │───▶│ Gateway  │───▶│  Kafka  │───▶│    STE   │───▶│   Mongo   │
└─────────┘    └──────────┘    └────┬────┘    └──────────┘    └───────────┘
                                          │
                                          ▼
                                    ┌──────────┐    ┌───────────┐
                                    │ Consensus │◀───│  Redis    │
                                    └─────┬────┘    └───────────┘
                                          │
                                          ▼
                                    ┌──────────┐
                                    │ Orchestr. │
                                    └─────┬────┘
                                          │
                                          ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌─────────┐
│  Code    │◀───│  Worker  │◀───│  Kafka   │    │  Temporal │    │  S3/Reg │
│  Forge   │    │  Agent   │    │ Tickets  │    └───────────┘    └─────────┘
└─────┬────┘    └──────────┘    └──────────┘
      │
      ▼
┌──────────┐
│  Image   │
│ Built    │
└──────────┘
```

---

**Documento versão 1.1** - Atualizado em 2026-03-15

---

## 41. Testes End-to-End

### Estrutura de Testes E2E

```python
# tests/e2e/test_complete_pipeline.py

import pytest
from httpx import AsyncClient
from kafka import KafkaConsumer
import time

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_code_generation_pipeline():
    """
    Teste E2E: Intenção → Código Gerado

    Fluxo completo:
    1. POST intenção no Gateway
    2. Consome do Kafka (STE processa)
    3. Aguarda Consensus
    4. Aguarda tickets criados
    5. Verifica código gerado
    """

    # 1. Enviar intenção
    async with AsyncClient() as client:
        response = await client.post(
            "http://gateway:8000/api/v1/intentions/",
            json={
                "text": "Criar API de usuários com Python e FastAPI",
                "language": "pt-BR",
                "actor": {"id": "test-user", "actor_type": "human"}
            }
        )

        assert response.status_code == 202
        intent_data = response.json()
        intent_id = intent_data["intent_id"]
        correlation_id = intent_data["correlation_id"]

    # 2. Aguardar processamento STE
    consumer = KafkaConsumer(
        "plans.consensus",
        bootstrap_servers="kafka:9092",
        auto_offset_reset="earliest",
        consumer_timeout_ms=30000
    )

    plan_found = False
    for message in consumer:
        if message.value.get("correlation_id") == correlation_id:
            plan_found = True
            break

    assert plan_found, "Plano não encontrado no tópico plans.consensus"

    # 3. Aguardar tickets
    ticket_consumer = KafkaConsumer(
        "execution.tickets",
        bootstrap_servers="kafka:9092",
        consumer_timeout_ms=30000
    )

    tickets_found = []
    for message in ticket_consumer:
        if message.value.get("correlation_id") == correlation_id:
            tickets_found.append(message.value)

    assert len(tickets_found) > 0, "Nenhum ticket criado"

    # 4. Verificar código gerado
    async with AsyncClient() as client:
        # Buscar artefato pelo artifact_id
        artifact_response = await client.get(
            f"http://code-forge:8000/api/v1/artifacts/{tickets_found[0]['artifact_id']}"
        )

        assert artifact_response.status_code == 200
        artifact = artifact_response.json()

        assert "content" in artifact
        assert "image_uri" in artifact

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_approval_flow_high_risk():
    """
    Teste E2E: Fluxo de aprovação para alto risco
    """

    async with AsyncClient() as client:
        # Intenção destrutiva (deve requerer aprovação)
        response = await client.post(
            "http://gateway:8000/api/v1/intentions/",
            json={
                "text": "Deletar todos os dados do banco de produção",
                "language": "pt-BR",
                "actor": {"id": "test-user", "actor_type": "human"}
            }
        )

        assert response.status_code == 202
        intent_id = response.json()["intent_id"]

    # Verificar que foi para aprovação
    approval_consumer = KafkaConsumer(
        "plans.approvals",
        bootstrap_servers="kafka:9092",
        consumer_timeout_ms=10000
    )

    approval_found = False
    for message in approval_consumer:
        if message.value.get("intent_id") == intent_id:
            approval_found = True
            assert message.value.get("requires_approval") == True
            break

    assert approval_found, "Plano de alto risco não enviado para aprovação"

    # Aprovar manualmente
    plan_id = approval_consumer._messages[0].value.get("plan_id")

    async with AsyncClient() as client:
        approve_response = await client.post(
            f"http://approval-service:8004/api/v1/approvals/{plan_id}/approve",
            json={
                "user_id": "admin",
                "comments": "Approved for E2E test"
            }
        )

        assert approve_response.status_code == 200
```

---

## 42. Manifestos Kubernetes Completos

### Deployment do Code Forge

```yaml
# services/code-forge/k8s/deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: code-forge
  namespace: neural-hive
  labels:
    app: code-forge
    version: v1
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: code-forge
  template:
    metadata:
      labels:
        app: code-forge
        version: v1
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: code-forge
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
      - name: code-forge
        image: registry.neural-hive.local/code-forge:1.0.0
        imagePullPolicy: IfNotPresent
        ports:
        - name: http
          containerPort: 8000
          protocol: TCP
        - name: metrics
          containerPort: 9090
          protocol: TCP
        env:
        - name: POD_NAME
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: PYTHONUNBUFFERED
          value: "1"
        - name: MONGODB_URI
          valueFrom:
            configMapKeyRef:
              name: code-forge-config
              key: mongodb_uri
        - name: KAFKA_BOOTSTRAP_SERVERS
          valueFrom:
            configMapKeyRef:
              name: neural-hive-config
              key: kafka_bootstrap_servers
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-secrets
              key: anthropic-api-key
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://jaeger-collector:4317"
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 1000m
            memory: 2Gi
        volumeMounts:
        - name: cache
          mountPath: /app/.cache
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        lifecycle:
          preStop:
            exec:
              command:
              - /bin/sh
              - -c
              - sleep 15
      volumes:
      - name: cache
        emptyDir:
          sizeLimit: 100Mi
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - code-forge
              topologyKey: kubernetes.io/hostname

---
apiVersion: v1
kind: Service
metadata:
  name: code-forge
  namespace: neural-hive
  labels:
    app: code-forge
spec:
  type: ClusterIP
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
    name: http
  - port: 9090
    targetPort: 9090
    protocol: TCP
    name: metrics
  selector:
    app: code-forge

---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: code-forge
  namespace: neural-hive
automountServiceAccountToken: false

---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: code-forge-pdb
  namespace: neural-hive
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: code-forge
```

### ConfigMap

```yaml
# services/code-forge/k8s/configmap.yaml

apiVersion: v1
kind: ConfigMap
metadata:
  name: code-forge-config
  namespace: neural-hive
data:
  mongodb_uri: "mongodb://mongodb:27017"
  mongodb_database: "codeforge"
  kafka_bootstrap_servers: "kafka.neural-hive.svc.cluster.local:9092"
  mcp_catalog_url: "http://mcp-tool-catalog:8080"
  analyst_agents_url: "http://analyst-agents:8080"
  service_registry_url: "service-registry:50051"
  llm_provider: "anthropic"
  llm_temperature: "0.2"
  llm_max_tokens: "8192"
  build_timeout_seconds: "300"
  registry_url: "registry.neural-hive.local"
```

---

## 43. CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/code-forge-ci.yml

name: Code Forge CI/CD

on:
  push:
    branches: [main, develop]
    paths:
      - 'services/code-forge/**'
      - 'libraries/python/**'
  pull_request:
    branches: [main, develop]

env:
  REGISTRY: registry.neural-hive.local
  IMAGE_NAME: code-forge

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install ruff mypy pylint
      - name: Run ruff
        working-directory: services/code-forge
        run: ruff check .
      - name: Run mypy
        working-directory: services/code-forge
        run: mypy src/

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - name: Install dependencies
        working-directory: services/code-forge
        run: |
          pip install -e ".[test]"
      - name: Run unit tests
        working-directory: services/code-forge
        run: |
          pytest tests/unit/ -v --cov=src --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml

  security-scan:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: './services/code-forge'
          format: 'sarif'
          output: 'trivy-results.sarif'
      - name: Upload Trivy results
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: trivy-results.sarif

  build:
    runs-on: ubuntu-latest
    needs: [lint, test, security-scan]
    if: github.event_name == 'push'
    outputs:
      image-tag: ${{ steps.meta.outputs.tags }}
      image-digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.REGISTRY_USERNAME }}
          password: ${{ secrets.REGISTRY_PASSWORD }}
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=sha,prefix={{branch}}-
      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: services/code-forge
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          build-args: |
            BUILD_DATE=${{ github.event.head_commit.timestamp }}
            VCS_REF=${{ github.sha }}

  deploy:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - name: Deploy to Kubernetes
        uses: azure/k8s-deploy@v5
        with:
          manifests: |
            services/code-forge/k8s/deployment.yaml
            services/code-forge/k8s/service.yaml
          images: ${{ needs.build.outputs.image-tag }}
          kubeconfig: ${{ secrets.KUBE_CONFIG }}
```

---

## 44. Monitoring Avançado

### Dashboards Grafana JSON

```json
{
  "dashboard": {
    "title": "Neural Hive-Mind - Pipeline Overview",
    "tags": ["neural-hive", "pipeline"],
    "timezone": "browser",
    "schemaVersion": 16,
    "version": 0,
    "refresh": "10s",
    "panels": [
      {
        "id": 1,
        "title": "Intenções por Domínio",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(neural_hive_gateway_intents_published_total[5m])",
            "legendFormat": "{{domain}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "reqps",
            "min": 0
          }
        }
      },
      {
        "id": 2,
        "title": "Tempo de Geração de Código",
        "type": "heatmap",
        "targets": [
          {
            "expr": "histogram_quantile(0.99, rate(codeforge_generation_duration_seconds_bucket[5m]))",
            "legendFormat": "P99"
          }
        ],
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
      },
      {
        "id": 3,
        "title": "Status do Consensus",
        "type": "stat",
        "targets": [
          {
            "expr": "consensus_aggregated_confidence",
            "legendFormat": "Confiança"
          }
        ],
        "options": {
          "colorMode": "value",
          "graphMode": "area",
          "orientation": "auto"
        }
      },
      {
        "id": 4,
        "title": "Tickets Processados",
        "type": "table",
        "targets": [
          {
            "expr": "worker_tickets_processed_total{status=\"COMPLETED\"}",
            "format": "table",
            "instant": true
          }
        ],
        "transformations": [
          {
            "id": "aggregate",
            "options": {
              "columns": {
                "Value": {
                  "aggregations": ["sum"],
                  "fields": {}
                }
              }
            }
          }
        ]
      },
      {
        "id": 5,
        "title": "Circuit Breakers Status",
        "type": "stat",
        "targets": [
          {
            "expr": "llm_circuit_breaker_open",
            "legendFormat": "LLM"
          },
          {
            "expr": "mongodb_circuit_breaker_open",
            "legendFormat": "MongoDB"
          },
          {
            "expr": "opa_circuit_breaker_open",
            "legendFormat": "OPA"
          }
        ],
        "options": {
          "displayMode": "gradient",
          "maxVizHeight": 300,
          "minVizHeight": 16,
          "minVizWidth": 8,
          "orientation": "horizontal",
          "showUnfilled": true
        }
      },
      {
        "id": 6,
        "title": "Kafka Consumer Lag",
        "type": "gauge",
        "targets": [
          {
            "expr": "kafka_consumer_lag{topic=\"execution.tickets\"}",
            "legendFormat": "Lag"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "short",
            "min": 0,
            "max": 100,
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"value": 0, "color": "green"},
                {"value": 50, "color": "yellow"},
                {"value": 80, "color": "red"}
              ]
            }
          }
        }
      },
      {
        "id": 7,
        "title": "Error Rate por Serviço",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m])",
            "legendFormat": "{{service}}"
          }
        ]
      },
      {
        "id": 8,
        "title": "Memory Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "container_memory_working_set_bytes{namespace=\"neural-hive\"}",
            "legendFormat": "{{pod}}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "bytes"
          }
        }
      }
    ]
  }
}
```

---

## 45. Runbooks Operacionais Detalhados

### Runbook: Pods em CrashLoopBackOff

```bash
#!/bin/bash
# runbooks/pods-crashloop-backoff.sh

echo "=== Troubleshooting CrashLoopBackOff Pods ==="

# 1. Identificar pods com problema
echo "Step 1: Identifying pods..."
pods=$(kubectl get pods -A | grep CrashLoopBackOff | awk '{print $1 "@" $2}')

if [ -z "$pods" ]; then
    echo "No pods in CrashLoopBackOff found."
    exit 0
fi

for pod in $pods; do
    IFS='@' read -r pod_name namespace <<< "$pod"

    echo "========================================="
    echo "Pod: $pod_name in namespace: $namespace"
    echo "========================================="

    # 2. Verificar logs anteriores
    echo "Step 2: Previous logs..."
    kubectl logs -n "$namespace" "$pod_name" --previous --tail=50

    # 3. Verificar logs atuais
    echo "Step 3: Current logs..."
    kubectl logs -n "$namespace" "$pod_name" --tail=50

    # 4. Descrever pod para debug
    echo "Step 4: Pod description..."
    kubectl describe pod -n "$namespace" "$pod_name"

    # 5. Verificar eventos recentes do namespace
    echo "Step 5: Recent events in namespace..."
    kubectl get events -n "$namespace" --sort-by='.lastTimestamp' | tail -10

    # 6. Soluções comuns

    # Caso 1: OOMKilled
    if kubectl logs -n "$namespace" "$pod_name" --previous | grep -q "OOMKilled"; then
        echo "DIAGNOSIS: Out of Memory"
        echo "SOLUTION: Increase memory limits in deployment"
        kubectl set resources deployment "$(kubectl get pod "$pod_name" -o jsonpath='{.metadata.ownerReferences[0].name}')" \
          --limits=memory=2Gi
    fi

    # Caso 2: ImagePullBackOff
    if kubectl describe pod -n "$namespace" "$pod_name" | grep -q "ImagePullBackOff"; then
        echo "DIAGNOSIS: Cannot pull image"
        echo "SOLUTION: Check image name and credentials"
        kubectl describe pod -n "$namespace" "$pod_name" | grep -A 5 "Image:"
    fi

    # Caso 3: Liveness probe failing
    if kubectl describe pod -n "$namespace" "$pod_name" | grep -q "Liveness probe failed"; then
        echo "DIAGNOSIS: Health check failing"
        echo "SOLUTION: Check /health endpoint or increase probe thresholds"
    fi

    # Caso 4: Dependency not ready
    if kubectl logs -n "$namespace" "$pod_name" | grep -q "Connection refused"; then
        echo "DIAGNOSIS: Dependency not ready"
        echo "SOLUTION: Check if required services are up"
    fi

    echo ""
done
```

### Runbook: Alta Latência

```bash
#!/bin/bash
# runbooks/high-latency.sh

echo "=== Troubleshooting High Latency ==="

# 1. Verificar latência P99 dos serviços
echo "Step 1: Checking P99 latency..."
services=("gateway" "ste" "consensus" "orchestrator" "code-forge")

for service in "${services[@]}"; do
    p99=$(curl -s "http://${service}:9090/metrics" | \
      grep "http_request_duration_seconds_bucket{le=\"1\"}" | \
      head -1 | grep -oP '\d+\.\d+(?=$)' || echo "N/A")

    echo "  $service P99: ${p99}s"

    if (( $(echo "$p99 > 1.0" | bc -l) )); then
        echo "    ⚠️  HIGH LATENCY DETECTED"

        # Investigar
        echo "    Investigating $service..."

        # Verificar CPU throttling
        cpu_throttling=$(kubectl exec -n neural-hive \
          "deployment/${service}" -- cat /sys/fs/cgroup/cpu/cpu.stat | \
          grep nr_throttled | awk '{print $2}')

        echo "    CPU Throttled: $cpu_throttling times"

        # Verificar memory pressure
        memory_pressure=$(kubectl exec -n neural-hive \
          "deployment/${service}" -- cat /proc/pressure/memory)

        echo "    Memory Pressure: $memory_pressure"
    fi
done

# 2. Verificar latência de dependências externas
echo "Step 2: Checking external dependencies..."

# MongoDB
echo "  MongoDB latency:"
time kubectl exec -n neural-hive mongodb-0 -- mongosh \
  --eval "db.adminCommand({ping: 1})"

# Kafka
echo "  Kafka latency:"
time kubectl exec -n neural-hive kafka-0 -- \
  kafka-broker-api-versions --bootstrap-server localhost:9092

# Redis
echo "  Redis latency:"
time kubectl exec -n neural-hive redis-0 -- redis-cli ping

# 3. Verificar network policies
echo "Step 3: Checking network policies..."
kubectl get networkpolicies -A

# 4. Verificar DNS resolution
echo "Step 4: Checking DNS..."
kubectl exec -n neural-hive deployment/gateway -- \
  nslookup code-forge.neural-hive.svc.cluster.local
```

---

## 46. Análise de Logs Centralizados

### Configuração Fluentd/Vector

```yaml
# infrastructure/logging/vector.yaml

sources:
  kubernetes_logs:
    type: kubernetes_logs
    namespace: neural-hive

transforms:
  parse_json:
    type: json_parser
    inputs:
      - kubernetes_logs
    field: message
    drop_invalid: true

  add_service_labels:
    type: remap
    inputs:
      - parse_json
    source: |
      .service = .pod_labels["app"] || "unknown"
      .namespace = .pod_namespace
      .trace_id = .traceparent || "unknown"
      .correlation_id = .correlation_id || "unknown"

filters:
  filter_neural_hive:
    type: filter
    inputs:
      - add_service_labels
    condition: .namespace == "neural-hive"

  sample_debug:
    type: sample
    inputs:
      - filter_neural_hive
    rate: 100  # 1% das mensagens em detalhe
    pass_samples: true

sinks:
  loki:
    type: loki
    inputs:
      - filter_neural_hive
    endpoint: http://loki:3100
    encoding:
      codec: json
    batch:
      max_events: 1000
      timeout_secs: 5
    labels:
      service: "{{ service }}"
      namespace: "{{ namespace }}"
      level: "{{ level }}"
    labels_from_key:
      trace_id: trace_id
      correlation_id: correlation_id

  stderr:
    type: console
    inputs:
      - sample_debug
    encoding:
      codec: json
```

---

## 47. Arquitetura de Multi-tenancy

### Isolamento de Tenants

```python
# libraries/python/neural_hive_core/src/multi_tenant.py

class TenantContext:
    """Contexto de tenant para isolação"""

    def __init__(
        self,
        tenant_id: str,
        isolation_level: IsolationLevel = IsolationLevel.LOGICAL
    ):
        self.tenant_id = tenant_id
        self.isolation_level = isolation_level

    def get_database_name(self, base_name: str) -> str:
        """Retorna nome do banco isolado por tenant"""

        if self.isolation_level == IsolationLevel.DEDICATED_DB:
            return f"{self.tenant_id}_{base_name}"
        else:
            return base_name

    def get_kafka_topic(self, base_topic: str) -> str:
        """Retorna tópico Kafka isolado por tenant"""

        if self.isolation_level == IsolationLevel.DEDICATED_TOPICS:
            return f"{self.tenant_id}.{base_topic}"
        else:
            return base_topic

    def get_redis_key_prefix(self) -> str:
        """Retorna prefixo de chave Redis isolado"""

        return f"tenant:{self.tenant_id}:"

class IsolationLevel(Enum):
    """Níveis de isolamento entre tenants"""
    LOGICAL = "logical"           # Separação lógica apenas
    DEDICATED_DB = "dedicated_db"  # Banco dedicado
    DEDICATED_TOPICS = "topics"    # Tópicos Kafka dedicados
    DEDICATED_NAMESPACE = "ns"     # Namespace K8s dedicado
```

---

## 48. Versionamento de APIs

### Estratégia de Versionamento

```python
# services/gateway-intencoes/src/api/versioning.py

from fastapi import FastAPI
from fastapi.responses import Response

app = FastAPI(
    title="Neural Hive-Mind Gateway API",
    version="2.0.0",
    description="API para submissão de intenções de geração de código"
)

@app.get("/api/v1/intentions", tags=["v1"])
async def list_intentions_v1(limit: int = 100):
    """
    Listar intenções (API v1)

    ⚠️ DEPRECATED: Usar /api/v2/intentions
    """
    return await intentions_service.list(limit=limit)

@app.get("/api/v2/intentions", tags=["v2"])
async def list_intentions_v2(
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "created_at",
    order: str = "desc"
):
    """
    Listar intenções (API v2)

    Melhorias:
    - Paginação com offset
    - Ordenação configurável
    - Filtros avançados
    """
    return await intentions_service.list_v2(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        order=order
    )

@app.get("/api/v2/intentions/{intent_id}", tags=["v2"])
async def get_intent_v2(intent_id: str):
    """Obter detalhes de uma intenção (v2)"""
    return await intentions_service.get(intent_id)

# Sunsetting de APIs antigas
@app.get("/api/v1/intentions/{intent_id}", include_in_schema=False)
async def get_intent_v1(intent_id: str):
    """
    Obter intenção (v1)

    ⚠️ DEPRECATED: Usar /api/v2/intentions/{intent_id}
    Esta API será removida em 2026-06-01
    """
    response = await intentions_service.get(intent_id)
    response.headers["X-API-WARNING"] = "Deprecated API, use v2"
    response.headers["Sunset": "2026-06-01"
    return response
```

---

## 49. Rate Limiting Avançado

### Configuração por Tenant

```python
# services/gateway-intencoes/src/rate_limiter/tenant_limiter.py

class TenantRateLimiter:
    """Rate limiting por tenant com Redis"""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        tenant_id: str,
        user_id: Optional[str],
        endpoint: str
    ) -> RateLimitResult:
        """
        Verifica rate limit considerando:
        1. Plano do tenant (free, pro, enterprise)
        2. Usuário específico
        3. Endpoint específico
        """

        # Buscar configuração do tenant
        tenant_config = await self._get_tenant_config(tenant_id)

        # Limites hierárquicos
        limits = [
            # Limite por usuário (mais restritivo)
            await self._check_user_limit(tenant_id, user_id, endpoint, tenant_config),
            # Limite por tenant
            await self._check_tenant_limit(tenant_id, endpoint, tenant_config),
            # Limite global
            await self._check_global_limit(endpoint, tenant_config),
        ]

        # Usar o limite mais restritivo
        min_limit = min(limits, key=lambda x: x.remaining)

        if min_limit.remaining <= 0:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=min_limit.reset_at,
                retry_after=min_limit.retry_after
            )

        return RateLimitResult(
            allowed=True,
            remaining=min_limit.remaining,
            reset_at=min_limit.reset_at,
            retry_after=None
        )

    async def _get_tenant_config(self, tenant_id: str) -> TenantConfig:
        """Busca configuração do tenant com cache"""

        cache_key = f"tenant_config:{tenant_id}"
        cached = await self.redis.get(cache_key)

        if cached:
            return TenantConfig.parse_raw(cached)

        # Buscar do banco
        config = await self.tenant_repo.get(tenant_id)

        # Cache por 5 minutos
        await self.redis.setex(
            cache_key,
            300,
            config.json()
        )

        return config

    async def _check_user_limit(
        self,
        tenant_id: str,
        user_id: str,
        endpoint: str,
        config: TenantConfig
    ) -> LimitInfo:
        """Verifica limite por usuário"""

        key = f"rate_limit:user:{tenant_id}:{user_id}:{endpoint}"

        # Token bucket algorithm
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, 60)  # 1 minuto

        limit = config.user_limits.get(endpoint, 100)

        return LimitInfo(
            remaining=max(0, limit - current),
            reset_at=int(time.time()) + 60,
            retry_after=60
        )
```

---

## 50. Arquitetura de Plugin/Extension

### Sistema de Plugins

```python
# libraries/python/neural_hive_plugins/src/plugin_manager.py

class PluginManager:
    """Gerenciador de plugins para extensibilidade"""

    def __init__(self):
        self.plugins: Dict[str, BasePlugin] = {}
        self.hooks: Dict[str, List[Callable]] = defaultdict(list)

    def register_plugin(self, plugin: BasePlugin):
        """Registra um plugin"""

        plugin_name = plugin.metadata.name
        version = plugin.metadata.version

        # Verificar compatibilidade
        if not self._is_compatible(plugin):
            raise PluginIncompatibleException(
                f"Plugin {plugin_name} v{version} is not compatible"
            )

        # Carregar plugin
        plugin.initialize()

        # Registrar hooks
        for hook in plugin.get_hooks():
            self.hooks[hook.name].append(hook)

        self.plugins[plugin_name] = plugin

        logger.info(
            "plugin_registered",
            plugin=plugin_name,
            version=version
        )

    async def execute_hook(
        self,
        hook_name: str,
        context: PluginContext
    ) -> PluginResult:
        """Executa todos os hooks registrados para um evento"""

        hooks = self.hooks.get(hook_name, [])

        results = []
        for hook in hooks:
            try:
                result = await hook.execute(context)
                results.append(result)

                # Se um hook falhar e não for continue-on-error, parar
                if not result.success and not hook.metadata.continue_on_error:
                    break

            except Exception as e:
                logger.error(
                    "hook_execution_failed",
                    hook=hook_name,
                    plugin=hook.metadata.plugin_name,
                    error=str(e)
                )

                if not hook.metadata.continue_on_error:
                    raise

        return PluginResult(
            success=all(r.success for r in results),
            results=results
        )

# Exemplo de plugin customizado
class CustomCodeValidatorPlugin(BasePlugin):
    """Plugin customizado para validação de código"""

    metadata = PluginMetadata(
        name="custom-code-validator",
        version="1.0.0",
        author="Company XYZ",
        description="Valida código contra regras específicas da empresa"
    )

    def get_hooks(self) -> List[Hook]:
        return [
            Hook(
                name="code_generation.post",
                handler=self.validate_generated_code
            ),
            Hook(
                name="code_generation.pre",
                handler=self.inject_company_headers
            )
        ]

    async def validate_generated_code(self, context: PluginContext) -> PluginResult:
        """Valida código gerado contra regras da empresa"""

        code_content = context.artifact.content

        # Verificar headers obrigatórios
        required_headers = [
            "Copyright Company XYZ",
            "Confidential"
        ]

        for header in required_headers:
            if header not in code_content:
                return PluginResult(
                    success=False,
                    message=f"Missing required header: {header}"
                )

        # Verificar padrões de命名
        if re.search(r'\bTODO\b', code_content):
            return PluginResult(
                success=False,
                message="TODO comments not allowed in production code"
            )

        return PluginResult(success=True)
```

---

**Documento versão 1.2** - Atualizado em 2026-03-15

---

## 51. Caching Strategies

### Multi-Layer Cache

```python
# libraries/python/neural_hive_cache/src/strategies.py

class CacheStrategy(ABC):
    """Estratégia base de cache"""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int):
        pass

class MultiLevelCache:
    """Cache com múltiplos níveis (L1, L2, L3)"""

    def __init__(self):
        # L1: Memória local (pod)
        self.l1_cache = {}
        self.l1_max_size = 1000

        # L2: Redis (cluster)
        self.l2_client = RedisClient()

        # L3: MongoDB (persistente)
        self.l3_client = MongoDBClient()

    async def get(self, key: str) -> Optional[Any]:
        """
        Busca em ordem: L1 → L2 → L3
        Atualiza níveis superiores quando encontra
        """

        # L1: Memória local
        if key in self.l1_cache:
            return self.l1_cache[key]

        # L2: Redis
        l2_value = await self.l2_client.get(key)
        if l2_value:
            # Promote para L1
            self._l1_set(key, l2_value)
            return l2_value

        # L3: MongoDB
        l3_value = await self.l3_client.get_cache(key)
        if l3_value:
            # Promote para L2 e L1
            await self.l2_client.setex(key, 3600, l3_value)
            self._l1_set(key, l3_value)
            return l3_value

        return None

    async def set(self, key: str, value: Any, ttl: int):
        """Escreve em todos os níveis"""

        # L1
        self._l1_set(key, value)

        # L2
        await self.l2_client.setex(key, ttl, value)

        # L3 (se TTL longo)
        if ttl > 3600:  # Mais de 1 hora
            await self.l3_client.set_cache(key, value, ttl)

    def _l1_set(self, key: str, value: Any):
        """Set com LRU eviction no L1"""
        if len(self.l1_cache) >= self.l1_max_size:
            # Remove item mais antigo (simplificado)
            oldest = next(iter(self.l1_cache))
            del self.l1_cache[oldest]
        self.l1_cache[key] = value
```

---

## 52. Message Transformation

### Kafka Streams

```python
# services/orchestrator-dynamic/src/kafka/streams.py

class KafkaStreamProcessor:
    """Processamento de streams Kafka"""

    def __init__(self):
        self.consumer = AIOKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="orchestrator-streams",
            auto_offset_reset="earliest"
        )

        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers
        )

    async def process_ticket_stream(self):
        """
        Processa stream de tickets para agregação

        Input: execution.tickets
        Output: tickets.aggregated
        """

        await self.consumer.subscribe(["execution.tickets"])

        async for msg in self.consumer:
            ticket = json.loads(msg.value)

            # Agregar por plan_id
            window_key = f"plan:{ticket['plan_id']}:window:{time.time() // 60}"

            # Agregar métricas
            await self.producer.send_and_wait(
                topic="tickets.aggregated",
                key=window_key.encode(),
                value=json.dumps({
                    "plan_id": ticket["plan_id"],
                    "timestamp": int(time.time()),
                    "tickets_count": 1,
                    "total_duration_ms": ticket.get("duration_ms", 0),
                    "success": 1 if ticket.get("status") == "COMPLETED" else 0
                }).encode()
            )
```

---

## 53. Database Sharding Strategy

### Shard Key Selection

```python
# services/execution-ticket-service/src/sharding.py

class ShardSelector:
    """Seleciona shard baseado em tenant_id"""

    def __init__(self, num_shards: int = 4):
        self.num_shards = num_shards

    def get_shard(self, tenant_id: str) -> int:
        """
        Seleciona shard usando hash consistente

        Shard: ticket_shard_0, ticket_shard_1, ...
        """

        shard_hash = hashlib.md5(tenant_id.encode()).hexdigest()
        shard_num = int(shard_hash, 16) % self.num_shards

        return shard_num

    def get_collection_name(self, tenant_id: str) -> str:
        """Retorna nome da coleção baseado no shard"""

        shard = self.get_shard(tenant_id)
        return f"ticket_shard_{shard}"

    async def query_across_shards(
        self,
        query: Dict,
        projection: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Executa query distribuída across shards
        """

        tasks = []
        for shard in range(self.num_shards):
            collection_name = f"ticket_shard_{shard}"
            tasks.append(self._query_shard(collection_name, query, projection))

        results = await asyncio.gather(*tasks)

        # Merge e ordenar
        merged = []
        for result in results:
            merged.extend(result)

        return merged
```

---

## 54. Distributed Locking

### Redis Distributed Lock

```python
# libraries/python/neural_hive_locks/src/redis_lock.py

class DistributedLock:
    """Lock distribuído com Redis"""

    def __init__(self, redis_client: Redis, lock_key: str, ttl: int = 30):
        self.redis = redis_client
        self.lock_key = f"lock:{lock_key}"
        self.ttl = ttl
        self.identifier = str(uuid.uuid4())

    async def __aenter__(self):
        """Adquire lock"""

        while True:
            # Try to acquire lock
            acquired = await self.redis.set(
                self.lock_key,
                self.identifier,
                nx=True,
                ex=self.ttl
            )

            if acquired:
                return self

            # Wait and retry
            await asyncio.sleep(0.1)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock"""

        # Only release if still owner
        current_value = await self.redis.get(self.lock_key)

        if current_value == self.identifier:
            await self.redis.delete(self.lock_key)

# Uso
async def process_with_lock(plan_id: str):
    """Processa plano com lock distribuído"""

    async with DistributedLock(redis, f"plan:{plan_id}"):
        # Apenas um worker processará este plano
        await execute_plan_workflow(plan_id)
```

---

## 55. Feature Flags

### Dynamic Configuration

```python
# services/semantic-translation-engine/src/feature_flags.py

class FeatureFlags:
    """Gerenciador de feature flags"""

    def __init__(self):
        self.flags = {}
        self.redis_client = RedisClient()

    async def load_flags(self):
        """Carrega flags do Redis"""

        flag_data = await self.redis_client.get("feature_flags")

        if flag_data:
            self.flags = json.loads(flag_data)
        else:
            # Defaults
            self.flags = {
                "enable_llm_generation": True,
                "enable_rag_context": True,
                "enable_approval_workflow": True,
                "experimental_multi_language": False,
                "max_concurrent_plans": 100,
                "enable_saga_compensation": True,
            }

    def is_enabled(self, flag_name: str) -> bool:
        """Verifica se flag está habilitada"""

        return self.flags.get(flag_name, False)

    def get_config(self, key: str, default=None):
        """Obtém valor de configuração"""

        return self.flags.get(key, default)

# Middleware FastAPI
@app.middleware("http")
async def feature_flag_middleware(request: Request, call_next):
    """Middleware para validar feature flags"""

    feature_flags = request.app.state.feature_flags

    # Exemplo: desabilitar experimental features anonimamente
    if "X-Experimental" in request.headers:
        if not feature_flags.is_enabled("experimental_multi_language"):
            return JSONResponse(
                status_code=503,
                content={"error": "Experimental features disabled"}
            )

    return await call_next(request)
```

---

## 56. A/B Testing Framework

### Experiment Configuration

```python
# libraries/python/neural_hive_experiments/src/ab_testing.py

class Experiment:
    """Configuração de experimento A/B"""

    def __init__(
        self,
        name: str,
        description: str,
        variants: List[Variant],
        traffic_split: Dict[str, float]
    ):
        self.name = name
        self.description = description
        self.variants = variants
        self.traffic_split = traffic_split  # {"A": 0.5, "B": 0.5}

class ABTestingManager:
    """Gerenciador de experimentos A/B"""

    async def assign_variant(
        self,
        experiment_name: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> str:
        """
        Atribui variante do experimento

        Usa consistent hashing para mesmo usuário sempre na mesma variante
        """

        experiment = await self.get_experiment(experiment_name)

        # Se user_id fornecido, usa para hash consistente
        if user_id:
            hash_input = f"{experiment_name}:{user_id}"
        else:
            hash_input = f"{experiment_name}:{tenant_id}"

        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        hash_float = hash_value / 2**32  # Normalizar para 0-1

        # Determinar variante baseado em traffic_split
        cumulative = 0.0
        for variant, split in experiment.traffic_split.items():
            cumulative += split
            if hash_float <= cumulative:
                return variant

        return list(experiment.traffic_split.keys())[0]  # Fallback

# Exemplo de uso
class LLMPromptExperiment(Experiment):
    """Experimento para testar diferentes prompts LLM"""

    name = "llm_prompt_v2"
    description = "Testa novo prompt template vs atual"

    variants = [
        Variant(name="control", prompt_template="CURRENT_PROMPT_V1"),
        Variant(name="treatment", prompt_template="ENHANCED_PROMPT_V2")
    ]

    traffic_split = {"control": 0.8, "treatment": 0.2}
```

---

## 57. Health Checks Avançados

### Deep Health Probes

```python
# services/code-forge/src/health/probes.py

from fastapi import HTTPException
from pydantic import BaseModel

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

class ComponentHealth(BaseModel):
    name: str
    status: HealthStatus
    message: Optional[str] = None
    response_time_ms: Optional[float] = None

class HealthReport(BaseModel):
    status: HealthStatus
    version: str
    uptime_seconds: float
    components: List[ComponentHealth]
    metrics: Dict[str, Any]

class HealthChecker:
    """Health checker avançado"""

    def __init__(self):
        self.start_time = time.time()
        self.checks = {
            "mongodb": self._check_mongodb,
            "redis": self._check_redis,
            "kafka": self._check_kafka,
            "llm": self._check_llm,
            "mcp_catalog": self._check_mcp_catalog,
        }

    async def get_health(self) -> HealthReport:
        """Executa todos os health checks"""

        components = []
        overall_status = HealthStatus.HEALTHY

        for name, check_func in self.checks.items():
            try:
                start = time.time()
                result = await check_func()
                duration = (time.time() - start) * 1000

                component = ComponentHealth(
                    name=name,
                    status=result["status"],
                    message=result.get("message"),
                    response_time_ms=duration
                )

                components.append(component)

                if result["status"] != HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED

            except Exception as e:
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e)
                ))
                overall_status = HealthStatus.UNHEALTHY

        return HealthReport(
            status=overall_status,
            version=settings.version,
            uptime_seconds=time.time() - self.start_time,
            components=components,
            metrics={
                "total_components": len(self.checks),
                "healthy_components": sum(
                    1 for c in components if c.status == HealthStatus.HEALTHY
                ),
                "degraded_components": sum(
                    1 for c in components if c.status == HealthStatus.DEGRADED
                ),
                "unhealthy_components": sum(
                    1 for c in components if c.status == HealthStatus.UNHEALTHY
                ),
            }
        )

    async def _check_mongodb(self) -> Dict:
        """Health check MongoDB"""
        try:
            await self.mongodb.client.admin.command('ping')
            return {"status": HealthStatus.HEALTHY}
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": str(e)
            }

    async def _check_kafka(self) -> Dict:
        """Health check Kafka"""
        try:
            metadata = await self.kafka.consumer.manager.cluster_metadata()
            brokers = metadata.brokers()

            if not brokers:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "message": "No brokers available"
                }

            return {
                "status": HealthStatus.HEALTHY,
                "message": f"{len(brokers)} brokers"
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": str(e)
            }
```

---

## 58. Backup e Restore

### Backup Strategy

```bash
#!/bin/bash
# infrastructure/backup/backup-all.sh

echo "=== Neural Hive-Mind Backup ==="
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/nhm/$BACKUP_DATE"
mkdir -p "$BACKUP_DIR"

# 1. MongoDB Backup
echo "Backing up MongoDB..."
kubectl exec -n neural-hive mongodb-0 -- \
  mongodump --archive=/backup/mongodb-$BACKUP_DATE.gz \
  --gzip

kubectl cp neural-hive/mongodb-0:/backup/mongodb-$BACKUP_DATE.gz \
  "$BACKUP_DIR/mongodb.gz"

# 2. Redis Backup
echo "Backing up Redis..."
kubectl exec -n neural-hive redis-0 -- \
  redis-cli --rdb /backup/redis-$BACKUP_DATE.rdb SAVE

kubectl cp neural-hive/redis-0:/data/dump.rdb \
  "$BACKUP_DIR/redis.rdb"

# 3. Kafka Topics Backup
echo "Backing up Kafka topics..."
kubectl exec -n neural-hive kafka-0 -- \
  kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic plans.consensus \
  --from-beginning \
  --max-messages 10000 \
  > "$BACKUP_DIR/plans.consensus.json" &
KAFKA_PID=$!

wait $KAFKA_PID

# 4. S3 Upload (backup off-site)
echo "Uploading to S3..."
aws s3 sync "$BACKUP_DIR" s3://nhm-backups/$BACKUP_DATE/

# 5. Cleanup old backups (keep last 7 days)
find /backups/nhm -type d -mtime +7 -exec rm -rf {} +

echo "Backup completed: $BACKUP_DIR"
echo "S3 location: s3://nhm-backups/$BACKUP_DATE/"
```

---

## 59. Disaster Recovery

### Recovery Procedures

```bash
#!/bin/bash
# infrastructure/disaster-recovery/recover-from-s3.sh

BACKUP_DATE=$1  # Formato: YYYYMMDD_HHMMSS
RECOVERY_DIR="/recovery/$BACKUP_DATE"

if [ -z "$BACKUP_DATE" ]; then
    echo "Usage: $0 <BACKUP_DATE>"
    echo "Example: $0 20260315_143000"
    exit 1
fi

echo "=== Neural Hive-Mind Disaster Recovery ==="
echo "Recovering from backup: $BACKUP_DATE"

# 1. Download backup from S3
echo "Step 1: Downloading from S3..."
aws s3 sync s3://nhm-backups/$BACKUP_DATE/ "$RECOVERY_DIR/"

# 2. Restore MongoDB
echo "Step 2: Restoring MongoDB..."
kubectl cp "$RECOVERY_DIR/mongodb.gz" \
  neural-hive/mongodb-0:/backup/mongodb-recovery.gz

kubectl exec -n neural-hive mongodb-0 -- \
  mongorestore --archive=/backup/mongodb-recovery.gz \
  --gzip --drop

# 3. Restore Redis
echo "Step 3: Restoring Redis..."
kubectl cp "$RECOVERY_DIR/redis.rdb" \
  neural-hive/redis-0:/data/dump.rdb

kubectl exec -n neural-hive redis-0 -- \
  redis-cli SHUTDOWN NOSAVE

kubectl exec -n neural-hive redis-0 -- \
  redis-cli --rdb /data/dump.rdb

# 4. Verify restoration
echo "Step 4: Verifying restoration..."

# Verificar MongoDB
mongodb_count=$(kubectl exec -n neural-hive mongodb-0 -- \
  mongosh neural_hive --eval "db.intent_envelope.countDocuments()")

echo "MongoDB documents: $mongodb_count"

# Verificar serviços
kubectl rollout status deployment/gateway-intencoes -n neural-hive
kubectl rollout status deployment/semantic-translation-engine -n neural-hive
kubectl rollout status deployment/code-forge -n neural-hive

echo "=== Recovery Complete ==="
```

---

## 60. Security Auditing

### Audit Trail Implementation

```python
# services/audit-service/src/audit/logger.py

class AuditLogger:
    """Logger de auditoria para compliance"""

    def __init__(self):
        self.elasticsearch_client = ElasticsearchClient()
        self.s3_client = S3Client()

    async def log_event(
        self,
        event_type: AuditEventType,
        actor: Actor,
        resource: str,
        action: str,
        result: str,
        metadata: Optional[Dict] = None
    ):
        """
        Registra evento de auditoria

        Armazena em:
        1. Elasticsearch (busca em tempo real)
        2. S3 (arquivamento longo prazo)
        """

        audit_event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            actor_id=actor.id,
            actor_type=actor.actor_type,
            resource=resource,
            action=action,
            result=result,  # SUCCESS, FAILURE, PARTIAL
            metadata=metadata or {},
            trace_id=metadata.get("trace_id") if metadata else None,
            correlation_id=metadata.get("correlation_id") if metadata else None,
        )

        # Elasticsearch (busca)
        await self.elasticsearch_client.index(
            index=f"audit-{datetime.utcnow().strftime('%Y-%m')}",
            document=audit_event.dict()
        )

        # S3 (arquivo)
        await self._archive_to_s3(audit_event)

    async def _archive_to_s3(self, event: AuditEvent):
        """Arquiva evento no S3 para retenção longa"""

        date_prefix = event.timestamp.strftime("%Y/%m/%d")
        key = f"audit-logs/{date_prefix}/{event.event_type.value}/{event.id}.json"

        await self.s3_client.put_object(
            Bucket="nhm-audit-logs",
            Key=key,
            Body=json.dumps(event.dict(), default=str),
            ContentType="application/json"
        )

# Eventos de auditoria
class AuditEventType(Enum):
    INTENTION_SUBMITTED = "intention_submitted"
    INTENTION_PROCESSED = "intention_processed"
    CODE_GENERATED = "code_generated"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    PLAN_EXECUTED = "plan_executed"
    PLAN_FAILED = "plan_failed"
    SECURITY_VIOLATION = "security_violation"
    DATA_ACCESSED = "data_accessed"
```

---

**Documento versão 1.3** - Atualizado em 2026-03-15

---

## 61. Performance Profiling

### Profile Hotspots

```python
# services/code-forge/src/profiling/profiler.py

import cProfile
import pstats
import io
from contextlib import asynccontextmanager

class CodeForgeProfiler:
    """Profiler para identificar gargalos"""

    @asynccontextmanager
    async def profile_generation(self, ticket_id: str):
        """Context manager para profiling de geração"""

        profiler = cProfile.Profile()
        profiler.enable()

        try:
            yield
        finally:
            profiler.disable()

            # Salvar stats
            stats = pstats.Stats(profiler)

            # Ordenar por tempo total
            stats.sort_stats('cumulative')

            # Output
            output = io.StringIO()
            stats.print_stats(20)  # Top 20 funções
            profile_output = output.getvalue()

            logger.info(
                "code_generation_profile",
                ticket_id=ticket_id,
                profile=profile_output
            )

            # Salvar arquivo de profile
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/profile_{ticket_id}_{timestamp}.prof"

            profiler.dump_stats(filename)

            # Upload para análise posterior
            await self._upload_profile(filename)

    async def _upload_profile(self, filename: str):
        """Upload profile para S3"""
        import boto3

        s3 = boto3.client('s3')

        s3.upload_file(
            Filename=filename,
            Bucket="nhm-profiles",
            Key=f"code-forge/{os.path.basename(filename)}"
        )
```

---

## 62. Database Migration System

### Migration Framework

```python
# libraries/python/neural_hive_migrations/src/migrator.py

class Migration:
    """Representa uma migration"""

    def __init__(
        self,
        version: int,
        name: str,
        up_fn: Callable,
        down_fn: Optional[Callable] = None
    ):
        self.version = version
        self.name = name
        self.up_fn = up_fn
        self.down_fn = down_fn

class DatabaseMigrator:
    """Executa migrations no MongoDB"""

    def __init__(self, mongodb_client):
        self.mongodb = mongodb_client
        self.migrations_collection = self.mongodb.neural_hive.migrations

    async def migrate_up(self, target_version: Optional[int] = None):
        """Executa migrations até versão alvo"""

        # Buscar versão atual
        current = await self._get_current_version()

        # Buscar migrations pendentes
        pending = await self._get_pending_migrations(current, target_version)

        for migration in pending:
            logger.info(
                "running_migration",
                version=migration.version,
                name=migration.name
            )

            # Executar migration
            async with self.mongodb.start_session() as session:
                await self.mongodb.client.admin.command(
                    {'configureFailPoint': f'migration_{migration.version}'}
                )

                await migration.up_fn(self.mongodb)

                # Registrar migration
                await self.migrations_collection.insert_one({
                    'version': migration.version,
                    'name': migration.name,
                    'executed_at': datetime.utcnow(),
                    'duration_ms': 0
                })

            logger.info(
                "migration_completed",
                version=migration.version
            )

    async def migrate_down(self, target_version: int):
        """Rollback para versão alvo"""

        current = await self._get_current_version()

        migrations_to_revert = await self._get_migrations_to_revert(
            current,
            target_version
        )

        for migration in reversed(migrations_to_revert):
            if migration.down_fn:
                logger.info(
                    "reverting_migration",
                    version=migration.version
                )

                await migration.down_fn(self.mongodb)

                # Remover registro
                await self.migrations_collection.delete_one({
                    'version': migration.version
                })

# Exemplo de migration
async def migration_001_add_artifacts_collection(mongodb):
    """Migration 001: Criar coleção de artefatos"""

    await mongodb.neural_hive.artifacts.create_indexes([
        {"keys": [("artifact_id", 1)], "unique": True},
        {"keys": [("plan_id", 1), ("created_at", -1)]},
        {"keys": [("status", 1)]},
    ])

async def migration_001_down(mongodb):
    """Rollback migration 001"""

    await mongodb.neural_hive.artifacts.drop()
```

---

## 63. API Documentation Generation

### OpenAPI/Swagger

```python
# services/gateway-intencoes/src/api/docs.py

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

def custom_openapi(app: FastAPI):
    """Gera documentação OpenAPI customizada"""

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = {
        "openapi": "3.1.0",
        "info": {
            "title": "Neural Hive-Mind Gateway API",
            "version": "2.0.0",
            "description": """
API para submissão de intenções de geração de código.

## Fluxo Principal

1. Submeter intenção via POST /api/v2/intentions
2. Receber confirmation com correlation_id
3. Consultar status via GET /api/v2/intentions/{intent_id}

## Domínios Suportados

- `BUSINESS`: Intenções de negócio
- `TECHNICAL`: Intenções técnicas
- `SECURITY`: Intenções de segurança

## Autenticação

Todas as requisições requerem token JWT válido no header:
```
Authorization: Bearer <token>
```

## Rate Limiting

- Plano Free: 100 requisições/hora
- Plano Pro: 1000 requisições/hora
- Plano Enterprise: ilimitado
            """,
            "contact": {
                "name": "Neural Hive-Mind Team",
                "email": "support@neural-hive.com",
                "url": "https://neural-hive.com/support"
            },
            "license": {
                "name": "Proprietary",
                "url": "https://neural-hive.com/license"
            }
        },
        "servers": [
            {
                "url": "https://api.neural-hive.com",
                "description": "Production",
                "variables": {
                    "env": {
                        "default": "prod",
                        "enum": ["prod", "staging", "dev"]
                    }
                }
            }
        ],
        "paths": {},
        "components": {
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "details": {"type": "object"}
                    },
                    "required": ["code", "message"]
                }
            },
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
        },
        "security": [{"BearerAuth": []}]
    }

    return openapi_schema
```

---

## 64. GraphQL Gateway

### Schema e Resolvers

```python
# services/gateway-intencoes/src/graphql/schema.py

from strawberry import Schema, type, field
from typing import List, Optional

@type
class Intent:
    id: str
    text: str
    domain: str
    confidence: float
    status: str
    created_at: datetime

@type
class IntentResponse:
    success: bool
    intent: Optional[Intent]
    error: Optional[str]

@type
class Query:
    @field
    async def get_intent(self, intent_id: str) -> IntentResponse:
        """Busca intenção por ID"""
        intent = await intentions_service.get(intent_id)

        if not intent:
            return IntentResponse(
                success=False,
                error=f"Intent {intent_id} not found"
            )

        return IntentResponse(success=True, intent=intent)

    @field
    async def list_intents(
        self,
        limit: int = 100,
        status: Optional[str] = None
    ) -> List[Intent]:
        """Lista intenções com filtros"""
        return await intentions_service.list(limit=limit, status=status)

@type
class Mutation:
    @field
    async def submit_intent(
        self,
        text: str,
        language: str = "pt-BR",
        actor_id: str = "anonymous"
    ) -> IntentResponse:
        """Submete nova intenção"""
        envelope = IntentEnvelope(
            text=text,
            language=language,
            actor=Actor(id=actor_id, actor_type=ActorType.HUMAN)
        )

        result = await intentions_service.submit(envelope)

        if result.success:
            return IntentResponse(success=True, intent=result.intent)
        else:
            return IntentResponse(
                success=False,
                error=result.error
            )

schema = Schema(query=Query, mutation=Mutation)
```

---

## 65. WebSocket Support

### Real-time Updates

```python
# services/gateway-intencoes/src/websocket/handler.py

from fastapi import WebSocket
from typing import Dict

class ConnectionManager:
    """Gerenciador de conexões WebSocket"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, connection_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[connection_id] = websocket

    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

    async def broadcast(self, message: dict, exclude: Optional[str] = None):
        """Envia mensagem para todas as conexões (exceto uma)"""

        for conn_id, connection in self.active_connections.items():
            if exclude and conn_id == exclude:
                continue

            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("websocket_send_error", conn_id=conn_id, error=str(e))

manager = ConnectionManager()

@app.websocket("/ws/intentions/{intent_id}")
async def websocket_intent_updates(
    websocket: WebSocket,
    intent_id: str
):
    """
    WebSocket para updates em tempo real de uma intenção

    Eventos enviados:
    - status_changed: Status da intenção mudou
    - plan_created: Cognitive plan criado
    - code_generated: Código foi gerado
    - completed: Processamento concluído
    """

    await manager.connect(intent_id, websocket)

    try:
        while True:
            # Keep-alive ping
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(intent_id)
```

---

## 66. Batch Processing

### Async Batch Jobs

```python
# services/batch-processor/src/jobs/batch_approval.py

class BatchApprovalJob:
    """Job para aprovar múltiplas intenções em lote"""

    def __init__(self):
        self.approval_service = ApprovalService()
        self.mongodb_client = MongoDBClient()

    async def run(
        self,
        batch_name: str,
        filter_query: Dict,
        approver_id: str
    ) -> BatchApprovalResult:
        """
        Executa aprovação em lote

        Args:
            batch_name: Nome do batch
            filter_query: Filtro para intenções
            approver_id: ID do aprovador

        Returns:
            Resultado do batch (approved, rejected, failed counts)
        """

        # Buscar intenções pendentes
        pending = await self.mongodb_client.neural_hive.approval_requests.find(
            {
                "status": "PENDING",
                **filter_query
            }
        ).to_list(length=1000)

        results = {
            "approved": 0,
            "rejected": 0,
            "failed": 0
        }

        for approval_request in pending:
            try:
                # Lógica de aprovação automática
                should_approve = await self._evaluate_batch_rules(
                    approval_request
                )

                if should_approve:
                    await self.approval_service.approve(
                        approval_request["plan_id"],
                        approver_id,
                        comments=f"Auto-approved via batch {batch_name}"
                    )
                    results["approved"] += 1
                else:
                    await self.approval_service.reject(
                        approval_request["plan_id"],
                        approver_id,
                        comments=f"Auto-rejected via batch {batch_name}"
                    )
                    results["rejected"] += 1

            except Exception as e:
                logger.error(
                    "batch_approval_failed",
                    plan_id=approval_request["plan_id"],
                    error=str(e)
                )
                results["failed"] += 1

        return BatchApprovalResult(
            batch_name=batch_name,
            total=len(pending),
            **results
        )

    async def _evaluate_batch_rules(
        self,
        approval_request: Dict
    ) -> bool:
        """Regras para aprovação em lote"""

        # Regra 1: Risco baixo
        if approval_request.get("risk_score", 1.0) < 0.3:
            return True

        # Regra 2: Tenant confiável
        tenant_id = approval_request.get("tenant_id")
        if await self._is_trusted_tenant(tenant_id):
            return True

        # Regra 3: Mesmo approver aprovou antes
        plan_id = approval_request.get("plan_id")
        similar_approved = await self._count_similar_approved(
            plan_id,
            tenant_id
        )

        if similar_approved >= 5:
            return True

        return False
```

---

## 67. Message Transformation Pipelines

### Event Sourcing Events

```python
# libraries/python/neural_hive_events/src/events.py

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict
import json

@dataclass
class DomainEvent:
    """Evento de domínio base"""

    event_type: str
    aggregate_id: str
    aggregate_type: str
    event_id: str
    occurred_at: datetime
    payload: Dict[str, Any]
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict:
        """Converte para dicionário"""
        return {
            "event_type": self.event_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": self.payload,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id
        }

# Eventos específicos
@dataclass
class IntentSubmittedEvent(DomainEvent):
    """Intenção submetida"""

    pass

@dataclass
class CognitivePlanCreatedEvent(DomainEvent):
    """Plano cognitivo criado"""

    pass

@dataclass
class CodeGenerationCompletedEvent(DomainEvent):
    """Geração de código completada"""

    pass

# Event Store
class EventStore:
    """Armazém de eventos (Event Sourcing)"""

    def __init__(self, mongodb_client):
        self.mongodb = mongodb_client
        self.events_collection = mongodb_client.neural_hive.events

    async def append(
        self,
        event: DomainEvent
    ) -> None:
        """Adiciona evento ao store"""

        await self.events_collection.insert_one(event.to_dict())

    async def get_events(
        self,
        aggregate_id: str,
        from_version: Optional[int] = None
    ) -> List[DomainEvent]:
        """Recupera eventos de um aggregate"""

        query = {"aggregate_id": aggregate_id}

        if from_version:
            query["version"] = {"$gte": from_version}

        cursor = self.events_collection.find(query).sort("occurred_at", 1)

        events = []
        async for doc in cursor:
            events.append(self._deserialize_event(doc))

        return events

    def _deserialize_event(self, data: Dict) -> DomainEvent:
        """Desserializa evento do banco"""

        event_class = self._get_event_class(data["event_type"])
        return event_class(**data["payload"])
```

---

## 68. Command Query Responsibility Segregation (CQRS)

### Implementation

```python
# libraries/python/neural_hive_cqrs/src/cqrs.py

class Command:
    """Comando para escrita"""
    pass

class Query:
    """Query para leitura"""
    pass

class CommandBus:
    """Bus de comandos (escrita)"""

    def __init__(self):
        self.handlers: Dict[type, Callable] = {}

    def register(
        self,
        command_type: type[Command],
        handler: Callable
    ) -> None:
        """Registra handler de comando"""
        self.handlers[command_type] = handler

    async def execute(self, command: Command) -> Any:
        """Executa comando"""

        handler = self.handlers.get(type(command))

        if not handler:
            raise NoHandlerRegistered(type(command))

        return await handler(command)

class QueryBus:
    """Bus de queries (leitura)"""

    def __init__(self):
        self.handlers: Dict[type, Callable] = {}

    def register(
        self,
        query_type: type[Query],
        handler: Callable
    ) -> None:
        """Registra handler de query"""
        self.handlers[query_type] = handler

    async def execute(self, query: Query) -> Any:
        """Executa query"""

        handler = self.handlers.get(type(query))

        if not handler:
            raise NoHandlerRegistered(type(query))

        return await handler(query)

# Exemplos de comandos e queries
class SubmitIntentCommand(Command):
    def __init__(self, text: str, actor: Actor):
        self.text = text
        self.actor = actor

class GetIntentStatusQuery(Query):
    def __init__(self, intent_id: str):
        self.intent_id = intent_id
```

---

## 69. Saga Orchestrator Pattern

### Choreography-Based Saga

```python
# services/saga-orchestrator/src/saga.py

class SagaOrchestrator:
    """Orquestrador de Saga (Choreography)"""

    def __init__(self):
        self.saga_log = MongoDBClient().neural_hive.saga_log
        self.kafka_producer = AIOKafkaProducer()

    async def execute_saga(
        self,
        saga_id: str,
        saga_definition: SagaDefinition
    ) -> SagaResult:
        """
        Executa saga (transação distribuída)

        Se qualquer passo falhar, executa compensação
        """

        saga_state = await self._create_saga_state(
            saga_id,
            saga_definition
        )

        executed_steps = []

        try:
            # Executar cada passo
            for step in saga_definition.steps:
                result = await self._execute_step(step, saga_state)

                if not result.success:
                    # Falhou - iniciar compensação
                    await self._compensate(
                        executed_steps,
                        saga_state
                    )
                    return SagaResult(status="COMPENSATED")

                executed_steps.append(step)

            # Todos passos executaram com sucesso
            await self._mark_saga_completed(saga_id)

            return SagaResult(status="COMPLETED")

        except Exception as e:
            logger.error(
                "saga_exception",
                saga_id=saga_id,
                error=str(e)
            )

            await self._compensate(executed_steps, saga_state)

            return SagaResult(
                status="FAILED",
                error=str(e)
            )

    async def _execute_step(
        self,
        step: SagaStep,
        saga_state: SagaState
    ) -> StepResult:
        """Executa um passo da saga"""

        logger.info(
            "saga_step_executing",
            saga_id=saga_state.saga_id,
            step=step.name
        )

        # Chamar serviço via HTTP/gRPC/Kafka
        if step.type == "http":
            return await self._execute_http_step(step, saga_state)
        elif step.type == "kafka":
            return await self._execute_kafka_step(step, saga_state)
        elif step.type == "grpc":
            return await self._execute_grpc_step(step, saga_state)

    async def _compensate(
        self,
        executed_steps: List[SagaStep],
        saga_state: SagaState
    ):
        """Executa compensação de passos executados"""

        logger.info(
            "saga_compensate_start",
            saga_id=saga_state.saga_id,
            steps_to_compensate=len(executed_steps)
        )

        # Compensar em ordem reversa
        for step in reversed(executed_steps):
            if step.compensation_action:
                try:
                    await self._execute_compensation(step, saga_state)
                    logger.info(
                        "saga_step_compensated",
                        step=step.name
                    )
                except Exception as e:
                    logger.error(
                        "saga_compensation_failed",
                        step=step.name,
                        error=str(e)
                    )
```

---

## 70. Final Checklist de Produção

### Pre-Go-Live Checklist

```markdown
# Neural Hive-Mind - Pre-Production Checklist

## Infrastructure
- [ ] Cluster Kubernetes configurado
  - [ ] Nodes com recursos suficientes (CPU, Memory, Storage)
  - [ ] Network policies configuradas
  - [ ] Ingress controller instalado
  - [ ] Cert-manager instalado (TLS automático)
  - [ ] PersistentVolumes configurados
- [ ] Infraestrutura de suporte
  - [ ] MongoDB replicaset (3 nós)
  - [ ] Redis cluster (3 nós)
  - [ ] Kafka cluster (3 brokers)
  - [ ] Temporal cluster (3 nós)
  - [ ] S3/MinIO para artefatos

## Security
- [ ] Secrets gerenciados
  - [ ] Usando Vault/K8s Secrets (não ConfigMap)
  - [ ] RBAC configurado
  - [ ] Network policies restritivas
- [ ] TLS habilitado
  - [ ] Certificados válidos
  - [ ] Redirecionamento HTTP→HTTPS
- [ ] Autenticação OAuth2/Keycloak
- [ ] Rate limiting configurado
- [ ] Audit logging habilitado

## Observability
- [ ] Tracing distribuído
  - [ ] Jaeger instalado
  - [ ] OpenTelemetry em todos serviços
  - [ ] Trace propagation funcionando
- [ ] Metrics
  - [ ] Prometheus configurado
  - [ ] Dashboards Grafana criados
  - [ ] Alertas Prometheus configurados
  - [ ] SLA monitors ativos
- [ ] Logging
  - [ ] Loki/Elastic Stack configurado
  - [ ] Structured logging
  - [ ] Log levels adequados (INFO, WARNING, ERROR)

## Data Backup
- [ ] Backup MongoDB automatizado
- [ ] Backup Redis configurado
- [ ] Kafka log retention configurado
- [ ] Backups armazenados off-site (S3)
- [ ] Procedimento de restore testado
- [ ] Retention policies definidas

## Application Readiness
- [ ] Health checks implementados
  - [ ] /health/live (liveness)
  - [ ] /health/ready (readiness)
- [ ] Graceful shutdown implementado
- [ ] Database migrations planejadas
- [ ] Rollback procedures documentados
- [ ] Runbooks operacionais criados

## Performance
- [ ] Profiling baseline estabelecido
- [ ] Load testing executado
  - [ ] Cenário de pico esperado
  - [ ] SLOs definidos e medidos
- [ ] Circuit breakers testados
- [ ] Caching configurado
- [ ] Connection pools otimizados
- [ ] HPA (Horizontal Pod Autoscaler) configurado

## Testing
- [ ] Testes unitários executando
- [ ] Testes de integração passando
- [ ] Testes E2E automatizados
- [ ] Testes de carga realizados
- [ ] Penetration testing realizado

## Documentation
- [ ] API docs atualizadas
- [ ] Architecture diagrams atualizados
- [ ] Runbooks documentados
- [ ] On-call procedures definidos
- [ ] Escalation matrix definida

## Monitoring & Alerting
- [ ] Dashboard de operações ativo
- [ ] Alertas críticos configurados
- [ ] On-call rotação definida
- [ ] PagerDuty/Slack integração
- [ ] Post-mortem process definido

## Compliance
- [ ] GDPR compliance (se aplicável)
- [ ] SOC2 preparado (se aplicável)
- [ ] Audit trail completo
- [ ] Retention policies seguidas
```

---

## 71. Análise Profunda do Fluxo Orchestrator Dynamic

### 71.1 Visão Geral do Fluxo C (Orchestration)

O **Orchestrator Dynamic** implementa o **Fluxo C** do NHM - a camada de orquestração que transforma Cognitive Plans em Execution Tickets. É um **serviço stateless** que usa **Temporal workflows** para garantir execução confiável.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FLUXO C - ORCHESTRATION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  plans.consensus          ┌──────────────────────────────────────┐         │
│  (Kafka Topic)    ───────▶│     FlowCConsumer                    │         │
│                          │     - Deserializa Avro/JSON           │         │
│  cognitive-plans-         │     - Extrai baggage (intent/plan)    │         │
│  approval-responses  ─────┤     - Executa Flow C                  │         │
│                          └─────────────────┬──────────────────────┘         │
│                                             │                                 │
│                                             ▼                                 │
│                          ┌──────────────────────────────────────┐         │
│                          │     FlowCOrchestrator                │         │
│                          │     - Gerencia workflow Temporal      │         │
│                          │     - Aprovações                      │         │
│                          └─────────────────┬──────────────────────┘         │
│                                             │                                 │
│                                             ▼                                 │
│                          ┌──────────────────────────────────────┐         │
│                          │  OrchestrationWorkflow (Temporal)     │         │
│                          │  ┌─────────────────────────────────┐  │         │
│                          │  │ C1: Validar Plano Cognitivo     │  │         │
│                          │  │ C2: Gerar Execution Tickets     │  │         │
│                          │  │ SLA Check (proativo)            │  │         │
│                          │  │ C3: Alocar Recursos             │  │         │
│                          │  │ C4: Publicar Tickets (Kafka)    │  │         │
│                          │  │ SLA Check (proativo)            │  │         │
│                          │  │ C5: Consolidar Resultados       │  │         │
│                          │  │ Saga Compensation (se falha)    │  │         │
│                          │  │ Self-Healing Trigger            │  │         │
│                          │  │ C6: Publicar Telemetria         │  │         │
│                          │  └─────────────────────────────────┘  │         │
│                          └─────────────────┬──────────────────────┘         │
│                                             │                                 │
│                                             ▼                                 │
│                          execution.tickets (Kafka) ──▶ Worker Agents         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 71.2 Componentes Principais

#### 71.2.1 FlowCConsumer

**Arquivo:** `services/orchestrator-dynamic/src/integration/flow_c_consumer.py`

**Responsabilidades:**
- Consumir mensagens do tópico `plans.consensus`
- Deserializar mensagens Avro/JSON
- Extrair contexto de tracing (headers W3C)
- Executar Flow C via FlowCOrchestrator
- Publicar incidentes em caso de falha

**Configurações Críticas:**
```python
consumer_config = {
    'bootstrap_servers': 'kafka-bootstrap.kafka.svc.cluster.local:9092',
    'group_id': 'flow-c-orchestrator',
    'auto_offset_reset': 'earliest',
    'enable_auto_commit': False,  # Commit manual após processamento
    'max_poll_interval_ms': 21600000,  # 6 HORAS - para workflows longos
    'session_timeout_ms': 30000,
    # NOTA: value_deserializer não usado - deserialização manual
}
```

**Por que 6 horas de max_poll_interval_ms?**
- Flow C pode levar **4+ horas** para planos complexos
- O consumer não deve ser rebalanceado durante execução
- Permite múltiplos tickets serem processados sequencialmente

#### 71.2.2 FlowCApprovalResponseConsumer

**Responsabilidades:**
- Consumir aprovações do tópico `cognitive-plans-approval-responses`
- Desserializar `cognitive_plan_json` (Avro workaround)
- Resumir Flow C após aprovação humana

**Tratamento Especial do cognitive_plan:**
```python
# O Approval Service serializa cognitive_plan como string JSON
# no campo cognitive_plan_json (Avro não suporta objetos aninhados)
cognitive_plan_json = approval_response.get("cognitive_plan_json")
if isinstance(cognitive_plan_json, str):
    cognitive_plan = json.loads(cognitive_plan_json)
    approval_response["cognitive_plan"] = cognitive_plan
```

#### 71.2.3 OrchestrationWorkflow (Temporal)

**Arquivo:** `services/orchestrator-dynamic/src/workflows/orchestration_workflow.py`

**Estrutura do Workflow:**
```python
@workflow.defn
class OrchestrationWorkflow:
    def __init__(self):
        self._status = 'initializing'
        self._tickets_generated = []
        self._rejected_tickets = []
        self._workflow_result = {}
        self._sla_warnings = []
```

**Signals (controle externo):**
- `ticket_completed(ticket_id, result)` - Notifica conclusão
- `cancel_workflow()` - Cancelamento manual

**Queries (inspeção):**
- `get_status()` - Retorna status atual
- `get_tickets()` - Lista tickets gerados

### 71.3 Etapas do Workflow Detalhadas

#### C1: Validar Plano Cognitivo

```python
validation_result = await workflow.execute_activity(
    validate_cognitive_plan,
    args=[plan_id, cognitive_plan],
    start_to_close_timeout=timedelta(seconds=5),
    retry_policy=RetryPolicy(
        maximum_attempts=2,
        initial_interval=timedelta(milliseconds=500),
        non_retryable_error_types=['InvalidSchemaError']
    )
)
```

**Validações:**
- Schema do cognitive_plan
- Presença de campos obrigatórios (plan_id, intent_id, tasks)
- Estrutura das tasks (dependencies, parameters)
- Regras de negócio específicas

**Audit Trail:**
```python
await workflow.execute_activity(
    audit_validation,
    args=[plan_id, validation_result],
    start_to_close_timeout=timedelta(seconds=3)
)
```

#### C2: Gerar Execution Tickets

```python
tickets = await workflow.execute_activity(
    generate_execution_tickets,
    args=[cognitive_plan, consolidated_decision],
    start_to_close_timeout=timedelta(seconds=30),
    retry_policy=RetryPolicy(maximum_attempts=2)
)
```

**Lógica de Geração:**
- Cada task do cognitive_plan gera N tickets
- Tipos: `code_forge`, `query`, `transform`, `validate`, `compensate`
- Parâmetros específicos por tipo de executor
- Dependencies entre tickets (DAG)

**SLA Check Proativo (pós-C2):**
```python
sla_check_result = await workflow.execute_activity(
    check_workflow_sla_proactive,
    args=[workflow_id, tickets, 'post_ticket_generation'],
    start_to_close_timeout=timedelta(seconds=5)
)

if sla_check_result.get('deadline_approaching'):
    warning_msg = f'SLA proativo: deadline se aproximando, restam {sla_check_result.get("remaining_seconds")}s'
    self._sla_warnings.append({
        'checkpoint': 'post_ticket_generation',
        'warning': warning_msg
    })
```

#### C3: Alocar Recursos

```python
for ticket in tickets:
    allocated_ticket = await workflow.execute_activity(
        allocate_resources,
        args=[ticket],
        start_to_close_timeout=timedelta(seconds=10),
        retry_policy=RetryPolicy(maximum_attempts=3)
    )
```

**Alocação Inteligente:**
- Priority calculator (baseado em business impact)
- Affinity tracker (localidade de dados)
- Resource allocator (capacidade disponível)

#### C4: Publicar Tickets no Kafka

```python
for ticket in allocated_tickets:
    publish_result = await workflow.execute_activity(
        publish_ticket_to_kafka,
        args=[ticket],
        start_to_close_timeout=timedelta(seconds=15),
        retry_policy=RetryPolicy(
            maximum_attempts=5,
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0
        )
    )
```

**Separação de Tickets:**
- `published_tickets` - Enviados para `execution.tickets`
- `rejected_tickets` - Rejeitados pelo scheduler (ex: capacidade insuficiente)

#### C5: Consolidar Resultados

```python
workflow_result = await workflow.execute_activity(
    consolidate_results,
    args=[published_tickets, workflow_id],
    start_to_close_timeout=timedelta(seconds=20)
)
```

**Saga Compensation Pattern (se inconsistente):**
```python
if not workflow_result.get('consistent', True):
    # Identificar tickets falhados
    failed_tickets = [
        t for t in published_tickets
        if t.get('ticket', {}).get('status') == 'FAILED'
    ]

    # Ordenação topológica reversa
    tickets_to_compensate = await workflow.execute_activity(
        build_compensation_order,
        args=[failed_tickets, published_tickets]
    )

    # Executar compensação
    for ticket_to_compensate in tickets_to_compensate:
        compensation_ticket_id = await workflow.execute_activity(
            compensate_ticket,
            args=[ticket_to_compensate, 'workflow_inconsistent']
        )
```

**Self-Healing Trigger:**
```python
await workflow.execute_activity(
    trigger_self_healing,
    args=[workflow_id, errors, published_tickets, workflow_result],
    start_to_close_timeout=timedelta(seconds=10)
)
```

#### C6: Publicar Telemetria

```python
try:
    await workflow.execute_activity(
        publish_telemetry,
        args=[workflow_result],
        start_to_close_timeout=timedelta(seconds=15),
        retry_policy=RetryPolicy(maximum_attempts=5)
    )
except Exception as e:
    # Fallback para buffer
    await workflow.execute_activity(
        buffer_telemetry,
        args=[workflow_result],
        start_to_close_timeout=timedelta(seconds=5)
    )
```

### 71.4 Tracing Distribuído

**Propagação de Contexto:**
```python
# Headers W3C Traceparent
extract_context_from_headers(message.headers)

# Business baggage
set_baggage('intent_id', intent_id)
set_baggage('plan_id', plan_id)

# Span attributes
span.set_attribute("neural.hive.intent.id", intent_id)
span.set_attribute("neural.hive.plan.id", plan_id)
span.set_attribute("messaging.kafka.offset", message.offset)
```

### 71.5 Tratamento de Erros

| Tipo de Erro | Tratamento |
|--------------|------------|
| `InvalidSchemaError` | Non-retryable - falha imediata |
| `CircuitBreakerError` | Retry com backoff exponencial |
| `SLAMonitorUnavailable` | Continua sem verificação |
| Activity não registrada | Metric + warning |
| Deserialização Avro falha | Fallback para JSON |

### 71.6 SLA Monitoring Proativo

**Checkpoints de Verificação:**
1. **post_ticket_generation** - Após gerar tickets
2. **post_ticket_publishing** - Após publicar

**Métricas Monitoradas:**
- Deadline se aproximando (< 30% restante)
- Budget crítico (tokens/custo)
- Tickets críticos pendentes

### 71.7 Integração com Serviços Externos

| Serviço | Tipo | Uso |
|---------|------|-----|
| Kafka | Message Broker | plans.consensus → execution.tickets |
| Temporal | Workflow Engine | Orquestração de C1-C6 |
| MongoDB | Database | Persistência de planos/tickets |
| Redis | Cache | Deduplicação, rate limiting |
| Schema Registry | Avro Schemas | Validação de mensagens |

### 71.8 Performance Considerations

**Timeouts Configurados:**
| Activity | Timeout | Justificativa |
|----------|---------|---------------|
| validate_cognitive_plan | 5s | Validação local |
| generate_execution_tickets | 30s | Pode gerar muitos tickets |
| allocate_resources | 10s | Consulta scheduler externo |
| publish_ticket_to_kafka | 15s | Rede + Kafka latency |
| consolidate_results | 20s | Queries agregadas |
| publish_telemetry | 15s | Prometheus remoto |

### 71.9 Diagrama de Estados

```
                    ┌──────────────┐
                    │  initializing │
                    └───────┬──────┘
                            │
                            ▼
                    ┌──────────────┐
              ┌────▶│validating_plan│
              │     └───────┬──────┘
              │             │
              │             ▼
              │     ┌──────────────┐
              │     │generating_tickets
              │     └───────┬──────┘
              │             │
              │             ▼
              │     ┌──────────────┐
              │     │allocating_resources
              │     └───────┬──────┘
              │             │
              │             ▼
              │     ┌──────────────┐
              │     │publishing_tickets
              │     └───────┬──────┘
              │             │
              │             ▼
              │     ┌──────────────┐
              │     │consolidating_results
              │     └───────┬──────┘
              │             │
              │  ┌──────────┴──────────┐
              │  │                     │
              │  ▼                     ▼
              │ consistent          inconsistent
              │  │                     │
              │  │                     ▼
              │  │             ┌──────────────┐
              │  │             │ compensation │
              │  │             └───────┬──────┘
              │  │                     │
              │  └──────────┬──────────┘
              │             │
              ▼             ▼
     ┌──────────────┐  ┌──────────────┐
     │publishing_   │  │   failed     │
     │telemetry     │  └──────────────┘
     └───────┬──────┘
             │
             ▼
     ┌──────────────┐
     │  completed   │
     └──────────────┘

Sinal: cancel_workflow ──▶ cancelled (de qualquer estado)
```

---

**Fim do Documento**

Este documento contém uma análise abrangente do Neural Hive-Mind, cobrindo 71 seções técnicas desde a arquitetura de alto nível até detalhes de implementação de produção.

**Total de seções: 71**

**Última atualização:** 2026-03-15
**Versão do documento:** 1.5
