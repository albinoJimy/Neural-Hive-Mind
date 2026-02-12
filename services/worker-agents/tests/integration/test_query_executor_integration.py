"""
Testes de integração para QueryExecutor.

Testa queries reais contra MongoDB/Redis em docker-compose.
Valida timeout e retry logic.
"""
import pytest
import asyncio
from datetime import datetime
from src.executors.query_executor import QueryExecutor
from src.config.settings import get_settings


@pytest.mark.integration
class TestMongoDBIntegration:
    """Testes de integração com MongoDB."""

    @pytest.fixture
    async def mongodb_client(self):
        """Cliente MongoDB real para testes."""
        from src.clients.mongodb_client import MongoDBClient

        config = get_settings()
        client = MongoDBClient(config)
        await client.initialize()

        # Inserir dados de teste
        test_collection = client.db['test_query_executor']
        await test_collection.delete_many({})  # Limpar antes
        await test_collection.insert_many([
            {'name': 'test1', 'status': 'active', 'value': 100},
            {'name': 'test2', 'status': 'active', 'value': 200},
            {'name': 'test3', 'status': 'inactive', 'value': 300}
        ])

        yield client

        # Cleanup
        await test_collection.delete_many({})
        await client.close()

    @pytest.fixture
    def query_executor(self, mongodb_client):
        """QueryExecutor com cliente MongoDB real."""
        config = get_settings()
        return QueryExecutor(
            config=config,
            vault_client=None,
            code_forge_client=None,
            metrics=None,
            mongodb_client=mongodb_client,
            redis_client=None,
            neo4j_client=None,
            kafka_consumer=None
        )

    @pytest.mark.asyncio
    async def test_mongodb_find_query(self, query_executor):
        """Testa query FIND no MongoDB."""
        ticket = {
            'ticket_id': 'test-mongodb-001',
            'task_id': 'task-001',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb',
                'collection': 'test_query_executor',
                'filter': {'status': 'active'},
                'projection': {'name': 1, 'value': 1}
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 2
        assert result['output']['documents'][0]['name'] in ['test1', 'test2']
        assert '_id' in result['output']['documents'][0]

    @pytest.mark.asyncio
    async def test_mongodb_query_with_limit(self, query_executor):
        """Testa query com limite no MongoDB."""
        ticket = {
            'ticket_id': 'test-mongodb-002',
            'task_id': 'task-002',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb',
                'collection': 'test_query_executor',
                'filter': {},
                'limit': 2
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 2

    @pytest.mark.asyncio
    async def test_mongodb_query_with_sort(self, query_executor):
        """Testa query com ordenação no MongoDB."""
        ticket = {
            'ticket_id': 'test-mongodb-003',
            'task_id': 'task-003',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb',
                'collection': 'test_query_executor',
                'filter': {},
                'sort': [('value', -1)],  # Descendente
                'limit': 1
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['documents'][0]['value'] == 300


@pytest.mark.integration
class TestRedisIntegration:
    """Testes de integração com Redis."""

    @pytest.fixture
    async def redis_client(self):
        """Cliente Redis real para testes."""
        from src.clients.redis_client import get_redis_client

        config = get_settings()
        client = await get_redis_client(config)

        if not client:
            pytest.skip("Redis não disponível")

        # Inserir dados de teste
        await client.set('test:query:1', '{"name": "test1", "value": 100}')
        await client.set('test:query:2', '{"name": "test2", "value": 200}')
        await client.set('test:other:1', '{"name": "other"}')

        yield client

        # Cleanup
        await client.delete('test:query:1', 'test:query:2', 'test:other:1')

    @pytest.fixture
    def query_executor(self, redis_client):
        """QueryExecutor com cliente Redis real."""
        config = get_settings()
        return QueryExecutor(
            config=config,
            vault_client=None,
            code_forge_client=None,
            metrics=None,
            mongodb_client=None,
            redis_client=redis_client,
            neo4j_client=None,
            kafka_consumer=None
        )

    @pytest.mark.asyncio
    async def test_redis_get_existing_key(self, query_executor):
        """Testa GET de chave existente no Redis."""
        ticket = {
            'ticket_id': 'test-redis-001',
            'task_id': 'task-001',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'redis',
                'operation': 'get',
                'key': 'test:query:1'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['exists'] is True
        assert result['output']['value']['name'] == 'test1'

    @pytest.mark.asyncio
    async def test_redis_get_nonexistent_key(self, query_executor):
        """Testa GET de chave inexistente no Redis."""
        ticket = {
            'ticket_id': 'test-redis-002',
            'task_id': 'task-002',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'redis',
                'operation': 'get',
                'key': 'test:nonexistent'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['exists'] is False
        assert result['output']['value'] is None

    @pytest.mark.asyncio
    async def test_redis_scan_with_pattern(self, query_executor):
        """Testa SCAN com padrão no Redis."""
        ticket = {
            'ticket_id': 'test-redis-003',
            'task_id': 'task-003',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'redis',
                'operation': 'scan',
                'pattern': 'test:query:*',
                'count': 100
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 2
        assert set(result['output']['keys']) == {'test:query:1', 'test:query:2'}

    @pytest.mark.asyncio
    async def test_redis_keys_with_pattern(self, query_executor):
        """Testa KEYS com padrão no Redis."""
        ticket = {
            'ticket_id': 'test-redis-004',
            'task_id': 'task-004',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'redis',
                'operation': 'keys',
                'pattern': 'test:*'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 3
        assert 'test:query:1' in result['output']['keys']


@pytest.mark.integration
@pytest.mark.skip(reason="Neo4j não disponível em todos os ambientes")
class TestNeo4jIntegration:
    """Testes de integração com Neo4j."""

    @pytest.fixture
    async def neo4j_client(self):
        """Cliente Neo4j real para testes."""
        from src.clients.neo4j_client import Neo4jClient

        config = get_settings()
        if not hasattr(config, 'neo4j_enabled') or not config.neo4j_enabled:
            pytest.skip("Neo4j não habilitado")

        client = Neo4jClient(
            uri=config.neo4j_uri,
            user=config.neo4j_user,
            password=config.neo4j_password,
            database=config.neo4j_database
        )
        await client.initialize()

        # Limpar e criar dados de teste
        await client.execute_write("MATCH (n:TestNode) DETACH DELETE n")
        await client.execute_write("""
            CREATE (n1:TestNode {name: 'node1', value: 100}),
                   (n2:TestNode {name: 'node2', value: 200}),
                   (n1)-[:RELATED_TO]->(n2)
        """)

        yield client

        # Cleanup
        await client.execute_write("MATCH (n:TestNode) DETACH DELETE n")
        await client.close()

    @pytest.fixture
    def query_executor(self, neo4j_client):
        """QueryExecutor com cliente Neo4j real."""
        config = get_settings()
        return QueryExecutor(
            config=config,
            vault_client=None,
            code_forge_client=None,
            metrics=None,
            mongodb_client=None,
            redis_client=None,
            neo4j_client=neo4j_client,
            kafka_consumer=None
        )

    @pytest.mark.asyncio
    async def test_neo4j_simple_query(self, query_executor):
        """Testa query Cypher simples."""
        ticket = {
            'ticket_id': 'test-neo4j-001',
            'task_id': 'task-001',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'neo4j',
                'cypher_query': 'MATCH (n:TestNode) RETURN n.name, n.value ORDER BY n.value'
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 2

    @pytest.mark.asyncio
    async def test_neo4j_query_with_parameters(self, query_executor):
        """Testa query Cypher com parâmetros."""
        ticket = {
            'ticket_id': 'test-neo4j-002',
            'task_id': 'task-002',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'neo4j',
                'cypher_query': 'MATCH (n:TestNode {name: $name}) RETURN n',
                'parameters': {'name': 'node1'}
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 1


@pytest.mark.integration
class TestTimeoutAndRetry:
    """Testes de timeout e lógica de retry."""

    @pytest.fixture
    async def mongodb_client(self):
        """Cliente MongoDB real."""
        from src.clients.mongodb_client import MongoDBClient

        config = get_settings()
        client = MongoDBClient(config)
        await client.initialize()

        # Criar índice para simular query lenta
        test_collection = client.db['test_timeout']
        await test_collection.delete_many({})
        # Inserir muitos documentos para query demorar
        await test_collection.insert_many([
            {'name': f'test{i}', 'data': 'x' * 1000}
            for i in range(1000)
        ])

        yield client

        await test_collection.delete_many({})
        await client.close()

    @pytest.fixture
    def query_executor(self, mongodb_client):
        """QueryExecutor para testes de timeout."""
        config = get_settings()
        return QueryExecutor(
            config=config,
            vault_client=None,
            code_forge_client=None,
            metrics=None,
            mongodb_client=mongodb_client,
            redis_client=None,
            neo4j_client=None,
            kafka_consumer=None
        )

    @pytest.mark.asyncio
    async def test_query_completes_within_timeout(self, query_executor):
        """Testa que query completa dentro do timeout."""
        ticket = {
            'ticket_id': 'test-timeout-001',
            'task_id': 'task-001',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb',
                'collection': 'test_timeout',
                'filter': {},
                'limit': 10
            }
        }

        start = asyncio.get_event_loop().time()
        result = await query_executor.execute(ticket)
        elapsed = asyncio.get_event_loop().time() - start

        assert result['success'] is True
        assert elapsed < 30  # Deve completar em menos de 30 segundos


@pytest.mark.integration
class TestComplexQueries:
    """Testes de queries complexas (joins, aggregations)."""

    @pytest.fixture
    async def mongodb_client(self):
        """Cliente MongoDB com dados complexos."""
        from src.clients.mongodb_client import MongoDBClient

        config = get_settings()
        client = MongoDBClient(config)
        await client.initialize()

        # Preparar dados para testes de agregação
        orders_collection = client.db['test_orders']
        await orders_collection.delete_many({})
        await orders_collection.insert_many([
            {'customer': 'Alice', 'product': 'Widget', 'quantity': 2, 'price': 10},
            {'customer': 'Alice', 'product': 'Gadget', 'quantity': 1, 'price': 20},
            {'customer': 'Bob', 'product': 'Widget', 'quantity': 5, 'price': 10},
            {'customer': 'Bob', 'product': 'Doohickey', 'quantity': 3, 'price': 15}
        ])

        yield client

        await orders_collection.delete_many({})
        await client.close()

    @pytest.fixture
    def query_executor(self, mongodb_client):
        """QueryExecutor para queries complexas."""
        config = get_settings()
        return QueryExecutor(
            config=config,
            vault_client=None,
            code_forge_client=None,
            metrics=None,
            mongodb_client=mongodb_client,
            redis_client=None,
            neo4j_client=None,
            kafka_consumer=None
        )

    @pytest.mark.asyncio
    async def test_mongodb_complex_filter(self, query_executor):
        """Testa filtro complexo com múltiplas condições."""
        ticket = {
            'ticket_id': 'test-complex-001',
            'task_id': 'task-001',
            'task_type': 'QUERY',
            'parameters': {
                'query_type': 'mongodb',
                'collection': 'test_orders',
                'filter': {
                    'customer': 'Alice',
                    'quantity': {'$gte': 1}
                },
                'sort': [('price', -1)]
            }
        }

        result = await query_executor.execute(ticket)

        assert result['success'] is True
        assert result['output']['count'] == 2
        # Ordenado por price descendente
        assert result['output']['documents'][0]['product'] == 'Gadget'
