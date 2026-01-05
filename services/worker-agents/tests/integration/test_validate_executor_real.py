"""
Integration tests for ValidateExecutor.

Tests the ValidateExecutor with mocked and real validation tool integrations,
including OPA, Trivy, SonarQube, Snyk, and Checkov.
"""

import asyncio
import json
import os
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tests.fixtures.client_fixtures import MockOPAServer
from tests.fixtures.executor_fixtures import (
    create_mock_sonarqube_client,
    create_mock_snyk_client,
    create_mock_checkov_client,
)
from tests.helpers.integration_helpers import (
    ExecutorTestHelper,
    ResultValidator,
)


pytestmark = [pytest.mark.integration]


class TestValidateExecutorWithMockOPA:
    """Tests for ValidateExecutor with mocked OPA API."""

    @pytest.mark.asyncio
    async def test_validate_executor_opa_policy_allow(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test successful policy validation with OPA."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Create mock OPA server that allows
        mock_server = MockOPAServer(default_allow=True)

        worker_config.opa_enabled = True
        worker_config.opa_url = 'http://opa-mock:8181'

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Patch httpx.AsyncClient to use mock transport
        with patch.object(httpx, 'AsyncClient') as mock_client_class:
            mock_client = mock_server.get_client()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            ticket = ExecutorTestHelper.create_validate_ticket(
                validation_type='policy',
                policy_path='policy/allow',
                input_data={'user': 'admin', 'action': 'read'},
            )

            result = await executor.execute(ticket)

        # Validate result
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_has_output(result, 'validation_passed', 'violations', 'validation_type')
        ResultValidator.assert_output_value(result, 'validation_passed', True)
        ResultValidator.assert_output_value(result, 'validation_type', 'policy')

    @pytest.mark.asyncio
    async def test_validate_executor_opa_policy_deny(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test policy validation with violations."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Create mock OPA server that denies
        mock_server = MockOPAServer(default_allow=False)

        worker_config.opa_enabled = True
        worker_config.opa_url = 'http://opa-mock:8181'

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        with patch.object(httpx, 'AsyncClient') as mock_client_class:
            mock_client = mock_server.get_client()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            ticket = ExecutorTestHelper.create_validate_ticket(
                validation_type='policy',
                policy_path='policy/allow',
                input_data={'user': 'guest', 'action': 'delete'},
            )

            result = await executor.execute(ticket)

        # Should fail with violations
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'validation_passed', False)
        assert len(result['output']['violations']) > 0

    @pytest.mark.asyncio
    async def test_validate_executor_opa_custom_policy(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test with custom OPA policy handler."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Create mock OPA server with custom policy
        mock_server = MockOPAServer()

        def custom_policy(input_data: dict) -> dict:
            # Allow only admin users
            if input_data.get('user') == 'admin':
                return {'allow': True, 'violations': []}
            return {
                'allow': False,
                'violations': [{'message': 'Access denied for non-admin user', 'rule': 'admin_only'}],
            }

        mock_server.add_policy('authz/admin', custom_policy)

        worker_config.opa_enabled = True
        worker_config.opa_url = 'http://opa-mock:8181'

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        with patch.object(httpx, 'AsyncClient') as mock_client_class:
            mock_client = mock_server.get_client()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            # Test with non-admin user
            ticket = ExecutorTestHelper.create_validate_ticket(
                validation_type='policy',
                policy_path='authz/admin',
                input_data={'user': 'guest'},
            )

            result = await executor.execute(ticket)

        ResultValidator.assert_failure(result)
        ResultValidator.assert_log_contains(result, 'OPA')

    @pytest.mark.asyncio
    async def test_validate_executor_opa_connection_error(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test handling of OPA connection error."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.opa_enabled = True
        worker_config.opa_url = 'http://opa-unreachable:8181'

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Mock connection error
        with patch.object(httpx.AsyncClient, 'post', side_effect=httpx.ConnectError('Connection refused')):
            ticket = ExecutorTestHelper.create_validate_ticket(
                validation_type='policy',
                policy_path='policy/allow',
            )

            result = await executor.execute(ticket)

        # Should fall back to simulation
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)


class TestValidateExecutorWithMockTrivy:
    """Tests for ValidateExecutor with mocked Trivy."""

    @pytest.mark.asyncio
    async def test_validate_executor_trivy_no_vulnerabilities(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test Trivy scan with no vulnerabilities."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.trivy_enabled = True
        worker_config.trivy_timeout_seconds = 30

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Mock Trivy subprocess
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'Results': [
                {'Vulnerabilities': []},
            ],
        })
        mock_result.stderr = ''

        with patch('subprocess.run', return_value=mock_result):
            ticket = ExecutorTestHelper.create_validate_ticket(
                validation_type='sast',
                working_dir='/tmp',
            )

            result = await executor.execute(ticket)

        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'validation_passed', True)
        assert len(result['output']['violations']) == 0

    @pytest.mark.asyncio
    async def test_validate_executor_trivy_critical_findings(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test Trivy scan with critical vulnerabilities."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.trivy_enabled = True

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Mock Trivy with critical vulnerabilities
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'Results': [
                {
                    'Vulnerabilities': [
                        {'VulnerabilityID': 'CVE-2024-1234', 'Severity': 'CRITICAL', 'Title': 'RCE Vulnerability'},
                        {'VulnerabilityID': 'CVE-2024-5678', 'Severity': 'HIGH', 'Title': 'XSS Vulnerability'},
                    ],
                },
            ],
        })
        mock_result.stderr = ''

        with patch('subprocess.run', return_value=mock_result):
            ticket = ExecutorTestHelper.create_validate_ticket(
                validation_type='sast',
                working_dir='/tmp',
            )

            result = await executor.execute(ticket)

        # Should fail due to critical findings
        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'validation_passed', False)
        assert len(result['output']['violations']) == 1  # Only CRITICAL

    @pytest.mark.asyncio
    async def test_validate_executor_trivy_timeout(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test Trivy scan timeout handling."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.trivy_enabled = True
        worker_config.trivy_timeout_seconds = 1

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('trivy', 1)):
            ticket = ExecutorTestHelper.create_validate_ticket(
                validation_type='sast',
                working_dir='/tmp',
            )

            result = await executor.execute(ticket)

        # Should succeed with simulated result on timeout
        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)


class TestValidateExecutorWithMockSonarQube:
    """Tests for ValidateExecutor with mocked SonarQube."""

    @pytest.mark.asyncio
    async def test_validate_executor_sonarqube_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test SonarQube analysis that passes."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.sonarqube_enabled = True
        worker_config.sonarqube_url = 'http://sonarqube:9000'
        worker_config.sonarqube_token = 'test-token'

        mock_client = create_mock_sonarqube_client(passed=True, issues=[])

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.sonarqube_client = mock_client

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='sonarqube',
            project_key='test-project',
            working_dir='/tmp/src',
        )

        result = await executor.execute(ticket)

        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'validation_type', 'sonarqube')

    @pytest.mark.asyncio
    async def test_validate_executor_sonarqube_with_issues(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test SonarQube analysis with issues."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.sonarqube_enabled = True
        worker_config.sonarqube_url = 'http://sonarqube:9000'
        worker_config.sonarqube_token = 'test-token'

        mock_client = create_mock_sonarqube_client(
            passed=False,
            issues=[
                {'key': 'issue1', 'severity': 'CRITICAL', 'message': 'SQL Injection'},
                {'key': 'issue2', 'severity': 'MAJOR', 'message': 'XSS vulnerability'},
            ],
        )

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.sonarqube_client = mock_client

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='sonarqube',
            project_key='test-project',
        )

        result = await executor.execute(ticket)

        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)


class TestValidateExecutorWithMockSnyk:
    """Tests for ValidateExecutor with mocked Snyk."""

    @pytest.mark.asyncio
    async def test_validate_executor_snyk_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test Snyk scan that passes."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.snyk_enabled = True
        worker_config.snyk_token = 'test-token'

        mock_client = create_mock_snyk_client(passed=True, vulnerabilities=[])

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.snyk_client = mock_client

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='snyk',
            manifest_path='/tmp/package.json',
        )

        result = await executor.execute(ticket)

        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'validation_type', 'snyk')

    @pytest.mark.asyncio
    async def test_validate_executor_snyk_with_vulnerabilities(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test Snyk scan with vulnerabilities."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.snyk_enabled = True
        worker_config.snyk_token = 'test-token'

        mock_client = create_mock_snyk_client(
            passed=False,
            vulnerabilities=[
                {'id': 'SNYK-JS-1234', 'severity': 'high', 'title': 'Prototype Pollution'},
            ],
        )

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.snyk_client = mock_client

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='snyk',
            manifest_path='/tmp/package.json',
        )

        result = await executor.execute(ticket)

        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)


class TestValidateExecutorWithMockCheckov:
    """Tests for ValidateExecutor with mocked Checkov."""

    @pytest.mark.asyncio
    async def test_validate_executor_checkov_success(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test Checkov IaC scan that passes."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.checkov_enabled = True

        mock_client = create_mock_checkov_client(passed=True, findings=[])

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.checkov_client = mock_client

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='iac',
            working_dir='/tmp/terraform',
        )

        result = await executor.execute(ticket)

        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=False)
        ResultValidator.assert_output_value(result, 'validation_type', 'iac')

    @pytest.mark.asyncio
    async def test_validate_executor_checkov_with_findings(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test Checkov IaC scan with findings."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        worker_config.checkov_enabled = True

        mock_client = create_mock_checkov_client(
            passed=False,
            findings=[
                {'check_id': 'CKV_AWS_21', 'severity': 'HIGH', 'resource': 's3_bucket.public'},
                {'check_id': 'CKV_AWS_19', 'severity': 'MEDIUM', 'resource': 's3_bucket.logs'},
            ],
        )

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.checkov_client = mock_client

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='iac',
            working_dir='/tmp/terraform',
        )

        result = await executor.execute(ticket)

        ResultValidator.assert_failure(result)
        ResultValidator.assert_simulated(result, expected=False)


class TestValidateExecutorSimulation:
    """Tests for ValidateExecutor simulation mode."""

    @pytest.mark.asyncio
    async def test_validate_executor_simulation_mode(
        self, worker_config_minimal, mock_vault_client, mock_metrics
    ):
        """Test validation in pure simulation mode."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        executor = ValidateExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='policy',
        )

        result = await executor.execute(ticket)

        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)
        ResultValidator.assert_has_output(result, 'validation_passed', 'violations', 'validation_type')
        ResultValidator.assert_log_contains(result, 'simulated')

    @pytest.mark.asyncio
    async def test_validate_executor_fallback_simulation(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test fallback to simulation when all tools are disabled."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Disable all validation tools
        worker_config.opa_enabled = False
        worker_config.trivy_enabled = False
        worker_config.sonarqube_enabled = False
        worker_config.snyk_enabled = False
        worker_config.checkov_enabled = False

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_validate_ticket()

        result = await executor.execute(ticket)

        ResultValidator.assert_success(result)
        ResultValidator.assert_simulated(result, expected=True)


class TestValidateExecutorValidation:
    """Tests for ValidateExecutor input validation."""

    @pytest.mark.asyncio
    async def test_validate_executor_missing_ticket_id(self, validate_executor):
        """Test that missing ticket_id raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'task_id': 'task-123',
            'task_type': 'VALIDATE',
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await validate_executor.execute(ticket)

        assert 'ticket_id' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_executor_wrong_task_type(self, validate_executor):
        """Test that wrong task_type raises ValidationError."""
        from services.worker_agents.src.executors.base_executor import ValidationError

        ticket = {
            'ticket_id': 'ticket-123',
            'task_id': 'task-123',
            'task_type': 'BUILD',  # Wrong type
            'parameters': {},
        }

        with pytest.raises(ValidationError) as exc_info:
            await validate_executor.execute(ticket)

        assert 'task type mismatch' in str(exc_info.value).lower()


@pytest.mark.real_integration
@pytest.mark.opa
class TestValidateExecutorRealOPA:
    """Tests that require a real OPA instance."""

    @pytest.mark.asyncio
    async def test_validate_executor_with_real_opa(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test with real OPA (requires OPA_URL env var)."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        opa_url = os.getenv('OPA_URL')
        if not opa_url:
            pytest.skip('OPA_URL not configured')

        worker_config.opa_enabled = True
        worker_config.opa_url = opa_url

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='policy',
            policy_path='system/health',
            input_data={},
        )

        result = await executor.execute(ticket)

        # With real service, expect either success or graceful failure
        assert 'success' in result
        assert 'output' in result
        assert 'metadata' in result


@pytest.mark.real_integration
@pytest.mark.trivy
class TestValidateExecutorRealTrivy:
    """Tests that require real Trivy installation."""

    @pytest.mark.asyncio
    async def test_validate_executor_with_real_trivy(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test with real Trivy (requires trivy in PATH)."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor
        import shutil

        if not shutil.which('trivy'):
            pytest.skip('Trivy not installed')

        worker_config.trivy_enabled = True
        worker_config.trivy_timeout_seconds = 120

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='sast',
            working_dir='/tmp',
        )

        result = await executor.execute(ticket)

        # With real Trivy, expect either success or proper failure
        assert 'success' in result
        assert 'output' in result
        assert 'metadata' in result


@pytest.mark.real_integration
@pytest.mark.sonarqube
class TestValidateExecutorRealSonarQube:
    """Tests that require a real SonarQube instance."""

    @pytest.mark.asyncio
    async def test_validate_executor_with_real_sonarqube(
        self, worker_config, mock_vault_client, mock_metrics
    ):
        """Test with real SonarQube (requires SONARQUBE_URL and SONARQUBE_TOKEN)."""
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        sonarqube_url = os.getenv('SONARQUBE_URL')
        sonarqube_token = os.getenv('SONARQUBE_TOKEN')

        if not sonarqube_url or not sonarqube_token:
            pytest.skip('SONARQUBE_URL and SONARQUBE_TOKEN not configured')

        worker_config.sonarqube_enabled = True
        worker_config.sonarqube_url = sonarqube_url
        worker_config.sonarqube_token = sonarqube_token

        from services.worker_agents.src.clients.sonarqube_client import SonarQubeClient
        real_client = SonarQubeClient(sonarqube_url, sonarqube_token)

        executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        executor.sonarqube_client = real_client

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='sonarqube',
            project_key='test-project',
        )

        result = await executor.execute(ticket)

        assert 'success' in result
        assert 'output' in result
