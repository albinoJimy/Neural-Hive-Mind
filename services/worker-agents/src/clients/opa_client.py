"""
Cliente OPA para avaliacao de politicas.

Este cliente implementa integracao com OPA (Open Policy Agent) API para
avaliacao de politicas seguindo o padrao estabelecido pelo ArgoCDClient.
"""

import asyncio
import httpx
import structlog
from typing import Dict, Any, Optional, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from opentelemetry import trace
from pydantic import BaseModel, Field
from enum import Enum


logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


class OPAAPIError(Exception):
    """Erro de chamada a API do OPA."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class OPATimeoutError(Exception):
    """Timeout em operacoes OPA."""
    pass


class OPAValidationError(Exception):
    """Erro de validacao de politica OPA."""
    pass


class ViolationSeverity(str, Enum):
    """Niveis de severidade de violacoes."""
    CRITICAL = 'CRITICAL'
    HIGH = 'HIGH'
    MEDIUM = 'MEDIUM'
    LOW = 'LOW'
    INFO = 'INFO'


class PolicyEvaluationRequest(BaseModel):
    """Request para avaliacao de politica OPA."""
    policy_path: str = Field(..., description='Caminho da politica (ex: policy/allow)')
    input_data: Dict[str, Any] = Field(default_factory=dict, description='Dados de entrada para avaliacao')
    decision: Optional[str] = Field(default=None, description='Decision point especifico')


class Violation(BaseModel):
    """Representacao de uma violacao de politica."""
    rule_id: str = Field(..., description='Identificador da regra violada')
    message: str = Field(..., description='Mensagem descritiva da violacao')
    severity: ViolationSeverity = Field(default=ViolationSeverity.MEDIUM, description='Severidade da violacao')
    resource: Optional[str] = Field(default=None, description='Recurso afetado')
    location: Optional[Dict[str, Any]] = Field(default=None, description='Localizacao no codigo/config')


class PolicyEvaluationResponse(BaseModel):
    """Resposta de avaliacao de politica OPA."""
    allow: bool = Field(default=False, description='Se a politica permite a acao')
    violations: List[Violation] = Field(default_factory=list, description='Lista de violacoes encontradas')
    decision: Optional[str] = Field(default=None, description='Decision point avaliado')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Metadados adicionais da avaliacao')


class BundleStatus(BaseModel):
    """Status de um bundle OPA."""
    name: str = Field(..., description='Nome do bundle')
    active_revision: str = Field(default='', description='Revisao ativa do bundle')
    last_successful_activation: str = Field(default='', description='Timestamp da ultima ativacao')


class OPAClient:
    """Cliente para API do OPA (Open Policy Agent)."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool = True,
        retry_attempts: int = 3,
        retry_backoff_base: int = 2,
        retry_backoff_max: int = 10,
    ):
        """
        Inicializa cliente OPA.

        Args:
            base_url: URL base do OPA (ex: http://opa:8181)
            token: Token de autenticacao Bearer (opcional)
            timeout: Timeout padrao para requisicoes em segundos
            verify_ssl: Verificar certificado SSL
            retry_attempts: Numero de tentativas em caso de falha
            retry_backoff_base: Base para exponential backoff em segundos
            retry_backoff_max: Maximo de backoff em segundos
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.retry_attempts = retry_attempts
        self.retry_backoff_base = retry_backoff_base
        self.retry_backoff_max = retry_backoff_max
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            verify=verify_ssl
        )
        self.logger = logger.bind(service='opa_client')

    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers para requisicoes."""
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    async def close(self):
        """Fecha cliente HTTP."""
        await self.client.aclose()
        self.logger.info('opa_client_closed')

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException))
    )
    async def evaluate_policy(self, request: PolicyEvaluationRequest) -> PolicyEvaluationResponse:
        """
        Avalia uma politica no OPA.

        Args:
            request: Dados da requisicao de avaliacao

        Returns:
            Resposta da avaliacao com resultado e violacoes

        Raises:
            OPAAPIError: Erro na API do OPA
            OPATimeoutError: Timeout na requisicao
            OPAValidationError: Erro de validacao
        """
        with tracer.start_as_current_span('opa.evaluate_policy') as span:
            policy_path = request.policy_path.lstrip('/')
            span.set_attribute('opa.policy_path', policy_path)
            span.set_attribute('opa.input_keys', list(request.input_data.keys()))

            self.logger.info(
                'opa_evaluate_policy',
                policy_path=policy_path,
                input_keys=list(request.input_data.keys())
            )

            try:
                response = await self.client.post(
                    f'{self.base_url}/v1/data/{policy_path}',
                    json={'input': request.input_data},
                    headers=self._get_headers()
                )
                response.raise_for_status()

                data = response.json()
                result = data.get('result', {})

                # Tratar diferentes tipos de resultado OPA
                # OPA pode retornar: booleano, lista, ou dicionario
                if isinstance(result, bool):
                    # Resultado booleano direto (ex: policy/allow retorna true/false)
                    allow = result
                    raw_violations = []
                elif isinstance(result, list):
                    # Resultado lista (ex: policy/violations retorna lista de violacoes)
                    allow = False
                    raw_violations = result
                elif isinstance(result, dict):
                    # Resultado dicionario padrao (ex: {allow: bool, violations: []})
                    allow = result.get('allow', False)
                    raw_violations = result.get('violations', [])
                else:
                    # Fallback para qualquer outro tipo
                    self.logger.warning(
                        'opa_unexpected_result_type',
                        policy_path=policy_path,
                        result_type=type(result).__name__
                    )
                    allow = False
                    raw_violations = []

                # Parsear violacoes
                violations = self._parse_violations(raw_violations)

                span.set_attribute('opa.allow', allow)
                span.set_attribute('opa.violations_count', len(violations))

                self.logger.info(
                    'opa_policy_evaluated',
                    policy_path=policy_path,
                    allow=allow,
                    violations_count=len(violations)
                )

                return PolicyEvaluationResponse(
                    allow=allow,
                    violations=violations,
                    decision=request.decision,
                    metadata={
                        'policy_path': policy_path,
                        'raw_result': result
                    }
                )

            except httpx.HTTPStatusError as e:
                self.logger.error(
                    'opa_evaluate_failed',
                    policy_path=policy_path,
                    status_code=e.response.status_code,
                    error=str(e)
                )
                span.set_attribute('opa.error', str(e))
                span.set_attribute('opa.status_code', e.response.status_code)
                raise OPAAPIError(
                    f'Falha ao avaliar politica {policy_path}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException as e:
                self.logger.error('opa_evaluate_timeout', policy_path=policy_path)
                span.set_attribute('opa.error', 'timeout')
                raise OPATimeoutError(f'Timeout ao avaliar politica {policy_path}')

    async def evaluate_policy_batch(
        self,
        requests: List[PolicyEvaluationRequest]
    ) -> List[PolicyEvaluationResponse]:
        """
        Avalia multiplas politicas em lote.

        Args:
            requests: Lista de requisicoes de avaliacao

        Returns:
            Lista de respostas de avaliacao
        """
        with tracer.start_as_current_span('opa.evaluate_policy_batch') as span:
            span.set_attribute('opa.batch_size', len(requests))

            self.logger.info('opa_evaluate_batch', batch_size=len(requests))

            tasks = [self.evaluate_policy(req) for req in requests]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            responses = []
            errors = []

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    errors.append((i, result))
                    # Criar resposta de erro
                    responses.append(PolicyEvaluationResponse(
                        allow=False,
                        violations=[Violation(
                            rule_id='opa_error',
                            message=str(result),
                            severity=ViolationSeverity.HIGH
                        )],
                        metadata={'error': str(result)}
                    ))
                else:
                    responses.append(result)

            if errors:
                self.logger.warning(
                    'opa_batch_partial_failure',
                    total=len(requests),
                    errors=len(errors)
                )

            return responses

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException))
    )
    async def get_bundle_status(self, bundle_name: str) -> BundleStatus:
        """
        Obtem status de um bundle OPA.

        Args:
            bundle_name: Nome do bundle

        Returns:
            Status do bundle

        Raises:
            OPAAPIError: Erro na API
        """
        with tracer.start_as_current_span('opa.get_bundle_status') as span:
            span.set_attribute('opa.bundle_name', bundle_name)

            try:
                response = await self.client.get(
                    f'{self.base_url}/v1/status/bundles/{bundle_name}',
                    headers=self._get_headers()
                )
                response.raise_for_status()

                data = response.json()
                result = data.get('result', {})

                return BundleStatus(
                    name=bundle_name,
                    active_revision=result.get('active_revision', ''),
                    last_successful_activation=result.get('last_successful_activation', '')
                )

            except httpx.HTTPStatusError as e:
                self.logger.error(
                    'opa_bundle_status_failed',
                    bundle_name=bundle_name,
                    status_code=e.response.status_code
                )
                raise OPAAPIError(
                    f'Falha ao obter status do bundle {bundle_name}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException:
                raise OPATimeoutError(f'Timeout ao obter status do bundle {bundle_name}')

    async def wait_for_bundle_activation(
        self,
        bundle_name: str,
        poll_interval: int = 5,
        timeout: int = 300
    ) -> BundleStatus:
        """
        Aguarda ativacao de um bundle via polling.

        Args:
            bundle_name: Nome do bundle
            poll_interval: Intervalo entre verificacoes em segundos
            timeout: Timeout total em segundos

        Returns:
            Status final do bundle

        Raises:
            OPATimeoutError: Timeout aguardando ativacao
        """
        with tracer.start_as_current_span('opa.wait_for_bundle_activation') as span:
            span.set_attribute('opa.bundle_name', bundle_name)
            span.set_attribute('opa.timeout', timeout)

            self.logger.info(
                'opa_waiting_for_bundle',
                bundle_name=bundle_name,
                timeout=timeout
            )

            start_time = asyncio.get_event_loop().time()

            while True:
                status = await self.get_bundle_status(bundle_name)

                if status.active_revision:
                    self.logger.info(
                        'opa_bundle_active',
                        bundle_name=bundle_name,
                        revision=status.active_revision
                    )
                    return status

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    self.logger.warning(
                        'opa_bundle_activation_timeout',
                        bundle_name=bundle_name,
                        elapsed=elapsed
                    )
                    raise OPATimeoutError(
                        f'Timeout aguardando ativacao do bundle {bundle_name}'
                    )

                await asyncio.sleep(poll_interval)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException))
    )
    async def query_data(self, path: str) -> Dict[str, Any]:
        """
        Query generico para dados no OPA.

        Args:
            path: Caminho para query (ex: data/policies)

        Returns:
            Dados retornados pelo OPA

        Raises:
            OPAAPIError: Erro na API
        """
        with tracer.start_as_current_span('opa.query_data') as span:
            path = path.lstrip('/')
            span.set_attribute('opa.query_path', path)

            try:
                response = await self.client.get(
                    f'{self.base_url}/v1/data/{path}',
                    headers=self._get_headers()
                )
                response.raise_for_status()

                data = response.json()
                return data.get('result', {})

            except httpx.HTTPStatusError as e:
                self.logger.error(
                    'opa_query_failed',
                    path=path,
                    status_code=e.response.status_code
                )
                raise OPAAPIError(
                    f'Falha ao consultar {path}: {e}',
                    status_code=e.response.status_code
                )
            except httpx.TimeoutException:
                raise OPATimeoutError(f'Timeout ao consultar {path}')

    async def health_check(self) -> bool:
        """
        Verifica se o OPA esta saudavel.

        Returns:
            True se OPA esta respondendo
        """
        try:
            response = await self.client.get(
                f'{self.base_url}/health',
                headers=self._get_headers()
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.warning('opa_health_check_failed', error=str(e))
            return False

    def _parse_violations(self, raw_violations: Any) -> List[Violation]:
        """
        Parseia violacoes brutas do OPA para modelo estruturado.

        Args:
            raw_violations: Violacoes em formato raw do OPA

        Returns:
            Lista de violacoes parseadas
        """
        violations = []

        if not raw_violations:
            return violations

        # Handle lista de violacoes
        if isinstance(raw_violations, list):
            for item in raw_violations:
                violation = self._parse_single_violation(item)
                if violation:
                    violations.append(violation)

        # Handle dicionario de violacoes
        elif isinstance(raw_violations, dict):
            for key, value in raw_violations.items():
                if isinstance(value, list):
                    for item in value:
                        violation = self._parse_single_violation(item, default_rule_id=key)
                        if violation:
                            violations.append(violation)
                else:
                    violation = self._parse_single_violation(value, default_rule_id=key)
                    if violation:
                        violations.append(violation)

        return violations

    def _parse_single_violation(
        self,
        item: Any,
        default_rule_id: str = 'unknown'
    ) -> Optional[Violation]:
        """
        Parseia uma unica violacao.

        Args:
            item: Item de violacao bruto
            default_rule_id: Rule ID padrao se nao especificado

        Returns:
            Violacao parseada ou None
        """
        if isinstance(item, str):
            return Violation(
                rule_id=default_rule_id,
                message=item,
                severity=self._classify_severity(item)
            )

        if isinstance(item, dict):
            rule_id = (
                item.get('rule_id') or
                item.get('id') or
                item.get('check_id') or
                item.get('rule') or
                default_rule_id
            )

            message = (
                item.get('message') or
                item.get('msg') or
                item.get('description') or
                item.get('reason') or
                str(item)
            )

            # Extrair severidade do item
            raw_severity = (
                item.get('severity') or
                item.get('level') or
                item.get('priority') or
                'MEDIUM'
            )
            severity = self._normalize_severity(raw_severity)

            return Violation(
                rule_id=str(rule_id),
                message=str(message),
                severity=severity,
                resource=item.get('resource') or item.get('target'),
                location=item.get('location') or item.get('pos')
            )

        return None

    def _classify_severity(self, message: str) -> ViolationSeverity:
        """
        Classifica severidade com base na mensagem.

        Args:
            message: Mensagem de violacao

        Returns:
            Severidade inferida
        """
        message_lower = message.lower()

        critical_keywords = ['critical', 'fatal', 'severe', 'emergency', 'breach']
        high_keywords = ['high', 'error', 'danger', 'fail', 'block']
        low_keywords = ['low', 'minor', 'trivial', 'cosmetic']
        info_keywords = ['info', 'notice', 'suggestion', 'hint']

        for keyword in critical_keywords:
            if keyword in message_lower:
                return ViolationSeverity.CRITICAL

        for keyword in high_keywords:
            if keyword in message_lower:
                return ViolationSeverity.HIGH

        for keyword in low_keywords:
            if keyword in message_lower:
                return ViolationSeverity.LOW

        for keyword in info_keywords:
            if keyword in message_lower:
                return ViolationSeverity.INFO

        return ViolationSeverity.MEDIUM

    def _normalize_severity(self, raw_severity: Any) -> ViolationSeverity:
        """
        Normaliza severidade para enum padrao.

        Args:
            raw_severity: Severidade em formato variado

        Returns:
            Severidade normalizada
        """
        if isinstance(raw_severity, ViolationSeverity):
            return raw_severity

        severity_str = str(raw_severity).upper().strip()

        severity_mapping = {
            'CRITICAL': ViolationSeverity.CRITICAL,
            'CRIT': ViolationSeverity.CRITICAL,
            'FATAL': ViolationSeverity.CRITICAL,
            'EMERGENCY': ViolationSeverity.CRITICAL,
            'HIGH': ViolationSeverity.HIGH,
            'ERROR': ViolationSeverity.HIGH,
            'DANGER': ViolationSeverity.HIGH,
            'MEDIUM': ViolationSeverity.MEDIUM,
            'MED': ViolationSeverity.MEDIUM,
            'WARNING': ViolationSeverity.MEDIUM,
            'WARN': ViolationSeverity.MEDIUM,
            'LOW': ViolationSeverity.LOW,
            'MINOR': ViolationSeverity.LOW,
            'INFO': ViolationSeverity.INFO,
            'INFORMATIONAL': ViolationSeverity.INFO,
            'NOTICE': ViolationSeverity.INFO,
        }

        return severity_mapping.get(severity_str, ViolationSeverity.MEDIUM)

    def count_violations_by_severity(
        self,
        violations: List[Violation]
    ) -> Dict[ViolationSeverity, int]:
        """
        Conta violacoes por severidade.

        Args:
            violations: Lista de violacoes

        Returns:
            Contagem por severidade
        """
        counts = {severity: 0 for severity in ViolationSeverity}
        for violation in violations:
            counts[violation.severity] += 1
        return counts
