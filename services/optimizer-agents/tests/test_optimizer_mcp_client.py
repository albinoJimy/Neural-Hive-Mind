"""Testes para OptimizerMCPClient - Integração HTTP com MCP Server."""

from unittest.mock import AsyncMock, patch

import pytest

from src.clients.optimizer_mcp_client import (
    DirectoryAnalysisResult,
    FileAnalysisResult,
    FileMetrics,
    OptimizerMCPClient,
    RecommendationsResult,
    SyncOptimizerMCPClient,
)


class MockHTTPResponse:
    """Mock de resposta HTTP com método json assíncrono."""

    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code

    async def json(self):
        return self._data

    def raise_for_status(self):
        pass


@pytest.fixture
def optimizer_client():
    """Fixture para OptimizerMCPClient."""
    client = OptimizerMCPClient(base_url="http://test:8080")

    # Mock do httpx client
    mock_http_client = AsyncMock()

    # Health check response (padrão)
    health_data = {
        "status": "healthy",
        "server": "Optimizer MCP HTTP Server",
        "version": "1.0.0",
    }
    mock_http_client.get.return_value = MockHTTPResponse(health_data)
    mock_http_client.post.return_value = MockHTTPResponse({})
    mock_http_client.aclose = AsyncMock()

    client._client = mock_http_client
    return client, mock_http_client


class TestOptimizerMCPClientInit:
    """Testes de inicialização."""

    def test_init_with_defaults(self):
        """Testa inicialização com valores padrão."""
        client = OptimizerMCPClient()
        assert (
            client.base_url == "http://optimizer-mcp-server.neural-hive-mind.svc.cluster.local:8080"
        )
        assert client.timeout == 30.0
        assert client._client is None

    def test_init_with_custom_url(self):
        """Testa inicialização com URL customizada."""
        client = OptimizerMCPClient(base_url="http://localhost:3000")
        assert client.base_url == "http://localhost:3000"

    def test_init_with_custom_timeout(self):
        """Testa inicialização com timeout customizado."""
        client = OptimizerMCPClient(timeout=60.0)
        assert client.timeout == 60.0


class TestHealthCheck:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, optimizer_client):
        """Testa health check com sucesso."""
        client, _ = optimizer_client
        result = await client.health_check()

        assert result["status"] == "healthy"
        assert result["server"] == "Optimizer MCP HTTP Server"
        assert result["version"] == "1.0.0"


class TestAnalyzeFile:
    """Testes de analyze_file."""

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, optimizer_client):
        """Testa análise de arquivo com sucesso."""
        client, mock_http = optimizer_client

        data = {
            "file_path": "src/test.py",
            "metrics": {
                "total_lines": 100,
                "code_lines": 80,
                "comment_lines": 10,
                "blank_lines": 10,
                "functions": 5,
                "classes": 2,
                "avg_function_length": 15.0,
                "max_function_length": 30,
                "max_complexity": 8,
            },
            "issues": [
                {
                    "file": "src/test.py",
                    "line": 10,
                    "column": 4,
                    "severity": "medium",
                    "category": "complexity",
                    "message": "Function is complex",
                    "suggestion": "Simplify logic",
                }
            ],
            "issue_count": 1,
            "summary": {"complexity": "low", "maintainability": "good"},
        }
        mock_http.get.return_value = MockHTTPResponse(data)

        result = await client.analyze_file("src/test.py")

        assert isinstance(result, FileAnalysisResult)
        assert result.file_path == "src/test.py"
        assert result.metrics.total_lines == 100
        assert result.metrics.functions == 5
        assert result.issue_count == 1
        assert len(result.issues) == 1
        assert result.issues[0].category == "complexity"


class TestAnalyzeDirectory:
    """Testes de analyze_directory."""

    @pytest.mark.asyncio
    async def test_analyze_directory_success(self, optimizer_client):
        """Testa análise de diretório com sucesso."""
        client, mock_http = optimizer_client

        data = {
            "summary": {
                "total_files": 10,
                "total_lines": 1000,
                "total_functions": 50,
                "total_issues": 5,
                "avg_issues_per_file": 0.5,
            },
            "severity_breakdown": {"low": 3, "medium": 2},
            "category_breakdown": {"complexity": 2, "style": 3},
            "top_files": [{"path": "src/complex.py", "issue_count": 3}],
            "issues": [
                {
                    "file": "src/test.py",
                    "line": 10,
                    "column": 4,
                    "severity": "medium",
                    "category": "complexity",
                    "message": "Function is complex",
                }
            ],
        }
        mock_http.get.return_value = MockHTTPResponse(data)

        result = await client.analyze_directory("src")

        assert isinstance(result, DirectoryAnalysisResult)
        assert result.summary["total_files"] == 10
        assert result.severity_breakdown["low"] == 3
        assert len(result.issues) == 1


class TestGetRecommendations:
    """Testes de get_recommendations."""

    @pytest.mark.asyncio
    async def test_get_recommendations_success(self, optimizer_client):
        """Testa obtenção de recomendações com sucesso."""
        client, mock_http = optimizer_client

        data = {
            "path": ".",
            "recommendations": [
                {
                    "priority": "high",
                    "category": "complexity",
                    "title": "Reduce Complexity",
                    "description": "High complexity found",
                    "actions": ["Extract methods", "Simplify logic"],
                }
            ],
            "total_recommendations": 1,
            "summary": {"high_priority": 1, "medium_priority": 0, "low_priority": 0},
        }
        mock_http.get.return_value = MockHTTPResponse(data)

        result = await client.get_recommendations()

        assert isinstance(result, RecommendationsResult)
        assert result.total_recommendations == 1
        assert len(result.recommendations) == 1
        assert result.recommendations[0].priority == "high"
        assert result.recommendations[0].category == "complexity"


class TestDetectCodeSmells:
    """Testes de detect_code_smells."""

    @pytest.mark.asyncio
    async def test_detect_code_smells_success(self, optimizer_client):
        """Testa detecção de code smells com sucesso."""
        client, mock_http = optimizer_client

        data = {
            "path": ".",
            "severity_filter": "medium",
            "total_smells": 2,
            "by_category": {
                "complexity": {"count": 1, "sample": []},
                "style": {"count": 1, "sample": []},
            },
            "all_smells": [],
        }
        mock_http.get.return_value = MockHTTPResponse(data)

        result = await client.detect_code_smells(severity="medium")

        assert result["total_smells"] == 2
        assert "complexity" in result["by_category"]


class TestExecuteTool:
    """Testes de execute_tool."""

    @pytest.mark.asyncio
    async def test_execute_tool_analyze_file(self, optimizer_client):
        """Testa execução de ferramenta analyze_file_performance."""
        client, mock_http = optimizer_client

        data = {
            "file_path": "src/test.py",
            "metrics": {
                "total_lines": 100,
                "code_lines": 80,
                "comment_lines": 10,
                "blank_lines": 10,
                "functions": 5,
                "classes": 2,
                "avg_function_length": 15.0,
                "max_function_length": 30,
                "max_complexity": 8,
            },
            "issues": [],
            "issue_count": 0,
        }
        mock_http.post.return_value = MockHTTPResponse(data)

        result = await client.execute_tool(
            "analyze_file_performance",
            {"file_path": "src/test.py"},
        )

        assert result["file_path"] == "src/test.py"
        assert result["metrics"]["total_lines"] == 100


class TestGetAvailableTools:
    """Testes de get_available_tools."""

    @pytest.mark.asyncio
    async def test_get_available_tools(self, optimizer_client):
        """Testa listagem de ferramentas."""
        client, mock_http = optimizer_client

        data = {
            "tools": [
                {"name": "analyze_file_performance", "description": "Analyze single file"},
                {"name": "analyze_directory_performance", "description": "Analyze directory"},
            ]
        }
        mock_http.get.return_value = MockHTTPResponse(data)

        result = await client.get_available_tools()

        assert len(result) == 2
        assert result[0]["name"] == "analyze_file_performance"


class TestSyncOptimizerMCPClient:
    """Testes para wrapper síncrono."""

    def test_sync_health_check(self):
        """Testa health check síncrono."""
        client = SyncOptimizerMCPClient(base_url="http://test:8080")

        with patch.object(
            client._async_client, "health_check", new_callable=AsyncMock
        ) as mock_health:
            mock_health.return_value = {"status": "healthy"}

            result = client.health_check()
            assert result["status"] == "healthy"

    def test_sync_analyze_file(self):
        """Testa analyze_file síncrono."""
        client = SyncOptimizerMCPClient(base_url="http://test:8080")

        with patch.object(
            client._async_client, "analyze_file", new_callable=AsyncMock
        ) as mock_analyze:
            mock_result = FileAnalysisResult(
                file_path="test.py",
                metrics=FileMetrics(),
                issues=[],
                issue_count=0,
                summary={},
            )
            mock_analyze.return_value = mock_result

            result = client.analyze_file("test.py")
            assert result.file_path == "test.py"


class TestClose:
    """Testes de close."""

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Testa fechamento do cliente."""
        client = OptimizerMCPClient()

        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock()

        client._client = mock_client

        await client.close()

        mock_client.aclose.assert_called_once()
        assert client._client is None
