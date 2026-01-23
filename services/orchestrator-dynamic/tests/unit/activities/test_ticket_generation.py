"""
Testes unitários para activities de geração de tickets.

Testes cobrem:
- generate_execution_tickets com planos simples e complexos
- Cálculo de SLA baseado em risk_band
- Cálculo de QoS baseado em criticidade
- allocate_resources com Intelligent Scheduler
- Fallback stub quando scheduler indisponível
- Validação OPA de ticket e alocação
- publish_ticket_to_kafka com tickets válidos e rejeitados
- Persistência no MongoDB
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from pymongo.errors import PyMongoError
from neural_hive_resilience.circuit_breaker import CircuitBreakerError

from src.activities.ticket_generation import (
    generate_execution_tickets,
    allocate_resources,
    publish_ticket_to_kafka,
    set_activity_dependencies
)


@pytest.fixture
def mock_activity_info():
    """Mock activity.info() para contexto de workflow."""
    with patch('src.activities.ticket_generation.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'test-workflow-123'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


@pytest.fixture
def simple_plan():
    """Criar plano cognitivo simples com uma task."""
    return {
        'plan_id': 'plan-001',
        'intent_id': 'intent-001',
        'tasks': [
            {
                'task_id': 'task-1',
                'task_type': 'EXECUTE',
                'description': 'Executar tarefa simples',
                'dependencies': [],
                'estimated_duration_ms': 60000,
                'parameters': {'key': 'value'},
                'required_capabilities': ['python']
            }
        ],
        'execution_order': ['task-1'],
        'risk_score': 0.3,
        'risk_band': 'low',
        'priority': 'NORMAL',
        'security_level': 'INTERNAL'
    }


@pytest.fixture
def complex_plan():
    """Criar plano cognitivo com múltiplas tasks e dependências."""
    return {
        'plan_id': 'plan-002',
        'intent_id': 'intent-002',
        'tasks': [
            {'task_id': 'task-1', 'dependencies': [], 'estimated_duration_ms': 30000},
            {'task_id': 'task-2', 'dependencies': ['task-1'], 'estimated_duration_ms': 45000},
            {'task_id': 'task-3', 'dependencies': ['task-1'], 'estimated_duration_ms': 60000},
            {'task_id': 'task-4', 'dependencies': ['task-2', 'task-3'], 'estimated_duration_ms': 90000}
        ],
        'execution_order': ['task-1', 'task-2', 'task-3', 'task-4'],
        'risk_score': 0.7,
        'risk_band': 'high',
        'priority': 'HIGH'
    }


@pytest.fixture
def consolidated_decision():
    """Criar decisão consolidada mock."""
    return {
        'decision_id': 'decision-001',
        'correlation_id': 'corr-001',
        'trace_id': 'trace-001',
        'span_id': 'span-001'
    }


@pytest.fixture
def mock_kafka_producer():
    """Criar mock de Kafka producer."""
    producer = AsyncMock()
    producer.publish_ticket.return_value = {
        'topic': 'execution.tickets',
        'partition': 0,
        'offset': 123,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }
    return producer


@pytest.fixture
def mock_mongodb_client():
    """Criar mock de MongoDB client."""
    client = AsyncMock()
    client.save_execution_ticket = AsyncMock()
    return client


@pytest.fixture
def mock_intelligent_scheduler():
    """Criar mock de Intelligent Scheduler."""
    scheduler = AsyncMock()

    async def schedule_ticket_mock(ticket):
        ticket['allocation_metadata'] = {
            'allocated_at': int(datetime.now().timestamp() * 1000),
            'agent_id': 'worker-agent-001',
            'agent_type': 'worker-agent',
            'priority_score': 0.8,
            'agent_score': 0.9,
            'composite_score': 0.85,
            'allocation_method': 'intelligent_scheduler',
            'workers_evaluated': 5
        }
        return ticket

    scheduler.schedule_ticket.side_effect = schedule_ticket_mock
    return scheduler


@pytest.fixture
def mock_policy_validator():
    """Criar mock de policy validator."""
    validator = AsyncMock()
    result = MagicMock()
    result.valid = True
    result.violations = []
    result.warnings = []
    result.policy_decisions = {'feature_flags': {'enable_intelligent_scheduler': True}}
    result.evaluated_at = datetime.now()
    validator.validate_execution_ticket.return_value = result
    validator.validate_resource_allocation.return_value = result
    return validator


@pytest.fixture
def mock_config():
    """Criar mock de configuração."""
    config = MagicMock()
    config.opa_enabled = True
    config.opa_fail_open = True
    return config


class TestGenerateExecutionTickets:
    """Testes para generate_execution_tickets activity."""

    @pytest.mark.asyncio
    async def test_simple_plan_generates_one_ticket(
        self, mock_activity_info, simple_plan, consolidated_decision
    ):
        """Plano simples deve gerar exatamente um ticket."""
        set_activity_dependencies(
            kafka_producer=None, mongodb_client=None
        )

        tickets = await generate_execution_tickets(simple_plan, consolidated_decision)

        assert len(tickets) == 1
        assert tickets[0]['plan_id'] == 'plan-001'
        assert tickets[0]['task_id'] == 'task-1'
        assert tickets[0]['status'] == 'PENDING'

    @pytest.mark.asyncio
    async def test_complex_plan_maps_dependencies_correctly(
        self, mock_activity_info, complex_plan, consolidated_decision
    ):
        """Plano complexo deve mapear dependências de task_id para ticket_id."""
        set_activity_dependencies(
            kafka_producer=None, mongodb_client=None
        )

        tickets = await generate_execution_tickets(complex_plan, consolidated_decision)

        assert len(tickets) == 4

        # Construir mapa de task_id para ticket_id
        task_to_ticket = {t['task_id']: t['ticket_id'] for t in tickets}

        # task-4 deve ter dependências de task-2 e task-3 (como ticket_ids)
        task_4_ticket = next(t for t in tickets if t['task_id'] == 'task-4')
        expected_deps = [task_to_ticket['task-2'], task_to_ticket['task-3']]
        assert set(task_4_ticket['dependencies']) == set(expected_deps)

    @pytest.mark.asyncio
    async def test_sla_calculation_critical_risk(
        self, mock_activity_info, consolidated_decision
    ):
        """risk_band 'critical' deve ter max_retries=5."""
        critical_plan = {
            'plan_id': 'plan-critical',
            'intent_id': 'intent-critical',
            'tasks': [{'task_id': 'task-1', 'dependencies': [], 'estimated_duration_ms': 60000}],
            'execution_order': ['task-1'],
            'risk_band': 'critical'
        }
        set_activity_dependencies(kafka_producer=None, mongodb_client=None)

        tickets = await generate_execution_tickets(critical_plan, consolidated_decision)

        assert tickets[0]['sla']['max_retries'] == 5

    @pytest.mark.asyncio
    async def test_sla_calculation_high_risk(
        self, mock_activity_info, consolidated_decision
    ):
        """risk_band 'high' deve ter max_retries=3."""
        high_plan = {
            'plan_id': 'plan-high',
            'intent_id': 'intent-high',
            'tasks': [{'task_id': 'task-1', 'dependencies': [], 'estimated_duration_ms': 60000}],
            'execution_order': ['task-1'],
            'risk_band': 'high'
        }
        set_activity_dependencies(kafka_producer=None, mongodb_client=None)

        tickets = await generate_execution_tickets(high_plan, consolidated_decision)

        assert tickets[0]['sla']['max_retries'] == 3

    @pytest.mark.asyncio
    async def test_qos_critical_uses_exactly_once(
        self, mock_activity_info, consolidated_decision
    ):
        """risk_band 'critical' deve usar delivery_mode EXACTLY_ONCE e consistency STRONG."""
        critical_plan = {
            'plan_id': 'plan-critical',
            'intent_id': 'intent-critical',
            'tasks': [{'task_id': 'task-1', 'dependencies': []}],
            'execution_order': ['task-1'],
            'risk_band': 'critical'
        }
        set_activity_dependencies(kafka_producer=None, mongodb_client=None)

        tickets = await generate_execution_tickets(critical_plan, consolidated_decision)

        assert tickets[0]['qos']['delivery_mode'] == 'EXACTLY_ONCE'
        assert tickets[0]['qos']['consistency'] == 'STRONG'

    @pytest.mark.asyncio
    async def test_qos_low_uses_at_least_once(
        self, mock_activity_info, simple_plan, consolidated_decision
    ):
        """risk_band 'low' deve usar delivery_mode AT_LEAST_ONCE."""
        set_activity_dependencies(kafka_producer=None, mongodb_client=None)

        tickets = await generate_execution_tickets(simple_plan, consolidated_decision)

        assert tickets[0]['qos']['delivery_mode'] == 'AT_LEAST_ONCE'
        assert tickets[0]['qos']['consistency'] == 'EVENTUAL'


class TestAllocateResources:
    """Testes para allocate_resources activity."""

    @pytest.mark.asyncio
    async def test_allocate_with_intelligent_scheduler(
        self, mock_activity_info, mock_intelligent_scheduler
    ):
        """Alocação com Intelligent Scheduler deve adicionar allocation_metadata."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'risk_band': 'medium',
            'status': 'PENDING'
        }
        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            intelligent_scheduler=mock_intelligent_scheduler,
            policy_validator=None,
            config=None
        )

        result = await allocate_resources(ticket)

        assert 'allocation_metadata' in result
        assert result['allocation_metadata']['allocation_method'] == 'intelligent_scheduler'
        assert result['allocation_metadata']['agent_id'] == 'worker-agent-001'

    @pytest.mark.asyncio
    async def test_allocate_fallback_stub_when_scheduler_unavailable(
        self, mock_activity_info
    ):
        """Sem scheduler, deve usar alocação stub com fallback."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'risk_band': 'medium',
            'status': 'PENDING'
        }
        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            intelligent_scheduler=None,  # Sem scheduler
            policy_validator=None,
            config=None
        )

        result = await allocate_resources(ticket)

        assert 'allocation_metadata' in result
        assert result['allocation_metadata']['allocation_method'] == 'fallback_stub'
        assert result['allocation_metadata']['agent_id'] == 'worker-agent-pool'

    @pytest.mark.asyncio
    async def test_allocate_with_opa_validation(
        self, mock_activity_info, mock_policy_validator, mock_config
    ):
        """Validação OPA deve ser executada antes da alocação."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'risk_band': 'medium',
            'status': 'PENDING'
        }
        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            intelligent_scheduler=None,
            policy_validator=mock_policy_validator,
            config=mock_config
        )

        result = await allocate_resources(ticket)

        mock_policy_validator.validate_execution_ticket.assert_called_once()
        assert 'metadata' in result
        assert 'policy_decisions' in result['metadata']

    @pytest.mark.asyncio
    async def test_allocate_rejects_on_opa_violation(
        self, mock_activity_info, mock_config
    ):
        """Violação de política OPA deve rejeitar alocação."""
        mock_validator = AsyncMock()
        violation = MagicMock()
        violation.policy_name = 'security-policy'
        violation.rule = 'deny-high-risk'
        violation.message = 'High risk not allowed'

        result_obj = MagicMock()
        result_obj.valid = False
        result_obj.violations = [violation]
        result_obj.warnings = []
        result_obj.policy_decisions = {}
        mock_validator.validate_execution_ticket.return_value = result_obj

        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'risk_band': 'critical',
            'status': 'PENDING'
        }
        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            intelligent_scheduler=None,
            policy_validator=mock_validator,
            config=mock_config
        )

        with pytest.raises(RuntimeError, match='rejeitado por políticas'):
            await allocate_resources(ticket)


class TestPublishTicketToKafka:
    """Testes para publish_ticket_to_kafka activity."""

    @pytest.fixture
    def mock_config_publish(self):
        """Config mock para testes de publish_ticket_to_kafka."""
        config = MagicMock()
        config.MONGODB_FAIL_OPEN_EXECUTION_TICKETS = False
        return config

    @pytest.mark.asyncio
    async def test_publish_valid_ticket(
        self, mock_activity_info, mock_kafka_producer, mock_mongodb_client, mock_config_publish
    ):
        """Ticket válido deve ser publicado no Kafka."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }
        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            config=mock_config_publish
        )

        result = await publish_ticket_to_kafka(ticket)

        assert result['published'] is True
        assert result['ticket_id'] == ticket['ticket_id']
        assert 'kafka_offset' in result
        mock_kafka_producer.publish_ticket.assert_called_once()
        mock_mongodb_client.save_execution_ticket.assert_called_once()

        # Verificar que o ticket foi publicado com status PENDING
        published_ticket = mock_kafka_producer.publish_ticket.call_args[0][0]
        assert published_ticket['status'] == 'PENDING', "Ticket deve ser publicado com status PENDING"

        # Verificar que o ticket foi persistido com status PENDING
        saved_ticket = mock_mongodb_client.save_execution_ticket.call_args[0][0]
        assert saved_ticket['status'] == 'PENDING', "Ticket deve ser persistido com status PENDING"

    @pytest.mark.asyncio
    async def test_rejected_ticket_not_published(
        self, mock_activity_info, mock_kafka_producer, mock_mongodb_client, mock_config_publish
    ):
        """Ticket rejeitado não deve ser publicado no Kafka."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'rejected',
            'allocation_metadata': None,
            'rejection_metadata': {
                'rejection_reason': 'policy_violation',
                'rejection_message': 'Security policy violated'
            }
        }
        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            config=mock_config_publish
        )

        result = await publish_ticket_to_kafka(ticket)

        assert result['published'] is False
        assert result['rejected'] is True
        assert result['rejection_reason'] == 'policy_violation'
        mock_kafka_producer.publish_ticket.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_persists_to_mongodb(
        self, mock_activity_info, mock_kafka_producer, mock_mongodb_client, mock_config_publish
    ):
        """Ticket publicado deve ser persistido no MongoDB."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }
        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            config=mock_config_publish
        )

        await publish_ticket_to_kafka(ticket)

        mock_mongodb_client.save_execution_ticket.assert_called_once()

        # Verificar que o ticket persistido mantém status PENDING
        saved_ticket = mock_mongodb_client.save_execution_ticket.call_args[0][0]
        assert saved_ticket['status'] == 'PENDING'

    @pytest.mark.asyncio
    async def test_publish_raises_when_kafka_unavailable(self, mock_activity_info, mock_config_publish):
        """Publicação deve falhar quando Kafka producer não disponível."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }
        set_activity_dependencies(
            kafka_producer=None,  # Sem producer
            mongodb_client=None,
            config=mock_config_publish
        )

        with pytest.raises(RuntimeError, match='Kafka producer'):
            await publish_ticket_to_kafka(ticket)

    @pytest.mark.asyncio
    async def test_publish_maintains_pending_status(
        self, mock_activity_info, mock_kafka_producer, mock_mongodb_client, mock_config_publish
    ):
        """Ticket com status PENDING deve manter o status após publicação."""
        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }
        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb_client,
            config=mock_config_publish
        )

        result = await publish_ticket_to_kafka(ticket)

        # Verificar que o status não foi alterado para RUNNING
        assert result['ticket']['status'] == 'PENDING'

        # Verificar que o ticket publicado no Kafka tem status PENDING
        published_ticket = mock_kafka_producer.publish_ticket.call_args[0][0]
        assert published_ticket['status'] == 'PENDING'

        # Verificar que o ticket persistido no MongoDB tem status PENDING
        saved_ticket = mock_mongodb_client.save_execution_ticket.call_args[0][0]
        assert saved_ticket['status'] == 'PENDING'


class TestSLATimeoutConfiguration:
    """Testes para configuração de timeout de SLA."""

    @pytest.mark.asyncio
    async def test_timeout_uses_configured_minimum(
        self, mock_activity_info, consolidated_decision
    ):
        """Timeout deve respeitar o mínimo configurado."""
        # Configurar mock com valores customizados
        mock_cfg = MagicMock()
        mock_cfg.sla_ticket_min_timeout_ms = 90000  # 90 segundos
        mock_cfg.sla_ticket_timeout_buffer_multiplier = 3.0

        plan = {
            'plan_id': 'plan-timeout-test',
            'intent_id': 'intent-timeout-test',
            'tasks': [{
                'task_id': 'task-1',
                'dependencies': [],
                'estimated_duration_ms': 10000  # 10s (menor que mínimo)
            }],
            'execution_order': ['task-1'],
            'risk_band': 'medium'
        }

        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            config=mock_cfg
        )

        tickets = await generate_execution_tickets(plan, consolidated_decision)

        # Timeout deve ser o mínimo configurado (90s), não 10s * 3.0 = 30s
        assert tickets[0]['sla']['timeout_ms'] == 90000

    @pytest.mark.asyncio
    async def test_timeout_uses_configured_multiplier(
        self, mock_activity_info, consolidated_decision
    ):
        """Timeout deve usar multiplicador configurado."""
        mock_cfg = MagicMock()
        mock_cfg.sla_ticket_min_timeout_ms = 60000  # 60 segundos
        mock_cfg.sla_ticket_timeout_buffer_multiplier = 4.0  # 4x buffer

        plan = {
            'plan_id': 'plan-multiplier-test',
            'intent_id': 'intent-multiplier-test',
            'tasks': [{
                'task_id': 'task-1',
                'dependencies': [],
                'estimated_duration_ms': 30000  # 30s
            }],
            'execution_order': ['task-1'],
            'risk_band': 'medium'
        }

        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            config=mock_cfg
        )

        tickets = await generate_execution_tickets(plan, consolidated_decision)

        # Timeout deve ser 30s * 4.0 = 120s (maior que mínimo de 60s)
        assert tickets[0]['sla']['timeout_ms'] == 120000

    @pytest.mark.asyncio
    async def test_timeout_defaults_when_config_unavailable(
        self, mock_activity_info, consolidated_decision
    ):
        """Timeout deve usar defaults quando config não disponível."""
        plan = {
            'plan_id': 'plan-default-test',
            'intent_id': 'intent-default-test',
            'tasks': [{
                'task_id': 'task-1',
                'dependencies': [],
                'estimated_duration_ms': 10000  # 10s
            }],
            'execution_order': ['task-1'],
            'risk_band': 'medium'
        }

        set_activity_dependencies(
            kafka_producer=None,
            mongodb_client=None,
            config=None  # Sem config
        )

        tickets = await generate_execution_tickets(plan, consolidated_decision)

        # Deve usar defaults: max(60000, 10000 * 3.0) = 60000
        assert tickets[0]['sla']['timeout_ms'] == 60000


class TestMongoDBPersistenceFailOpen:
    """Testes para configuração fail-open de persistência MongoDB."""

    @pytest.mark.asyncio
    async def test_publish_propagates_persistence_error_when_fail_open_disabled(
        self, mock_activity_info, mock_kafka_producer
    ):
        """publish_ticket_to_kafka deve propagar erros quando fail-open=False."""
        mock_mongodb = AsyncMock()
        mock_mongodb.save_execution_ticket = AsyncMock(
            side_effect=PyMongoError('Database error')
        )

        mock_cfg = MagicMock()
        mock_cfg.MONGODB_FAIL_OPEN_EXECUTION_TICKETS = False

        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }

        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb,
            config=mock_cfg
        )

        with pytest.raises(RuntimeError, match='Falha crítica na persistência'):
            await publish_ticket_to_kafka(ticket)

    @pytest.mark.asyncio
    async def test_publish_continues_when_fail_open_enabled(
        self, mock_activity_info, mock_kafka_producer
    ):
        """publish_ticket_to_kafka deve continuar quando fail-open=True."""
        mock_mongodb = AsyncMock()
        mock_mongodb.save_execution_ticket = AsyncMock(
            side_effect=PyMongoError('Database error')
        )

        mock_cfg = MagicMock()
        mock_cfg.MONGODB_FAIL_OPEN_EXECUTION_TICKETS = True

        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }

        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb,
            config=mock_cfg
        )

        result = await publish_ticket_to_kafka(ticket)

        # Deve continuar com publicação mesmo com erro de persistência
        assert result['published'] is True
        assert result['ticket_id'] == ticket['ticket_id']
        mock_kafka_producer.publish_ticket.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_handles_circuit_breaker_error(
        self, mock_activity_info, mock_kafka_producer
    ):
        """Circuit breaker aberto deve propagar RuntimeError para retry do Temporal."""
        mock_mongodb = AsyncMock()
        mock_mongodb.save_execution_ticket = AsyncMock(
            side_effect=CircuitBreakerError('Circuit breaker is open')
        )

        mock_cfg = MagicMock()
        mock_cfg.MONGODB_FAIL_OPEN_EXECUTION_TICKETS = False

        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }

        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb,
            config=mock_cfg
        )

        # Circuit breaker aberto indica problema sistêmico - deve propagar RuntimeError
        # para que o Temporal possa fazer retry quando o circuit breaker fechar
        with pytest.raises(RuntimeError, match='Circuit breaker aberto'):
            await publish_ticket_to_kafka(ticket)

        # Kafka publish foi chamado antes da persistência falhar
        mock_kafka_producer.publish_ticket.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_raises_when_config_unavailable(
        self, mock_activity_info, mock_kafka_producer
    ):
        """Deve falhar quando config não foi injetado."""
        mock_mongodb = AsyncMock()
        mock_mongodb.save_execution_ticket = AsyncMock()

        ticket = {
            'ticket_id': str(uuid.uuid4()),
            'plan_id': 'plan-001',
            'status': 'PENDING',
            'allocation_metadata': {'agent_id': 'worker-001'}
        }

        set_activity_dependencies(
            kafka_producer=mock_kafka_producer,
            mongodb_client=mock_mongodb,
            config=None  # Sem config
        )

        # Sem config, deve propagar erro de configuração
        with pytest.raises(RuntimeError, match='Config não foi injetado'):
            await publish_ticket_to_kafka(ticket)
