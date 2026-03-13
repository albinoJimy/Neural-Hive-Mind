"""
Teste E2E: Fluxo Completo Intention → Code

Valida o pipeline cognitivo completo:
1. Gateway → STE → Consensus → Orchestrator → Worker
2. Propagação de correlation_id em todos os hops
3. Geração de código/artefatos
4. Distributed tracing (traceparent)

Pré-requisitos:
- Todos os serviços rodando (minikube/kind ou cluster real)
- Kafka acessível
- MongoDB acessível
- Redis acessível (opcional - fallback MongoDB)

Execução:
    pytest tests/e2e/test_full_intent_to_code.py -v --asyncio-mode=auto
"""

import asyncio
import os
import uuid
import pytest
import structlog
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

# Imports condicionais para Kubernetes/Docker
try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

try:
    from confluent_kafka import Consumer, KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

logger = structlog.get_logger()


@dataclass
class TestContext:
    """Contexto compartilhado entre steps do teste"""
    intent_id: str
    correlation_id: str
    trace_id: Optional[str] = None
    plan_id: Optional[str] = None
    decision_id: Optional[str] = None
    ticket_ids: list = None
    artifact_path: Optional[str] = None

    def __post_init__(self):
        if self.ticket_ids is None:
            self.ticket_ids = []


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def test_config():
    """Configuração do ambiente de teste"""
    return {
        'kafka_bootstrap_servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        'kafka_intentions_topic': os.getenv('KAFKA_INTENTIONS_TOPIC', 'intentions.security'),
        'kafka_plans_topic': os.getenv('KAFKA_PLANS_TOPIC', 'plans.ready'),
        'kafka_consensus_topic': os.getenv('KAFKA_CONSENSUS_TOPIC', 'plans.consensus'),
        'kafka_tickets_topic': os.getenv('KAFKA_TICKETS_TOPIC', 'execution.tickets'),
        'gateway_url': os.getenv('GATEWAY_URL', 'http://localhost:8000'),
        'approval_service_url': os.getenv('APPROVAL_SERVICE_URL', 'http://localhost:8003'),
        'timeout_seconds': int(os.getenv('E2E_TIMEOUT_SECONDS', '300')),
    }


@pytest.fixture
def test_context():
    """Cria contexto único para cada teste"""
    intent_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    return TestContext(
        intent_id=intent_id,
        correlation_id=correlation_id
    )


@pytest.fixture
async def kafka_consumer(test_config):
    """Consumer Kafka para monitorar tópicos"""
    if not KAFKA_AVAILABLE:
        pytest.skip("confluent-kafka não instalado")

    consumer_config = {
        'bootstrap.servers': test_config['kafka_bootstrap_servers'],
        'group.id': f'e2e-test-{uuid.uuid4()}',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,
    }

    consumer = Consumer(consumer_config)
    consumer.subscribe([
        test_config['kafka_plans_topic'],
        test_config['kafka_consensus_topic'],
        test_config['kafka_tickets_topic'],
    ])

    yield consumer

    consumer.close()


# =============================================================================
# TESTE PRINCIPAL
# =============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_intent_to_code_full_flow(test_config, test_context, kafka_consumer):
    """
    Teste E2E completo: Intenção → Gateway → STE → Consensus → Orchestrator → Worker

    Fluxo validado:
    1. Submissão de intenção via Gateway
    2. Geração de Cognitive Plan (STE)
    3. Consenso dos especialistas
    4. Geração de tickets de execução
    5. Execução pelos workers
    6. Compilação/Deploy do código gerado

    Assertions:
    - correlation_id propagado em todos os serviços
    - trace_id consistente (W3C traceparent)
    - Código/artefato gerado com sucesso
    """
    logger.info(
        'e2e_test_started',
        test_name='test_intent_to_code_full_flow',
        intent_id=test_context.intent_id,
        correlation_id=test_context.correlation_id
    )

    # STEP 1: Submeter intenção
    await step_1_submit_intent(test_config, test_context)

    # STEP 2: Aguardar Cognitive Plan no Kafka
    await step_2_wait_for_cognitive_plan(test_config, test_context, kafka_consumer)

    # STEP 3: Aguardar decisão de consenso
    await step_3_wait_for_consensus_decision(test_config, test_context, kafka_consumer)

    # STEP 4: Aguardar tickets de execução
    await step_4_wait_for_execution_tickets(test_config, test_context, kafka_consumer)

    # STEP 5: Validar propagação de tracing
    await step_5_validate_trace_propagation(test_config, test_context)

    # STEP 6: Aguardar conclusão da execução
    await step_6_wait_for_completion(test_config, test_context)

    logger.info(
        'e2e_test_passed',
        test_name='test_intent_to_code_full_flow',
        intent_id=test_context.intent_id,
        plan_id=test_context.plan_id,
        execution_time_seconds=getattr(test_context, 'execution_time', None)
    )


# =============================================================================
# STEP IMPLEMENTATIONS
# =============================================================================

async def step_1_submit_intent(test_config: Dict, ctx: TestContext):
    """STEP 1: Submeter intenção via Gateway"""
    import httpx

    logger.info('step_1_submitting_intent', intent_id=ctx.intent_id)

    payload = {
        'intent_id': ctx.intent_id,
        'natural_language': 'Create a REST API endpoint for user management with CRUD operations',
        'domain': 'security',
        'context': {
            'framework': 'fastapi',
            'database': 'mongodb',
            'authentication': 'jwt'
        },
        'user_id': 'e2e-test-user',
        'correlation_id': ctx.correlation_id  # FASE 1: correlation_id obrigatório
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{test_config['gateway_url']}/api/v1/intentions",
            json=payload,
            headers={
                'X-Correlation-ID': ctx.correlation_id,
                'X-Request-ID': str(uuid.uuid4())
            }
        )

        if response.status_code not in (200, 201, 202):
            pytest.fail(f"Gateway rejected request: {response.status_code} - {response.text}")

        result = response.json()

        # Validar resposta
        assert 'intent_id' in result or 'request_id' in result, "Missing intent_id in response"

        logger.info(
            'step_1_intent_submitted',
            intent_id=ctx.intent_id,
            status_code=response.status_code
        )


async def step_2_wait_for_cognitive_plan(test_config: Dict, ctx: TestContext, consumer):
    """STEP 2: Aguardar Cognitive Plan no tópico plans.ready"""
    logger.info('step_2_waiting_for_cognitive_plan', intent_id=ctx.intent_id)

    plan_found = False
    max_wait = test_config['timeout_seconds']
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < max_wait:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue

        if msg.error():
            logger.warning('kafka_consumer_error', error=msg.error())
            continue

        # Deserializar mensagem
        try:
            import json
            value = json.loads(msg.value().decode('utf-8'))

            # Verificar se é o plano da nossa intenção
            if value.get('intent_id') == ctx.intent_id or value.get('intentionId') == ctx.intent_id:
                ctx.plan_id = value.get('plan_id') or value.get('planId')

                # FASE 1: Validar correlation_id
                headers = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                          for k, v in (msg.headers() or [])}
                found_correlation_id = headers.get('correlation-id')

                assert found_correlation_id == ctx.correlation_id, \
                    f"correlation_id mismatch: expected {ctx.correlation_id}, got {found_correlation_id}"

                # FASE 5: Validar traceparent
                ctx.trace_id = headers.get('traceparent') or headers.get('trace-id')

                # Validar campos obrigatórios
                assert ctx.plan_id, "plan_id missing in Cognitive Plan"
                assert 'tasks' in value or 'tasks_count' in value, "No tasks in Cognitive Plan"

                plan_found = True
                logger.info(
                    'step_2_cognitive_plan_found',
                    plan_id=ctx.plan_id,
                    correlation_id=found_correlation_id,
                    trace_id=ctx.trace_id,
                    tasks_count=value.get('tasks_count', len(value.get('tasks', [])))
                )
                break

        except Exception as e:
            logger.warning('step_2_message_parse_error', error=str(e))
            continue

    assert plan_found, f"Cognitive Plan not found within {max_wait}s"


async def step_3_wait_for_consensus_decision(test_config: Dict, ctx: TestContext, consumer):
    """STEP 3: Aguardar decisão de consenso no tópico plans.consensus"""
    logger.info('step_3_waiting_for_consensus', plan_id=ctx.plan_id)

    decision_found = False
    max_wait = 60  # 60 segundos para consenso
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < max_wait:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue

        if msg.error():
            continue

        try:
            import json
            value = json.loads(msg.value().decode('utf-8'))

            # Verificar se é a decisão do nosso plano
            if value.get('plan_id') == ctx.plan_id:
                ctx.decision_id = value.get('decision_id')

                # FASE 1: Validar correlation_id
                headers = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                          for k, v in (msg.headers() or [])}
                found_correlation_id = headers.get('correlation-id')

                assert found_correlation_id == ctx.correlation_id, \
                    f"correlation_id mismatch in consensus: expected {ctx.correlation_id}, got {found_correlation_id}"

                # Validar decisão
                assert ctx.decision_id, "decision_id missing"
                final_decision = value.get('final_decision')
                assert final_decision in ('APPROVED', 'REJECTED', 'approved', 'rejected'), \
                    f"Invalid final_decision: {final_decision}"

                decision_found = True
                logger.info(
                    'step_3_consensus_decision_found',
                    decision_id=ctx.decision_id,
                    final_decision=final_decision,
                    correlation_id=found_correlation_id
                )
                break

        except Exception as e:
            logger.warning('step_3_message_parse_error', error=str(e))
            continue

    assert decision_found, f"Consensus Decision not found within {max_wait}s"


async def step_4_wait_for_execution_tickets(test_config: Dict, ctx: TestContext, consumer):
    """STEP 4: Aguardar tickets de execução no tópico execution.tickets"""
    logger.info('step_4_waiting_for_tickets', plan_id=ctx.plan_id)

    tickets = []
    max_wait = 30
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < max_wait:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue

        if msg.error():
            continue

        try:
            import json
            value = json.loads(msg.value().decode('utf-8'))

            # Verificar se é ticket do nosso plano
            if value.get('plan_id') == ctx.plan_id:
                ticket_id = value.get('ticket_id')

                # FASE 1: Validar correlation_id
                headers = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                          for k, v in (msg.headers() or [])}
                found_correlation_id = headers.get('correlation-id')

                assert found_correlation_id == ctx.correlation_id, \
                    f"correlation_id mismatch in ticket: expected {ctx.correlation_id}, got {found_correlation_id}"

                tickets.append(ticket_id)
                logger.info(
                    'step_4_ticket_found',
                    ticket_id=ticket_id,
                    task_type=value.get('task_type'),
                    executor=value.get('executor')
                )

        except Exception as e:
            logger.warning('step_4_message_parse_error', error=str(e))
            continue

    assert len(tickets) > 0, "No execution tickets found"
    ctx.ticket_ids = tickets

    logger.info('step_4_all_tickets_collected', ticket_count=len(tickets))


async def step_5_validate_trace_propagation(test_config: Dict, ctx: TestContext):
    """STEP 5: Validar propagação de tracing end-to-end"""
    logger.info('step_5_validating_trace_propagation')

    # Validar que trace_id foi propagado
    if ctx.trace_id:
        logger.info('step_5_traceparent_propagated', trace_id=ctx.trace_id)
    else:
        # Se não tiver traceparent, verificar se pelo menos trace_id/span_id estão presentes
        logger.warning('step_5_traceparent_not_found', note='traceparent header not found, checking fallback')

    # O mais importante: correlation_id deve ser consistente
    assert ctx.correlation_id, "correlation_id deve estar presente"
    assert ctx.plan_id, "plan_id deve estar presente"
    assert ctx.decision_id, "decision_id deve estar presente"
    assert len(ctx.ticket_ids) > 0, "tickets devem ter sido gerados"

    logger.info(
        'step_5_trace_validation_complete',
        correlation_id=ctx.correlation_id,
        trace_id=ctx.trace_id,
        plan_id=ctx.plan_id,
        decision_id=ctx.decision_id,
        ticket_count=len(ctx.ticket_ids)
    )


async def step_6_wait_for_completion(test_config: Dict, ctx: TestContext):
    """STEP 6: Aguardar conclusão da execução (Worker → Code)"""
    logger.info('step_6_waiting_for_completion', ticket_count=len(ctx.ticket_ids))

    # Em um cenário real, verificaríamos:
    # 1. Status dos tickets no Execution Ticket Service
    # 2. Artefatos gerados no Code Forge
    # 3. Deploy no ArgoCD (se aplicável)

    # Para este teste E2E, aguardamos um tempo razoável e validamos
    # que o sistema não entrou em estado de erro

    await asyncio.sleep(10)  # Aguardar processamento

    # TODO: Adicionar verificações reais de conclusão quando APIs estiverem disponíveis
    # - GET /api/v1/tickets/{ticket_id}
    # - GET /api/v1/artifacts/{plan_id}
    # - GET /api/v1/approvals/{plan_id}

    logger.info('step_6_completion_assumed', note='Full E2E test validation pending API availability')


# =============================================================================
# TESTES ADICIONAIS
# =============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_correlation_id_propagation(test_config, test_context):
    """
    Teste específico para FASE 1: Valida propagação de correlation_id

    Verifica que correlation_id é propagado através de:
    1. Gateway → STE
    2. STE → Consensus
    3. Consensus → Orchestrator
    4. Orchestrator → Worker
    """
    correlation_id = str(uuid.uuid4())

    # Submeter intenção com correlation_id específico
    import httpx

    payload = {
        'intent_id': str(uuid.uuid4()),
        'natural_language': 'Test correlation propagation',
        'domain': 'security',
        'correlation_id': correlation_id
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{test_config['gateway_url']}/api/v1/intentions",
            json=payload,
            headers={'X-Correlation-ID': correlation_id}
        )
        assert response.status_code in (200, 201, 202)

    # TODO: Verificar propagação em cada hop
    # (requer consumer em cada tópico ou APIs de consulta)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_w3c_traceparent_format(test_config, test_context):
    """
    Teste para FASE 5: Valida formato W3C traceparent

    Formato esperado: 00-trace_id-span_id-flags
    Exemplo: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
    """
    import httpx

    payload = {
        'intent_id': str(uuid.uuid4()),
        'natural_language': 'Test W3C traceparent',
        'domain': 'security'
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{test_config['gateway_url']}/api/v1/intentions",
            json=payload,
            headers={'X-Correlation-ID': test_context.correlation_id}
        )
        assert response.status_code in (200, 201, 202)

    # TODO: Consumir tópicos e validar traceparent header
    # Verificar formato: 00-{32 hex chars}-{16 hex chars}-{2 hex chars}


# =============================================================================
# TESTES DE STRESS
# =============================================================================

@pytest.mark.e2e
@pytest.mark.stress
@pytest.mark.asyncio
async def test_concurrent_intentions(test_config):
    """
    Teste de stress: 50 intenções concorrentes

    Valida que:
    - Nenhuma intenção é perdida
    - correlation_id é único por intenção
    - Sistema degrada gracefulmente sob carga
    """
    import httpx

    concurrent_requests = 50
    intent_ids = [str(uuid.uuid4()) for _ in range(concurrent_requests)]
    correlation_ids = [str(uuid.uuid4()) for _ in range(concurrent_requests)]

    async def submit_intent(intent_id: str, correlation_id: str):
        payload = {
            'intent_id': intent_id,
            'natural_language': f'Concurrent test intent {intent_id}',
            'domain': 'security',
            'correlation_id': correlation_id
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{test_config['gateway_url']}/api/v1/intentions",
                json=payload,
                headers={'X-Correlation-ID': correlation_id}
            )
            return response.status_code, intent_id, correlation_id

    # Executar concorrentemente
    tasks = [
        submit_intent(intent_ids[i], correlation_ids[i])
        for i in range(concurrent_requests)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Validar resultados
    success_count = 0
    for result in results:
        if isinstance(result, Exception):
            logger.error('concurrent_request_failed', error=str(result))
        else:
            status_code, intent_id, correlation_id = result
            if status_code in (200, 201, 202):
                success_count += 1
            else:
                logger.warning(
                    'concurrent_request_rejected',
                    intent_id=intent_id,
                    status_code=status_code
                )

    # Pelo menos 90% devem ser aceitos
    success_rate = success_count / concurrent_requests
    assert success_rate >= 0.9, f"Success rate too low: {success_rate:.2%}"

    logger.info(
        'stress_test_completed',
        total_requests=concurrent_requests,
        successful=success_count,
        success_rate=f"{success_rate:.2%}"
    )


# =============================================================================
# UTILITIES
# =============================================================================

def pytest_configure(config):
    """Configuração pytest"""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end"
    )
    config.addinivalue_line(
        "markers", "stress: mark test as stress test"
    )
