"""
Testes unitarios para ApprovalGate.

Cobertura:
- Aprovacao automatica
- Rejeicao automatica
- Revisao manual
- Thresholds de qualidade
- Criacao de Merge Request
"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestApprovalGateAutoApproval:
    """Testes de aprovacao automatica."""

    @pytest.mark.asyncio
    async def test_auto_approve_high_quality(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve aprovar automaticamente com score alto."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        # Simular score alto
        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.95)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        assert sample_pipeline_context_with_validations.metadata['approval'] == 'auto'
        mock_git_client.create_merge_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_approve_exactly_at_threshold(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve aprovar automaticamente quando score igual ao threshold."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.9)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        assert sample_pipeline_context_with_validations.metadata['approval'] == 'auto'


class TestApprovalGateAutoRejection:
    """Testes de rejeicao automatica."""

    @pytest.mark.asyncio
    async def test_auto_reject_low_quality(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve rejeitar automaticamente com score baixo."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.3)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            min_quality_score=0.5
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        assert sample_pipeline_context_with_validations.metadata['approval'] == 'rejected'

    @pytest.mark.asyncio
    async def test_auto_reject_critical_issues(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve rejeitar automaticamente com issues criticos."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.85)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=True)

        gate = ApprovalGate(
            git_client=mock_git_client
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        assert sample_pipeline_context_with_validations.metadata['approval'] == 'rejected'


class TestApprovalGateManualReview:
    """Testes de revisao manual."""

    @pytest.mark.asyncio
    async def test_manual_review_medium_quality(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve requerer revisao manual para score medio."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.75)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        assert sample_pipeline_context_with_validations.metadata['approval'] == 'manual'
        mock_git_client.create_merge_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_manual_review_creates_merge_request(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve criar Merge Request para revisao manual."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.7)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        mock_git_client.create_merge_request.assert_called_once()
        # Verificar que MR URL foi salva
        assert 'git_mr_url' in sample_pipeline_context_with_validations.metadata


class TestApprovalGateThresholds:
    """Testes de configuracao de thresholds."""

    @pytest.mark.asyncio
    async def test_default_thresholds(
        self,
        mock_git_client
    ):
        """Deve usar thresholds padrao."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(git_client=mock_git_client)

        assert gate.auto_approval_threshold == 0.9
        assert gate.min_quality_score == 0.5

    @pytest.mark.asyncio
    async def test_custom_thresholds(
        self,
        mock_git_client
    ):
        """Deve aceitar thresholds customizados."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.95,
            min_quality_score=0.6
        )

        assert gate.auto_approval_threshold == 0.95
        assert gate.min_quality_score == 0.6


class TestApprovalGateMergeRequestContent:
    """Testes de conteudo do Merge Request."""

    @pytest.mark.asyncio
    async def test_merge_request_branch_name(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve usar pipeline_id no nome do branch."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.7)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        call_args = mock_git_client.create_merge_request.call_args[0]
        branch_name = call_args[0]
        assert branch_name.startswith('code-forge-')
        assert sample_pipeline_context_with_validations.pipeline_id[:8] in branch_name

    @pytest.mark.asyncio
    async def test_merge_request_includes_quality_score(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve incluir quality score na descricao."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.75)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        call_args = mock_git_client.create_merge_request.call_args[0]
        description = call_args[2]
        assert 'Quality Score: 0.75' in description

    @pytest.mark.asyncio
    async def test_merge_request_includes_artifact_count(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve incluir contagem de artefatos na descricao."""
        from services.code_forge.src.services.approval_gate import ApprovalGate

        sample_pipeline_context_with_validations.calculate_quality_score = MagicMock(return_value=0.7)
        sample_pipeline_context_with_validations.has_critical_issues = MagicMock(return_value=False)

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        await gate.check_approval(sample_pipeline_context_with_validations)

        call_args = mock_git_client.create_merge_request.call_args[0]
        description = call_args[2]
        assert 'Artifacts:' in description
