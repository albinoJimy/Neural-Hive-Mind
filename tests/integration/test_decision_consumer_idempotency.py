"""
Testes de idempotência para o DecisionConsumer.

Verifica que decisões duplicadas são detectadas e ignoradas corretamente,
e que o sistema continua funcionando mesmo quando Redis está indisponível (fail-open).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

# Add orchestrator-dynamic src to path
ROOT = Path(__file__).resolve().parents[2]
ORCH_SRC = ROOT / "services" / "orchestrator-dynamic" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

# Stub temporalio if not installed
try:
    import temporalio.activity
except ImportError:
    temporalio = SimpleNamespace()
    temporalio.activity = SimpleNamespace(logger=SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None))
    sys.modules["temporalio"] = temporalio
    sys.modules["temporalio.activity"] = temporalio.activity

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_config():
    """Fixture para configuração mockada."""
    config = MagicMock()
    config.kafka_bootstrap_servers = 'localhost:9092'
    config.kafka_consensus_topic = 'plans.consensus'
    config.kafka_consumer_group = 'orchestrator-consumer'
    config.kafka_sasl_username = 'test'
    config.kafka_sasl_password = 'test'
    config.kafka_security_protocol = 'PLAINTEXT'
    config.kafka_sasl_mechanism = 'PLAIN'
    config.temporal_task_queue = 'orchestration-queue'
    config.temporal_workflow_id_prefix = 'nhm-'
    return config


@pytest.fixture
def mock_redis_client():
    """Fixture para Redis client mockado."""
    redis_mock = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_temporal_client():
    """Fixture para Temporal client mockado."""
    return AsyncMock()


@pytest.fixture
def mock_mongodb_client():
    """Fixture para MongoDB client mockado."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_duplicate_decision_is_skipped(mock_config, mock_redis_client, mock_temporal_client, mock_mongodb_client):
    """Testar que decisões duplicadas são ignoradas (two-phase scheme)."""
    # Mock all external dependencies before import
    with patch.dict('sys.modules', {
        'aiokafka': MagicMock(),
        'src.workflows.orchestration_workflow': MagicMock(),
        'neural_hive_observability': MagicMock(),
        'neural_hive_observability.context': MagicMock(),
    }):
        # Reset prometheus registry for clean test
        from prometheus_client import REGISTRY
        collectors_to_remove = []
        for collector in REGISTRY._names_to_collectors.values():
            if hasattr(collector, '_name') and 'orchestrator_decision_duplicates' in getattr(collector, '_name', ''):
                collectors_to_remove.append(collector)
        for collector in collectors_to_remove:
            try:
                REGISTRY.unregister(collector)
            except Exception:
                pass

        from consumers.decision_consumer import DecisionConsumer

        # Setup: exists retorna False (não processado), set retorna True/False
        mock_redis_client.exists = AsyncMock(side_effect=[False, False])
        mock_redis_client.set = AsyncMock(side_effect=[True, False])

        consumer = DecisionConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        # Primeira mensagem - deve processar (não é duplicata)
        is_dup_1 = await consumer._is_duplicate_decision("decision-123")
        assert is_dup_1 is False

        # Segunda mensagem - deve detectar duplicata (processing key já existe)
        is_dup_2 = await consumer._is_duplicate_decision("decision-123")
        assert is_dup_2 is True

        # Verificar chamadas ao Redis
        assert mock_redis_client.set.call_count == 2


@pytest.mark.asyncio
async def test_redis_failure_allows_processing(mock_config, mock_temporal_client, mock_mongodb_client):
    """Testar fail-open quando Redis falha."""
    with patch.dict('sys.modules', {
        'aiokafka': MagicMock(),
        'src.workflows.orchestration_workflow': MagicMock(),
        'neural_hive_observability': MagicMock(),
        'neural_hive_observability.context': MagicMock(),
    }):
        from consumers.decision_consumer import DecisionConsumer

        redis_mock = AsyncMock()
        redis_mock.exists = AsyncMock(side_effect=Exception("Redis connection failed"))

        consumer = DecisionConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            mongodb_client=mock_mongodb_client,
            redis_client=redis_mock
        )

        # Deve retornar False (não é duplicata) para permitir processamento
        is_dup = await consumer._is_duplicate_decision("decision-456")
        assert is_dup is False


@pytest.mark.asyncio
async def test_no_redis_client_allows_processing(mock_config, mock_temporal_client, mock_mongodb_client):
    """Testar que processamento continua quando Redis não está disponível."""
    with patch.dict('sys.modules', {
        'aiokafka': MagicMock(),
        'src.workflows.orchestration_workflow': MagicMock(),
        'neural_hive_observability': MagicMock(),
        'neural_hive_observability.context': MagicMock(),
    }):
        from consumers.decision_consumer import DecisionConsumer

        consumer = DecisionConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            mongodb_client=mock_mongodb_client,
            redis_client=None  # Redis não disponível
        )

        # Deve retornar False (não é duplicata) para permitir processamento
        is_dup = await consumer._is_duplicate_decision("decision-789")
        assert is_dup is False


@pytest.mark.asyncio
async def test_deduplication_ttl_is_correct(mock_config, mock_redis_client, mock_temporal_client, mock_mongodb_client):
    """Testar que o TTL correto é usado na deduplicação (two-phase scheme)."""
    with patch.dict('sys.modules', {
        'aiokafka': MagicMock(),
        'src.workflows.orchestration_workflow': MagicMock(),
        'neural_hive_observability': MagicMock(),
        'neural_hive_observability.context': MagicMock(),
    }):
        from consumers.decision_consumer import DecisionConsumer

        mock_redis_client.exists = AsyncMock(return_value=False)
        mock_redis_client.set = AsyncMock(return_value=True)

        consumer = DecisionConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        await consumer._is_duplicate_decision("decision-ttl-test")

        # Verificar que set foi chamado com TTL de PROCESSING (300 segundos) na fase 2
        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args

        # Verificar argumentos - agora usa chave processing com TTL curto
        assert call_args[0][0] == "decision:processing:decision-ttl-test"  # key
        assert call_args[0][1] == "1"  # value
        assert call_args[1]['ex'] == 300  # TTL 5 minutos (processing)
        assert call_args[1]['nx'] is True  # Only set if not exists


@pytest.mark.asyncio
async def test_different_decisions_are_not_duplicates(mock_config, mock_redis_client, mock_temporal_client, mock_mongodb_client):
    """Testar que decisões diferentes não são consideradas duplicatas entre si (two-phase scheme)."""
    with patch.dict('sys.modules', {
        'aiokafka': MagicMock(),
        'src.workflows.orchestration_workflow': MagicMock(),
        'neural_hive_observability': MagicMock(),
        'neural_hive_observability.context': MagicMock(),
    }):
        from consumers.decision_consumer import DecisionConsumer

        # exists sempre retorna False (não processado), set sempre retorna True (chave criada)
        mock_redis_client.exists = AsyncMock(return_value=False)
        mock_redis_client.set = AsyncMock(return_value=True)

        consumer = DecisionConsumer(
            config=mock_config,
            temporal_client=mock_temporal_client,
            mongodb_client=mock_mongodb_client,
            redis_client=mock_redis_client
        )

        # Decisões diferentes - nenhuma deve ser duplicata
        is_dup_1 = await consumer._is_duplicate_decision("decision-A")
        is_dup_2 = await consumer._is_duplicate_decision("decision-B")
        is_dup_3 = await consumer._is_duplicate_decision("decision-C")

        assert is_dup_1 is False
        assert is_dup_2 is False
        assert is_dup_3 is False

        # Verificar que Redis set foi chamado 3 vezes com chaves de processing diferentes
        assert mock_redis_client.set.call_count == 3
        calls = mock_redis_client.set.call_args_list
        assert calls[0][0][0] == "decision:processing:decision-A"
        assert calls[1][0][0] == "decision:processing:decision-B"
        assert calls[2][0][0] == "decision:processing:decision-C"
