"""
Cliente AWS Lambda Runtime para execução de comandos via Lambda.

Este cliente implementa execução serverless de comandos via AWS Lambda API,
com suporte a invocação síncrona e assíncrona.
"""

import asyncio
import json
import base64
import structlog
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from opentelemetry import trace
from pydantic import BaseModel, Field
from enum import Enum


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class LambdaRuntimeError(Exception):
    """Erro de execução no Lambda Runtime."""
    def __init__(self, message: str, status_code: Optional[int] = None, error_type: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


class LambdaTimeoutError(Exception):
    """Timeout aguardando execução Lambda."""
    pass


class LambdaInvocationType(str, Enum):
    """Tipos de invocação Lambda."""
    REQUEST_RESPONSE = 'RequestResponse'  # Síncrono
    EVENT = 'Event'  # Assíncrono
    DRY_RUN = 'DryRun'  # Validação apenas


class LambdaLogType(str, Enum):
    """Tipos de log Lambda."""
    NONE = 'None'
    TAIL = 'Tail'  # Retorna últimos 4KB de logs


class LambdaPayload(BaseModel):
    """Payload para invocação Lambda."""
    command: str = Field(..., description='Comando a executar')
    args: Optional[list] = Field(default=None, description='Argumentos do comando')
    env_vars: Optional[Dict[str, str]] = Field(default=None, description='Variáveis de ambiente')
    working_dir: Optional[str] = Field(default=None, description='Diretório de trabalho')
    timeout_seconds: Optional[int] = Field(default=None, description='Timeout da execução')
    stdin: Optional[str] = Field(default=None, description='Input para stdin')


class LambdaInvocationRequest(BaseModel):
    """Request para invocação Lambda."""
    function_name: str = Field(..., description='Nome ou ARN da função Lambda')
    payload: LambdaPayload = Field(..., description='Payload da invocação')
    invocation_type: LambdaInvocationType = Field(default=LambdaInvocationType.REQUEST_RESPONSE)
    log_type: LambdaLogType = Field(default=LambdaLogType.TAIL)
    qualifier: Optional[str] = Field(default=None, description='Versão ou alias da função')
    client_context: Optional[Dict[str, Any]] = Field(default=None, description='Contexto do cliente')


class LambdaExecutionOutput(BaseModel):
    """Output da execução no Lambda."""
    exit_code: int = 0
    stdout: str = ''
    stderr: str = ''
    error: Optional[str] = None


class LambdaInvocationResult(BaseModel):
    """Resultado da invocação Lambda."""
    request_id: str
    status_code: int
    function_error: Optional[str] = None
    log_result: Optional[str] = None
    executed_version: Optional[str] = None
    response: LambdaExecutionOutput
    duration_ms: int
    billed_duration_ms: Optional[int] = None
    memory_used_mb: Optional[int] = None


class LambdaRuntimeClient:
    """Cliente para execução de comandos via AWS Lambda."""

    def __init__(
        self,
        region: str = 'us-east-1',
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        session_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout: int = 900,
        function_name: str = 'neural-hive-executor',
    ):
        """
        Inicializa cliente Lambda Runtime.

        Args:
            region: Região AWS
            access_key: AWS Access Key (None para IAM role)
            secret_key: AWS Secret Key (None para IAM role)
            session_token: AWS Session Token (para credenciais temporárias)
            endpoint_url: URL customizada do endpoint (para LocalStack, etc)
            timeout: Timeout padrão em segundos (max 900)
            function_name: Nome padrão da função Lambda
        """
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.endpoint_url = endpoint_url
        self.timeout = min(timeout, 900)  # Lambda max é 15 min
        self.function_name = function_name
        self._session = None
        self._client = None
        self._initialized = False
        self.logger = logger.bind(service='lambda_runtime_client')

    async def initialize(self) -> None:
        """Inicializa sessão AWS."""
        try:
            import aioboto3

            session_kwargs = {
                'region_name': self.region,
            }

            if self.access_key and self.secret_key:
                session_kwargs['aws_access_key_id'] = self.access_key
                session_kwargs['aws_secret_access_key'] = self.secret_key
                if self.session_token:
                    session_kwargs['aws_session_token'] = self.session_token

            self._session = aioboto3.Session(**session_kwargs)
            self._initialized = True
            self.logger.info(
                'lambda_runtime_client_initialized',
                region=self.region,
                function=self.function_name
            )

        except ImportError:
            self.logger.error('aioboto3_not_installed')
            raise LambdaRuntimeError('aioboto3 não está instalado')
        except Exception as e:
            self.logger.error('lambda_runtime_init_failed', error=str(e))
            raise LambdaRuntimeError(f'Falha ao inicializar cliente Lambda: {e}')

    async def close(self) -> None:
        """Fecha sessão AWS."""
        self._session = None
        self._initialized = False
        self.logger.info('lambda_runtime_client_closed')

    def _parse_log_result(self, log_result: Optional[str]) -> Optional[str]:
        """Decodifica logs em base64 retornados pelo Lambda."""
        if not log_result:
            return None
        try:
            return base64.b64decode(log_result).decode('utf-8')
        except Exception:
            return log_result

    def _parse_response_payload(self, payload: bytes) -> LambdaExecutionOutput:
        """Parseia payload de resposta do Lambda."""
        try:
            data = json.loads(payload.decode('utf-8'))

            # Se o Lambda retorna diretamente o resultado de execução
            if isinstance(data, dict):
                return LambdaExecutionOutput(
                    exit_code=data.get('exit_code', data.get('exitCode', 0)),
                    stdout=data.get('stdout', data.get('output', '')),
                    stderr=data.get('stderr', ''),
                    error=data.get('error', data.get('errorMessage'))
                )

            # Se retorna string simples
            return LambdaExecutionOutput(
                exit_code=0,
                stdout=str(data),
                stderr=''
            )

        except json.JSONDecodeError:
            # Payload não é JSON
            return LambdaExecutionOutput(
                exit_code=0,
                stdout=payload.decode('utf-8', errors='replace'),
                stderr=''
            )
        except Exception as e:
            return LambdaExecutionOutput(
                exit_code=-1,
                stdout='',
                stderr='',
                error=f'Erro ao parsear resposta: {e}'
            )

    def _extract_metrics_from_logs(self, logs: Optional[str]) -> Dict[str, Any]:
        """Extrai métricas de billing dos logs do Lambda."""
        metrics = {}
        if not logs:
            return metrics

        try:
            for line in logs.split('\n'):
                if 'Billed Duration:' in line:
                    parts = line.split('Billed Duration:')[1].split()
                    if parts:
                        metrics['billed_duration_ms'] = int(parts[0])
                if 'Memory Size:' in line:
                    parts = line.split('Memory Size:')[1].split()
                    if parts:
                        metrics['memory_size_mb'] = int(parts[0])
                if 'Max Memory Used:' in line:
                    parts = line.split('Max Memory Used:')[1].split()
                    if parts:
                        metrics['memory_used_mb'] = int(parts[0])
        except Exception:
            pass

        return metrics

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def invoke_lambda(
        self,
        request: LambdaInvocationRequest,
        metrics=None
    ) -> LambdaInvocationResult:
        """
        Invoca função Lambda para executar comando.

        Args:
            request: Parâmetros da invocação
            metrics: Objeto de métricas Prometheus (opcional)

        Returns:
            LambdaInvocationResult com resultado da execução

        Raises:
            LambdaRuntimeError: Erro na invocação
            LambdaTimeoutError: Timeout aguardando execução
        """
        if not self._initialized:
            await self.initialize()

        with tracer.start_as_current_span('lambda.invoke') as span:
            function_name = request.function_name or self.function_name
            span.set_attribute('lambda.function_name', function_name)
            span.set_attribute('lambda.invocation_type', request.invocation_type.value)

            start_time = asyncio.get_event_loop().time()

            try:
                # Preparar payload
                payload_json = json.dumps(request.payload.model_dump(exclude_none=True))

                self.logger.info(
                    'lambda_invoking',
                    function_name=function_name,
                    invocation_type=request.invocation_type.value,
                    payload_size=len(payload_json)
                )

                # Preparar parâmetros da invocação
                invoke_params = {
                    'FunctionName': function_name,
                    'InvocationType': request.invocation_type.value,
                    'LogType': request.log_type.value,
                    'Payload': payload_json.encode('utf-8'),
                }

                if request.qualifier:
                    invoke_params['Qualifier'] = request.qualifier

                if request.client_context:
                    context_json = json.dumps(request.client_context)
                    invoke_params['ClientContext'] = base64.b64encode(
                        context_json.encode('utf-8')
                    ).decode('utf-8')

                # Invocar Lambda
                client_kwargs = {}
                if self.endpoint_url:
                    client_kwargs['endpoint_url'] = self.endpoint_url

                async with self._session.client('lambda', **client_kwargs) as lambda_client:
                    try:
                        response = await asyncio.wait_for(
                            lambda_client.invoke(**invoke_params),
                            timeout=self.timeout
                        )
                    except asyncio.TimeoutError:
                        raise LambdaTimeoutError(
                            f'Timeout após {self.timeout}s invocando {function_name}'
                        )

                # Processar resposta
                status_code = response.get('StatusCode', 500)
                function_error = response.get('FunctionError')
                request_id = response['ResponseMetadata']['RequestId']
                executed_version = response.get('ExecutedVersion')
                log_result = self._parse_log_result(response.get('LogResult'))

                # Ler payload de resposta
                payload_stream = response.get('Payload')
                if payload_stream:
                    response_payload = await payload_stream.read()
                    execution_output = self._parse_response_payload(response_payload)
                else:
                    execution_output = LambdaExecutionOutput(
                        exit_code=-1,
                        error='Nenhum payload retornado'
                    )

                # Se houve erro de função
                if function_error:
                    execution_output.error = function_error
                    if execution_output.exit_code == 0:
                        execution_output.exit_code = 1

                duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

                # Extrair métricas de billing dos logs
                billing_metrics = self._extract_metrics_from_logs(log_result)

                span.set_attribute('lambda.request_id', request_id)
                span.set_attribute('lambda.status_code', status_code)
                if function_error:
                    span.set_attribute('lambda.function_error', function_error)

                self.logger.info(
                    'lambda_invocation_completed',
                    function_name=function_name,
                    request_id=request_id,
                    status_code=status_code,
                    function_error=function_error,
                    duration_ms=duration_ms,
                    billed_duration_ms=billing_metrics.get('billed_duration_ms')
                )

                # Registrar métricas
                if metrics:
                    status = 'success' if not function_error else 'failed'
                    if hasattr(metrics, 'lambda_invocations_total'):
                        metrics.lambda_invocations_total.labels(status=status).inc()
                    if hasattr(metrics, 'lambda_duration_seconds'):
                        metrics.lambda_duration_seconds.observe(duration_ms / 1000)
                    if billing_metrics.get('billed_duration_ms') and hasattr(metrics, 'lambda_billed_duration_seconds'):
                        metrics.lambda_billed_duration_seconds.observe(
                            billing_metrics['billed_duration_ms'] / 1000
                        )

                return LambdaInvocationResult(
                    request_id=request_id,
                    status_code=status_code,
                    function_error=function_error,
                    log_result=log_result,
                    executed_version=executed_version,
                    response=execution_output,
                    duration_ms=duration_ms,
                    billed_duration_ms=billing_metrics.get('billed_duration_ms'),
                    memory_used_mb=billing_metrics.get('memory_used_mb')
                )

            except LambdaTimeoutError:
                if metrics and hasattr(metrics, 'lambda_invocations_total'):
                    metrics.lambda_invocations_total.labels(status='timeout').inc()
                raise

            except Exception as e:
                self.logger.error(
                    'lambda_invocation_failed',
                    function_name=function_name,
                    error=str(e)
                )
                if metrics and hasattr(metrics, 'lambda_invocations_total'):
                    metrics.lambda_invocations_total.labels(status='failed').inc()
                raise LambdaRuntimeError(f'Erro na invocação Lambda: {e}')

    async def health_check(self) -> bool:
        """Verifica se Lambda API está acessível."""
        try:
            if not self._session:
                return False

            async with self._session.client('lambda') as lambda_client:
                await lambda_client.list_functions(MaxItems=1)
            return True
        except Exception:
            return False

    async def get_function_info(self, function_name: Optional[str] = None) -> Dict[str, Any]:
        """Obtém informações da função Lambda."""
        if not self._initialized:
            await self.initialize()

        fn_name = function_name or self.function_name

        try:
            async with self._session.client('lambda') as lambda_client:
                response = await lambda_client.get_function(FunctionName=fn_name)
                config = response.get('Configuration', {})
                return {
                    'function_name': config.get('FunctionName'),
                    'runtime': config.get('Runtime'),
                    'memory_size': config.get('MemorySize'),
                    'timeout': config.get('Timeout'),
                    'handler': config.get('Handler'),
                    'last_modified': config.get('LastModified'),
                    'state': config.get('State'),
                }
        except Exception as e:
            self.logger.warning('lambda_get_function_failed', function_name=fn_name, error=str(e))
            return {}
