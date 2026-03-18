# MCP Execution Repository

from datetime import datetime, timedelta
from typing import Any

from neural_hive_observability import get_logger

logger = get_logger(__name__)


class MCPExecutionRepository:
    """
    Repositório para logs e métricas de execuções MCP.

    Armazena:
    - Logs de execução de ferramentas
    - Métricas agregadas por servidor/ferramenta
    - Estatísticas de performance
    """

    COLLECTION_NAME = "mcp_tool_executions"

    def __init__(self, mongo_client: Any) -> None:
        """
        Inicializa repositório.

        Args:
            mongo_client: Cliente MongoDB com atributo .database
        """
        self.mongo = mongo_client
        self.collection = mongo_client.database[self.COLLECTION_NAME]

    async def log_execution(
        self,
        execution_id: str,
        server: str,
        tool_name: str,
        params: dict[str, Any],
        result: dict[str, Any] | None,
        status: str,
        duration_ms: int,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Registra execução de ferramenta MCP.

        Args:
            execution_id: ID único da execução
            server: Nome do servidor MCP
            tool_name: Nome da ferramenta
            params: Parâmetros da execução
            result: Resultado da execução
            status: Status (success/error)
            duration_ms: Duração em milissegundos
            metadata: Metadados adicionais

        Returns:
            ID do documento inserido
        """
        document = {
            "_id": execution_id,
            "server": server,
            "tool_name": tool_name,
            "params": params,
            "result": result,
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {},
        }

        result = await self.collection.insert_one(document)
        logger.debug(
            "execution_logged",
            execution_id=execution_id,
            server=server,
            tool=tool_name,
            status=status,
        )
        return str(result.inserted_id)

    async def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        """
        Busca execução por ID.

        Args:
            execution_id: ID da execução

        Returns:
            Documento da execução ou None
        """
        result = await self.collection.find_one({"_id": execution_id})
        return result

    async def get_executions_by_server(
        self,
        server: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Busca execuções por servidor.

        Args:
            server: Nome do servidor
            limit: Limite de resultados

        Returns:
            Lista de execuções
        """
        cursor = (
            self.collection.find({"server": server}).sort("timestamp", -1).limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def get_executions_by_tool(
        self,
        server: str,
        tool_name: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Busca execuções por ferramenta.

        Args:
            server: Nome do servidor
            tool_name: Nome da ferramenta
            limit: Limite de resultados

        Returns:
            Lista de execuções
        """
        cursor = (
            self.collection.find({"server": server, "tool_name": tool_name})
            .sort("timestamp", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def get_recent_executions(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Busca execuções recentes.

        Args:
            limit: Limite de resultados

        Returns:
            Lista de execuções recentes
        """
        cursor = self.collection.find().sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_metrics_by_server(
        self,
        server: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Agrega métricas por servidor.

        Args:
            server: Nome do servidor
            days: Período em dias

        Returns:
            Métricas agregadas
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            {"$match": {"server": server, "timestamp": {"$gte": cutoff_date}}},
            {
                "$group": {
                    "_id": "$server",
                    "total_executions": {"$sum": 1},
                    "success_count": {
                        "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                    },
                    "error_count": {
                        "$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}
                    },
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                    "total_duration_ms": {"$sum": "$duration_ms"},
                }
            },
        ]

        cursor = self.collection.aggregate(pipeline)
        results = await cursor.to_list(length=1)

        if results:
            return results[0]
        return {
            "_id": server,
            "total_executions": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_duration_ms": 0,
        }

    async def get_metrics_by_tool(
        self,
        server: str,
        tool_name: str,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Agrega métricas por ferramenta.

        Args:
            server: Nome do servidor
            tool_name: Nome da ferramenta
            days: Período em dias

        Returns:
            Métricas agregadas
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            {
                "$match": {
                    "server": server,
                    "tool_name": tool_name,
                    "timestamp": {"$gte": cutoff_date},
                }
            },
            {
                "$group": {
                    "_id": {"server": "$server", "tool": "$tool_name"},
                    "total_executions": {"$sum": 1},
                    "success_count": {
                        "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                    },
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "total_executions": 1,
                    "success_count": 1,
                    "avg_duration_ms": 1,
                    "success_rate": {
                        "$divide": ["$success_count", "$total_executions"]
                    },
                }
            },
        ]

        cursor = self.collection.aggregate(pipeline)
        results = await cursor.to_list(length=1)

        if results:
            return results[0]
        return {
            "total_executions": 0,
            "success_count": 0,
            "avg_duration_ms": 0,
            "success_rate": 0.0,
        }

    async def delete_old_executions(
        self,
        days_old: int = 30,
    ) -> int:
        """
        Deleta execuções antigas (TTL).

        Args:
            days_old: Idade em dias para deletar

        Returns:
            Número de documentos deletados
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)

        result = await self.collection.delete_many({"timestamp": {"$lt": cutoff_date}})

        logger.info(
            "old_executions_deleted",
            days_old=days_old,
            deleted_count=result.deleted_count,
        )
        return result.deleted_count


def register_mcp_repository_hooks(
    repository: MCPExecutionRepository,
) -> None:
    """
    Registra hooks para limpeza automática de execuções antigas.

    Args:
        repository: Repositório MCP
    """
    # TODO: Implementar background task para limpeza periódica
    logger.info("mcp_repository_hooks_registered")
