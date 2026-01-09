"""
Unit tests for plan_validation activities.

Tests cover:
- validate_cognitive_plan with valid and invalid plans
- DAG validation (execution_order references, dependencies)
- OPA integration (mocked)
- audit_validation persistence (fail-open behavior)
- optimize_dag cycle detection
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.activities.plan_validation import (
    validate_cognitive_plan,
    audit_validation,
    optimize_dag,
    set_activity_dependencies
)


@pytest.fixture
def mock_activity_info():
    """Mock activity.info() for workflow context."""
    with patch('src.activities.plan_validation.activity') as mock_activity:
        mock_info = MagicMock()
        mock_info.workflow_id = 'test-workflow-123'
        mock_activity.info.return_value = mock_info
        mock_activity.logger = MagicMock()
        yield mock_activity


@pytest.fixture
def valid_plan():
    """Create a valid cognitive plan."""
    return {
        'plan_id': 'test-plan-001',
        'tasks': [
            {'task_id': 'task-1', 'dependencies': [], 'description': 'First task'},
            {'task_id': 'task-2', 'dependencies': ['task-1'], 'description': 'Second task'},
            {'task_id': 'task-3', 'dependencies': ['task-2'], 'description': 'Third task'}
        ],
        'execution_order': ['task-1', 'task-2', 'task-3'],
        'risk_score': 0.5,
        'risk_band': 'medium',
        'schema_version': 1
    }


@pytest.fixture
def mock_policy_validator():
    """Create mock policy validator."""
    validator = AsyncMock()
    result = MagicMock()
    result.valid = True
    result.violations = []
    result.warnings = []
    result.policy_decisions = {}
    validator.validate_cognitive_plan.return_value = result
    return validator


@pytest.fixture
def mock_config():
    """Create mock config."""
    config = MagicMock()
    config.opa_enabled = True
    config.opa_fail_open = True
    return config


@pytest.fixture
def mock_mongodb_client():
    """Create mock MongoDB client."""
    client = AsyncMock()
    client.save_validation_audit = AsyncMock()
    return client


class TestValidateCognitivePlan:
    """Tests for validate_cognitive_plan activity."""

    @pytest.mark.asyncio
    async def test_valid_plan_returns_valid_true(self, mock_activity_info, valid_plan):
        """Valid plan should return valid=True with no errors."""
        set_activity_dependencies(policy_validator=None, config=None, mongodb_client=None)

        result = await validate_cognitive_plan('test-plan-001', valid_plan)

        assert result['valid'] is True
        assert len(result['errors']) == 0
        assert 'validated_at' in result

    @pytest.mark.asyncio
    async def test_missing_required_fields_returns_errors(self, mock_activity_info):
        """Plan missing required fields should return errors."""
        incomplete_plan = {
            'plan_id': 'incomplete-plan',
            'tasks': []
            # Missing: execution_order, risk_score, risk_band
        }
        set_activity_dependencies(policy_validator=None, config=None, mongodb_client=None)

        result = await validate_cognitive_plan('incomplete-plan', incomplete_plan)

        assert result['valid'] is False
        assert len(result['errors']) >= 3
        assert any('execution_order' in e for e in result['errors'])
        assert any('risk_score' in e for e in result['errors'])
        assert any('risk_band' in e for e in result['errors'])

    @pytest.mark.asyncio
    async def test_expired_plan_returns_error(self, mock_activity_info, valid_plan):
        """Plan with expired valid_until should return error."""
        # Set valid_until to 1 hour ago (in milliseconds)
        past_time = datetime.now() - timedelta(hours=1)
        valid_plan['valid_until'] = int(past_time.timestamp() * 1000)
        set_activity_dependencies(policy_validator=None, config=None, mongodb_client=None)

        result = await validate_cognitive_plan('test-plan-001', valid_plan)

        assert result['valid'] is False
        assert any('expirado' in e or 'expired' in e.lower() for e in result['errors'])

    @pytest.mark.asyncio
    async def test_invalid_dag_task_not_in_execution_order(self, mock_activity_info):
        """Task referenced in execution_order but not defined should error."""
        invalid_dag_plan = {
            'plan_id': 'invalid-dag-plan',
            'tasks': [
                {'task_id': 'task-1', 'dependencies': []}
            ],
            'execution_order': ['task-1', 'task-nonexistent'],  # task-nonexistent doesn't exist
            'risk_score': 0.5,
            'risk_band': 'medium'
        }
        set_activity_dependencies(policy_validator=None, config=None, mongodb_client=None)

        result = await validate_cognitive_plan('invalid-dag-plan', invalid_dag_plan)

        assert result['valid'] is False
        assert any('task-nonexistent' in e for e in result['errors'])

    @pytest.mark.asyncio
    async def test_invalid_dependency_reference(self, mock_activity_info):
        """Task with non-existent dependency should error."""
        invalid_dep_plan = {
            'plan_id': 'invalid-dep-plan',
            'tasks': [
                {'task_id': 'task-1', 'dependencies': []},
                {'task_id': 'task-2', 'dependencies': ['task-nonexistent']}  # Invalid dependency
            ],
            'execution_order': ['task-1', 'task-2'],
            'risk_score': 0.5,
            'risk_band': 'medium'
        }
        set_activity_dependencies(policy_validator=None, config=None, mongodb_client=None)

        result = await validate_cognitive_plan('invalid-dep-plan', invalid_dep_plan)

        assert result['valid'] is False
        assert any('task-nonexistent' in e for e in result['errors'])

    @pytest.mark.asyncio
    async def test_opa_validation_with_violations(
        self, mock_activity_info, valid_plan, mock_config
    ):
        """OPA policy violations should be added to errors."""
        mock_validator = AsyncMock()
        violation = MagicMock()
        violation.policy_name = 'security-policy'
        violation.message = 'High risk operation not allowed'

        result_obj = MagicMock()
        result_obj.valid = False
        result_obj.violations = [violation]
        result_obj.warnings = []
        result_obj.policy_decisions = {}
        mock_validator.validate_cognitive_plan.return_value = result_obj

        set_activity_dependencies(
            policy_validator=mock_validator,
            config=mock_config,
            mongodb_client=None
        )

        result = await validate_cognitive_plan('test-plan-001', valid_plan)

        assert result['valid'] is False
        assert any('security-policy' in e for e in result['errors'])

    @pytest.mark.asyncio
    async def test_opa_validation_with_warnings(
        self, mock_activity_info, valid_plan, mock_policy_validator, mock_config
    ):
        """OPA policy warnings should be added to warnings list."""
        warning = MagicMock()
        warning.policy_name = 'cost-policy'
        warning.message = 'Operation may incur high costs'

        mock_policy_validator.validate_cognitive_plan.return_value.warnings = [warning]

        set_activity_dependencies(
            policy_validator=mock_policy_validator,
            config=mock_config,
            mongodb_client=None
        )

        result = await validate_cognitive_plan('test-plan-001', valid_plan)

        assert result['valid'] is True
        assert any('cost-policy' in w for w in result['warnings'])

    @pytest.mark.asyncio
    async def test_opa_failure_fail_open(
        self, mock_activity_info, valid_plan, mock_config
    ):
        """OPA failure with fail_open=True should not add error."""
        mock_validator = AsyncMock()
        mock_validator.validate_cognitive_plan.side_effect = Exception('OPA connection error')
        mock_config.opa_fail_open = True

        set_activity_dependencies(
            policy_validator=mock_validator,
            config=mock_config,
            mongodb_client=None
        )

        result = await validate_cognitive_plan('test-plan-001', valid_plan)

        # Should still be valid since fail_open=True
        assert result['valid'] is True


class TestAuditValidation:
    """Tests for audit_validation activity."""

    @pytest.mark.asyncio
    async def test_audit_saves_to_mongodb(
        self, mock_activity_info, mock_mongodb_client
    ):
        """Audit should persist to MongoDB when client is available."""
        set_activity_dependencies(
            policy_validator=None,
            config=None,
            mongodb_client=mock_mongodb_client
        )

        validation_result = {'valid': True, 'errors': [], 'warnings': []}

        await audit_validation('test-plan-001', validation_result)

        mock_mongodb_client.save_validation_audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_fail_open_when_mongodb_unavailable(self, mock_activity_info):
        """Audit should not raise when MongoDB is unavailable (fail-open)."""
        set_activity_dependencies(
            policy_validator=None,
            config=None,
            mongodb_client=None  # No MongoDB
        )

        validation_result = {'valid': True, 'errors': [], 'warnings': []}

        # Should not raise
        await audit_validation('test-plan-001', validation_result)

    @pytest.mark.asyncio
    async def test_audit_fail_open_on_mongodb_error(
        self, mock_activity_info, mock_mongodb_client
    ):
        """Audit should not raise on MongoDB error (fail-open)."""
        mock_mongodb_client.save_validation_audit.side_effect = Exception('MongoDB error')

        set_activity_dependencies(
            policy_validator=None,
            config=None,
            mongodb_client=mock_mongodb_client
        )

        validation_result = {'valid': True, 'errors': [], 'warnings': []}

        # Should not raise
        await audit_validation('test-plan-001', validation_result)


class TestOptimizeDag:
    """Tests for optimize_dag activity."""

    @pytest.mark.asyncio
    async def test_dag_without_cycles_returns_not_optimized(self, mock_activity_info):
        """DAG without cycles should return optimized=False."""
        tasks = [
            {'task_id': 'task-1', 'dependencies': []},
            {'task_id': 'task-2', 'dependencies': ['task-1']},
            {'task_id': 'task-3', 'dependencies': ['task-2']}
        ]
        execution_order = ['task-1', 'task-2', 'task-3']

        result = await optimize_dag(tasks, execution_order)

        assert result['optimized'] is False
        assert result['new_execution_order'] == execution_order
        assert result['removed_dependencies'] == []

    @pytest.mark.asyncio
    async def test_dag_with_cycle_returns_optimized(self, mock_activity_info):
        """DAG with cycle should be detected and return optimized=True."""
        tasks = [
            {'task_id': 'task-1', 'dependencies': ['task-3']},  # Cycle: 1 -> 3 -> 2 -> 1
            {'task_id': 'task-2', 'dependencies': ['task-1']},
            {'task_id': 'task-3', 'dependencies': ['task-2']}
        ]
        execution_order = ['task-1', 'task-2', 'task-3']

        result = await optimize_dag(tasks, execution_order)

        assert result['optimized'] is True

    @pytest.mark.asyncio
    async def test_dag_self_reference_cycle(self, mock_activity_info):
        """Task referencing itself should be detected as cycle."""
        tasks = [
            {'task_id': 'task-1', 'dependencies': ['task-1']}  # Self-reference
        ]
        execution_order = ['task-1']

        result = await optimize_dag(tasks, execution_order)

        assert result['optimized'] is True

    @pytest.mark.asyncio
    async def test_empty_dag(self, mock_activity_info):
        """Empty DAG should return not optimized."""
        tasks = []
        execution_order = []

        result = await optimize_dag(tasks, execution_order)

        assert result['optimized'] is False
        assert result['new_execution_order'] == []
