"""Unit tests para models."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from src.models.hypothesis import (
    Hypothesis,
    HypothesisCreate,
    HypothesisUpdate,
    HypothesisFilter,
    HypothesisStatus,
    HypothesisPriority,
    HypothesisResults,
    PyObjectId,
)
from src.models.hypothesis_version import HypothesisVersion, VersionDiff
from src.models.workflow import (
    HypothesisWorkflow,
    WorkflowTransition,
    TransitionError,
    HypothesisStatus as WorkflowStatus,
)


class TestHypothesisModel:
    """Testes para Hypothesis model."""

    def test_create_hypothesis_minimal(self):
        """Testa criação de hipótese com dados mínimos."""
        data = HypothesisCreate(
            title="Test hypothesis",
            description="Test description",
            expected_outcome="Expected result",
            author="test-user",
        )

        hypothesis = Hypothesis(**data.model_dump())

        assert hypothesis.title == "Test hypothesis"
        assert hypothesis.description == "Test description"
        assert hypothesis.status == HypothesisStatus.DRAFT
        assert hypothesis.priority == HypothesisPriority.MEDIUM
        assert hypothesis.current_version == 1
        assert hypothesis.versions == [1]

    def test_hypothesis_with_all_fields(self):
        """Testa criação de hipótese com todos os campos."""
        data = HypothesisCreate(
            title="Complete hypothesis",
            description="Complete description",
            background="Background info",
            expected_outcome="Expected outcome",
            metrics=["metric1", "metric2"],
            baseline_metrics={"metric1": 100.0},
            target_metrics={"metric1": 90.0},
            priority=HypothesisPriority.CRITICAL,
            author="test-user",
            reviewers=["reviewer1", "reviewer2"],
            tags=["performance", "optimization"],
            requires_experiment=True,
            auto_approve=False,
        )

        hypothesis = Hypothesis(**data.model_dump())

        assert hypothesis.priority == HypothesisPriority.CRITICAL
        assert len(hypothesis.metrics) == 2
        assert hypothesis.baseline_metrics["metric1"] == 100.0
        assert len(hypothesis.reviewers) == 2
        assert len(hypothesis.tags) == 2

    def test_hypothesis_to_dict(self):
        """Testa conversão para dicionário."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id=str(uuid4()),
        )

        data = hypothesis.to_dict()

        assert "hypothesis_id" in data
        assert data["title"] == "Test"
        assert "status" in data

    def test_hypothesis_validation_empty_strings(self):
        """Testa validação de strings vazias."""
        with pytest.raises(ValueError):
            HypothesisCreate(
                title="",
                description="Description",
                expected_outcome="Outcome",
                author="user",
            )

        with pytest.raises(ValueError):
            HypothesisCreate(
                title="Title",
                description="   ",
                expected_outcome="Outcome",
                author="user",
            )


class TestHypothesisFilter:
    """Testes para HypothesisFilter."""

    def test_default_filter(self):
        """Testa filtro com valores padrão."""
        filter = HypothesisFilter()

        assert filter.limit == 50
        assert filter.offset == 0
        assert filter.sort_by == "created_at"
        assert filter.sort_order == -1
        assert filter.status is None

    def test_filter_with_status(self):
        """Testa filtro com status."""
        filter = HypothesisFilter(
            status=HypothesisStatus.PROPOSED,
            limit=10,
        )

        assert filter.status == HypothesisStatus.PROPOSED
        assert filter.limit == 10

    def test_filter_validation_invalid_sort_field(self):
        """Testa validação de campo de ordenação inválido."""
        with pytest.raises(ValueError):
            HypothesisFilter(sort_by="invalid_field")

    def test_filter_validation_valid_sort_fields(self):
        """Testa campos de ordenação válidos."""
        valid_fields = [
            "created_at",
            "updated_at",
            "title",
            "priority",
            "status",
            "proposed_at",
            "approved_at",
        ]

        for field in valid_fields:
            filter = HypothesisFilter(sort_by=field)
            assert filter.sort_by == field

    def test_filter_validation_limits(self):
        """Testa validação de limites."""
        # Limite válido
        filter = HypothesisFilter(limit=100, offset=10)
        assert filter.limit == 100
        assert filter.offset == 10

        # Limite máximo
        filter = HypothesisFilter(limit=200)
        assert filter.limit == 200

        # Limite inválido - acima do máximo
        with pytest.raises(ValueError):
            HypothesisFilter(limit=201)

        # Offset inválido - negativo
        with pytest.raises(ValueError):
            HypothesisFilter(offset=-1)


class TestHypothesisStatus:
    """Testes para HypothesisStatus enum."""

    def test_active_states(self):
        """Testa estados ativos."""
        active = HypothesisStatus.active_states()

        assert HypothesisStatus.DRAFT in active
        assert HypothesisStatus.PROPOSED in active
        assert HypothesisStatus.APPROVED in active
        assert HypothesisStatus.IN_TESTING in active
        assert HypothesisStatus.COMPLETED in active

        assert HypothesisStatus.ACCEPTED not in active
        assert HypothesisStatus.REJECTED not in active
        assert HypothesisStatus.ARCHIVED not in active

    def test_terminal_states(self):
        """Testa estados terminais."""
        terminal = HypothesisStatus.terminal_states()

        assert HypothesisStatus.ACCEPTED in terminal
        assert HypothesisStatus.REJECTED in terminal
        assert HypothesisStatus.ARCHIVED in terminal

        assert HypothesisStatus.DRAFT not in terminal


class TestHypothesisResults:
    """Testes para HypothesisResults."""

    def test_create_results(self):
        """Testa criação de resultados."""
        results = HypothesisResults(
            experiment_id="exp-123",
            status="completed",
            outcome="validated",
            confidence_level=0.95,
            improvement_percentage=15.5,
            statistical_significance=True,
        )

        assert results.experiment_id == "exp-123"
        assert results.outcome == "validated"
        assert results.confidence_level == 0.95
        assert results.statistical_significance is True

    def test_results_confidence_validation(self):
        """Testa validação de confiança."""
        # Válido
        HypothesisResults(confidence_level=0.5)

        # Inválido - acima de 1
        with pytest.raises(ValueError):
            HypothesisResults(confidence_level=1.5)

        # Inválido - abaixo de 0
        with pytest.raises(ValueError):
            HypothesisResults(confidence_level=-0.1)


class TestHypothesisVersion:
    """Testes para HypothesisVersion."""

    def test_from_hypothesis(self):
        """Testa criação de versão a partir de hipótese."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            current_version=2,
            hypothesis_id="hyp-123",
        )

        version = HypothesisVersion.from_hypothesis(
            hypothesis=hypothesis,
            created_by="user",
            change_reason="Updated",
            change_type="update",
        )

        assert version.hypothesis_id == "hyp-123"
        assert version.version_number == 2
        assert version.created_by == "user"
        assert version.change_reason == "Updated"
        assert version.change_type == "update"
        assert "hypothesis_id" in version.snapshot


class TestVersionDiff:
    """Testes para VersionDiff."""

    def test_compare_identical_snapshots(self):
        """Testa comparação de snapshots idênticos."""
        snapshot = {
            "title": "Title",
            "description": "Description",
            "status": "DRAFT",
            "priority": "MEDIUM",
        }

        diff = VersionDiff.compare(snapshot, snapshot)

        assert len(diff.changed_fields) == 0
        assert len(diff.changes) == 0

    def test_compare_different_snapshots(self):
        """Testa comparação de snapshots diferentes."""
        from_snapshot = {
            "title": "Old Title",
            "description": "Description",
            "status": "DRAFT",
            "priority": "MEDIUM",
            "current_version": 1,
        }

        to_snapshot = {
            "title": "New Title",
            "description": "Description",
            "status": "PROPOSED",
            "priority": "HIGH",
            "current_version": 2,
        }

        diff = VersionDiff.compare(from_snapshot, to_snapshot)

        assert len(diff.changed_fields) == 3
        assert "title" in diff.changed_fields
        assert "status" in diff.changed_fields
        assert "priority" in diff.changed_fields

        assert diff.changes["title"]["from"] == "Old Title"
        assert diff.changes["title"]["to"] == "New Title"


class TestHypothesisWorkflow:
    """Testes para HypothesisWorkflow."""

    def test_valid_transition_draft_to_proposed(self):
        """Testa transição válida DRAFT -> PROPOSED."""
        HypothesisWorkflow.validate_transition(
            WorkflowStatus.DRAFT,
            WorkflowStatus.PROPOSED,
            "author",
        )

    def test_invalid_transition_draft_to_approved(self):
        """Testa transição inválida DRAFT -> APPROVED."""
        with pytest.raises(TransitionError):
            HypothesisWorkflow.validate_transition(
                WorkflowStatus.DRAFT,
                WorkflowStatus.APPROVED,
                "author",
            )

    def test_transition_requires_reviewer_role(self):
        """Testa que aprovação requer papel de revisor."""
        with pytest.raises(TransitionError):
            HypothesisWorkflow.validate_transition(
                WorkflowStatus.PROPOSED,
                WorkflowStatus.APPROVED,
                "author",  # Deveria ser "reviewer"
            )

    def test_get_allowed_transitions_for_draft(self):
        """Testa transições permitidas para DRAFT."""
        allowed = HypothesisWorkflow.get_allowed_transitions(
            WorkflowStatus.DRAFT,
            "author",
        )

        assert WorkflowStatus.PROPOSED in allowed
        assert WorkflowStatus.ARCHIVED in allowed
        assert WorkflowStatus.APPROVED not in allowed

    def test_get_allowed_transitions_for_proposed_author(self):
        """Testa transições permitidas para PROPOSED como author."""
        allowed = HypothesisWorkflow.get_allowed_transitions(
            WorkflowStatus.PROPOSED,
            "author",
        )

        # Author pode voltar para DRAFT
        assert WorkflowStatus.DRAFT in allowed
        # Mas não pode aprovar (requer reviewer)
        assert WorkflowStatus.APPROVED not in allowed

    def test_get_allowed_transitions_for_proposed_reviewer(self):
        """Testa transições permitidas para PROPOSED como reviewer."""
        allowed = HypothesisWorkflow.get_allowed_transitions(
            WorkflowStatus.PROPOSED,
            "reviewer",
        )

        # Reviewer pode aprovar ou rejeitar
        assert WorkflowStatus.APPROVED in allowed
        assert WorkflowStatus.REJECTED in allowed

    def test_can_propose(self):
        """Testa verificação se pode propor."""
        assert HypothesisWorkflow.can_propose(WorkflowStatus.DRAFT) is True
        assert HypothesisWorkflow.can_propose(WorkflowStatus.PROPOSED) is False

    def test_can_approve(self):
        """Testa verificação se pode aprovar."""
        assert HypothesisWorkflow.can_approve(WorkflowStatus.PROPOSED) is True
        assert HypothesisWorkflow.can_approve(WorkflowStatus.DRAFT) is False

    def test_can_start_test(self):
        """Testa verificação se pode iniciar teste."""
        assert HypothesisWorkflow.can_start_test(WorkflowStatus.APPROVED) is True
        assert HypothesisWorkflow.can_start_test(WorkflowStatus.PROPOSED) is False

    def test_can_complete(self):
        """Testa verificação se pode completar."""
        assert HypothesisWorkflow.can_complete(WorkflowStatus.COMPLETED) is True
        assert HypothesisWorkflow.can_complete(WorkflowStatus.IN_TESTING) is False

    def test_can_archive(self):
        """Testa verificação se pode arquivar."""
        assert HypothesisWorkflow.can_archive(WorkflowStatus.ACCEPTED) is True
        assert HypothesisWorkflow.can_archive(WorkflowStatus.REJECTED) is True
        assert HypothesisWorkflow.can_archive(WorkflowStatus.DRAFT) is True
        assert HypothesisWorkflow.can_archive(WorkflowStatus.IN_TESTING) is False

    def test_is_terminal(self):
        """Testa verificação de estado terminal."""
        assert HypothesisWorkflow.is_terminal(WorkflowStatus.ARCHIVED) is True
        assert HypothesisWorkflow.is_terminal(WorkflowStatus.DRAFT) is False

    def test_get_next_suggested(self):
        """Testa sugestão de próximo estado."""
        assert HypothesisWorkflow.get_next_suggested(WorkflowStatus.DRAFT) == WorkflowStatus.PROPOSED
        assert HypothesisWorkflow.get_next_suggested(WorkflowStatus.PROPOSED) == WorkflowStatus.APPROVED
        assert HypothesisWorkflow.get_next_suggested(WorkflowStatus.APPROVED) == WorkflowStatus.IN_TESTING
        assert HypothesisWorkflow.get_next_suggested(WorkflowStatus.IN_TESTING) == WorkflowStatus.COMPLETED
        assert HypothesisWorkflow.get_next_suggested(WorkflowStatus.COMPLETED) == WorkflowStatus.ACCEPTED


class TestWorkflowTransition:
    """Testes para WorkflowTransition."""

    def test_create_transition(self):
        """Testa criação de transição."""
        transition = WorkflowTransition(
            from_status=HypothesisStatus.DRAFT,
            to_status=HypothesisStatus.PROPOSED,
            transitioned_by="user",
            reason="Proposta para revisão",
        )

        assert transition.from_status == HypothesisStatus.DRAFT
        assert transition.to_status == HypothesisStatus.PROPOSED
        assert transition.transitioned_by == "user"
        assert transition.reason == "Proposta para revisão"
        assert isinstance(transition.transitioned_at, datetime)

    def test_transition_with_metadata(self):
        """Testa transição com metadados."""
        metadata = {
            "reviewer_comments": "Looks good",
            "priority_changed": False,
        }

        transition = WorkflowTransition(
            from_status=HypothesisStatus.PROPOSED,
            to_status=HypothesisStatus.APPROVED,
            transitioned_by="reviewer",
            metadata=metadata,
        )

        assert transition.metadata == metadata
        assert transition.metadata["reviewer_comments"] == "Looks good"
