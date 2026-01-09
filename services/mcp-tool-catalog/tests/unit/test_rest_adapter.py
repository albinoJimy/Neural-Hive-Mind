"""
Testes unitarios para RESTAdapter.

Cobertura:
- Execucao de requisicoes REST (GET, POST, PUT, DELETE)
- Tratamento de erros HTTP (4xx, 5xx)
- Timeout e retries com exponential backoff
- Headers e autenticacao Bearer
- Parsing de query params e body
- Metricas de execucao
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRESTAdapterExecution:
    """Testes de execucao de requisicoes REST."""

    @pytest.mark.asyncio
    async def test_execute_post_success(self):
        """Deve executar POST com sucesso."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter(timeout_seconds=30, max_retries=3)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"result": "success"}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await adapter.execute(
                tool_id='api-tool-001',
                tool_name='sonarqube',
                command='https://api.example.com/analyze',
                parameters={'body': {'project': 'myapp'}},
                context={'http_method': 'POST'}
            )

            assert result.success is True
            assert result.exit_code == 200
            assert '{"result": "success"}' in result.output

            # Validar chamada do request
            mock_session.request.assert_called_once()
            call_kwargs = mock_session.request.call_args.kwargs
            assert call_kwargs['method'] == 'POST'
            assert call_kwargs['url'] == 'https://api.example.com/analyze'

    @pytest.mark.asyncio
    async def test_execute_get_success(self):
        """Deve executar GET com query params."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"items": []}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await adapter.execute(
                tool_id='api-tool-001',
                tool_name='api-client',
                command='https://api.example.com/items',
                parameters={'query': {'page': 1, 'limit': 10}},
                context={'http_method': 'GET'}
            )

            assert result.success is True
            assert result.exit_code == 200

            # Validar query params
            call_kwargs = mock_session.request.call_args.kwargs
            assert call_kwargs['method'] == 'GET'
            assert call_kwargs['params'] == {'page': 1, 'limit': 10}


class TestRESTAdapterErrorHandling:
    """Testes de tratamento de erros HTTP."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize('status_code,expected_success', [
        (200, True),
        (201, True),
        (204, True),
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (500, False),
        (502, False),
        (503, False),
    ])
    async def test_http_status_code_handling(self, status_code, expected_success):
        """Deve tratar diferentes status codes HTTP."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter(max_retries=1)

        mock_response = AsyncMock()
        mock_response.status = status_code
        mock_response.text = AsyncMock(return_value='Response body')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await adapter.execute(
                tool_id='api-tool-001',
                tool_name='http-client',
                command='https://api.example.com/endpoint',
                parameters={},
                context={}
            )

            assert result.success is expected_success
            assert result.exit_code == status_code

            # Erros HTTP devem ter mensagem de erro
            if not expected_success:
                assert result.error is not None
                assert f'HTTP {status_code}' in result.error


class TestRESTAdapterTimeoutAndRetries:
    """Testes de timeout e retries."""

    @pytest.mark.asyncio
    async def test_timeout_after_max_retries(self):
        """Deve retornar erro apos esgotar retries por timeout."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter(timeout_seconds=1, max_retries=2)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(side_effect=asyncio.TimeoutError())
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await adapter.execute(
                    tool_id='api-tool-001',
                    tool_name='slow-api',
                    command='https://api.example.com/slow',
                    parameters={},
                    context={}
                )

            assert result.success is False
            assert 'timeout' in result.error.lower()
            assert result.metadata.get('timeout') is True

    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        """Deve fazer retry com exponential backoff."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter(timeout_seconds=5, max_retries=3)

        call_count = 0
        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='success')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        def request_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise asyncio.TimeoutError()
            return mock_response

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(side_effect=request_side_effect)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            with patch('asyncio.sleep', side_effect=mock_sleep):
                result = await adapter.execute(
                    tool_id='api-tool-001',
                    tool_name='flaky-api',
                    command='https://api.example.com/flaky',
                    parameters={},
                    context={}
                )

            assert result.success is True
            # Exponential backoff: 2^1=2, 2^2=4
            assert sleep_calls == [2, 4]

    @pytest.mark.asyncio
    async def test_general_exception_handling(self):
        """Deve tratar excecoes gerais apos retries."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter(max_retries=2)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(side_effect=Exception('Connection refused'))
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await adapter.execute(
                tool_id='api-tool-001',
                tool_name='broken-api',
                command='https://api.example.com/broken',
                parameters={},
                context={}
            )

            assert result.success is False
            assert 'Connection refused' in result.error
            assert result.metadata.get('exception') == 'Exception'


class TestRESTAdapterAuthentication:
    """Testes de autenticacao."""

    @pytest.mark.asyncio
    async def test_bearer_token_authentication(self):
        """Deve incluir Bearer token no header."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await adapter.execute(
                tool_id='api-tool-001',
                tool_name='secure-api',
                command='https://api.example.com/secure',
                parameters={},
                context={'auth_token': 'my-secret-token'}
            )

            call_kwargs = mock_session.request.call_args.kwargs
            assert 'Authorization' in call_kwargs['headers']
            assert call_kwargs['headers']['Authorization'] == 'Bearer my-secret-token'

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        """Deve passar headers customizados."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await adapter.execute(
                tool_id='api-tool-001',
                tool_name='header-api',
                command='https://api.example.com/headers',
                parameters={},
                context={
                    'headers': {
                        'X-Custom-Header': 'custom-value',
                        'Content-Type': 'application/json'
                    }
                }
            )

            call_kwargs = mock_session.request.call_args.kwargs
            assert call_kwargs['headers']['X-Custom-Header'] == 'custom-value'
            assert call_kwargs['headers']['Content-Type'] == 'application/json'


class TestRESTAdapterParameters:
    """Testes de parametros de requisicao."""

    @pytest.mark.asyncio
    async def test_query_params_and_body(self):
        """Deve separar query params do body corretamente."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await adapter.execute(
                tool_id='api-tool-001',
                tool_name='params-api',
                command='https://api.example.com/data',
                parameters={
                    'query': {'filter': 'active', 'sort': 'name'},
                    'body': {'name': 'test', 'value': 123}
                },
                context={'http_method': 'POST'}
            )

            call_kwargs = mock_session.request.call_args.kwargs
            assert call_kwargs['params'] == {'filter': 'active', 'sort': 'name'}
            assert call_kwargs['json'] == {'name': 'test', 'value': 123}

    @pytest.mark.asyncio
    async def test_empty_body_sends_none(self):
        """Deve enviar None quando body esta vazio."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            await adapter.execute(
                tool_id='api-tool-001',
                tool_name='get-api',
                command='https://api.example.com/data',
                parameters={},
                context={'http_method': 'GET'}
            )

            call_kwargs = mock_session.request.call_args.kwargs
            assert call_kwargs['json'] is None


class TestRESTAdapterMetrics:
    """Testes de metricas."""

    @pytest.mark.asyncio
    async def test_execution_time_recorded(self):
        """Deve registrar tempo de execucao."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await adapter.execute(
                tool_id='api-tool-001',
                tool_name='metrics-api',
                command='https://api.example.com/metrics',
                parameters={},
                context={}
            )

            assert result.execution_time_ms > 0
            assert isinstance(result.execution_time_ms, float)

    @pytest.mark.asyncio
    async def test_metadata_includes_request_info(self):
        """Deve incluir informacoes da requisicao no metadata."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{}')
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = MagicMock()
            mock_session.request = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            result = await adapter.execute(
                tool_id='api-tool-001',
                tool_name='metadata-api',
                command='https://api.example.com/info',
                parameters={},
                context={'http_method': 'GET'}
            )

            assert result.metadata is not None
            assert result.metadata['endpoint'] == 'https://api.example.com/info'
            assert result.metadata['method'] == 'GET'
            assert result.metadata['status_code'] == 200
            assert 'attempt' in result.metadata


class TestRESTAdapterValidation:
    """Testes de validacao."""

    @pytest.mark.asyncio
    async def test_validate_tool_availability_returns_true(self):
        """Deve retornar True para validacao (simplificado)."""
        from src.adapters.rest_adapter import RESTAdapter

        adapter = RESTAdapter()

        # RESTAdapter.validate_tool_availability retorna True por padrao
        is_available = await adapter.validate_tool_availability('any-tool')

        assert is_available is True
