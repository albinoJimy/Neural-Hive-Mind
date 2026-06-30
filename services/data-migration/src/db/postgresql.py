"""
PostgreSQL Client para Data Migration Service.

Implementa conexão assíncrona com PostgreSQL usando asyncpg
para extrair dados do banco legado.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from src.config.settings import get_settings

logger = structlog.get_logger()

# Regex para validar identificadores SQL (table names, column names)
# Segue o padrão PostgreSQL: [a-zA-Z_][a-zA-Z0-9_]*
SQL_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$")


def validate_sql_identifier(identifier: str, identifier_type: str = "identifier") -> None:
    """
    Valida se um identificador SQL é seguro contra injection.

    Args:
        identifier: Nome do identificador (table, column, schema)
        identifier_type: Tipo do identificador para mensagem de erro

    Raises:
        ValueError: Se o identificador contiver caracteres inválidos
    """
    if not identifier:
        raise ValueError(f"{identifier_type} cannot be empty")

    if not SQL_IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(
            f"Invalid {identifier_type}: '{identifier}'. "
            f"Only alphanumeric characters, underscores, and dots are allowed."
        )


class PostgreSQLClient:
    """
    Cliente PostgreSQL para extração de dados do sistema legado.

    Suporta conexão assíncrona com pool de conexões via asyncpg.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        min_size: int = 10,
        max_size: int = 100,
        dsn: Optional[str] = None,
    ):
        """
        Inicializa cliente PostgreSQL.

        Args:
            host: Host do PostgreSQL
            port: Porta do PostgreSQL
            database: Nome do banco de dados
            user: Usuário do PostgreSQL
            password: Senha do PostgreSQL
            min_size: Tamanho mínimo do pool de conexões
            max_size: Tamanho máximo do pool de conexões
            dsn: DSN completo (sobrescreve outros parâmetros se fornecido)
        """
        if dsn:
            self.dsn = dsn
        else:
            # Se nenhum parâmetro for fornecido, usar settings
            if not any([host, port, database, user]):
                settings = get_settings()
                self.dsn = settings.postgres_url
            else:
                self.dsn = self._build_dsn(
                    host or "localhost",
                    port or 5432,
                    database or "postgres",
                    user or "postgres",
                    password,
                )

        self.min_size = min_size
        self.max_size = max_size
        self.pool = None
        self._connected = False

    def _build_dsn(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: Optional[str],
    ) -> str:
        """Constrói DSN de conexão."""
        if password:
            return f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return f"postgresql://{user}@{host}:{port}/{database}"

    async def connect(self) -> None:
        """
        Estabelece conexão com PostgreSQL e cria pool.

        Raises:
            ConnectionError: Se não conseguir conectar
        """
        try:
            import asyncpg

            self.pool = await asyncpg.create_pool(
                self.dsn, min_size=self.min_size, max_size=self.max_size, command_timeout=60
            )
            self._connected = True
            logger.info(
                "postgresql_client_connected",
                dsn=self._mask_dsn(self.dsn),
                min_size=self.min_size,
                max_size=self.max_size,
            )
        except ImportError as e:
            logger.error("asyncpg_not_installed", error=str(e))
            raise RuntimeError("asyncpg é necessário. Instale: pip install asyncpg") from e
        except Exception as e:
            logger.error("postgresql_connection_failed", error=str(e))
            raise ConnectionError(f"Falha ao conectar ao PostgreSQL: {e}") from e

    async def disconnect(self) -> None:
        """Fecha pool de conexões."""
        if self.pool:
            await self.pool.close()
            self._connected = False
            logger.info("postgresql_client_disconnected")

    async def is_connected(self) -> bool:
        """Verifica se está conectado."""
        return self._connected and self.pool is not None

    async def execute_query(
        self,
        query: str,
        params: Optional[tuple] = None,
        fetch: str = "all",
    ) -> List[Dict[str, Any]]:
        """
        Executa query SQL e retorna resultados.

        Args:
            query: Query SQL a executar
            params: Parâmetros para query preparada
            fetch: Tipo de fetch ('all', 'one', 'val', 'none')

        Returns:
            Lista de dicionários com resultados

        Raises:
            RuntimeError: Se não estiver conectado
        """
        if not self._connected or not self.pool:
            raise RuntimeError("PostgreSQL não está conectado. Chame connect() primeiro.")

        try:
            async with self.pool.acquire() as conn:
                if fetch == "all":
                    results = (
                        await conn.fetch(query, *params) if params else await conn.fetch(query)
                    )
                    return [dict(row) for row in results]
                elif fetch == "one":
                    result = (
                        await conn.fetchrow(query, *params)
                        if params
                        else await conn.fetchrow(query)
                    )
                    return dict(result) if result else None
                elif fetch == "val":
                    result = (
                        await conn.fetchval(query, *params)
                        if params
                        else await conn.fetchval(query)
                    )
                    return result
                elif fetch == "none":
                    await conn.execute(query, *params) if params else await conn.execute(query)
                    return []
                else:
                    raise ValueError(
                        f"fetch deve ser 'all', 'one', 'val' ou 'none', recebido: {fetch}"
                    )
        except Exception as e:
            logger.error("query_execution_failed", query=query[:100], error=str(e))
            raise

    async def get_tables(
        self,
        schema: str = "public",
        limit: Optional[int] = None,
    ) -> List[str]:
        """
        Lista tabelas no schema.

        Args:
            schema: Schema para listar tabelas
            limit: Limite de tabelas

        Returns:
            Lista de nomes de tabelas
        """
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        params = [schema]

        if limit:
            query += " LIMIT $2"
            params.append(limit)

        results = await self.execute_query(query, tuple(params))
        return [row["table_name"] for row in results]

    async def get_table_schema(
        self,
        table_name: str,
        schema: str = "public",
    ) -> List[Dict[str, Any]]:
        """
        Obtém schema detalhado de uma tabela.

        Args:
            table_name: Nome da tabela
            schema: Schema da tabela

        Returns:
            Lista de dicionários com informações das colunas
        """
        query = """
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = $1
            AND table_name = $2
            ORDER BY ordinal_position
        """

        return await self.execute_query(query, (schema, table_name))

    async def get_table_count(
        self,
        table_name: str,
        schema: str = "public",
        where: Optional[str] = None,
    ) -> int:
        """
        Conta linhas de uma tabela.

        Args:
            table_name: Nome da tabela
            schema: Schema da tabela
            where: Cláusula WHERE adicional (sem WHERE) - NÃO SUPORTADO por segurança

        Returns:
            Número de linhas

        Raises:
            ValueError: Se identificadores forem inválidos
        """
        # Validar identificadores contra SQL injection
        validate_sql_identifier(schema, "schema")
        validate_sql_identifier(table_name, "table_name")

        # NÃO suportar WHERE customizado por segurança - risk of SQL injection
        if where:
            logger.warning(
                "unsafe_where_clause_provided",
                msg="WHERE clause not supported for security reasons",
            )
            raise ValueError(
                "Custom WHERE clauses are not supported in get_table_count "
                "for SQL injection protection. Use fetch_batch with proper filtering instead."
            )

        # Identificadores (schema/table) NÃO podem ser placeholders ($1/$2) em
        # PostgreSQL — placeholders ligam apenas VALORES. Interpola-se os
        # identificadores JÁ validados acima por validate_sql_identifier (defesa
        # anti-injection), espelhando o padrão seguro de fetch_batch.
        query = f"SELECT COUNT(*) FROM {schema}.{table_name}"
        result = await self.execute_query(query, fetch="val")
        return result if isinstance(result, int) else 0

    async def fetch_batch(
        self,
        table_name: str,
        offset: int = 0,
        batch_size: int = 1000,
        columns: Optional[List[str]] = None,
        schema: str = "public",
        where: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch de um lote de dados da tabela.

        Args:
            table_name: Nome da tabela
            offset: Offset para paginação
            batch_size: Tamanho do lote
            columns: Colunas específicas (None = todas)
            schema: Schema da tabela
            where: Cláusula WHERE (sem WHERE) - NÃO SUPORTADO por segurança
            order_by: Coluna para ordenação

        Returns:
            Lista de dicionários com os dados

        Raises:
            ValueError: Se identificadores forem inválidos ou cláusulas inseguras
        """
        # Validar identificadores contra SQL injection
        validate_sql_identifier(schema, "schema")
        validate_sql_identifier(table_name, "table_name")

        # NÃO suportar WHERE customizado por segurança
        if where:
            raise ValueError(
                "Custom WHERE clauses are not supported in fetch_batch "
                "for SQL injection protection."
            )

        # Validar column names se fornecidas
        if columns:
            for col in columns:
                validate_sql_identifier(col, "column")

        # Usar identifiers validados na query
        col_clause = ", ".join(columns) if columns else "*"

        # Construir query com parameter binding para valores
        # Note: Identificadores (table, schema, columns) são validados via regex
        # Valores (limit, offset) usam parameter binding
        query = f"SELECT {col_clause} FROM {schema}.{table_name}"

        if order_by:
            validate_sql_identifier(order_by, "order_by")
            query += f" ORDER BY {order_by}"
        else:
            # Adiciona ORDER BY por id se existir para paginação determinística
            query += " ORDER BY 1"  # Primeira coluna

        # Usar parameter binding para LIMIT e OFFSET
        query += " LIMIT $1 OFFSET $2"

        return await self.execute_query(query, (batch_size, offset))

    async def insert_batch(
        self,
        table: str,
        data: List[Dict[str, Any]],
        schema: str = "public",
    ) -> int:
        """
        Insere um lote de linhas numa tabela do destino (escrita real).

        Usado por ``BatchMigrator._migrate_table`` para gravar as linhas já
        transformadas no banco moderno. Sem este método o ``target_client``
        (um ``PostgreSQLClient``) não suportava escrita e a migração gravava 0
        linhas (bug B da migração J4 real).

        Args:
            table: Nome da tabela de destino.
            data: Lista de dicts (linhas transformadas). Linhas homogéneas —
                as colunas são derivadas das chaves da 1ª linha.
            schema: Schema da tabela de destino.

        Returns:
            Número de linhas inseridas (``len(data)``).

        Raises:
            ValueError: Se schema/tabela/coluna forem identificadores inválidos.
            RuntimeError: Se não estiver conectado.
        """
        if not data:
            return 0

        # Validar identificadores ANTES de qualquer interpolação (defesa
        # anti-injection — mesmo padrão de get_table_count/fetch_batch).
        validate_sql_identifier(schema, "schema")
        validate_sql_identifier(table, "table")

        # Colunas derivadas da 1ª linha; exigir homogeneidade para evitar
        # desalinhamento entre colunas da query e valores enviados.
        cols = list(data[0].keys())
        if not cols:
            raise ValueError("insert_batch: linhas sem colunas")
        for col in cols:
            validate_sql_identifier(col, "column")

        expected = set(cols)
        for idx, row in enumerate(data):
            if set(row.keys()) != expected:
                raise ValueError(
                    f"insert_batch: linha {idx} tem colunas diferentes da 1ª linha "
                    f"(esperado {sorted(expected)}, obtido {sorted(row.keys())})"
                )

        # Identificadores (schema/table/colunas) JÁ validados são interpolados;
        # os VALORES usam placeholders $1..$N (binding seguro do asyncpg).
        col_clause = ", ".join(cols)
        placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
        query = f"INSERT INTO {schema}.{table} ({col_clause}) VALUES ({placeholders})"

        rows = [tuple(row.get(col) for col in cols) for row in data]

        if not self._connected or not self.pool:
            raise RuntimeError("PostgreSQL não está conectado. Chame connect() primeiro.")

        try:
            async with self.pool.acquire() as conn:
                # executemany NÃO simula sucesso: se os tipos não baterem, asyncpg
                # levanta e nós relançamos (sem mascarar a falha).
                await conn.executemany(query, rows)
        except Exception as e:
            logger.error(
                "insert_batch_failed",
                table=f"{schema}.{table}",
                rows=len(data),
                error=str(e),
            )
            raise

        return len(data)

    async def get_primary_keys(
        self,
        table_name: str,
        schema: str = "public",
    ) -> List[str]:
        """
        Obtém chaves primárias de uma tabela.

        Args:
            table_name: Nome da tabela
            schema: Schema da tabela

        Returns:
            Lista de nomes das colunas PK
        """
        query = """
            SELECT a.attname AS column_name
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid
                AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = $1::regclass
            AND i.indisprimary
        """

        results = await self.execute_query(query, (f"{schema}.{table_name}",))
        return [row["column_name"] for row in results]

    async def get_foreign_keys(
        self,
        table_name: str,
        schema: str = "public",
    ) -> List[Dict[str, Any]]:
        """
        Obtém chaves estrangeiras de uma tabela.

        Args:
            table_name: Nome da tabela
            schema: Schema da tabela

        Returns:
            Lista de dicionários com informações das FKs
        """
        query = """
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = $1
            AND tc.table_name = $2
        """

        return await self.execute_query(query, (schema, table_name))

    async def get_indexes(
        self,
        table_name: str,
        schema: str = "public",
    ) -> List[Dict[str, Any]]:
        """
        Obtém índices de uma tabela.

        Args:
            table_name: Nome da tabela
            schema: Schema da tabela

        Returns:
            Lista de dicionários com informações dos índices
        """
        query = """
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = $1
            AND tablename = $2
            AND indexname NOT LIKE '%%_pkey'
        """

        return await self.execute_query(query, (schema, table_name))

    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica saúde da conexão PostgreSQL.

        Returns:
            Dicionário com status de saúde
        """
        try:
            start = datetime.now(timezone.utc)
            result = await self.execute_query("SELECT 1 as health_check", fetch="val")
            latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            return {
                "status": "healthy" if result == 1 else "unhealthy",
                "latency_ms": round(latency_ms, 2),
                "connected": self._connected,
            }
        except Exception as e:
            logger.error("postgresql_health_check_failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "connected": False,
            }

    def _mask_dsn(self, dsn: str) -> str:
        """Mascara senha no DSN para logs."""
        if "@" not in dsn:
            return dsn
        parts = dsn.split("@")
        user_part = parts[0]
        # Formato: postgresql://user:pass@host:port/db ou postgresql://user@host:port/db
        if "://" in user_part:
            protocol_user = user_part.split("://")
            if len(protocol_user) == 2:
                protocol = protocol_user[0] + "://"
                user_info = protocol_user[1]
                if ":" in user_info:
                    user, _ = user_info.split(":", 1)
                    return f"{protocol}{user}:****@{parts[1]}"
        # Sem protocolo no user_part
        if ":" in user_part:
            user, _ = user_part.split(":", 1)
            return f"{user}:****@{parts[1]}"
        return dsn

    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()

    @classmethod
    def _reset_for_tests(cls) -> None:
        """Reseta singleton para testes."""
        global _postgresql_client
        _postgresql_client = None


_postgresql_client: Optional[PostgreSQLClient] = None


def get_postgresql_client() -> PostgreSQLClient:
    """
    Retorna singleton do PostgreSQL client.

    Returns:
        Instância de PostgreSQLClient
    """
    global _postgresql_client
    if _postgresql_client is None:
        _postgresql_client = PostgreSQLClient()
    return _postgresql_client
