"""
Testes para MCPIntegration.
"""
import pytest
from unittest.mock import AsyncMock, patch
import httpx

from src.services.mcp_integration import MCPIntegration, MCPIntegrationError


@pytest.mark.asyncio
async def test_initialize():
    """Testar inicialização do cliente."""
    integration = MCPIntegration(timeout=5.0)
    await integration.initialize()

    assert integration._client is not None
    assert integration.timeout == 5.0

    await integration.close()


@pytest.mark.asyncio
async def test_close():
    """Testar fechamento do cliente."""
    integration = MCPIntegration()
    await integration.initialize()
    await integration.close()

    assert integration._client is None


@pytest.mark.asyncio
async def test_scout_list_files_success():
    """Testar list_files com sucesso."""
    integration = MCPIntegration()
    await integration.initialize()

    # Mock response
    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"files": [{"path": "test.py", "size": 1024}]}
        }
        mock_post.return_value = mock_response

        result = await integration.scout_list_files(path="/test")

        assert len(result) == 1
        assert result[0]["path"] == "test.py"

    await integration.close()


@pytest.mark.asyncio
async def test_scout_list_files_error():
    """Testar list_files com erro."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_post.side_effect = httpx.HTTPError("Connection refused")

        with pytest.raises(MCPIntegrationError):
            await integration.scout_list_files()

    await integration.close()


@pytest.mark.asyncio
async def test_scout_search_code_success():
    """Testar search_code com sucesso."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"matches": [{"file": "test.py", "line": 10, "code": "def test()"}]}
        }
        mock_post.return_value = mock_response

        result = await integration.scout_search_code(query="def test")

        assert len(result) >= 1
        assert result[0]["file"] == "test.py"

    await integration.close()


@pytest.mark.asyncio
async def test_scout_analyze_structure_success():
    """Testar analyze_structure com sucesso."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"structure": {"modules": ["module1", "module2"]}}
        }
        mock_post.return_value = mock_response

        result = await integration.scout_analyze_structure(path="/test")

        assert "structure" in result
        assert result["structure"]["modules"] == ["module1", "module2"]

    await integration.close()


@pytest.mark.asyncio
async def test_optimizer_analyze_performance_success():
    """Testar analyze_performance com sucesso."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"complexity": "O(n)", "suggestions": ["Use list comprehension"]}
        }
        mock_post.return_value = mock_response

        result = await integration.optimizer_analyze_performance(code="def test(): pass")

        assert "complexity" in result
        assert result["complexity"] == "O(n)"

    await integration.close()


@pytest.mark.asyncio
async def test_optimizer_suggest_refactors_success():
    """Testar suggest_refactors com sucesso."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"suggestions": [{"type": "simplify", "description": "Use built-in"}]}
        }
        mock_post.return_value = mock_response

        result = await integration.optimizer_suggest_refactors(code="x = x + 1")

        assert len(result) >= 1
        assert result[0]["type"] == "simplify"

    await integration.close()


@pytest.mark.asyncio
async def test_optimizer_optimize_queries_success():
    """Testar optimize_queries com sucesso."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"optimized": [{"query": "SELECT * FROM t", "improvement": "Add index"}]}
        }
        mock_post.return_value = mock_response

        result = await integration.optimizer_optimize_queries(queries=["SELECT * FROM t"])

        assert len(result) >= 1

    await integration.close()


@pytest.mark.asyncio
async def test_execute_aggregated_analysis_code_discovery():
    """Testar análise agregada de code discovery."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"files": [{"path": "test.py"}]}
        }
        mock_post.return_value = mock_response

        result = await integration.execute_aggregated_analysis(
            analysis_type="code_discovery",
            params={"path": "/test"},
        )

        assert result["analysis_type"] == "code_discovery"
        assert "scout_list_files" in result["tools_used"]
        assert "data" in result

    await integration.close()


@pytest.mark.asyncio
async def test_execute_aggregated_analysis_performance_optimization():
    """Testar análise agregada de performance optimization."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'post') as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"complexity": "O(n)"}
        }
        mock_post.return_value = mock_response

        result = await integration.execute_aggregated_analysis(
            analysis_type="performance_optimization",
            params={"code": "def test(): pass"},
        )

        assert result["analysis_type"] == "performance_optimization"
        assert "data" in result

    await integration.close()


@pytest.mark.asyncio
async def test_health_check_all_up():
    """Testar health check com todos servidores ativos."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        health = await integration.health_check()

        assert health["scout"] is True
        assert health["optimizer"] is True

    await integration.close()


@pytest.mark.asyncio
async def test_health_check_all_down():
    """Testar health check com servidores inativos."""
    integration = MCPIntegration()
    await integration.initialize()

    with patch.object(integration._client, 'get') as mock_get:
        mock_get.side_effect = httpx.HTTPError("Connection refused")

        health = await integration.health_check()

        assert health["scout"] is False
        assert health["optimizer"] is False

    await integration.close()


@pytest.mark.asyncio
async def test_retry_on_failure():
    """Testar retry em falha."""
    integration = MCPIntegration(max_retries=3)
    await integration.initialize()

    call_count = 0

    async def failing_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.HTTPError("Temporary error")
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "data": {}}
        return mock_response

    with patch.object(integration._client, 'post', failing_post):
        result = await integration.scout_list_files()

        assert call_count == 2  # Falhou 1 vez, sucedeu na 2ª
        assert result is not None

    await integration.close()
