# MCP Execution Repository

import asyncio
from datetime import UTC, datetime

UTC = UTC  # type: ignore, timedelta
from typing import Any

from neural_hive_observability import get_logger

logger = get_logger(__name__)


class MCPCleanupTask:
    """
    Background task para limpeza periódica de execuções MCP antigas.

    Executa a cada 24 horas por padrão, deletando execuções com mais de
    30 dias. Configurável via variáveis de ambiente.
    """

    # Configurações padrão
    DEFAULT_CLEANUP_INTERVAL_HOURS = 24
    DEFAULT_RETENTION_DAYS = 30

    def __init__(
        self,
        repository: "MCPExecutionRepository",
        cleanup_interval_hours: int | None = None,
        retention_days: int | None = None,
    ) -> None:
        """
        Inicializa task de limpeza.

        Args:
            repository: Repositório MCP para limpeza
            cleanup_interval_hours: Intervalo em horas (padrão: 24)
            retention_days: Dias de retenção (padrão: 30)
        """
        self.repository = repository
        self.cleanup_interval = timedelta(
            hours=cleanup_interval_hours or self.DEFAULT_CLEANUP_INTERVAL_HOURS
        )
        self.retention_days = retention_days or self.DEFAULT_RETENTION_DAYS
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._stop_event = asyncio.Event()

    async def _cleanup_loop(self) -> None:
        """
        Loop de limpeza periódica.

        Executa limpeza a cada intervalo configurado até que stop() seja chamado.
        """
        logger.info(
            "mcp_cleanup_task_started",
            interval_hours=self.cleanup_interval.total_seconds() / 3600,
            retention_days=self.retention_days,
        )

        while not self._stop_event.is_set():
            try:
                # Executar limpeza
                deleted = await self.repository.delete_old_executions(days_old=self.retention_days)
                logger.info(
                    "mcp_cleanup_completed",
                    deleted_count=deleted,
                    retention_days=self.retention_days,
                )
            except Exception as e:
                logger.exception(
                    "mcp_cleanup_failed",
                    error=str(e),
                    retention_days=self.retention_days,
                )

            # Aguardar próximo ciclo ou sinal de parada
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.cleanup_interval.total_seconds(),
                )
                break
            except TimeoutError:
                # Timeout esperado - continuar loop
                continue

        logger.info("mcp_cleanup_task_stopped")

    async def start(self) -> None:
        """
        Inicia o background task de limpeza.

        Raises:
            RuntimeError: Se task já estiver rodando
        """
        if self._running:
            logger.warning("mcp_cleanup_task_already_running")
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info("mcp_cleanup_task_scheduled")

    async def stop(self) -> None:
        """
        Para o background task de limpeza.

        Aguarda task atual completar antes de retornar.
        """
        if not self._running:
            return

        logger.info("mcp_cleanup_task_stopping")
        self._stop_event.set()

        if self._task:
            await asyncio.shield(self._task)
            self._task = None

        self._running = False
        logger.info("mcp_cleanup_task_stopped_cleanly")

    async def run_once(self) -> int:
        """
        Executa limpeza uma vez (síncrono).

        Útil para testes ou execução manual.

        Returns:
            Número de documentos deletados
        """
        logger.info("mcp_cleanup_manual_run", retention_days=self.retention_days)
        deleted = await self.repository.delete_old_executions(days_old=self.retention_days)
        logger.info("mcp_cleanup_manual_completed", deleted_count=deleted)
        return deleted


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
        self._cleanup_task: MCPCleanupTask | None = None

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
            "timestamp": datetime.now(UTC),
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
        return await self.collection.find_one({"_id": execution_id})

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
        cursor = self.collection.find({"server": server}).sort("timestamp", -1).limit(limit)
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
        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        pipeline = [
            {"$match": {"server": server, "timestamp": {"$gte": cutoff_date}}},
            {
                "$group": {
                    "_id": "$server",
                    "total_executions": {"$sum": 1},
                    "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
                    "error_count": {"$sum": {"$cond": [{"$eq": ["$status", "error"]}, 1, 0]}},
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
        cutoff_date = datetime.now(UTC) - timedelta(days=days)

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
                    "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "total_executions": 1,
                    "success_count": 1,
                    "avg_duration_ms": 1,
                    "success_rate": {"$divide": ["$success_count", "$total_executions"]},
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
        cutoff_date = datetime.now(UTC) - timedelta(days=days_old)

        result = await self.collection.delete_many({"timestamp": {"$lt": cutoff_date}})

        logger.info(
            "old_executions_deleted",
            days_old=days_old,
            deleted_count=result.deleted_count,
        )
        return result.deleted_count

    async def start_cleanup_task(
        self,
        cleanup_interval_hours: int | None = None,
        retention_days: int | None = None,
    ) -> None:
        """
        Inicia background task de limpeza periódica.

        Args:
            cleanup_interval_hours: Intervalo em horas (padrão: 24)
            retention_days: Dias de retenção (padrão: 30)
        """
        if self._cleanup_task is None:
            self._cleanup_task = MCPCleanupTask(
                self,
                cleanup_interval_hours=cleanup_interval_hours,
                retention_days=retention_days,
            )
        await self._cleanup_task.start()

    async def stop_cleanup_task(self) -> None:
        """
        Para background task de limpeza periódica.
        """
        if self._cleanup_task:
            await self._cleanup_task.stop()


def register_mcp_repository_hooks(
    repository: MCPExecutionRepository,
) -> None:
    """
    Registra hooks para limpeza automática de execuções antigas.

    NOTA: Esta função agora registra o background task de limpeza.
    Para ambientes de produção, chamar repository.start_cleanup_task() explicitamente.

    Args:
        repository: Repositório MCP
    """
    logger.info(
        "mcp_repository_hooks_registered",
        cleanup_available=True,
        note="Call repository.start_cleanup_task() to enable background cleanup",
    )
