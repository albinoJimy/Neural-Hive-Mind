"""
Testes de Consistência de Dados

Testes abrangentes para verificar consistência entre camadas de memória:
- MongoDB -> ClickHouse (via Kafka e batch)
- Políticas de retenção
- Idempotência de eventos
- Recuperação de falhas
"""
import json
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from src.clients.unified_memory_client import UnifiedMemoryClient
from src.clients.kafka_sync_producer import KafkaSyncProducer
from src.consumers.sync_event_consumer import SyncEventConsumer
from src.services.retention_policy_manager import RetentionPolicyManager
from src.jobs.sync_mongodb_to_clickhouse import MongoToClickHouseSync


class MockSettings:
    """Mock de configurações para testes"""
    def __init__(self):
        self.mongodb_context_collection = 'operational_context'
        self.mongodb_lineage_collection = 'data_lineage'
        self.mongodb_quality_collection = 'data_quality_metrics'
        self.mongodb_retention_days = 30
        self.clickhouse_retention_months = 18
        self.redis_default_ttl = 300
        self.redis_max_ttl = 900
        self.enable_realtime_sync = True
        self.enable_cache = True
        self.kafka_bootstrap_servers = 'localhost:9092'
        self.kafka_sync_topic = 'memory.sync.events'
        self.kafka_dlq_topic = 'memory.sync.events.dlq'
        self.kafka_consumer_group = 'test-consumer'
        self.kafka_security_protocol = 'PLAINTEXT'
        self.kafka_sasl_username = None
        self.kafka_sasl_password = None


@pytest.fixture
def settings():
    """Fixture de configurações"""
    return MockSettings()


@pytest.fixture
def mock_redis():
    """Mock do cliente Redis"""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete_pattern = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_mongodb():
    """Mock do cliente MongoDB"""
    mongodb = AsyncMock()
    mongodb.insert_one = AsyncMock(return_value='test-id')
    mongodb.find_one = AsyncMock(return_value=None)
    mongodb.find = AsyncMock(return_value=[])
    mongodb.delete_many = AsyncMock(return_value=5)
    mongodb.count_documents = AsyncMock(return_value=10)
    mongodb.update_many = AsyncMock(return_value=3)
    return mongodb


@pytest.fixture
def mock_neo4j():
    """Mock do cliente Neo4j"""
    neo4j = AsyncMock()
    neo4j.run_query = AsyncMock(return_value=[])
    return neo4j


@pytest.fixture
def mock_clickhouse():
    """Mock do cliente ClickHouse"""
    clickhouse = MagicMock()
    clickhouse.database = 'neural_hive'
    clickhouse.insert_batch = AsyncMock(return_value=True)
    clickhouse.client = MagicMock()
    clickhouse.client.query = MagicMock(return_value=MagicMock(result_rows=[[0]]))
    clickhouse.client.command = MagicMock()
    return clickhouse


@pytest.fixture
def mock_kafka_producer():
    """Mock do producer Kafka"""
    producer = AsyncMock()
    producer.publish_sync_event = AsyncMock(return_value=True)
    producer.is_running = True
    return producer


class TestUnifiedMemoryClientSync:
    """Testes de sincronização via UnifiedMemoryClient"""

    @pytest.mark.asyncio
    async def test_save_publishes_kafka_event(
        self,
        settings,
        mock_redis,
        mock_mongodb,
        mock_neo4j,
        mock_clickhouse,
        mock_kafka_producer
    ):
        """
        Testa se save() publica evento Kafka para sincronização.
        """
        client = UnifiedMemoryClient(
            mock_redis,
            mock_mongodb,
            mock_neo4j,
            mock_clickhouse,
            settings,
            kafka_producer=mock_kafka_producer
        )

        test_data = {
            'entity_id': str(uuid.uuid4()),
            'data_type': 'context',
            'content': 'test content'
        }

        entity_id = await client.save(test_data, 'context')

        # Verifica que MongoDB foi chamado
        mock_mongodb.insert_one.assert_called_once()

        # Verifica que Kafka producer foi chamado
        mock_kafka_producer.publish_sync_event.assert_called_once()

        # Verifica estrutura do evento
        call_args = mock_kafka_producer.publish_sync_event.call_args[0][0]
        assert 'event_id' in call_args
        assert call_args['entity_id'] == entity_id
        assert call_args['data_type'] == 'context'
        assert call_args['operation'] == 'INSERT'

    @pytest.mark.asyncio
    async def test_save_continues_on_kafka_failure(
        self,
        settings,
        mock_redis,
        mock_mongodb,
        mock_neo4j,
        mock_clickhouse
    ):
        """
        Testa que save() continua mesmo se Kafka falhar (fail-open).
        """
        failing_producer = AsyncMock()
        failing_producer.publish_sync_event = AsyncMock(side_effect=Exception("Kafka error"))

        client = UnifiedMemoryClient(
            mock_redis,
            mock_mongodb,
            mock_neo4j,
            mock_clickhouse,
            settings,
            kafka_producer=failing_producer
        )

        test_data = {'entity_id': 'test-123', 'content': 'test'}

        # Não deve lançar exceção
        entity_id = await client.save(test_data, 'context')
        assert entity_id is not None

        # MongoDB ainda deve ser chamado
        mock_mongodb.insert_one.assert_called_once()


class TestSyncEventConsumer:
    """Testes do consumer de sincronização"""

    @pytest.mark.asyncio
    async def test_process_event_inserts_to_clickhouse(
        self,
        settings,
        mock_clickhouse
    ):
        """
        Testa se eventos são inseridos corretamente no ClickHouse.
        """
        consumer = SyncEventConsumer(settings, mock_clickhouse)

        event = {
            'event_id': str(uuid.uuid4()),
            'entity_id': 'test-entity-123',
            'data_type': 'context',
            'operation': 'INSERT',
            'collection': 'operational_context',
            'timestamp': int(datetime.utcnow().timestamp() * 1000),
            'data': json.dumps({'content': 'test data'}),
            'metadata': json.dumps({'source': 'test'})
        }

        await consumer._process_event(event)

        # Verifica que insert_batch foi chamado
        mock_clickhouse.insert_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotency_skips_duplicate_events(
        self,
        settings,
        mock_clickhouse
    ):
        """
        Testa que eventos duplicados são ignorados (idempotência).
        """
        # Configura ClickHouse para retornar que registro já existe
        mock_clickhouse.client.query = MagicMock(
            return_value=MagicMock(result_rows=[[1]])
        )

        consumer = SyncEventConsumer(settings, mock_clickhouse)

        event = {
            'event_id': str(uuid.uuid4()),
            'entity_id': 'test-entity-123',
            'data_type': 'context',
            'operation': 'INSERT',
            'collection': 'operational_context',
            'timestamp': int(datetime.utcnow().timestamp() * 1000),
            'data': json.dumps({'content': 'test data'}),
            'metadata': None
        }

        await consumer._process_event(event)

        # insert_batch NÃO deve ser chamado porque registro já existe
        mock_clickhouse.insert_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_operation_ignored(
        self,
        settings,
        mock_clickhouse
    ):
        """
        Testa que operações DELETE são ignoradas (dados históricos são imutáveis).
        """
        consumer = SyncEventConsumer(settings, mock_clickhouse)

        event = {
            'event_id': str(uuid.uuid4()),
            'entity_id': 'test-entity-123',
            'data_type': 'context',
            'operation': 'DELETE',
            'collection': 'operational_context',
            'timestamp': int(datetime.utcnow().timestamp() * 1000),
            'data': '{}',
            'metadata': None
        }

        await consumer._process_event(event)

        # insert_batch NÃO deve ser chamado para DELETE
        mock_clickhouse.insert_batch.assert_not_called()


class TestRetentionPolicyManager:
    """Testes do gerenciador de políticas de retenção"""

    @pytest.mark.asyncio
    async def test_mongodb_cleanup_dry_run(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse,
        mock_neo4j
    ):
        """
        Testa cleanup do MongoDB em modo dry-run.
        """
        manager = RetentionPolicyManager(
            settings,
            mongodb_client=mock_mongodb,
            clickhouse_client=mock_clickhouse,
            neo4j_client=mock_neo4j
        )

        result = await manager._cleanup_mongodb(dry_run=True)

        # Deve chamar count_documents, não delete_many
        assert mock_mongodb.count_documents.call_count >= 1
        mock_mongodb.delete_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_mongodb_cleanup_executes_delete(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse,
        mock_neo4j
    ):
        """
        Testa cleanup do MongoDB executando delete real.
        """
        manager = RetentionPolicyManager(
            settings,
            mongodb_client=mock_mongodb,
            clickhouse_client=mock_clickhouse,
            neo4j_client=mock_neo4j
        )

        result = await manager._cleanup_mongodb(dry_run=False)

        # Deve chamar delete_many
        assert mock_mongodb.delete_many.call_count >= 1

    @pytest.mark.asyncio
    async def test_clickhouse_cleanup_dry_run(
        self,
        settings,
        mock_mongodb,
        mock_clickhouse,
        mock_neo4j
    ):
        """
        Testa cleanup do ClickHouse em modo dry-run.
        """
        manager = RetentionPolicyManager(
            settings,
            mongodb_client=mock_mongodb,
            clickhouse_client=mock_clickhouse,
            neo4j_client=mock_neo4j
        )

        result = await manager._cleanup_clickhouse(dry_run=True)

        # Deve chamar query para contagem, não command para delete
        assert mock_clickhouse.client.query.call_count >= 1
        mock_clickhouse.client.command.assert_not_called()

    def test_get_ttl_for_data_type(self, settings):
        """
        Testa obtenção de TTL para diferentes tipos de dados.
        """
        manager = RetentionPolicyManager(settings)

        # MongoDB
        assert manager.get_ttl_for_data_type('operational_context', 'mongodb') == 30
        assert manager.get_ttl_for_data_type('cognitive_ledger', 'mongodb') == 365

        # ClickHouse
        assert manager.get_ttl_for_data_type('cognitive_plans_history', 'clickhouse') == 18
        assert manager.get_ttl_for_data_type('telemetry_events', 'clickhouse') == 12

        # Redis
        assert manager.get_ttl_for_data_type('context', 'redis') == 300
        assert manager.get_ttl_for_data_type('session', 'redis') == 900


class TestBatchSyncJob:
    """Testes do job de sincronização batch"""

    @pytest.mark.asyncio
    async def test_prepare_row_for_context_history(self, settings):
        """
        Testa preparação de linha para tabela operational_context_history.
        """
        sync_job = MongoToClickHouseSync(settings)

        document = {
            '_id': 'mongo-id-123',
            'entity_id': 'test-entity',
            'data_type': 'context',
            'created_at': datetime(2024, 1, 15, 10, 30, 0),
            'content': 'test content',
            'metadata': {'source': 'test'}
        }

        row = sync_job._prepare_row(document, 'operational_context_history')

        assert isinstance(row, list)
        assert row[0] == 'test-entity'  # entity_id
        assert row[1] == 'context'  # data_type
        assert isinstance(row[2], datetime)  # created_at

    @pytest.mark.asyncio
    async def test_prepare_row_for_quality_metrics(self, settings):
        """
        Testa preparação de linha para tabela quality_metrics_history.
        """
        sync_job = MongoToClickHouseSync(settings)

        document = {
            '_id': 'mongo-id-123',
            'collection': 'test_collection',
            'created_at': datetime(2024, 1, 15, 10, 30, 0),
            'completeness_score': 0.95,
            'freshness_score': 0.88,
            'consistency_score': 0.92,
            'metadata': {}
        }

        row = sync_job._prepare_row(document, 'quality_metrics_history')

        assert isinstance(row, list)
        assert row[0] == 'test_collection'  # collection
        assert row[2] == 0.95  # completeness_score
        assert row[3] == 0.88  # freshness_score
        assert row[4] == 0.92  # consistency_score

    def test_get_column_names(self, settings):
        """
        Testa obtenção de nomes de colunas para diferentes tabelas.
        """
        sync_job = MongoToClickHouseSync(settings)

        context_cols = sync_job._get_column_names('operational_context_history')
        assert 'entity_id' in context_cols
        assert 'data_type' in context_cols

        lineage_cols = sync_job._get_column_names('data_lineage_history')
        assert 'source' in lineage_cols
        assert 'target' in lineage_cols

        metrics_cols = sync_job._get_column_names('quality_metrics_history')
        assert 'completeness_score' in metrics_cols
        assert 'freshness_score' in metrics_cols


class TestKafkaSyncProducer:
    """Testes do producer Kafka"""

    @pytest.mark.asyncio
    async def test_publish_sync_event_success(self, settings):
        """
        Testa publicação bem-sucedida de evento.
        """
        with patch('aiokafka.AIOKafkaProducer') as MockProducer:
            mock_producer_instance = AsyncMock()
            mock_producer_instance.send_and_wait = AsyncMock()
            MockProducer.return_value = mock_producer_instance

            producer = KafkaSyncProducer(settings)
            producer.producer = mock_producer_instance
            producer._started = True

            event = {
                'event_id': str(uuid.uuid4()),
                'entity_id': 'test-123',
                'data_type': 'context',
                'operation': 'INSERT',
                'collection': 'operational_context',
                'timestamp': int(datetime.utcnow().timestamp() * 1000),
                'data': '{}',
                'metadata': None
            }

            result = await producer.publish_sync_event(event)

            assert result is True
            mock_producer_instance.send_and_wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_returns_false_when_not_started(self, settings):
        """
        Testa que publish retorna False quando producer não está rodando.
        """
        producer = KafkaSyncProducer(settings)
        producer._started = False

        event = {'event_id': 'test'}
        result = await producer.publish_sync_event(event)

        assert result is False
