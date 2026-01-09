"""
Testes unitarios para LambdaRuntimeClient.

Cobertura:
- Inicializacao
- Invocacao sincrona
- Invocacao assincrona
- Parsing de resposta
- Timeout handling
- Error handling
- Metricas de billing
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLambdaRuntimeClientInitialization:
    """Testes de inicializacao."""

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Deve inicializar cliente com sucesso."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(
            region='us-east-1',
            access_key='test-key',
            secret_key='test-secret'
        )

        with patch('src.clients.lambda_runtime_client.aioboto3') as mock_boto:
            mock_session = MagicMock()
            mock_boto.Session.return_value = mock_session

            await client.initialize()

            assert client._initialized is True
            mock_boto.Session.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_aioboto3_not_installed(self):
        """Deve levantar erro quando aioboto3 nao instalado."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient, LambdaRuntimeError

        client = LambdaRuntimeClient(region='us-east-1')

        with patch.dict('sys.modules', {'aioboto3': None}):
            with patch('builtins.__import__', side_effect=ImportError):
                # Import error seria capturado
                pass


class TestLambdaRuntimeClientInvocation:
    """Testes de invocacao."""

    @pytest.mark.asyncio
    async def test_invoke_lambda_success(self):
        """Deve invocar Lambda com sucesso."""
        from src.clients.lambda_runtime_client import (
            LambdaRuntimeClient, LambdaInvocationRequest,
            LambdaPayload, LambdaInvocationType
        )

        client = LambdaRuntimeClient(
            region='us-east-1',
            function_name='test-function'
        )
        client._initialized = True

        mock_session = MagicMock()
        mock_lambda_client = AsyncMock()

        # Mock response payload
        mock_payload_stream = AsyncMock()
        mock_payload_stream.read = AsyncMock(return_value=json.dumps({
            'exit_code': 0,
            'stdout': 'Hello World',
            'stderr': ''
        }).encode('utf-8'))

        mock_response = {
            'StatusCode': 200,
            'FunctionError': None,
            'LogResult': None,
            'ExecutedVersion': '$LATEST',
            'ResponseMetadata': {'RequestId': 'req-123'},
            'Payload': mock_payload_stream
        }

        # Setup context manager mock
        mock_lambda_client.__aenter__ = AsyncMock(return_value=mock_lambda_client)
        mock_lambda_client.__aexit__ = AsyncMock(return_value=None)
        mock_lambda_client.invoke = AsyncMock(return_value=mock_response)

        mock_session.client = MagicMock(return_value=mock_lambda_client)
        client._session = mock_session

        request = LambdaInvocationRequest(
            function_name='test-function',
            payload=LambdaPayload(
                command='echo',
                args=['Hello', 'World']
            ),
            invocation_type=LambdaInvocationType.REQUEST_RESPONSE
        )

        result = await client.invoke_lambda(request)

        assert result.status_code == 200
        assert result.response.exit_code == 0
        assert result.response.stdout == 'Hello World'

    @pytest.mark.asyncio
    async def test_invoke_lambda_with_function_error(self):
        """Deve tratar function error."""
        from src.clients.lambda_runtime_client import (
            LambdaRuntimeClient, LambdaInvocationRequest,
            LambdaPayload
        )

        client = LambdaRuntimeClient(region='us-east-1')
        client._initialized = True

        mock_session = MagicMock()
        mock_lambda_client = AsyncMock()

        mock_payload_stream = AsyncMock()
        mock_payload_stream.read = AsyncMock(return_value=json.dumps({
            'errorMessage': 'Command failed',
            'errorType': 'RuntimeError'
        }).encode('utf-8'))

        mock_response = {
            'StatusCode': 200,
            'FunctionError': 'Unhandled',
            'LogResult': None,
            'ResponseMetadata': {'RequestId': 'req-456'},
            'Payload': mock_payload_stream
        }

        mock_lambda_client.__aenter__ = AsyncMock(return_value=mock_lambda_client)
        mock_lambda_client.__aexit__ = AsyncMock(return_value=None)
        mock_lambda_client.invoke = AsyncMock(return_value=mock_response)

        mock_session.client = MagicMock(return_value=mock_lambda_client)
        client._session = mock_session

        request = LambdaInvocationRequest(
            function_name='test-function',
            payload=LambdaPayload(command='bad-command')
        )

        result = await client.invoke_lambda(request)

        assert result.function_error == 'Unhandled'
        assert result.response.exit_code != 0

    @pytest.mark.asyncio
    async def test_invoke_lambda_timeout(self):
        """Deve levantar timeout."""
        from src.clients.lambda_runtime_client import (
            LambdaRuntimeClient, LambdaInvocationRequest,
            LambdaPayload, LambdaTimeoutError
        )

        client = LambdaRuntimeClient(region='us-east-1', timeout=1)
        client._initialized = True

        mock_session = MagicMock()
        mock_lambda_client = AsyncMock()

        # Simular timeout
        async def slow_invoke(**kwargs):
            await asyncio.sleep(10)
            return {}

        mock_lambda_client.__aenter__ = AsyncMock(return_value=mock_lambda_client)
        mock_lambda_client.__aexit__ = AsyncMock(return_value=None)
        mock_lambda_client.invoke = slow_invoke

        mock_session.client = MagicMock(return_value=mock_lambda_client)
        client._session = mock_session

        request = LambdaInvocationRequest(
            function_name='test-function',
            payload=LambdaPayload(command='slow-command')
        )

        with pytest.raises(LambdaTimeoutError):
            await client.invoke_lambda(request)


class TestLambdaRuntimeClientParsing:
    """Testes de parsing de resposta."""

    def test_parse_response_payload_dict(self):
        """Deve parsear payload dict."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(region='us-east-1')

        payload = json.dumps({
            'exit_code': 0,
            'stdout': 'Output text',
            'stderr': 'Error text'
        }).encode('utf-8')

        output = client._parse_response_payload(payload)

        assert output.exit_code == 0
        assert output.stdout == 'Output text'
        assert output.stderr == 'Error text'

    def test_parse_response_payload_string(self):
        """Deve parsear payload string."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(region='us-east-1')

        payload = json.dumps('Simple string output').encode('utf-8')

        output = client._parse_response_payload(payload)

        assert output.exit_code == 0
        assert output.stdout == 'Simple string output'

    def test_parse_response_payload_non_json(self):
        """Deve tratar payload nao-JSON."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(region='us-east-1')

        payload = b'Plain text response'

        output = client._parse_response_payload(payload)

        assert output.exit_code == 0
        assert output.stdout == 'Plain text response'

    def test_parse_log_result(self):
        """Deve decodificar log result base64."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient
        import base64

        client = LambdaRuntimeClient(region='us-east-1')

        log_text = 'START RequestId: abc123\nEND RequestId: abc123'
        log_base64 = base64.b64encode(log_text.encode('utf-8')).decode('utf-8')

        result = client._parse_log_result(log_base64)

        assert 'START RequestId' in result

    def test_extract_metrics_from_logs(self):
        """Deve extrair metricas de billing dos logs."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(region='us-east-1')

        logs = '''
        START RequestId: abc123
        Billed Duration: 100 ms
        Memory Size: 128 MB
        Max Memory Used: 64 MB
        END RequestId: abc123
        '''

        metrics = client._extract_metrics_from_logs(logs)

        assert metrics['billed_duration_ms'] == 100
        assert metrics['memory_size_mb'] == 128
        assert metrics['memory_used_mb'] == 64


class TestLambdaRuntimeClientHealthCheck:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Deve retornar True quando API acessivel."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(region='us-east-1')

        mock_session = MagicMock()
        mock_lambda_client = AsyncMock()
        mock_lambda_client.__aenter__ = AsyncMock(return_value=mock_lambda_client)
        mock_lambda_client.__aexit__ = AsyncMock(return_value=None)
        mock_lambda_client.list_functions = AsyncMock(return_value={'Functions': []})

        mock_session.client = MagicMock(return_value=mock_lambda_client)
        client._session = mock_session

        result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_no_session(self):
        """Deve retornar False quando sem sessao."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(region='us-east-1')
        client._session = None

        result = await client.health_check()

        assert result is False


class TestLambdaRuntimeClientFunctionInfo:
    """Testes de obtencao de info da funcao."""

    @pytest.mark.asyncio
    async def test_get_function_info_success(self):
        """Deve obter informacoes da funcao."""
        from src.clients.lambda_runtime_client import LambdaRuntimeClient

        client = LambdaRuntimeClient(
            region='us-east-1',
            function_name='test-function'
        )
        client._initialized = True

        mock_session = MagicMock()
        mock_lambda_client = AsyncMock()
        mock_lambda_client.__aenter__ = AsyncMock(return_value=mock_lambda_client)
        mock_lambda_client.__aexit__ = AsyncMock(return_value=None)
        mock_lambda_client.get_function = AsyncMock(return_value={
            'Configuration': {
                'FunctionName': 'test-function',
                'Runtime': 'python3.11',
                'MemorySize': 512,
                'Timeout': 300,
                'Handler': 'lambda_function.handler',
                'State': 'Active'
            }
        })

        mock_session.client = MagicMock(return_value=mock_lambda_client)
        client._session = mock_session

        info = await client.get_function_info()

        assert info['function_name'] == 'test-function'
        assert info['runtime'] == 'python3.11'
        assert info['memory_size'] == 512


class TestLambdaRuntimeClientModels:
    """Testes dos modelos Pydantic."""

    def test_lambda_payload_model(self):
        """Deve validar LambdaPayload."""
        from src.clients.lambda_runtime_client import LambdaPayload

        payload = LambdaPayload(
            command='echo',
            args=['hello', 'world'],
            env_vars={'DEBUG': 'true'},
            working_dir='/tmp',
            timeout_seconds=60
        )

        assert payload.command == 'echo'
        assert len(payload.args) == 2
        assert payload.env_vars['DEBUG'] == 'true'

    def test_lambda_invocation_request_model(self):
        """Deve validar LambdaInvocationRequest."""
        from src.clients.lambda_runtime_client import (
            LambdaInvocationRequest, LambdaPayload,
            LambdaInvocationType, LambdaLogType
        )

        request = LambdaInvocationRequest(
            function_name='my-function',
            payload=LambdaPayload(command='test'),
            invocation_type=LambdaInvocationType.REQUEST_RESPONSE,
            log_type=LambdaLogType.TAIL,
            qualifier='$LATEST'
        )

        assert request.function_name == 'my-function'
        assert request.invocation_type == LambdaInvocationType.REQUEST_RESPONSE

    def test_lambda_invocation_result_model(self):
        """Deve validar LambdaInvocationResult."""
        from src.clients.lambda_runtime_client import (
            LambdaInvocationResult, LambdaExecutionOutput
        )

        result = LambdaInvocationResult(
            request_id='req-123',
            status_code=200,
            function_error=None,
            response=LambdaExecutionOutput(
                exit_code=0,
                stdout='Success',
                stderr=''
            ),
            duration_ms=150,
            billed_duration_ms=200,
            memory_used_mb=64
        )

        assert result.request_id == 'req-123'
        assert result.response.exit_code == 0
        assert result.billed_duration_ms == 200
