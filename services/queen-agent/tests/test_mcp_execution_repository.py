"""
Testes para MCP Execution Repository.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


@pytest.fixture()
def mock_mongo():
    """Mock MongoDB client e collection."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()

    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mock_db.__getitem__ = lambda self, name: mock_collection
    mock_database = MagicMock()
    mock_database.__getitem__ = lambda self, name: mock_collection

    mock_client.database = mock_db

    return mock_client


@pytest.fixture()
def repository(mock_mongo):
    """Cria instância do repositório com mocks."""
    from src.repositories.mcp_execution_repository import MCPExecutionRepository

    return MCPExecutionRepository(mock_mongo)


class TestMCPExecutionRepository:
    """Testes do MCPExecutionRepository."""

    @pytest.mark.asyncio()
    async def test_log_execution(self, repository):
        """Testa log de execução de ferramenta."""
        execution_id = str(uuid4())
        repository.collection.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=execution_id)
        )

        await repository.log_execution(
            execution_id=execution_id,
            server="scout",
            tool_name="list_files",
            params={"path": "/src"},
            result={"files": ["a.py"]},
            status="success",
            duration_ms=150,
        )

        # Verificar que o insert foi chamado
        assert repository.collection.insert_one.called
        call_args = repository.collection.insert_one.call_args[0][0]
        assert call_args["_id"] == execution_id
        assert call_args["server"] == "scout"
        assert call_args["tool_name"] == "list_files"
        assert call_args["status"] == "success"

    @pytest.mark.asyncio()
    async def test_log_execution_with_metadata(self, repository):
        """Testa log com metadados adicionais."""
        execution_id = str(uuid4())
        repository.collection.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=execution_id)
        )

        await repository.log_execution(
            execution_id=execution_id,
            server="optimizer",
            tool_name="suggest_refactors",
            params={"path": "/src"},
            result={"suggestions": []},
            status="success",
            duration_ms=200,
            metadata={"request_id": "req-123", "user": "test-user"},
        )

        assert repository.collection.insert_one.called
        call_args = repository.collection.insert_one.call_args[0][0]
        assert call_args["metadata"]["request_id"] == "req-123"

    @pytest.mark.asyncio()
    async def test_get_execution_by_id(self, repository):
        """Testa busca de execução por ID."""
        execution_id = str(uuid4())

        # Mock response
        repository.collection.find_one = AsyncMock(
            return_value={
                "_id": execution_id,
                "server": "scout",
                "tool_name": "list_files",
                "status": "success",
            }
        )

        result = await repository.get_execution(execution_id)

        assert result["server"] == "scout"
        repository.collection.find_one.assert_called_once_with({"_id": execution_id})

    @pytest.mark.asyncio()
    async def test_get_executions_by_server(self, repository):
        """Testa busca de execuções por servidor."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {"server": "scout", "tool_name": "list_files", "status": "success"},
                {"server": "scout", "tool_name": "search_code", "status": "success"},
            ]
        )
        repository.collection.find.return_value.sort.return_value.limit.return_value = mock_cursor

        results = await repository.get_executions_by_server(server="scout", limit=10)

        assert len(results) == 2
        assert all(r["server"] == "scout" for r in results)

    @pytest.mark.asyncio()
    async def test_get_metrics_by_server(self, repository):
        """Testa agregação de métricas por servidor."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "scout",
                    "total_executions": 100,
                    "success_count": 95,
                    "error_count": 5,
                },
            ]
        )
        repository.collection.aggregate.return_value = mock_cursor

        metrics = await repository.get_metrics_by_server(server="scout")

        assert metrics["total_executions"] == 100
        assert metrics["success_count"] == 95

    @pytest.mark.asyncio()
    async def test_get_metrics_by_tool(self, repository):
        """Testa agregação de métricas por ferramenta."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {"_id": "list_files", "avg_duration_ms": 150, "success_rate": 0.98},
            ]
        )
        repository.collection.aggregate.return_value = mock_cursor

        metrics = await repository.get_metrics_by_tool(server="scout", tool_name="list_files")

        assert metrics["avg_duration_ms"] == 150
        assert metrics["success_rate"] == 0.98

    @pytest.mark.asyncio()
    async def test_get_recent_executions(self, repository):
        """Testa busca de execuções recentes."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "server": "scout",
                    "tool_name": "list_files",
                    "timestamp": datetime.now(),
                },
                {
                    "server": "optimizer",
                    "tool_name": "suggest_refactors",
                    "timestamp": datetime.now(),
                },
            ]
        )
        repository.collection.find.return_value.sort.return_value.limit.return_value = mock_cursor

        results = await repository.get_recent_executions(limit=10)

        assert len(results) == 2

    @pytest.mark.asyncio()
    async def test_delete_old_executions(self, repository):
        """Testa deleção de execuções antigas."""
        repository.collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=50))

        deleted = await repository.delete_old_executions(days_old=30)

        assert deleted == 50
        repository.collection.delete_many.assert_called_once()


class TestMCPExecutionRepositoryIntegration:
    """Testes de integração com MongoDB."""

    @pytest.mark.asyncio()
    async def test_full_lifecycle(self, mock_mongo):
        """Testa ciclo de vida completo: log -> retrieve -> metrics."""
        from src.repositories.mcp_execution_repository import MCPExecutionRepository

        repository = MCPExecutionRepository(mock_mongo)

        execution_id = str(uuid4())

        # 1. Log execution
        repository.collection.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id=execution_id)
        )
        await repository.log_execution(
            execution_id=execution_id,
            server="scout",
            tool_name="list_files",
            params={"path": "/src"},
            result={"files": ["a.py"]},
            status="success",
            duration_ms=100,
        )

        # 2. Retrieve
        repository.collection.find_one = AsyncMock(
            return_value={
                "_id": execution_id,
                "server": "scout",
                "status": "success",
            }
        )
        execution = await repository.get_execution(execution_id)
        assert execution["server"] == "scout"

        # 3. Metrics
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {"_id": "scout", "total_executions": 1, "success_count": 1},
            ]
        )
        repository.collection.aggregate.return_value = mock_cursor
        metrics = await repository.get_metrics_by_server("scout")
        assert metrics["total_executions"] == 1


# =============================================================================
# TESTS: MCPCleanupTask
# =============================================================================


class TestMCPCleanupTask:
    """Testes para MCPCleanupTask."""

    @pytest.mark.asyncio()
    async def test_cleanup_task_initialization(self, mock_mongo):
        """Testa inicialização do cleanup task."""
        from src.repositories.mcp_execution_repository import MCPCleanupTask, MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)
        task = MCPCleanupTask(repo, cleanup_interval_hours=12, retention_days=14)

        assert task.repository == repo
        assert task.cleanup_interval.total_seconds() == 12 * 3600
        assert task.retention_days == 14
        assert not task._running

    @pytest.mark.asyncio()
    async def test_cleanup_task_default_values(self, mock_mongo):
        """Testa valores padrão do cleanup task."""
        from src.repositories.mcp_execution_repository import MCPCleanupTask, MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)
        task = MCPCleanupTask(repo)

        assert task.cleanup_interval.total_seconds() == 24 * 3600
        assert task.retention_days == 30

    @pytest.mark.asyncio()
    async def test_cleanup_task_start_stop(self, mock_mongo):
        """Testa iniciar e parar cleanup task."""
        from src.repositories.mcp_execution_repository import MCPCleanupTask, MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)
        task = MCPCleanupTask(repo, cleanup_interval_hours=1)

        # Start
        await task.start()
        assert task._running is True
        assert task._task is not None

        # Stop
        await task.stop()
        assert task._running is False

    @pytest.mark.asyncio()
    async def test_cleanup_task_run_once(self, mock_mongo):
        """Testa execução única de limpeza."""
        from src.repositories.mcp_execution_repository import MCPCleanupTask, MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)
        # Mock delete_many como async
        repo.collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=5))
        task = MCPCleanupTask(repo, retention_days=7)

        # Executar uma vez
        deleted = await task.run_once()

        # Verificar que delete_old_executions foi chamado
        assert deleted == 5

    @pytest.mark.asyncio()
    async def test_cleanup_task_idempotent_start(self, mock_mongo):
        """Testa que start múltiplas vezes não cria tasks duplicadas."""
        from src.repositories.mcp_execution_repository import MCPCleanupTask, MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)
        task = MCPCleanupTask(repo, cleanup_interval_hours=1)

        await task.start()
        first_task = task._task

        await task.start()  # Segunda chamada deve ser ignorada
        assert task._task == first_task

        await task.stop()


class TestMCPRepositoryCleanupIntegration:
    """Testes de integração para cleanup no repositório."""

    @pytest.mark.asyncio()
    async def test_repository_start_cleanup_task(self, mock_mongo):
        """Testa iniciar cleanup task através do repositório."""
        from src.repositories.mcp_execution_repository import MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)

        await repo.start_cleanup_task(cleanup_interval_hours=1, retention_days=7)

        assert repo._cleanup_task is not None
        assert repo._cleanup_task._running is True

        await repo.stop_cleanup_task()

    @pytest.mark.asyncio()
    async def test_repository_stop_cleanup_task(self, mock_mongo):
        """Testa parar cleanup task através do repositório."""
        from src.repositories.mcp_execution_repository import MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)

        await repo.start_cleanup_task(cleanup_interval_hours=1)
        await repo.stop_cleanup_task()

        assert repo._cleanup_task._running is False

    @pytest.mark.asyncio()
    async def test_repository_cleanup_task_reuse(self, mock_mongo):
        """Testa que task é reutilizado em chamadas múltiplas."""
        from src.repositories.mcp_execution_repository import MCPExecutionRepository

        repo = MCPExecutionRepository(mock_mongo)

        await repo.start_cleanup_task(cleanup_interval_hours=1)
        first_task = repo._cleanup_task

        await repo.start_cleanup_task(cleanup_interval_hours=1)
        assert repo._cleanup_task == first_task

        await repo.stop_cleanup_task()
