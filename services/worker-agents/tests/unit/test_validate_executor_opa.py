"""
Testes unitarios para ValidateExecutor com integracao OPA.

Cobertura:
- Execucao OPA com cliente dedicado (_execute_opa_with_client)
- Execucao OPA legacy (_execute_opa_legacy)
- Fallback conservador (_execute_opa_fallback)
- Tratamento de diferentes tipos de resultado OPA
- Metricas de violacoes
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


@pytest.fixture
def mock_opa_client():
    """Mock OPAClient para testes."""
    from services.worker_agents.src.clients.opa_client import (
        PolicyEvaluationResponse,
        Violation,
        ViolationSeverity
    )

    client = MagicMock()
    client.evaluate_policy = AsyncMock()
    client.count_violations_by_severity = MagicMock(return_value={
        ViolationSeverity.CRITICAL: 0,
        ViolationSeverity.HIGH: 0,
        ViolationSeverity.MEDIUM: 0,
        ViolationSeverity.LOW: 0,
        ViolationSeverity.INFO: 0,
    })
    return client


@pytest.fixture
def mock_metrics_with_policy_violations():
    """Mock metrics com policy_violations_total."""
    metrics = MagicMock()

    # Validate metrics
    metrics.validate_tasks_executed_total = MagicMock()
    metrics.validate_tasks_executed_total.labels.return_value.inc = MagicMock()
    metrics.validate_duration_seconds = MagicMock()
    metrics.validate_duration_seconds.labels.return_value.observe = MagicMock()
    metrics.validate_violations_total = MagicMock()
    metrics.validate_violations_total.labels.return_value.inc = MagicMock()
    metrics.validate_tools_executed_total = MagicMock()
    metrics.validate_tools_executed_total.labels.return_value.inc = MagicMock()

    # OPA metrics
    metrics.opa_api_calls_total = MagicMock()
    metrics.opa_api_calls_total.labels.return_value.inc = MagicMock()
    metrics.opa_policy_evaluation_duration_seconds = MagicMock()
    metrics.opa_policy_evaluation_duration_seconds.labels.return_value.observe = MagicMock()

    # Nova metrica policy_violations_total
    metrics.policy_violations_total = MagicMock()
    metrics.policy_violations_total.labels.return_value.inc = MagicMock()

    return metrics


@pytest.fixture
def validate_executor_with_opa_client(worker_config, mock_opa_client, mock_metrics_with_policy_violations):
    """ValidateExecutor com OPAClient injetado."""
    from services.worker_agents.src.executors.validate_executor import ValidateExecutor

    executor = ValidateExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics_with_policy_violations,
        opa_client=mock_opa_client
    )
    return executor


@pytest.fixture
def validate_ticket_opa():
    """Ticket de validacao OPA."""
    import uuid
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'policy',
            'policy_path': 'policy/allow',
            'input_data': {'user': 'admin', 'action': 'read'},
        },
    }


class TestExecuteOPAWithClient:
    """Testes de _execute_opa_with_client."""

    @pytest.mark.asyncio
    async def test_execute_opa_success(self, validate_executor_with_opa_client, mock_opa_client, validate_ticket_opa):
        """Deve executar validacao OPA com sucesso."""
        from services.worker_agents.src.clients.opa_client import (
            PolicyEvaluationResponse,
            ViolationSeverity
        )

        mock_opa_client.evaluate_policy.return_value = PolicyEvaluationResponse(
            allow=True,
            violations=[],
            metadata={'policy_path': 'policy/allow'}
        )
        mock_opa_client.count_violations_by_severity.return_value = {
            ViolationSeverity.CRITICAL: 0,
            ViolationSeverity.HIGH: 0,
            ViolationSeverity.MEDIUM: 0,
            ViolationSeverity.LOW: 0,
            ViolationSeverity.INFO: 0,
        }

        result = await validate_executor_with_opa_client.execute(validate_ticket_opa)

        assert result['success'] is True
        assert result['output']['validation_passed'] is True
        assert result['output']['violations'] == []
        assert result['metadata']['client_type'] == 'dedicated'

    @pytest.mark.asyncio
    async def test_execute_opa_with_violations(self, validate_executor_with_opa_client, mock_opa_client, validate_ticket_opa):
        """Deve retornar violacoes quando politica falha."""
        from services.worker_agents.src.clients.opa_client import (
            PolicyEvaluationResponse,
            Violation,
            ViolationSeverity
        )

        violations = [
            Violation(
                rule_id='auth_required',
                message='Authentication required',
                severity=ViolationSeverity.HIGH
            )
        ]
        mock_opa_client.evaluate_policy.return_value = PolicyEvaluationResponse(
            allow=False,
            violations=violations,
            metadata={'policy_path': 'policy/allow'}
        )
        mock_opa_client.count_violations_by_severity.return_value = {
            ViolationSeverity.CRITICAL: 0,
            ViolationSeverity.HIGH: 1,
            ViolationSeverity.MEDIUM: 0,
            ViolationSeverity.LOW: 0,
            ViolationSeverity.INFO: 0,
        }

        result = await validate_executor_with_opa_client.execute(validate_ticket_opa)

        assert result['success'] is False
        assert result['output']['validation_passed'] is False
        assert len(result['output']['violations']) == 1
        assert result['output']['violations'][0]['rule_id'] == 'auth_required'

    @pytest.mark.asyncio
    async def test_execute_opa_timeout_fallback(self, validate_executor_with_opa_client, mock_opa_client, validate_ticket_opa):
        """Deve usar fallback conservador em timeout."""
        from services.worker_agents.src.clients.opa_client import OPATimeoutError

        mock_opa_client.evaluate_policy.side_effect = OPATimeoutError('Connection timeout')

        result = await validate_executor_with_opa_client.execute(validate_ticket_opa)

        # Fallback conservador retorna falha
        assert result['success'] is False
        assert result['output']['validation_passed'] is False
        assert result['metadata']['conservative_failure'] is True

    @pytest.mark.asyncio
    async def test_execute_opa_api_error_fallback(self, validate_executor_with_opa_client, mock_opa_client, validate_ticket_opa):
        """Deve usar fallback conservador em erro de API."""
        from services.worker_agents.src.clients.opa_client import OPAAPIError

        mock_opa_client.evaluate_policy.side_effect = OPAAPIError('Server error', status_code=500)

        result = await validate_executor_with_opa_client.execute(validate_ticket_opa)

        # Fallback conservador retorna falha
        assert result['success'] is False
        assert result['output']['validation_passed'] is False
        assert result['metadata']['conservative_failure'] is True


class TestExecuteOPALegacy:
    """Testes de _execute_opa_legacy."""

    @pytest.fixture
    def validate_executor_legacy(self, worker_config, mock_metrics_with_policy_violations):
        """ValidateExecutor sem OPAClient (modo legacy)."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.opa_url = 'http://opa.test:8181'
        worker_config.opa_enabled = True

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=None,
            code_forge_client=None,
            metrics=mock_metrics_with_policy_violations,
            opa_client=None  # Sem cliente dedicado, usa legacy
        )
        return executor

    @pytest.mark.asyncio
    async def test_legacy_dict_result(self, validate_executor_legacy, validate_ticket_opa):
        """Deve tratar resultado dicionario no modo legacy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': {
                'allow': True,
                'violations': []
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await validate_executor_legacy.execute(validate_ticket_opa)

            assert result['success'] is True
            assert result['output']['validation_passed'] is True
            assert result['metadata']['client_type'] == 'legacy'

    @pytest.mark.asyncio
    async def test_legacy_boolean_true_result(self, validate_executor_legacy, validate_ticket_opa):
        """Deve tratar resultado booleano true no modo legacy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': True}
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await validate_executor_legacy.execute(validate_ticket_opa)

            assert result['success'] is True
            assert result['output']['validation_passed'] is True

    @pytest.mark.asyncio
    async def test_legacy_boolean_false_result(self, validate_executor_legacy, validate_ticket_opa):
        """Deve tratar resultado booleano false no modo legacy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': False}
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await validate_executor_legacy.execute(validate_ticket_opa)

            assert result['success'] is False
            assert result['output']['validation_passed'] is False

    @pytest.mark.asyncio
    async def test_legacy_list_result(self, validate_executor_legacy, validate_ticket_opa):
        """Deve tratar resultado lista como violacoes no modo legacy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'result': [
                {'rule_id': 'rule1', 'message': 'Error 1'},
                {'rule_id': 'rule2', 'message': 'Error 2'}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await validate_executor_legacy.execute(validate_ticket_opa)

            assert result['success'] is False
            assert result['output']['validation_passed'] is False
            assert len(result['output']['violations']) == 2

    @pytest.mark.asyncio
    async def test_legacy_error_fallback(self, validate_executor_legacy, validate_ticket_opa):
        """Deve usar fallback conservador em erro no modo legacy."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError('Connection refused')
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await validate_executor_legacy.execute(validate_ticket_opa)

            # Fallback conservador retorna falha
            assert result['success'] is False
            assert result['output']['validation_passed'] is False


class TestOPAFallback:
    """Testes de _execute_opa_fallback."""

    @pytest.mark.asyncio
    async def test_fallback_returns_conservative_failure(self, validate_executor_with_opa_client):
        """Deve retornar falha conservadora."""
        result = await validate_executor_with_opa_client._execute_opa_fallback(
            ticket_id='test-123',
            policy_path='policy/allow',
            reason='timeout'
        )

        assert result['success'] is False
        assert result['output']['validation_passed'] is False
        assert len(result['output']['violations']) == 1
        assert result['output']['violations'][0]['rule_id'] == 'opa_unavailable'
        assert result['metadata']['conservative_failure'] is True
        assert 'OPA unavailable' in result['logs'][1]

    @pytest.mark.asyncio
    async def test_fallback_includes_reason(self, validate_executor_with_opa_client):
        """Deve incluir motivo do fallback."""
        result = await validate_executor_with_opa_client._execute_opa_fallback(
            ticket_id='test-123',
            policy_path='policy/allow',
            reason='api_error'
        )

        assert result['output']['fallback_reason'] == 'api_error'
        assert result['metadata']['fallback_reason'] == 'api_error'


class TestRecordOPAViolationMetrics:
    """Testes de _record_opa_violation_metrics."""

    def test_record_metrics_with_violations(self, validate_executor_with_opa_client, mock_metrics_with_policy_violations):
        """Deve registrar metricas para violacoes."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity

        severity_counts = {
            ViolationSeverity.CRITICAL: 1,
            ViolationSeverity.HIGH: 2,
            ViolationSeverity.MEDIUM: 0,
            ViolationSeverity.LOW: 1,
            ViolationSeverity.INFO: 0,
        }

        validate_executor_with_opa_client._record_opa_violation_metrics(severity_counts)

        # Verifica que validate_violations_total foi chamado
        calls = mock_metrics_with_policy_violations.validate_violations_total.labels.call_args_list
        assert len(calls) == 3  # CRITICAL, HIGH, LOW (os que tem count > 0)

        # Verifica que policy_violations_total foi chamado
        policy_calls = mock_metrics_with_policy_violations.policy_violations_total.labels.call_args_list
        assert len(policy_calls) == 3

    def test_record_metrics_no_violations(self, validate_executor_with_opa_client, mock_metrics_with_policy_violations):
        """Nao deve registrar metricas sem violacoes."""
        from services.worker_agents.src.clients.opa_client import ViolationSeverity

        severity_counts = {
            ViolationSeverity.CRITICAL: 0,
            ViolationSeverity.HIGH: 0,
            ViolationSeverity.MEDIUM: 0,
            ViolationSeverity.LOW: 0,
            ViolationSeverity.INFO: 0,
        }

        validate_executor_with_opa_client._record_opa_violation_metrics(severity_counts)

        # Nenhuma metrica deve ser registrada
        mock_metrics_with_policy_violations.validate_violations_total.labels.assert_not_called()
        mock_metrics_with_policy_violations.policy_violations_total.labels.assert_not_called()

    def test_record_metrics_without_metrics_instance(self, worker_config):
        """Nao deve falhar sem instancia de metricas."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor
        from services.worker_agents.src.clients.opa_client import ViolationSeverity

        executor = ValidateExecutor(
            config=worker_config,
            metrics=None  # Sem metricas
        )

        severity_counts = {
            ViolationSeverity.HIGH: 1,
        }

        # Nao deve lancar excecao
        executor._record_opa_violation_metrics(severity_counts)
