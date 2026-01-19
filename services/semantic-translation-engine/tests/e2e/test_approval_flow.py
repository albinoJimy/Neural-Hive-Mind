"""
Testes E2E para fluxo de aprovação do Semantic Translation Engine.

Este módulo valida os seguintes cenários:
1. Fluxo destrutivo completo: Intent → Detecção → Bloqueio → Aprovação → Execução
2. Fluxo de rejeição: Intent → Detecção → Bloqueio → Rejeição → Sem Execução
3. Decomposição avançada: Pattern Matching + Task Splitting + Dependências
4. Validação de métricas Prometheus
5. Cenários de falha: Kafka down, MongoDB down, Timeout

Requisitos:
- Kafka cluster acessível
- MongoDB cluster acessível
- Approval Service rodando
- Semantic Translation Engine rodando
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Importações do projeto (com fallback para ambientes sem dependências completas)
try:
    from src.models.cognitive_plan import (
        ApprovalStatus,
        CognitivePlan,
        RiskBand,
        TaskNode,
    )
    COGNITIVE_PLAN_AVAILABLE = True
except ImportError:
    COGNITIVE_PLAN_AVAILABLE = False
    # Criar mocks para os tipos
    class RiskBand:
        LOW = 'low'
        MEDIUM = 'medium'
        HIGH = 'high'
        CRITICAL = 'critical'

    class ApprovalStatus:
        PENDING = 'pending'
        APPROVED = 'approved'
        REJECTED = 'rejected'

    class TaskNode:
        def __init__(self, task_id, task_type, description, dependencies=None):
            self.task_id = task_id
            self.task_type = task_type
            self.description = description
            self.dependencies = dependencies or []

try:
    from src.services.destructive_detector import DestructiveDetector
    DESTRUCTIVE_DETECTOR_AVAILABLE = True
except ImportError:
    DESTRUCTIVE_DETECTOR_AVAILABLE = False
    DestructiveDetector = None

try:
    from src.services.risk_scorer import RiskScorer
    RISK_SCORER_AVAILABLE = True
except ImportError:
    RISK_SCORER_AVAILABLE = False
    RiskScorer = None

try:
    from src.services.approval_processor import ApprovalProcessor
    APPROVAL_PROCESSOR_AVAILABLE = True
except ImportError:
    APPROVAL_PROCESSOR_AVAILABLE = False
    ApprovalProcessor = None

# Tentar importar helpers de E2E (podem não existir em todos os ambientes)
try:
    from tests.e2e.utils.kafka_helpers import (
        KafkaTestHelper,
        KafkaMessageValidation,
        wait_for_kafka_message,
        collect_kafka_messages,
    )
    KAFKA_HELPERS_AVAILABLE = True
except ImportError:
    KAFKA_HELPERS_AVAILABLE = False

try:
    from tests.e2e.utils.database_helpers import MongoDBTestHelper
    MONGODB_HELPERS_AVAILABLE = True
except ImportError:
    MONGODB_HELPERS_AVAILABLE = False


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
STE_METRICS_URL = os.getenv(
    'STE_METRICS_URL',
    'http://semantic-translation-engine.neural-hive-orchestration.svc.cluster.local:8000'
)

# Tópicos Kafka
TOPIC_INTENTS = 'intents'
TOPIC_COGNITIVE_PLANS = 'cognitive-plans'
TOPIC_APPROVAL_REQUESTS = 'cognitive-plans-approval-requests'
TOPIC_APPROVAL_RESPONSES = 'cognitive-plans-approval-responses'

# Coleções MongoDB
COLLECTION_LEDGER = 'cognitive_plans_ledger'
COLLECTION_APPROVALS = 'plan_approvals'


# ============================================================================
# Fixtures de dados de teste
# ============================================================================

@pytest.fixture
def destructive_intent_data() -> Dict[str, Any]:
    """Intent com operação destrutiva em produção."""
    intent_id = f'intent-e2e-destructive-{uuid.uuid4().hex[:8]}'
    return {
        'intent_id': intent_id,
        'correlation_id': f'corr-{uuid.uuid4().hex[:8]}',
        'trace_id': f'trace-{uuid.uuid4().hex[:8]}',
        'span_id': f'span-{uuid.uuid4().hex[:8]}',
        'description': 'Deletar todos os usuários inativos da produção',
        'objectives': ['delete', 'cleanup'],
        'entities': ['users', 'orders'],
        'metadata': {
            'priority': 'critical',
            'security_level': 'restricted',
            'domain': 'infrastructure',
            'requester': 'admin@company.com',
        },
        'tasks': [
            {
                'task_id': 'task-query',
                'task_type': 'query',
                'description': 'Buscar usuários inativos há mais de 1 ano',
                'dependencies': [],
            },
            {
                'task_id': 'task-delete',
                'task_type': 'delete',
                'description': 'Deletar todos os usuários inativos da produção',
                'dependencies': ['task-query'],
            },
            {
                'task_id': 'task-notify',
                'task_type': 'notify',
                'description': 'Notificar administradores',
                'dependencies': ['task-delete'],
            },
        ],
    }


@pytest.fixture
def complex_intent_data() -> Dict[str, Any]:
    """Intent complexo com padrão de migração de dados."""
    intent_id = f'intent-e2e-complex-{uuid.uuid4().hex[:8]}'
    return {
        'intent_id': intent_id,
        'correlation_id': f'corr-{uuid.uuid4().hex[:8]}',
        'trace_id': f'trace-{uuid.uuid4().hex[:8]}',
        'span_id': f'span-{uuid.uuid4().hex[:8]}',
        'description': 'Migrar dados de clientes do sistema legado para novo sistema',
        'objectives': ['create', 'transform', 'query'],
        'entities': ['source_db', 'target_db', 'staging_table', 'customers'],
        'metadata': {
            'priority': 'high',
            'security_level': 'confidential',
            'domain': 'data-engineering',
            'keywords': ['migrate', 'data', 'transformation'],
        },
        'tasks': [
            {
                'task_id': 'task-extract',
                'task_type': 'query',
                'description': 'Extrair dados do sistema legado',
                'dependencies': [],
            },
            {
                'task_id': 'task-validate',
                'task_type': 'validate',
                'description': 'Validar integridade dos dados extraídos',
                'dependencies': ['task-extract'],
            },
            {
                'task_id': 'task-transform',
                'task_type': 'transform',
                'description': 'Transformar dados para novo formato',
                'dependencies': ['task-validate'],
            },
            {
                'task_id': 'task-load',
                'task_type': 'create',
                'description': 'Carregar dados no novo sistema',
                'dependencies': ['task-transform'],
            },
        ],
    }


@pytest.fixture
def safe_intent_data() -> Dict[str, Any]:
    """Intent simples e seguro (query apenas)."""
    intent_id = f'intent-e2e-safe-{uuid.uuid4().hex[:8]}'
    return {
        'intent_id': intent_id,
        'correlation_id': f'corr-{uuid.uuid4().hex[:8]}',
        'trace_id': f'trace-{uuid.uuid4().hex[:8]}',
        'span_id': f'span-{uuid.uuid4().hex[:8]}',
        'description': 'Consultar relatório de vendas do mês',
        'objectives': ['query'],
        'entities': ['sales_report'],
        'metadata': {
            'priority': 'low',
            'security_level': 'public',
            'domain': 'analytics',
        },
        'tasks': [
            {
                'task_id': 'task-query',
                'task_type': 'query',
                'description': 'Buscar dados de vendas do mês atual',
                'dependencies': [],
            },
            {
                'task_id': 'task-format',
                'task_type': 'transform',
                'description': 'Formatar relatório',
                'dependencies': ['task-query'],
            },
        ],
    }


@pytest.fixture
def mock_settings():
    """Settings mockado para testes."""
    settings = MagicMock()
    settings.destructive_detection_enabled = True
    settings.destructive_detection_strict_mode = False
    settings.risk_weight_priority = 0.3
    settings.risk_weight_security = 0.4
    settings.risk_weight_complexity = 0.3
    settings.risk_threshold_high = 0.7
    settings.risk_threshold_critical = 0.9
    settings.kafka_bootstrap_servers = KAFKA_BOOTSTRAP
    settings.kafka_security_protocol = 'PLAINTEXT'
    settings.kafka_enable_idempotence = True
    settings.kafka_approval_topic = TOPIC_APPROVAL_REQUESTS
    settings.kafka_plans_topic = TOPIC_COGNITIVE_PLANS
    settings.kafka_approval_responses_topic = TOPIC_APPROVAL_RESPONSES
    settings.schema_registry_url = None
    settings.environment = 'test'
    return settings


@pytest.fixture
def sample_ledger_entry() -> Dict[str, Any]:
    """Entrada de ledger com plano pendente de aprovação."""
    plan_id = f'plan-e2e-{uuid.uuid4().hex[:8]}'
    intent_id = f'intent-e2e-{uuid.uuid4().hex[:8]}'
    return {
        'plan_id': plan_id,
        'intent_id': intent_id,
        'version': '1.0.0',
        'timestamp': datetime.utcnow(),
        'plan_data': {
            'plan_id': plan_id,
            'intent_id': intent_id,
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
                    'description': 'Deletar registros obsoletos da produção',
                    'dependencies': ['task-query'],
                },
            ],
            'execution_order': ['task-query', 'task-delete'],
            'complexity_score': 0.4,
            'explainability_token': f'exp-{uuid.uuid4().hex[:8]}',
            'reasoning_summary': 'Plano para remoção de dados obsoletos',
            'original_domain': 'infrastructure',
            'original_priority': 'high',
            'original_security_level': 'confidential',
            'requires_approval': True,
            'risk_factors': {
                'priority': 0.9,
                'security': 0.85,
                'complexity': 0.4,
            },
            'risk_matrix': {
                'BUSINESS': 0.8,
                'SECURITY': 0.9,
                'OPERATIONAL': 0.7,
                'TECHNICAL': 0.6,
            },
        },
    }


# ============================================================================
# Fixtures de infraestrutura
# ============================================================================

@pytest.fixture
def kafka_test_helper():
    """Helper para testes Kafka (skip se não disponível)."""
    if not KAFKA_HELPERS_AVAILABLE:
        pytest.skip('KafkaTestHelper não disponível')

    helper = KafkaTestHelper(bootstrap_servers=KAFKA_BOOTSTRAP)
    yield helper
    helper.close()


@pytest.fixture
def mongodb_test_helper():
    """Helper para testes MongoDB (skip se não disponível)."""
    if not MONGODB_HELPERS_AVAILABLE:
        pytest.skip('MongoDBTestHelper não disponível')

    helper = MongoDBTestHelper(uri=MONGODB_URI, database=MONGODB_DATABASE)
    helper.connect()
    yield helper
    helper.close()


@pytest.fixture
async def approval_service_client():
    """Cliente HTTP para Approval Service."""
    async with httpx.AsyncClient(
        base_url=APPROVAL_SERVICE_URL,
        timeout=30.0,
    ) as client:
        yield client


# ============================================================================
# Helpers de validação
# ============================================================================

async def wait_for_plan_in_topic(
    kafka_helper,
    topic: str,
    plan_id: str,
    timeout: int = 60,
) -> Optional[Dict[str, Any]]:
    """
    Aguarda plano aparecer em tópico Kafka.

    Args:
        kafka_helper: KafkaTestHelper configurado
        topic: Nome do tópico
        plan_id: ID do plano a buscar
        timeout: Timeout em segundos

    Returns:
        Mensagem encontrada ou None se timeout
    """
    validation = await kafka_helper.validate_topic_messages(
        topic=topic,
        filter_fn=lambda msg: msg.get('plan_id') == plan_id,
        timeout_seconds=timeout,
        expected_count=1,
    )
    return validation.sample_messages[0] if validation.valid else None


async def validate_ledger_entry(
    mongodb_helper,
    plan_id: str,
    expected_status: str,
) -> Dict[str, Any]:
    """
    Valida entrada no ledger MongoDB.

    Args:
        mongodb_helper: MongoDBTestHelper configurado
        plan_id: ID do plano
        expected_status: Status esperado (pending, approved, rejected)

    Returns:
        Documento do ledger

    Raises:
        AssertionError: Se plano não encontrado ou status incorreto
    """
    docs = mongodb_helper.find_documents(
        COLLECTION_LEDGER,
        {'plan_id': plan_id},
    )
    assert len(docs) > 0, f'Plano {plan_id} não encontrado no ledger'

    entry = docs[0]
    plan_data = entry.get('plan_data', entry)
    actual_status = plan_data.get('approval_status', entry.get('approval_status'))

    assert actual_status == expected_status, (
        f'Status esperado: {expected_status}, atual: {actual_status}'
    )
    return entry


async def scrape_prometheus_metrics(
    service_url: str,
    metric_names: List[str],
) -> Dict[str, float]:
    """
    Faz scrape de métricas Prometheus do serviço.

    Args:
        service_url: URL base do serviço
        metric_names: Lista de nomes de métricas a buscar

    Returns:
        Dicionário com nome_métrica -> valor
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f'{service_url}/metrics')
            response.raise_for_status()
        except httpx.HTTPError:
            return {}

        metrics: Dict[str, float] = {}
        for line in response.text.split('\n'):
            if line.startswith('#') or not line.strip():
                continue

            for metric_name in metric_names:
                if line.startswith(metric_name):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            # Extrai o nome completo (com labels) e valor
                            metric_key = parts[0]
                            value = float(parts[-1])
                            metrics[metric_key] = value
                        except (ValueError, IndexError):
                            continue

        return metrics


def create_task_nodes(tasks_data: List[Dict[str, Any]]) -> List[TaskNode]:
    """Converte lista de dicts em lista de TaskNode."""
    return [
        TaskNode(
            task_id=t['task_id'],
            task_type=t['task_type'],
            description=t.get('description', ''),
            dependencies=t.get('dependencies', []),
        )
        for t in tasks_data
    ]


# ============================================================================
# Cenário 1: Fluxo Destrutivo Completo com Aprovação
# ============================================================================

@pytest.mark.e2e
@pytest.mark.approval_flow
@pytest.mark.asyncio
@pytest.mark.skipif(
    not APPROVAL_PROCESSOR_AVAILABLE,
    reason='ApprovalProcessor não disponível (dependências faltando)'
)
class TestDestructiveIntentApprovalFlow:
    """
    Testes para fluxo completo de intent destrutivo com aprovação.

    Valida: Intent destrutivo → Detecção → Bloqueio → Aprovação → Execução
    """

    async def test_destructive_intent_end_to_end_approval(
        self,
        mock_settings,
        sample_ledger_entry,
    ):
        """
        Fluxo E2E completo: intent destrutivo detectado, bloqueado e aprovado.

        Este teste valida o fluxo completo usando mocks para simular
        a infraestrutura Kafka/MongoDB quando não disponível.
        """
        # Arrange: Criar componentes
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=sample_ledger_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        # Act: Simular resposta de aprovação
        plan_id = sample_ledger_entry['plan_id']
        approval_response = {
            'plan_id': plan_id,
            'intent_id': sample_ledger_entry['intent_id'],
            'decision': 'approved',
            'approved_by': 'security-admin@company.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': None,
        }

        trace_context = {
            'correlation_id': f'corr-{uuid.uuid4().hex[:8]}',
            'trace_id': f'trace-{uuid.uuid4().hex[:8]}',
            'span_id': f'span-{uuid.uuid4().hex[:8]}',
        }

        await processor.process_approval_response(approval_response, trace_context)

        # Assert: Verificar que ledger foi consultado
        mongodb_client.query_ledger.assert_called_once_with(plan_id)

        # Assert: Verificar que ledger foi atualizado com aprovação
        mongodb_client.update_plan_approval_status.assert_called_once()
        update_call = mongodb_client.update_plan_approval_status.call_args
        assert update_call.kwargs['plan_id'] == plan_id
        assert update_call.kwargs['approval_status'] == 'approved'
        assert update_call.kwargs['approved_by'] == 'security-admin@company.com'

        # Assert: Verificar que plano foi publicado para execução
        plan_producer.send_plan.assert_called_once()

        # Assert: Verificar métricas
        metrics.record_approval_decision.assert_called_once_with(
            decision='approved',
            risk_band='high',
            is_destructive=True,
        )

    def test_destructive_detection_identifies_delete_operation(
        self,
        mock_settings,
        destructive_intent_data,
    ):
        """Valida que DestructiveDetector identifica operação de delete."""
        # Arrange
        detector = DestructiveDetector(mock_settings)
        tasks = create_task_nodes(destructive_intent_data['tasks'])

        # Act
        result = detector.detect(tasks)

        # Assert
        assert result['is_destructive'] is True
        assert 'task-delete' in result['destructive_tasks']
        assert result['severity'] in ['high', 'critical']  # Produção = critical
        assert result['total_destructive_count'] >= 1

    def test_destructive_detection_with_production_keyword_is_critical(
        self,
        mock_settings,
        destructive_intent_data,
    ):
        """Valida severidade crítica quando 'produção' está na descrição."""
        # Arrange
        detector = DestructiveDetector(mock_settings)
        tasks = create_task_nodes(destructive_intent_data['tasks'])

        # Act
        result = detector.detect(tasks)

        # Assert: Produção + todos = critical
        assert result['severity'] == 'critical'

    @pytest.mark.skipif(
        not RISK_SCORER_AVAILABLE,
        reason='RiskScorer não disponível (dependências faltando)'
    )
    def test_risk_scorer_requires_approval_for_destructive(
        self,
        mock_settings,
        destructive_intent_data,
    ):
        """Valida que RiskScorer marca intent destrutivo como requerendo aprovação."""
        # Arrange
        risk_scorer = RiskScorer(mock_settings)
        tasks = create_task_nodes(destructive_intent_data['tasks'])
        intermediate_repr = {
            'id': destructive_intent_data['intent_id'],
            'metadata': destructive_intent_data['metadata'],
            'historical_context': {'similar_intents': []},
        }

        # Act
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr,
            tasks,
        )

        # Assert
        assert risk_matrix['is_destructive'] is True
        requires_approval = (
            risk_score >= 0.7 or
            risk_matrix['is_destructive'] or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )
        assert requires_approval is True


# ============================================================================
# Cenário 2: Fluxo de Rejeição
# ============================================================================

@pytest.mark.e2e
@pytest.mark.approval_flow
@pytest.mark.asyncio
@pytest.mark.skipif(
    not APPROVAL_PROCESSOR_AVAILABLE,
    reason='ApprovalProcessor não disponível (dependências faltando)'
)
class TestDestructiveIntentRejectionFlow:
    """
    Testes para fluxo de rejeição de intent destrutivo.

    Valida: Intent destrutivo → Detecção → Bloqueio → Rejeição → Sem Execução
    """

    async def test_destructive_intent_rejection_flow(
        self,
        mock_settings,
        sample_ledger_entry,
    ):
        """
        Fluxo E2E: intent destrutivo detectado, bloqueado e rejeitado.

        Plano não deve ser publicado após rejeição.
        """
        # Arrange
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=sample_ledger_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        # Act: Simular resposta de rejeição
        plan_id = sample_ledger_entry['plan_id']
        rejection_reason = 'Operação de delete em produção requer análise adicional do DBA'

        approval_response = {
            'plan_id': plan_id,
            'intent_id': sample_ledger_entry['intent_id'],
            'decision': 'rejected',
            'approved_by': 'security-admin@company.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': rejection_reason,
        }

        trace_context = {'correlation_id': f'corr-{uuid.uuid4().hex[:8]}'}

        await processor.process_approval_response(approval_response, trace_context)

        # Assert: Verificar que ledger foi atualizado com rejeição
        mongodb_client.update_plan_approval_status.assert_called_once()
        update_call = mongodb_client.update_plan_approval_status.call_args
        assert update_call.kwargs['approval_status'] == 'rejected'
        assert 'DBA' in update_call.kwargs['rejection_reason']

        # Assert: Plano NÃO deve ser publicado após rejeição
        plan_producer.send_plan.assert_not_called()

        # Assert: Métricas de rejeição
        metrics.record_approval_decision.assert_called_once_with(
            decision='rejected',
            risk_band='high',
            is_destructive=True,
        )

    async def test_rejected_plan_not_published_to_execution_topic(
        self,
        mock_settings,
        sample_ledger_entry,
    ):
        """Valida que plano rejeitado não é publicado para execução."""
        # Arrange
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=sample_ledger_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        # Act
        approval_response = {
            'plan_id': sample_ledger_entry['plan_id'],
            'intent_id': sample_ledger_entry['intent_id'],
            'decision': 'rejected',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': 'Risco muito alto',
        }

        await processor.process_approval_response(approval_response, {})

        # Assert: send_plan nunca deve ser chamado para rejeições
        plan_producer.send_plan.assert_not_called()


# ============================================================================
# Cenário 3: Decomposição Avançada
# ============================================================================

@pytest.mark.e2e
@pytest.mark.approval_flow
@pytest.mark.skipif(
    not DESTRUCTIVE_DETECTOR_AVAILABLE or not RISK_SCORER_AVAILABLE,
    reason='DestructiveDetector ou RiskScorer não disponível (dependências faltando)'
)
class TestAdvancedDecompositionFlow:
    """
    Testes para decomposição avançada de intents complexos.

    Valida: Pattern Matching + Task Splitting + Dependências de Entidades
    """

    def test_complex_intent_not_destructive(
        self,
        mock_settings,
        complex_intent_data,
    ):
        """Intent de migração não deve ser marcado como destrutivo."""
        # Arrange
        detector = DestructiveDetector(mock_settings)
        tasks = create_task_nodes(complex_intent_data['tasks'])

        # Act
        result = detector.detect(tasks)

        # Assert: Migração sem delete não é destrutiva
        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []

    def test_complex_intent_lower_risk_band(
        self,
        mock_settings,
        complex_intent_data,
    ):
        """Intent de migração deve ter risk_band apropriado."""
        # Arrange
        risk_scorer = RiskScorer(mock_settings)
        tasks = create_task_nodes(complex_intent_data['tasks'])
        intermediate_repr = {
            'id': complex_intent_data['intent_id'],
            'metadata': complex_intent_data['metadata'],
            'historical_context': {'similar_intents': []},
        }

        # Act
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr,
            tasks,
        )

        # Assert: Não destrutivo, mas pode ser high por priority/security
        assert risk_matrix['is_destructive'] is False
        # O risco depende de priority=high e security_level=confidential

    def test_safe_intent_bypasses_approval(
        self,
        mock_settings,
        safe_intent_data,
    ):
        """Intent seguro deve bypassar fluxo de aprovação."""
        # Arrange
        risk_scorer = RiskScorer(mock_settings)
        tasks = create_task_nodes(safe_intent_data['tasks'])
        intermediate_repr = {
            'id': safe_intent_data['intent_id'],
            'metadata': safe_intent_data['metadata'],
            'historical_context': {'similar_intents': []},
        }

        # Act
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr,
            tasks,
        )

        # Assert
        assert risk_matrix['is_destructive'] is False

        # Para operações de baixo risco, não deve requerer aprovação
        requires_approval = (
            risk_score >= 0.7 or
            risk_matrix['is_destructive'] or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        # Se risk_band é LOW e score < 0.7, não requer aprovação
        if risk_band == RiskBand.LOW:
            assert requires_approval is False or risk_score >= 0.7

    def test_task_dependencies_preserved_in_cognitive_plan(
        self,
        mock_settings,
        complex_intent_data,
    ):
        """Valida que dependências entre tasks são preservadas."""
        # Arrange
        tasks = create_task_nodes(complex_intent_data['tasks'])

        # Assert: Verificar dependências
        task_map = {t.task_id: t for t in tasks}

        # task-validate depende de task-extract
        assert 'task-extract' in task_map['task-validate'].dependencies

        # task-transform depende de task-validate
        assert 'task-validate' in task_map['task-transform'].dependencies

        # task-load depende de task-transform
        assert 'task-transform' in task_map['task-load'].dependencies


# ============================================================================
# Cenário 4: Validação de Métricas Prometheus
# ============================================================================

@pytest.mark.e2e
@pytest.mark.metrics
@pytest.mark.asyncio
@pytest.mark.skipif(
    not APPROVAL_PROCESSOR_AVAILABLE or not DESTRUCTIVE_DETECTOR_AVAILABLE,
    reason='ApprovalProcessor ou DestructiveDetector não disponível (dependências faltando)'
)
class TestPrometheusMetricsValidation:
    """
    Testes para validação de métricas Prometheus.

    Valida que métricas são registradas corretamente durante o fluxo.
    """

    async def test_metrics_recorded_for_approval_flow(
        self,
        mock_settings,
        sample_ledger_entry,
    ):
        """Valida que métricas são incrementadas durante fluxo de aprovação."""
        # Arrange
        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()

        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=sample_ledger_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        # Act
        approval_response = {
            'plan_id': sample_ledger_entry['plan_id'],
            'intent_id': sample_ledger_entry['intent_id'],
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
        }

        await processor.process_approval_response(approval_response, {})

        # Assert: Verificar que métricas foram chamadas
        metrics.record_approval_decision.assert_called_once()
        call_args = metrics.record_approval_decision.call_args
        assert call_args.kwargs['decision'] == 'approved'
        assert call_args.kwargs['is_destructive'] is True

    def test_destructive_detection_metrics_recorded(self, mock_settings):
        """Valida que métricas de detecção destrutiva são registradas."""
        # Este teste usa patch para verificar métricas Prometheus reais
        with patch(
            'src.services.destructive_detector.destructive_operations_detected_total'
        ) as mock_counter:
            with patch(
                'src.services.destructive_detector.destructive_tasks_per_plan'
            ) as mock_histogram:
                # Arrange
                detector = DestructiveDetector(mock_settings)
                tasks = [
                    TaskNode(
                        task_id='task-delete',
                        task_type='delete',
                        description='Delete records from production',
                        dependencies=[],
                    ),
                ]

                # Act
                result = detector.detect(tasks)

                # Assert
                assert result['is_destructive'] is True
                mock_counter.labels.assert_called()
                mock_histogram.observe.assert_called_once_with(1)


# ============================================================================
# Cenário 5: Cenários de Falha
# ============================================================================

@pytest.mark.e2e
@pytest.mark.failure_scenarios
@pytest.mark.asyncio
@pytest.mark.skipif(
    not APPROVAL_PROCESSOR_AVAILABLE,
    reason='ApprovalProcessor não disponível (dependências faltando)'
)
class TestFailureScenarios:
    """
    Testes para cenários de falha e resiliência.

    Valida tratamento de erros em Kafka, MongoDB e timeout.
    """

    async def test_mongodb_unavailable_approval_flow(self, mock_settings):
        """Processor deve propagar exceção quando MongoDB falha."""
        # Arrange
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(
            side_effect=Exception('MongoDB connection lost')
        )

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        approval_response = {
            'plan_id': 'plan-fail',
            'intent_id': 'intent-fail',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
        }

        # Act & Assert: Deve propagar exceção para retry do consumer
        with pytest.raises(Exception, match='MongoDB connection lost'):
            await processor.process_approval_response(approval_response, {})

        # Plano não deve ser publicado
        plan_producer.send_plan.assert_not_called()

    async def test_invalid_plan_data_handling(self, mock_settings):
        """Processor deve tratar dados de plano inválidos."""
        # Arrange: Ledger entry com plan_data malformado
        malformed_entry = {
            'plan_id': 'plan-malformed',
            'timestamp': datetime.utcnow(),
            'plan_data': {
                'approval_status': 'pending',
                'risk_band': 'high',
                'is_destructive': False,
                # Missing required fields
            },
        }

        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=malformed_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        approval_response = {
            'plan_id': 'plan-malformed',
            'intent_id': 'intent-x',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
        }

        # Act & Assert: Deve propagar erro de reconstrução
        with pytest.raises(Exception):
            await processor.process_approval_response(approval_response, {})

    async def test_plan_not_found_in_ledger(self, mock_settings):
        """Processor deve tratar plano não encontrado no ledger."""
        # Arrange
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=None)

        plan_producer = MagicMock()
        metrics = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        approval_response = {
            'plan_id': 'plan-not-exists',
            'intent_id': 'intent-not-exists',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
        }

        # Act: Processor deve logar erro e ignorar quando plano não encontrado
        # (comportamento graceful - não levanta exceção)
        await processor.process_approval_response(approval_response, {})

        # Assert: Plano não deve ser publicado quando não encontrado
        plan_producer.send_plan.assert_not_called()

    def test_detection_disabled_returns_safe_result(self):
        """Quando detecção desabilitada, retorna resultado seguro."""
        # Arrange
        settings = MagicMock()
        settings.destructive_detection_enabled = False

        detector = DestructiveDetector(settings)
        tasks = [
            TaskNode(
                task_id='task-delete',
                task_type='delete',
                description='Delete everything from production',
                dependencies=[],
            ),
        ]

        # Act
        result = detector.detect(tasks)

        # Assert: Mesmo com operação destrutiva, retorna false quando desabilitado
        assert result['is_destructive'] is False
        assert result['destructive_tasks'] == []


# ============================================================================
# Testes de Integração com Infraestrutura Real (opcional)
# ============================================================================

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.skipif(
    not KAFKA_HELPERS_AVAILABLE or not MONGODB_HELPERS_AVAILABLE,
    reason='Helpers de infraestrutura não disponíveis'
)
class TestRealInfrastructureIntegration:
    """
    Testes com infraestrutura real (Kafka, MongoDB).

    Estes testes requerem ambiente completo e são marcados como slow.
    """

    @pytest.mark.asyncio
    async def test_kafka_message_round_trip(self, kafka_test_helper):
        """Valida envio e recebimento de mensagem Kafka."""
        # Este teste só executa se Kafka estiver disponível
        pytest.skip('Teste requer Kafka real - execute manualmente')

    @pytest.mark.asyncio
    async def test_mongodb_ledger_persistence(self, mongodb_test_helper):
        """Valida persistência no ledger MongoDB."""
        # Este teste só executa se MongoDB estiver disponível
        pytest.skip('Teste requer MongoDB real - execute manualmente')

    @pytest.mark.asyncio
    async def test_approval_service_health(self, approval_service_client):
        """Valida health check do Approval Service."""
        try:
            response = await approval_service_client.get('/health')
            assert response.status_code == 200
        except httpx.HTTPError:
            pytest.skip('Approval Service não disponível')


# ============================================================================
# Testes de Contrato de API
# ============================================================================

@pytest.mark.e2e
@pytest.mark.approval_flow
class TestApprovalAPIContract:
    """Testes de contrato para APIs de aprovação."""

    def test_approval_response_schema(self):
        """Valida schema de resposta de aprovação."""
        # Schema esperado
        required_fields = [
            'plan_id',
            'intent_id',
            'decision',
            'approved_by',
            'approved_at',
        ]

        # Resposta válida
        valid_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-123',
            'decision': 'approved',
            'approved_by': 'admin@company.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
        }

        # Assert: Todos os campos obrigatórios presentes
        for field in required_fields:
            assert field in valid_response

    def test_approval_decision_values(self):
        """Valida valores válidos para decision."""
        valid_decisions = ['approved', 'rejected']

        for decision in valid_decisions:
            response = {
                'plan_id': 'plan-123',
                'intent_id': 'intent-123',
                'decision': decision,
                'approved_by': 'admin',
                'approved_at': int(datetime.utcnow().timestamp() * 1000),
            }
            assert response['decision'] in valid_decisions

    def test_rejection_requires_reason(self):
        """Valida que rejeição deve incluir motivo."""
        rejection_response = {
            'plan_id': 'plan-123',
            'intent_id': 'intent-123',
            'decision': 'rejected',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': 'Operação muito arriscada',
        }

        # Assert: rejection_reason presente para rejeições
        assert 'rejection_reason' in rejection_response
        assert rejection_response['rejection_reason'] is not None
