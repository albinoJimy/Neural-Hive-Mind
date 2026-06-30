"""
Testes unitários para PostgreSQLClient.truncate_table.

Cobre validação de identificador (anti-injection) e construção do SQL
``TRUNCATE ... RESTART IDENTITY CASCADE`` usado no fallback idempotente do
``/rollback`` (limpeza do destino).
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.postgresql import PostgreSQLClient


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


class TestTruncateTable:
    """Testes para PostgreSQLClient.truncate_table."""

    @pytest.mark.asyncio
    async def test_truncate_table_builds_expected_sql(self):
        """Constrói TRUNCATE ... RESTART IDENTITY CASCADE com schema.table."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="TRUNCATE TABLE")

        async def get_pool():
            async with mock_pool_with_conn(mock_conn) as pool:
                return pool

        client.pool = await get_pool()
        client._connected = True

        await client.truncate_table("users", schema="public")

        mock_conn.execute.assert_called_once()
        executed_sql = mock_conn.execute.call_args.args[0]
        assert executed_sql == ("TRUNCATE TABLE public.users RESTART IDENTITY CASCADE")

    @pytest.mark.asyncio
    async def test_truncate_table_uses_fetch_none(self):
        """Usa execute_query com fetch='none' (sem retorno de linhas)."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")
        client.execute_query = AsyncMock(return_value=[])

        await client.truncate_table("contas", schema="modern")

        client.execute_query.assert_awaited_once()
        _, kwargs = client.execute_query.call_args
        assert kwargs.get("fetch") == "none"
        query = client.execute_query.call_args.args[0]
        assert query == "TRUNCATE TABLE modern.contas RESTART IDENTITY CASCADE"

    @pytest.mark.asyncio
    async def test_truncate_table_rejects_malicious_table(self):
        """Identificador malicioso → ValueError (anti-injection)."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")
        client.execute_query = AsyncMock()

        with pytest.raises(ValueError):
            await client.truncate_table("users; DROP TABLE accounts;--")

        client.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_truncate_table_rejects_malicious_schema(self):
        """Schema malicioso → ValueError (anti-injection)."""
        client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")
        client.execute_query = AsyncMock()

        with pytest.raises(ValueError):
            await client.truncate_table("users", schema="public;DROP")

        client.execute_query.assert_not_called()
