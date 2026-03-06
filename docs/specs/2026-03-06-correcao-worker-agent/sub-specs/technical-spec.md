# Especificação Técnica

Especificação técnica para correção dos bugs críticos do Worker Agent identificados no teste E2E de 2026-03-05.

## Requisitos Técnicos

### 1. Correção do ExecutionEngine

**Arquivo:** `services/worker-agents/src/engine/execution_engine.py`
**Método:** `_execute_ticket()`
**Linhas:** 270-294

**Implementação atual:**
```python
result = await self._execute_task_with_retry(ticket)
duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

await self.ticket_client.update_ticket_status(
    ticket_id,
    'COMPLETED',
    actual_duration_ms=duration_ms
)
```

**Implementação corrigida:**
```python
result = await self._execute_task_with_retry(ticket)
duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

if result.get('success'):
    await self.ticket_client.update_ticket_status(
        ticket_id,
        'COMPLETED',
        actual_duration_ms=duration_ms
    )
    await self.result_producer.publish_result(
        ticket_id,
        'COMPLETED',
        result,
        actual_duration_ms=duration_ms
    )
else:
    error_msg = result.get('error', 'Task execution failed')
    await self.ticket_client.update_ticket_status(
        ticket_id,
        'FAILED',
        actual_duration_ms=duration_ms,
        error_message=error_msg
    )
    await self.result_producer.publish_result(
        ticket_id,
        'FAILED',
        result,
        actual_duration_ms=duration_ms
    )
```

**Critérios de aceite:**
- Tickets com `result['success'] == True` são marcados COMPLETED
- Tickets com `result['success'] == False` são marcados FAILED
- Mensagem de erro é incluída no status do ticket
- Result producer publica status correto

### 2. Validação de Parâmetros nos Executors

**Arquivos:**
- `services/worker-agents/src/executors/base_executor.py`
- `services/worker-agents/src/executors/query_executor.py`
- `services/worker-agents/src/executors/transform_executor.py`
- `services/worker-agents/src/executors/validate_executor.py`

**Implementação - BaseExecutor:**
```python
def validate_required_parameters(
    self,
    ticket_id: str,
    parameters: Dict[str, Any],
    required: List[str]
) -> None:
    """
    Valida que todos os parâmetros obrigatórios estão presentes.

    Raises:
        ValueError: Se algum parâmetro obrigatório estiver faltando
    """
    missing = [p for p in required if p not in parameters or not parameters[p]]
    if missing:
        raise ValueError(
            f"Ticket {ticket_id}: Missing required parameters: {missing}. "
            f"Got: {list(parameters.keys())}"
        )
```

**Uso no QueryExecutor:**
```python
def validate_ticket(self, ticket: ExecutionTicket) -> None:
    """Valida parâmetros do ticket QUERY."""
    self.validate_required_parameters(
        ticket.ticket_id,
        ticket.parameters,
        required=['collection']
    )
```

**Uso no TransformExecutor:**
```python
def validate_ticket(self, ticket: ExecutionTicket) -> None:
    """Valida parâmetros do ticket TRANSFORM."""
    self.validate_required_parameters(
        ticket.ticket_id,
        ticket.parameters,
        required=['input_data']
    )
```

### 3. Geração de Parâmetros Específicos na STE

**Arquivo:** `services/semantic-translation-engine/src/services/decomposition_templates.py`
**Classe:** `DecompositionTemplates`
**Método:** `generate_tasks()`

**Implementação corrigida:**
```python
def _build_task_parameters(
    self,
    task_template: TaskTemplate,
    subject: str,
    target: str,
    entities: List[str],
    intent_text: str
) -> Dict[str, Any]:
    """
    Constrói parâmetros específicos para cada tipo de task.
    """
    # Parâmetros base
    base_params = {
        "subject": subject,
        "target": target,
        "entities": entities
    }

    # Adicionar parâmetros específicos por tipo
    if task_template.task_type == 'query':
        # Inferir coleção MongoDB baseado no subject
        collection = self._infer_collection(subject, entities)
        base_params.update({
            "collection": collection,
            "filter": self._build_filter(subject, entities),
            "limit": 100
        })

    elif task_template.task_type == 'transform':
        # Para transform, input_data será preenchido durante execução
        # ou pode ter origem em tasks QUERY anteriores
        base_params.update({
            "input_data": None,  # Será populado pelo executor
            "operations": []
        })

    elif task_template.task_type == 'validate':
        # Mapear para política OPA apropriada
        policy_path = self._get_policy_path(subject, task_template.semantic_domain)
        base_params.update({
            "policy_path": policy_path,
            "input_data": None  # Será populado pelo executor
        })

    return base_params

def _infer_collection(self, subject: str, entities: List[str]) -> str:
    """
    Infere nome da coleção MongoDB baseado no subject.
    """
    # Mapeamento de subjects para coleções
    collection_map = {
        'sap': 'sap_infrastructure',
        'kubernetes': 'kubernetes_clusters',
        'infraestrutura': 'infrastructure_inventory',
        'sistema': 'systems_catalog'
    }

    subject_lower = subject.lower()
    for key, collection in collection_map.items():
        if key in subject_lower:
            return collection

    # Fallback: usar primeira entidade ou nome derivado
    return entities[0].lower().replace(' ', '_') if entities else 'default'

def _get_policy_path(
    self,
    subject: str,
    semantic_domain: str
) -> str:
    """
    Retorna caminho da política OPA baseado no domínio semântico.
    """
    policy_map = {
        'security': '/neural_hive/security/validation',
        'architecture': '/neural_hive/architecture/compliance',
        'quality': '/neural_hive/quality/standards',
        'performance': '/neural_hive/performance/limits'
    }

    return policy_map.get(semantic_domain, '/neural_hive/default/validation')
```

**Modificação no método `generate_tasks()`:**
```python
# ANTES (linha 565):
parameters={
    "subject": subject,
    "target": target,
    "entities": entities
},

# DEPOIS:
parameters=self._build_task_parameters(
    task_template, subject, target, entities, intent_text
),
```

## Ordem de Implementação

1. **BaseExecutor** - Adicionar método `validate_required_parameters()`
2. **QueryExecutor** - Adicionar `validate_ticket()` usando o novo método
3. **TransformExecutor** - Adicionar `validate_ticket()` usando o novo método
4. **ValidateExecutor** - Adicionar `validate_ticket()` usando o novo método
5. **ExecutionEngine** - Modificar para verificar `result['success']`
6. **DecompositionTemplates** - Adicionar `_build_task_parameters()` e métodos auxiliares
7. **Testes** - Executar teste E2E para validar as correções

## Testes

### Teste 1: Falha de Execução Deve Retornar FAILED
1. Criar ticket com parâmetros inválidos
2. Executar via Worker Agent
3. Verificar que status final é FAILED (não COMPLETED)

### Teste 2: Query com Parâmetros Corretos
1. Criar ticket QUERY com `collection` válida
2. Executar via Worker Agent
3. Verificar que status final é COMPLETED

### Teste 3: Transform com Parâmetros Corretos
1. Criar ticket TRANSFORM com `input_data` válido
2. Executar via Worker Agent
3. Verificar que status final é COMPLETED

### Teste 4: E2E Completo
1. Enviar intent pela Gateway
2. Verificar que tickets são criados com parâmetros corretos
3. Verificar que execução completa com sucesso
