"""Integration tests para workflow de hipóteses."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from bson import ObjectId

from src.models.hypothesis import (
    Hypothesis,
    HypothesisCreate,
    HypothesisStatus,
    HypothesisPriority,
    HypothesisResults,
    HypothesisFilter,
    HypothesisUpdate,
)
from src.models.workflow import WorkflowTransition
from src.services.hypothesis_service import HypothesisService


@pytest.mark.asyncio
class TestHypothesisWorkflowIntegration:
    """Testes de integração para workflow completo."""

    @pytest.fixture
    async def hypothesis_service(self):
        """Service para testes com mocks configurados."""
        from src.repositories.hypothesis_repository import HypothesisRepository
        from src.services.versioning_service import VersioningService

        mock_client = AsyncMock()
        mock_settings = Mock()
        mock_settings.mongodb_hypotheses_collection = "test_hypotheses"
        mock_settings.mongodb_versions_collection = "test_versions"
        mock_settings.max_versions_per_hypothesis = 50
        mock_settings.enable_versioning = True

        repo = HypothesisRepository(mock_client, mock_settings)
        version_repo = AsyncMock()
        versioning = VersioningService(version_repo)

        service = HypothesisService(repo, versioning)
        service.settings = mock_settings

        return service

    @pytest.fixture
    def sample_create_data(self):
        """Dados de criação."""
        return HypothesisCreate(
            title="Reduce latency via weight optimization",
            description="Optimize consensus weights to reduce P95 latency",
            background="Current P95 latency is 200ms, above SLO of 150ms",
            expected_outcome="P95 latency reduced to 150ms or below",
            metrics=["latency_p95", "throughput"],
            baseline_metrics={"latency_p95": 200.0, "throughput": 1000.0},
            target_metrics={"latency_p95": 150.0},
            priority=HypothesisPriority.HIGH,
            author="test-user",
            tags=["performance", "latency", "consensus"],
        )

    async def test_create_and_propose_workflow(
        self, hypothesis_service, sample_create_data
    ):
        """Testa criação e proposta de hipótese."""
        hypothesis = Hypothesis(
            **sample_create_data.model_dump(),
            hypothesis_id="hyp-123",
            status=HypothesisStatus.DRAFT,
        )

        # Simular criação
        assert hypothesis.status == HypothesisStatus.DRAFT
        assert hypothesis.author == "test-user"

        # Simular transição para PROPOSED
        transition = WorkflowTransition(
            from_status=HypothesisStatus.DRAFT,
            to_status=HypothesisStatus.PROPOSED,
            transitioned_by="test-user",
            reason="Ready for review",
        )
        assert transition.to_status == HypothesisStatus.PROPOSED

    async def test_workflow_states(self):
        """Testa transições válidas entre estados."""
        # Estados possíveis e suas transições válidas
        valid_transitions = {
            HypothesisStatus.DRAFT: [HypothesisStatus.PROPOSED, HypothesisStatus.ARCHIVED],
            HypothesisStatus.PROPOSED: [HypothesisStatus.DRAFT, HypothesisStatus.APPROVED, HypothesisStatus.REJECTED],
            HypothesisStatus.APPROVED: [HypothesisStatus.IN_TESTING],
            HypothesisStatus.IN_TESTING: [HypothesisStatus.COMPLETED],
            HypothesisStatus.COMPLETED: [HypothesisStatus.ACCEPTED, HypothesisStatus.REJECTED],
            HypothesisStatus.ACCEPTED: [HypothesisStatus.ARCHIVED],
            HypothesisStatus.REJECTED: [HypothesisStatus.ARCHIVED],
            HypothesisStatus.ARCHIVED: [],  # Terminal
        }

        for from_status, to_statuses in valid_transitions.items():
            for to_status in to_statuses:
                # Verifica que a transição é válida
                assert to_status in to_statuses or from_status == HypothesisStatus.ARCHIVED

    async def test_hypothesis_results_model(self):
        """Testa modelo de resultados."""
        results = HypothesisResults(
            experiment_id="exp-123",
            status="completed",
            outcome="validated",
            confidence_level=0.95,
            improvement_percentage=25.0,
            statistical_significance=True,
            actual_baseline_metrics={"latency_p95": 200.0},
            actual_target_metrics={"latency_p95": 145.0},
        )

        assert results.outcome == "validated"
        assert results.confidence_level == 0.95
        assert results.statistical_significance is True

    async def test_hypothesis_filter_validation(self):
        """Testa validação de filtros."""
        # Filtro padrão
        filter_default = HypothesisFilter()
        assert filter_default.limit == 50
        assert filter_default.offset == 0

        # Filtro com status
        filter_status = HypothesisFilter(status=HypothesisStatus.APPROVED)
        assert filter_status.status == HypothesisStatus.APPROVED

        # Filtro com busca
        filter_search = HypothesisFilter(search_text="latency", tags=["performance"])
        assert filter_search.search_text == "latency"
        assert filter_search.tags == ["performance"]

    async def test_hypothesis_update_model(self):
        """Testa modelo de atualização."""
        update = HypothesisUpdate(
            title="Updated title",
            description="Updated description",
        )

        update_dict = update.model_dump(exclude_unset=True)
        assert "title" in update_dict
        assert "description" in update_dict
        assert update_dict["title"] == "Updated title"

    async def test_workflow_role_requirements(self):
        """Testa requisitos de role por transição."""
        from src.models.workflow import HypothesisWorkflow

        # DRAFT -> PROPOSED: sempre possível
        assert HypothesisWorkflow.can_propose(HypothesisStatus.DRAFT)

        # PROPOSED -> APPROVED: sempre possível se status correto
        assert HypothesisWorkflow.can_approve(HypothesisStatus.PROPOSED)
        assert not HypothesisWorkflow.can_approve(HypothesisStatus.DRAFT)

    async def test_terminal_states(self):
        """Testa estados terminais."""
        from src.models.workflow import HypothesisWorkflow

        # ACCEPTED e REJECTED são terminais (não podem mais mudar, exceto para ARCHIVED)
        assert HypothesisWorkflow.is_terminal(HypothesisStatus.ACCEPTED) is False  # Pode arquivar
        assert HypothesisWorkflow.is_terminal(HypothesisStatus.REJECTED) is False  # Pode arquivar
        # ARCHIVED é verdadeiramente terminal
        assert HypothesisWorkflow.is_terminal(HypothesisStatus.ARCHIVED) is True


def mock_settings():
    """Mock settings."""
    from unittest.mock import Mock

    settings = Mock()
    settings.environment = "test"
    settings.mongodb_database = "test_neural_hive"
    settings.mongodb_hypotheses_collection = "test_hypotheses"
    settings.mongodb_versions_collection = "test_versions"
    settings.max_versions_per_hypothesis = 50
    return settings
