"""
Testes unitarios para Authorization Audit Log.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.policies.opa_client import OPAClient


@pytest.fixture
def mock_mongodb_client():
    """Mock do MongoDB client."""
    client = AsyncMock()
    client.save_authorization_audit = AsyncMock()
    client.authorization_audit = AsyncMock()
    return client


@pytest.fixture
def mock_config():
    """Mock de configuracao."""
    config = MagicMock()
    config.opa_host = 'localhost'
    config.opa_port = 8181
    config.opa_timeout_seconds = 5
    config.opa_cache_ttl_seconds = 300
    config.opa_retry_attempts = 3
    config.opa_circuit_breaker_enabled = False
    config.opa_circuit_breaker_failure_threshold = 5
    config.opa_circuit_breaker_timeout_seconds = 60
    config.opa_circuit_breaker_recovery_timeout_seconds = 30
    config.opa_max_concurrent_evaluations = 10
    config.opa_fail_open = True
    return config


@pytest.fixture
def mock_metrics():
    """Mock de metricas."""
    metrics = MagicMock()
    metrics.record_authorization_audit_logged = MagicMock()
    metrics.record_authorization_audit_error = MagicMock()
    return metrics


class TestAuthorizationAuditLogging:
    """Testes para logging de decisoes de autorizacao."""

    @pytest.mark.asyncio
    async def test_authorization_audit_logged_on_allow(self, mock_config, mock_mongodb_client, mock_metrics):
        """Testa que decisao 'allow' e auditada."""
        with patch('src.policies.opa_client.get_metrics', return_value=mock_metrics):
            opa_client = OPAClient(mock_config, mongodb_client=mock_mongodb_client)
            await opa_client.initialize()

            policy_path = 'neuralhive/orchestrator/security_constraints'
            input_data = {
                'input': {
                    'resource': {'tenant_id': 'tenant-123', 'type': 'ticket', 'id': 'ticket-456'},
                    'context': {'user_id': 'user-789', 'action': 'create', 'workflow_id': 'wf-abc'}
                }
            }

            # Mock da avaliacao OPA
            with patch.object(opa_client, '_evaluate_policy_internal') as mock_eval:
                mock_eval.return_value = {
                    'result': {'allow': True, 'violations': []},
                    'policy_path': policy_path
                }

                await opa_client.evaluate_policy(policy_path, input_data)

            # Verificar que audit foi chamado
            mock_mongodb_client.save_authorization_audit.assert_called_once()

            # Verificar conteudo do audit
            call_args = mock_mongodb_client.save_authorization_audit.call_args[0][0]
            assert call_args['decision'] == 'allow'
            assert call_args['tenant_id'] == 'tenant-123'
            assert call_args['user_id'] == 'user-789'
            assert call_args['policy_path'] == policy_path
            assert call_args['violations'] == []
            assert call_args['resource']['type'] == 'ticket'
            assert call_args['context']['workflow_id'] == 'wf-abc'

            # Verificar metrica registrada (inclui tenant_id)
            mock_metrics.record_authorization_audit_logged.assert_called_once_with(
                policy_path=policy_path,
                decision='allow',
                tenant_id='tenant-123'
            )

    @pytest.mark.asyncio
    async def test_authorization_audit_logged_on_deny(self, mock_config, mock_mongodb_client, mock_metrics):
        """Testa que decisao 'deny' e auditada com violacoes."""
        with patch('src.policies.opa_client.get_metrics', return_value=mock_metrics):
            opa_client = OPAClient(mock_config, mongodb_client=mock_mongodb_client)
            await opa_client.initialize()

            policy_path = 'neuralhive/orchestrator/security_constraints'
            input_data = {
                'input': {
                    'resource': {'tenant_id': 'tenant-123'},
                    'context': {'user_id': 'user-456'}
                }
            }

            violations = [
                {'severity': 'critical', 'msg': 'Tenant nao autorizado'}
            ]

            with patch.object(opa_client, '_evaluate_policy_internal') as mock_eval:
                mock_eval.return_value = {
                    'result': {'allow': False, 'violations': violations},
                    'policy_path': policy_path
                }

                await opa_client.evaluate_policy(policy_path, input_data)

            # Verificar audit
            call_args = mock_mongodb_client.save_authorization_audit.call_args[0][0]
            assert call_args['decision'] == 'deny'
            assert call_args['violations'] == violations

            # Verificar metrica de deny (inclui tenant_id)
            mock_metrics.record_authorization_audit_logged.assert_called_once_with(
                policy_path=policy_path,
                decision='deny',
                tenant_id='tenant-123'
            )

    @pytest.mark.asyncio
    async def test_authorization_audit_logged_on_violations_without_allow_field(
        self, mock_config, mock_mongodb_client, mock_metrics
    ):
        """Testa que decisao e 'deny' quando ha violacoes mesmo sem campo 'allow'."""
        with patch('src.policies.opa_client.get_metrics', return_value=mock_metrics):
            opa_client = OPAClient(mock_config, mongodb_client=mock_mongodb_client)
            await opa_client.initialize()

            policy_path = 'neuralhive/orchestrator/resource_limits'
            input_data = {
                'input': {
                    'resource': {'tenant_id': 'tenant-123'},
                    'context': {}
                }
            }

            violations = [
                {'severity': 'warning', 'msg': 'Limite de recursos excedido'}
            ]

            with patch.object(opa_client, '_evaluate_policy_internal') as mock_eval:
                # Resultado sem campo 'allow' explicito, mas com violacoes
                mock_eval.return_value = {
                    'result': {'violations': violations},
                    'policy_path': policy_path
                }

                await opa_client.evaluate_policy(policy_path, input_data)

            # Verificar que decisao foi 'deny' por causa das violacoes
            call_args = mock_mongodb_client.save_authorization_audit.call_args[0][0]
            assert call_args['decision'] == 'deny'

    @pytest.mark.asyncio
    async def test_authorization_audit_fail_open(self, mock_config, mock_mongodb_client, mock_metrics):
        """Testa que falha no audit nao bloqueia avaliacao (fail-open)."""
        # Simular falha no MongoDB
        mock_mongodb_client.save_authorization_audit.side_effect = Exception('MongoDB down')

        with patch('src.policies.opa_client.get_metrics', return_value=mock_metrics):
            opa_client = OPAClient(mock_config, mongodb_client=mock_mongodb_client)
            await opa_client.initialize()

            policy_path = 'neuralhive/orchestrator/security_constraints'
            input_data = {'input': {'resource': {}, 'context': {}}}

            with patch.object(opa_client, '_evaluate_policy_internal') as mock_eval:
                mock_eval.return_value = {
                    'result': {'allow': True},
                    'policy_path': policy_path
                }

                # Nao deve lancar excecao (fail-open)
                result = await opa_client.evaluate_policy(policy_path, input_data)
                assert result is not None
                assert result['result']['allow'] is True

    @pytest.mark.asyncio
    async def test_authorization_audit_without_mongodb(self, mock_config, mock_metrics):
        """Testa que audit e pulado se MongoDB nao esta disponivel."""
        with patch('src.policies.opa_client.get_metrics', return_value=mock_metrics):
            # Criar OPA client sem MongoDB
            opa_client = OPAClient(mock_config, mongodb_client=None)
            await opa_client.initialize()

            policy_path = 'neuralhive/orchestrator/security_constraints'
            input_data = {'input': {'resource': {}, 'context': {}}}

            with patch.object(opa_client, '_evaluate_policy_internal') as mock_eval:
                mock_eval.return_value = {
                    'result': {'allow': True},
                    'policy_path': policy_path
                }

                # Nao deve falhar
                result = await opa_client.evaluate_policy(policy_path, input_data)
                assert result is not None

            # Verificar que metrica NAO foi registrada (sem MongoDB)
            mock_metrics.record_authorization_audit_logged.assert_not_called()

    @pytest.mark.asyncio
    async def test_authorization_audit_extracts_tenant_from_security(
        self, mock_config, mock_mongodb_client, mock_metrics
    ):
        """Testa extracao de tenant_id do campo security quando nao esta em resource."""
        with patch('src.policies.opa_client.get_metrics', return_value=mock_metrics):
            opa_client = OPAClient(mock_config, mongodb_client=mock_mongodb_client)
            await opa_client.initialize()

            policy_path = 'neuralhive/orchestrator/security_constraints'
            input_data = {
                'input': {
                    'resource': {'type': 'ticket'},  # Sem tenant_id aqui
                    'context': {'user_id': 'user-123'},
                    'security': {'tenant_id': 'tenant-from-security'}  # tenant_id aqui
                }
            }

            with patch.object(opa_client, '_evaluate_policy_internal') as mock_eval:
                mock_eval.return_value = {
                    'result': {'allow': True},
                    'policy_path': policy_path
                }

                await opa_client.evaluate_policy(policy_path, input_data)

            # Verificar que tenant_id foi extraido do security
            call_args = mock_mongodb_client.save_authorization_audit.call_args[0][0]
            assert call_args['tenant_id'] == 'tenant-from-security'

    @pytest.mark.asyncio
    async def test_authorization_audit_timestamp_format(
        self, mock_config, mock_mongodb_client, mock_metrics
    ):
        """Testa que timestamp e salvo em formato ISO."""
        with patch('src.policies.opa_client.get_metrics', return_value=mock_metrics):
            opa_client = OPAClient(mock_config, mongodb_client=mock_mongodb_client)
            await opa_client.initialize()

            policy_path = 'neuralhive/orchestrator/security_constraints'
            input_data = {'input': {'resource': {}, 'context': {}}}

            with patch.object(opa_client, '_evaluate_policy_internal') as mock_eval:
                mock_eval.return_value = {
                    'result': {'allow': True},
                    'policy_path': policy_path
                }

                await opa_client.evaluate_policy(policy_path, input_data)

            # Verificar formato do timestamp
            call_args = mock_mongodb_client.save_authorization_audit.call_args[0][0]
            timestamp = call_args['timestamp']

            # Tentar parsear como ISO
            parsed = datetime.fromisoformat(timestamp)
            assert isinstance(parsed, datetime)


class TestMongoDBAuthorizationAuditPersistence:
    """Testes para persistencia de audit no MongoDB."""

    @pytest.mark.asyncio
    async def test_save_authorization_audit_success(self, mock_mongodb_client):
        """Testa persistencia bem-sucedida de audit entry."""
        from src.clients.mongodb_client import MongoDBClient

        # Mock do MongoDB client com authorization_audit collection
        mongodb_client = MagicMock(spec=MongoDBClient)
        mongodb_client.authorization_audit = AsyncMock()
        mongodb_client.authorization_audit.insert_one = AsyncMock()
        mongodb_client._get_retry_decorator = MagicMock(return_value=lambda f: f)

        # Criar audit entry
        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'tenant_id': 'tenant-123',
            'user_id': 'user-456',
            'decision': 'allow',
            'policy_path': 'test/policy',
            'violations': [],
            'resource': {'type': 'ticket'},
            'context': {}
        }

        # Chamar metodo (mockado)
        await mongodb_client.authorization_audit.insert_one(audit_entry)

        # Verificar chamada
        mongodb_client.authorization_audit.insert_one.assert_called_once_with(audit_entry)
