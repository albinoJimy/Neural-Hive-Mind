"""
Testes unitários para GitClient - funcionalidade de versionamento de templates.

Cobertura:
- Listar tags disponíveis (list_tags)
- Fazer checkout de tag específica (checkout_tag)
- Obter tag atualmente ativa (get_current_tag)
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime


class TestGitClientListTags:
    """Testes de listagem de tags do repositório de templates."""

    @pytest.mark.asyncio
    async def test_list_tags_empty_repo(self):
        """Deve retornar lista vazia quando repositório não tem tags."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Mock repo vazio (sem tags)
        mock_repo = Mock()
        mock_repo.tags = []
        mock_repo.remotes.origin.fetch = Mock()

        git_client.repo = mock_repo

        tags = await git_client.list_tags()

        assert tags == []
        mock_repo.remotes.origin.fetch.assert_called_once_with('tags --prune-tags')

    @pytest.mark.asyncio
    async def test_list_tags_multiple_versions(self):
        """Deve listar todas as tags disponíveis em ordem descendente."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Mock repo com tags
        mock_repo = Mock()
        mock_tag_v2 = Mock()
        mock_tag_v2.name = 'v2.0.0'
        mock_tag_v2.commit.hexsha = 'abc123'

        mock_tag_v1 = Mock()
        mock_tag_v1.name = 'v1.5.0'
        mock_tag_v1.commit.hexsha = 'def456'

        mock_tag_v0 = Mock()
        mock_tag_v0.name = 'v1.0.0'
        mock_tag_v0.commit.hexsha = 'ghi789'

        mock_repo.tags = [mock_tag_v0, mock_tag_v1, mock_tag_v2]
        mock_repo.remotes.origin.fetch = Mock()

        git_client.repo = mock_repo

        tags = await git_client.list_tags()

        # Deve retornar em ordem descendente (v2.0.0, v1.5.0, v1.0.0)
        assert len(tags) == 3
        assert tags[0]['name'] == 'v2.0.0'
        assert tags[1]['name'] == 'v1.5.0'
        assert tags[2]['name'] == 'v1.0.0'


class TestGitClientCheckoutTag:
    """Testes de checkout de tags específicas."""

    @pytest.mark.asyncio
    async def test_checkout_tag_success(self):
        """Deve fazer checkout de tag com sucesso."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Mock repo com tag
        mock_repo = Mock()
        mock_tag = Mock()
        mock_tag.name = 'v1.5.0'
        mock_tag.commit.hexsha = 'abc123'

        mock_repo.tags = [mock_tag]
        mock_repo.git.checkout = Mock()

        git_client.repo = mock_repo

        result = await git_client.checkout_tag('v1.5.0')

        assert result is True
        mock_repo.git.checkout.assert_called_once_with('v1.5.0')

    @pytest.mark.asyncio
    async def test_checkout_tag_not_found(self):
        """Deve retornar False quando tag não existe."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Mock repo sem tags
        mock_repo = Mock()
        mock_repo.tags = []

        git_client.repo = mock_repo

        result = await git_client.checkout_tag('v1.5.0')

        assert result is False

    @pytest.mark.asyncio
    async def test_checkout_tag_without_repo(self):
        """Deve lançar erro quando repo não foi clonado."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Repo não inicializado
        git_client.repo = None

        with pytest.raises(RuntimeError, match='Repositório não foi clonado'):
            await git_client.checkout_tag('v1.5.0')


class TestGitClientGetCurrentTag:
    """Testes de obtenção da tag atual."""

    @pytest.mark.asyncio
    async def test_get_current_tag_on_tag(self):
        """Deve retornar nome da tag quando HEAD está em uma tag."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Mock repo onde HEAD aponta para uma tag
        mock_repo = Mock()
        mock_repo.head.commit.hexsha = 'abc123'

        mock_tag = Mock()
        mock_tag.name = 'v1.5.0'
        mock_tag.commit.hexsha = 'abc123'

        mock_repo.tags = [mock_tag]

        git_client.repo = mock_repo

        current_tag = await git_client.get_current_tag()

        assert current_tag == 'v1.5.0'

    @pytest.mark.asyncio
    async def test_get_current_tag_on_branch(self):
        """Deve retornar None quando HEAD não está em uma tag."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Mock repo onde HEAD não aponta para nenhuma tag
        mock_repo = Mock()
        mock_repo.head.commit.hexsha = 'xyz999'

        mock_tag = Mock()
        mock_tag.name = 'v1.5.0'
        mock_tag.commit.hexsha = 'abc123'

        mock_repo.tags = [mock_tag]

        git_client.repo = mock_repo

        current_tag = await git_client.get_current_tag()

        assert current_tag is None


class TestGitClientTagIntegration:
    """Testes de integração de versionamento de templates."""

    @pytest.mark.asyncio
    async def test_full_tag_workflow(self):
        """Deve listar, fazer checkout e verificar tag atual."""
        from src.clients.git_client import GitClient

        git_client = GitClient(
            templates_repo='https://github.com/test/templates',
            templates_branch='main',
            local_path='/tmp/test_templates'
        )

        # Mock repo
        mock_repo = Mock()

        # Tags disponíveis
        mock_tag_v2 = Mock()
        mock_tag_v2.name = 'v2.0.0'
        mock_tag_v2.commit.hexsha = 'aaa111'

        mock_tag_v1 = Mock()
        mock_tag_v1.name = 'v1.0.0'
        mock_tag_v1.commit.hexsha = 'bbb222'

        mock_repo.tags = [mock_tag_v1, mock_tag_v2]
        mock_repo.remotes.origin.fetch = Mock()
        mock_repo.git.checkout = Mock()

        git_client.repo = mock_repo

        # 1. Listar tags
        tags = await git_client.list_tags()
        assert len(tags) == 2
        assert tags[0]['name'] == 'v2.0.0'

        # 2. Fazer checkout de v1.0.0
        # Simular mudança de HEAD para v1.0.0 após checkout
        mock_repo.head.commit.hexsha = 'bbb222'

        result = await git_client.checkout_tag('v1.0.0')
        assert result is True

        # 3. Verificar tag atual
        current_tag = await git_client.get_current_tag()
        assert current_tag == 'v1.0.0'
