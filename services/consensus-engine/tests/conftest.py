"""
Fixtures compartilhadas para testes do consensus-engine.

Fornece fixtures reutilizáveis para testes do consensus-engine, seguindo o padrão
estabelecido em libraries/python/neural_hive_specialists/tests/conftest.py.
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime, timezone
import uuid

from google.protobuf.timestamp_pb2 import Timestamp
from neural_hive_specialists.proto_gen import specialist_pb2, specialist_pb2_grpc


# ===========================
# Fixtures de Configuração
# ===========================

@pytest.fixture
def mock_consensus_config():
    """Configuração mock para o consensus-engine."""
    config = MagicMock()
    config.specialist_business_endpoint = "specialist-business.neural-hive.svc.cluster.local:50051"
    config.specialist_technical_endpoint = "specialist-technical.neural-hive.svc.cluster.local:50051"
    config.specialist_behavior_endpoint = "specialist-behavior.neural-hive.svc.cluster.local:50051"
    config.specialist_evolution_endpoint = "specialist-evolution.neural-hive.svc.cluster.local:50051"
    config.specialist_architecture_endpoint = "specialist-architecture.neural-hive.svc.cluster.local:50051"
    config.grpc_timeout_ms = 5000
    config.grpc_max_retries = 3
    # Timeouts específicos por specialist (None = usa grpc_timeout_ms)
    config.specialist_business_timeout_ms = None
    config.specialist_technical_timeout_ms = None
    config.specialist_behavior_timeout_ms = None
    config.specialist_evolution_timeout_ms = None
    config.specialist_architecture_timeout_ms = None

    def get_specialist_timeout_ms(specialist_type: str) -> int:
        """Retorna timeout específico ou fallback para global."""
        timeout_field = f'specialist_{specialist_type}_timeout_ms'
        specific_timeout = getattr(config, timeout_field, None)
        return specific_timeout if specific_timeout is not None else config.grpc_timeout_ms

    config.get_specialist_timeout_ms = get_specialist_timeout_ms
    return config


@pytest.fixture
def mock_consensus_config_with_specific_timeouts():
    """Configuração mock com timeouts específicos por specialist."""
    config = MagicMock()
    config.specialist_business_endpoint = "specialist-business.neural-hive.svc.cluster.local:50051"
    config.specialist_technical_endpoint = "specialist-technical.neural-hive.svc.cluster.local:50051"
    config.specialist_behavior_endpoint = "specialist-behavior.neural-hive.svc.cluster.local:50051"
    config.specialist_evolution_endpoint = "specialist-evolution.neural-hive.svc.cluster.local:50051"
    config.specialist_architecture_endpoint = "specialist-architecture.neural-hive.svc.cluster.local:50051"
    config.grpc_timeout_ms = 30000  # 30s padrão
    config.grpc_max_retries = 3
    # Business Specialist com timeout específico de 120s (ML pesado)
    config.specialist_business_timeout_ms = 120000
    # Outros usam fallback
    config.specialist_technical_timeout_ms = None
    config.specialist_behavior_timeout_ms = None
    config.specialist_evolution_timeout_ms = None
    config.specialist_architecture_timeout_ms = None

    def get_specialist_timeout_ms(specialist_type: str) -> int:
        """Retorna timeout específico ou fallback para global."""
        timeout_field = f'specialist_{specialist_type}_timeout_ms'
        specific_timeout = getattr(config, timeout_field, None)
        return specific_timeout if specific_timeout is not None else config.grpc_timeout_ms

    config.get_specialist_timeout_ms = get_specialist_timeout_ms
    return config


# ===========================
# Fixtures de Dados de Teste
# ===========================

@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo válido para testes."""
    return {
        "plan_id": str(uuid.uuid4()),
        "intent_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "original_domain": "BUSINESS",  # FIX BUG-002: Campo correto do schema Avro
        "version": "1.0",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Analyze business requirements",
                "dependencies": [],
                "estimated_effort": "medium"
            },
            {
                "task_id": "task-2",
                "description": "Design technical solution",
                "dependencies": ["task-1"],
                "estimated_effort": "high"
            }
        ],
        "risk_band": "medium",
        "requires_human_approval": False,
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "semantic-translation-engine"
        }
    }


@pytest.fixture
def cognitive_plan_without_correlation_id(sample_cognitive_plan):
    """Plano cognitivo sem correlation_id para testes de fallback."""
    plan = sample_cognitive_plan.copy()
    plan.pop('correlation_id', None)
    return plan


@pytest.fixture
def cognitive_plan_with_empty_correlation_id(sample_cognitive_plan):
    """Plano cognitivo com correlation_id vazio."""
    plan = sample_cognitive_plan.copy()
    plan['correlation_id'] = ''
    return plan


@pytest.fixture
def sample_trace_context():
    """Contexto de trace válido para testes."""
    return {
        "trace_id": str(uuid.uuid4()),
        "span_id": str(uuid.uuid4())
    }


@pytest.fixture
def valid_timestamp_protobuf():
    """Timestamp protobuf válido."""
    timestamp = Timestamp()
    timestamp.FromDatetime(datetime.now(timezone.utc))

    # Validar que timestamp está no formato correto
    assert timestamp.seconds > 0, "Timestamp seconds deve ser positivo"
    assert 0 <= timestamp.nanos < 1_000_000_000, "Timestamp nanos deve estar no range [0, 1e9)"

    return timestamp


@pytest.fixture
def valid_evaluate_plan_response(valid_timestamp_protobuf):
    """Response protobuf válida de EvaluatePlan."""
    response = specialist_pb2.EvaluatePlanResponse(
        opinion_id=str(uuid.uuid4()),
        specialist_type="business",
        specialist_version="1.0.9",
        opinion="APPROVE",
        confidence=0.95,
        reasoning="Plan aligns with business objectives and shows clear ROI.",
        processing_time_ms=150
    )

    # Adicionar timestamp válido
    response.evaluated_at.CopyFrom(valid_timestamp_protobuf)

    # Adicionar risks e mitigations
    risk = response.risks.add()
    risk.risk_id = "risk-1"
    risk.description = "Potential timeline overrun"
    risk.severity = "MEDIUM"
    risk.probability = 0.3

    mitigation = response.mitigations.add()
    mitigation.mitigation_id = "mit-1"
    mitigation.for_risk_id = "risk-1"
    mitigation.description = "Add buffer time to schedule"
    mitigation.effectiveness = 0.8

    return response


@pytest.fixture
def invalid_timestamp_dict():
    """Dict simulando desserialização incorreta de timestamp."""
    return {'seconds': 123, 'nanos': 456}


@pytest.fixture
def invalid_timestamp_negative_seconds():
    """Timestamp com seconds negativos."""
    timestamp = Timestamp()
    timestamp.seconds = -1
    timestamp.nanos = 0
    return timestamp


@pytest.fixture
def invalid_timestamp_out_of_range_nanos():
    """Timestamp com nanos fora do range válido."""
    timestamp = Timestamp()
    timestamp.seconds = 1705320645
    timestamp.nanos = 1_000_000_000  # >= 1e9 é inválido
    return timestamp


# ===========================
# Fixtures de Mocks gRPC
# ===========================

@pytest.fixture
def mock_grpc_channel():
    """Mock de canal gRPC."""
    channel = AsyncMock()
    return channel


@pytest.fixture
def mock_grpc_stub():
    """Mock de stub gRPC."""
    stub = AsyncMock(spec=specialist_pb2_grpc.SpecialistServiceStub)
    stub.EvaluatePlan = AsyncMock()
    stub.GetCapabilities = AsyncMock()
    return stub


@pytest.fixture
def mock_specialists_grpc_client(mock_consensus_config):
    """Cliente gRPC mock para testes."""
    from src.clients.specialists_grpc_client import SpecialistsGrpcClient

    client = SpecialistsGrpcClient(config=mock_consensus_config)

    # client.stubs será populado nos testes individuais conforme necessário

    return client


# ===========================
# Fixtures de Respostas Múltiplas
# ===========================

@pytest.fixture
def multiple_valid_responses(valid_timestamp_protobuf):
    """Lista de responses válidas de múltiplos specialists."""
    specialist_types = ["business", "technical", "behavior", "evolution", "architecture"]
    responses = []

    for i, spec_type in enumerate(specialist_types):
        response = specialist_pb2.EvaluatePlanResponse(
            opinion_id=f"op-{i}-{uuid.uuid4()}",
            specialist_type=spec_type,
            specialist_version="1.0.9",
            opinion="APPROVE" if i % 2 == 0 else "NEEDS_REVISION",
            confidence=0.85 + (i * 0.02),
            reasoning=f"Opinion from {spec_type} specialist",
            processing_time_ms=100 + (i * 20)
        )

        # Adicionar timestamp válido
        timestamp = Timestamp()
        timestamp.FromDatetime(datetime.now(timezone.utc))
        response.evaluated_at.CopyFrom(timestamp)

        responses.append(response)

    return responses


# ===========================
# Fixtures para ConsensusOrchestrator
# ===========================

@pytest.fixture
def mock_consensus_orchestrator_config():
    """Configuração mock para o ConsensusOrchestrator."""
    config = MagicMock()
    config.min_confidence_score = 0.7
    config.max_divergence_threshold = 0.3
    config.critical_risk_threshold = 0.8
    config.enable_pheromones = False
    config.enable_bayesian_averaging = True
    return config


@pytest.fixture
def mock_pheromone_client():
    """Cliente de feromônios mock."""
    client = AsyncMock()
    client.calculate_dynamic_weight = AsyncMock(return_value=0.2)
    client.get_aggregated_pheromone = AsyncMock(return_value={'net_strength': 0.5})
    client.publish_pheromone = AsyncMock()
    return client


@pytest.fixture
def sample_specialist_opinions():
    """Lista de 5 opiniões válidas de especialistas para testes de consenso."""
    return [
        {
            'specialist_type': 'business',
            'opinion_id': str(uuid.uuid4()),
            'opinion': {
                'confidence_score': 0.85,
                'risk_score': 0.2,
                'recommendation': 'approve'
            },
            'processing_time_ms': 100
        },
        {
            'specialist_type': 'technical',
            'opinion_id': str(uuid.uuid4()),
            'opinion': {
                'confidence_score': 0.88,
                'risk_score': 0.15,
                'recommendation': 'approve'
            },
            'processing_time_ms': 120
        },
        {
            'specialist_type': 'behavior',
            'opinion_id': str(uuid.uuid4()),
            'opinion': {
                'confidence_score': 0.82,
                'risk_score': 0.18,
                'recommendation': 'approve'
            },
            'processing_time_ms': 90
        },
        {
            'specialist_type': 'evolution',
            'opinion_id': str(uuid.uuid4()),
            'opinion': {
                'confidence_score': 0.90,
                'risk_score': 0.12,
                'recommendation': 'approve'
            },
            'processing_time_ms': 110
        },
        {
            'specialist_type': 'architecture',
            'opinion_id': str(uuid.uuid4()),
            'opinion': {
                'confidence_score': 0.87,
                'risk_score': 0.16,
                'recommendation': 'approve'
            },
            'processing_time_ms': 130
        }
    ]


# ===========================
# Fixtures para Testes de Resiliência do Consumer
# ===========================

@pytest.fixture
def mock_config_with_resilience():
    """Configuração mock com parâmetros de resiliência para testes rápidos."""
    config = MagicMock()
    # Configurações básicas do consumer
    config.kafka_plans_topic = 'plans.ready'
    config.kafka_bootstrap_servers = 'localhost:9092'
    config.kafka_consumer_group_id = 'consensus-engine-test'
    config.kafka_auto_offset_reset = 'earliest'
    config.kafka_enable_auto_commit = False
    config.enable_parallel_invocation = True
    config.grpc_timeout_ms = 5000
    # Parâmetros de resiliência (valores menores para testes rápidos)
    config.consumer_max_consecutive_errors = 5
    config.consumer_base_backoff_seconds = 0.1
    config.consumer_max_backoff_seconds = 1.0
    config.consumer_poll_timeout_seconds = 0.5
    config.consumer_enable_dlq = False
    config.kafka_dlq_topic = 'plans.ready.dlq'
    config.consumer_max_retries_before_dlq = 2
    # Timeouts específicos por specialist
    config.specialist_business_timeout_ms = None
    config.specialist_technical_timeout_ms = None
    config.specialist_behavior_timeout_ms = None
    config.specialist_evolution_timeout_ms = None
    config.specialist_architecture_timeout_ms = None

    def get_specialist_timeout_ms(specialist_type: str) -> int:
        """Retorna timeout específico ou fallback para global."""
        timeout_field = f'specialist_{specialist_type}_timeout_ms'
        specific_timeout = getattr(config, timeout_field, None)
        return specific_timeout if specific_timeout is not None else config.grpc_timeout_ms

    config.get_specialist_timeout_ms = get_specialist_timeout_ms
    return config


@pytest.fixture
def mock_kafka_message_success():
    """Mock de mensagem Kafka com sucesso."""
    msg = MagicMock()
    msg.error.return_value = None
    msg.value.return_value = b'{"plan_id": "test-123", "intent_id": "int-123"}'
    msg.topic.return_value = 'plans.ready'
    msg.partition.return_value = 0
    msg.offset.return_value = 1
    return msg


@pytest.fixture
def mock_kafka_message_with_error():
    """Mock de mensagem Kafka com erro."""
    from confluent_kafka import KafkaError
    msg = MagicMock()
    error = MagicMock()
    error.code.return_value = KafkaError._ALL_BROKERS_DOWN
    msg.error.return_value = error
    msg.topic.return_value = 'plans.ready'
    msg.partition.return_value = 0
    msg.offset.return_value = 1
    return msg


@pytest.fixture
def systemic_error_examples():
    """Lista de erros sistêmicos para testes."""
    return [
        ConnectionError('gRPC unavailable'),
        TimeoutError('Request timeout'),
        OSError('Network unreachable')
    ]


@pytest.fixture
def business_error_examples():
    """Lista de erros de negócio para testes."""
    return [
        ValueError('Invalid plan format'),
        KeyError('Missing required field'),
        TypeError('Wrong type')
    ]


# ===========================
# Configuração pytest
# ===========================

def pytest_configure(config):
    """Configurar markers customizados."""
    config.addinivalue_line(
        "markers", "unit: marca testes unitários"
    )
    config.addinivalue_line(
        "markers", "integration: marca testes de integração"
    )
    config.addinivalue_line(
        "markers", "asyncio: marca testes assíncronos"
    )
