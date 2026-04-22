"""
Testes para MCPIntegration.
Usa mocks para evitar dependências externas (HTTP servers).
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock httpx antes de importar
mock_httpx = MagicMock()
mock_httpx.AsyncClient = MagicMock
mock_httpx.HTTPError = Exception
mock_httpx.TimeoutException = Exception
sys.modules["httpx"] = mock_httpx

from src.services.mcp_integration import (
    MCPIntegration,
    MCPIntegrationError,
)


def create_mock_response(status_code=200, json_data=None):
    """Criar mock response com json() síncrono."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data or {}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.fixture()
async def mcp_client():
    """Cliente MCP com mocks HTTP."""
    client = MCPIntegration(
        scout_url="http://scout-test:8000",
        optimizer_url="http://optimizer-test:8001",
        timeout=5.0,
    )

    # Mock do cliente HTTP
    mock_http_client = AsyncMock()
    mock_http_client.aclose = AsyncMock()

    # Configurar get para health check
    async def mock_get(url, **kwargs):
        mock_r = MagicMock()
        mock_r.status_code = 200
        return mock_r

    mock_http_client.get = mock_get
    client._client = mock_http_client

    return client


# ============================================================================
# Testes de Inicialização
# ============================================================================


@pytest.mark.asyncio()
async def test_initialize():
    """Testar inicialização do cliente."""
    integration = MCPIntegration(timeout=5.0)

    with patch("src.services.mcp_integration.httpx.AsyncClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.aclose = AsyncMock()
        mock_client_class.return_value = mock_instance

        await integration.initialize()

        assert integration._client is not None
        assert integration.timeout == 5.0

        await integration.close()


@pytest.mark.asyncio()
async def test_close():
    """Testar fechamento do cliente."""
    integration = MCPIntegration()

    mock_http_client = AsyncMock()
    mock_http_client.aclose = AsyncMock()
    integration._client = mock_http_client

    await integration.close()

    mock_http_client.aclose.assert_called_once()
    assert integration._client is None


# ============================================================================
# Testes Scout Tools
# ============================================================================


@pytest.mark.asyncio()
async def test_scout_list_files_success(mcp_client):
    """Testar list_files com sucesso."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200,
            json_data={"status": "success", "data": {"files": [{"path": "test.py", "size": 1024}]}},
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.scout_list_files(path="/test")

    assert len(result) == 1
    assert result[0]["path"] == "test.py"


@pytest.mark.asyncio()
async def test_scout_list_files_error():
    """Testar list_files com erro."""
    integration = MCPIntegration()

    mock_http_client = AsyncMock()
    mock_http_client.aclose = AsyncMock()

    async def failing_post(url, json=None, **kwargs):
        raise Exception("Connection refused")

    mock_http_client.post = failing_post
    integration._client = mock_http_client

    # tenacity RetryError包裹了MCPIntegrationError
    from tenacity import RetryError

    with pytest.raises((MCPIntegrationError, RetryError)):
        await integration.scout_list_files()


@pytest.mark.asyncio()
async def test_scout_search_code_success(mcp_client):
    """Testar search_code com sucesso."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200,
            json_data={
                "status": "success",
                "data": {"matches": [{"file": "test.py", "line": 10, "code": "def test()"}]},
            },
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.scout_search_code(query="def test")

    assert len(result) >= 1
    assert result[0]["file"] == "test.py"


@pytest.mark.asyncio()
async def test_scout_analyze_structure_success(mcp_client):
    """Testar analyze_structure com sucesso."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200,
            json_data={
                "status": "success",
                "data": {"structure": {"modules": ["module1", "module2"]}},
            },
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.scout_analyze_structure(path="/test")

    assert "structure" in result
    assert result["structure"]["modules"] == ["module1", "module2"]


# ============================================================================
# Testes Optimizer Tools
# ============================================================================


@pytest.mark.asyncio()
async def test_optimizer_analyze_performance_success(mcp_client):
    """Testar analyze_performance com sucesso."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200,
            json_data={
                "status": "success",
                "data": {"complexity": "O(n)", "suggestions": ["Use list comprehension"]},
            },
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.optimizer_analyze_performance(code="def test(): pass")

    assert "complexity" in result
    assert result["complexity"] == "O(n)"


@pytest.mark.asyncio()
async def test_optimizer_suggest_refactors_success(mcp_client):
    """Testar suggest_refactors com sucesso."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200,
            json_data={
                "status": "success",
                "data": {"suggestions": [{"type": "simplify", "description": "Use built-in"}]},
            },
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.optimizer_suggest_refactors(code="x = x + 1")

    assert len(result) >= 1
    assert result[0]["type"] == "simplify"


@pytest.mark.asyncio()
async def test_optimizer_optimize_queries_success(mcp_client):
    """Testar optimize_queries com sucesso."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200,
            json_data={
                "status": "success",
                "data": {"optimized": [{"query": "SELECT * FROM t", "improvement": "Add index"}]},
            },
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.optimizer_optimize_queries(queries=["SELECT * FROM t"])

    assert len(result) >= 1


# ============================================================================
# Testes de Análise Agregada
# ============================================================================


@pytest.mark.asyncio()
async def test_execute_aggregated_analysis_code_discovery(mcp_client):
    """Testar análise agregada de code discovery."""
    call_count = [0]

    async def mock_post(url, json=None, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return create_mock_response(
                status_code=200,
                json_data={"status": "success", "data": {"files": [{"path": "test.py"}]}},
            )
        else:
            return create_mock_response(
                status_code=200,
                json_data={"status": "success", "data": {"structure": {"dirs": ["src"]}}},
            )

    mcp_client._client.post = mock_post

    result = await mcp_client.execute_aggregated_analysis(
        analysis_type="code_discovery",
        params={"path": "/test"},
    )

    assert result["analysis_type"] == "code_discovery"
    assert "scout_list_files" in result["tools_used"]
    assert "scout_analyze_structure" in result["tools_used"]
    assert "data" in result


@pytest.mark.asyncio()
async def test_execute_aggregated_analysis_performance_optimization(mcp_client):
    """Testar análise agregada de performance optimization."""
    call_count = [0]

    async def mock_post(url, json=None, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return create_mock_response(
                status_code=200, json_data={"status": "success", "data": {"complexity": "O(n)"}}
            )
        else:
            return create_mock_response(
                status_code=200,
                json_data={"status": "success", "data": {"suggestions": [{"type": "optimize"}]}},
            )

    mcp_client._client.post = mock_post

    result = await mcp_client.execute_aggregated_analysis(
        analysis_type="performance_optimization",
        params={"code": "def test(): pass"},
    )

    assert result["analysis_type"] == "performance_optimization"
    assert "optimizer_analyze_performance" in result["tools_used"]
    assert "data" in result


@pytest.mark.asyncio()
async def test_execute_aggregated_analysis_with_errors(mcp_client):
    """Testar análise agregada com erros parciais."""
    call_count = [0]

    async def mock_post(url, json=None, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Primeira call retorna status error
            return create_mock_response(
                status_code=200, json_data={"status": "error", "error": "timeout"}
            )
        else:
            # Segunda succeeds
            return create_mock_response(
                status_code=200, json_data={"status": "success", "data": {"structure": {}}}
            )

    mcp_client._client.post = mock_post

    result = await mcp_client.execute_aggregated_analysis(
        analysis_type="code_discovery", params={"path": "."}
    )

    # Deve ter errors mas continuar com outros tools
    assert len(result["errors"]) > 0
    assert "scout_analyze_structure" in result["tools_used"]


@pytest.mark.asyncio()
async def test_execute_aggregated_analysis_unknown_type(mcp_client):
    """Testar análise agregada com tipo desconhecido."""
    result = await mcp_client.execute_aggregated_analysis(analysis_type="unknown_type", params={})

    assert result["analysis_type"] == "unknown_type"
    assert len(result["tools_used"]) == 0


# ============================================================================
# Testes de Health Check
# ============================================================================


@pytest.mark.asyncio()
async def test_health_check_all_up(mcp_client):
    """Testar health check com todos servidores ativos."""

    async def mock_get(url, **kwargs):
        mock_r = MagicMock()
        mock_r.status_code = 200
        return mock_r

    mcp_client._client.get = mock_get

    health = await mcp_client.health_check()

    assert health["scout"] is True
    assert health["optimizer"] is True


@pytest.mark.asyncio()
async def test_health_check_all_down(mcp_client):
    """Testar health check com servidores inativos."""

    async def mock_get(url, **kwargs):
        raise Exception("Connection refused")

    mcp_client._client.get = mock_get

    health = await mcp_client.health_check()

    assert health["scout"] is False
    assert health["optimizer"] is False


@pytest.mark.asyncio()
async def test_health_check_client_not_initialized():
    """Testar health check com cliente não inicializado."""
    client = MCPIntegration()

    health = await client.health_check()

    assert health["scout"] is False
    assert health["optimizer"] is False


# ============================================================================
# Testes de Retry
# ============================================================================


@pytest.mark.asyncio()
async def test_retry_on_failure():
    """Testar retry em falha."""
    integration = MCPIntegration(max_retries=3)
    integration._client = AsyncMock()

    # Usar dict mutável em vez de list para evitar problemas de scoping
    state = {"count": 0}

    async def failing_post(*args, **kwargs):
        state["count"] += 1
        if state["count"] < 2:
            raise Exception("Temporary error")
        return create_mock_response(status_code=200, json_data={"status": "success", "data": {}})

    integration._client.post = failing_post

    result = await integration.scout_list_files()

    assert state["count"] == 2  # Falhou 1 vez, sucedeu na 2ª
    assert result is not None


# ============================================================================
# Testes Adicionais
# ============================================================================


@pytest.mark.asyncio()
async def test_scout_list_files_with_pattern(mcp_client):
    """Testar scout_list_files com pattern."""

    async def mock_post(url, json=None, **kwargs):
        # Verificar payload
        assert json.get("pattern") == "*.py"
        return create_mock_response(
            status_code=200,
            json_data={"status": "success", "data": {"files": [{"path": "main.py"}]}},
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.scout_list_files(path="src", pattern="*.py")

    assert len(result) == 1


@pytest.mark.asyncio()
async def test_scout_search_code_with_file_pattern(mcp_client):
    """Testar scout_search_code com file_pattern."""

    async def mock_post(url, json=None, **kwargs):
        # Verificar payload
        assert json.get("file_pattern") == "test_*.py"
        return create_mock_response(
            status_code=200, json_data={"status": "success", "data": {"matches": []}}
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.scout_search_code(query="test", file_pattern="test_*.py")

    assert result == []


@pytest.mark.asyncio()
async def test_performance_optimization_without_code(mcp_client):
    """Testar performance_optimization sem código fornecido."""
    result = await mcp_client.execute_aggregated_analysis(
        analysis_type="performance_optimization", params={}  # sem "code"
    )

    # Não deve usar nenhuma tool (não há código para analisar)
    assert len(result["tools_used"]) == 0


@pytest.mark.asyncio()
async def test_scout_list_files_error_response(mcp_client):
    """Testar scout_list_files com response de erro."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200, json_data={"status": "error", "error": "invalid path"}
        )

    mcp_client._client.post = mock_post

    with pytest.raises(MCPIntegrationError, match="Scout list_files failed"):
        await mcp_client.scout_list_files(path="/invalid")


@pytest.mark.asyncio()
async def test_optimizer_suggest_refactors_empty(mcp_client):
    """Testar suggest_refactors sem sugestões."""

    async def mock_post(url, json=None, **kwargs):
        return create_mock_response(
            status_code=200, json_data={"status": "success", "data": {"suggestions": []}}
        )

    mcp_client._client.post = mock_post

    result = await mcp_client.optimizer_suggest_refactors(code="perfect code")

    assert result == []
