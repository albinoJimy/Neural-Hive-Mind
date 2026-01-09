"""
Testes unitários para activities de consolidação de resultados.

Testes cobrem:
- consolidate_results com tickets completados e falhados
- Cálculo de success_rate
- Detecção de SLA violations
- Cálculo de erro ML (predicted vs actual duration)
- Publicação de alertas via Kafka
- trigger_self_healing com diferentes tipos de incidentes
- publish_telemetry e buffer_telemetry (fail-open)
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.activities.result_consolidation import (
    consolidate_results,
    trigger_self_healing,
    publish_telemetry,
    buffer_telemetry,
    compute_and_record_ml_error,
    set_activity_dependencies
)


@pytest.fixture
def mock_activity_info():
    """Mock activity.info() para contexto de workflow."""
    with patch('src.activities.result_consolidation.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'test-workflow-123'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


@pytest.fixture
def mock_config():
    """Criar mock de configuração."""
    config = MagicMock()
    config.sla_management_enabled = False
    config.ml_allocation_outcomes_enabled = False
    config.self_healing_enabled = True
    config.self_healing_engine_url = 'http://self-healing:8080'
    config.self_healing_timeout_seconds = 30
    return config


@pytest.fixture
def mock_mongodb_client():
    """Criar mock de MongoDB client."""
    client = AsyncMock()
    client.save_workflow_result = AsyncMock()
    client.save_incident = AsyncMock()
    client.save_telemetry_buffer = AsyncMock()
    return client


@pytest.fixture
def mock_kafka_producer():
    """Criar mock de Kafka producer."""
    producer = AsyncMock()
    producer.publish_incident_avro = AsyncMock(return_value=True)
    producer.initialize = AsyncMock()
    return producer


@pytest.fixture
def mock_metrics():
    """Criar mock de métricas."""
    metrics = MagicMock()
    metrics.record_ml_prediction_error_with_logging = MagicMock()
    metrics.record_ml_prediction_accuracy = MagicMock()
    metrics.record_self_healing_triggered = MagicMock()
    return metrics


@pytest.fixture
def successful_tickets():
    """Lista de tickets completados com sucesso."""
    return [
        {
            'ticket': {
                'ticket_id': 'ticket-1',
                'plan_id': 'plan-001',
                'intent_id': 'intent-001',
                'status': 'COMPLETED',
                'estimated_duration_ms': 60000,
                'actual_duration_ms': 55000,
                'retry_count': 0,
                'sla': {'timeout_ms': 120000, 'deadline': 1704067200000}
            }
        },
        {
            'ticket': {
                'ticket_id': 'ticket-2',
                'plan_id': 'plan-001',
                'intent_id': 'intent-001',
                'status': 'COMPLETED',
                'estimated_duration_ms': 45000,
                'actual_duration_ms': 48000,
                'retry_count': 0,
                'sla': {'timeout_ms': 90000, 'deadline': 1704067200000}
            }
        }
    ]


@pytest.fixture
def mixed_tickets():
    """Lista de tickets com sucesso, falha e compensados."""
    return [
        {
            'ticket': {
                'ticket_id': 'ticket-1',
                'plan_id': 'plan-001',
                'intent_id': 'intent-001',
                'status': 'COMPLETED',
                'estimated_duration_ms': 60000,
                'retry_count': 0
            }
        },
        {
            'ticket': {
                'ticket_id': 'ticket-2',
                'plan_id': 'plan-001',
                'intent_id': 'intent-001',
                'status': 'FAILED',
                'estimated_duration_ms': 45000,
                'actual_duration_ms': 150000,  # Excedeu timeout
                'retry_count': 3,
                'sla': {'timeout_ms': 90000, 'deadline': 1704067200000}
            }
        },
        {
            'ticket': {
                'ticket_id': 'ticket-3',
                'plan_id': 'plan-001',
                'intent_id': 'intent-001',
                'status': 'COMPENSATED',
                'estimated_duration_ms': 30000,
                'retry_count': 1
            }
        }
    ]


class TestConsolidateResults:
    """Testes para consolidate_results activity."""

    @pytest.mark.asyncio
    async def test_all_successful_returns_success_status(
        self, mock_activity_info, successful_tickets, mock_config
    ):
        """Todos tickets completados devem retornar status SUCCESS."""
        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            set_activity_dependencies(config=mock_config)

            result = await consolidate_results(successful_tickets, 'workflow-001')

            assert result['status'] == 'SUCCESS'
            assert result['metrics']['successful_tickets'] == 2
            assert result['metrics']['failed_tickets'] == 0
            assert result['consistent'] is True

    @pytest.mark.asyncio
    async def test_majority_failed_returns_failed_status(
        self, mock_activity_info, mock_config
    ):
        """Maioria de tickets falhados deve retornar status FAILED."""
        failed_tickets = [
            {'ticket': {'ticket_id': 't1', 'status': 'FAILED', 'estimated_duration_ms': 1000}},
            {'ticket': {'ticket_id': 't2', 'status': 'FAILED', 'estimated_duration_ms': 1000}},
            {'ticket': {'ticket_id': 't3', 'status': 'COMPLETED', 'estimated_duration_ms': 1000}}
        ]
        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            set_activity_dependencies(config=mock_config)

            result = await consolidate_results(failed_tickets, 'workflow-001')

            assert result['status'] == 'FAILED'

    @pytest.mark.asyncio
    async def test_mixed_results_returns_partial_status(
        self, mock_activity_info, mixed_tickets, mock_config
    ):
        """Resultados mistos devem retornar status PARTIAL."""
        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            set_activity_dependencies(config=mock_config)

            result = await consolidate_results(mixed_tickets, 'workflow-001')

            assert result['status'] == 'PARTIAL'
            assert result['metrics']['successful_tickets'] == 1
            assert result['metrics']['failed_tickets'] == 1
            assert result['metrics']['compensated_tickets'] == 1

    @pytest.mark.asyncio
    async def test_invalid_status_marks_inconsistent(
        self, mock_activity_info, mock_config
    ):
        """Tickets com status inválido devem marcar resultado como inconsistente."""
        invalid_tickets = [
            {'ticket': {'ticket_id': 't1', 'status': 'INVALID_STATUS', 'estimated_duration_ms': 1000}}
        ]
        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            set_activity_dependencies(config=mock_config)

            result = await consolidate_results(invalid_tickets, 'workflow-001')

            assert result['consistent'] is False
            assert len(result['errors']) > 0
            assert any('inválido' in e.lower() or 'invalid' in e.lower() for e in result['errors'])

    @pytest.mark.asyncio
    async def test_calculates_total_duration_and_retries(
        self, mock_activity_info, mixed_tickets, mock_config
    ):
        """Deve calcular duração total e número de retries corretamente."""
        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            set_activity_dependencies(config=mock_config)

            result = await consolidate_results(mixed_tickets, 'workflow-001')

            assert result['metrics']['total_duration_ms'] == 135000  # 60000 + 45000 + 30000
            assert result['metrics']['total_retries'] == 4  # 0 + 3 + 1

    @pytest.mark.asyncio
    async def test_persists_result_to_mongodb(
        self, mock_activity_info, successful_tickets, mock_config, mock_mongodb_client
    ):
        """Resultado deve ser persistido no MongoDB."""
        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            set_activity_dependencies(config=mock_config, mongodb_client=mock_mongodb_client)

            await consolidate_results(successful_tickets, 'workflow-001')

            mock_mongodb_client.save_workflow_result.assert_called_once()


class TestComputeAndRecordMlError:
    """Testes para compute_and_record_ml_error."""

    def test_computes_error_correctly(self, mock_metrics):
        """Deve calcular erro ML corretamente (actual - predicted)."""
        ticket = {
            'ticket_id': 'ticket-1',
            'actual_duration_ms': 65000,
            'allocation_metadata': {
                'predicted_duration_ms': 60000
            }
        }

        compute_and_record_ml_error(ticket, mock_metrics)

        # error_ms = 65000 - 60000 = 5000
        mock_metrics.record_ml_prediction_error_with_logging.assert_called_once()
        call_kwargs = mock_metrics.record_ml_prediction_error_with_logging.call_args
        assert call_kwargs[1]['error_ms'] == 5000

    def test_skips_when_no_actual_duration(self, mock_metrics):
        """Deve pular quando actual_duration_ms não disponível."""
        ticket = {
            'ticket_id': 'ticket-1',
            'actual_duration_ms': None,
            'allocation_metadata': {
                'predicted_duration_ms': 60000
            }
        }

        compute_and_record_ml_error(ticket, mock_metrics)

        mock_metrics.record_ml_prediction_error_with_logging.assert_not_called()

    def test_uses_estimated_when_no_prediction(self, mock_metrics):
        """Deve usar estimated_duration_ms como fallback se não houver predição ML."""
        ticket = {
            'ticket_id': 'ticket-1',
            'actual_duration_ms': 55000,
            'estimated_duration_ms': 60000,
            'allocation_metadata': {}  # Sem predicted_duration_ms
        }

        compute_and_record_ml_error(ticket, mock_metrics)

        mock_metrics.record_ml_prediction_error_with_logging.assert_called_once()


class TestTriggerSelfHealing:
    """Testes para trigger_self_healing activity."""

    @pytest.mark.asyncio
    async def test_infers_timeout_incident_type(
        self, mock_activity_info, mock_config, mock_kafka_producer
    ):
        """Deve inferir tipo TICKET_TIMEOUT de inconsistências com timeout."""
        inconsistencies = ['Ticket expirou por timeout', 'Deadline excedido']

        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            with patch('src.activities.result_consolidation.KafkaProducerClient', return_value=mock_kafka_producer):
                set_activity_dependencies(config=mock_config, kafka_producer=mock_kafka_producer)

                await trigger_self_healing('workflow-001', inconsistencies)

                # Verificar que incident_event foi criado com tipo correto
                mock_kafka_producer.publish_incident_avro.assert_called_once()
                call_args = mock_kafka_producer.publish_incident_avro.call_args[0][0]
                assert call_args['incident_type'] == 'TICKET_TIMEOUT'

    @pytest.mark.asyncio
    async def test_infers_worker_failure_incident_type(
        self, mock_activity_info, mock_config, mock_kafka_producer
    ):
        """Deve inferir tipo WORKER_FAILURE de inconsistências com worker."""
        inconsistencies = ['Worker não responde', 'Worker unhealthy']

        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            with patch('src.activities.result_consolidation.KafkaProducerClient', return_value=mock_kafka_producer):
                set_activity_dependencies(config=mock_config, kafka_producer=mock_kafka_producer)

                await trigger_self_healing('workflow-001', inconsistencies)

                call_args = mock_kafka_producer.publish_incident_avro.call_args[0][0]
                assert call_args['incident_type'] == 'WORKER_FAILURE'

    @pytest.mark.asyncio
    async def test_infers_sla_violation_incident_type(
        self, mock_activity_info, mock_config, mock_kafka_producer
    ):
        """Deve inferir tipo SLA_VIOLATION de inconsistências com SLA."""
        inconsistencies = ['SLA violado', 'Violation detectada']

        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            with patch('src.activities.result_consolidation.KafkaProducerClient', return_value=mock_kafka_producer):
                set_activity_dependencies(config=mock_config, kafka_producer=mock_kafka_producer)

                await trigger_self_healing('workflow-001', inconsistencies)

                call_args = mock_kafka_producer.publish_incident_avro.call_args[0][0]
                assert call_args['incident_type'] == 'SLA_VIOLATION'

    @pytest.mark.asyncio
    async def test_buffers_to_mongodb_when_kafka_fails(
        self, mock_activity_info, mock_config, mock_mongodb_client
    ):
        """Deve persistir no MongoDB quando Kafka falhar (fail-open)."""
        inconsistencies = ['Erro genérico']

        mock_kafka_producer = AsyncMock()
        mock_kafka_producer.publish_incident_avro = AsyncMock(return_value=False)  # Falha
        mock_kafka_producer.initialize = AsyncMock()

        with patch('src.activities.result_consolidation.get_settings', return_value=mock_config):
            with patch('src.activities.result_consolidation.KafkaProducerClient', return_value=mock_kafka_producer):
                set_activity_dependencies(
                    config=mock_config,
                    kafka_producer=mock_kafka_producer,
                    mongodb_client=mock_mongodb_client
                )

                await trigger_self_healing('workflow-001', inconsistencies)

                mock_mongodb_client.save_incident.assert_called_once()


class TestPublishTelemetry:
    """Testes para publish_telemetry activity."""

    @pytest.mark.asyncio
    async def test_creates_telemetry_frame_with_sla_metrics(self, mock_activity_info):
        """Deve criar telemetry frame com métricas de SLA."""
        workflow_result = {
            'workflow_id': 'workflow-001',
            'plan_id': 'plan-001',
            'intent_id': 'intent-001',
            'metrics': {'total_tickets': 2, 'successful_tickets': 2},
            'tickets_summary': [
                {'ticket_id': 't1'},
                {'ticket_id': 't2'}
            ],
            'sla_status': {
                'deadline_approaching': False,
                'budget_critical': False,
                'violations_count': 0
            },
            'sla_remaining_seconds': 3600,
            'budget_status': 'HEALTHY'
        }

        with patch('src.activities.result_consolidation.get_metrics') as mock_get_metrics:
            mock_metrics = MagicMock()
            mock_get_metrics.return_value = mock_metrics

            await publish_telemetry(workflow_result)

            # Não deve lançar exceção
            assert True


class TestBufferTelemetry:
    """Testes para buffer_telemetry activity."""

    @pytest.mark.asyncio
    async def test_buffers_telemetry_to_mongodb(
        self, mock_activity_info, mock_mongodb_client
    ):
        """Deve persistir telemetry frame no MongoDB."""
        telemetry_frame = {
            'correlation': {'workflow_id': 'workflow-001'},
            'metrics': {'total_tickets': 2}
        }
        set_activity_dependencies(mongodb_client=mock_mongodb_client)

        await buffer_telemetry(telemetry_frame)

        mock_mongodb_client.save_telemetry_buffer.assert_called_once()

    @pytest.mark.asyncio
    async def test_buffer_fail_open_when_mongodb_unavailable(self, mock_activity_info):
        """Deve não lançar exceção quando MongoDB indisponível (fail-open)."""
        telemetry_frame = {
            'correlation': {'workflow_id': 'workflow-001'},
            'metrics': {'total_tickets': 2}
        }
        set_activity_dependencies(mongodb_client=None)

        # Não deve lançar exceção
        await buffer_telemetry(telemetry_frame)
