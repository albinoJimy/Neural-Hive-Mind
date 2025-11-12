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
