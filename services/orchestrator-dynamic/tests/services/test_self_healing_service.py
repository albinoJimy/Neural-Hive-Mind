"""
Tests for SelfHealingService.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.self_healing_service import (
    CorrectionAction,
    CorrectionStrategy,
    FailureType,
    SelfHealingService,
    WorkflowFailure,
)


@pytest.fixture(autouse=True)
def mock_tracer():
    """Mock tracer para evitar erros de None."""
    with patch("src.services.self_healing_service.get_tracer") as mock:
        tracer = MagicMock()
        mock.return_value = tracer
        yield tracer


class TestWorkflowFailure:
    """Testes para WorkflowFailure."""

    def test_creation(self):
        """Testa criação de WorkflowFailure."""
        failure = WorkflowFailure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_type=FailureType.TIMEOUT,
            activity_name="test_activity",
            error_message="Task timed out",
        )

        assert failure.workflow_id == "wf-123"
        assert failure.run_id == "run-456"
        assert failure.failure_type == FailureType.TIMEOUT
        assert failure.activity_name == "test_activity"
        assert failure.error_message == "Task timed out"

    def test_to_dict(self):
        """Testa conversão para dict."""
        failure = WorkflowFailure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_type=FailureType.ACTIVITY_FAILURE,
            error_message="Activity failed",
        )

        data = failure.to_dict()

        assert data["workflow_id"] == "wf-123"
        assert data["run_id"] == "run-456"
        assert data["failure_type"] == "activity_failure"
        assert "timestamp" in data


class TestCorrectionAction:
    """Testes para CorrectionAction."""

    def test_creation(self):
        """Testa criação de CorrectionAction."""
        action = CorrectionAction(
            strategy=CorrectionStrategy.RETRY,
            description="Retry activity",
            parameters={"backoff_ms": 1000},
        )

        assert action.strategy == CorrectionStrategy.RETRY
        assert action.description == "Retry activity"
        assert action.parameters["backoff_ms"] == 1000
        assert action.executed is False

    def test_to_dict(self):
        """Testa conversão para dict."""
        action = CorrectionAction(
            strategy=CorrectionStrategy.ESCALATION,
            description="Escalate to human",
            requires_approval=True,
        )

        data = action.to_dict()

        assert data["strategy"] == "escalation"
        assert data["description"] == "Escalate to human"
        assert data["requires_approval"] is True


class TestSelfHealingService:
    """Testes para SelfHealingService."""

    @pytest.fixture
    def service(self):
        """Fixture para serviço."""
        return SelfHealingService()

    def test_initialization(self, service):
        """Testa inicialização padrão."""
        assert service.enable_auto_correction is True
        assert service.enable_auto_retry is True
        assert service.max_retry_attempts == 3
        assert service.retry_backoff_ms == 1000

    def test_classify_timeout_failure(self, service):
        """Testa classificação de timeout."""
        failure_type = service._classify_failure("Task timed out after 30 seconds", "TimeoutError")

        assert failure_type == FailureType.TIMEOUT

    def test_classify_permission_failure(self, service):
        """Testa classificação de permissão."""
        failure_type = service._classify_failure(
            "Permission denied to access resource", "PermissionError"
        )

        assert failure_type == FailureType.PERMISSION_DENIED

    def test_classify_validation_failure(self, service):
        """Testa classificação de validação."""
        failure_type = service._classify_failure("Validation failed: Invalid schema", "ValueError")

        assert failure_type == FailureType.VALIDATION_ERROR

    def test_classify_resource_unavailable_failure(self, service):
        """Testa classificação de recurso indisponível."""
        failure_type = service._classify_failure(
            "Service temporarily unavailable", "ConnectionError"
        )

        assert failure_type == FailureType.RESOURCE_UNAVAILABLE

    def test_classify_unknown_failure(self, service):
        """Testa classificação de falha desconhecida."""
        failure_type = service._classify_failure("Something went wrong", "RuntimeError")

        assert failure_type == FailureType.UNKNOWN

    @pytest.mark.asyncio
    async def test_analyze_failure(self, service):
        """Testa análise de falha."""
        error = Exception("Task timed out")

        failure = await service.analyze_failure(
            workflow_id="wf-123",
            run_id="run-456",
            error=error,
            activity_name="test_activity",
        )

        assert failure.workflow_id == "wf-123"
        assert failure.run_id == "run-456"
        assert failure.activity_name == "test_activity"
        assert failure.failure_type == FailureType.TIMEOUT

    @pytest.mark.asyncio
    async def test_suggest_correction_for_timeout(self, service):
        """Testa sugestão de correção para timeout."""
        failure = WorkflowFailure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_type=FailureType.TIMEOUT,
            activity_name="test_activity",
        )

        correction = await service.suggest_correction(failure, retry_count=0)

        assert correction.strategy == CorrectionStrategy.PARAMETER_ADJUSTMENT
        assert "timeout" in correction.description.lower()
        assert correction.parameters.get("timeout_multiplier") == 2.0

    @pytest.mark.asyncio
    async def test_suggest_correction_for_permission(self, service):
        """Testa sugestão de correção para permissão."""
        failure = WorkflowFailure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_type=FailureType.PERMISSION_DENIED,
            activity_name="test_activity",
        )

        correction = await service.suggest_correction(failure, retry_count=0)

        assert correction.strategy == CorrectionStrategy.ESCALATION
        assert correction.requires_approval is True

    @pytest.mark.asyncio
    async def test_suggest_correction_after_max_retries(self, service):
        """Testa sugestão após máximo de retries."""
        failure = WorkflowFailure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_type=FailureType.ACTIVITY_FAILURE,
            activity_name="test_activity",
        )

        correction = await service.suggest_correction(failure, retry_count=3)

        assert correction.strategy == CorrectionStrategy.ESCALATION
        assert correction.requires_approval is True

    @pytest.mark.asyncio
    async def test_execute_retry_correction(self, service):
        """Testa execução de correção de retry."""
        correction = CorrectionAction(
            strategy=CorrectionStrategy.RETRY,
            description="Retry activity",
            parameters={"backoff_ms": 1000},
        )

        result = await service.execute_correction(correction, "wf-123")

        assert result["status"] == "retry_scheduled"
        assert result["backoff_ms"] == 1000

    @pytest.mark.asyncio
    async def test_execute_escalation_correction(self, service):
        """Testa execução de correção de escalation."""
        correction = CorrectionAction(
            strategy=CorrectionStrategy.ESCALATION,
            description="Escalate to human",
            requires_approval=True,
        )

        result = await service.execute_correction(correction, "wf-123")

        assert result["status"] == "escalated"
        assert result["requires_human_intervention"] is True

    def test_record_failure(self, service):
        """Testa registro de falha no histórico."""
        failure = WorkflowFailure(
            workflow_id="wf-123",
            run_id="run-456",
            failure_type=FailureType.TIMEOUT,
            activity_name="test_activity",
        )

        service._record_failure(failure)

        key = "wf-123:test_activity"
        assert key in service.failure_history
        assert len(service.failure_history[key]) == 1
        assert service.failure_history[key][0] == failure

    def test_merge_inputs(self, service):
        """Testa merge de inputs."""
        original = {"param1": "value1", "param2": "value2"}
        corrections = {"param2": "corrected", "param3": "value3"}

        merged = service._merge_inputs(original, corrections)

        assert merged["param1"] == "value1"
        assert merged["param2"] == "corrected"
        assert merged["param3"] == "value3"

    @pytest.mark.asyncio
    async def test_failure_pattern_accumulation(self, service):
        """Testa acumulação de padrões de falha."""
        # Registrar múltiplas falhas
        for i in range(5):
            failure = WorkflowFailure(
                workflow_id="wf-123",
                run_id=f"run-{i}",
                failure_type=FailureType.TIMEOUT,
                activity_name="test_activity",
            )
            service._record_failure(failure)

        key = "wf-123:test_activity"
        assert len(service.failure_history[key]) == 5

    @pytest.mark.asyncio
    async def test_correction_sets_executed_flag(self, service):
        """Testa que execução marca flag executed."""
        correction = CorrectionAction(
            strategy=CorrectionStrategy.RETRY,
            description="Retry",
        )

        assert correction.executed is False

        await service.execute_correction(correction, "wf-123")

        assert correction.executed is True
        assert correction.executed_at is not None
        assert correction.result is not None


class TestCorrectionStrategyEnum:
    """Testes para CorrectionStrategy enum."""

    def test_all_strategies(self):
        """Testa todas as estratégias disponíveis."""
        assert CorrectionStrategy.RETRY.value == "retry"
        assert CorrectionStrategy.PARAMETER_ADJUSTMENT.value == "parameter_adjustment"
        assert CorrectionStrategy.FALLBACK.value == "fallback"
        assert CorrectionStrategy.ESCALATION.value == "escalation"
        assert CorrectionStrategy.SKIP.value == "skip"


class TestFailureTypeEnum:
    """Testes para FailureType enum."""

    def test_all_types(self):
        """Testa todos os tipos disponíveis."""
        assert FailureType.ACTIVITY_FAILURE.value == "activity_failure"
        assert FailureType.TIMEOUT.value == "timeout"
        assert FailureType.RESOURCE_UNAVAILABLE.value == "resource_unavailable"
        assert FailureType.PERMISSION_DENIED.value == "permission_denied"
        assert FailureType.VALIDATION_ERROR.value == "validation_error"
        assert FailureType.UNKNOWN.value == "unknown"
