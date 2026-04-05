"""
Testes unitários para FeatureFlagRepository.

Cobertura:
- create: Criar nova feature flag
- get_by_name: Buscar flag por nome
- update: Atualizar flag existente
- delete: Remover flag
- list: Listar todas as flags com filtros
- enable/disable: Ativar/desativar flag
- exists: Verificar se flag existe
- Métodos de bulk operations
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError

from src.models.feature_flag import (
    FeatureFlag,
    RolloutStrategy,
    RolloutType,
)
from src.repositories.feature_flag_repository import (
    FeatureFlagRepository,
    RepositoryError,
)


@pytest.fixture
def mock_collection():
    """Fixture para coleção MongoDB mockada."""
    collection = MagicMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.update_one = AsyncMock()
    collection.delete_one = AsyncMock()
    collection.find = MagicMock()
    collection.find.return_value.to_list = AsyncMock()
    collection.count_documents = AsyncMock()
    return collection


@pytest.fixture
def mock_db():
    """Fixture para database MongoDB mockado."""
    db = MagicMock()
    return db


@pytest.fixture
def repository(mock_db):
    """Fixture para repositório."""
    mock_db.__getitem__ = Mock(return_value=MagicMock())
    return FeatureFlagRepository(mock_db)


class TestFeatureFlagRepositoryInit:
    """Testes para inicialização do repositório."""

    def test_init_with_collection_name(self, mock_db):
        """Testa inicialização com nome de coleção."""
        repo = FeatureFlagRepository(mock_db, collection_name="custom_flags")

        assert repo.collection_name == "custom_flags"

    def test_init_defaults_to_feature_flags(self, mock_db):
        """Testa nome default de coleção."""
        repo = FeatureFlagRepository(mock_db)

        assert repo.collection_name == "feature_flags"


class TestFeatureFlagRepositoryCreate:
    """Testes para método create."""

    @pytest.mark.asyncio
    async def test_create_success(self, repository, mock_db):
        """Testa criação bem-sucedida de flag."""
        flag = FeatureFlag(
            name="test_feature",
            description="Test feature",
            enabled=True,
        )

        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="test_id"))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.create(flag)

        assert result.name == "test_feature"
        assert result.enabled is True
        mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_key_error(self, repository, mock_db):
        """Testa erro de chave duplicada."""
        flag = FeatureFlag(name="existing", description="Existing")

        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(side_effect=DuplicateKeyError("E11000"))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        with pytest.raises(RepositoryError) as exc_info:
            await repository.create(flag)

        assert "duplicate" in str(exc_info.value).lower() or "já existe" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_mongo_error_propagates(self, repository, mock_db):
        """Testa propagação de erro MongoDB."""
        flag = FeatureFlag(name="test", description="test")

        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(side_effect=PyMongoError("Connection error"))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        with pytest.raises(RepositoryError):
            await repository.create(flag)


class TestFeatureFlagRepositoryGetByName:
    """Testes para método get_by_name."""

    @pytest.mark.asyncio
    async def test_get_by_name_found(self, repository, mock_db):
        """Testa busca de flag existente."""
        flag_data = {
            "name": "test_feature",
            "description": "Test",
            "enabled": True,
            "rollout_strategy": {"type": "immediate"},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=flag_data)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.get_by_name("test_feature")

        assert result is not None
        assert result.name == "test_feature"
        assert result.enabled is True

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, repository, mock_db):
        """Testa busca de flag inexistente."""
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.get_by_name("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_name_with_invalid_data(self, repository, mock_db):
        """Testa busca com dados inválidos."""
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={"invalid": "data"})
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.get_by_name("bad_data")

        # Deve retornar None ou lançar erro dependendo da implementação
        assert result is None


class TestFeatureFlagRepositoryUpdate:
    """Testes para método update."""

    @pytest.mark.asyncio
    async def test_update_success(self, repository, mock_db):
        """Testa atualização bem-sucedida."""
        flag = FeatureFlag(name="test", description="Updated", enabled=True)

        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.update("test", flag)

        assert result is True
        mock_collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found(self, repository, mock_db):
        """Testa atualização de flag inexistente."""
        flag = FeatureFlag(name="test", description="Updated")

        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.update("test", flag)

        assert result is False

    @pytest.mark.asyncio
    async def test_update_with_partial_data(self, repository, mock_db):
        """Testa atualização parcial."""
        flag = FeatureFlag(name="test", description="New description")

        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.update("test", flag, partial=True)

        assert result is True


class TestFeatureFlagRepositoryDelete:
    """Testes para método delete."""

    @pytest.mark.asyncio
    async def test_delete_success(self, repository, mock_db):
        """Testa deleção bem-sucedida."""
        mock_collection = MagicMock()
        mock_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.delete("test_feature")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repository, mock_db):
        """Testa deleção de flag inexistente."""
        mock_collection = MagicMock()
        mock_collection.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.delete("nonexistent")

        assert result is False


class TestFeatureFlagRepositoryList:
    """Testes para método list."""

    @pytest.mark.asyncio
    async def test_list_all(self, repository, mock_db):
        """Testa listagem de todas as flags."""
        flags_data = [
            {
                "name": "flag1",
                "description": "First",
                "enabled": True,
                "rollout_strategy": {"type": "immediate"},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
            {
                "name": "flag2",
                "description": "Second",
                "enabled": False,
                "rollout_strategy": {"type": "immediate"},
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        ]

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=flags_data)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.list()

        assert len(result) == 2
        assert result[0].name == "flag1"
        assert result[1].name == "flag2"

    @pytest.mark.asyncio
    async def test_list_with_enabled_filter(self, repository, mock_db):
        """Testa listagem filtrando por enabled."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        await repository.list(enabled_only=True)

        mock_collection.find.assert_called_once()
        call_args = mock_collection.find.call_args
        assert "enabled" in str(call_args)

    @pytest.mark.asyncio
    async def test_list_with_tag_filter(self, repository, mock_db):
        """Testa listagem filtrando por tag."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        await repository.list(tags=["experiment"])

        mock_collection.find.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, repository, mock_db):
        """Testa listagem com paginação."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        await repository.list(skip=10, limit=20)

        mock_cursor.skip.assert_called_once_with(10)
        mock_cursor.limit.assert_called_once_with(20)


class TestFeatureFlagRepositoryEnableDisable:
    """Testes para métodos enable/disable."""

    @pytest.mark.asyncio
    async def test_enable_flag(self, repository, mock_db):
        """Testa habilitar flag."""
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.enable("test_feature")

        assert result is True

    @pytest.mark.asyncio
    async def test_disable_flag(self, repository, mock_db):
        """Testa desabilitar flag."""
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.disable("test_feature")

        assert result is True

    @pytest.mark.asyncio
    async def test_enable_nonexistent_flag(self, repository, mock_db):
        """Testa habilitar flag inexistente."""
        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.enable("nonexistent")

        assert result is False


class TestFeatureFlagRepositoryExists:
    """Testes para método exists."""

    @pytest.mark.asyncio
    async def test_exists_true(self, repository, mock_db):
        """Testa verifica quando flag existe."""
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=1)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.exists("test_feature")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self, repository, mock_db):
        """Testa verifica quando flag não existe."""
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.exists("nonexistent")

        assert result is False


class TestFeatureFlagRepositoryCount:
    """Testes para método count."""

    @pytest.mark.asyncio
    async def test_count_all(self, repository, mock_db):
        """Testa contagem total de flags."""
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=42)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.count()

        assert result == 42

    @pytest.mark.asyncio
    async def test_count_enabled_only(self, repository, mock_db):
        """Testa contagem de flags habilitadas."""
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=10)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.count(enabled_only=True)

        assert result == 10


class TestFeatureFlagRepositoryBulkOperations:
    """Testes para operações em lote."""

    @pytest.mark.asyncio
    async def test_bulk_enable(self, repository, mock_db):
        """Testa habilitar múltiplas flags."""
        mock_collection = MagicMock()
        mock_collection.update_many = AsyncMock(return_value=MagicMock(modified_count=3))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.bulk_enable(["flag1", "flag2", "flag3"])

        assert result == 3

    @pytest.mark.asyncio
    async def test_bulk_disable(self, repository, mock_db):
        """Testa desabilitar múltiplas flags."""
        mock_collection = MagicMock()
        mock_collection.update_many = AsyncMock(return_value=MagicMock(modified_count=2))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.bulk_disable(["flag1", "flag2"])

        assert result == 2

    @pytest.mark.asyncio
    async def test_bulk_delete(self, repository, mock_db):
        """Testa deletar múltiplas flags."""
        mock_collection = MagicMock()
        mock_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=5))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        result = await repository.bulk_delete(["flag1", "flag2", "flag3", "flag4", "flag5"])

        assert result == 5


class TestFeatureFlagRepositoryErrorHandling:
    """Testes para tratamento de erros."""

    @pytest.mark.asyncio
    async def test_mongo_error_wrapped_in_repository_error(self, repository, mock_db):
        """Testa que erros do MongoDB são wrapped em RepositoryError."""
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(side_effect=PyMongoError("Connection lost"))
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        with pytest.raises(RepositoryError):
            await repository.get_by_name("test")
