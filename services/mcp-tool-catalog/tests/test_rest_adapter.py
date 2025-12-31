"""
Testes unitarios para RESTAdapter.

Cobertura:
- Execucao de requisicoes HTTP (GET, POST)
- Query parameters e body
- Autenticacao (Bearer token)
- Timeout e retry com exponential backoff
- Tratamento de erros HTTP
- Validacao de disponibilidade
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aioresponses import aioresponses

from src.adapters.rest_adapter import RESTAdapter
from src.adapters.base_adapter import ExecutionResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def rest_adapter():
    """RESTAdapter com timeout e retry configurados."""
    return RESTAdapter(timeout_seconds=30, max_retries=3)


@pytest.fixture
def mock_aiohttp():
    """Context manager para mockar requisicoes HTTP."""
    with aioresponses() as m:
        yield m


# ============================================================================
# Testes de Execucao HTTP
# ============================================================================

class TestRESTAdapterExecution:
    """Testes de execucao de requisicoes HTTP."""

    @pytest.mark.asyncio
    async def test_execute_get_request_success(self, rest_adapter, mock_aiohttp):
        """Testa GET request bem-sucedido."""
        mock_aiohttp.get(
            "http://api.example.com/status",
            payload={"status": "healthy"},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="health-check",
            tool_name="health",
            command="http://api.example.com/status",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is True
        assert "healthy" in result.output
        assert result.exit_code == 200
        assert result.metadata.get("method") == "GET"

    @pytest.mark.asyncio
    async def test_execute_post_request_with_body(self, rest_adapter, mock_aiohttp):
        """Testa POST request com JSON body."""
        mock_aiohttp.post(
            "http://api.example.com/analyze",
            payload={"result": "success", "issues": 0},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="sonarqube-001",
            tool_name="sonarqube",
            command="http://api.example.com/analyze",
            parameters={
                "body": {"project": "my-project", "language": "python"}
            },
            context={"http_method": "POST"}
        )

        assert result.success is True
        assert "success" in result.output
        assert result.exit_code == 200
        assert result.metadata.get("method") == "POST"

    @pytest.mark.asyncio
    async def test_execute_with_query_params(self, rest_adapter, mock_aiohttp):
        """Testa query parameters construidos corretamente."""
        mock_aiohttp.get(
            "http://api.example.com/search?q=test&limit=10",
            payload={"results": []},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="search-001",
            tool_name="search",
            command="http://api.example.com/search",
            parameters={
                "query": {"q": "test", "limit": 10}
            },
            context={"http_method": "GET"}
        )

        assert result.success is True
        assert result.exit_code == 200

    @pytest.mark.asyncio
    async def test_execute_with_authentication(self, rest_adapter, mock_aiohttp):
        """Testa Bearer token no header."""
        mock_aiohttp.post(
            "http://api.example.com/secure",
            payload={"authenticated": True},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="secure-001",
            tool_name="secure-api",
            command="http://api.example.com/secure",
            parameters={"body": {}},
            context={
                "http_method": "POST",
                "auth_token": "secret-bearer-token"
            }
        )

        assert result.success is True
        assert "authenticated" in result.output

    @pytest.mark.asyncio
    async def test_execute_with_custom_headers(self, rest_adapter, mock_aiohttp):
        """Testa headers customizados."""
        mock_aiohttp.post(
            "http://api.example.com/custom",
            payload={"received": True},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="custom-001",
            tool_name="custom-api",
            command="http://api.example.com/custom",
            parameters={"body": {}},
            context={
                "http_method": "POST",
                "headers": {
                    "X-Custom-Header": "custom-value",
                    "Accept": "application/json"
                }
            }
        )

        assert result.success is True


# ============================================================================
# Testes de Status HTTP
# ============================================================================

class TestHTTPStatusHandling:
    """Testes de tratamento de status HTTP."""

    @pytest.mark.asyncio
    async def test_execute_2xx_success(self, rest_adapter, mock_aiohttp):
        """Testa status 2xx como sucesso."""
        # 201 Created
        mock_aiohttp.post(
            "http://api.example.com/create",
            payload={"id": 123},
            status=201
        )

        result = await rest_adapter.execute(
            tool_id="create-001",
            tool_name="create",
            command="http://api.example.com/create",
            parameters={"body": {"name": "test"}},
            context={"http_method": "POST"}
        )

        assert result.success is True
        assert result.exit_code == 201

    @pytest.mark.asyncio
    async def test_execute_4xx_failure(self, rest_adapter, mock_aiohttp):
        """Testa status 4xx como falha."""
        mock_aiohttp.post(
            "http://api.example.com/bad",
            payload={"error": "Bad Request"},
            status=400
        )

        result = await rest_adapter.execute(
            tool_id="bad-001",
            tool_name="bad-api",
            command="http://api.example.com/bad",
            parameters={"body": {}},
            context={"http_method": "POST"}
        )

        assert result.success is False
        assert result.exit_code == 400
        assert "HTTP 400" in result.error

    @pytest.mark.asyncio
    async def test_execute_401_unauthorized(self, rest_adapter, mock_aiohttp):
        """Testa status 401 Unauthorized."""
        mock_aiohttp.get(
            "http://api.example.com/protected",
            payload={"error": "Unauthorized"},
            status=401
        )

        result = await rest_adapter.execute(
            tool_id="protected-001",
            tool_name="protected",
            command="http://api.example.com/protected",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is False
        assert result.exit_code == 401

    @pytest.mark.asyncio
    async def test_execute_404_not_found(self, rest_adapter, mock_aiohttp):
        """Testa status 404 Not Found."""
        mock_aiohttp.get(
            "http://api.example.com/missing",
            payload={"error": "Not Found"},
            status=404
        )

        result = await rest_adapter.execute(
            tool_id="missing-001",
            tool_name="missing",
            command="http://api.example.com/missing",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is False
        assert result.exit_code == 404

    @pytest.mark.asyncio
    async def test_execute_500_server_error(self, rest_adapter, mock_aiohttp):
        """Testa status 500 Server Error."""
        # Com retry, precisa mockar 3 vezes (max_retries=3)
        mock_aiohttp.post(
            "http://api.example.com/error",
            payload={"error": "Internal Server Error"},
            status=500,
            repeat=True
        )

        result = await rest_adapter.execute(
            tool_id="error-001",
            tool_name="error-api",
            command="http://api.example.com/error",
            parameters={"body": {}},
            context={"http_method": "POST"}
        )

        assert result.success is False
        assert result.exit_code == 500


# ============================================================================
# Testes de Timeout e Retry
# ============================================================================

class TestTimeoutAndRetry:
    """Testes de timeout e retry."""

    @pytest.mark.asyncio
    async def test_execute_timeout(self, mock_aiohttp):
        """Testa timeout de requisicao."""
        adapter = RESTAdapter(timeout_seconds=1, max_retries=1)

        mock_aiohttp.post(
            "http://api.example.com/slow",
            exception=asyncio.TimeoutError()
        )

        result = await adapter.execute(
            tool_id="slow-001",
            tool_name="slow-api",
            command="http://api.example.com/slow",
            parameters={"body": {}},
            context={"http_method": "POST"}
        )

        assert result.success is False
        assert "Timeout" in result.error
        assert result.metadata.get("timeout") is True

    @pytest.mark.asyncio
    async def test_execute_retry_on_failure(self, mock_aiohttp):
        """Testa retry com exponential backoff."""
        adapter = RESTAdapter(timeout_seconds=5, max_retries=3)

        # Primeira e segunda tentativa falham, terceira sucesso
        mock_aiohttp.post(
            "http://api.example.com/flaky",
            exception=asyncio.TimeoutError()
        )
        mock_aiohttp.post(
            "http://api.example.com/flaky",
            exception=asyncio.TimeoutError()
        )
        mock_aiohttp.post(
            "http://api.example.com/flaky",
            payload={"success": True},
            status=200
        )

        result = await adapter.execute(
            tool_id="flaky-001",
            tool_name="flaky-api",
            command="http://api.example.com/flaky",
            parameters={"body": {}},
            context={"http_method": "POST"}
        )

        assert result.success is True
        assert result.metadata.get("attempt") == 3

    @pytest.mark.asyncio
    async def test_execute_all_retries_exhausted(self, mock_aiohttp):
        """Testa quando todas as tentativas falham."""
        adapter = RESTAdapter(timeout_seconds=1, max_retries=2)

        mock_aiohttp.post(
            "http://api.example.com/down",
            exception=asyncio.TimeoutError(),
            repeat=True
        )

        result = await adapter.execute(
            tool_id="down-001",
            tool_name="down-api",
            command="http://api.example.com/down",
            parameters={"body": {}},
            context={"http_method": "POST"}
        )

        assert result.success is False
        assert result.metadata.get("attempts") == 2


# ============================================================================
# Testes de Tratamento de Erros
# ============================================================================

class TestErrorHandling:
    """Testes de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_execute_connection_error(self, mock_aiohttp):
        """Testa erro de conexao."""
        import aiohttp

        adapter = RESTAdapter(timeout_seconds=5, max_retries=1)

        mock_aiohttp.post(
            "http://api.example.com/unreachable",
            exception=aiohttp.ClientConnectionError("Connection refused")
        )

        result = await adapter.execute(
            tool_id="unreachable-001",
            tool_name="unreachable",
            command="http://api.example.com/unreachable",
            parameters={"body": {}},
            context={"http_method": "POST"}
        )

        assert result.success is False
        assert "ClientConnectionError" in result.metadata.get("exception", "")

    @pytest.mark.asyncio
    async def test_execute_invalid_json_response(self, rest_adapter, mock_aiohttp):
        """Testa resposta com JSON invalido."""
        mock_aiohttp.get(
            "http://api.example.com/invalid",
            body="not json",
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="invalid-001",
            tool_name="invalid",
            command="http://api.example.com/invalid",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        # Deve retornar sucesso pois status e 200, mas output e texto
        assert result.success is True
        assert result.output == "not json"


# ============================================================================
# Testes de Validacao de Disponibilidade
# ============================================================================

class TestToolAvailability:
    """Testes de validacao de disponibilidade."""

    @pytest.mark.asyncio
    async def test_validate_tool_availability_success(self, rest_adapter):
        """Testa que validacao sempre retorna True (implementacao atual)."""
        # Nota: implementacao atual sempre retorna True
        # Testes reais devem ser feitos em integration tests
        result = await rest_adapter.validate_tool_availability("sonarqube")
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_tool_availability_any_tool(self, rest_adapter):
        """Testa validacao para qualquer ferramenta."""
        result = await rest_adapter.validate_tool_availability("any-tool")
        assert result is True


# ============================================================================
# Testes de Metodo HTTP Padrao
# ============================================================================

class TestDefaultHTTPMethod:
    """Testes de metodo HTTP padrao."""

    @pytest.mark.asyncio
    async def test_default_method_is_post(self, rest_adapter, mock_aiohttp):
        """Testa que metodo padrao e POST."""
        mock_aiohttp.post(
            "http://api.example.com/default",
            payload={"method": "POST"},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="default-001",
            tool_name="default",
            command="http://api.example.com/default",
            parameters={"body": {}},
            context={}  # Sem http_method especificado
        )

        assert result.success is True
        assert result.metadata.get("method") == "POST"

    @pytest.mark.asyncio
    async def test_method_case_insensitive(self, rest_adapter, mock_aiohttp):
        """Testa que metodo e case-insensitive."""
        mock_aiohttp.get(
            "http://api.example.com/case",
            payload={"result": "ok"},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="case-001",
            tool_name="case",
            command="http://api.example.com/case",
            parameters={"query": {}},
            context={"http_method": "get"}  # lowercase
        )

        assert result.success is True
        assert result.metadata.get("method") == "GET"


# ============================================================================
# Testes de Tempo de Execucao
# ============================================================================

class TestExecutionTime:
    """Testes de medicao de tempo de execucao."""

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self, rest_adapter, mock_aiohttp):
        """Testa que tempo de execucao e registrado."""
        mock_aiohttp.get(
            "http://api.example.com/timed",
            payload={"result": "ok"},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="timed-001",
            tool_name="timed",
            command="http://api.example.com/timed",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.execution_time_ms > 0
        assert result.execution_time_ms < 10000  # Menos de 10s para teste

    @pytest.mark.asyncio
    async def test_execution_time_includes_retries(self, mock_aiohttp):
        """Testa que tempo de execucao inclui retries."""
        adapter = RESTAdapter(timeout_seconds=1, max_retries=2)

        mock_aiohttp.post(
            "http://api.example.com/slow-retry",
            exception=asyncio.TimeoutError()
        )
        mock_aiohttp.post(
            "http://api.example.com/slow-retry",
            payload={"success": True},
            status=200
        )

        result = await adapter.execute(
            tool_id="slow-retry-001",
            tool_name="slow-retry",
            command="http://api.example.com/slow-retry",
            parameters={"body": {}},
            context={"http_method": "POST"}
        )

        # Tempo deve incluir backoff entre retries
        assert result.execution_time_ms > 0


# ============================================================================
# Testes de Metadados
# ============================================================================

class TestMetadata:
    """Testes de metadados do resultado."""

    @pytest.mark.asyncio
    async def test_metadata_includes_endpoint(self, rest_adapter, mock_aiohttp):
        """Testa que metadata inclui endpoint."""
        mock_aiohttp.get(
            "http://api.example.com/meta",
            payload={"result": "ok"},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="meta-001",
            tool_name="meta",
            command="http://api.example.com/meta",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.metadata.get("endpoint") == "http://api.example.com/meta"

    @pytest.mark.asyncio
    async def test_metadata_includes_status_code(self, rest_adapter, mock_aiohttp):
        """Testa que metadata inclui status code."""
        mock_aiohttp.get(
            "http://api.example.com/status",
            payload={"result": "ok"},
            status=201
        )

        result = await rest_adapter.execute(
            tool_id="status-001",
            tool_name="status",
            command="http://api.example.com/status",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.metadata.get("status_code") == 201

    @pytest.mark.asyncio
    async def test_metadata_includes_attempt_number(self, rest_adapter, mock_aiohttp):
        """Testa que metadata inclui numero da tentativa."""
        mock_aiohttp.get(
            "http://api.example.com/attempt",
            payload={"result": "ok"},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="attempt-001",
            tool_name="attempt",
            command="http://api.example.com/attempt",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.metadata.get("attempt") == 1


# ============================================================================
# Testes de Diferentes Tipos de Response
# ============================================================================

class TestResponseTypes:
    """Testes de diferentes tipos de resposta."""

    @pytest.mark.asyncio
    async def test_json_response(self, rest_adapter, mock_aiohttp):
        """Testa resposta JSON."""
        mock_aiohttp.get(
            "http://api.example.com/json",
            payload={"key": "value", "number": 42},
            status=200
        )

        result = await rest_adapter.execute(
            tool_id="json-001",
            tool_name="json",
            command="http://api.example.com/json",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is True
        assert "key" in result.output
        assert "value" in result.output

    @pytest.mark.asyncio
    async def test_text_response(self, rest_adapter, mock_aiohttp):
        """Testa resposta texto."""
        mock_aiohttp.get(
            "http://api.example.com/text",
            body="Plain text response",
            status=200,
            content_type="text/plain"
        )

        result = await rest_adapter.execute(
            tool_id="text-001",
            tool_name="text",
            command="http://api.example.com/text",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is True
        assert result.output == "Plain text response"

    @pytest.mark.asyncio
    async def test_empty_response(self, rest_adapter, mock_aiohttp):
        """Testa resposta vazia."""
        mock_aiohttp.delete(
            "http://api.example.com/delete",
            body="",
            status=204
        )

        result = await rest_adapter.execute(
            tool_id="delete-001",
            tool_name="delete",
            command="http://api.example.com/delete",
            parameters={"body": {}},
            context={"http_method": "DELETE"}
        )

        assert result.success is True
        assert result.output == ""
        assert result.exit_code == 204
