"""
Testes unitários para cliente PostgreSQL (asyncpg).

Cobre conexão, queries, health check e operações comuns.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.postgresql import PostgreSQLClient, get_postgresql_client


@asynccontextmanager
async def mock_pool_with_conn(mock_conn):
    """Helper para criar mock pool que retorna conexão."""

    class MockPool:
        @asynccontextmanager
        async def acquire(self):
            yield mock_conn

    yield MockPool()


@pytest.fixture(autouse=True)
def reset_postgresql_singleton():
    """Reseta singleton do PostgreSQL entre testes."""
    PostgreSQLClient._reset_for_tests()
    yield
    PostgreSQLClient._reset_for_tests()


class TestPostgreSQLClient:
    """Testes para PostgreSQLClient."""

    def test_initialization_with_dsn(self):
        """Verifica inicialização com DSN completo."""
        dsn = "postgresql://user:password@localhost:5432/legacy_db"
        client = PostgreSQLClient(dsn=dsn)

        assert client.dsn == dsn
        assert client.min_size == 10
        assert client.max_size == 100

    def test_initialization_with_params(self):
        """Verifica inicialização com parâmetros individuais."""
        client = PostgreSQLClient(
            host="localhost",
            port=5432,
            database="legacy_db",
            user="user",
            password="password",
            min_size=5,
            max_size=50,
        )

        assert client.dsn == "postgresql://user:password@localhost:5432/legacy_db"
        assert client.min_size == 5
        assert client.max_size == 50

    def test_initialization_without_password(self):
        """Verifica inicialização sem senha."""
        client = PostgreSQLClient(host="localhost", port=5432, database="legacy_db", user="user")

        assert client.dsn == "postgresql://user@localhost:5432/legacy_db"

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Verifica conexão com sucesso."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        async def mock_create(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=mock_create):
            await client.connect()

            assert client._connected is True
            assert client.pool == mock_pool

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        """Verifica falha na conexão."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        with patch("asyncpg.create_pool", side_effect=Exception("Connection refused")):
            with pytest.raises(ConnectionError, match="Falha ao conectar ao PostgreSQL"):
                await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Verifica desconexão."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        async def mock_create(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=mock_create):
            await client.connect()
            await client.disconnect()

            assert client._connected is False
            mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected(self):
        """Verifica verificação de conexão."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        # Antes de conectar
        assert await client.is_connected() is False

        mock_pool = MagicMock()

        async def mock_create(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=mock_create):
            await client.connect()
            assert await client.is_connected() is True

    @pytest.mark.asyncio
    async def test_execute_query_fetch_all(self):
        """Verifica execução de query com fetch='all'."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": 1, "name": "test"}])

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        results = await client.execute_query("SELECT * FROM users")

        assert len(results) == 1
        assert results[0]["id"] == 1
        mock_conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_raises_when_not_connected(self):
        """Verifica erro quando não conectado."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        with pytest.raises(RuntimeError, match="PostgreSQL não está conectado"):
            await client.execute_query("SELECT 1")

    @pytest.mark.asyncio
    async def test_execute_query_invalid_fetch(self):
        """Verifica erro para fetch inválido."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        with pytest.raises(ValueError, match="fetch deve ser 'all', 'one', 'val' ou 'none'"):
            await client.execute_query("SELECT 1", fetch="invalid")

    @pytest.mark.asyncio
    async def test_get_tables(self):
        """Verifica listagem de tabelas."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {"table_name": "users"},
                {"table_name": "orders"},
                {"table_name": "products"},
            ]
        )

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        tables = await client.get_tables(schema="public")

        assert len(tables) == 3
        assert "users" in tables
        assert "orders" in tables
        assert "products" in tables

    @pytest.mark.asyncio
    async def test_get_table_schema(self):
        """Verifica obtenção de schema da tabela."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "column_name": "id",
                    "data_type": "integer",
                    "is_nullable": "NO",
                    "column_default": "nextval('users_id_seq')",
                },
                {
                    "column_name": "name",
                    "data_type": "character varying",
                    "is_nullable": "NO",
                    "column_default": None,
                },
            ]
        )

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        schema = await client.get_table_schema("users", schema="public")

        assert len(schema) == 2
        assert schema[0]["column_name"] == "id"
        assert schema[0]["data_type"] == "integer"

    @pytest.mark.asyncio
    async def test_get_table_count(self):
        """Verifica contagem de linhas da tabela."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(return_value=10000)

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        count = await client.get_table_count("users")

        assert count == 10000
        mock_conn.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_batch(self):
        """Verifica fetch de batch de dados."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.fetch = AsyncMock(
            return_value=[{"id": i, "name": f"user_{i}"} for i in range(10)]
        )

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        batch = await client.fetch_batch("users", offset=0, batch_size=10)

        assert len(batch) == 10
        assert batch[0]["id"] == 0
        assert batch[0]["name"] == "user_0"

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Verifica health check com sucesso."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        result = await client.health_check()

        assert result["status"] == "healthy"
        assert result["connected"] is True
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Verifica health check com falha."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.fetchval = AsyncMock(side_effect=Exception("Connection lost"))

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        result = await client.health_check()

        assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Verifica uso como context manager."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        async def mock_create(*args, **kwargs):
            return mock_pool

        with patch("asyncpg.create_pool", side_effect=mock_create):
            async with PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db") as client:
                assert client._connected is True

            assert client._connected is False
            mock_pool.close.assert_called_once()

    def test_mask_dsn_with_password(self):
        """Verifica mascaramento de DSN com senha."""
        client = PostgreSQLClient(dsn="postgresql://user:secret@localhost:5432/db")
        masked = client._mask_dsn(client.dsn)

        assert "secret" not in masked
        assert "****" in masked

    def test_mask_dsn_without_password(self):
        """Verifica mascaramento de DSN sem senha."""
        client = PostgreSQLClient(dsn="postgresql://user@localhost:5432/db")
        masked = client._mask_dsn(client.dsn)

        # Quando não há senha, o DSN é preservado (pode ter ou não máscara)
        # O importante é que localhost está lá
        assert "localhost" in masked


class TestGetPostgreSQLClient:
    """Testes para função get_postgresql_client."""

    @pytest.mark.asyncio
    async def test_returns_singleton_instance(self):
        """Verifica que retorna instância singleton."""
        with patch("src.db.postgresql.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.postgres_url = "postgresql://user:pass@localhost:5432/db"
            mock_get_settings.return_value = mock_settings

            client1 = get_postgresql_client()
            client2 = get_postgresql_client()

            assert client1 is client2

    @pytest.mark.asyncio
    async def test_creates_from_settings(self):
        """Verifica criação a partir de settings."""
        with patch("src.db.postgresql.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.postgres_url = "postgresql://user:pass@localhost:5432/legacy_db"
            mock_get_settings.return_value = mock_settings

            client = get_postgresql_client()

            # O DSN deve vir das settings
            assert client.dsn == "postgresql://user:pass@localhost:5432/legacy_db"
