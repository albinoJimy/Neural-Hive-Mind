"""
PostgreSQL Client para Analyst Agents.

Implementa conexão assíncrona com PostgreSQL usando asyncpg.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class PostgreSQLClient:
    """
    Cliente PostgreSQL para consulta de insights e ações de analistas.

    Suporta conexão assíncrona com pool de conexões via asyncpg.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "neural_hive",
        user: str = "postgres",
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
            self.dsn = self._build_dsn(host, port, database, user, password)

        self.min_size = min_size
        self.max_size = max_size
        self.pool = None
        self._connected = False

    def _build_dsn(
        self, host: str, port: int, database: str, user: str, password: Optional[str]
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
        self, query: str, params: Optional[tuple] = None, fetch: str = "all"
    ) -> list[dict[str, Any]]:
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

    async def get_insights(
        self,
        plan_id: Optional[str] = None,
        analyst_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        time_range: Optional[dict[str, datetime]] = None,
    ) -> list[dict[str, Any]]:
        """
        Busca insights de analistas do PostgreSQL.

        Args:
            plan_id: ID do plano para filtrar
            analyst_type: Tipo de analista para filtrar
            limit: Limite de resultados
            offset: Offset para paginação
            time_range: Dicionário com 'start' e 'end' datetime

        Returns:
            Lista de insights
        """
        query = """
            SELECT
                id,
                plan_id,
                analyst_type,
                insight_data,
                created_at,
                updated_at
            FROM analyst_insights
            WHERE 1=1
        """
        params = []

        if plan_id:
            query += " AND plan_id = $" + str(len(params) + 1)
            params.append(plan_id)

        if analyst_type:
            query += " AND analyst_type = $" + str(len(params) + 1)
            params.append(analyst_type)

        if time_range:
            start = time_range.get("start")
            end = time_range.get("end")
            if start:
                query += " AND created_at >= $" + str(len(params) + 1)
                params.append(start)
            if end:
                query += " AND created_at <= $" + str(len(params) + 1)
                params.append(end)

        query += (
            " ORDER BY created_at DESC LIMIT $"
            + str(len(params) + 1)
            + " OFFSET $"
            + str(len(params) + 2)
        )
        params.extend([limit, offset])

        return await self.execute_query(query, tuple(params) if params else None)

    async def get_analyst_actions(
        self,
        insight_id: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Busca ações de analistas do PostgreSQL.

        Args:
            insight_id: ID do insight relacionado
            action_type: Tipo de ação para filtrar
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de ações
        """
        query = """
            SELECT
                id,
                insight_id,
                action_type,
                action_data,
                executed_at,
                status
            FROM analyst_actions
            WHERE 1=1
        """
        params = []

        if insight_id:
            query += " AND insight_id = $" + str(len(params) + 1)
            params.append(insight_id)

        if action_type:
            query += " AND action_type = $" + str(len(params) + 1)
            params.append(action_type)

        query += (
            " ORDER BY executed_at DESC LIMIT $"
            + str(len(params) + 1)
            + " OFFSET $"
            + str(len(params) + 2)
        )
        params.extend([limit, offset])

        return await self.execute_query(query, tuple(params) if params else None)

    async def get_feature_usage(
        self,
        feature_name: Optional[str] = None,
        time_range: Optional[dict[str, datetime]] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Busca estatísticas de uso de features.

        Args:
            feature_name: Nome da feature para filtrar
            time_range: Dicionário com 'start' e 'end' datetime
            limit: Limite de resultados

        Returns:
            Lista de estatísticas de uso
        """
        query = """
            SELECT
                feature_name,
                usage_count,
                last_used_at,
                unique_users
            FROM feature_usage
            WHERE 1=1
        """
        params = []

        if feature_name:
            query += " AND feature_name = $" + str(len(params) + 1)
            params.append(feature_name)

        if time_range:
            start = time_range.get("start")
            end = time_range.get("end")
            if start:
                query += " AND last_used_at >= $" + str(len(params) + 1)
                params.append(start)
            if end:
                query += " AND last_used_at <= $" + str(len(params) + 1)
                params.append(end)

        query += " ORDER BY usage_count DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        return await self.execute_query(query, tuple(params) if params else None)

    async def get_insight_by_id(self, insight_id: str) -> Optional[dict[str, Any]]:
        """
        Busca insight por ID.

        Args:
            insight_id: ID do insight

        Returns:
            Dicionário com insight ou None
        """
        query = """
            SELECT
                id,
                plan_id,
                analyst_type,
                insight_data,
                created_at,
                updated_at
            FROM analyst_insights
            WHERE id = $1
        """
        return await self.execute_query(query, (insight_id,), fetch="one")

    async def get_insights_by_plan(self, plan_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """
        Busca insights por plano.

        Args:
            plan_id: ID do plano
            limit: Limite de resultados

        Returns:
            Lista de insights do plano
        """
        query = """
            SELECT
                id,
                plan_id,
                analyst_type,
                insight_data,
                created_at,
                updated_at
            FROM analyst_insights
            WHERE plan_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """
        return await self.execute_query(query, (plan_id, limit))

    async def count_insights(
        self, plan_id: Optional[str] = None, analyst_type: Optional[str] = None
    ) -> int:
        """
        Conta insights por filtro.

        Args:
            plan_id: ID do plano para filtrar
            analyst_type: Tipo de analista para filtrar

        Returns:
            Número de insights
        """
        query = "SELECT COUNT(*) FROM analyst_insights WHERE 1=1"
        params = []

        if plan_id:
            query += " AND plan_id = $" + str(len(params) + 1)
            params.append(plan_id)

        if analyst_type:
            query += " AND analyst_type = $" + str(len(params) + 1)
            params.append(analyst_type)

        result = await self.execute_query(query, tuple(params) if params else None, fetch="val")
        return result if isinstance(result, int) else 0

    async def get_insights_statistics(self, time_range_hours: int = 24) -> dict[str, Any]:
        """
        Obtém estatísticas agregadas de insights.

        Args:
            time_range_hours: Janela de tempo em horas

        Returns:
            Dicionário com estatísticas
        """
        since = datetime.now(UTC) - timedelta(hours=time_range_hours)

        query = """
            SELECT
                analyst_type,
                COUNT(*) as count,
                AVG(COALESCE((insight_data->>'confidence')::float, 0)) as avg_confidence
            FROM analyst_insights
            WHERE created_at >= $1
            GROUP BY analyst_type
            ORDER BY count DESC
        """

        results = await self.execute_query(query, (since,))

        by_type = {}
        total_confidence = 0.0
        total_count = 0

        for row in results:
            analyst_type = row["analyst_type"]
            by_type[analyst_type] = {
                "count": row["count"],
                "avg_confidence": row["avg_confidence"] or 0.0,
            }
            total_confidence += row["avg_confidence"] or 0.0
            total_count += row["count"]

        return {
            "by_type": by_type,
            "total_insights": total_count,
            "avg_confidence": total_confidence / len(by_type) if by_type else 0.0,
            "time_range_hours": time_range_hours,
        }

    async def create_tables(self) -> None:
        """
        Cria tabelas necessárias para analyst-agents.

        Esta é uma operação administrativa. Em produção,
        use migrations proper.
        """
        tables = [
            """
            CREATE TABLE IF NOT EXISTS analyst_insights (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                plan_id VARCHAR(255) NOT NULL,
                analyst_type VARCHAR(50) NOT NULL,
                insight_data JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS analyst_actions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                insight_id UUID REFERENCES analyst_insights(id) ON DELETE CASCADE,
                action_type VARCHAR(50) NOT NULL,
                action_data JSONB DEFAULT '{}'::jsonb,
                executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                status VARCHAR(20) DEFAULT 'pending'
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS feature_usage (
                id SERIAL PRIMARY KEY,
                feature_name VARCHAR(100) UNIQUE NOT NULL,
                usage_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                unique_users INTEGER DEFAULT 0
            );
            """,
        ]

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_analyst_insights_plan_id ON analyst_insights(plan_id);",
            "CREATE INDEX IF NOT EXISTS idx_analyst_insights_analyst_type ON analyst_insights(analyst_type);",
            "CREATE INDEX IF NOT EXISTS idx_analyst_insights_created_at ON analyst_insights(created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_analyst_actions_insight_id ON analyst_actions(insight_id);",
            "CREATE INDEX IF NOT EXISTS idx_analyst_actions_executed_at ON analyst_actions(executed_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_feature_usage_feature_name ON feature_usage(feature_name);",
        ]

        try:
            async with self.pool.acquire() as conn:
                for table_sql in tables:
                    await conn.execute(table_sql)
                for index_sql in indexes:
                    await conn.execute(index_sql)
            logger.info("postgresql_tables_created")
        except Exception as e:
            logger.error("postgresql_tables_creation_failed", error=str(e))
            raise

    async def insert_insight(
        self, plan_id: str, analyst_type: str, insight_data: dict[str, Any]
    ) -> str:
        """
        Insere novo insight.

        Args:
            plan_id: ID do plano
            analyst_type: Tipo de analista
            insight_data: Dados do insight

        Returns:
            ID do insight criado
        """
        query = """
            INSERT INTO analyst_insights (plan_id, analyst_type, insight_data)
            VALUES ($1, $2, $3)
            RETURNING id
        """
        result = await self.execute_query(query, (plan_id, analyst_type, insight_data), fetch="val")
        return str(result)

    async def update_insight(self, insight_id: str, insight_data: dict[str, Any]) -> bool:
        """
        Atualiza insight existente.

        Args:
            insight_id: ID do insight
            insight_data: Novos dados

        Returns:
            True se atualizado
        """
        query = """
            UPDATE analyst_insights
            SET insight_data = $2, updated_at = NOW()
            WHERE id = $1
        """
        result = await self.execute_query(query, (insight_id, insight_data), fetch="val")
        # fetch='val' com UPDATE retorna o string de status (ex: 'UPDATE 1')
        return str(result).startswith("UPDATE 1") if result else True

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

    async def health_check(self) -> dict[str, Any]:
        """
        Verifica saúde da conexão PostgreSQL.

        Returns:
            Dicionário com status de saúde
        """
        try:
            start = datetime.now(UTC)
            result = await self.execute_query("SELECT 1 as health_check", fetch="val")
            latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000

            return {
                "status": "healthy" if result == 1 else "unhealthy",
                "latency_ms": round(latency_ms, 2),
                "connected": self._connected,
            }
        except Exception as e:
            logger.error("postgresql_health_check_failed", error=str(e))
            return {"status": "unhealthy", "error": str(e), "connected": False}

    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()
