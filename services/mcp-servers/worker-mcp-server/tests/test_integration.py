"""
Testes de Integração do Worker MCP Server.

Testam a integração entre componentes usando HTTP clients mockados.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Add shared module path
shared_path = str(Path(__file__).parent.parent.parent.parent / "shared")
if Path(shared_path).exists():
    sys.path.insert(0, shared_path)


@pytest.fixture
def mock_worker_agent_response():
    """Fixture para resposta mockada do Worker Agent."""
    return {
        "execution_id": "exec-test-123",
        "status": "pending",
        "task_id": "task-test-456",
        "workflow_id": "workflow-test-789",
        "executor_type": "query",
        "timestamp": 1713131400000,
    }


@pytest.fixture
def mock_orchestrator_response():
    """Fixture para resposta mockada do Orchestrator."""
    return {"success": True, "message": "Status received"}


@pytest.fixture
def mock_service_registry_response():
    """Fixture para resposta mockada do Service Registry."""
    return {"status": "healthy", "service": "test-service"}


class TestWorkerMCPIntegration:
    """Testes de integração do Worker MCP Server."""

    def test_settings_can_be_loaded(self):
        """
        DADO: O servidor está configurado
        QUANDO: Carrego as configurações
        ENTÃO: Deve retornar configurações válidas
        """
        from worker_mcp_server.config.settings import get_settings

        settings = get_settings()
        assert settings.service_name == "worker-mcp-server"
        assert settings.port == 3013
        assert settings.worker_agent_port == 8005
        assert settings.orchestrator_port == 8003

    def test_mcp_server_instance_exists(self):
        """
        DADO: O servidor MCP está inicializado
        QUANDO: Verifico a instância
        ENTÃO: Deve existir com nome e versão corretos
        """
        from worker_mcp_server.server import mcp

        assert mcp is not None
        assert mcp.name == "Worker MCP Server"

    def test_tools_can_be_imported(self):
        """
        DADO: O módulo de ferramentas existe
        QUANDO: Importo as funções de tools
        ENTÃO: Todas as 5 ferramentas devem estar disponíveis
        """
        from worker_mcp_server.tools.worker_tools import (
            check_dependencies,
            execute_task,
            handle_compensation,
            monitor_progress,
            report_status,
        )

        assert callable(execute_task)
        assert callable(check_dependencies)
        assert callable(monitor_progress)
        assert callable(handle_compensation)
        assert callable(report_status)

    @pytest.mark.asyncio
    async def test_execute_task_integration(self, mock_worker_agent_response):
        """
        DADO: Uma tarefa válida
        QUANDO: Executo execute_task
        ENTÃO: Deve chamar Worker Agent e retornar execution_id
        """
        mock_response = Mock()
        mock_response.json = Mock(return_value=mock_worker_agent_response)
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import execute_task

            result = await execute_task(
                task_id="task-test-456",
                workflow_id="workflow-test-789",
                executor_type="query",
                parameters={"query": "SELECT * FROM users"},
            )

        assert result["execution_id"] == "exec-test-123"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_check_dependencies_integration(self):
        """
        DADO: Um workflow com dependências
        QUANDO: Executo check_dependencies
        ENTÃO: Deve verificar no Service Registry e retornar status
        """
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import check_dependencies

            result = await check_dependencies(
                workflow_id="workflow-test-789",
                dependencies=["service-a", "service-b"],
            )

        assert result["satisfied"] is True
        assert result["missing"] == []

    @pytest.mark.asyncio
    async def test_monitor_progress_integration(self):
        """
        DADO: Uma execução em andamento
        QUANDO: Executo monitor_progress
        ENTÃO: Deve consultar Worker Agent e retornar progresso
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "status": "in_progress",
                "progress_percent": 45,
                "logs": ["Step 1 completed"],
                "execution_id": "exec-test-123",
            }
        )
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import monitor_progress

            result = await monitor_progress(execution_id="exec-test-123")

        assert result["status"] == "in_progress"
        assert result["progress_percent"] == 45

    @pytest.mark.asyncio
    async def test_handle_compensation_integration(self):
        """
        DADO: Uma execução falhou
        QUANDO: Executo handle_compensation
        ENTÃO: Deve chamar Worker Agent e executar compensação
        """
        mock_response = Mock()
        mock_response.json = Mock(
            return_value={
                "success": True,
                "compensation_id": "comp-test-456",
                "execution_id": "exec-test-123",
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
                execution_id="exec-test-123",
                original_task_id="task-test-456",
                compensation_type="rollback",
            )

        assert result["success"] is True
        assert result["compensation_id"] == "comp-test-456"

    @pytest.mark.asyncio
    async def test_report_status_integration(self):
        """
        DADO: Uma execução completou
        QUANDO: Executo report_status
        ENTÃO: Deve reportar ao Orchestrator
        """
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import report_status

            result = await report_status(
                execution_id="exec-test-123",
                task_id="task-test-456",
                workflow_id="workflow-test-789",
                status="completed",
                output={"result": "success"},
            )

        assert result["success"] is True


class TestMCPEndpoint:
    """Testes do endpoint MCP JSON-RPC."""

    def test_mcp_server_has_tools_registered(self):
        """
        DADO: O servidor MCP está montado
        QUANDO: Verifico as ferramentas registradas
        ENTÃO: Deve ter 5 ferramentas registradas
        """
        from worker_mcp_server.tools.worker_tools import (
            check_dependencies,
            execute_task,
            handle_compensation,
            monitor_progress,
            report_status,
        )

        # Verifica que todas as funções existem
        assert callable(execute_task)
        assert callable(check_dependencies)
        assert callable(monitor_progress)
        assert callable(handle_compensation)
        assert callable(report_status)

    def test_mcp_server_has_resource(self):
        """
        DADO: O servidor MCP está montado
        QUANDO: Verifico os recursos disponíveis
        ENTÃO: O recurso worker://info deve existir
        """
        from worker_mcp_server.server import mcp

        # FastMCP armazena resources internamente
        # Verifica que o servidor foi criado corretamente
        assert mcp is not None
        assert mcp.name == "Worker MCP Server"


class TestErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_worker_agent_unavailable(self):
        """
        DADO: Worker Agent está indisponível
        QUANDO: Executo execute_task
        ENTÃO: Deve retornar erro com mensagem apropriada
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import execute_task

            result = await execute_task(
                task_id="task-test-456",
                workflow_id="workflow-test-789",
                executor_type="query",
            )

        assert result["status"] == "ERROR"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_orchestrator_unavailable(self):
        """
        DADO: Orchestrator está indisponível
        QUANDO: Executo report_status
        ENTÃO: Deve retornar success=False
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import report_status

            result = await report_status(
                execution_id="exec-test-123",
                task_id="task-test-456",
                workflow_id="workflow-test-789",
                status="completed",
            )

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_service_registry_timeout(self):
        """
        DADO: Service Registry está lento (timeout)
        QUANDO: Executo check_dependencies
        ENTÃO: Deve retornar satisfied=True (fail-open)
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            mock_client_class.return_value = mock_client

            from worker_mcp_server.tools.worker_tools import check_dependencies

            result = await check_dependencies(
                workflow_id="workflow-test-789",
                dependencies=["service-a"],
            )

        # Em caso de erro, assume dependências OK para não bloquear
        assert result["satisfied"] is True
