"""Unit tests para services."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from src.models.hypothesis import (
    Hypothesis,
    HypothesisCreate,
    HypothesisUpdate,
    HypothesisStatus,
    HypothesisPriority,
    HypothesisResults,
)
from src.models.workflow import TransitionError, WorkflowTransition
from src.services.hypothesis_service import HypothesisService
from src.services.versioning_service import VersioningService


class TestVersioningService:
    """Testes para VersioningService."""

    @pytest.fixture
    def version_repository(self):
        """Mock version repository."""
        return AsyncMock()

    @pytest.fixture
    def versioning_service(self, version_repository):
        """Instância do service."""
        return VersioningService(version_repository)

    @pytest.fixture
    def sample_hypothesis(self):
        """Hipótese de exemplo."""
        return Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            current_version=1,
        )

    @pytest.mark.asyncio
    async def test_create_version(self, versioning_service, version_repository, sample_hypothesis):
        """Testa criação de versão."""
        from src.models.hypothesis_version import HypothesisVersion

        version_repository.save.return_value = HypothesisVersion(
            version_id="hyp-123:1",
            hypothesis_id="hyp-123",
            version_number=1,
            snapshot={},
            created_by="user",
        )

        version = await versioning_service.create_version(
            hypothesis=sample_hypothesis,
            created_by="user",
            change_reason="Test",
        )

        assert version.hypothesis_id == "hyp-123"
        assert version.version_number == 1
        assert version.created_by == "user"
        version_repository.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_version_with_changes(
        self, versioning_service, version_repository, sample_hypothesis
    ):
        """Testa criação de versão com cálculo de mudanças."""
        from src.models.hypothesis_version import HypothesisVersion

        previous_snapshot = {
            "title": "Old Title",
            "description": "Description",
        }

        # Capturar o argumento passado para save
        saved_version = None

        def mock_save(version):
            nonlocal saved_version
            saved_version = version
            return version

        version_repository.save.side_effect = mock_save

        version = await versioning_service.create_version(
            hypothesis=sample_hypothesis,
            created_by="user",
            previous_snapshot=previous_snapshot,
        )

        assert "title" in saved_version.changes
        assert saved_version.changes["title"]["from"] == "Old Title"

    @pytest.mark.asyncio
    async def test_get_version_history(self, versioning_service, version_repository):
        """Testa busca de histórico de versões."""
        version_repository.list_versions.return_value = []

        history = await versioning_service.get_version_history("hyp-123")

        version_repository.list_versions.assert_called_once_with(
            hypothesis_id="hyp-123",
            limit=50,
        )

    @pytest.mark.asyncio
    async def test_compare_versions(self, versioning_service, version_repository):
        """Testa comparação entre versões."""
        version_repository.compare_versions.return_value = Mock()

        await versioning_service.compare_versions(
            hypothesis_id="hyp-123",
            from_version=1,
            to_version=2,
        )

        version_repository.compare_versions.assert_called_once_with(
            hypothesis_id="hyp-123",
            from_version=1,
            to_version=2,
        )


class TestHypothesisService:
    """Testes para HypothesisService."""

    @pytest.fixture
    def hypothesis_repository(self):
        """Mock hypothesis repository."""
        from src.models.hypothesis import Hypothesis, HypothesisStatus

        repo = AsyncMock()
        sample_hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="test-user",
            hypothesis_id=str(uuid4()),
            status=HypothesisStatus.DRAFT,
        )
        repo.create.return_value = sample_hypothesis
        repo.get_by_id.return_value = None
        return repo

    @pytest.fixture
    def versioning_service(self):
        """Mock versioning service."""
        return AsyncMock()

    @pytest.fixture
    def hypothesis_service(self, hypothesis_repository, versioning_service):
        """Instância do service."""
        return HypothesisService(hypothesis_repository, versioning_service)

    @pytest.fixture
    def sample_create_data(self):
        """Dados de criação de exemplo."""
        return HypothesisCreate(
            title="Test hypothesis",
            description="Test description",
            expected_outcome="Test outcome",
            author="test-user",
        )

    @pytest.mark.asyncio
    async def test_create_hypothesis(self, hypothesis_service, hypothesis_repository, sample_create_data):
        """Testa criação de hipótese."""
        created_hypothesis = await hypothesis_service.create(sample_create_data, author="user")

        assert created_hypothesis.status == HypothesisStatus.DRAFT
        hypothesis_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_versioning(
        self, hypothesis_service, hypothesis_repository, versioning_service, sample_create_data
    ):
        """Testa criação com versionamento."""
        created = await hypothesis_service.create(sample_create_data, author="user")

        assert versioning_service.create_version.called

    @pytest.mark.asyncio
    async def test_get_by_id(self, hypothesis_service, hypothesis_repository):
        """Testa busca por ID."""
        hypothesis_repository.get_by_id.return_value = Mock(
            hypothesis_id="hyp-123",
            title="Test",
        )

        result = await hypothesis_service.get_by_id("hyp-123")

        assert result is not None
        hypothesis_repository.get_by_id.assert_called_once_with("hyp-123")

    @pytest.mark.asyncio
    async def test_list_hypotheses(self, hypothesis_service, hypothesis_repository):
        """Testa listagem de hipóteses."""
        hypothesis_repository.list_by_filters.return_value = {
            "total": 10,
            "offset": 0,
            "limit": 50,
            "items": [],
        }

        result = await hypothesis_service.list()

        assert result["total"] == 10

    @pytest.mark.asyncio
    async def test_update_hypothesis(self, hypothesis_service, hypothesis_repository, versioning_service):
        """Testa atualização de hipótese."""
        hypothesis = Hypothesis(
            title="Old Title",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            current_version=1,
            versions=[1],
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.update.return_value = hypothesis

        update_data = HypothesisUpdate(title="New Title")

        result = await hypothesis_service.update("hyp-123", update_data, "user", create_version=False)

        assert result is not None
        hypothesis_repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_propose_hypothesis(self, hypothesis_service, hypothesis_repository):
        """Testa proposta de hipótese."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.DRAFT,
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.transition_status.return_value = (hypothesis, Mock())

        updated, transition = await hypothesis_service.propose("hyp-123", "user", "Reason")

        assert updated is not None
        assert transition is not None

    @pytest.mark.asyncio
    async def test_propose_invalid_transition(self, hypothesis_service, hypothesis_repository):
        """Testa proposta com transição inválida."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.PROPOSED,  # Já está proposto
        )
        hypothesis_repository.get_by_id.return_value = hypothesis

        with pytest.raises(TransitionError):
            await hypothesis_service.propose("hyp-123", "user")

    @pytest.mark.asyncio
    async def test_approve_hypothesis(self, hypothesis_service, hypothesis_repository):
        """Testa aprovação de hipótese."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.PROPOSED,
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.transition_status.return_value = (hypothesis, Mock())

        updated, transition = await hypothesis_service.approve("hyp-123", "reviewer")

        assert updated is not None

    @pytest.mark.asyncio
    async def test_reject_hypothesis(self, hypothesis_service, hypothesis_repository):
        """Testa rejeição de hipótese."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.PROPOSED,
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.transition_status.return_value = (hypothesis, Mock())

        updated, transition = await hypothesis_service.reject("hyp-123", "reviewer", "Not valid")

        assert updated is not None

    @pytest.mark.asyncio
    async def test_start_testing(self, hypothesis_service, hypothesis_repository):
        """Testa início de teste."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.APPROVED,
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.set_experiment_id.return_value = True
        hypothesis_repository.transition_status.return_value = (hypothesis, Mock())

        updated, transition = await hypothesis_service.start_testing(
            "hyp-123", "exp-123", "system"
        )

        assert updated is not None
        hypothesis_repository.set_experiment_id.assert_called_once_with("hyp-123", "exp-123")

    @pytest.mark.asyncio
    async def test_complete_testing(self, hypothesis_service, hypothesis_repository):
        """Testa conclusão de teste."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.IN_TESTING,
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.set_results.return_value = True
        hypothesis_repository.transition_status.return_value = (hypothesis, Mock())

        results = HypothesisResults(
            experiment_id="exp-123",
            status="completed",
            outcome="validated",
            confidence_level=0.95,
        )

        updated, transition = await hypothesis_service.complete("hyp-123", results)

        assert updated is not None
        hypothesis_repository.set_results.assert_called_once()

    @pytest.mark.asyncio
    async def test_accept_hypothesis(self, hypothesis_service, hypothesis_repository):
        """Testa aceitação de hipótese."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.COMPLETED,
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.transition_status.return_value = (hypothesis, Mock())

        updated, transition = await hypothesis_service.accept("hyp-123", "reviewer")

        assert updated is not None

    @pytest.mark.asyncio
    async def test_archive_hypothesis(self, hypothesis_service, hypothesis_repository):
        """Testa arquivamento de hipótese."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.REJECTED,  # REJECTED pode ser arquivado por qualquer um
        )
        hypothesis_repository.get_by_id.return_value = hypothesis
        hypothesis_repository.transition_status.return_value = (hypothesis, Mock())

        updated, transition = await hypothesis_service.archive("hyp-123", "user")

        assert updated is not None

    @pytest.mark.asyncio
    async def test_delete_hypothesis(self, hypothesis_service, hypothesis_repository):
        """Testa remoção (soft delete) de hipótese."""
        hypothesis_repository.delete.return_value = True

        result = await hypothesis_service.delete("hyp-123")

        assert result is True
        hypothesis_repository.delete.assert_called_once_with("hyp-123")

    @pytest.mark.asyncio
    async def test_get_allowed_transitions(self, hypothesis_service, hypothesis_repository):
        """Testa obtenção de transições permitidas."""
        hypothesis = Hypothesis(
            title="Test",
            description="Description",
            expected_outcome="Outcome",
            author="user",
            hypothesis_id="hyp-123",
            status=HypothesisStatus.DRAFT,
        )
        hypothesis_repository.get_by_id.return_value = hypothesis

        transitions = await hypothesis_service.get_allowed_transitions("hyp-123", "author")

        assert HypothesisStatus.PROPOSED in transitions
        assert HypothesisStatus.APPROVED not in transitions

    @pytest.mark.asyncio
    async def test_get_aggregations(self, hypothesis_service, hypothesis_repository):
        """Testa obtenção de agregações."""
        hypothesis_repository.get_aggregations.return_value = {
            "total": 100,
            "by_status": {},
        }

        result = await hypothesis_service.get_aggregations()

        assert result["total"] == 100
