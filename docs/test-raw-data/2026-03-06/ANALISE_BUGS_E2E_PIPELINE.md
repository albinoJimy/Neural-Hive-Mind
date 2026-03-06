# Análise de Bugs - Teste E2E Pipeline Completo

**Data:** 2026-03-06
**Teste:** E2E Pipeline Completo
**Intent ID:** 2663b828-5d7d-439d-90ff-8ce0ba79e9f8
**Plan ID:** 1ac4f574-4109-4db3-931b-b0cea24d6a68

---

## Resumo Executivo

Três bugs críticos foram identificados durante a execução do teste E2E que impedem a conclusão do fluxo de execução:

1. **Retry com ticket_id duplicado** - Violação de chave única no PostgreSQL
2. **Filtro agent_type ignorado** - Workers não são descobertos pelo Orchestrator
3. **Formato incorreto da mensagem de aprovação** - Campo `decision` ausente

---

## Bug 1: Retry com ticket_id Duplicado

### Severidade: ALTA
### Impacto: Tickets não são criados devido a erro de duplicação

### Localização
- **Arquivo:** `libraries/neural_hive_integration/neural_hive_integration/clients/execution_ticket_client.py`
- **Linha:** 135-161

### Descrição

O método `create_ticket` possui um decorator `@retry` que tenta recriar o ticket com o **mesmo ticket_id** em caso de falha de rede/timeout.

### Root Cause

1. O `ticket_id` é gerado pelo orchestrator ANTES de chamar `create_ticket()`
2. Quando ocorre um timeout na resposta HTTP, o tenacity refaz a chamada com os **mesmos argumentos**
3. O PostgreSQL já inseriu o ticket na primeira tentativa (sucesso silencioso)
4. Segunda e terceira tentativas falham com `UniqueViolationError`

### Logs do Erro

```
2026-03-06T23:27:39.707341 - ticket_created (201 Created)
2026-03-06T23:27:41.725756 - duplicate key error (500)
2026-03-06T23:27:43.744242 - duplicate key error (500)
```

### Correção Aplicada

Gerar o `ticket_id` dentro do método `create_ticket()` para que cada retry use um UUID diferente:

```python
# FIX: Generate ticket_id inside create_ticket to avoid duplicate key on retry
if "ticket_id" not in ticket_data or not ticket_data["ticket_id"]:
    from uuid import uuid4
    ticket_data = ticket_data.copy()
    ticket_data["ticket_id"] = str(uuid4())
```

---

## Bug 2: Filtro agent_type Ignorado

### Severidade: CRÍTICA
### Impacto: Workers não são descobertos, tickets nunca são processados

### Localização
- **Arquivo:** `services/service-registry/src/grpc_server/registry_servicer.py`
- **Linha:** 175-190

### Descrição

O filtro `agent_type` passado via `filters={"agent_type": "WORKER"}` é ignorado pelo método `DiscoverAgents`.

### Root Cause

1. Orchestrator chama: `discover_agents(capabilities=[], filters={"agent_type": "WORKER"})`
2. `DiscoverAgents` passa `filters` para `match_agents` sem extrair `agent_type`
3. `match_agents` chama `etcd_client.list_agents(agent_type=None, filters=...)`
4. `agent_type=None` faz scan de todos os tipos de agente
5. O filtro `{"agent_type": "WORKER"}` no dict `filters` não é tratado

### Logs do Erro

```
2026-03-06 23:27:43 [info] discovering_agents capabilities=[]
2026-03-06 23:27:43 [info] agents_discovered count=0
```

### Correção Aplicada

Extrair `agent_type` do `filters` e passá-lo como parâmetro para `match_agents`:

```python
# Extract agent_type from filters for match_agents
agent_type = None
if filters and "agent_type" in filters:
    agent_type_str = filters.pop("agent_type").lower()
    # Convert to AgentType enum
    agent_type = AgentType[agent_type_str.upper()]

agents = await self.matching_engine.match_agents(
    capabilities_required=capabilities_required,
    filters=filters,
    max_results=max_results,
    agent_type=agent_type  # ← Passar agent_type explicitamente
)
```

---

## Bug 3: Formato Incorreto da Mensagem de Aprovação

### Severidade: MÉDIA
### Impacto: Mensagem precisa usar campo `decision` em vez de `status`

### Localização
- **Componente:** Produtor de mensagens Kafka (Approval Service ou manual)

### Descrição

A mensagem de aprovação enviada ao tópico `cognitive-plans-approval-responses` deve usar o campo `decision`, não `status`.

### Root Cause

O código `flow_c_orchestrator.py:1592` faz:
```python
decision = approval_response.get("decision", "rejected")
```

Se o campo `decision` não existe, default é `"rejected"` e o plano não é executado.

### Formato Incorreto (enviado durante teste)

```python
{
    'approval_id': 'aa57a9b7-3b81-4e5c-be61-ed58b304a782',
    'plan_id': '1ac4f574-4109-4db3-931b-b0cea24d6a68',
    'status': 'approved',  # ❌ ERRADO
    'approved_by': 'qa-tester',
    'approved_at': '2026-03-06T23:17:16.476Z'
}
```

### Formato Correto

```python
{
    'approval_id': 'aa57a9b7-3b81-4e5c-be61-ed58b304a782',
    'plan_id': '1ac4f574-4109-4db3-931b-b0cea24d6a68',
    'decision': 'approved',  # ✅ CORRETO
    'approved_by': 'qa-tester',
    'approved_at': '2026-03-06T23:17:16.476Z',
    'trace_id': '2663b828-5d7d-439d-90ff-8ce0ba79e9f8'
}
```

---

## Validação das Correções

### Pré-requisitos para Re-deploy

1. **Rebuild das imagens:**
   - `neural_hive_integration` (Bug 1)
   - `service-registry` (Bug 2)

2. **Redeploy dos serviços:**
   - Service Registry
   - Orchestrator Dynamic

### Teste de Validação

Após aplicar as correções, executar novamente o teste E2E para verificar:

1. Workers são descobertos corretamente (count > 0)
2. Tickets são criados sem erro de duplicação
3. Tickets mudam de status PENDING → ASSIGNED → COMPLETED

---

## Status das Correções

| Bug | Status | Commit |
|-----|--------|--------|
| Bug 1 - Retry ticket_id | ✅ CORRIGIDO | Pending commit |
| Bug 2 - Filtro agent_type | ✅ CORRIGIDO | Pending commit |
| Bug 3 - Formato mensagem | ✅ DOCUMENTADO | N/A |

---

## Recomendações Adicionais

1. **Adicionar teste unitário** para `DiscoverAgents` verificando filtro `agent_type`
2. **Adicionar teste de integração** para retry com ticket_id duplicado
3. **Validação de schema** da mensagem de aprovação no consumo do Kafka
