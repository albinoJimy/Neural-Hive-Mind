"""
Configuração pytest e fixtures compartilhadas para testes do Semantic Translation Engine.

Este módulo fornece:
- Configuração de markers customizados
- Fixtures para settings mockados
- Fixtures para componentes do STE
- Fixtures para dados de teste
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock

import pytest


# ============================================================================
# Configuração de ambiente
# ============================================================================

KAFKA_BOOTSTRAP = os.getenv(
    'KAFKA_BOOTSTRAP',
    'neural-hive-kafka-bootstrap.neural-hive-kafka.svc.cluster.local:9092'
)
MONGODB_URI = os.getenv(
    'MONGODB_URI',
    'mongodb://mongodb-cluster.mongodb-cluster.svc.cluster.local:27017'
)
MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'neural_hive')
APPROVAL_SERVICE_URL = os.getenv(
    'APPROVAL_SERVICE_URL',
    'http://approval-service.neural-hive-orchestration.svc.cluster.local:8000'
)


# ============================================================================
# Configuração pytest
# ============================================================================

def pytest_configure(config: pytest.Config) -> None:
    """Configura pytest com markers customizados."""
    config.addinivalue_line(
        'markers',
        'e2e: Testes end-to-end que requerem infraestrutura completa'
    )
    config.addinivalue_line(
        'markers',
        'slow: Testes que levam mais de 30 segundos'
    )
    config.addinivalue_line(
        'markers',
        'approval_flow: Testes específicos do fluxo de aprovação'
    )
    config.addinivalue_line(
        'markers',
        'destructive: Testes envolvendo operações destrutivas'
    )
    config.addinivalue_line(
        'markers',
        'metrics: Testes que validam métricas Prometheus'
    )
    config.addinivalue_line(
        'markers',
        'failure_scenarios: Testes de cenários de falha e resiliência'
    )
    config.addinivalue_line(
        'markers',
        'integration: Testes de integração entre componentes'
    )


@pytest.fixture(scope='session')
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Cria event loop para a sessão de testes."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope='session', autouse=True)
def _configure_logging() -> None:
    """Configura logging para testes."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )


# ============================================================================
# Fixtures de Settings
# ============================================================================

@pytest.fixture
def mock_settings() -> MagicMock:
    """
    Settings mockado com valores padrão para testes.

    Retorna MagicMock com atributos configurados para:
    - Detecção destrutiva habilitada
    - Pesos de risco padrão
    - Configuração Kafka de teste
    """
    settings = MagicMock()

    # Detecção destrutiva
    settings.destructive_detection_enabled = True
    settings.destructive_detection_strict_mode = False

    # Pesos de risco
    settings.risk_weight_priority = 0.3
    settings.risk_weight_security = 0.4
    settings.risk_weight_complexity = 0.3
    settings.risk_threshold_high = 0.7
    settings.risk_threshold_critical = 0.9

    # Kafka
    settings.kafka_bootstrap_servers = KAFKA_BOOTSTRAP
    settings.kafka_security_protocol = 'PLAINTEXT'
    settings.kafka_enable_idempotence = True
    settings.kafka_approval_topic = 'cognitive-plans-approval-requests'
    settings.kafka_plans_topic = 'cognitive-plans'
    settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
    settings.kafka_consumer_group_id = 'semantic-translation-engine-test'
    settings.kafka_auto_offset_reset = 'earliest'
    settings.kafka_session_timeout_ms = 30000
    settings.kafka_sasl_mechanism = 'PLAIN'
    settings.kafka_sasl_username = ''
    settings.kafka_sasl_password = ''

    # Schema Registry
    settings.schema_registry_url = None

    # Ambiente
    settings.environment = 'test'

    return settings


@pytest.fixture
def settings_strict_mode(mock_settings) -> MagicMock:
    """Settings com modo estrito de detecção destrutiva habilitado."""
    mock_settings.destructive_detection_strict_mode = True
    return mock_settings


@pytest.fixture
def settings_detection_disabled(mock_settings) -> MagicMock:
    """Settings com detecção destrutiva desabilitada."""
    mock_settings.destructive_detection_enabled = False
    return mock_settings


# ============================================================================
# Fixtures de dados de teste
# ============================================================================

@pytest.fixture
def sample_task_nodes() -> List[Dict[str, Any]]:
    """Lista de tasks de exemplo para testes."""
    return [
        {
            'task_id': 'task-1',
            'task_type': 'query',
            'description': 'Buscar dados',
            'dependencies': [],
        },
        {
            'task_id': 'task-2',
            'task_type': 'transform',
            'description': 'Transformar dados',
            'dependencies': ['task-1'],
        },
    ]


@pytest.fixture
def destructive_task_nodes() -> List[Dict[str, Any]]:
    """Lista de tasks destrutivas para testes."""
    return [
        {
            'task_id': 'task-query',
            'task_type': 'query',
            'description': 'Buscar registros inativos',
            'dependencies': [],
        },
        {
            'task_id': 'task-delete',
            'task_type': 'delete',
            'description': 'Deletar todos os registros inativos da produção',
            'dependencies': ['task-query'],
        },
    ]


@pytest.fixture
def sample_intent_id() -> str:
    """ID de intent único para testes."""
    return f'intent-test-{uuid.uuid4().hex[:8]}'


@pytest.fixture
def sample_plan_id() -> str:
    """ID de plano único para testes."""
    return f'plan-test-{uuid.uuid4().hex[:8]}'


@pytest.fixture
def sample_correlation_id() -> str:
    """ID de correlação único para testes."""
    return f'corr-test-{uuid.uuid4().hex[:8]}'


@pytest.fixture
def sample_intermediate_repr(sample_intent_id) -> Dict[str, Any]:
    """Representação intermediária de intent para testes."""
    return {
        'id': sample_intent_id,
        'metadata': {
            'priority': 'normal',
            'security_level': 'internal',
        },
        'historical_context': {
            'similar_intents': [],
        },
    }


@pytest.fixture
def high_risk_intermediate_repr(sample_intent_id) -> Dict[str, Any]:
    """Representação intermediária de alto risco."""
    return {
        'id': sample_intent_id,
        'metadata': {
            'priority': 'critical',
            'security_level': 'confidential',
        },
        'historical_context': {
            'similar_intents': [],
        },
    }


@pytest.fixture
def low_risk_intermediate_repr(sample_intent_id) -> Dict[str, Any]:
    """Representação intermediária de baixo risco."""
    return {
        'id': sample_intent_id,
        'metadata': {
            'priority': 'low',
            'security_level': 'public',
        },
        'historical_context': {
            'similar_intents': [],
        },
    }


@pytest.fixture
def sample_ledger_entry(sample_plan_id, sample_intent_id) -> Dict[str, Any]:
    """Entrada de ledger de exemplo para testes."""
    return {
        'plan_id': sample_plan_id,
        'intent_id': sample_intent_id,
        'version': '1.0.0',
        'timestamp': datetime.utcnow(),
        'plan_data': {
            'plan_id': sample_plan_id,
            'intent_id': sample_intent_id,
            'version': '1.0.0',
            'approval_status': 'pending',
            'risk_band': 'high',
            'risk_score': 0.85,
            'is_destructive': True,
            'destructive_tasks': ['task-delete'],
            'tasks': [
                {
                    'task_id': 'task-query',
                    'task_type': 'query',
                    'description': 'Buscar registros',
                    'dependencies': [],
                },
                {
                    'task_id': 'task-delete',
                    'task_type': 'delete',
                    'description': 'Deletar registros obsoletos',
                    'dependencies': ['task-query'],
                },
            ],
            'execution_order': ['task-query', 'task-delete'],
            'complexity_score': 0.4,
            'explainability_token': f'exp-{uuid.uuid4().hex[:8]}',
            'reasoning_summary': 'Plano para remoção de dados',
            'original_domain': 'infrastructure',
            'original_priority': 'high',
            'original_security_level': 'confidential',
            'requires_approval': True,
            'risk_matrix': {
                'is_destructive': True,
                'destructive_tasks': ['task-delete'],
                'destructive_severity': 'high',
                'destructive_count': 1,
            },
        },
    }


@pytest.fixture
def sample_approval_response(sample_plan_id, sample_intent_id) -> Dict[str, Any]:
    """Resposta de aprovação de exemplo."""
    return {
        'plan_id': sample_plan_id,
        'intent_id': sample_intent_id,
        'decision': 'approved',
        'approved_by': 'admin@company.com',
        'approved_at': int(datetime.utcnow().timestamp() * 1000),
        'rejection_reason': None,
    }


@pytest.fixture
def sample_rejection_response(sample_plan_id, sample_intent_id) -> Dict[str, Any]:
    """Resposta de rejeição de exemplo."""
    return {
        'plan_id': sample_plan_id,
        'intent_id': sample_intent_id,
        'decision': 'rejected',
        'approved_by': 'admin@company.com',
        'approved_at': int(datetime.utcnow().timestamp() * 1000),
        'rejection_reason': 'Operação muito arriscada para produção',
    }


@pytest.fixture
def sample_trace_context(sample_correlation_id) -> Dict[str, str]:
    """Contexto de trace para testes."""
    return {
        'correlation_id': sample_correlation_id,
        'trace_id': f'trace-{uuid.uuid4().hex[:8]}',
        'span_id': f'span-{uuid.uuid4().hex[:8]}',
    }
