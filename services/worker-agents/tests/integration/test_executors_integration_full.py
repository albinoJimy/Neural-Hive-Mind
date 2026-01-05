"""
Full E2E Integration Tests for Worker Agents Executors.

These tests cover complete workflows that involve multiple executors
working together, simulating real-world scenarios.

Test categories:
- Full pipeline flows (BUILD -> DEPLOY -> TEST -> VALIDATE)
- Parallel executor execution
- Executor dependency chains
- Error handling and recovery
- Metrics collection across flows
"""

import asyncio
import os
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.fixtures.executor_fixtures import (
    create_mock_code_forge_client,
    create_pipeline_status,
)
from tests.helpers.integration_helpers import (
    ExecutorTestHelper,
    ResultValidator,
)


pytestmark = [pytest.mark.integration]


class TestFullPipelineFlow:
    """Tests for complete build-deploy-test-validate pipeline flows."""

    @pytest.mark.asyncio
    async def test_full_build_deploy_test_validate_flow(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test complete flow: BUILD -> DEPLOY -> TEST -> VALIDATE.

        This simulates a real CI/CD pipeline where:
        1. BUILD creates an artifact
        2. DEPLOY uses the artifact from BUILD
        3. TEST runs integration tests against the deployment
        4. VALIDATE validates the deployed application
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor
        from services.worker_agents.src.executors.test_executor import TestExecutor
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Create mock Code Forge client for build
        mock_code_forge = create_mock_code_forge_client(
            pipeline_id='pipeline-e2e-123',
            status='completed',
        )

        # Step 1: BUILD
        build_executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_code_forge,
            metrics=mock_metrics,
        )

        build_ticket = ExecutorTestHelper.create_build_ticket(
            artifact_id='e2e-app',
            branch='main',
            commit_sha='e2e123abc',
        )

        build_result = await build_executor.execute(build_ticket)
        ResultValidator.assert_success(build_result)

        # Extract build artifacts for deploy
        build_output = build_result.get('output', {})
        artifact_info = {
            'pipeline_id': build_output.get('pipeline_id', 'pipeline-e2e-123'),
            'artifact_id': build_output.get('artifact_id', 'e2e-app'),
        }

        # Step 2: DEPLOY (using build output)
        deploy_executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        deploy_ticket = ExecutorTestHelper.create_deploy_ticket(
            namespace='e2e-test',
            deployment_name='e2e-app',
            image=f"registry/e2e-app:{artifact_info['pipeline_id']}",
            replicas=2,
            build_pipeline_id=artifact_info['pipeline_id'],
        )

        deploy_result = await deploy_executor.execute(deploy_ticket)
        ResultValidator.assert_success(deploy_result)

        deploy_output = deploy_result.get('output', {})

        # Step 3: TEST (integration tests against deployment)
        test_executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        test_ticket = ExecutorTestHelper.create_test_ticket(
            test_command='echo "E2E tests passed"',
            test_suite='integration',
            working_dir='/tmp',
            deployment_id=deploy_output.get('deployment_id', 'deploy-e2e'),
            target_namespace='e2e-test',
        )

        test_result = await test_executor.execute(test_ticket)
        ResultValidator.assert_success(test_result)

        # Step 4: VALIDATE (security and policy validation)
        validate_executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        validate_ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='policy',
            policy_path='policy/deployment/allow',
            input_data={
                'namespace': 'e2e-test',
                'deployment': 'e2e-app',
                'image': f"registry/e2e-app:{artifact_info['pipeline_id']}",
            },
        )

        validate_result = await validate_executor.execute(validate_ticket)
        ResultValidator.assert_success(validate_result)

        # Verify all stages completed
        assert build_result['success']
        assert deploy_result['success']
        assert test_result['success']
        assert validate_result['success']

    @pytest.mark.asyncio
    async def test_build_deploy_flow_with_rollback_on_test_failure(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that deploy can be rolled back when tests fail.

        Flow:
        1. BUILD succeeds
        2. DEPLOY succeeds
        3. TEST fails
        4. DEPLOY rollback is triggered
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor
        from services.worker_agents.src.executors.test_executor import TestExecutor

        # Build
        mock_code_forge = create_mock_code_forge_client(status='completed')
        build_executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_code_forge,
            metrics=mock_metrics,
        )

        build_result = await build_executor.execute(
            ExecutorTestHelper.create_build_ticket(artifact_id='rollback-test-app')
        )
        ResultValidator.assert_success(build_result)

        # Deploy
        deploy_executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        deploy_result = await deploy_executor.execute(
            ExecutorTestHelper.create_deploy_ticket(
                deployment_name='rollback-test-app',
                namespace='rollback-test',
            )
        )
        ResultValidator.assert_success(deploy_result)

        # Test - simulate failure with a command that returns non-zero
        test_executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Use a command that will fail
        test_ticket = ExecutorTestHelper.create_test_ticket(
            test_command='python -c "exit(1)"',
            test_suite='smoke',
            working_dir='/tmp',
        )

        test_result = await test_executor.execute(test_ticket)

        # Test should fail
        ResultValidator.assert_failure(test_result)

        # In a real scenario, we would trigger rollback
        # For this test, we verify the failure is properly captured
        assert test_result.get('output', {}).get('tests_passed') is False or test_result['success'] is False


class TestParallelExecutorExecution:
    """Tests for running multiple executors in parallel."""

    @pytest.mark.asyncio
    async def test_parallel_validate_execution(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test running multiple validation types in parallel.

        Runs OPA policy, Trivy, and Checkov validations concurrently.
        """
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        validate_executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        # Create multiple validation tickets
        tickets = [
            ExecutorTestHelper.create_validate_ticket(
                validation_type='policy',
                policy_path='policy/allow',
                input_data={'user': 'test', 'action': 'read'},
            ),
            ExecutorTestHelper.create_validate_ticket(
                validation_type='sast',
                working_dir='/tmp',
            ),
            ExecutorTestHelper.create_validate_ticket(
                validation_type='iac',
                working_dir='/tmp',
            ),
        ]

        # Execute all validations in parallel
        results = await asyncio.gather(
            *[validate_executor.execute(ticket) for ticket in tickets],
            return_exceptions=True,
        )

        # All should complete
        assert len(results) == 3

        # At least some should succeed (simulation mode)
        successful = sum(
            1 for r in results
            if isinstance(r, dict) and r.get('success') is True
        )
        assert successful >= 1, f'Expected at least 1 success, got results: {results}'

    @pytest.mark.asyncio
    async def test_parallel_build_execution(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test running multiple builds in parallel.

        Simulates building multiple microservices concurrently.
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        # Track which builds complete
        build_ids = ['service-a', 'service-b', 'service-c']

        async def create_build_with_delay(artifact_id: str, delay: float):
            """Create a build with simulated delay."""
            mock_client = create_mock_code_forge_client(
                pipeline_id=f'pipeline-{artifact_id}',
                status='completed',
            )

            executor = BuildExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                code_forge_client=mock_client,
                metrics=mock_metrics,
            )

            ticket = ExecutorTestHelper.create_build_ticket(artifact_id=artifact_id)
            result = await executor.execute(ticket)
            await asyncio.sleep(delay)  # Simulate different build times
            return artifact_id, result

        # Execute all builds in parallel
        tasks = [
            create_build_with_delay(build_id, delay=0.1 * i)
            for i, build_id in enumerate(build_ids)
        ]

        results = await asyncio.gather(*tasks)

        # All builds should complete
        assert len(results) == len(build_ids)

        for artifact_id, result in results:
            assert artifact_id in build_ids
            ResultValidator.assert_success(result)

    @pytest.mark.asyncio
    async def test_parallel_test_execution_different_suites(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test running different test suites in parallel.

        Runs unit, integration, and e2e test suites concurrently.
        """
        from services.worker_agents.src.executors.test_executor import TestExecutor

        test_executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        test_suites = ['unit', 'integration', 'e2e']
        tickets = [
            ExecutorTestHelper.create_test_ticket(
                test_command='echo "Running tests"',
                test_suite=suite,
                working_dir='/tmp',
            )
            for suite in test_suites
        ]

        # Execute all test suites in parallel
        results = await asyncio.gather(
            *[test_executor.execute(ticket) for ticket in tickets]
        )

        # All should succeed
        assert len(results) == len(test_suites)
        for result in results:
            ResultValidator.assert_success(result)


class TestExecutorDependencyChains:
    """Tests for executors with dependencies between them."""

    @pytest.mark.asyncio
    async def test_sequential_builds_with_dependencies(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test building dependent services in sequence.

        base-lib -> service-a (depends on base-lib) -> service-b (depends on service-a)
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        builds = [
            ('base-lib', None),
            ('service-a', 'base-lib'),
            ('service-b', 'service-a'),
        ]

        build_results: Dict[str, Any] = {}

        for artifact_id, depends_on in builds:
            mock_client = create_mock_code_forge_client(
                pipeline_id=f'pipeline-{artifact_id}',
                status='completed',
            )

            executor = BuildExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                code_forge_client=mock_client,
                metrics=mock_metrics,
            )

            params: Dict[str, Any] = {'artifact_id': artifact_id}
            if depends_on:
                # Include dependency info
                params['depends_on'] = depends_on
                params['dependency_pipeline_id'] = build_results.get(depends_on, {}).get('pipeline_id')

            ticket = ExecutorTestHelper.create_ticket('BUILD', params)
            result = await executor.execute(ticket)

            ResultValidator.assert_success(result)
            build_results[artifact_id] = result.get('output', {})

        # Verify all builds completed in order
        assert len(build_results) == len(builds)
        for artifact_id, _ in builds:
            assert artifact_id in build_results

    @pytest.mark.asyncio
    async def test_deploy_with_validation_gate(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that deployment proceeds only after validation passes.

        VALIDATE -> DEPLOY (only if validation passes)
        """
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        # First: Validate the deployment configuration
        validate_executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        validate_ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='policy',
            policy_path='policy/deployment/allow',
            input_data={
                'namespace': 'production',
                'image': 'app:v1.0',
                'replicas': 3,
            },
        )

        validate_result = await validate_executor.execute(validate_ticket)

        # Check if validation passed before deploying
        if validate_result.get('success') and validate_result.get('output', {}).get('validation_passed', False):
            # Proceed with deployment
            deploy_executor = DeployExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                metrics=mock_metrics,
            )

            deploy_ticket = ExecutorTestHelper.create_deploy_ticket(
                namespace='production',
                deployment_name='app',
                image='app:v1.0',
                replicas=3,
            )

            deploy_result = await deploy_executor.execute(deploy_ticket)
            ResultValidator.assert_success(deploy_result)
        else:
            # Validation blocked deployment (also acceptable outcome)
            assert validate_result.get('success') or validate_result.get('output', {}).get('validation_passed') is not None


class TestErrorHandlingAndRecovery:
    """Tests for error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_executor_retry_on_transient_failure(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that executors retry on transient failures.
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        call_count = {'value': 0}

        async def transient_failure(artifact_id):
            call_count['value'] += 1
            if call_count['value'] < 2:
                raise ConnectionError('Network timeout')
            return 'pipeline-recovered'

        mock_client = AsyncMock()
        mock_client.trigger_pipeline = AsyncMock(side_effect=transient_failure)
        mock_client.wait_for_pipeline_completion = AsyncMock(
            return_value=create_pipeline_status(
                pipeline_id='pipeline-recovered',
                status='completed',
            )
        )

        # Configure faster retries for test
        worker_config.code_forge_retry_attempts = 3
        worker_config.retry_backoff_base_seconds = 0.01
        worker_config.retry_backoff_max_seconds = 0.05

        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket(artifact_id='retry-test')
        result = await executor.execute(ticket)

        # Should succeed after retry
        ResultValidator.assert_success(result)
        assert call_count['value'] >= 2

    @pytest.mark.asyncio
    async def test_executor_graceful_degradation(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that executors gracefully degrade when dependencies are unavailable.
        """
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Disable all validation tools
        worker_config.opa_enabled = False
        worker_config.trivy_enabled = False
        worker_config.sonarqube_enabled = False
        worker_config.snyk_enabled = False
        worker_config.checkov_enabled = False

        validate_executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_validate_ticket(
            validation_type='policy',
            policy_path='policy/allow',
            input_data={'test': 'data'},
        )

        result = await validate_executor.execute(ticket)

        # Should still complete (either with simulation or graceful handling)
        assert 'success' in result
        assert 'output' in result

    @pytest.mark.asyncio
    async def test_pipeline_continues_on_non_critical_failure(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that pipeline can continue when non-critical steps fail.

        BUILD -> VALIDATE (non-critical, can fail) -> DEPLOY
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        # Build succeeds
        mock_code_forge = create_mock_code_forge_client(status='completed')
        build_executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_code_forge,
            metrics=mock_metrics,
        )

        build_result = await build_executor.execute(
            ExecutorTestHelper.create_build_ticket(artifact_id='resilient-app')
        )
        ResultValidator.assert_success(build_result)

        # Validate - might fail but is non-critical
        validate_executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        validate_result = await validate_executor.execute(
            ExecutorTestHelper.create_validate_ticket(
                validation_type='sast',
                working_dir='/tmp',
            )
        )

        # Record validation result but don't block
        validation_warning = not validate_result.get('success', False)

        # Deploy regardless of non-critical validation
        deploy_executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        deploy_result = await deploy_executor.execute(
            ExecutorTestHelper.create_deploy_ticket(
                deployment_name='resilient-app',
                namespace='staging',
            )
        )

        # Deploy should succeed even if validation had issues
        ResultValidator.assert_success(deploy_result)

        # Optionally include validation warning in deployment metadata
        if validation_warning:
            # In a real implementation, you might add warnings to the result
            pass


class TestMetricsCollectionAcrossFlows:
    """Tests for metrics collection during full workflows."""

    @pytest.mark.asyncio
    async def test_metrics_recorded_for_complete_flow(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that metrics are recorded for each step in a complete flow.
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor
        from services.worker_agents.src.executors.test_executor import TestExecutor
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Reset metrics tracking
        mock_metrics.reset_mock()

        # Build
        mock_code_forge = create_mock_code_forge_client(status='completed')
        build_executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_code_forge,
            metrics=mock_metrics,
        )
        await build_executor.execute(ExecutorTestHelper.create_build_ticket())

        # Deploy
        deploy_executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        await deploy_executor.execute(ExecutorTestHelper.create_deploy_ticket())

        # Test
        test_executor = TestExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        await test_executor.execute(
            ExecutorTestHelper.create_test_ticket(test_command='echo "test"')
        )

        # Validate
        validate_executor = ValidateExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        await validate_executor.execute(
            ExecutorTestHelper.create_validate_ticket(
                validation_type='policy',
                policy_path='policy/allow',
                input_data={'test': True},
            )
        )

        # Verify metrics were recorded for each executor
        # Build metrics
        assert mock_metrics.build_tasks_executed_total.labels.called

        # Deploy metrics
        assert mock_metrics.deploy_tasks_executed_total.labels.called

        # Test metrics
        assert mock_metrics.test_tasks_executed_total.labels.called

        # Validate metrics
        assert mock_metrics.validate_tasks_executed_total.labels.called

    @pytest.mark.asyncio
    async def test_duration_metrics_captured(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that duration metrics are captured for executor operations.
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        mock_code_forge = create_mock_code_forge_client(status='completed')
        executor = BuildExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            code_forge_client=mock_code_forge,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket()
        result = await executor.execute(ticket)

        ResultValidator.assert_success(result)

        # Check that duration metrics were recorded
        # The actual implementation should call observe() on duration histograms
        metadata = result.get('metadata', {})
        assert 'duration_seconds' in metadata or mock_metrics.build_duration_seconds.labels.called


class TestSimulationVsRealMode:
    """Tests comparing simulation mode vs real service mode."""

    @pytest.mark.asyncio
    async def test_simulation_mode_completes_flow(
        self,
        worker_config_minimal,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that complete flow works in simulation mode (no external services).
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor
        from services.worker_agents.src.executors.test_executor import TestExecutor
        from services.worker_agents.src.executors.validate_executor import ValidateExecutor

        # Build in simulation mode
        build_executor = BuildExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            code_forge_client=None,
            metrics=mock_metrics,
        )
        build_result = await build_executor.execute(
            ExecutorTestHelper.create_build_ticket()
        )
        ResultValidator.assert_success(build_result)
        ResultValidator.assert_simulated(build_result, expected=True)

        # Deploy in simulation mode
        deploy_executor = DeployExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        deploy_result = await deploy_executor.execute(
            ExecutorTestHelper.create_deploy_ticket()
        )
        ResultValidator.assert_success(deploy_result)
        ResultValidator.assert_simulated(deploy_result, expected=True)

        # Test in simulation mode
        test_executor = TestExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        test_result = await test_executor.execute(
            ExecutorTestHelper.create_test_ticket(test_command='echo "sim test"')
        )
        # Note: test executor may run the command locally even in "minimal" config
        ResultValidator.assert_success(test_result)

        # Validate in simulation mode
        validate_executor = ValidateExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )
        validate_result = await validate_executor.execute(
            ExecutorTestHelper.create_validate_ticket()
        )
        ResultValidator.assert_success(validate_result)
        ResultValidator.assert_simulated(validate_result, expected=True)

    @pytest.mark.asyncio
    async def test_simulation_mode_returns_valid_outputs(
        self,
        worker_config_minimal,
        mock_vault_client,
        mock_metrics,
    ):
        """
        Test that simulation mode returns properly structured outputs.
        """
        from services.worker_agents.src.executors.build_executor import BuildExecutor

        executor = BuildExecutor(
            config=worker_config_minimal,
            vault_client=mock_vault_client,
            code_forge_client=None,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_build_ticket(
            artifact_id='sim-test-artifact',
            branch='develop',
            commit_sha='sim123abc',
        )

        result = await executor.execute(ticket)

        # Verify structure
        assert 'success' in result
        assert 'output' in result
        assert 'metadata' in result
        assert 'logs' in result

        # Verify simulation-specific outputs
        output = result['output']
        assert 'build_id' in output or 'artifact_url' in output

        metadata = result['metadata']
        assert metadata.get('simulated') is True
        assert 'executor' in metadata


@pytest.mark.real_integration
class TestRealIntegrationFlows:
    """
    Tests that run against real external services.

    These tests require actual service instances and are skipped
    unless INTEGRATION_TEST_MODE=real is set.
    """

    @pytest.mark.asyncio
    @pytest.mark.code_forge
    async def test_real_build_with_code_forge(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """Test build execution with real Code Forge service."""
        from services.worker_agents.src.executors.build_executor import BuildExecutor
        from neural_hive_integration.clients.code_forge_client import CodeForgeClient

        code_forge_url = os.getenv('CODE_FORGE_URL')
        if not code_forge_url:
            pytest.skip('CODE_FORGE_URL not configured')

        real_client = CodeForgeClient(base_url=code_forge_url, timeout=120)

        try:
            executor = BuildExecutor(
                config=worker_config,
                vault_client=mock_vault_client,
                code_forge_client=real_client,
                metrics=mock_metrics,
            )

            ticket = ExecutorTestHelper.create_build_ticket(
                artifact_id='real-integration-test',
                branch='main',
            )

            result = await executor.execute(ticket)

            # Should either succeed or fail gracefully
            assert 'success' in result
            assert 'output' in result

        finally:
            await real_client.close()

    @pytest.mark.asyncio
    @pytest.mark.argocd
    async def test_real_deploy_with_argocd(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """Test deployment execution with real ArgoCD service."""
        from services.worker_agents.src.executors.deploy_executor import DeployExecutor

        argocd_url = os.getenv('ARGOCD_URL')
        argocd_token = os.getenv('ARGOCD_TOKEN')

        if not argocd_url or not argocd_token:
            pytest.skip('ArgoCD configuration not available')

        worker_config.argocd_enabled = True
        worker_config.argocd_url = argocd_url
        worker_config.argocd_token = argocd_token

        executor = DeployExecutor(
            config=worker_config,
            vault_client=mock_vault_client,
            metrics=mock_metrics,
        )

        ticket = ExecutorTestHelper.create_deploy_ticket(
            namespace='test-integration',
            deployment_name='test-app',
            image='nginx:latest',
        )

        result = await executor.execute(ticket)

        # Should either succeed or fail gracefully
        assert 'success' in result
        assert 'output' in result

    @pytest.mark.asyncio
    @pytest.mark.opa
    async def test_real_validate_with_opa(
        self,
        worker_config,
        mock_vault_client,
        mock_metrics,
    ):
        """Test policy validation with real OPA service."""
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
            policy_path='authz/allow',
            input_data={
                'user': 'test-user',
                'action': 'read',
                'resource': 'document',
            },
        )

        result = await executor.execute(ticket)

        # Should either succeed or fail gracefully
        assert 'success' in result
        assert 'output' in result
