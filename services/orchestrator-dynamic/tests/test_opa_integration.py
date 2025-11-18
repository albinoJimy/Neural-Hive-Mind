"""
Testes de integração para validação OPA no orchestrator-dynamic.
"""
import pytest
import asyncio
import pybreaker
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.policies import OPAClient, PolicyValidator
from src.policies.opa_client import OPAConnectionError, OPAPolicyNotFoundError
from src.config.settings import OrchestratorSettings
from src.models.validation import ValidationResult, PolicyViolation


@pytest.fixture
def mock_config():
    """Fixture com configurações mock."""
    config = Mock(spec=OrchestratorSettings)
    config.opa_host = 'localhost'
    config.opa_port = 8181
    config.opa_timeout_seconds = 2
    config.opa_retry_attempts = 3
    config.opa_cache_ttl_seconds = 30
    config.opa_fail_open = False
    config.opa_circuit_breaker_enabled = True
    config.opa_circuit_breaker_failure_threshold = 5
    config.opa_circuit_breaker_reset_timeout = 60
    config.opa_policy_resource_limits = 'neuralhive/orchestrator/resource_limits'
    config.opa_policy_sla_enforcement = 'neuralhive/orchestrator/sla_enforcement'
    config.opa_policy_feature_flags = 'neuralhive/orchestrator/feature_flags'
    config.opa_max_concurrent_tickets = 100
    config.opa_allowed_capabilities = ['code_generation', 'deployment', 'testing', 'validation']
    config.opa_resource_limits = {'max_cpu': '4000m', 'max_memory': '8Gi'}
    return config


@pytest.fixture
def mock_circuit_breaker():
    """Fixture com circuit breaker mock."""
    breaker = Mock(spec=pybreaker.CircuitBreaker)
    breaker.call = Mock(side_effect=lambda fn: fn())
    breaker.state = Mock(name='closed')
    breaker.fail_counter = 0
    breaker.current_state = Mock(name='closed')
    breaker._state = Mock()
    breaker._state.call_succeeded = Mock()
    breaker._state.call_failed = Mock()
    return breaker


@pytest.fixture
async def opa_client_with_breaker(mock_config):
    """Fixture com OPAClient inicializado com circuit breaker."""
    with patch('src.policies.opa_client.CircuitBreaker'):
        client = OPAClient(mock_config)
        await client.initialize()
        yield client
        await client.close()


@pytest.fixture
async def opa_client(mock_config):
    """Fixture com OPAClient inicializado."""
    client = OPAClient(mock_config)
    await client.initialize()
    yield client
    await client.close()


class TestOPAClient:
    """Testes do OPAClient."""

    @pytest.mark.asyncio
    async def test_evaluate_policy_success(self, opa_client):
        """Testa avaliação de política com sucesso."""
        with patch.object(opa_client.session, 'post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'result': {'allow': True, 'violations': []}
            })
            mock_post.return_value.__aenter__.return_value = mock_response

            result = await opa_client.evaluate_policy(
                'neuralhive/orchestrator/resource_limits',
                {'input': {'resource': {'ticket_id': 'test-123'}}}
            )

            assert result['result']['allow'] is True
            assert len(result['result']['violations']) == 0
            assert result['policy_path'] == 'neuralhive/orchestrator/resource_limits'

    @pytest.mark.asyncio
    async def test_evaluate_policy_violation(self, opa_client):
        """Testa avaliação com violação de política."""
        with patch.object(opa_client.session, 'post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'result': {
                    'allow': False,
                    'violations': [{
                        'policy': 'resource_limits',
                        'rule': 'timeout_exceeds_maximum',
                        'severity': 'high',
                        'msg': 'Timeout excedido'
                    }]
                }
            })
            mock_post.return_value.__aenter__.return_value = mock_response

            result = await opa_client.evaluate_policy(
                'neuralhive/orchestrator/resource_limits',
                {'input': {'resource': {'timeout_ms': 999999999}}}
            )

            assert result['result']['allow'] is False
            assert len(result['result']['violations']) == 1
            assert result['result']['violations'][0]['rule'] == 'timeout_exceeds_maximum'
            assert result['policy_path'] == 'neuralhive/orchestrator/resource_limits'

    @pytest.mark.asyncio
    async def test_evaluate_policy_timeout(self, opa_client, mock_config):
        """Testa timeout na avaliação."""
        import asyncio

        with patch.object(opa_client.session, 'post') as mock_post:
            # Simular timeout
            mock_post.side_effect = asyncio.TimeoutError()

            with pytest.raises(Exception) as exc_info:
                await opa_client.evaluate_policy(
                    'neuralhive/orchestrator/resource_limits',
                    {'input': {'resource': {}}}
                )

            assert 'Timeout' in str(exc_info.value) or 'timeout' in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_health_check_success(self, opa_client):
        """Testa health check com sucesso."""
        with patch.object(opa_client.session, 'get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response

            is_healthy = await opa_client.health_check()

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, opa_client):
        """Testa health check com falha."""
        with patch.object(opa_client.session, 'get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 503
            mock_get.return_value.__aenter__.return_value = mock_response

            is_healthy = await opa_client.health_check()

            assert is_healthy is False


class TestPolicyValidator:
    """Testes do PolicyValidator."""

    @pytest.mark.asyncio
    async def test_validate_cognitive_plan_success(self, mock_config):
        """Testa validação de plano cognitivo com sucesso."""
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(return_value=[
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/resource_limits'},
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/sla_enforcement'}
        ])

        validator = PolicyValidator(mock_opa_client, mock_config)

        plan = {
            'plan_id': 'test-plan-1',
            'tasks': [{'task_id': 'task-1'}],
            'execution_order': ['task-1'],
            'namespace': 'production'
        }

        result = await validator.validate_cognitive_plan(plan)

        assert result.valid is True
        assert len(result.violations) == 0
        mock_opa_client.batch_evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_execution_ticket_violation(self, mock_config):
        """Testa validação de ticket com violação."""
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(return_value=[
            {
                'result': {
                    'allow': False,
                    'violations': [{
                        'policy': 'resource_limits',
                        'rule': 'timeout_exceeds_maximum',
                        'severity': 'high',
                        'msg': 'Timeout excedido',
                        'field': 'sla.timeout_ms'
                    }],
                    'warnings': []
                },
                'policy_path': 'neuralhive/orchestrator/resource_limits'
            },
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/sla_enforcement'},
            {'result': {'enable_intelligent_scheduler': True}, 'policy_path': 'neuralhive/orchestrator/feature_flags'}
        ])

        validator = PolicyValidator(mock_opa_client, mock_config)

        ticket = {
            'ticket_id': 'test-ticket-1',
            'risk_band': 'critical',
            'sla': {'timeout_ms': 999999999},
            'namespace': 'production'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert len(result.violations) == 1
        assert result.violations[0].policy_name == 'resource_limits'
        assert result.violations[0].severity == 'high'

    @pytest.mark.asyncio
    async def test_feature_flags_extraction(self, mock_config):
        """Testa extração de feature flags."""
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(return_value=[
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/resource_limits'},
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/sla_enforcement'},
            {
                'result': {
                    'enable_intelligent_scheduler': True,
                    'enable_burst_capacity': False,
                    'enable_predictive_allocation': False
                },
                'policy_path': 'neuralhive/orchestrator/feature_flags'
            }
        ])

        validator = PolicyValidator(mock_opa_client, mock_config)

        ticket = {
            'ticket_id': 'test-ticket-1',
            'namespace': 'production'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is True
        assert 'feature_flags' in result.policy_decisions
        assert result.policy_decisions['feature_flags']['enable_intelligent_scheduler'] is True
        assert result.policy_decisions['feature_flags']['enable_burst_capacity'] is False


class TestPolicyIntegration:
    """Testes de integração end-to-end."""

    @pytest.mark.asyncio
    async def test_c1_validation_with_opa(self, mock_config):
        """Testa integração OPA em C1 (validação de plano)."""
        # Setup
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(return_value=[
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/resource_limits'},
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/sla_enforcement'}
        ])

        validator = PolicyValidator(mock_opa_client, mock_config)

        # Plano cognitivo de exemplo
        plan = {
            'plan_id': 'test-plan-1',
            'tasks': [
                {'task_id': 't1', 'dependencies': []},
                {'task_id': 't2', 'dependencies': ['t1']}
            ],
            'execution_order': ['t1', 't2'],
            'risk_score': 0.3,
            'risk_band': 'medium',
            'namespace': 'production'
        }

        # Executar validação
        result = await validator.validate_cognitive_plan(plan)

        # Verificar resultados
        assert result.valid is True
        assert len(result.violations) == 0
        assert 'resource_limits' in result.policy_decisions
        mock_opa_client.batch_evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_c1_validation_with_opa_violation(self, mock_config):
        """Testa integração OPA em C1 com violação."""
        # Setup
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(return_value=[
            {
                'result': {
                    'allow': False,
                    'violations': [{
                        'policy': 'resource_limits',
                        'rule': 'timeout_exceeds_maximum',
                        'severity': 'high',
                        'msg': 'Timeout excedido',
                        'field': 'tasks[0].timeout_ms'
                    }],
                    'warnings': []
                },
                'policy_path': 'neuralhive/orchestrator/resource_limits'
            },
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/sla_enforcement'}
        ])

        validator = PolicyValidator(mock_opa_client, mock_config)

        plan = {
            'plan_id': 'test-plan-2',
            'tasks': [{'task_id': 't1', 'timeout_ms': 999999999}],
            'execution_order': ['t1'],
            'risk_band': 'critical',
            'namespace': 'production'
        }

        result = await validator.validate_cognitive_plan(plan)

        assert result.valid is False
        assert len(result.violations) == 1
        assert 'resource_limits' in result.violations[0].policy_name

    @pytest.mark.asyncio
    async def test_c3_allocation_with_opa(self, mock_config):
        """Testa integração OPA em C3 (alocação de recursos)."""
        # Setup
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(return_value=[
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/resource_limits'},
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/sla_enforcement'},
            {
                'result': {
                    'enable_intelligent_scheduler': True,
                    'enable_burst_capacity': False
                },
                'policy_path': 'neuralhive/orchestrator/feature_flags'
            }
        ])

        validator = PolicyValidator(mock_opa_client, mock_config)

        # Ticket de exemplo
        ticket = {
            'ticket_id': 'test-ticket-1',
            'risk_band': 'high',
            'sla': {
                'timeout_ms': 60000,
                'deadline': int((datetime.now() + timedelta(hours=1)).timestamp() * 1000),
                'max_retries': 3
            },
            'qos': {'delivery_mode': 'EXACTLY_ONCE', 'consistency': 'STRONG'},
            'required_capabilities': ['code_generation'],
            'estimated_duration_ms': 30000,
            'namespace': 'production'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is True
        assert 'feature_flags' in result.policy_decisions
        assert result.policy_decisions['feature_flags']['enable_intelligent_scheduler'] is True

    @pytest.mark.asyncio
    async def test_c3_allocation_with_opa_rejection(self, mock_config):
        """Testa integração OPA em C3 com rejeição."""
        # Setup
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(return_value=[
            {'result': {'allow': True, 'violations': [], 'warnings': []}, 'policy_path': 'neuralhive/orchestrator/resource_limits'},
            {
                'result': {
                    'allow': False,
                    'violations': [{
                        'policy': 'sla_enforcement',
                        'rule': 'deadline_in_past',
                        'severity': 'critical',
                        'msg': 'Deadline no passado',
                        'field': 'sla.deadline'
                    }],
                    'warnings': []
                },
                'policy_path': 'neuralhive/orchestrator/sla_enforcement'
            },
            {'result': {'enable_intelligent_scheduler': True}, 'policy_path': 'neuralhive/orchestrator/feature_flags'}
        ])

        validator = PolicyValidator(mock_opa_client, mock_config)

        # Ticket com deadline no passado
        ticket = {
            'ticket_id': 'test-ticket-2',
            'risk_band': 'critical',
            'sla': {
                'timeout_ms': 60000,
                'deadline': int((datetime.now() - timedelta(hours=1)).timestamp() * 1000),
                'max_retries': 5
            },
            'namespace': 'production'
        }

        result = await validator.validate_execution_ticket(ticket)

        assert result.valid is False
        assert len(result.violations) == 1
        assert result.violations[0].severity == 'critical'


class TestCircuitBreaker:
    """Testes do circuit breaker."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, mock_config):
        """Testa abertura do circuit breaker após falhas consecutivas."""
        import aiohttp

        client = OPAClient(mock_config)
        await client.initialize()

        # Simular 5 falhas consecutivas (atingindo o threshold de 5)
        with patch.object(client, '_evaluate_policy_internal', side_effect=OPAConnectionError("Connection failed")):
            for i in range(5):
                try:
                    await client.evaluate_policy('test/policy', {'input': {}})
                except OPAConnectionError:
                    pass  # Esperado durante as 5 primeiras falhas

        # Verificar que o circuit breaker abriu após 5 falhas
        state = client.get_circuit_breaker_state()
        assert state['enabled'] is True
        assert state['state'] == 'open', f"Circuit breaker deveria estar 'open', mas está '{state['state']}'"
        assert state['failure_count'] == 5

        # 6ª chamada deve falhar imediatamente com circuit breaker open
        with pytest.raises(OPAConnectionError) as exc_info:
            await client.evaluate_policy('test/policy', {'input': {}})

        # Verificar mensagem de circuit breaker aberto
        assert 'circuit breaker aberto' in str(exc_info.value).lower()

        await client.close()

    @pytest.mark.asyncio
    async def test_circuit_breaker_excludes_404(self, mock_config):
        """Testa que 404s não abrem o circuit breaker."""
        client = OPAClient(mock_config)
        await client.initialize()

        # Capturar failure_count inicial
        initial_state = client.get_circuit_breaker_state()
        initial_failure_count = initial_state['failure_count']

        # Simular 10 erros 404 (esses devem ser excluídos pelo circuit breaker)
        with patch.object(client, '_evaluate_policy_internal', side_effect=OPAPolicyNotFoundError("Policy not found")):
            for i in range(10):
                try:
                    await client.evaluate_policy('test/policy', {'input': {}})
                except OPAPolicyNotFoundError:
                    pass

        # Circuit breaker deve permanecer fechado e failure_count não deve aumentar
        state = client.get_circuit_breaker_state()
        assert state['enabled'] is True
        assert state['state'] == 'closed', f"Circuit breaker deveria estar 'closed', mas está '{state['state']}'"
        assert state['failure_count'] == initial_failure_count, \
            f"Failure count aumentou de {initial_failure_count} para {state['failure_count']} com erros 404 (deveria ser excluído)"

        await client.close()

    @pytest.mark.asyncio
    async def test_circuit_breaker_disabled(self, mock_config):
        """Testa comportamento com circuit breaker desabilitado."""
        import aiohttp

        mock_config.opa_circuit_breaker_enabled = False
        client = OPAClient(mock_config)
        await client.initialize()

        # Simular 10 falhas - todas devem tentar normalmente
        with patch.object(client, '_evaluate_policy_internal', side_effect=aiohttp.ClientError("Connection failed")):
            for i in range(10):
                try:
                    await client.evaluate_policy('test/policy', {'input': {}})
                except OPAConnectionError:
                    pass  # Esperado

        # Circuit breaker está desabilitado
        state = client.get_circuit_breaker_state()
        assert state['enabled'] is False
        await client.close()

    @pytest.mark.asyncio
    async def test_circuit_breaker_metrics_recorded(self, mock_config):
        """Testa que métricas do circuit breaker são registradas."""
        client = OPAClient(mock_config)
        await client.initialize()

        with patch.object(client.metrics, 'record_opa_circuit_breaker_state') as mock_metric:
            # Simular mudança de estado
            client._on_circuit_breaker_state_change(
                client._circuit_breaker,
                Mock(name='closed'),
                Mock(name='open')
            )

            # Verificar que métrica foi chamada
            mock_metric.assert_called()

        await client.close()

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_state(self, mock_config):
        """Testa obtenção do estado do circuit breaker."""
        client = OPAClient(mock_config)
        await client.initialize()

        state = client.get_circuit_breaker_state()

        assert 'enabled' in state
        assert 'state' in state
        assert 'failure_count' in state
        assert 'last_failure_time' in state
        assert state['enabled'] is True

        await client.close()


class TestBatchValidation:
    """Testes de validação em batch."""

    @pytest.mark.asyncio
    async def test_batch_validate_multiple_tickets(self, mock_config):
        """Testa validação em batch de múltiplos tickets."""
        mock_opa_client = AsyncMock()

        # Simular 10 tickets
        tickets = [{'ticket_id': f'ticket-{i}'} for i in range(10)]
        mock_results = [
            {'result': {'allow': True, 'violations': []}, 'policy_path': 'test/policy'}
            for _ in range(10)
        ]

        mock_opa_client.batch_evaluate = AsyncMock(return_value=mock_results)

        # Executar batch
        evaluations = [('test/policy', {'input': ticket}) for ticket in tickets]
        results = await mock_opa_client.batch_evaluate(evaluations)

        assert len(results) == 10
        assert all(r['result']['allow'] is True for r in results)

    @pytest.mark.asyncio
    async def test_batch_validate_preserves_order(self, opa_client):
        """Testa que batch validation preserva ordem."""
        tickets = [
            {'ticket_id': 't1'},
            {'ticket_id': 't2'},
            {'ticket_id': 't3'}
        ]

        evaluations = [('test/policy', {'input': ticket}) for ticket in tickets]

        with patch.object(opa_client, 'evaluate_policy') as mock_eval:
            mock_eval.side_effect = [
                {'result': {'allow': True}, 'policy_path': 'test/policy', 'input_id': 't1'},
                {'result': {'allow': True}, 'policy_path': 'test/policy', 'input_id': 't2'},
                {'result': {'allow': True}, 'policy_path': 'test/policy', 'input_id': 't3'}
            ]

            results = await opa_client.batch_evaluate(evaluations)

            assert len(results) == 3


class TestFailOpenFailClosed:
    """Testes de fail-open vs fail-closed."""

    @pytest.mark.asyncio
    async def test_fail_closed_rejects_on_opa_error(self, mock_config):
        """Testa fail-closed rejeita tickets em erro OPA."""
        import aiohttp

        mock_config.opa_fail_open = False
        mock_opa_client = AsyncMock()
        mock_opa_client.evaluate_policy = AsyncMock(side_effect=OPAConnectionError("Connection timeout"))

        validator = PolicyValidator(mock_opa_client, mock_config)

        ticket = {'ticket_id': 'test-1', 'namespace': 'production'}

        result = await validator.validate_execution_ticket(ticket)

        # Em fail-closed, deve rejeitar
        assert result.valid is False
        assert len(result.violations) > 0

    @pytest.mark.asyncio
    async def test_fail_open_allows_on_opa_error(self, mock_config):
        """Testa fail-open permite tickets em erro OPA."""
        mock_config.opa_fail_open = True
        mock_opa_client = AsyncMock()
        mock_opa_client.batch_evaluate = AsyncMock(side_effect=OPAConnectionError("Connection timeout"))

        validator = PolicyValidator(mock_opa_client, mock_config)

        ticket = {'ticket_id': 'test-1', 'namespace': 'production'}

        result = await validator.validate_execution_ticket(ticket)

        # Em fail-open, deve permitir com warning
        assert result.valid is True
        assert len(result.warnings) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
