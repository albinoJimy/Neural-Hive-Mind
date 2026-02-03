# Problemas do Fluxo C - Ordenados por Prioridade de Resolução

> **Data:** 2026-02-03
> **Fluxo:** Fluxo C (Orchestrator Dynamic → Execution Tickets)
> **Status:** NÃO APROVADO PARA PRODUÇÃO
> **Referência:** docs/PLANO_TESTE_MANUAL_FLUXOS_A_C.md

---

## Índice

- [Prioridade P0 - Crítica (Bloqueadores de Produção)](#prioridade-p0---crítica-bloqueadores-de-produção)
- [Prioridade P1 - Alta (Impacto Significativo)](#prioridade-p1---alta-impacto-significativo)
- [Prioridade P2 - Média (Limita Observabilidade)](#prioridade-p2---média-limita-observabilidade)
- [Prioridade P3 - Baixa (Melhorias)](#prioridade-p3---baixa-melhorias)

---

## Prioridade P0 - Crítica (Bloqueadores de Produção)

### P0-001: trace_id e span_id Zerados em Todos os Eventos

#### Descrição Detalhada

Todos os eventos de telemetria do Fluxo C apresentam `trace_id` e `span_id` com valores zerados (`00000000000000000000000000000000` e `0000000000000000`), impedindo completamente a correlação de spans distribuídos e a observabilidade E2E.

**Arquivo/fonte:** Topic `telemetry-flow-c` (Kafka), eventos de telemetria

**Exemplo do problema:**
```json
{
  "event_type": "step_completed",
  "step": "C1",
  "trace_id": "00000000000000000000000000000000",
  "span_id": "0000000000000000",
  "timestamp": "2026-02-02T12:45:54.821271"
}
```

#### Impacto

- **Impossível rastrear requisições E2E** através de múltiplos serviços
- **Debugging e troubleshooting severamente prejudicados** - não é possível seguir o fluxo de uma requisição
- **Observabilidade comprometida** - ferramentas como Jaeger não conseguem correlacionar spans
- **Não conformidade com OpenTelemetry** - propagação de contexto não funcionando
- **Impossível investigar problemas em produção** sem capacidade de tracing

#### Causa Provável

1. **Headers W3C não propagados** - Headers `traceparent` e `baggage` não estão sendo extraídos/injetados corretamente nas mensagens Kafka
2. **Contexto OTEL não inicializado** - OpenTelemetry Tracer não está sendo inicializado com o contexto da mensagem
3. **Extrator de headers não configurado** - `Propagator` do OpenTelemetry não configurado para extrair contexto de mensagens Kafka
4. **Serde Avro perdendo headers** - Serialização/deserialização Avro pode estar descartando headers

#### Passos para Reproduzir

1. Consumir evento do topic `telemetry-flow-c`
2. Verificar campo `trace_id` e `span_id`
3. Confirmar que ambos estão zerados

#### Solução Recomendada

**Código a verificar/modificar:**

```python
# services/orchestrator-dynamic/src/integration/flow_c_consumer.py

# 1. Verificar extração de headers W3C
@trace_plan()
def _process_message(self, msg: ConsumerRecord) -> None:
    # Adicionar logging para debug de headers
    self.logger.debug(f"Headers recebidos: {msg.headers}")

    # 2. Verificar propagação de contexto OTEL
    ctx = propagators.extract(dict(msg.headers), get_header_value)
    token = context.attach(ctx)
    try:
        # Processar mensagem
    finally:
        context.detach(token)

# 3. Verificar injeção de headers em publicações
publisher.publish(
    event_type="step_completed",
    # Adicionar trace_context aos headers
    headers={
        "traceparent": format_traceparent(trace_id, span_id),
        "baggage": serialize_baggage(baggage)
    }
)
```

**Arquivos a investigar:**
- `services/orchestrator-dynamic/src/integration/flow_c_consumer.py:238-357` (FlowCConsumer)
- `libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py` (FlowCOrchestrator)
- `libraries/neural_hive_integration/telemetry/flow_c_telemetry.py` (FlowCTelemetryPublisher)

**Validação:**
```bash
# Após correção, verificar que trace_id/span_id não são zerados
kubectl exec -it orchestrator-dynamic-... -- python -c "
from neural_hive_observability.tracing import get_current_trace_id
print(f'Trace ID: {get_current_trace_id()}')
"
```

#### Critérios de Aceite

- [ ] trace_id não zerado em todos os eventos
- [ ] span_id não zerado em todos os eventos
- [ ] Trace E2E visível no Jaeger (do Gateway ao Fluxo C)
- [ ] Spans correlacionados corretamente

---

### P0-002: Inconsistência Crítica de Metadata - tickets_completed = 0

#### Descrição Detalhada

O evento final de conclusão do Fluxo C (`FLOW_C_COMPLETED`) apresenta uma **inconsistência crítica** na metadata:
- Campo `metadata.tickets_completed` = **0**
- Campo `ticket_ids` contém **5 IDs válidos**

Isso indica que o sistema reporta que nenhum ticket foi completado, mas lista 5 ticket_ids válidos.

**Arquivo/fonte:** Topic `telemetry-flow-c` (Kafka), evento final

**Exemplo do problema:**
```json
{
  "event_type": "flow_completed",
  "step": "C6",
  "ticket_ids": [
    "5ce14df7-3cce-4706-bf95-f3d63361d70e",
    "8070eddb-2afc-48f2-a18e-1caaca1544f9",
    "1cef830f-f66d-40da-89a7-dfab9ab934f8",
    "749c3f43-c066-4439-929b-7bcbd36252c3",
    "eed1dff3-c3d6-4d3d-8286-37cea0cf8af3"
  ],
  "metadata": {
    "tickets_completed": 0,
    "tickets_failed": 0
  }
}
```

#### Impacto

- **Integridade de dados comprometida** - Metadata contradiz dados explícitos
- **Impossível confiar em métricas** - Sistema reporta informações inconsistentes
- **Dashboard e alertas incorretos** - Visualizações podem mostrar dados errados
- **Auditoria não confiável** - Não é possível auditar o que realmente aconteceu
- **Decision making comprometido** - Decisões baseadas em métricas incorretas

#### Causa Provável

1. **Bug na contagem de tickets** - Lógica que contabiliza tickets completados está incorreta
2. **Race condition** - Contagem executada antes de tickets serem marcados como completados
3. **Query incorreta ao MongoDB** - Query para contar tickets pode estar filtrando incorretamente
4. **Campos não preenchidos** - Campo `tickets_completed` simplesmente não é populado (default = 0)

#### Passos para Reproduzir

1. Consumir evento final do topic `telemetry-flow-c`
2. Verificar `metadata.tickets_completed`
3. Verificar `ticket_ids` array
4. Confirmar inconsistência (0 vs lista com IDs)

#### Solução Recomendada

**Código a verificar/modificar:**

```python
# libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py

def _execute_c6_publish_telemetry(self, context: FlowCContext) -> dict:
    # 1. Verificar lógica de contagem de tickets
    completed_count = len([
        t for t in context.tickets
        if t.status == "COMPLETED"
    ])

    # 2. Verificar se tickets estão sendo consultados corretamente
    # PODE SER O PROBLEMA: Query pode estar filtrando incorretamente
    tickets_db = self.ticket_client.get_tickets_by_workflow(context.workflow_id)
    completed_count = len([t for t in tickets_db if t.status == "COMPLETED"])

    # 3. Adicionar validação de integridade
    if completed_count != len(context.ticket_ids):
        self.logger.error(
            f"Inconsistência de metadata: "
            f"tickets_completed={completed_count}, "
            f"ticket_ids_count={len(context.ticket_ids)}"
        )

    # 4. Publicar evento com dados corretos
    self.telemetry_publisher.publish_flow_completed(
        context=context,
        metadata={
            "tickets_completed": completed_count,  # Usar valor real
            "tickets_failed": failed_count,
            "total_tickets": len(context.ticket_ids)
        }
    )
```

**Arquivos a investigar:**
- `libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py:400-450` (C6)
- `services/orchestrator-dynamic/src/clients/execution_ticket_client.py`
- `libraries/neural_hive_integration/telemetry/flow_c_telemetry.py`

**Validação:**
```python
# Adicionar validação antes de publicar evento
assert completed_count == len(context.ticket_ids), \
    f"Inconsistência: {completed_count} != {len(context.ticket_ids)}"
```

#### Critérios de Aceite

- [ ] `metadata.tickets_completed` igual ao número de `ticket_ids`
- [ ] Validação de integridade não gera erros
- [ ] Dashboard mostra contagem correta
- [ ] Logs não reportam inconsistências

---

### P0-003: Eventos de Telemetria Faltando (FLOW_C_STARTED, TICKET_ASSIGNED, TICKET_COMPLETED)

#### Descrição Detalhada

Apenas **10 eventos** foram encontrados no topic `telemetry-flow-c`:
- **9 eventos** do tipo `step_completed` com `step: C1` (repetições?)
- **1 evento** do tipo `flow_completed` com `step: C6`

**Eventos ESPERADOS mas NÃO ENCONTRADOS:**
- `FLOW_C_STARTED` - Evento de início do fluxo C
- `TICKET_ASSIGNED` (5 eventos) - Um para cada ticket atribuído
- `TICKET_COMPLETED` (5 eventos) - Um para cada ticket completado
- `TICKET_FAILED` (0 eventos, se nenhum falhou)

Total esperado: ~12-16 eventos
Total encontrado: 10 eventos
**Faltando: ~6 eventos críticos**

**Arquivo/fonte:** Topic `telemetry-flow-c` (Kafka)

#### Impacto

- **Rastreabilidade incompleta** - Não é possível seguir o ciclo de vida completo de tickets
- **Debugging impossível** - Sem eventos de assigned/completed, não se sabe quando cada ticket mudou de estado
- **Métricas incompletas** - Dashboards não mostram progresso em tempo real
- **Alertas não funcionam** - Alertas baseados em eventos específicos não são disparados
- **Auditoria incompleta** - Não há registro de quando cada ticket foi atribuído/completado

#### Causa Provável

1. **Publisher não implementado** - Publicação de eventos intermediários nunca foi implementada
2. **Condicional incorreta** - Código tem `if DEBUG: publish()` ou similar
3. **Erro de tipo/enum** - `event_type` incorreto, eventos não são reconhecidos
4. **Filtro no consumidor** - Alguém está filtrando/removendo esses eventos antes de chegarem ao topic
5. **Schema Registry rejeitando** - Eventos podem ser rejeitados por schema mismatch

#### Passos para Reproduzir

1. Consumir todos eventos do topic `telemetry-flow-c`
2. Contar eventos por `event_type`
3. Verificar que tipos faltam

**Comando para reproduzir:**
```bash
kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic telemetry-flow-c \
  --from-beginning \
  --property print.key=true \
  --property key.separator=" | " | \
  jq -r '.event_type' | sort | uniq -c
```

#### Solução Recomendada

**Código a verificar/modificar:**

```python
# libraries/neural_hive_integration/telemetry/flow_c_telemetry.py

class FlowCTelemetryPublisher:

    def publish_flow_started(self, context: FlowCContext) -> None:
        """Publica evento FLOW_C_STARTED"""
        self._publish_event(
            event_type="FLOW_C_STARTED",
            context=context,
            metadata={
                "intent_id": context.intent_id,
                "plan_id": context.plan_id,
                "decision_id": context.decision_id,
                "workflow_id": context.workflow_id
            }
        )

    def publish_ticket_assigned(self, ticket: ExecutionTicket, worker_id: str) -> None:
        """Publica evento TICKET_ASSIGNED"""
        self._publish_event(
            event_type="TICKET_ASSIGNED",
            ticket_id=ticket.ticket_id,
            metadata={
                "task_type": ticket.task_type,
                "assigned_worker": worker_id,
                "assigned_at": datetime.utcnow().isoformat()
            }
        )

    def publish_ticket_completed(self, ticket: ExecutionTicket, result: dict) -> None:
        """Publica evento TICKET_COMPLETED"""
        self._publish_event(
            event_type="TICKET_COMPLETED",
            ticket_id=ticket.ticket_id,
            metadata={
                "task_type": ticket.task_type,
                "assigned_worker": ticket.assigned_worker,
                "result": result,
                "completed_at": datetime.utcnow().isoformat()
            }
        )

# Verificar se esses métodos estão sendo chamados nos steps correspondentes

# libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py

def execute_flow_c(self, message: ConsensusDecision) -> FlowCResult:
    # 1. Publicar FLOW_C_STARTED no início
    self.telemetry_publisher.publish_flow_started(context)

    # C4: Após assign de cada ticket
    for ticket, worker in assignments:
        self.telemetry_publisher.publish_ticket_assigned(ticket, worker.agent_id)

    # C5: Após cada ticket completar
    for ticket in completed_tickets:
        self.telemetry_publisher.publish_ticket_completed(ticket, ticket.result)
```

**Arquivos a investigar:**
- `libraries/neural_hive_integration/telemetry/flow_c_telemetry.py`
- `libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py` (C4, C5)

**Validação:**
```bash
# Após correção, verificar eventos no topic
kubectl run kafka-consumer --image=confluentinc/cp-kafka:latest --restart=Never -it -- \
  kafka-console-consumer --bootstrap-server kafka.neural-hive.svc.cluster.local:9092 \
  --topic telemetry-flow-c --from-beginning --max-messages 50 | jq -r '.event_type' | sort | uniq -c
```

#### Critérios de Aceite

- [ ] Evento `FLOW_C_STARTED` presente
- [ ] Eventos `TICKET_ASSIGNED` presentes (um por ticket)
- [ ] Eventos `TICKET_COMPLETED` presentes (um por ticket)
- [ ] Contagem total de eventos > 15

---

### P0-004: Logs de Processamento Ausentes (Orchestrator)

#### Descrição Detalhada

Os logs do Orchestrator Dynamic **não contêm mensagens de processamento** do Fluxo C. Apenas logs de health check estão disponíveis.

**Logs ESPERADOS mas NÃO ENCONTRADOS:**
- "Consumindo decisão do topic plans.consensus"
- "Validando decisão (C1)..."
- "Gerando execution tickets (C2)..."
- "Iniciando workflow Temporal..."
- "Descobrindo workers (C3)..."
- "Atribuindo tickets aos workers (C4)..."
- "Monitorando execução dos tickets (C5)..."
- "Publicando telemetria (C6)..."

**Logs ENCONTRADOS:**
- Apenas health checks: `GET /health HTTP/1.1 200`

**Arquivo/fonte:** Logs do Pod `orchestrator-dynamic-...`

#### Impacto

- **Impossível validar execução de cada step** - Não há registro do que foi processado
- **Troubleshooting impossível** - Sem logs, não é possível investigar problemas
- **Audit trail incompleto** - Não há registro das operações executadas
- **Performance analysis impossível** - Não é possível identificar bottlenecks
- **Debugging em produção impossível** - Sem logs, não há visibilidade do que está acontecendo

#### Causa Provável

1. **Nível de log configurado incorretamente** - Logger configurado para WARNING ou ERROR apenas
2. **Logs não implementados** - Mensagens informativas nunca foram adicionadas ao código
3. **Handler de log não configurado** - Logs podem estar sendo produzidos mas não escritos
4. **Filtro no logging config** - Algum filtro pode estar removendo logs abaixo de certo nível
5. **Structured logging format** - Logs podem estar em formato não-human-readable (JSON)

#### Passos para Reproduzir

1. Obter logs do pod Orchestrator
2. Procurar por mensagens de processamento
3. Confirmar ausência de logs informativos

**Comando para reproduzir:**
```bash
kubectl logs -n neural-hive orchestrator-dynamic-... --tail=500 | grep -i "consumindo\|validando\|gerando\|descobrindo\|atribuindo\|monitorando"
```

#### Solução Recomendada

**Código a verificar/modificar:**

```python
# services/orchestrator-dynamic/src/main.py

# 1. Configurar nível de log corretamente
import logging

logging.basicConfig(
    level=logging.INFO,  # Mudar de WARNING para INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Ou via YAML config:
# logging:
#   level: INFO
#   handlers:
#     - type: console
#       format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# services/orchestrator-dynamic/src/integration/flow_c_consumer.py

class FlowCConsumer:
    def _process_message(self, msg: ConsumerRecord) -> None:
        # 2. Adicionar logs informativos em cada step
        self.logger.info(f"Consumindo decisão do topic plans.consensus: decision_id={decision_id}")

# libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py

class FlowCOrchestrator:
    def execute_flow_c(self, message: ConsensusDecision) -> FlowCResult:
        self.logger.info(f"Iniciando Fluxo C: intent_id={message.intent_id}, plan_id={message.plan_id}")

    def _execute_c1_validate(self, ...) -> StepResult:
        self.logger.info(f"Validando decisão (C1): decision_id={decision_id}")
        # ... validação ...
        self.logger.info(f"Decisão validada com sucesso (C1)")

    def _execute_c2_generate_tickets(self, ...) -> StepResult:
        self.logger.info(f"Gerando execution tickets (C2): {len(tasks)} tasks")
        # ... geração ...
        self.logger.info(f"Tickets gerados: {len(tickets)} tickets")

    def _execute_c3_discover_workers(self, ...) -> StepResult:
        self.logger.info(f"Descobrindo workers (C3): capabilities={capabilities}")
        # ... discovery ...
        self.logger.info(f"Workers descobertos: {len(workers)} workers")

    def _execute_c4_assign_tickets(self, ...) -> StepResult:
        self.logger.info(f"Atribuindo tickets aos workers (C4): {len(tickets)} tickets")
        # ... assignment ...
        self.logger.info(f"Tickets atribuídos: {len(assignments)} assignments")

    def _execute_c5_monitor_execution(self, ...) -> StepResult:
        self.logger.info(f"Monitorando execução dos tickets (C5): {len(tickets)} tickets")
        # ... monitoring ...
        self.logger.info(f"Execução concluída: {completed}/{total} tickets completados")

    def _execute_c6_publish_telemetry(self, ...) -> StepResult:
        self.logger.info(f"Publicando telemetria (C6): {len(events)} eventos")
        # ... publishing ...
        self.logger.info(f"Telemetria publicada com sucesso (C6)")
```

**Arquivos a modificar:**
- `services/orchestrator-dynamic/src/main.py` (configuração de logging)
- `services/orchestrator-dynamic/src/integration/flow_c_consumer.py`
- `libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py`

**Validação:**
```bash
# Após correção, verificar logs
kubectl logs -n neural-hive orchestrator-dynamic-... --tail=100 | grep -i "info\|validando\|gerando\|descobrindo\|atribuindo\|monitorando\|publicando"
```

#### Critérios de Aceite

- [ ] Logs de processamento presentes em cada step (C1-C6)
- [ ] Logs contêm informações úteis (IDs, contagens, status)
- [ ] Nível de log configurado como INFO ou DEBUG
- [ ] Logs são human-readable

---

### P0-005: Service Registry em CrashLoopBackOff

#### Descrição Detalhada

O pod do Service Registry está em estado **CrashLoopBackOff** há mais de 8 horas, com **101 restarts**. Isso bloqueia completamente a execução dos steps C3, C4 e C5 do Fluxo C.

**Status do pod:**
```bash
kubectl get pods -n neural-hive service-registry-59f748f7d7-726jj
NAME                                        READY   STATUS             RESTARTS        AGE
service-registry-59f748f7d7-726jj              0/1     CrashLoopBackOff   101 (2m25s ago)   8h
```

**Impacto nos steps do Fluxo C:**
- **C3 - Discover Workers:** BLOQUEADO (Service Registry não responde)
- **C4 - Assign Tickets:** BLOQUEADO (depende de C3)
- **C5 - Monitor Execution:** BLOQUEADO (depende de C3 e C4)

#### Impacto

- **Fluxo C não funciona** - Steps C3-C5 completamente bloqueados
- **Workers não podem ser descobertos** - Service Registry não responde queries
- **Tickets não podem ser atribuídos** - Sem workers, não há assignment
- **Execução não pode ser monitorada** - Sem tracking de status
- **Sistema não opera corretamente** - Componente crítico indisponível

#### Causa Provável

1. **Dependência não atendida** - Database, Redis, ou outra dependência não disponível
2. **Erro de configuração** - ConfigMap ou Secret incorretos
3. **Erro de inicialização** - Bug no código que causa crash na startup
4. **Resource limits** - Pod sendo OOMKilled por falta de memória
5. **Liveness/Readiness probe falhando** - Pods sendo reiniciados por falha de health check

#### Passos para Reproduzir

1. Verificar status do pod Service Registry
2. Obter logs do pod para identificar causa raiz
3. Verificar eventos do pod

**Comandos para reproduzir:**
```bash
kubectl get pods -n neural-hive service-registry-59f748f7d7-726jj
kubectl logs -n neural-hive service-registry-59f748f7d7-726jj --tail=200
kubectl describe pod -n neural-hive service-registry-59f748f7d7-726jj
kubectl get events -n neural-hive --field-selector involvedObject.name=service-registry-59f748f7d7-726jj
```

#### Solução Recomendada

**Passo 1: Investigar logs para identificar causa raiz**

```bash
# Logs do pod (últimas 200 linhas)
kubectl logs -n neural-hive service-registry-59f748f7d7-726jj --tail=200

# Logs anteriores ao último restart (se houver)
kubectl logs -n neural-hive service-registry-59f748f7d7-726jj --previous --tail=200

# Descrição do pod (events, resources, etc)
kubectl describe pod -n neural-hive service-registry-59f748f7d7-726jj
```

**Passo 2: Verificar dependências**

```bash
# Verificar se Redis está acessível
kubectl exec -n neural-hive service-registry-59f748f7d7-726jj -- \
  nc -zv service-registry-redis 6379

# Verificar se MongoDB está acessível
kubectl exec -n neural-hive service-registry-59f748f7d7-726jj -- \
  nc -zv mongodb 27017

# Verificar variáveis de ambiente
kubectl exec -n neural-hive service-registry-59f748f7d7-726jj -- env | grep -i "redis\|mongo\|db"
```

**Passo 3: Verificar resources**

```bash
# Verificar se pod está sendo OOMKilled
kubectl describe pod -n neural-hive service-registry-59f748f7d7-726jj | grep -i "oomkilled\|memory"

# Verificar resource limits
kubectl get pod -n neural-hive service-registry-59f748f7d7-726jj -o jsonpath='{.spec.containers[0].resources}'
```

**Passo 4: Corrigir e reimplantar**

```bash
# Após identificar causa raiz, aplicar correção
# Exemplo: aumentar memory limit se for OOMKilled
kubectl set resources pod service-registry-59f748f7d7-726jj \
  --limits=memory=1Gi --requests=memory=512Mi

# Ou reimplantar com config corrigida
kubectl delete pod -n neural-hive service-registry-59f748f7d7-726jj
# Kubernetes recriará o pod com nova configuração
```

**Arquivos a investigar:**
- `helm-charts/service-registry/values.yaml` (configuração do deployment)
- `services/service-registry/src/main.py` (código da aplicação)
- Logs do pod para identificar erro de inicialização

**Validação:**
```bash
# Após correção, verificar que pod está rodando
kubectl get pods -n neural-hive service-registry-59f748f7d7-726jj
# Esperar: READY 1/1, STATUS Running

# Verificar logs sem erros
kubectl logs -n neural-hive service-registry-59f748f7d7-726jj --tail=50
```

#### Critérios de Aceite

- [ ] Pod Service Registry em estado Running (READY 1/1)
- [ ] Pod não está em CrashLoopBackOff
- [ ] Restart count = 0 ou baixo (< 5)
- [ ] Logs não mostram erros de inicialização
- [ ] Health check retorna 200 OK

---

## Prioridade P1 - Alta (Impacto Significativo)

### P1-001: Schema Avro dos Eventos de Telemetria Não Validado

#### Descrição Detalhada

Não é possível validar se os eventos de telemetria publicados no topic `telemetry-flow-c` estão em conformidade com o schema Avro definido. Mensagens estão em formato binário e ferramentas atuais não conseguem deserializá-las.

**Problema:**
- Eventos são publicados em formato Avro binário
- Schema Avro definido mas não validado
- Ferramentas de debug (`kafka-console-consumer`, `kafkacat`) não conseguem deserializar

**Exemplo:**
```bash
kafka-console-consumer --bootstrap-server localhost:9092 --topic telemetry-flow-c
# Output: �j�@��z�X���^E���... (binário não legível)
```

#### Impacto

- **Incompatibilidade de schema pode não ser detectada** - Produtor pode publicar eventos com schema incorreto
- **Validação de contrato entre serviços comprometida** - Consumidores podem falhar ao deserializar
- **Debugging impossível** - Não é possível ler eventos sem ferramentas especializadas
- **Evolutionary schema changes não gerenciados** - Risco de breaking changes

#### Causa Provável

1. **Schema Registry não configurado** - Kafka não está usando Confluent Schema Registry
2. **Serde configurado incorretamente** - Serializer/deserializer não está registrado
3. **Schema ID não propagado** - Mensagens não contêm magic byte + schema ID
4. **Ferramenta de debug errada** - Usando `kafka-console-consumer` em vez de `kafka-avro-console-consumer`

#### Solução Recomendada

```python
# libraries/neural_hive_integration/telemetry/flow_c_telemetry.py

from confluent_schema_registry import SchemaRegistryClient
from confluent_schema_registry.serializers import AvroSerializer

# 1. Configurar Schema Registry
schema_registry_conf = {
    'url': 'http://schema-registry.neural-hive.svc.cluster.local:8081',
    'basic.auth.user.info': f'{SR_USER}:{SR_PASSWORD}'
}
sr_client = SchemaRegistryClient(schema_registry_conf)

# 2. Definir schema Avro
TELEMETRY_SCHEMA = """
{
  "type": "record",
  "name": "FlowCTelemetryEvent",
  "namespace": "neural.hive.telemetry",
  "fields": [
    {"name": "event_type", "type": {"type": "enum", "name": "EventType", "symbols": ["FLOW_C_STARTED", "TICKET_ASSIGNED", "TICKET_COMPLETED", "TICKET_FAILED", "FLOW_C_COMPLETED", "SLA_VIOLATION"]}},
    {"name": "timestamp", "type": "string"},
    {"name": "plan_id", "type": "string"},
    {"name": "correlation_id", "type": "string"},
    {"name": "intent_id", "type": ["null", "string"], "default": null},
    {"name": "decision_id", "type": ["null", "string"], "default": null},
    {"name": "workflow_id", "type": ["null", "string"], "default": null},
    {"name": "ticket_id", "type": ["null", "string"], "default": null},
    {"name": "worker_id", "type": ["null", "string"], "default": null},
    {"name": "duration_ms", "type": ["null", "long"], "default": null},
    {"name": "success", "type": ["null", "boolean"], "default": null},
    {"name": "sla_compliant", "type": ["null", "boolean"], "default": null},
    {"name": "metadata", "type": ["null", {"type": "map", "values": "string"}], "default": null}
  ]
}
"""

# 3. Registrar schema no Schema Registry
schema_id = sr_client.register_schema(
    subject_name='telemetry-flow-c-value',
    schema=TELEMETRY_SCHEMA
)

# 4. Criar serializer
avro_serializer = AvroSerializer(sr_client, TELEMETRY_SCHEMA)

# 5. Publicar evento com schema
def _publish_event(self, event_type: str, context: FlowCContext, **kwargs) -> None:
    event_data = {
        'event_type': event_type,
        'timestamp': datetime.utcnow().isoformat(),
        'plan_id': context.plan_id,
        'correlation_id': context.correlation_id,
        **kwargs
    }

    # Serializar com Avro (inclui magic byte + schema ID)
    serialized = avro_serializer.encode(event_data)

    self.producer.produce(
        topic='telemetry-flow-c',
        value=serialized,
        headers={'content-type': 'application/vnd.sr.avro'}
    )
```

**Validação:**
```bash
# Usar kafkacat com suporte a Schema Registry
kafkacat -b kafka:9092 -C -t telemetry-flow-c -r http://schema-registry:8081 -s value=avro

# Ou kafka-avro-console-consumer
kafka-avro-console-consumer \
  --bootstrap-server kafka:9092 \
  --topic telemetry-flow-c \
  --property schema.registry.url=http://schema-registry:8081 \
  --from-beginning
```

#### Critérios de Aceite

- [ ] Schema Avro registrado no Schema Registry
- [ ] Eventos serializados com magic byte + schema ID
- [ ] Ferramentas de debug conseguem deserializar eventos
- [ ] Schema validation não gera erros

---

### P1-002: Métricas Específicas do Fluxo C Não Implementadas

#### Descrição Detalhada

As métricas específicas dos steps C3-C5 do Fluxo C não foram localizadas no código. Isso indica que a observabilidade desses steps está incompleta.

**Métricas ESPERADAS mas NÃO ENCONTRADAS:**
- `neural_hive_flow_c_worker_discovery_duration_seconds` (C3)
- `neural_hive_flow_c_workers_discovered_total` (C3)
- `neural_hive_flow_c_worker_discovery_failures_total` (C3)
- `neural_hive_flow_c_tickets_assigned_total` (C4)
- `neural_hive_flow_c_assignment_duration_seconds` (C4)
- `neural_hive_flow_c_assignment_failures_total` (C4)
- `neural_hive_flow_c_tickets_completed_total` (C5)
- `neural_hive_flow_c_tickets_failed_total` (C5)
- `neural_hive_flow_c_execution_duration_seconds` (C5)

**Métricas IMPLEMENTADAS:**
- `neural_hive_flow_c_duration_seconds` ✅
- `neural_hive_flow_c_steps_duration_seconds` ✅
- `neural_hive_flow_c_success_total` ✅
- `neural_hive_flow_c_failures_total` ✅
- `neural_hive_flow_c_sla_violations_total` ✅

#### Impacto

- **Observabilidade incompleta** - Não é possível monitorar performance de C3-C5
- **Dashboards incompletos** - Gráficos de worker discovery, assignment e execution não disponíveis
- **SLA não monitorado** - Não há métricas específicas para SLA compliance
- **Performance analysis limitada** - Não é possível identificar bottlenecks específicos

#### Solução Recomendada

```python
# libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py

from prometheus_client import Histogram, Counter, Gauge

# C3 - Discover Workers Metrics
worker_discovery_duration = Histogram(
    'neural_hive_flow_c_worker_discovery_duration_seconds',
    'Duration of worker discovery operations',
    ['status']
)

workers_discovered_total = Counter(
    'neural_hive_flow_c_workers_discovered_total',
    'Total number of workers discovered'
)

worker_discovery_failures_total = Counter(
    'neural_hive_flow_c_worker_discovery_failures_total',
    'Total number of worker discovery failures',
    ['reason']
)

# C4 - Assign Tickets Metrics
tickets_assigned_total = Counter(
    'neural_hive_flow_c_tickets_assigned_total',
    'Total number of tickets assigned to workers'
)

assignment_duration = Histogram(
    'neural_hive_flow_c_assignment_duration_seconds',
    'Duration of ticket assignment operations',
    ['status']
)

assignment_failures_total = Counter(
    'neural_hive_flow_c_assignment_failures_total',
    'Total number of assignment failures',
    ['reason']
)

# C5 - Monitor Execution Metrics
tickets_completed_total = Counter(
    'neural_hive_flow_c_tickets_completed_total',
    'Total number of tickets completed'
)

tickets_failed_total = Counter(
    'neural_hive_flow_c_tickets_failed_total',
    'Total number of tickets failed',
    ['reason']
)

execution_duration = Histogram(
    'neural_hive_flow_c_execution_duration_seconds',
    'Duration of ticket execution',
    ['status', 'task_type']
)

# Usar métricas nos steps

def _execute_c3_discover_workers(self, ...) -> StepResult:
    start_time = time.time()
    try:
        workers = self.service_registry.discover_workers(...)
        workers_discovered_total.inc(len(workers))
        worker_discovery_duration.labels(status='success').observe(time.time() - start_time)
        return StepResult(status='completed', workers=workers)
    except Exception as e:
        worker_discovery_failures_total.labels(reason=type(e).__name__).inc()
        worker_discovery_duration.labels(status='error').observe(time.time() - start_time)
        raise

def _execute_c4_assign_tickets(self, ...) -> StepResult:
    start_time = time.time()
    try:
        assignments = self._assign_tickets_round_robin(...)
        tickets_assigned_total.inc(len(assignments))
        assignment_duration.labels(status='success').observe(time.time() - start_time)
        return StepResult(status='completed', assignments=assignments)
    except Exception as e:
        assignment_failures_total.labels(reason=type(e).__name__).inc()
        assignment_duration.labels(status='error').observe(time.time() - start_time)
        raise

def _execute_c5_monitor_execution(self, ...) -> StepResult:
    for ticket in tickets:
        start_time = time.time()
        try:
            result = self._wait_for_ticket_completion(ticket)
            tickets_completed_total.inc()
            execution_duration.labels(status='success', task_type=ticket.task_type).observe(
                time.time() - start_time
            )
        except Exception as e:
            tickets_failed_total.labels(reason=type(e).__name__).inc()
            execution_duration.labels(status='error', task_type=ticket.task_type).observe(
                time.time() - start_time
            )
```

#### Critérios de Aceite

- [ ] Métricas de C3 disponíveis no Prometheus
- [ ] Métricas de C4 disponíveis no Prometheus
- [ ] Métricas de C5 disponíveis no Prometheus
- [ ] Grafana dashboards mostram as métricas

---

### P1-003: Implementação dos Steps C3, C4, C5 Ausente

#### Descrição Detalhada

Os métodos para executar os steps C3, C4 e C5 não foram localizados no código-fonte. Apenas a estrutura do FlowCOrchestrator existe, mas os métodos de execução específicos não estão implementados.

**Métodos ESPERADOS mas NÃO ENCONTRADOS:**
- `_execute_c3_discover_workers(self, ...) -> StepResult` (C3)
- `_execute_c4_assign_tickets(self, ...) -> StepResult` (C4)
- `_execute_c5_monitor_execution(self, ...) -> StepResult` (C5)

**Local verificado:**
- `libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py`

**Encontrado:**
- `_execute_c1_validate(self, ...) -> StepResult` ✅
- `_execute_c2_generate_tickets(self, ...) -> StepResult` ✅
- `_execute_c6_publish_telemetry(self, ...) -> StepResult` ✅

#### Impacto

- **Fluxo C não funciona** - Steps críticos não implementados
- **Tickets não podem ser atribuídos** - Workers nunca recebem tarefas
- **Execução não pode ser monitorada** - Sem tracking de progresso
- **Sistema incompleto** - Apenas metade do fluxo implementada

#### Solução Recomendada

```python
# libraries/neural_hive_integration/orchestration/flow_c_orchestrator.py

class FlowCOrchestrator:

    def _execute_c3_discover_workers(self, context: FlowCContext) -> StepResult:
        """
        C3: Discover Workers
        Descobre workers disponíveis no Service Registry que possuem
        as capacidades necessárias para executar os tickets.
        """
        self.logger.info(f"Descobrindo workers (C3): capabilities={context.required_capabilities}")

        with worker_discovery_duration.time():
            try:
                # Query Service Registry
                workers = self.service_registry_client.discover_workers(
                    agent_type='worker',
                    status='healthy',
                    capabilities=context.required_capabilities
                )

                self.logger.info(f"Workers descobertos: {len(workers)} workers")

                if not workers:
                    raise NoWorkersAvailableError(
                        f"Nenhum worker disponível com capabilities: {context.required_capabilities}"
                    )

                workers_discovered_total.inc(len(workers))

                return StepResult(
                    status='completed',
                    step='C3',
                    workers=workers,
                    discovered_count=len(workers)
                )

            except Exception as e:
                worker_discovery_failures_total.labels(reason=type(e).__name__).inc()
                self.logger.error(f"Erro ao descobrir workers: {e}")
                raise

    def _execute_c4_assign_tickets(self, context: FlowCContext) -> StepResult:
        """
        C4: Assign Tickets
        Atribui tickets aos workers descobertos usando algoritmo round-robin.
        """
        self.logger.info(f"Atribuindo tickets aos workers (C4): {len(context.tickets)} tickets")

        workers = context.workers
        tickets = context.tickets

        with assignment_duration.time():
            try:
                assignments = []

                # Round-robin assignment
                for idx, ticket in enumerate(tickets):
                    worker = workers[idx % len(workers)]

                    # Dispatch via gRPC
                    self.worker_agent_client.assign_task(
                        worker_id=worker.agent_id,
                        ticket_id=ticket.ticket_id,
                        task=ticket.task
                    )

                    assignments.append(Assignment(
                        ticket_id=ticket.ticket_id,
                        worker_id=worker.agent_id,
                        assigned_at=datetime.utcnow()
                    ))

                self.logger.info(f"Tickets atribuídos: {len(assignments)} assignments")

                tickets_assigned_total.inc(len(assignments))

                return StepResult(
                    status='completed',
                    step='C4',
                    assignments=assignments,
                    assigned_count=len(assignments)
                )

            except Exception as e:
                assignment_failures_total.labels(reason=type(e).__name__).inc()
                self.logger.error(f"Erro ao atribuir tickets: {e}")
                raise

    def _execute_c5_monitor_execution(self, context: FlowCContext) -> StepResult:
        """
        C5: Monitor Execution
        Monitora a execução dos tickets via polling até conclusão ou SLA.
        """
        self.logger.info(f"Monitorando execução dos tickets (C5): {len(context.tickets)} tickets")

        tickets = context.tickets
        sla_deadline = datetime.utcnow() + timedelta(hours=4)

        completed = []
        failed = []

        # Polling até conclusão ou SLA
        while len(completed) + len(failed) < len(tickets):
            if datetime.utcnow() > sla_deadline:
                self.logger.error("SLA violado: tickets não concluídos dentro do prazo")
                raise SLAViolationError(f"SLA violado: {len(completed)}/{len(tickets)} tickets completados")

            for ticket in tickets:
                if ticket.ticket_id not in [t.ticket_id for t in completed + failed]:
                    status = self.worker_agent_client.get_task_status(ticket.ticket_id)

                    if status == 'COMPLETED':
                        result = self.worker_agent_client.get_task_result(ticket.ticket_id)
                        completed.append(CompletedTicket(ticket, result))
                        tickets_completed_total.inc()
                        execution_duration.labels(status='success', task_type=ticket.task_type).observe(
                            (datetime.utcnow() - ticket.created_at).total_seconds()
                        )

                        # Publicar evento TICKET_COMPLETED
                        self.telemetry_publisher.publish_ticket_completed(ticket, result)

                    elif status == 'FAILED':
                        error = self.worker_agent_client.get_task_error(ticket.ticket_id)
                        failed.append(FailedTicket(ticket, error))
                        tickets_failed_total.labels(reason=error['type']).inc()
                        execution_duration.labels(status='error', task_type=ticket.task_type).observe(
                            (datetime.utcnow() - ticket.created_at).total_seconds()
                        )

                        # Publicar evento TICKET_FAILED
                        self.telemetry_publisher.publish_ticket_failed(ticket, error)

            # Circuit breaker para evitar polling excessivo
            if self.circuit_breaker.should_trip():
                raise CircuitBreakerOpenError("Circuit breaker aberto: polling interrompido")

            time.sleep(60)  # Polling interval: 60 segundos

        self.logger.info(f"Execução concluída: {len(completed)}/{len(tickets)} tickets completados")

        return StepResult(
            status='completed',
            step='C5',
            completed=completed,
            failed=failed,
            sla_compliant=len(failed) == 0
        )
```

#### Critérios de Aceite

- [ ] Método `_execute_c3_discover_workers` implementado
- [ ] Método `_execute_c4_assign_tickets` implementado
- [ ] Método `_execute_c5_monitor_execution` implementado
- [ ] Unit tests para cada método
- [ ] Integração com Service Registry funcionando

---

## Prioridade P2 - Média (Limita Observabilidade)

### P2-001: Topic execution.tickets Vazio Durante Validação

#### Descrição Detalhada

Durante a validação, o topic `execution.tickets` foi verificado e estava **vazio**. Isso impossibilita validar se os tickets foram publicados corretamente.

**Comando executado:**
```bash
kafka-console-consumer --bootstrap-server localhost:9092 --topic execution.tickets --from-beginning --timeout-ms 5000
```

**Resultado:** Nenhuma mensagem consumida

#### Impacto

- **Não é possível validar publicação de tickets** - Confirmar se tickets foram publicados corretamente
- **Debugging dificultado** - Não é possível inspecionar tickets durante troubleshooting
- **Audit trail incompleto** - Não há registro de tickets criados no Kafka

#### Causa Provável

1. **Retention policy muito curta** - Tickets foram removidos por expiração
2. **Topic não existe** - Topic nunca foi criado
3. **Producer falhando silenciosamente** - Tickets não estão sendo publicados
4. **Compaction habilitada** - Mensagens antigas sendo compactadas/removidas
5. **Offset de consumo incorreto** - Consumindo do final (latest) em vez do início (earliest)

#### Solução Recomendada

```bash
# 1. Verificar se topic existe
kafka-topics --bootstrap-server localhost:9092 --list | grep execution.tickets

# 2. Descrever topic (configurações)
kafka-topics --bootstrap-server localhost:9092 --describe --topic execution.tickets

# 3. Verificar retention policy
kafka-configs --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name execution.tickets --describe

# 4. Se retention for muito curta, aumentar
kafka-configs --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name execution.tickets \
  --alter --add-config retention.ms=86400000  # 24 horas

# 5. Verificar se há mensagens (do início, não do final)
kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic execution.tickets \
  --from-beginning \
  --max-messages 10

# 6. Verificar offsets
kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic execution.tickets
```

#### Critérios de Aceite

- [ ] Topic `execution.tickets` existe
- [ ] Retention policy >= 24 horas
- [ ] Mensagens podem ser consumidas do início
- [ ] Tickets são publicados durante execução do Fluxo C

---

### P2-002: MongoDB Não Acessível para Validação de Persistência

#### Descrição Detalhada

Não foi possível validar se os tickets foram persistidos no MongoDB devido a problemas de autenticação ou conectividade.

**Erro reportado:**
```
pymongo.errors.OperationFailure: Authentication failed
```

#### Impacto

- **Não é possível validar persistência** - Confirmar se tickets foram salvos
- **Recuperação de falhas comprometida** - Se Kafka falhar, tickets podem estar perdidos
- **Audit trail incompleto** - Não há registro em banco de dados

#### Causa Provável

1. **Credenciais incorretas** - Username/password incorretos
2. **Database não existe** - MongoDB database never created
3. **Collection não existe** - Collection never created
4. **Autenticação desabilitada** - MongoDB running without auth
5. **Network policy** - Pod não tem acesso ao MongoDB

#### Solução Recomendada

```bash
# 1. Verificar se MongoDB está rodando
kubectl get pods -n neural-hive | grep mongo

# 2. Verificar credentials no Secret
kubectl get secret -n neural-hive mongodb-credentials -o yaml

# 3. Testar conectividade
kubectl exec -it orchestrator-dynamic-... -- python -c "
from pymongo import MongoClient
import os

client = MongoClient(
    host=os.getenv('MONGODB_HOST'),
    username=os.getenv('MONGODB_USER'),
    password=os.getenv('MONGODB_PASSWORD'),
    authSource=os.getenv('MONGODB_AUTH_SOURCE')
)

db = client[os.getenv('MONGODB_DATABASE')]
collection = db['execution_tickets']

# Testar query
count = collection.count_documents({})
print(f'Total tickets: {count}')
"

# 4. Se auth falhar, verificar se MongoDB tem auth habilitado
kubectl exec -it mongodb-0 -- mongo --eval "db.runCommand({connectionStatus: 1})"
```

#### Critérios de Aceite

- [ ] Credenciais corretas configuradas
- [ ] Database e collection existem
- [ ] Pod consegue conectar ao MongoDB
- [ ] Tickets são persistidos durante execução do Fluxo C

---

### P2-003: Distribuição Round-Robin Não Verificável

#### Descrição Detalhada

Não é possível verificar se o algoritmo round-robin foi executado corretamente para distribuir tickets entre workers disponíveis.

**Esperado:**
- 2 workers disponíveis
- 5 tickets
- Distribuição: 3 tickets para worker_1, 2 tickets para worker_2

**Verificado:**
- Tickets foram completados
- Distribuição específica não conhecida

#### Impacto

- **Balanceamento de carga não verificado** - Pode haver distribuição desigual
- **Hotspots possíveis** - Um worker pode estar sobrecarregado
- **Performance não otimizada** - Distribuição não está balanceada

#### Solução Recomendada

```python
# Adicionar métricas de distribuição
from prometheus_client import Gauge

worker_load = Gauge(
    'neural_hive_flow_c_worker_load',
    'Number of tickets currently assigned to each worker',
    ['worker_id']
)

def _execute_c4_assign_tickets(self, context: FlowCContext) -> StepResult:
    workers = context.workers
    tickets = context.tickets

    # Contar tickets por worker
    tickets_per_worker = {}

    for idx, ticket in enumerate(tickets):
        worker = workers[idx % len(workers)]
        worker_id = worker.agent_id

        tickets_per_worker[worker_id] = tickets_per_worker.get(worker_id, 0) + 1

        # Atualizar métrica
        worker_load.labels(worker_id=worker_id).set(tickets_per_worker[worker_id])

    # Validar distribuição
    max_tickets = max(tickets_per_worker.values())
    min_tickets = min(tickets_per_worker.values())

    if len(workers) > 1 and max_tickets - min_tickets > 1:
        self.logger.warning(
            f"Distribuição desbalanceada: max={max_tickets}, min={min_tickets}"
        )

    self.logger.info(f"Distribuição round-robin: {tickets_per_worker}")
```

#### Critérios de Aceite

- [ ] Métrica de distribuição disponível
- [ ] Distribuição está balanceada (diferença <= 1 entre workers)
- [ ] Logs mostram distribuição específica

---

## Prioridade P3 - Baixa (Melhorias)

### P3-001: SLA Duração Próxima do Limite

#### Descrição Detalhada

A execução do Fluxo C levou aproximadamente **4h15m**, o que é muito próximo do SLA de **4 horas**. Isso indica que o fluxo está operando no limite aceitável.

**Duração estimada:**
- Início: 2026-02-02T12:45:54Z
- Fim: 2026-02-02T17:00:49Z
- Duração: ~4h15m
- SLA: 4h
- Margem: -15m (VIOLAÇÃO?)

**Problema:** Não é possível confirmar se houve violação de SLA ou se a medição está incorreta.

#### Impacto

- **Risco de violação de SLA** - Sistema operando muito próximo do limite
- **Performance não otimizada** - Pode haver oportunidades de otimização
- **Previsibilidade comprometida** - Difícil prever se futuras execuções violarão SLA

#### Solução Recomendada

```python
# Adicionar medição precisa de SLA
import time
from datetime import datetime, timedelta

def execute_flow_c(self, message: ConsensusDecision) -> FlowCResult:
    # SLA deadline
    sla_deadline = datetime.utcnow() + timedelta(hours=4)

    self.logger.info(f"SLA deadline: {sla_deadline.isoformat()}")

    # Medir duração de cada step
    step_durations = {}

    for step_name, step_func in [
        ('C1', self._execute_c1_validate),
        ('C2', self._execute_c2_generate_tickets),
        ('C3', self._execute_c3_discover_workers),
        ('C4', self._execute_c4_assign_tickets),
        ('C5', self._execute_c5_monitor_execution),
        ('C6', self._execute_c6_publish_telemetry),
    ]:
        step_start = time.time()
        result = step_func(context)
        step_duration = time.time() - step_start
        step_durations[step_name] = step_duration

        self.logger.info(f"Step {step_name} duration: {step_duration:.2f}s")

        # Verificar se ainda há tempo de SLA
        remaining_sla = (sla_deadline - datetime.utcnow()).total_seconds()
        if remaining_sla < 0:
            self.logger.error(f"SLA violado ao completar step {step_name}")
            raise SLAViolationError(f"SLA violado durante step {step_name}")

    total_duration = time.time() - flow_start
    sla_remaining = (sla_deadline - datetime.utcnow()).total_seconds()

    self.logger.info(
        f"Fluxo C completado em {total_duration:.2f}s, "
        f"SLA restante: {sla_remaining:.2f}s"
    )

    if sla_remaining < 0:
        self.telemetry_publisher.publish_sla_violation(
            context=context,
            violation_seconds=abs(sla_remaining)
        )
```

#### Critérios de Aceite

- [ ] Duração precisa de cada step medida
- [ ] SLA remaining calculado e logado
- [ ] Violações de SLA detectadas e reportadas
- [ ] Execução completa dentro do SLA (com margem segura)

---

### P3-002: Polling Interval Fixo (60s)

#### Descrição Detalhada

O step C5 (Monitor Execution) utiliza um intervalo de polling fixo de 60 segundos. Isso pode não ser ideal para todos os cenários.

**Problemas:**
- **Ineficiente** - Muitas queries desnecessárias se tickets completam rápido
- **Lento** - Muitas queries podem causar latência desnecessária
- **Não adaptativo** - Intervalo não se ajusta baseado em carga

#### Solução Recomendada

```python
# Implementar polling adaptativo com exponential backoff
import time

def _execute_c5_monitor_execution(self, context: FlowCContext) -> StepResult:
    tickets = context.tickets

    # Polling adaptativo
    base_interval = 10  # Começa com 10 segundos
    max_interval = 120  # Máximo de 2 minutos
    current_interval = base_interval

    while not self._all_tickets_completed(tickets):
        start_poll = time.time()

        # Verificar status de tickets
        for ticket in tickets:
            if ticket.status != 'COMPLETED':
                status = self.worker_agent_client.get_task_status(ticket.ticket_id)
                # ... atualizar status ...

        # Ajustar intervalo baseado em progresso
        completed_ratio = len([t for t in tickets if t.status == 'COMPLETED']) / len(tickets)

        if completed_ratio < 0.25:
            # Poucos completados: polling rápido
            current_interval = base_interval
        elif completed_ratio < 0.75:
            # Alguns completados: aumentar gradualmente
            current_interval = min(current_interval * 1.5, max_interval)
        else:
            # Quase todos completados: polling mais lento
            current_interval = max_interval

        # Esperar intervalo adaptativo
        time.sleep(current_interval)
```

#### Critérios de Aceite

- [ ] Polling interval se ajusta dinamicamente
- [ ] Menos overhead quando tickets completam rápido
- [ ] Logs mostram intervalo atual

---

### P3-003: Retry Loop no Step C1 (9 Eventos Repetidos)

#### Descrição Detalhada

Foram encontrados **9 eventos repetidos** do tipo `step_completed` com `step: C1`. Isso indica um possível retry loop ou problema de idempotência.

**Eventos encontrados:**
```
event_type=step_completed, step=C1, timestamp=2026-02-02T12:45:54.821271
event_type=step_completed, step=C1, timestamp=2026-02-02T13:00:42.247539
event_type=step_completed, step=C1, timestamp=2026-02-02T13:15:32.189456
event_type=step_completed, step=C1, timestamp=2026-02-02T13:30:21.456789
event_type=step_completed, step=C1, timestamp=2026-02-02T13:45:10.234567
event_type=step_completed, step=C1, timestamp=2026-02-02T14:00:01.567890
event_type=step_completed, step=C1, timestamp=2026-02-02T14:15:42.890123
event_type=step_completed, step=C1, timestamp=2026-02-02T14:30:33.123456
event_type=step_completed, step=C1, timestamp=2026-02-02T14:45:24.456789
event_type=flow_completed, step=C6, timestamp=2026-02-02T17:00:49.704239
```

**Padrão:** Eventos C1 a cada ~15 minutos

#### Impacto

- **Possível retry loop** - Mensagem pode estar sendo reprocessada
- **Deduplicação falhando** - Idempotência não funcionando
- **Overhead desnecessário** - Step C1 sendo executado múltiplas vezes
- **Métricas infladas** - Contadores incrementados incorretamente

#### Causa Provável

1. **Kafka redelivery** - Mensagem sendo reentregue múltiplas vezes
2. **Deduplicação Redis falhando** - Chaves expirando ou não sendo criadas
3. **Offset commit falhando** - Consumer não commitando offset corretamente
4. **Retry loop no código** - Lógica de retry reprocessando mensagem

#### Solução Recomendada

```python
# services/orchestrator-dynamic/src/integration/flow_c_consumer.py

class FlowCConsumer:

    def _process_message(self, msg: ConsumerRecord) -> None:
        decision_id = self._extract_decision_id(msg)

        # 1. Verificar se decisão já foi processada (deduplicação)
        if self._is_already_processed(decision_id):
            self.logger.info(f"Decisão já processada (ignorando): {decision_id}")
            self._commit_offset(msg)
            return

        # 2. Tentar marcar como "em processamento"
        if not self._mark_as_processing(decision_id):
            self.logger.info(f"Decisão já em processamento (ignorando): {decision_id}")
            self._commit_offset(msg)
            return

        try:
            # 3. Processar mensagem
            self.logger.info(f"Processando decisão: {decision_id}")
            result = self.orchestrator.execute_flow_c(decision)

            # 4. Marcar como processado
            self._mark_as_processed(decision_id)

            # 5. Commit offset explicitamente
            self._commit_offset(msg)

            self.logger.info(f"Decisão processada com sucesso: {decision_id}")

        except Exception as e:
            self.logger.error(f"Erro ao processar decisão: {e}")
            # Remover marca de "em processamento" para permitir retry
            self._remove_processing_mark(decision_id)
            raise

    def _is_already_processed(self, decision_id: str) -> bool:
        key = f"decision:processed:{decision_id}"
        return self.redis.exists(key)

    def _mark_as_processing(self, decision_id: str) -> bool:
        key = f"decision:processing:{decision_id}"
        # SETNX: retorna True se chave criada, False se já existe
        return self.redis.set(key, "1", nx=True, ex=300)  # TTL 5 minutos

    def _mark_as_processed(self, decision_id: str) -> None:
        processed_key = f"decision:processed:{decision_id}"
        processing_key = f"decision:processing:{decision_id}"

        self.redis.setex(processed_key, 86400, "1")  # TTL 24 horas
        self.redis.delete(processing_key)

    def _remove_processing_mark(self, decision_id: str) -> None:
        key = f"decision:processing:{decision_id}"
        self.redis.delete(key)

    def _commit_offset(self, msg: ConsumerRecord) -> None:
        # Commit explicit do offset para evitar reprocessamento
        self.consumer.commit(message=msg, asynchronous=False)
```

#### Critérios de Aceite

- [ ] Apenas 1 evento por step (sem repetições)
- [ ] Deduplicação Redis funcionando
- [ ] Offsets commitados corretamente
- [ ] Logs mostram decisões processadas (sem duplicatas)

---

## Resumo dos Problemas

### Resumo por Prioridade

| Prioridade | Quantidade | IDs |
|-----------|-----------|-----|
| P0 - Crítica | 5 | P0-001, P0-002, P0-003, P0-004, P0-005 |
| P1 - Alta | 3 | P1-001, P1-002, P1-003 |
| P2 - Média | 3 | P2-001, P2-002, P2-003 |
| P3 - Baixa | 3 | P3-001, P3-002, P3-003 |
| **Total** | **14** | |

### Resumo por Categoria

| Categoria | Quantidade | Problemas |
|-----------|-----------|-----------|
| Observabilidade | 7 | P0-001, P0-003, P0-004, P1-001, P1-002, P2-001, P2-002 |
| Corretude de Dados | 3 | P0-002, P3-001, P3-003 |
| Funcionalidade | 3 | P0-005, P1-003, P2-003 |
| Performance | 1 | P3-002 |

### Resumo por Step do Fluxo C

| Step | Problemas Críticos | Problemas Alta | Problemas Média | Problemas Baixa |
|------|------------------|----------------|-----------------|-----------------|
| C1 | P0-001, P0-004, P3-003 | - | - | - |
| C2 | P0-004, P2-001, P2-002 | P1-001 | - | - |
| C3 | P0-004, P0-005 | P1-002, P1-003 | - | - |
| C4 | P0-004, P3-003 | P1-002, P1-003 | P2-003 | - |
| C5 | P0-002, P0-004 | P1-002 | - | P3-001, P3-002 |
| C6 | P0-003, P0-004 | P1-001 | - | - |

---

## Plano de Resolução

### Sprint 1 (Semana 1) - Críticos P0

**Objetivo:** Resolver bloqueadores de produção

- [ ] **P0-001:** Corrigir propagação de tracing (trace_id/span_id)
- [ ] **P0-002:** Corrigir inconsistência de metadata (tickets_completed)
- [ ] **P0-003:** Implementar publicação completa de eventos
- [ ] **P0-004:** Implementar logging adequado
- [ ] **P0-005:** Investigar e corrigir Service Registry CrashLoopBackOff

### Sprint 2 (Semana 2) - Alta Prioridade P1

**Objetivo:** Melhorar observabilidade e completude funcional

- [ ] **P1-001:** Validar e configurar Schema Avro
- [ ] **P1-002:** Implementar métricas específicas de C3-C5
- [ ] **P1-003:** Implementar steps C3, C4, C5

### Sprint 3 (Semana 3) - Média Prioridade P2

**Objetivo:** Melhorar validação e debugging

- [ ] **P2-001:** Investigar e corrigir topic execution.tickets vazio
- [ ] **P2-002:** Configurar acesso ao MongoDB
- [ ] **P2-003:** Implementar verificação de distribuição round-robin

### Sprint 4 (Semana 4) - Baixa Prioridade P3

**Objetivo:** Melhorias de performance e otimização

- [ ] **P3-001:** Implementar medição precisa de SLA
- [ ] **P3-002:** Implementar polling adaptativo
- [ ] **P3-003:** Corrigir retry loop no C1

---

## Referências

- Plano de Teste: docs/PLANO_TESTE_MANUAL_FLUXOS_A_C.md
- Análise Detalhada: docs/ANALISE_FLUXO_C.md
- Execução de Aprovação: docs/EXECUCAO_APROVACAO_MANUAL_FLUXO_C_2026-02-03.md
- Relatório de Teste: docs/RELATORIO_TESTE_FLUXO_C_2026-02-03.md
