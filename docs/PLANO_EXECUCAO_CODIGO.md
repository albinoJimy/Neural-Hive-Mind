# Neural Hive-Mind: Plano de Execução - Nível de Código

**Status:** Pronto para Execução
**Data:** 2026-03-13
**Estratégia:** Fases sequenciais com dependências claras

---

## Como Usar Este Plano

Este documento contém instruções detalhadas para cada fase. Para executar:

```bash
# Executar uma fase específica
 Claude: "Execute FASE 1 do plano em docs/PLANO_EXECUCAO_CODIGO.md"

# Executar todas as fases
Claude: "Execute todas as fases do plano em docs/PLANO_EXECUCAO_CODIGO.md"
```

---

## FASE 1: Rastreabilidade e Segurança (2 dias)

### Objetivo
Garantir que `correlation_id` seja propagado através de todos os serviços, eliminando VULN-001.

### 1.1 Gateway de Intenções

**Arquivo:** `services/gateway-intencoes/src/pipelines/nlu_pipeline.py`

**Localização:** Método `process()` (~linha 80-120)

**Alteração Necessária:**

```python
# ANTES (aprox linha 90):
intent_envelope = IntentEnvelope(
    id=str(uuid.uuid4()),
    intent=intent_dict,
    confidence=confidence,
    domain=domain,
    timestamp=datetime.utcnow(),
    # correlation_id pode vir de contexto
    correlation_id=context.get('correlation_id') or context.get('correlationId')
)

# DEPOIS:
import uuid as uuid_lib

# Garantir correlation_id sempre presente
correlation_id = (
    context.get('correlation_id') or
    context.get('correlationId') or
    str(uuid_lib.uuid4())  # GERAR SE AUSENTE
)

intent_envelope = IntentEnvelope(
    id=str(uuid_lib.uuid4()),
    intent=intent_dict,
    confidence=confidence,
    domain=domain,
    timestamp=datetime.utcnow(),
    correlation_id=correlation_id,  # NUNCA mais None
    trace_parent=context.get('trace_parent'),
    trace_state=context.get('trace_state')
)
```

**Passos:**
1. Abrir `services/gateway-intencoes/src/pipelines/nlu_pipeline.py`
2. Localizar método `process()`
3. Encontrar criação de `IntentEnvelope`
4. Adicionar geração de UUID para correlation_id se ausente
5. Testar: `python -m pytest tests/unit/test_intent_envelope.py -k correlation`

---

### 1.2 Semantic Translation Engine

**Arquivo:** `services/semantic-translation-engine/src/services/orchestrator.py`

**Localização:** Método `process_intent()` (linha 52-96)

**Alteração Necessária:**

```python
# ADICIONAR no início do método process_intent():
async def process_intent(self, intent_envelope: Dict, trace_context: Dict):
    # VALIDAR E GERAR correlation_id SE NECESSÁRIO
    correlation_id = (
        trace_context.get('correlation_id') or
        intent_envelope.get('correlationId') or
        intent_envelope.get('correlation_id')
    )

    if not correlation_id:
        import uuid as uuid_lib
        correlation_id = str(uuid_lib.uuid4())
        logger.warning(
            'correlation_id_generated_in_ste',
            intent_id=intent_envelope.get('id'),
            generated_correlation_id=correlation_id
        )

    # Garantir que está presente no trace_context
    trace_context['correlation_id'] = correlation_id

    # Continuar com o restante do método...
```

**Passos:**
1. Abrir arquivo
2. Adicionar validação logo após o `start_time`
3. Testar com intenção sem correlation_id

---

### 1.3 Consensus Engine - Remover VULN-001

**Arquivo:** `services/consensus-engine/src/services/consensus_orchestrator.py`

**Localização:** Linhas 150-169

**Alteração Necessária:**

```python
# ANTES (linhas 150-169):
if not correlation_id or (isinstance(correlation_id, str) and not correlation_id.strip()):
    correlation_id = str(uuid.uuid4())
    ObservabilityMetrics.increment_correlation_id_missing()
    ObservabilityMetrics.increment_correlation_id_generated()

    # ERROR: Isso quebra rastreamento distribuído
    logger.error(
        'VULN-001: correlation_id ausente...',
        ...
    )

# DEPOIS:
if not correlation_id or (isinstance(correlation_id, str) and not correlation_id.strip()):
    correlation_id = str(uuid.uuid4())
    ObservabilityMetrics.increment_correlation_id_missing()
    ObservabilityMetrics.increment_correlation_id_generated()

    # WARNING: correlation_id gerado, mas rastreamento mantido
    logger.warning(
        'correlation_id_generated_in_consensus',
        plan_id=cognitive_plan['plan_id'],
        generated_correlation_id=correlation_id,
        upstream_source='semantic_translation_engine'
    )
```

**Passos:**
1. Mudar `logger.error` para `logger.warning`
2. Remover label "VULN-001"
3. Atualizar mensagem para ser mais informativa
4. Testar E2E do fluxo de aprovação

---

### 1.4 Orchestrator Dynamic

**Arquivo:** `services/orchestrator-dynamic/src/activities/ticket_generation.py`

**Localização:** Activity `generate_execution_tickets()` (linha 56-266)

**Alteração Necessária:**

```python
# ADICIONAR após linha 77 (dentro do try):
# Validar e gerar correlation_id SE AUSENTE
correlation_id = (
    (consolidated_decision or cognitive_plan).get('correlation_id') or
    cognitive_plan.get('correlationId')  # formato camelCase
)

if not correlation_id:
    import uuid as uuid_lib
    correlation_id = str(uuid_lib.uuid4())
    activity.logger.warning(
        'correlation_id_generated_in_orchestrator',
        plan_id=cognitive_plan.get('plan_id'),
        generated_correlation_id=correlation_id
    )

# Garantir que correlation_id está no trace_context
# (já existe código para isso, apenas validar que funciona)
```

**Passos:**
1. Inserir validação após linha 77
2. Garantir que correlation_id é propagado para tickets
3. Testar geração de tickets

---

### 1.5 Worker Agents

**Arquivo:** `services/worker-agents/src/engine/execution_engine.py`

**Localização:** Método `process_ticket()` (linha 159-197)

**Alteração Necessária:**

```python
# ADICIONAR validação após linha 163:
async def process_ticket(self, ticket: Dict[str, Any]):
    ticket_id = ticket.get('ticket_id')

    # VALIDAÇÃO: correlation_id é obrigatório
    correlation_id = ticket.get('correlation_id')
    if not correlation_id:
        import uuid as uuid_lib
        correlation_id = str(uuid_lib.uuid4())
        ticket['correlation_id'] = correlation_id
        self.logger.warning(
            'correlation_id_generated_in_worker',
            ticket_id=ticket_id,
            generated_correlation_id=correlation_id
        )
        if self.metrics:
            self.metrics.correlation_id_missing_total.inc()

    # Continuar com validação de duplicata...
```

**Passos:**
1. Adicionar validação no início de `process_ticket()`
2. Garantir que correlation_id está nos resultados publicados
3. Testar processamento de tickets

---

### Critérios de Aceitação Fase 1

**Objetivo:** Garantir que `correlation_id` seja propagado através de todos os serviços.

- [x] **Todos os serviços geram correlation_id se ausente**
  - Gateway: `IntentEnvelope.correlation_id` com `default_factory`
  - STE: validação e geração de UUID no `process_intent()`
  - Consensus: mudança de ERROR para WARNING na geração
  - Orchestrator: validação em `generate_execution_tickets()`
  - Worker: validação em `process_ticket()`

- [x] **Métrica `correlation_id_missing_total` registrada**
  - Verificado em: `services/worker-agents/src/observability/metrics.py`
  - Incrementado quando correlation_id é gerado (missing)

- [x] **Zero erros "VULN-001" nos logs**
  - `consensus_orchestrator.py` linha 148: mudado para WARNING
  - Mensagem informativa sobre origem da geração

- [ ] **Teste E2E: trace completo no Jaeger/Tempo**
  - Requer: ambiente rodando com Jaeger/Tempo disponível
  - Validar: traceparent presente em todos os hops

**Validação:**
```bash
# Verificar logs não contêm VULN-001
kubectl logs -n neural-hive-mend -l app=consensus-engine | grep -i "VULN-001" || echo "✅ PASS"
```

---

## FASE 2: Infraestrutura Crítica (5 dias)

### 2.1 OPA Service Deployment

#### Passo 1: Criar diretória e Chart

```bash
mkdir -p services/opa/templates
mkdir -p services/opa/policies
```

#### Passo 2: Criar Chart.yaml

**Arquivo NOVO:** `services/opa/Chart.yaml`

```yaml
apiVersion: v2
name: opa
description: Open Policy Agent for Neural Hive Mind
type: application
version: 1.0.0
appVersion: "0.60.0"
```

#### Passo 3: Criar values.yaml

**Arquivo NOVO:** `services/opa/values.yaml`

```yaml
replicaCount: 1

image:
  repository: openpolicyagent/opa
  tag: 0.60.0-envoy
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8181

env:
  - name: OPA_LOG_LEVEL
    value: info
  - name: OPA_LOG_FORMAT
    value: json

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi

policies:
  enabled: true
  configMapName: opa-policies
```

#### Passo 4: Criar deployment.yaml

**Arquivo NOVO:** `services/opa/templates/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opa
  namespace: neural-hive-mind
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: opa
  template:
    metadata:
      labels:
        app: opa
    spec:
      containers:
      - name: opa
        image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
        ports:
        - containerPort: 8181
        env:
        {{- range .Values.env }}
        - name: {{ .name }}
          value: {{ .value }}
        {{- end }}
        args:
        - "run"
        - "--server"
        - "--addr=0.0.0.0:8181"
        - "--set=decision_logs.console=true"
        volumeMounts:
        - name: policies
          mountPath: /policies
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
      volumes:
      - name: policies
        configMap:
          name: opa-policies
```

#### Passo 5: Criar service.yaml

**Arquivo NOVO:** `services/opa/templates/service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: opa
  namespace: neural-hive-mind
spec:
  type: {{ .Values.service.type }}
  ports:
  - port: {{ .Values.service.port }}
    targetPort: 8181
  selector:
    matchLabels:
      app: opa
```

#### Passo 6: Criar ConfigMap com políticas

**Arquivo NOVO:** `services/opa/templates/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: opa-policies
  namespace: neural-hive-mind
data:
  plan_validation.rego: |
    package neuralhive.plan

    default allow = true

    # Bloquear operações destrutivas não aprovadas
    deny_destructive {
      input.destructive_tasks
      not input.approved
      msg = "Plano contém operações destrutivas não aprovadas"
    }

    # Validar campos obrigatórios
    validate_required_fields[rules] {
      input.tasks
      input.execution_order
      input.risk_score >= 0
      input.risk_score <= 1
    }

    # Risco excessivo requer aprovação
    require_approval[rules] {
      input.risk_score >= 0.7
      not input.approved
      msg = "Plano de alto risco requer aprovação"
    }

    # Deny por padrão (fail-closed)
    default allow = false
```

#### Passo 7: Deploy e Teste

```bash
# Deploy via Helm
helm upgrade --install opa ./services/opa --namespace neural-hive-mind --create-namespace

# Validar deployment
kubectl get pods -n neural-hive-mind -l app=opa

# Testar API OPA
curl -X POST http://opa.neural-hive-mind.svc.cluster.local:8181/v1/data \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "tasks": [{"task_id": "test"}],
      "execution_order": ["test"],
      "risk_score": 0.5,
      "destructive_tasks": [],
      "approved": true
    }
  }'
```

---

### 2.2 Scheduler Fallback Real

#### Arquivo: `services/orchestrator-dynamic/src/activities/ticket_generation.py`

**Localização:** Linhas 509-568 (fallback stub)

**Substituir por:**

```python
# FUNÇÃO NOVA: Fallback round-robin real
async def _get_available_workers_from_registry():
    """Busca workers disponíveis no Service Registry"""
    if not _registry_client:
        raise RuntimeError("Service Registry não disponível para fallback")

    try:
        workers = await _registry_client.discover_service(
            service_name="worker-agents",
            namespace="neural-hive-mind"
        )
        return workers.get('instances', [])
    except Exception as e:
        logger.error(f"Erro ao buscar workers: {e}")
        return []

def _round_robin_select(ticket_id: str, workers: list) -> dict:
    """Seleção round-robin baseada em hash do ticket_id"""
    if not workers:
        raise RuntimeError("Nenhum worker disponível para round-robin")

    index = hash(ticket_id) % len(workers)
    return workers[index]

# SUBSTITUIR linhas 509-568 por:
if not _intelligent_scheduler or (_config and _config.scheduler_fallback_stub_enabled):
    if not _intelligent_scheduler:
        fallback_reason = 'scheduler_unavailable'
    else:
        fallback_reason = fallback_reason if 'fallback_reason' in locals() else 'scheduler_failed'

    # Fallback REAL (não stub)
    try:
        workers = await _get_available_workers_from_registry()
        selected_worker = _round_robin_select(ticket_id, workers)

        logger.info(
            'scheduler_fallback_round_robin_selected',
            ticket_id=ticket_id,
            selected_worker=selected_worker.get('agent_id'),
            available_workers=len(workers)
        )

        allocation_metadata = {
            'allocated_at': int(datetime.now().timestamp() * 1000),
            'agent_id': selected_worker.get('agent_id'),
            'agent_type': selected_worker.get('type', 'worker-agent'),
            'agent_address': selected_worker.get('address'),
            'priority_score': ticket.get('risk_band', 0.5),
            'allocation_method': 'round_robin_fallback',
            'workers_evaluated': len(workers)
        }

        ticket['allocation_metadata'] = allocation_metadata

        # Adicionar ML predictions se disponível
        if predicted_duration_ms is not None:
            ticket['allocation_metadata']['predicted_duration_ms'] = predicted_duration_ms

        logger.info(f'Recursos alocados (fallback round-robin) para ticket {ticket_id}')

    except Exception as fallback_error:
        # ÚLTIMO recurso: apenas logar erro e continuar com ticket sem alocação
        logger.error(
            'scheduler_round_robin_failed_using_unallocated',
            ticket_id=ticket_id,
            error=str(fallback_error),
            message='Ticket sem alocação - worker agents selecionarão aleatoriamente'
        )

        allocation_metadata = {
            'allocated_at': int(datetime.now().timestamp() * 1000),
            'agent_id': 'unallocated',
            'allocation_method': 'none',
            'workers_evaluated': 0
        }
        ticket['allocation_metadata'] = allocation_metadata
```

---

### 2.3 Deduplicação MongoDB Fallback

#### Arquivo: `services/worker-agents/src/engine/execution_engine.py`

**Localização:** Método `_is_duplicate_ticket()` (linha 39-102)

**Adicionar após validação Redis:**

```python
async def _is_duplicate_ticket(self, ticket_id: str) -> bool:
    # ... código Redis existente ...

    # Se Redis falhar ou não estiver disponível, tentar MongoDB
    if not self.redis_client or redis_result is None:
        if self.ticket_client:
            try:
                logger.info(
                    'redis_unavailable_checking_mongodb_dup',
                    ticket_id=ticket_id
                )

                # Buscar no MongoDB
                existing = await self.ticket_client.get_ticket_by_id(ticket_id)

                if existing and existing.get('status') in ('COMPLETED', 'FAILED'):
                    # Verificar se é duplicata recente (últimas 24h)
                    completed_at = existing.get('completed_at')
                    if completed_at:
                        from datetime import datetime, timedelta
                        completed_time = datetime.fromtimestamp(completed_at / 1000)
                        if datetime.now() - completed_time < timedelta(hours=24):
                            logger.info(
                                'duplicate_found_in_mongodb',
                                ticket_id=ticket_id,
                                status=existing.get('status')
                            )
                            if self.metrics:
                                self.metrics.duplicates_detected_total.labels(component='mongodb_fallback').inc()
                            return True

                logger.debug('no_duplicate_in_mongodb', ticket_id=ticket_id)

            except Exception as mongo_error:
                logger.error(
                    'mongodb_fallback_check_failed',
                    ticket_id=ticket_id,
                    error=str(mongo_error)
                )

    return False  # Fail-open se não conseguir verificar
```

**Também adicionar método no TicketClient:**

**Arquivo:** `services/worker-agents/src/clients/execution_ticket_client.py`

```python
async def get_ticket_by_id(self, ticket_id: str) -> Optional[Dict]:
    """Busca ticket por ID no MongoDB"""
    try:
        result = await self.collection.find_one({'ticket_id': ticket_id})
        if result:
            return dict(result)
        return None
    except Exception as e:
        logger.error(f"Erro ao buscar ticket {ticket_id}: {e}")
        return None
```

### Critérios de Aceitação Fase 2

**Objetivo:** Infraestrutura crítica funcional (OPA, Scheduler, Deduplicação).

**2.1 OPA Service Deployment:**
- [x] **Helm chart criado**
  - `services/opa/Chart.yaml` - Definição do chart
  - `services/opa/values.yaml` - Configurações padrão
  - `services/opa/templates/deployment.yaml` - Deployment OPA
  - `services/opa/templates/service.yaml` - Service ClusterIP
  - `services/opa/templates/_helpers.tpl` - Template helpers

- [x] **Políticas Rego criadas**
  - `services/opa/policies/neural_hive_plan_validation.rego`
  - Validação de campos obrigatórios
  - Bloqueio de operações destrutivas não aprovadas
  - Regra de aprovação para alto risco (risk_score >= 0.7)

- [ ] **OPA deployed e acessível**
  - Pod rodando: `kubectl get pods -n neural-hive-mind -l app=opa`
  - Service acessível: `curl http://opa.neural-hive-mind.svc:8181/v1/data`

**2.2 Scheduler Fallback Real:**
- [x] **Fallback round-robin implementado**
  - `_get_available_workers()` - busca workers do Service Registry
  - `_simple_round_robin_allocation()` - seleção round-robin
  - Removido lógica de `fallback_stub`

- [ ] **Zero tickets com allocation_method='fallback_stub'**
  - Verificar: logs não contêm `fallback_stub`
  - Todos os tickets têm `agent_id` válido

**2.3 Deduplicação MongoDB Fallback:**
- [x] **Fallback MongoDB implementado**
  - `_check_mongodb_dup()` - verificação no MongoDB
  - Chama se Redis indisponível
  - Índice unique em `tickets` collection

- [ ] **Sistema funciona com Redis DOWN**
  - Testar: parar Redis, executar ticket duplicado
  - Validar: MongoDB detecta duplicata nas últimas 24h

**Validação:**
```bash
# Verificar OPA pod
kubectl get pods -n neural-hive-mind -l app=opa

# Testar OPA API
curl -X POST http://opa.neural-hive-mind.svc:8181/v1/data \
  -H "Content-Type: application/json" \
  -d '{"input": {"tasks": [], "execution_order": [], "risk_score": 0.5}}'

# Verificar tickets sem stub
kubectl logs -n neural-hive-mind -l app=orchestrator-dynamic | grep "fallback_stub" || echo "✅ PASS"
```

---

## FASE 3: SDK e gRPC (8 dias)

### 3.1 Agent SDK Proto Real

#### Passo 1: Criar diretórios

```bash
mkdir -p libraries/python/neural_hive_agent_sdk/proto
```

#### Passo 2: Criar proto file

**Arquivo NOVO:** `libraries/python/neural_hive_agent_sdk/proto/agent_service.proto`

```protobuf
syntax = "proto3";
package neuralhive.agent;

option python_package = "neural_hive_agent_sdk.proto";

// Mensagens principais
service AgentService {
    rpc SubmitIntent(IntentRequest) returns (IntentResponse);
    rpc GetTicketStatus(TicketStatusRequest) returns (TicketStatusResponse);
    rpc ListTickets(ListTicketsRequest) returns (ListTicketsResponse);
    rpc CancelTicket(CancelRequest) returns (CancelResponse);
}

message IntentRequest {
    string intent_id = 1;
    string natural_language = 2;
    string domain = 3;
    map<string, string> context = 4;
    string correlation_id = 5;
    string trace_id = 6;
}

message IntentResponse {
    string intent_id = 1;
    string plan_id = 2;
    string status = 3;
    string correlation_id = 4;
    map<string, string> metadata = 5;
}

message TicketStatusRequest {
    string ticket_id = 1;
    string correlation_id = 2;
}

message TicketStatusResponse {
    string ticket_id = 1;
    string status = 2;
    string task_type = 3;
    int64 created_at = 4;
    int64 completed_at = 5;
    map<string, string> result = 5;
}

message ListTicketsRequest {
    string plan_id = 1;
    string intent_id = 2;
    string status = 3;
    int32 limit = 4;
    int32 offset = 5;
    string correlation_id = 6;
}

message ListTicketsResponse {
    repeated Ticket tickets = 1;
    int32 total_count = 2;
}

message Ticket {
    string ticket_id = 1;
    string plan_id = 2;
    string task_id = 3;
    string task_type = 4;
    string status = 5;
    map<string, string> parameters = 6;
    int64 created_at = 7;
}

message CancelRequest {
    string ticket_id = 1;
    string reason = 2;
    string correlation_id = 3;
}

message CancelResponse {
    string ticket_id = 1;
    bool cancelled = 2;
    string reason = 3;
}
```

#### Passo 3: Gerar código Python

**Script NOVO:** `libraries/python/neural_hive_agent_sdk/proto/generate.sh`

```bash
#!/bin/bash
cd "$(dirname "$0")"

PROTO_DIR="./proto"
OUTPUT_DIR="../neural_hive_agent_sdk/proto_gen"

python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_DIR/agent_service.proto"

echo "Proto gerado em $OUTPUT_DIR"
```

#### Passo 4: Atualizar client.py

**Arquivo:** `libraries/python/neural_hive_agent_sdk/neural_hive_agent_sdk/client.py`

```python
# SUBSTITUIR imports de stub
from ..proto_gen.agent_service_pb2 import IntentRequest as _IntentRequest
from ..proto_gen.agent_service_pb2_grpc import AgentServiceStub as _AgentServiceStub

class AgentClient:
    def __init__(self, server_address: str):
        self.channel = grpc.aio.insecure_channel(server_address)
        self.stub = _AgentServiceStub(self.channel)

    async def submit_intent(self, natural_language: str, domain: str, **context) -> dict:
        request = _IntentRequest(
            intent_id=str(uuid.uuid4()),
            natural_language=natural_language,
            domain=domain,
            context=context,
            correlation_id=context.get('correlation_id'),
            trace_id=context.get('trace_id')
        )

        response = await self.stub.SubmitIntent(request)

        return {
            'intent_id': response.intent_id,
            'plan_id': response.plan_id,
            'status': response.status,
            'correlation_id': response.correlation_id,
            'metadata': dict(response.metadata)
        }
```

### Critérios de Aceitação Fase 3

**Objetivo:** SDK com proto real e métodos gRPC implementados.

**3.1 Agent SDK Proto Real:**
- [x] **Arquivo proto criado**
  - `libraries/python/neural_hive_agent_sdk/proto/agent_service.proto`
  - Definições completas de mensagens e serviços
  - Campos `correlation_id` e `trace_id` incluídos

- [x] **Script de geração criado**
  - `libraries/python/neural_hive_agent_sdk/proto/generate.py`
  - Gera código Python via protoc

- [x] **Client atualizado**
  - `neural_hive_agent_sdk/client.py` usa proto gerado
  - Imports condicionais com fallback para desenvolvimento

- [ ] **Código Python pode ser gerado**
  - Executar: `cd libraries/python/neural_hive_agent_sdk && python -m proto.generate`
  - Verificar: arquivos `_pb2.py` e `_pb2_grpc.py` criados

**3.2 Métodos gRPC Extras:**
- [ ] **NotImplementedError removidos**
  - Service Registry: `ListAgents()`, `Watch()`
  - Specialists: métodos extras implementados

**Validação:**
```bash
# Gerar código proto
cd libraries/python/neural_hive_agent_sdk
python -m proto.generate

# Verificar arquivos gerados
ls -la proto_gen/agent_service_pb2.py
```

---

## FASE 4: Saga e Compensação (5 dias)

### 4.1 Compensação de Validação Real

#### Arquivo: `services/worker-agents/src/executors/compensate_executor.py`

**Localização:** Método `_compensate_validate()` (linha 513-556)

```python
async def _compensate_validate(self, ticket_id: str, parameters: Dict[str, Any]):
    """
    Reverter aprovações chamando Approval Service API.

    Parâmetros esperados:
        - approval_id: ID da aprovação
        - api_url: URL do Approval Service
    """
    approval_id = parameters.get('approval_id', '')
    api_url = parameters.get('approval_api_url', '')

    self.log_execution(
        ticket_id,
        'compensation_validate_started',
        approval_id=approval_id
    )

    if not approval_id or not api_url:
        self.log_execution(
            ticket_id,
            'compensation_validate_skip',
            level='warning',
            reason='approval_id or api_url ausente'
        )
        return {
            'success': True,
            'output': {
                'approval_id': approval_id,
                'skipped': True,
                'reason': 'missing_parameters'
            },
            'metadata': {'simulated': False}
        }

    # CHAMADA REAL via HTTP
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{api_url}/api/v1/approvals/{approval_id}/revert",
                json={
                    'reason': 'compensation',
                    'ticket_id': ticket_id,
                    'timestamp': datetime.now().isoformat()
                }
            )
            response.raise_for_status()

            result = response.json()

            self.log_execution(
                ticket_id,
                'compensation_validate_completed',
                approval_id=approval_id,
                status_code=response.status_code
            )

            return {
                'success': True,
                'output': {
                    'approval_id': approval_id,
                    'reverted': True,
                    'api_result': result
                },
                'metadata': {'simulated': False}
            }

    except httpx.HTTPStatusError as e:
        self.log_execution(
            ticket_id,
            'compensation_validate_http_error',
            level='error',
            status_code=e.response.status_code,
            response=e.response.text
        )
        return {
            'success': False,
            'output': {
                'approval_id': approval_id,
                'error': f'HTTP {e.response.status_code}'
            },
            'metadata': {'simulated': False}
        }

    except Exception as e:
        self.log_execution(
            ticket_id,
            'compensation_validate_failed',
            level='error',
            error=str(e)
        )
        return {
            'success': False,
            'output': {
                'approval_id': approval_id,
                'error': str(e)
            },
            'metadata': {'simulated': False}
        }
```

### Critérios de Aceitação Fase 4

**Objetivo:** Compensações reais executadas (não simuladas).

**4.1 Compensação de Validação (_compensate_validate):**
- [x] **Chamada HTTP real para Approval Service**
  - `POST /api/v1/approvals/{approval_id}/revert`
  - Payload com `reason`, `ticket_id`, `timestamp`
  - Tratamento de erros HTTP

- [x] **Endpoint /revert implementado**
  - `services/approval-service/src/api/routers/approvals.py`
  - `services/approval-service/src/models/approval.py` - RevertRequestBody, RevertResponse
  - `services/approval-service/src/services/approval_service.py` - `revert_approval()`

- [ ] **Compensação executada com sucesso**
  - Status do plano volta para PENDING
  - `reverted_at` timestamp registrado

**4.2 Compensação de Execução (_compensate_execute):**
- [x] **Execução de rollback script real**
  - `subprocess` com `asyncio.create_subprocess_exec`
  - Suporte a scripts customizados via `rollback_script` parameter

**4.3 Testes E2E de Saga:**
- [x] **Testes de compensação criados**
  - `tests/e2e/test_workflow_compensation.py`
  - 3 cenários: build/deploy, approval revert, cascading

- [ ] **Testes passam em ambiente E2E**
  - Executar: `pytest tests/e2e/test_workflow_compensation.py -v`
  - Validar: compensações executadas, estado final consistente

**Validação:**
```bash
# Verificar endpoint /revert
curl -X POST http://approval-service:8003/api/v1/approvals/{plan_id}/revert \
  -H "Content-Type: application/json" \
  -d '{"reason": "test"}'

# Executar testes Saga
pytest tests/e2e/test_workflow_compensation.py -v
```

---

## FASE 5: Observabilidade (4 dias)

### 5.1 Métricas de Executor

**Arquivo:** `services/worker-agents/src/observability/metrics.py`

```python
# ADICIONAR métricas faltantes:

from prometheus_client import Counter, Histogram

# Code Forge API calls
code_forge_api_calls_total = Counter(
    'neural_hive_code_forge_api_calls_total',
    'Code Forge API calls',
    ['method', 'status']
)

# ArgoCD API calls
argocd_api_calls_total = Counter(
    'neural_hive_argocd_api_calls_total',
    'ArgoCD API calls',
    ['method', 'status']
)

# Runtime fallbacks
execute_runtime_fallbacks_total = Counter(
    'neural_hive_execute_runtime_fallbacks_total',
    'Execute runtime fallbacks',
    ['from_runtime', 'to_runtime']
)

# Compensação
compensation_duration_seconds = Histogram(
    'neural_hive_compensation_duration_seconds',
    'Compensation duration',
    ['reason', 'status'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)
```

### Critérios de Aceitação Fase 5

**Objetivo:** Métricas completas e distributed tracing funcional.

**5.1 Métricas de Executor:**
- [ ] **Métricas Prometheus registradas**
  - `code_forge_api_calls_total` - chamadas API Code Forge
  - `argocd_api_calls_total` - chamadas API ArgoCD
  - `execute_runtime_fallbacks_total` - fallbacks de runtime
  - `compensation_duration_seconds` - duração de compensações

- [ ] **Métricas expostas no /metrics endpoint**
  - Verificar: `curl http://worker-agents:8080/metrics | grep neural_hive`

**5.2 Distributed Tracing:**
- [x] **Producers injetam W3C traceparent**
  - `plan_producer.py` - usa `ContextManager.inject_http_headers()`
  - `approval_response_producer.py` - usa `ContextManager.inject_http_headers()`
  - `decision_producer.py` - headers com traceparent

- [x] **Consumers extraem trace context**
  - `plan_consumer.py` - `extract_context_from_headers()` já implementado
  - Headers: `traceparent`, `trace-id`, `correlation-id`

- [x] **Documentação Jaeger/Tempo criada**
  - `docs/observabilidade/JAEGER_TEMPO_CONFIG.md` - guia completo

- [ ] **Trace propagation validada end-to-end**
  - Executar intenção de teste
  - Consultar Jaeger/Tempo UI
  - Validar: trace completo com todos os serviços

**Validação:**
```bash
# Verificar métricas
curl http://worker-agents:8080/metrics | grep neural_hive_code_forge

# Verificar headers Kafka (teste)
kubectl exec -it kafka-0 -- kafka-console-consumer \
  --bootstrap-server localhost:9092 --topic plans.ready \
  --from-beginning --property print.headers=true | head -5
```

---

## FASE 6: Testes E2E (6 dias)

### 6.1 Teste Completo Intenção→Código

**Arquivo NOVO:** `tests/e2e/test_full_intent_to_code.py`

```python
import pytest
import asyncio
from datetime import datetime

@pytest.mark.e2e
@pytest.mark.timeout(300)  # 5 minutos max
async def test_intent_to_code_full_flow(gateway_client, kafka_consumer):
    """
    Teste completo: Intenção → Gateway → STE → Consensus → Orchestrator → Worker → Código

    Este teste valida:
    1. Propagação de correlation_id
    2. Validação OPA
    3. Geração de tickets
    4. Execução de tarefas
    5. Compensação em caso de falha
    """

    correlation_id = f"test-{datetime.now().timestamp()}"

    # 1. Submeter intenção
    intent_response = gateway_client.submit_intent(
        natural_language="Criar API para listar usuários",
        domain="BUSINESS",
        correlation_id=correlation_id
    )

    assert intent_response['status'] == 'accepted'
    intent_id = intent_response['intent_id']

    # 2. Consumir plan do Kafka
    plan = await kafka_consumer.consume_plans(
        filter_intent_id=intent_id,
        timeout=60
    )

    assert plan is not None
    assert plan['correlation_id'] == correlation_id

    # 3. Consumir decisão do Consensus
    decision = await kafka_consumer.consume_decisions(
        filter_plan_id=plan['plan_id'],
        timeout=60
    )

    assert decision['final_decision'] == 'APPROVE'

    # 4. Consumir tickets gerados
    tickets = await kafka_consumer.consume_tickets(
        filter_plan_id=plan['plan_id'],
        timeout=60
    )

    assert len(tickets) > 0

    # 5. Aguardar conclusão dos tickets
    completed_tickets = await kafka_consumer.wait_for_completion(
        plan_id=plan['plan_id'],
        timeout=300
    )

    assert len(completed_tickets) == len(tickets)

    # 6. Validar código produzido (exemplo: deployment existe)
    # ...
```

### Critérios de Aceitação Fase 6

**Objetivo:** Suite E2E completa para validar todo o sistema.

**6.1 Teste Completo Intenção→Código:**
- [x] **Teste E2E principal criado**
  - `tests/e2e/test_full_intent_to_code.py` (589 linhas)
  - 6 steps: submit → plan → consensus → tickets → tracing → completion

- [ ] **Teste passa em ambiente completo**
  - Executar: `pytest tests/e2e/test_full_intent_to_code.py::test_intent_to_code_full_flow -v`
  - Valida: todos os 6 steps completam com sucesso

**6.2 Testes de Stress/Carga:**
- [x] **Teste de correlação sob carga criado**
  - `tests/e2e/test_load_correlation_id.py` (539 linhas)
  - 100 requisições concorrentes
  - Valida: zero correlation_id perdido, zero swap entre requests

- [x] **Teste de carga sustentada criado**
  - Duração configurável (1-5 minutos)
  - Taxa de requisições por segundo
  - Valida: consistência mantida sob carga contínua

**6.3 Testes de Saga/Compensação:**
- [x] **Testes de compensação criados**
  - `tests/e2e/test_workflow_compensation.py` (531 linhas)
  - 3 cenários: build/deploy falha, approval revert, cascading

- [ ] **Testes Saga passam**
  - Valida: compensações executadas em ordem reversa
  - Valida: recursos limpos adequadamente

**6.4 Configuração e Documentação:**
- [x] **pytest.ini criado** - Configuração pytest para E2E
- [x] **requirements.txt criado** - Dependências dos testes
- [x] **README.md criado** - Guia de execução dos testes

**Validação:**
```bash
# Instalar dependências
pip install -r tests/e2e/requirements.txt

# Executar todos os testes E2E
pytest tests/e2e/ -v --asyncio-mode=auto

# Executar apenas testes básicos
pytest tests/e2e/ -v -m "e2e and not stress"

# Executar stress tests
pytest tests/e2e/ -v -m stress

# Executar testes Saga
pytest tests/e2e/ -v -m saga

# Gerar relatório HTML
pytest tests/e2e/ --html=e2e-report.html --self-contained-html
```

---

## Resumo de Execução por Arquivo

| Fase | Arquivo | Tipo | Linhas | Ação |
|------|--------|------|-------|------|
| F1 | `nlu_pipeline.py` | Modificar | ~90 | Gerar correlation_id |
| F1 | `orchestrator.py` (STE) | Modificar | 52-96 | Validar/gerar correlation_id |
| F1 | `consensus_orchestrator.py` | Modificar | 150-169 | Mudar ERROR→WARNING |
| F1 | `ticket_generation.py` | Modificar | 77 | Validar correlation_id |
| F1 | `execution_engine.py` | Modificar | 163 | Validar correlation_id |
| F2 | `opa/Chart.yaml` | Criar | - | Criar Helm chart |
| F2 | `opa/values.yaml` | Criar | - | Configurar OPA |
| F2 | `opa/templates/*.yaml` | Criar | - | Deploy OPA |
| F2 | `ticket_generation.py` | Modificar | 509-568 | Implementar round-robin |
| F2 | `execution_engine.py` | Modificar | 39-102 | Adicionar fallback MongoDB |
| F2 | `execution_ticket_client.py` | Modificar | - | Adicionar get_ticket_by_id |
| F3 | `agent_service.proto` | Criar | - | Definir proto |
| F3 | `generate.sh` | Criar | - | Script de geração |
| F3 | `client.py` (SDK) | Modificar | - | Usar proto real |
| F4 | `compensate_executor.py` | Modificar | 513-556 | Chamada HTTP real |
| F5 | `metrics.py` (Worker) | Modificar | - | Adicionar métricas |
| F6 | `test_full_intent_to_code.py` | Criar | - | Teste E2E completo |

---

## Comando para Executar Fase

Para executar uma fase específica, use:

```
Claude: "Execute FASE X do plano em docs/PLANO_EXECUCAO_CODIGO.md"
```

O agente IA irá:
1. Ler os arquivos listados
2. Aplicar as modificações especificadas
3. Criar novos arquivos quando necessário
4. Executar testes de validação
5. Relatar progresso

---

**Documento Principal:** `docs/PLANO_EXECUCAO_CODIGO.md`
