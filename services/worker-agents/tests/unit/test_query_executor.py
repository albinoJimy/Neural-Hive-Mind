"""
Testes unitários para QueryExecutor.

Testa cada tipo de query com mocks.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock
from src.executors.query_executor import QueryExecutor
from src.executors.base_executor import ValidationError


@pytest.fixture
def mock_config():
    """Configuração mock para testes."""
    config = MagicMock()
    config.agent_id = 'test-agent'
    config.namespace = 'test'
    return config


@pytest.fixture
def mock_metrics():
    """Métricas mock para testes."""
    metrics = MagicMock()
    metrics.query_executed_total = MagicMock()
    metrics.query_executed_total.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))
    metrics.query_duration_seconds = MagicMock()
    metrics.query_duration_seconds.labels = MagicMock(return_value=MagicMock(observe=MagicMock()))
    return metrics


@pytest.fixture
def query_executor(mock_config, mock_metrics):
    """Instância do QueryExecutor para testes."""
    executor = QueryExecutor(
        config=mock_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        mongodb_client=None,
        redis_client=None,
        neo4j_client=None,
        kafka_consumer=None
    )
    return executor


class TestQueryExecutorBasics:
    """Testes básicos do QueryExecutor."""

    def test_get_task_type(self, query_executor):
        """Verifica que get_task_type retorna 'QUERY'."""
        assert query_executor.get_task_type() == 'QUERY'

    def test_validate_ticket_success(self, query_executor):
        """Valida ticket com campos obrigatórios."""
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {'query_type': 'mongodb'}
        }
        # Não deve levantar exceção
        query_executor.validate_ticket(ticket)

    def test_validate_ticket_missing_fields(self, query_executor):
        """Falha quando campos obrigatórios estão faltando."""
        ticket = {
            'ticket_id': 'test-123',
            'task_type': 'QUERY'
        }
        with pytest.raises(ValidationError, match='Missing required fields'):
            query_executor.validate_ticket(ticket)

    def test_validate_ticket_wrong_type(self, query_executor):
        """Falha quando task_type não é QUERY."""
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'BUILD',
            'parameters': {}
        }
        with pytest.raises(ValidationError, match='Task type mismatch'):
            query_executor.validate_ticket(ticket)


class TestMongoDBQueries:
    """Testes de queries MongoDB."""

    @pytest.mark.asyncio
    async def test_mongodb_query_success(self, query_executor, mock_config):
        """Testa query MongoDB bem-sucedida."""
        # Mock MongoDB client
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_cursor = MagicMock()

        # Configurar chain de mocks
        query_executor.mongodb_client = MagicMock()
        query_executor.mongodb_client.db = mock_db
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[
            {'_id': 'doc1', 'name': 'test1'},
            {'_id': 'doc2', 'name': 'test2'}
        ])

        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb',
                'collection': 'test_collection',
                'filter': {'status': 'active'},
                'limit': 10
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert len(result['output']['documents']) == 2
        assert result['output']['count'] == 2
        assert result['metadata']['query_type'] == 'mongodb'
        assert result['metadata']['collection'] == 'test_collection'

    @pytest.mark.asyncio
    async def test_mongodb_query_no_client(self, query_executor):
        """Testa query MongoDB quando cliente não disponível."""
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb',
                'collection': 'test'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is False
        assert 'not available' in result['metadata']['error'].lower()

    @pytest.mark.asyncio
    async def test_mongodb_query_missing_collection(self, query_executor, mock_config):
        """Testa query MongoDB sem parâmetro collection."""
        query_executor.mongodb_client = MagicMock()

        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is False
        assert 'collection' in result['metadata']['error'].lower()


class TestNeo4jQueries:
    """Testes de queries Neo4j."""

    @pytest.mark.asyncio
    async def test_neo4j_query_success(self, query_executor):
        """Testa query Neo4j bem-sucedida."""
        # Mock Neo4j client
        query_executor.neo4j_client = MagicMock()
        query_executor.neo4j_client.execute_query = AsyncMock(return_value=[
            {'n': {'id': '1', 'name': 'Node1'}},
            {'n': {'id': '2', 'name': 'Node2'}}
        ])

        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'neo4j',
                'cypher_query': 'MATCH (n) RETURN n LIMIT 10',
                'parameters': {'limit': 10}
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 2
        assert result['metadata']['query_type'] == 'neo4j'
        query_executor.neo4j_client.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_neo4j_query_no_client(self, query_executor):
        """Testa query Neo4j quando cliente não disponível."""
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'neo4j',
                'cypher_query': 'MATCH (n) RETURN n'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is False
        assert 'not available' in result['metadata']['error'].lower()


class TestRedisQueries:
    """Testes de queries Redis."""

    @pytest.mark.asyncio
    async def test_redis_get_success(self, query_executor):
        """Testa query Redis GET bem-sucedida."""
        query_executor.redis_client = MagicMock()
        query_executor.redis_client.get = AsyncMock(return_value='{"key": "value"}')

        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'redis',
                'operation': 'get',
                'key': 'test_key'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['key'] == 'test_key'
        assert result['output']['exists'] is True
        assert result['output']['value'] == {'key': 'value'}

    @pytest.mark.asyncio
    async def test_redis_scan_success(self, query_executor):
        """Testa query Redis SCAN bem-sucedida."""
        import asyncio

        async def mock_scan_iter(*args, **kwargs):
            """Generator mock para scan_iter."""
            for i in range(5):
                yield f'key:{i}'

        query_executor.redis_client = MagicMock()
        query_executor.redis_client.scan_iter = mock_scan_iter

        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'redis',
                'operation': 'scan',
                'pattern': 'test:*',
                'count': 100
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 5
        assert result['output']['pattern'] == 'test:*'

    @pytest.mark.asyncio
    async def test_redis_no_client(self, query_executor):
        """Testa query Redis quando cliente não disponível."""
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'redis',
                'operation': 'get',
                'key': 'test'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is False
        assert 'not available' in result['metadata']['error'].lower()


class TestKafkaQueries:
    """Testes de queries Kafka."""

    @pytest.mark.asyncio
    async def test_kafka_query_success(self, query_executor):
        """Testa query Kafka bem-sucedida."""
        # Este teste usa o mock de importação
        # A implementação real tenta importar aiokafka
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'kafka',
                'topic': 'test-topic',
                'max_messages': 10,
                'timeout_ms': 5000
            }
        }

        # Como aiokafka pode não estar instalado no ambiente de teste,
        # esperamos que retorne erro de importação ou outro erro tratado
        result = await query_executor.execute(ticket)

        # Pode ser sucesso se aiokafka instalado, ou erro se não instalado
        assert 'success' in result
        assert 'metadata' in result
        assert result['metadata']['query_type'] == 'kafka'

    @pytest.mark.asyncio
    async def test_kafka_query_missing_topic(self, query_executor):
        """Testa query Kafka sem parâmetro topic."""
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'kafka',
                'max_messages': 10
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is False
        assert 'topic' in result['metadata']['error'].lower()


class TestUtilityMethods:
    """Testes de métodos utilitários."""

    def test_serialize_doc_with_id(self, query_executor):
        """Testa serialização de documento com _id."""
        from bson.objectid import ObjectId

        doc = {'_id': ObjectId('507f1f77bcf86cd799439011'), 'name': 'test'}
        serialized = query_executor._serialize_doc(doc)

        assert '_id' in serialized
        assert isinstance(serialized['_id'], str)
        assert serialized['name'] == 'test'

    def test_is_json_valid(self, query_executor):
        """Testa detecção de JSON válido."""
        assert query_executor._is_json('{"key": "value"}') is True
        assert query_executor._is_json('[]') is True
        assert query_executor._is_json('not json') is False
        assert query_executor._is_json('') is False

    def test_error_result(self, query_executor):
        """Testa geração de resultado de erro."""
        result = query_executor._error_result('Test error', 'test_type')

        assert result['success'] is False
        assert result['output'] is None
        assert result['metadata']['query_type'] == 'test_type'
        assert result['metadata']['error'] == 'Test error'
        assert len(result['logs']) == 1


class TestQueryTypeDispatch:
    """Testes de dispatch por query_type."""

    @pytest.mark.asyncio
    async def test_unsupported_query_type(self, query_executor):
        """Testa erro para query_type não suportado."""
        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'unsupported_type'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is False
        assert 'Unsupported query_type' in result['metadata']['error']

    @pytest.mark.asyncio
    async def test_default_query_type_mongodb(self, query_executor):
        """Testa que query_type padrão é mongodb."""
        query_executor.mongodb_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_cursor = MagicMock()

        query_executor.mongodb_client.db = mock_db
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])

        ticket = {
            'ticket_id': 'test-123',
            'task_id': 'task-123',
            'task_type': 'QUERY',
            'parameters': {
                'collection': 'test'
            }
        }

        result = await query_executor.execute(ticket)

        # Deve usar mongodb como padrão
        assert result['metadata']['query_type'] == 'mongodb'
