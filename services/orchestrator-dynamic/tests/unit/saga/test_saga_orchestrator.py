"""
Testes unitarios para SagaOrchestrator.

Testa a coordenacao de Sagas incluindo criacao, execucao,
tratamento de falhas e compensacao automatica.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Mock dos modulos problematicos antes de importar
sys.modules["neural_hive_resilience"] = MagicMock()

# Importar os tipos de status para comparacao
from src.saga.saga_state import SagaStatus, StepStatus


@pytest.fixture()
def mock_repository():
    """Mock do SagaRepository."""
    repo = AsyncMock()
    repo.save = AsyncMock(return_value=True)
    repo.find_by_id = AsyncMock()
    repo.find_by_workflow = AsyncMock()
    repo.find_by_status = AsyncMock(return_value=[])
    repo.find_pending_sagas = AsyncMock(return_value=[])
    repo.find_failed_sagas = AsyncMock(return_value=[])
    repo.update_status = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)
    repo.count_by_status = AsyncMock(return_value={})
    return repo


@pytest.fixture()
def mock_event_store():
    """Mock do SagaEventStore."""
    store = AsyncMock()
    store.record_event = AsyncMock(return_value=True)
    store.record_event_raw = AsyncMock(return_value=True)
    store.get_saga_events = AsyncMock(return_value=[])
    store.get_events_by_type = AsyncMock(return_value=[])
    store.get_latest_saga_status = AsyncMock(return_value=None)
    store.delete_saga_events = AsyncMock(return_value=0)
    return store


@pytest.fixture()
def orchestrator(mock_repository, mock_event_store):
    """SagaOrchestrator com mocks."""
    from src.saga.saga_orchestrator import SagaOrchestrator

    return SagaOrchestrator(repository=mock_repository, event_store=mock_event_store)


@pytest.fixture()
def sample_step_definitions():
    """Definicoes de steps para teste."""
    return [
        {
            "name": "validate_plan",
            "action": "validate",
            "compensation_action": "invalidate",
            "parameters": {"plan_id": "plan-123"},
            "max_retries": 3,
        },
        {
            "name": "build_artifact",
            "action": "build",
            "compensation_action": "delete_artifacts",
            "parameters": {"artifact_id": "art-456"},
            "max_retries": 2,
        },
        {
            "name": "deploy_to_production",
            "action": "deploy",
            "compensation_action": "rollback_deployment",
            "parameters": {"namespace": "production"},
            "max_retries": 1,
        },
    ]


class TestCreateSaga:
    """Testes para create_saga."""

    @pytest.mark.asyncio()
    async def test_create_saga_with_steps(
        self, orchestrator, mock_repository, mock_event_store, sample_step_definitions
    ):
        """Deve criar saga com steps corretamente configurados."""
        saga = await orchestrator.create_saga(
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            steps=sample_step_definitions,
            metadata={"tenant": "acme"},
        )

        # Verificar campos principais
        assert saga.saga_id is not None
        assert len(saga.saga_id) == 36  # UUID format
        assert saga.workflow_id == "workflow-123"
        assert saga.plan_id == "plan-123"
        assert saga.intent_id == "intent-123"
        assert saga.status == SagaStatus.PENDING
        assert len(saga.steps) == 3

        # Verificar steps
        assert saga.steps[0].name == "validate_plan"
        assert saga.steps[0].action == "validate"
        assert saga.steps[0].compensation_action == "invalidate"
        assert saga.steps[0].status == StepStatus.PENDING
        assert saga.steps[0].max_retries == 3

        assert saga.steps[1].name == "build_artifact"
        assert saga.steps[2].name == "deploy_to_production"

        # Verificar ordem de compensacao (reversa)
        assert len(saga.compensation_order) == 3
        assert saga.compensation_order[0] == saga.steps[2].step_id
        assert saga.compensation_order[1] == saga.steps[1].step_id
        assert saga.compensation_order[2] == saga.steps[0].step_id

        # Verificar que foi persistido
        mock_repository.save.assert_called_once()

        # Verificar que evento foi registrado
        mock_event_store.record_event_raw.assert_called_once()
        call_args = mock_event_store.record_event_raw.call_args
        assert call_args[1]["saga_id"] == saga.saga_id

    @pytest.mark.asyncio()
    async def test_create_saga_without_metadata(self, orchestrator, mock_repository):
        """Deve criar saga sem metadados opcionais."""
        saga = await orchestrator.create_saga(
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            steps=[{"name": "test_step", "action": "test", "compensation_action": "rollback"}],
        )

        assert saga.metadata == {}
        mock_repository.save.assert_called_once()


class TestStartSaga:
    """Testes para start_saga."""

    @pytest.mark.asyncio()
    async def test_start_saga_updates_status(self, orchestrator, mock_repository, mock_event_store):
        """Deve atualizar status para STARTED."""
        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.PENDING,
            steps=[],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.start_saga("saga-123")

        assert result.status == SagaStatus.STARTED
        assert result.started_at is not None
        mock_repository.save.assert_called()
        mock_event_store.record_event_raw.assert_called()

    @pytest.mark.asyncio()
    async def test_start_saga_not_found_returns_none(self, orchestrator, mock_repository):
        """Deve retornar None se saga nao existe."""
        mock_repository.find_by_id = AsyncMock(return_value=None)

        result = await orchestrator.start_saga("nonexistent")

        assert result is None
        mock_repository.save.assert_not_called()

    @pytest.mark.asyncio()
    async def test_start_already_started_saga_returns_current(
        self, orchestrator, mock_repository, mock_event_store
    ):
        """Deve retornar saga atual se ja iniciada."""
        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.IN_PROGRESS,
            steps=[],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.start_saga("saga-123")

        # Nao deve mudar status nem chamar save
        assert result.status == SagaStatus.IN_PROGRESS
        mock_repository.save.assert_not_called()
        mock_event_store.record_event_raw.assert_not_called()


class TestCompleteStep:
    """Testes para complete_step."""

    @pytest.mark.asyncio()
    async def test_complete_step_updates_status(
        self, orchestrator, mock_repository, mock_event_store
    ):
        """Deve marcar step como completado e salvar."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep, StepStatus

        step = SagaStep(
            step_id="step-1",
            name="test_step",
            action="test",
            compensation_action="rollback",
            created_at=1000000,
        )

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.STARTED,
            steps=[step],
            compensation_order=[],
            created_at=1000000,
            current_step_index=0,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.complete_step(
            "saga-123", "step-1", result={"output": "success"}
        )

        assert result.status == SagaStatus.COMPLETED  # Unico step completado = saga completa
        assert step.status == StepStatus.COMPLETED
        assert step.result == {"output": "success"}
        assert step.completed_at is not None
        assert result.completed_at is not None

        mock_repository.save.assert_called()
        mock_event_store.record_event_raw.assert_called()

    @pytest.mark.asyncio()
    async def test_complete_step_with_next_pending(self, orchestrator, mock_repository):
        """Deve manter IN_PROGRESS se ha steps pendentes."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep, StepStatus

        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )

        step2 = SagaStep(
            step_id="step-2",
            name="second",
            action="b",
            compensation_action="rollback_b",
            created_at=1000000,
        )

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.STARTED,
            steps=[step1, step2],
            compensation_order=[],
            created_at=1000000,
            current_step_index=0,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.complete_step("saga-123", "step-1")

        assert result.status == SagaStatus.IN_PROGRESS
        assert result.current_step_index == 1
        assert step1.status == StepStatus.COMPLETED

    @pytest.mark.asyncio()
    async def test_complete_step_not_found_returns_none(self, orchestrator, mock_repository):
        """Deve retornar None se step nao existe."""
        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.STARTED,
            steps=[],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.complete_step("saga-123", "nonexistent")

        assert result is None
        mock_repository.save.assert_not_called()


class TestFailStep:
    """Testes para fail_step."""

    @pytest.mark.asyncio()
    async def test_fail_step_triggers_compensation(
        self, orchestrator, mock_repository, mock_event_store
    ):
        """Deve iniciar compensacao quando step falha."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep, StepStatus

        # Step ja completado (sera compensado)
        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )
        step1.mark_completed()

        # Step que falha
        step2 = SagaStep(
            step_id="step-2",
            name="second",
            action="b",
            compensation_action="rollback_b",
            created_at=1000000,
        )

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.IN_PROGRESS,
            steps=[step1, step2],
            compensation_order=[],
            created_at=1000000,
            current_step_index=1,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.fail_step("saga-123", "step-2", error="Connection timeout")

        assert result.status == SagaStatus.COMPENSATING
        assert step2.status == StepStatus.FAILED
        assert step2.error == "Connection timeout"
        assert result.error == "Connection timeout"

        mock_repository.save.assert_called()
        # Deve registrar falha do step e inicio de compensacao
        assert mock_event_store.record_event_raw.call_count == 2

    @pytest.mark.asyncio()
    async def test_fail_step_with_no_completed_marks_failed(self, orchestrator, mock_repository):
        """Deve marcar como FAILED se nenhum step completado."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep, StepStatus

        # Primeiro step falha antes de completar nada
        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.STARTED,
            steps=[step1],
            compensation_order=[],
            created_at=1000000,
            current_step_index=0,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.fail_step("saga-123", "step-1", error="Validation failed")

        assert result.status == SagaStatus.FAILED
        assert result.failed_at is not None
        assert step1.status == StepStatus.FAILED

    @pytest.mark.asyncio()
    async def test_fail_step_without_compensation(self, orchestrator, mock_repository):
        """Deve nao iniciar compensacao se parametro for False."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep

        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )
        step1.mark_completed()

        step2 = SagaStep(
            step_id="step-2",
            name="second",
            action="b",
            compensation_action="rollback_b",
            created_at=1000000,
        )

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.IN_PROGRESS,
            steps=[step1, step2],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.fail_step(
            "saga-123", "step-2", error="Error", trigger_compensation=False
        )

        # Nao deve iniciar compensacao
        assert result.status != SagaStatus.COMPENSATING


class TestCompensateStep:
    """Testes para compensate_step."""

    @pytest.mark.asyncio()
    async def test_compensate_step_marks_compensated(
        self, orchestrator, mock_repository, mock_event_store
    ):
        """Deve marcar step como compensado."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep, StepStatus

        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )
        step1.mark_completed()

        step2 = SagaStep(
            step_id="step-2",
            name="second",
            action="b",
            compensation_action="rollback_b",
            created_at=1000000,
        )
        step2.mark_completed()

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.COMPENSATING,
            steps=[step1, step2],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.compensate_step(
            "saga-123", "step-1", compensation_result={"rolled_back": True}
        )

        assert step1.status == StepStatus.COMPENSATED
        assert step1.compensated_at is not None
        assert step1.compensation_result == {"rolled_back": True}

        mock_repository.save.assert_called()
        mock_event_store.record_event_raw.assert_called()

    @pytest.mark.asyncio()
    async def test_compensate_all_steps_completes_saga(self, orchestrator, mock_repository):
        """Deve marcar saga como COMPENSATED quando todos steps compensados."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep

        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )
        step1.mark_completed()

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.COMPENSATING,
            steps=[step1],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.compensate_step("saga-123", "step-1")

        assert result.status == SagaStatus.COMPENSATED
        assert result.compensated_at is not None


class TestGetSagaState:
    """Testes para get_saga_state."""

    @pytest.mark.asyncio()
    async def test_get_saga_state_returns_saga(self, orchestrator, mock_repository):
        """Deve retornar estado da saga."""
        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.IN_PROGRESS,
            steps=[],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.get_saga_state("saga-123")

        assert result is not None
        assert result.saga_id == "saga-123"
        assert result.status == SagaStatus.IN_PROGRESS

    @pytest.mark.asyncio()
    async def test_get_saga_state_not_found_returns_none(self, orchestrator, mock_repository):
        """Deve retornar None se saga nao existe."""
        mock_repository.find_by_id = AsyncMock(return_value=None)

        result = await orchestrator.get_saga_state("nonexistent")

        assert result is None


class TestGetCurrentStep:
    """Testes para get_current_step."""

    @pytest.mark.asyncio()
    async def test_get_current_step(self, orchestrator, mock_repository):
        """Deve retornar step atual."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep

        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )

        step2 = SagaStep(
            step_id="step-2",
            name="second",
            action="b",
            compensation_action="rollback_b",
            created_at=1000000,
        )

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.IN_PROGRESS,
            steps=[step1, step2],
            compensation_order=[],
            created_at=1000000,
            current_step_index=1,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.get_current_step("saga-123")

        assert result is not None
        assert result.step_id == "step-2"

    @pytest.mark.asyncio()
    async def test_get_current_step_no_saga_returns_none(self, orchestrator, mock_repository):
        """Deve retornar None se saga nao existe."""
        mock_repository.find_by_id = AsyncMock(return_value=None)

        result = await orchestrator.get_current_step("nonexistent")

        assert result is None


class TestGetCompensationOrder:
    """Testes para get_compensation_order."""

    @pytest.mark.asyncio()
    async def test_get_compensation_order_returns_reversed_steps(
        self, orchestrator, mock_repository
    ):
        """Deve retornar steps na ordem reversa de execucao."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep

        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )
        step1.mark_completed()

        step2 = SagaStep(
            step_id="step-2",
            name="second",
            action="b",
            compensation_action="rollback_b",
            created_at=1000000,
        )
        step2.mark_completed()

        step3 = SagaStep(
            step_id="step-3",
            name="third",
            action="c",
            compensation_action="rollback_c",
            created_at=1000000,
        )
        # step3 ainda pendente

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.IN_PROGRESS,
            steps=[step1, step2, step3],
            compensation_order=[],
            created_at=1000000,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.get_compensation_order("saga-123")

        # So steps completados devem ser retornados, em ordem reversa
        assert len(result) == 2
        assert result[0].step_id == "step-2"
        assert result[1].step_id == "step-1"


class TestRetrySaga:
    """Testes para retry_saga."""

    @pytest.mark.asyncio()
    async def test_retry_saga_resets_state(self, orchestrator, mock_repository):
        """Deve resetar estado para nova tentativa."""
        from src.saga.saga_state import SagaState, SagaStatus, SagaStep, StepStatus

        step1 = SagaStep(
            step_id="step-1",
            name="first",
            action="a",
            compensation_action="rollback_a",
            created_at=1000000,
        )
        step1.mark_failed("Error")

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.FAILED,
            steps=[step1],
            compensation_order=[],
            created_at=1000000,
            retry_count=0,
            max_retries=2,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.retry_saga("saga-123")

        assert result.retry_count == 1
        assert result.status == SagaStatus.PENDING
        assert result.current_step_index == 0
        assert result.failed_at is None
        assert result.error is None
        assert step1.status == StepStatus.PENDING

        mock_repository.save.assert_called_once()

    @pytest.mark.asyncio()
    async def test_retry_saga_max_retries_returns_none(self, orchestrator, mock_repository):
        """Deve retornar None se maximo de retentativas atingido."""
        from src.saga.saga_state import SagaState, SagaStatus

        saga = SagaState(
            saga_id="saga-123",
            workflow_id="workflow-123",
            plan_id="plan-123",
            intent_id="intent-123",
            status=SagaStatus.FAILED,
            steps=[],
            compensation_order=[],
            created_at=1000000,
            retry_count=3,
            max_retries=3,
        )

        mock_repository.find_by_id = AsyncMock(return_value=saga)

        result = await orchestrator.retry_saga("saga-123")

        assert result is None
        mock_repository.save.assert_not_called()
