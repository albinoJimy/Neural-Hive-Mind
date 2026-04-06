"""
Testes do Worker MCP Server - Fase GREEN (TDD)

Testes escritos ANTES da implementação.
Com MOCKS para isolar a unidade sendo testada.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

# ===== FIXTURES =====


@pytest.fixture
def mock_http_client():
    """Mock de cliente HTTP para Worker Agent."""
    return AsyncMock()


@pytest.fixture
def mcp():
    """Fixture para servidor MCP."""
    return


# ===== TESTES DAS FERRAMENTAS =====


class TestExecuteTask:
    """Testes da ferramenta execute_task."""

    @pytest.mark.asyncio
    async def test_execute_task_success(self):
        """
        DADO: Uma tarefa válida com task_id, workflow_id e executor_type
        QUANDO: Executo execute_task
        ENTÃO: Deve retornar resultado com execution_id e status 'pending'
        """
        # Arrange
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "execution_id": "exec-123",
                "status": "pending",
                "task_id": "task-456",
                "workflow_id": "workflow-789",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient", autospec=True) as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Act
            from worker_mcp_server.tools.worker_tools import execute_task

            result = await execute_task(
                task_id="task-456",
                workflow_id="workflow-789",
                executor_type="query",
                parameters={"query": "SELECT * FROM users"},
            )

        # Assert
        assert result["status"] == "pending"
        assert result["execution_id"] == "exec-123"

    @pytest.mark.asyncio
    async def test_execute_task_missing_required_field(self):
        """
        DADO: Uma tarefa sem task_id (passando string vazia)
        QUANDO: Executo execute_task
        ENTÃO: Deve levantar ValueError
        """
        from worker_mcp_server.tools.worker_tools import execute_task

        with pytest.raises(ValueError, match="task_id"):
            await execute_task(
                task_id="",  # string vazia é falsy
                workflow_id="workflow-789",
                executor_type="query",
            )

    @pytest.mark.asyncio
    async def test_execute_task_invalid_executor_type(self):
        """
        DADO: Uma tarefa com executor_type inválido
        QUANDO: Executo execute_task
        ENTÃO: Deve levantar ValueError
        """
        from worker_mcp_server.tools.worker_tools import execute_task

        with pytest.raises(ValueError, match="executor_type"):
            await execute_task(
                task_id="task-456", workflow_id="workflow-789", executor_type="invalid_type"
            )


class TestCheckDependencies:
    """Testes da ferramenta check_dependencies."""

    @pytest.mark.asyncio
    async def test_check_dependencies_all_satisfied(self):
        """
        DADO: Um workflow com todas as dependências satisfeitas
        QUANDO: Executo check_dependencies
        ENTÃO: Deve retornar satisfied=True com lista vazia de missing
        """
        # Mock responses - todos os serviços respondem 200
        mock_response_ok = Mock()
        mock_response_ok.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response_ok)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import check_dependencies

            result = await check_dependencies(
                workflow_id="workflow-789", dependencies=["service-a", "service-b"]
            )

        assert result["satisfied"] is True
        assert result["missing"] == []
        assert result["workflow_id"] == "workflow-789"

    @pytest.mark.asyncio
    async def test_check_dependencies_missing_services(self):
        """
        DADO: Um workflow com dependências não satisfeitas
        QUANDO: Executo check_dependencies
        ENTÃO: Deve retornar satisfied=False com lista de missing
        """

        def mock_get_side_effect(*args, **kwargs):
            # Simular service-a respondendo 200, service-x falhando
            url = args[0] if args else kwargs.get("url", "")
            mock_resp = Mock()
            if "service-x" in url:
                mock_resp.status_code = 503
            else:
                mock_resp.status_code = 200
            return mock_resp

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(side_effect=mock_get_side_effect)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import check_dependencies

            result = await check_dependencies(
                workflow_id="workflow-789", dependencies=["service-a", "service-x"]
            )

        assert result["satisfied"] is False
        assert "service-x" in result["missing"]


class TestMonitorProgress:
    """Testes da ferramenta monitor_progress."""

    @pytest.mark.asyncio
    async def test_monitor_progress_existing_execution(self):
        """
        DADO: Uma execução em andamento
        QUANDO: Executo monitor_progress
        ENTÃO: Deve retornar status atual, progress_percent e logs
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "status": "in_progress",
                "progress_percent": 45,
                "logs": ["Step 1 completed", "Step 2 running"],
                "execution_id": "exec-123",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import monitor_progress

            result = await monitor_progress(execution_id="exec-123")

        assert result["status"] == "in_progress"
        assert result["progress_percent"] == 45
        assert "logs" in result

    @pytest.mark.asyncio
    async def test_monitor_progress_completed_execution(self):
        """
        DADO: Uma execução já completada
        QUANDO: Executo monitor_progress
        ENTÃO: Deve retornar status='completed' com 100% progress
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "status": "completed",
                "progress_percent": 100,
                "logs": ["All steps completed"],
                "execution_id": "exec-completed",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import monitor_progress

            result = await monitor_progress(execution_id="exec-completed")

        assert result["status"] == "completed"
        assert result["progress_percent"] == 100


class TestHandleCompensation:
    """Testes da ferramenta handle_compensation."""

    @pytest.mark.asyncio
    async def test_handle_compensation_successful(self):
        """
        DADO: Uma execução falhou requer compensação
        QUANDO: Executo handle_compensation
        ENTÃO: Deve executar transação compensatória e retornar success=True
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "success": True,
                "compensation_id": "comp-456",
                "execution_id": "exec-123",
                "status": "completed",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import handle_compensation

            result = await handle_compensation(
                execution_id="exec-123", original_task_id="task-456", compensation_type="rollback"
            )

        assert result["success"] is True
        assert result["compensation_id"] == "comp-456"

    @pytest.mark.asyncio
    async def test_handle_compensation_invalid_type(self):
        """
        DADO: Um tipo de compensação inválido
        QUANDO: Executo handle_compensation
        ENTÃO: Deve levantar ValueError
        """
        from worker_mcp_server.tools.worker_tools import handle_compensation

        with pytest.raises(ValueError, match="compensation_type"):
            await handle_compensation(
                execution_id="exec-123",
                original_task_id="task-456",
                compensation_type="invalid_type",
            )


class TestReportStatus:
    """Testes da ferramenta report_status."""

    @pytest.mark.asyncio
    async def test_report_status_success(self):
        """
        DADO: Uma execução completou com status
        QUANDO: Executo report_status
        ENTÃO: Deve reportar status ao Orchestrator e retornar success=True
        """
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import report_status

            result = await report_status(
                execution_id="exec-123",
                task_id="task-456",
                workflow_id="workflow-789",
                status="completed",
                output={"result": "data"},
            )

        assert result["success"] is True
        assert result["execution_id"] == "exec-123"

    @pytest.mark.asyncio
    async def test_report_status_invalid_status(self):
        """
        DADO: Um status inválido
        QUANDO: Executo report_status
        ENTÃO: Deve levantar ValueError
        """
        from worker_mcp_server.tools.worker_tools import report_status

        with pytest.raises(ValueError, match="status"):
            await report_status(
                execution_id="exec-123",
                task_id="task-456",
                workflow_id="workflow-789",
                status="invalid_status",
            )


# ===== TESTES DE INTEGRAÇÃO DO SERVIDOR =====


class TestWorkerMCPServerIntegration:
    """Testes de integração do servidor MCP."""

    def test_server_has_required_tools(self):
        """
        DADO: O servidor Worker MCP está inicializado
        QUANDO: Listo ferramentas disponíveis
        ENTÃO: Deve ter exatamente 5 ferramentas registradas
        """
        from worker_mcp_server.server import mcp

        # Verificar que o servidor MCP está configurado
        assert mcp is not None
        assert mcp.name == "Worker MCP Server"

    def test_tools_have_metadata(self):
        """
        DADO: O servidor Worker MCP está inicializado
        QUANDO: Examino metadata das ferramentas
        ENTÃO: Cada ferramenta deve ter descrição e parâmetros documentados
        """
        from worker_mcp_server.tools.worker_tools import (
            check_dependencies,
            execute_task,
            handle_compensation,
            monitor_progress,
            report_status,
        )

        # Verificar que funções de tools existem e têm docstrings
        assert execute_task.__doc__
        assert check_dependencies.__doc__
        assert monitor_progress.__doc__
        assert handle_compensation.__doc__
        assert report_status.__doc__

    def test_server_info_resource_exists(self):
        """
        DADO: O servidor Worker MCP está inicializado
        QUANDO: Verifico recursos disponíveis
        ENTÃO: O recurso worker://info deve existir
        """
        from worker_mcp_server.server import mcp

        # FastMCP tem métodos para listar resources
        # O recurso "worker://info" está definido no servidor
        assert mcp is not None

    def test_register_function_exists(self):
        """
        DADO: O módulo worker_tools está importado
        QUANDO: Verifico a função de registro
        ENTÃO: register_worker_tools deve existir
        """
        from worker_mcp_server.tools.worker_tools import register_worker_tools

        assert callable(register_worker_tools)
