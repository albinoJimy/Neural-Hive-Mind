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
        from src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.95), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
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
        from src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.9), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
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
        from src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(
            git_client=mock_git_client,
            min_quality_score=0.5
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.3), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
            await gate.check_approval(sample_pipeline_context_with_validations)

        assert sample_pipeline_context_with_validations.metadata['approval'] == 'rejected'

    @pytest.mark.asyncio
    async def test_auto_reject_critical_issues(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve rejeitar automaticamente com issues criticos."""
        from src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(
            git_client=mock_git_client
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.85), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=True):
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
        from src.services.approval_gate import ApprovalGate

        # Adicionar target_repo para permitir criacao de MR
        sample_pipeline_context_with_validations.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.75), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
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
        from src.services.approval_gate import ApprovalGate

        # Adicionar target_repo para permitir criacao de MR
        sample_pipeline_context_with_validations.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.7), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
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
        from src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(git_client=mock_git_client)

        assert gate.auto_approval_threshold == 0.9
        assert gate.min_quality_score == 0.5

    @pytest.mark.asyncio
    async def test_custom_thresholds(
        self,
        mock_git_client
    ):
        """Deve aceitar thresholds customizados."""
        from src.services.approval_gate import ApprovalGate

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
        from src.services.approval_gate import ApprovalGate

        # Adicionar target_repo para permitir criacao de MR
        sample_pipeline_context_with_validations.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.7), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
            await gate.check_approval(sample_pipeline_context_with_validations)

        # Acesso via kwargs pois a funcao e chamada com argumentos nomeados
        call_kwargs = mock_git_client.create_merge_request.call_args[1]
        branch_name = call_kwargs['branch']
        assert branch_name.startswith('code-forge-')
        assert sample_pipeline_context_with_validations.pipeline_id[:8] in branch_name

    @pytest.mark.asyncio
    async def test_merge_request_includes_quality_score(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve incluir quality score na descricao."""
        from src.services.approval_gate import ApprovalGate

        # Adicionar target_repo para permitir criacao de MR
        sample_pipeline_context_with_validations.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.75), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
            await gate.check_approval(sample_pipeline_context_with_validations)

        # Acesso via kwargs pois a funcao e chamada com argumentos nomeados
        call_kwargs = mock_git_client.create_merge_request.call_args[1]
        description = call_kwargs['description']
        assert 'Quality Score: 0.75' in description

    @pytest.mark.asyncio
    async def test_merge_request_includes_artifact_count(
        self,
        mock_git_client,
        sample_pipeline_context_with_validations
    ):
        """Deve incluir contagem de artefatos na descricao."""
        from src.services.approval_gate import ApprovalGate

        # Adicionar target_repo para permitir criacao de MR
        sample_pipeline_context_with_validations.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        gate = ApprovalGate(
            git_client=mock_git_client,
            auto_approval_threshold=0.9,
            min_quality_score=0.5
        )

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.7), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
            await gate.check_approval(sample_pipeline_context_with_validations)

        # Acesso via kwargs pois a funcao e chamada com argumentos nomeados
        call_kwargs = mock_git_client.create_merge_request.call_args[1]
        description = call_kwargs['description']
        assert 'Artifacts:' in description


class TestApprovalGateCommitAndPush:
    """Testes do metodo _commit_and_push."""

    @pytest.mark.asyncio
    async def test_commit_and_push_with_artifact(
        self,
        mock_git_client,
        mock_mongodb_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve commitar e push artefatos para o repositorio."""
        from src.services.approval_gate import ApprovalGate

        # Configurar mock do MongoDB para retornar código
        mock_code = "def main():\n    print('Hello World')"
        mock_mongodb_client.get_artifact_content = AsyncMock(return_value=mock_code)

        # Configurar ticket com target_repo
        sample_pipeline_context_with_artifacts.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        gate = ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client
        )

        result = await gate._commit_and_push(
            sample_pipeline_context_with_artifacts,
            auto_approved=False
        )

        assert result is not None
        assert result.startswith('code-forge-')
        mock_git_client.create_branch.assert_called_once()
        mock_git_client.commit_artifacts.assert_called_once()
        mock_git_client.push_branch.assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_and_push_without_mongodb(
        self,
        mock_git_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve retornar None quando MongoDB client nao esta disponivel."""
        from src.services.approval_gate import ApprovalGate

        gate = ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=None
        )

        result = await gate._commit_and_push(
            sample_pipeline_context_with_artifacts,
            auto_approved=False
        )

        assert result is None
        mock_git_client.create_branch.assert_not_called()

    @pytest.mark.asyncio
    async def test_commit_and_push_without_target_repo(
        self,
        mock_git_client,
        mock_mongodb_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve retornar None quando target_repo nao foi fornecido."""
        from src.services.approval_gate import ApprovalGate

        mock_mongodb_client.get_artifact_content = AsyncMock(return_value="code")

        # Remover target_repo se existir
        sample_pipeline_context_with_artifacts.ticket.parameters.pop('target_repo', None)

        gate = ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client
        )

        result = await gate._commit_and_push(
            sample_pipeline_context_with_artifacts,
            auto_approved=False
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_commit_creates_readme_with_metadata(
        self,
        mock_git_client,
        mock_mongodb_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve criar README com metadados do artefato."""
        from src.services.approval_gate import ApprovalGate

        mock_code = "def main():\n    pass"
        mock_mongodb_client.get_artifact_content = AsyncMock(return_value=mock_code)
        sample_pipeline_context_with_artifacts.ticket.parameters.update({
            'target_repo': 'https://github.com/test/repo',
            'service_name': 'test-service',
            'description': 'Test service'
        })

        gate = ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client
        )

        await gate._commit_and_push(
            sample_pipeline_context_with_artifacts,
            auto_approved=True
        )

        # Verificar que commit_artifacts foi chamado com README
        call_kwargs = mock_git_client.commit_artifacts.call_args[1]
        artifacts = call_kwargs['artifacts']

        readme_artifact = next((a for a in artifacts if a['path'] == 'README.md'), None)
        assert readme_artifact is not None
        readme_content = readme_artifact['content']
        assert 'Neural Code Forge' in readme_content
        assert sample_pipeline_context_with_artifacts.pipeline_id in readme_content
        assert '**Auto-Approved**: True' in readme_content

    @pytest.mark.asyncio
    async def test_commit_saves_commit_metadata(
        self,
        mock_git_client,
        mock_mongodb_client,
        sample_pipeline_context_with_artifacts
    ):
        """Deve salvar metadados do commit no contexto."""
        from src.services.approval_gate import ApprovalGate

        mock_code = "code"
        mock_mongodb_client.get_artifact_content = AsyncMock(return_value=mock_code)
        mock_git_client.commit_artifacts = AsyncMock(return_value='abc123def')
        sample_pipeline_context_with_artifacts.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        gate = ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client
        )

        await gate._commit_and_push(
            sample_pipeline_context_with_artifacts,
            auto_approved=False
        )

        assert 'git_commit_sha' in sample_pipeline_context_with_artifacts.metadata
        assert 'git_branch' in sample_pipeline_context_with_artifacts.metadata
        assert sample_pipeline_context_with_artifacts.metadata['git_commit_sha'] == 'abc123def'


class TestApprovalGateGetFilename:
    """Testes do metodo _get_filename_for_language."""

    @pytest.mark.asyncio
    async def test_filename_python(self):
        """Deve retornar main.py para Python."""
        from src.services.approval_gate import ApprovalGate
        gate = ApprovalGate(git_client=MagicMock())
        assert gate._get_filename_for_language('python') == 'main.py'

    @pytest.mark.asyncio
    async def test_filename_javascript(self):
        """Deve retornar index.js para JavaScript."""
        from src.services.approval_gate import ApprovalGate
        gate = ApprovalGate(git_client=MagicMock())
        assert gate._get_filename_for_language('javascript') == 'index.js'

    @pytest.mark.asyncio
    async def test_filename_typescript(self):
        """Deve retornar index.ts para TypeScript."""
        from src.services.approval_gate import ApprovalGate
        gate = ApprovalGate(git_client=MagicMock())
        assert gate._get_filename_for_language('typescript') == 'index.ts'

    @pytest.mark.asyncio
    async def test_filename_go(self):
        """Deve retornar main.go para Go."""
        from src.services.approval_gate import ApprovalGate
        gate = ApprovalGate(git_client=MagicMock())
        assert gate._get_filename_for_language('go') == 'main.go'

    @pytest.mark.asyncio
    async def test_filename_unknown(self):
        """Deve retornar main.{lang} para linguagens desconhecidas."""
        from src.services.approval_gate import ApprovalGate
        gate = ApprovalGate(git_client=MagicMock())
        assert gate._get_filename_for_language('rust') == 'main.rs'


class TestApprovalGateAutoApprovedCommit:
    """Testes de commit quando auto-approved."""

    @pytest.mark.asyncio
    async def test_auto_approved_commits_code(
        self,
        mock_git_client,
        mock_mongodb_client,
        sample_pipeline_context_with_validations
    ):
        """Deve commitar codigo mesmo quando auto-approved."""
        from src.services.approval_gate import ApprovalGate
        from src.models.artifact import CodeForgeArtifact, ArtifactType, GenerationMethod

        gate = ApprovalGate(
            git_client=mock_git_client,
            mongodb_client=mock_mongodb_client,
            auto_approval_threshold=0.9
        )

        # Adicionar artefato ao contexto
        artifact = CodeForgeArtifact(
            artifact_id='test-artifact',
            ticket_id='ticket-123',
            artifact_type=ArtifactType.CODE,
            language='python',
            confidence_score=0.9,
            generation_method=GenerationMethod.TEMPLATE,
            content_uri='mongodb://test',
            content_hash='abc123',
            created_at=datetime.now()
        )
        sample_pipeline_context_with_validations.generated_artifacts.append(artifact)

        # Modificar ticket para incluir target_repo
        sample_pipeline_context_with_validations.ticket.parameters['target_repo'] = 'https://github.com/test/repo'

        mock_mongodb_client.get_artifact_content = AsyncMock(return_value='def main(): pass')

        # Mock methods usando patch na classe
        with patch('src.models.pipeline_context.PipelineContext.calculate_quality_score', return_value=0.95), \
             patch('src.models.pipeline_context.PipelineContext.has_critical_issues', return_value=False):
            await gate.check_approval(sample_pipeline_context_with_validations)

        # Verificar que commit foi chamado mesmo com auto-approval
        mock_git_client.create_branch.assert_called_once()
        mock_git_client.commit_artifacts.assert_called_once()
        mock_git_client.push_branch.assert_called_once()
        assert sample_pipeline_context_with_validations.metadata['approval'] == 'auto'
