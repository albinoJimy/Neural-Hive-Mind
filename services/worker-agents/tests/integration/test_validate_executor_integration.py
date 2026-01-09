"""
Testes de integracao para ValidateExecutor.

Este modulo contem testes de integracao que verificam:
- Validacao via OPA (allow/deny)
- Tratamento de timeout OPA
- Tratamento de erros de API OPA
- Validacao SAST via Trivy
- Fallback conservador
- Metricas de violacoes por severidade

Todos os testes usam mocks dos clientes externos.
"""

import asyncio
import pytest
import uuid
from dataclasses import dataclass
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================
# Fixtures Especificas
# ============================================


@pytest.fixture
def validate_executor_with_opa(worker_config, mock_metrics, mock_opa_client):
    """ValidateExecutor configurado com cliente OPA mockado."""
    from services.worker_agents.src.executors.validate_executor import ValidateExecutor

    worker_config.opa_enabled = True
    worker_config.opa_url = 'http://opa.test:8181'

    return ValidateExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        opa_client=mock_opa_client
    )


@pytest.fixture
def validate_executor_with_trivy(worker_config, mock_metrics):
    """ValidateExecutor configurado para Trivy."""
    from services.worker_agents.src.executors.validate_executor import ValidateExecutor

    worker_config.trivy_enabled = True
    worker_config.trivy_timeout_seconds = 60
    worker_config.opa_enabled = False

    return ValidateExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        opa_client=None
    )


@pytest.fixture
def validate_executor_simulation_only(worker_config, mock_metrics):
    """ValidateExecutor sem clientes externos (apenas simulacao)."""
    from services.worker_agents.src.executors.validate_executor import ValidateExecutor

    worker_config.opa_enabled = False
    worker_config.trivy_enabled = False

    return ValidateExecutor(
        config=worker_config,
        vault_client=None,
        code_forge_client=None,
        metrics=mock_metrics,
        opa_client=None
    )


@pytest.fixture
def validate_ticket_policy():
    """Ticket de validacao de politica OPA."""
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'policy',
            'policy_path': 'policy/allow',
            'input_data': {
                'resource': 'deployment',
                'action': 'create',
                'user': 'admin'
            }
        }
    }


@pytest.fixture
def validate_ticket_sast():
    """Ticket de validacao SAST (Trivy)."""
    ticket_id = str(uuid.uuid4())
    return {
        'ticket_id': ticket_id,
        'task_id': f'task-{ticket_id[:8]}',
        'task_type': 'VALIDATE',
        'parameters': {
            'validation_type': 'sast',
            'working_dir': '/tmp/code'
        }
    }


# ============================================
# Classes Mock para ViolationSeverity
# ============================================


class MockViolationSeverity(Enum):
    CRITICAL = 'CRITICAL'
    HIGH = 'HIGH'
    MEDIUM = 'MEDIUM'
    LOW = 'LOW'


@dataclass
class MockViolation:
    rule_id: str = 'rule-001'
    message: str = 'Test violation'
    severity: MockViolationSeverity = MockViolationSeverity.MEDIUM
    resource: str = None
    location: str = None


@dataclass
class MockPolicyEvaluationResponse:
    allow: bool = True
    violations: list = None
    metadata: dict = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []
        if self.metadata is None:
            self.metadata = {}


# ============================================
# Testes OPA Allow
# ============================================


class TestValidateExecutorOPAAllow:
    """Testes de politica OPA que permite acao."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_allow(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve retornar sucesso quando politica OPA permite acao."""
        mock_opa_client.evaluate_policy.return_value = MockPolicyEvaluationResponse(
            allow=True,
            violations=[]
        )

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        assert result['success'] is True
        assert result['output']['validation_passed'] is True
        assert result['output']['violations'] == []
        assert result['metadata']['simulated'] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_allow_with_metadata(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve incluir metadata da avaliacao OPA."""
        mock_opa_client.evaluate_policy.return_value = MockPolicyEvaluationResponse(
            allow=True,
            violations=[],
            metadata={'decision_id': 'dec-123', 'timestamp': '2024-01-01T00:00:00Z'}
        )

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        assert result['success'] is True
        assert 'opa_metadata' in result['metadata']


# ============================================
# Testes OPA Deny
# ============================================


class TestValidateExecutorOPADeny:
    """Testes de politica OPA que nega acao."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_deny_with_violations(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve retornar falha quando politica OPA nega com violacoes."""
        violations = [
            MockViolation(
                rule_id='rule-001',
                message='Unauthorized user',
                severity=MockViolationSeverity.HIGH
            )
        ]

        mock_opa_client.evaluate_policy.return_value = MockPolicyEvaluationResponse(
            allow=False,
            violations=violations
        )

        mock_opa_client.count_violations_by_severity.return_value = {
            MockViolationSeverity.CRITICAL: 0,
            MockViolationSeverity.HIGH: 1,
            MockViolationSeverity.MEDIUM: 0,
            MockViolationSeverity.LOW: 0,
        }

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        assert result['success'] is False
        assert result['output']['validation_passed'] is False
        assert len(result['output']['violations']) == 1
        assert result['output']['violations'][0]['severity'] == 'HIGH'

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_deny_multiple_violations(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve listar todas as violacoes quando OPA nega."""
        violations = [
            MockViolation(rule_id='rule-001', message='Violation 1', severity=MockViolationSeverity.HIGH),
            MockViolation(rule_id='rule-002', message='Violation 2', severity=MockViolationSeverity.MEDIUM),
            MockViolation(rule_id='rule-003', message='Violation 3', severity=MockViolationSeverity.LOW),
        ]

        mock_opa_client.evaluate_policy.return_value = MockPolicyEvaluationResponse(
            allow=False,
            violations=violations
        )

        mock_opa_client.count_violations_by_severity.return_value = {
            MockViolationSeverity.CRITICAL: 0,
            MockViolationSeverity.HIGH: 1,
            MockViolationSeverity.MEDIUM: 1,
            MockViolationSeverity.LOW: 1,
        }

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        assert result['success'] is False
        assert len(result['output']['violations']) == 3


# ============================================
# Testes OPA Timeout
# ============================================


class TestValidateExecutorOPATimeout:
    """Testes de timeout na avaliacao OPA."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_timeout(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve retornar falha conservadora quando OPA timeout."""
        from services.worker_agents.src.clients.opa_client import OPATimeoutError

        mock_opa_client.evaluate_policy.side_effect = OPATimeoutError(
            'OPA evaluation timed out'
        )

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        # Fallback conservador: falha quando OPA indisponivel
        assert result['success'] is False
        assert result['output']['validation_passed'] is False
        assert result['output']['fallback_reason'] == 'timeout'
        assert result['metadata']['conservative_failure'] is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_timeout_metrics(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client,
        mock_metrics
    ):
        """Deve registrar metrica de timeout."""
        from services.worker_agents.src.clients.opa_client import OPATimeoutError

        mock_opa_client.evaluate_policy.side_effect = OPATimeoutError(
            'OPA evaluation timed out'
        )

        await validate_executor_with_opa.execute(validate_ticket_policy)

        mock_metrics.validate_tasks_executed_total.labels.assert_called()


# ============================================
# Testes OPA API Error
# ============================================


class TestValidateExecutorOPAAPIError:
    """Testes de erros de API OPA."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_api_error_503(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve retornar falha conservadora quando OPA API erro 503."""
        from services.worker_agents.src.clients.opa_client import OPAAPIError

        mock_opa_client.evaluate_policy.side_effect = OPAAPIError(
            message='Service Unavailable',
            status_code=503
        )

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        assert result['success'] is False
        assert result['output']['validation_passed'] is False
        assert result['output']['fallback_reason'] == 'api_error'

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_opa_api_error_500(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve retornar falha conservadora quando OPA API erro 500."""
        from services.worker_agents.src.clients.opa_client import OPAAPIError

        mock_opa_client.evaluate_policy.side_effect = OPAAPIError(
            message='Internal Server Error',
            status_code=500
        )

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        assert result['success'] is False
        assert result['metadata']['conservative_failure'] is True


# ============================================
# Testes SAST (Trivy)
# ============================================


class TestValidateExecutorSAST:
    """Testes de validacao SAST via Trivy."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_trivy_success(
        self,
        validate_executor_with_trivy,
        validate_ticket_sast
    ):
        """Deve executar validacao SAST com sucesso (sem vulnerabilidades)."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"Results": []}',
                stderr=''
            )

            result = await validate_executor_with_trivy.execute(validate_ticket_sast)

            assert result['success'] is True
            assert result['output']['validation_passed'] is True
            assert result['output']['violations'] == []
            assert result['metadata']['simulated'] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_trivy_critical_vulnerabilities(
        self,
        validate_executor_with_trivy,
        validate_ticket_sast
    ):
        """Deve falhar quando Trivy encontra vulnerabilidades CRITICAL."""
        trivy_output = {
            'Results': [
                {
                    'Vulnerabilities': [
                        {'VulnerabilityID': 'CVE-2024-0001', 'Severity': 'CRITICAL', 'Title': 'Critical vuln'},
                        {'VulnerabilityID': 'CVE-2024-0002', 'Severity': 'CRITICAL', 'Title': 'Another critical'},
                    ]
                }
            ]
        }

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=str(trivy_output).replace("'", '"'),
                stderr=''
            )

            result = await validate_executor_with_trivy.execute(validate_ticket_sast)

            assert result['success'] is False
            assert result['output']['validation_passed'] is False
            assert len(result['output']['violations']) == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_trivy_timeout(
        self,
        validate_executor_with_trivy,
        validate_ticket_sast
    ):
        """Deve usar fallback simulado quando Trivy timeout."""
        import subprocess

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd='trivy',
                timeout=60
            )

            result = await validate_executor_with_trivy.execute(validate_ticket_sast)

            # Fallback para simulacao quando Trivy timeout
            assert result['success'] is True
            assert result['metadata']['simulated'] is True


# ============================================
# Testes de Metricas de Violacoes
# ============================================


class TestValidateExecutorViolationMetrics:
    """Testes de metricas de violacoes por severidade."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_violation_metrics_by_severity(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client,
        mock_metrics
    ):
        """Deve registrar metricas de violacoes por severidade."""
        violations = [
            MockViolation(rule_id='r1', severity=MockViolationSeverity.HIGH),
            MockViolation(rule_id='r2', severity=MockViolationSeverity.HIGH),
            MockViolation(rule_id='r3', severity=MockViolationSeverity.MEDIUM),
            MockViolation(rule_id='r4', severity=MockViolationSeverity.MEDIUM),
            MockViolation(rule_id='r5', severity=MockViolationSeverity.MEDIUM),
            MockViolation(rule_id='r6', severity=MockViolationSeverity.LOW),
        ]

        mock_opa_client.evaluate_policy.return_value = MockPolicyEvaluationResponse(
            allow=False,
            violations=violations
        )

        mock_opa_client.count_violations_by_severity.return_value = {
            MockViolationSeverity.CRITICAL: 0,
            MockViolationSeverity.HIGH: 2,
            MockViolationSeverity.MEDIUM: 3,
            MockViolationSeverity.LOW: 1,
        }

        await validate_executor_with_opa.execute(validate_ticket_policy)

        # Verificar que metricas foram registradas
        mock_metrics.validate_violations_total.labels.assert_called()


# ============================================
# Testes de Simulacao
# ============================================


class TestValidateExecutorSimulation:
    """Testes de fallback para simulacao."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_simulation_fallback(
        self,
        validate_executor_simulation_only,
        validate_ticket_policy
    ):
        """Deve usar simulacao quando nenhum provider disponivel."""
        result = await validate_executor_simulation_only.execute(validate_ticket_policy)

        assert result['success'] is True
        assert result['metadata']['simulated'] is True
        assert result['output']['validation_passed'] is True
        assert result['output']['violations'] == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_simulation_logs(
        self,
        validate_executor_simulation_only,
        validate_ticket_policy
    ):
        """Deve incluir logs informativos na simulacao."""
        result = await validate_executor_simulation_only.execute(validate_ticket_policy)

        assert 'logs' in result
        assert len(result['logs']) > 0


# ============================================
# Testes de Validacao de Ticket
# ============================================


class TestValidateExecutorTicketValidation:
    """Testes de validacao de ticket."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_missing_ticket_id(
        self,
        validate_executor_with_opa
    ):
        """Deve falhar com ticket sem ID."""
        invalid_ticket = {
            'task_type': 'VALIDATE',
            'parameters': {}
        }

        with pytest.raises(ValueError):
            await validate_executor_with_opa.execute(invalid_ticket)

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_wrong_task_type(
        self,
        validate_executor_with_opa
    ):
        """Deve falhar com task_type incorreto."""
        invalid_ticket = {
            'ticket_id': str(uuid.uuid4()),
            'task_type': 'BUILD',
            'parameters': {}
        }

        with pytest.raises(ValueError):
            await validate_executor_with_opa.execute(invalid_ticket)


# ============================================
# Testes de Erros Inesperados
# ============================================


class TestValidateExecutorUnexpectedErrors:
    """Testes de erros inesperados."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.executor_integration
    async def test_validate_executor_unexpected_exception(
        self,
        validate_executor_with_opa,
        validate_ticket_policy,
        mock_opa_client
    ):
        """Deve tratar excecoes inesperadas graciosamente."""
        mock_opa_client.evaluate_policy.side_effect = RuntimeError(
            'Unexpected error'
        )

        result = await validate_executor_with_opa.execute(validate_ticket_policy)

        # Fallback conservador
        assert result['success'] is False
