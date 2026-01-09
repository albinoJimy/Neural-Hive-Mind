"""
Testes unitarios para OPAClient.

Cobertura:
- Avaliacao de politica com sucesso
- Parsing de violacoes
- Tratamento de resultados booleanos
- Tratamento de resultados lista
- Timeout
- Erros de API
- Retry logic
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


@pytest.fixture
def opa_client():
    """Fixture para OPAClient."""
    from services.worker_agents.src.clients.opa_client import OPAClient
    return OPAClient(
        base_url='http://opa.test:8181',
        token='test-token',
        timeout=30,
        verify_ssl=True,
        retry_attempts=3,
        retry_backoff_base=1,
        retry_backoff_max=5
    )


@pytest.fixture
def policy_request():
    """Fixture para PolicyEvaluationRequest."""
    from services.worker_agents.src.clients.opa_client import PolicyEvaluationRequest
    return PolicyEvaluationRequest(
        policy_path='policy/allow',
        input_data={'user': 'admin', 'action': 'read'},
        decision=None
    )


class TestOPAClientInit:
    """Testes de inicializacao do cliente."""

    def test_init_with_token(self):
        """Deve inicializar com token."""
        from services.worker_agents.src.clients.opa_client import OPAClient
        client = OPAClient(
            base_url='http://opa.test:8181',
            token='my-token',
            timeout=60
        )
        assert client.base_url == 'http://opa.test:8181'
        assert client.token == 'my-token'
        assert client.timeout == 60

    def test_init_without_token(self):
        """Deve inicializar sem token."""
        from services.worker_agents.src.clients.opa_client import OPAClient
        client = OPAClient(
            base_url='http://opa.test:8181',
            timeout=30
        )
        assert client.base_url == 'http://opa.test:8181'
        assert client.token is None

    def test_init_strips_trailing_slash(self):
        """Deve remover barra final da URL."""
        from services.worker_agents.src.clients.opa_client import OPAClient
        client = OPAClient(
            base_url='http://opa.test:8181/',
            timeout=30
        )
        assert client.base_url == 'http://opa.test:8181'

    def test_get_headers_with_token(self, opa_client):
        """Deve incluir header Authorization com token."""
        headers = opa_client._get_headers()
        assert headers['Content-Type'] == 'application/json'
        assert headers['Authorization'] == 'Bearer test-token'

    def test_get_headers_without_token(self):
        """Deve retornar headers sem Authorization sem token."""
        from services.worker_agents.src.clients.opa_client import OPAClient
        client = OPAClient(base_url='http://opa.test:8181', timeout=30)
        headers = client._get_headers()
        assert headers['Content-Type'] == 'application/json'
        assert 'Authorization' not in headers


class TestEvaluatePolicy:
    """Testes de avaliacao de politica."""

    @pytest.mark.asyncio
    async def test_evaluate_policy_success_dict_result(self, opa_client, policy_request):
        """Deve avaliar politica com sucesso (resultado dicionario)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': {
                'allow': True,
                'violations': []
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await opa_client.evaluate_policy(policy_request)

            assert result.allow is True
            assert len(result.violations) == 0
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_policy_success_boolean_result(self, opa_client, policy_request):
        """Deve tratar resultado booleano corretamente."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': True}
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await opa_client.evaluate_policy(policy_request)

            assert result.allow is True
            assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_evaluate_policy_success_boolean_false(self, opa_client, policy_request):
        """Deve tratar resultado booleano false corretamente."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': False}
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await opa_client.evaluate_policy(policy_request)

            assert result.allow is False
            assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_evaluate_policy_success_list_result(self, opa_client, policy_request):
        """Deve tratar resultado lista como violacoes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': [
                {'rule_id': 'rule1', 'message': 'Violation 1'},
                {'rule_id': 'rule2', 'message': 'Violation 2'}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await opa_client.evaluate_policy(policy_request)

            assert result.allow is False
            assert len(result.violations) == 2
            assert result.violations[0].rule_id == 'rule1'
            assert result.violations[1].rule_id == 'rule2'

    @pytest.mark.asyncio
    async def test_evaluate_policy_with_violations(self, opa_client, policy_request):
        """Deve retornar violacoes parseadas."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': {
                'allow': False,
                'violations': [
                    {
                        'rule_id': 'auth_required',
                        'message': 'Authentication required',
                        'severity': 'HIGH'
                    },
                    {
                        'rule_id': 'rate_limit',
                        'message': 'Rate limit exceeded',
                        'severity': 'MEDIUM'
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(opa_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await opa_client.evaluate_policy(policy_request)

            assert result.allow is False
            assert len(result.violations) == 2
            assert result.violations[0].rule_id == 'auth_required'
            assert result.violations[0].severity.value == 'HIGH'

    @pytest.mark.asyncio
    async def test_evaluate_policy_timeout(self, opa_client, policy_request):
        """Deve lancar OPATimeoutError em timeout."""
        from services.worker_agents.src.clients.opa_client import OPATimeoutError

        with patch.object(opa_client.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException('Connection timeout')

            with pytest.raises(OPATimeoutError):
                await opa_client.evaluate_policy(policy_request)

    @pytest.mark.asyncio
    async def test_evaluate_policy_api_error(self, opa_client, policy_request):
        """Deve lancar OPAAPIError em erro HTTP."""
        from services.worker_agents.src.clients.opa_client import OPAAPIError

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(opa_client.client, 'post', new_callable=AsyncMock) as mock_post:
            error = httpx.HTTPStatusError(
                'Internal Server Error',
                request=MagicMock(),
                response=mock_response
            )
            mock_post.side_effect = error

            with pytest.raises(OPAAPIError) as exc_info:
                await opa_client.evaluate_policy(policy_request)

            assert exc_info.value.status_code == 500


class TestParseViolations:
    """Testes de parsing de violacoes."""

    def test_parse_violations_empty_list(self, opa_client):
        """Deve retornar lista vazia para input vazio."""
        result = opa_client._parse_violations([])
        assert result == []

    def test_parse_violations_none(self, opa_client):
        """Deve retornar lista vazia para None."""
        result = opa_client._parse_violations(None)
        assert result == []

    def test_parse_violations_string_list(self, opa_client):
        """Deve parsear lista de strings."""
        violations = ['Error 1', 'Error 2']
        result = opa_client._parse_violations(violations)
        assert len(result) == 2
        assert result[0].message == 'Error 1'
        assert result[1].message == 'Error 2'

    def test_parse_violations_dict_list(self, opa_client):
        """Deve parsear lista de dicionarios."""
        violations = [
            {'rule_id': 'rule1', 'message': 'Error 1', 'severity': 'HIGH'},
            {'rule_id': 'rule2', 'message': 'Error 2', 'severity': 'LOW'}
        ]
        result = opa_client._parse_violations(violations)
        assert len(result) == 2
        assert result[0].rule_id == 'rule1'
        assert result[0].severity.value == 'HIGH'
        assert result[1].rule_id == 'rule2'
        assert result[1].severity.value == 'LOW'

    def test_parse_violations_nested_dict(self, opa_client):
        """Deve parsear dicionario com listas de violacoes."""
        violations = {
            'auth': ['Auth error 1', 'Auth error 2'],
            'rate_limit': ['Rate exceeded']
        }
        result = opa_client._parse_violations(violations)
        assert len(result) == 3


class TestClassifySeverity:
    """Testes de classificacao de severidade."""

    def test_classify_severity_critical(self, opa_client):
        """Deve classificar como CRITICAL."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client._classify_severity('Critical security breach detected')
        assert result == ViolationSeverity.CRITICAL

    def test_classify_severity_high(self, opa_client):
        """Deve classificar como HIGH."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client._classify_severity('Error: authentication failed')
        assert result == ViolationSeverity.HIGH

    def test_classify_severity_low(self, opa_client):
        """Deve classificar como LOW."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client._classify_severity('Minor issue detected')
        assert result == ViolationSeverity.LOW

    def test_classify_severity_info(self, opa_client):
        """Deve classificar como INFO."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client._classify_severity('Info: suggestion for improvement')
        assert result == ViolationSeverity.INFO

    def test_classify_severity_default_medium(self, opa_client):
        """Deve retornar MEDIUM como padrao."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client._classify_severity('Some random message')
        assert result == ViolationSeverity.MEDIUM


class TestNormalizeSeverity:
    """Testes de normalizacao de severidade."""

    def test_normalize_severity_already_enum(self, opa_client):
        """Deve retornar enum inalterado."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client._normalize_severity(ViolationSeverity.HIGH)
        assert result == ViolationSeverity.HIGH

    def test_normalize_severity_string(self, opa_client):
        """Deve converter string para enum."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        assert opa_client._normalize_severity('CRITICAL') == ViolationSeverity.CRITICAL
        assert opa_client._normalize_severity('high') == ViolationSeverity.HIGH
        assert opa_client._normalize_severity('Warning') == ViolationSeverity.MEDIUM
        assert opa_client._normalize_severity('MINOR') == ViolationSeverity.LOW

    def test_normalize_severity_unknown(self, opa_client):
        """Deve retornar MEDIUM para valor desconhecido."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client._normalize_severity('UNKNOWN')
        assert result == ViolationSeverity.MEDIUM


class TestCountViolationsBySeverity:
    """Testes de contagem de violacoes por severidade."""

    def test_count_violations_empty(self, opa_client):
        """Deve retornar zeros para lista vazia."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity
        result = opa_client.count_violations_by_severity([])
        assert all(count == 0 for count in result.values())

    def test_count_violations_mixed(self, opa_client):
        """Deve contar violacoes por severidade."""
        from services.worker_agents.src.clients.opa_client import Violation, ViolationSeverity
        violations = [
            Violation(rule_id='r1', message='m1', severity=ViolationSeverity.HIGH),
            Violation(rule_id='r2', message='m2', severity=ViolationSeverity.HIGH),
            Violation(rule_id='r3', message='m3', severity=ViolationSeverity.MEDIUM),
            Violation(rule_id='r4', message='m4', severity=ViolationSeverity.LOW),
        ]
        result = opa_client.count_violations_by_severity(violations)
        assert result[ViolationSeverity.HIGH] == 2
        assert result[ViolationSeverity.MEDIUM] == 1
        assert result[ViolationSeverity.LOW] == 1
        assert result[ViolationSeverity.CRITICAL] == 0


class TestHealthCheck:
    """Testes de health check."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, opa_client):
        """Deve retornar True quando OPA esta saudavel."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(opa_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await opa_client.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, opa_client):
        """Deve retornar False quando OPA esta indisponivel."""
        with patch.object(opa_client.client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.ConnectError('Connection refused')

            result = await opa_client.health_check()

            assert result is False
