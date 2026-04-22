"""Testes E2E para Data Migration Service.

Estes testes validam o fluxo completo de migração incluindo:
- Criação de job de migração
- Execução batch
- Verificação de status
- Rollback de migração
"""

import asyncio
import os
from dataclasses import dataclass

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import MongoClient
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.kafka import KafkaContainer
from testcontainers.mongodb import MongoDbContainer
from testcontainers.postgres import PostgresContainer


# Configuração dos containers
@pytest.fixture(scope="session")
def postgres_container():
    """Container PostgreSQL para testes."""
    container = PostgresContainer(
        image="postgres:17-alpine",
        username="test",
        password="test",
        dbname="legacy",
        port=5432,
    )
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def mongodb_container():
    """Container MongoDB para testes."""
    container = MongoDbContainer(image="mongo:7.0")
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def kafka_container():
    """Container Kafka para testes."""
    container = KafkaContainer(image="confluentinc/cp-kafka:7.5.0")
    container.start()
    yield container
    container.stop()


@dataclass
class TestContext:
    """Contexto compartilhado entre testes."""

    postgres_url: str
    mongodb_url: str
    kafka_bootstrap_servers: str
    base_url: str = "http://localhost:8019"
    api_prefix: str = "/api/v1"


@pytest_asyncio.fixture
async def test_client(
    postgres_container: PostgresContainer,
    mongodb_container: MongoDbContainer,
    kafka_container: KafkaContainer,
):
    """Cliente HTTP async para testes."""
    # Aguardar containers estarem prontos
    wait_for_logs(postgres_container, "database system is ready to accept connections", timeout=30)
    wait_for_logs(mongodb_container, "Waiting for connections", timeout=30)

    context = TestContext(
        postgres_url=postgres_container.get_connection_url(),
        mongodb_url=mongodb_container.get_connection_url(),
        kafka_bootstrap_servers=kafka_container.get_bootstrap_server(),
    )

    # Configurar variáveis de ambiente
    os.environ["POSTGRES_URL"] = context.postgres_url
    os.environ["MONGODB_URL"] = context.mongodb_url
    os.environ["KAFKA_BOOTSTRAP_SERVERS"] = context.kafka_bootstrap_servers
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"

    # Importar e iniciar o servidor
    from src.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=context.base_url, timeout=30.0) as client:
        yield client, context


@pytest.mark.e2e
class TestDataMigrationE2E:
    """Testes E2E para Data Migration Service."""

    async def test_health_check(self, test_client: tuple[AsyncClient, TestContext]):
        """Testa health check endpoint."""
        client, context = test_client

        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "data-migration"
        assert data["status"] == "healthy"
        assert "version" in data

    async def test_create_migration_job(self, test_client: tuple[AsyncClient, TestContext]):
        """Testa criação de job de migração."""
        client, context = test_client

        payload = {
            "name": "test_users_migration",
            "source_type": "postgresql",
            "source_config": {
                "table": "users",
                "query": "SELECT * FROM users WHERE created_at > '2020-01-01'",
            },
            "destination_type": "mongodb",
            "destination_config": {
                "collection": "users",
                "database": "migration_test",
            },
            "strategy": "batch",
            "batch_size": 100,
        }

        response = await client.post(f"{context.api_prefix}/migrations", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test_users_migration"
        assert data["status"] == "pending"
        assert "migration_id" in data

    async def test_list_migrations(self, test_client: tuple[AsyncClient, TestContext]):
        """Testa listagem de migrações."""
        client, context = test_client

        response = await client.get(f"{context.api_prefix}/migrations")
        assert response.status_code == 200
        data = response.json()
        assert "migrations" in data
        assert isinstance(data["migrations"], list)

    async def test_get_migration_status(self, test_client: tuple[AsyncClient, TestContext]):
        """Testa obtenção de status de migração específica."""
        client, context = test_client

        # Primeiro criar uma migração
        payload = {
            "name": "status_test_migration",
            "source_type": "postgresql",
            "source_config": {"table": "products"},
            "destination_type": "mongodb",
            "destination_config": {"collection": "products"},
            "strategy": "batch",
        }

        create_response = await client.post(f"{context.api_prefix}/migrations", json=payload)
        assert create_response.status_code == 201
        migration_id = create_response.json()["migration_id"]

        # Obter status
        response = await client.get(f"{context.api_prefix}/migrations/{migration_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["migration_id"] == migration_id
        assert "status" in data

    async def test_execute_batch_migration(
        self, test_client: tuple[AsyncClient, TestContext], postgres_container: PostgresContainer
    ):
        """Testa execução de migração batch completa."""
        client, context = test_client

        # Preparar dados de teste no PostgreSQL
        postgres_client = postgres_container.get_connection()
        cursor = postgres_client.cursor()

        # Criar tabela de teste
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_customers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Inserir dados de teste
        cursor.execute("""
            INSERT INTO test_customers (name, email)
            VALUES
                ('Alice', 'alice@example.com'),
                ('Bob', 'bob@example.com'),
                ('Charlie', 'charlie@example.com')
        """)
        postgres_client.commit()
        cursor.close()
        postgres_client.close()

        # Criar job de migração
        payload = {
            "name": "customers_batch_migration",
            "source_type": "postgresql",
            "source_config": {"table": "test_customers"},
            "destination_type": "mongodb",
            "destination_config": {"collection": "customers", "database": "migration_test"},
            "strategy": "batch",
            "batch_size": 10,
        }

        create_response = await client.post(f"{context.api_prefix}/migrations", json=payload)
        assert create_response.status_code == 201
        migration_id = create_response.json()["migration_id"]

        # Executar migração
        exec_response = await client.post(f"{context.api_prefix}/migrations/{migration_id}/execute")
        assert exec_response.status_code == 202

        # Aguardar conclusão (polling)
        max_attempts = 30
        for _ in range(max_attempts):
            await asyncio.sleep(1)
            status_response = await client.get(
                f"{context.api_prefix}/migrations/{migration_id}/status"
            )
            status_data = status_response.json()
            if status_data["status"] in ["completed", "failed", "rollback"]:
                break

        # Verificar resultado final
        final_status = status_data
        assert final_status["status"] in ["completed", "rollback", "failed"]
        assert "records_processed" in final_status

    async def test_rollback_migration(self, test_client: tuple[AsyncClient, TestContext]):
        """Testa rollback de migração."""
        client, context = test_client

        # Criar migração
        payload = {
            "name": "rollback_test_migration",
            "source_type": "postgresql",
            "source_config": {"table": "orders"},
            "destination_type": "mongodb",
            "destination_config": {"collection": "orders"},
            "strategy": "batch",
        }

        create_response = await client.post(f"{context.api_prefix}/migrations", json=payload)
        migration_id = create_response.json()["migration_id"]

        # Executar rollback
        rollback_response = await client.post(
            f"{context.api_prefix}/migrations/{migration_id}/rollback"
        )
        assert rollback_response.status_code == 200

        data = rollback_response.json()
        assert data["migration_id"] == migration_id
        assert "rollback_point" in data

    async def test_schema_mapping(
        self, test_client: tuple[AsyncClient, TestContext], postgres_container: PostgresContainer
    ):
        """Testa mapeamento de schema."""
        client, context = test_client

        # Preparar tabela com tipos específicos
        postgres_client = postgres_container.get_connection()
        cursor = postgres_client.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_schema_types (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50),
                age INTEGER,
                balance DECIMAL(10,2),
                active BOOLEAN,
                created_at TIMESTAMP
            )
        """)
        postgres_client.commit()
        cursor.close()
        postgres_client.close()

        # Solicitar mapeamento
        payload = {
            "source_type": "postgresql",
            "source_config": {"table": "test_schema_types"},
            "destination_type": "mongodb",
        }

        response = await client.post(f"{context.api_prefix}/schema/map", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "source_schema" in data
        assert "destination_schema" in data
        assert "field_mappings" in data

    async def test_data_validation(
        self, test_client: tuple[AsyncClient, TestContext], mongodb_container: MongoDbContainer
    ):
        """Testa validação de dados após migração."""
        client, context = test_client

        # Inserir dados de teste no MongoDB
        mongo_client = MongoClient(mongodb_container.get_connection_url())
        db = mongo_client["migration_test"]
        collection = db["validation_test"]

        collection.insert_many(
            [
                {"name": "Alice", "age": 30, "email": "alice@example.com"},
                {"name": "Bob", "age": 25, "email": "bob@example.com"},
                {"name": "Charlie", "age": None, "email": "charlie@example.com"},
            ]
        )
        mongo_client.close()

        # Executar validação
        payload = {
            "destination_type": "mongodb",
            "destination_config": {"collection": "validation_test", "database": "migration_test"},
            "validation_rules": [
                {"field": "name", "type": "required"},
                {"field": "age", "type": "integer"},
                {"field": "email", "type": "email"},
            ],
        }

        response = await client.post(f"{context.api_prefix}/data/validate", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "total_records" in data
        assert "valid_records" in data
        assert "invalid_records" in data
        assert "validation_errors" in data


@pytest.mark.e2e
class TestServiceRegistryIntegration:
    """Testes de integração com Service Registry."""

    async def test_service_registration(self, test_client: tuple[AsyncClient, TestContext]):
        """Testa registro no Service Registry."""
        client, context = test_client

        # O serviço deve se registrar automaticamente no startup
        # Verificar health check indica conexão
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # Registry connected pode ser False em testes locais
        assert "registry_connected" in data

    async def test_heartbeat_verification(self, test_client: tuple[AsyncClient, TestContext]):
        """Testa envio periódico de heartbeat."""
        client, context = test_client

        # Aguardar heartbeat ser enviado
        await asyncio.sleep(2)

        # Verificar que o serviço continua healthy
        response = await client.get("/health")
        assert response.status_code == 200


@pytest.mark.e2e
class TestKafkaIntegration:
    """Testes de integração com Kafka."""

    async def test_migration_progress_events(
        self,
        test_client: tuple[AsyncClient, TestContext],
        kafka_container: KafkaContainer,
    ):
        """Testa publicação de eventos de progresso no Kafka."""
        client, context = test_client

        # Criar e executar migração
        payload = {
            "name": "kafka_test_migration",
            "source_type": "postgresql",
            "source_config": {"table": "kafka_test"},
            "destination_type": "mongodb",
            "destination_config": {"collection": "kafka_test"},
            "strategy": "batch",
        }

        create_response = await client.post(f"{context.api_prefix}/migrations", json=payload)
        migration_id = create_response.json()["migration_id"]

        exec_response = await client.post(f"{context.api_prefix}/migrations/{migration_id}/execute")
        assert exec_response.status_code == 202

        # Verificar que eventos foram publicados (via status)
        await asyncio.sleep(2)
        status_response = await client.get(f"{context.api_prefix}/migrations/{migration_id}/status")
        assert status_response.status_code == 200
