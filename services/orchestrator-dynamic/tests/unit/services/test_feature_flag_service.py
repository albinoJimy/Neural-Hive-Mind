"""
Testes unitários para FeatureFlagService.

Testa gestão de feature flags com cache em Redis e persistência em MongoDB.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.feature_flag_service import FeatureFlagService


@pytest.fixture
def mock_mongodb():
    """Mock do cliente MongoDB."""
    client = AsyncMock()
    collection = AsyncMock()
    client.__getitem__ = MagicMock(return_value=collection)
    return collection


@pytest.fixture
def mock_redis():
    """Mock do cliente Redis."""
    return AsyncMock()


@pytest.fixture
def feature_flag_data():
    """Dados de uma feature flag para testes."""
    return {
        "flag_name": "new_workflow_engine",
        "description": "Ativa novo motor de workflows",
        "enabled": True,
        "rollout_strategy": "gradual",
        "rollout_config": {
            "percentage": 50,
            "whitelist": ["tenant-123", "tenant-456"],
            "namespaces": ["staging", "dev"],
            "canary_list": [],
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "platform-engineer",
    }


class TestFeatureFlagService:
    """Testes do FeatureFlagService."""

    @pytest.mark.asyncio
    async def test_get_flag_from_cache(self, mock_mongodb, mock_redis, feature_flag_data):
        """Testa buscar flag do cache Redis."""
        # Setup mock Redis - flag está no cache
        cached_data = json.dumps(feature_flag_data)
        mock_redis.get = AsyncMock(return_value=cached_data)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.get_flag("new_workflow_engine")

        assert result["flag_name"] == "new_workflow_engine"
        assert result["enabled"] is True
        mock_redis.get.assert_called_once_with("feature_flag:new_workflow_engine")
        mock_mongodb.find_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_flag_from_mongodb_cache_miss(self, mock_mongodb, mock_redis, feature_flag_data):
        """Testa buscar flag do MongoDB quando cache miss."""
        # Setup mocks - cache miss, flag no MongoDB
        mock_redis.get = AsyncMock(return_value=None)
        mock_mongodb.find_one = AsyncMock(return_value=feature_flag_data)
        mock_redis.setex = AsyncMock(return_value=True)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.get_flag("new_workflow_engine")

        assert result["flag_name"] == "new_workflow_engine"
        mock_redis.get.assert_called_once()
        mock_mongodb.find_one.assert_awaited_once_with({"flag_name": "new_workflow_engine"})
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_flag_not_found(self, mock_mongodb, mock_redis):
        """Testa buscar flag que não existe."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_mongodb.find_one = AsyncMock(return_value=None)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.get_flag("nonexistent_flag")

        assert result is None
        mock_redis.get.assert_called_once()
        mock_mongodb.find_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_flag_create_new(self, mock_mongodb, mock_redis, feature_flag_data):
        """Testa criar nova feature flag."""
        mock_mongodb.update_one = AsyncMock(return_value=MagicMock(upserted_id="new_id"))
        mock_redis.delete = AsyncMock(return_value=1)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.set_flag("new_workflow_engine", feature_flag_data)

        assert result["flag_name"] == "new_workflow_engine"
        mock_mongodb.update_one.assert_called_once()
        mock_redis.delete.assert_called_once_with("feature_flag:new_workflow_engine")

    @pytest.mark.asyncio
    async def test_set_flag_invalidates_cache(self, mock_mongodb, mock_redis):
        """Testa que set_flag invalida o cache."""
        flag_data = {"flag_name": "test_flag", "enabled": True}
        mock_mongodb.update_one = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        await service.set_flag("test_flag", flag_data)

        mock_redis.delete.assert_called_once_with("feature_flag:test_flag")

    @pytest.mark.asyncio
    async def test_delete_flag(self, mock_mongodb, mock_redis):
        """Testa deletar feature flag."""
        mock_mongodb.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        mock_redis.delete = AsyncMock(return_value=1)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.delete_flag("test_flag")

        assert result is True
        mock_mongodb.delete_one.assert_awaited_once_with({"flag_name": "test_flag"})
        mock_redis.delete.assert_called_once_with("feature_flag:test_flag")

    @pytest.mark.asyncio
    async def test_delete_flag_not_found(self, mock_mongodb, mock_redis):
        """Testa deletar flag que não existe."""
        mock_mongodb.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_redis.delete = AsyncMock(return_value=0)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.delete_flag("nonexistent_flag")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_flags(self, mock_mongodb, mock_redis, feature_flag_data):
        """Testa listar todas as flags."""
        cursor = AsyncMock()
        cursor.to_list = AsyncMock(return_value=[feature_flag_data, {**feature_flag_data, "flag_name": "another_flag"}])
        mock_mongodb.find = MagicMock(return_value=cursor)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.list_flags()

        assert len(result) == 2
        mock_mongodb.find.assert_called_once_with({}, sort=[("created_at", -1)])

    @pytest.mark.asyncio
    async def test_list_flags_with_filter(self, mock_mongodb, mock_redis, feature_flag_data):
        """Testa listar flags com filtro de enabled."""
        cursor = AsyncMock()
        cursor.to_list = AsyncMock(return_value=[feature_flag_data])
        mock_mongodb.find = MagicMock(return_value=cursor)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.list_filters(enabled_only=True)

        assert len(result) == 1
        mock_mongodb.find.assert_called_once_with({"enabled": True}, sort=[("created_at", -1)])

    @pytest.mark.asyncio
    async def test_evaluate_flag_enabled_true(self, mock_mongodb, mock_redis):
        """Testa avaliação de flag ativa sem restrições."""
        flag_data = {
            "flag_name": "test_flag",
            "enabled": True,
            "rollout_strategy": "all",
            "rollout_config": {},
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(flag_data))

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.evaluate_flag("test_flag", context={"tenant_id": "tenant-123"})

        assert result is True

    @pytest.mark.asyncio
    async def test_evaluate_flag_disabled(self, mock_mongodb, mock_redis):
        """Testa avaliação de flag desativada."""
        flag_data = {
            "flag_name": "test_flag",
            "enabled": False,
            "rollout_strategy": "all",
            "rollout_config": {},
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(flag_data))

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.evaluate_flag("test_flag", context={})

        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_flag_not_found(self, mock_mongodb, mock_redis):
        """Testa avaliação de flag inexistente retorna False."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_mongodb.find_one = AsyncMock(return_value=None)

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
        result = await service.evaluate_flag("nonexistent_flag", context={})

        assert result is False

    @pytest.mark.asyncio
    async def test_evaluate_flag_with_namespace_filter(self, mock_mongodb, mock_redis):
        """Testa avaliação de flag com filtro de namespace."""
        flag_data = {
            "flag_name": "test_flag",
            "enabled": True,
            "rollout_strategy": "all",  # Usar all para garantir True se namespace OK
            "rollout_config": {
                "namespaces": ["staging", "dev"],
            },
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(flag_data))

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)

        # Namespace permitido
        result = await service.evaluate_flag("test_flag", context={"namespace": "staging"})
        assert result is True

        # Namespace não permitido
        result = await service.evaluate_flag("test_flag", context={"namespace": "production"})
        assert result is False


class TestFeatureFlagServiceRolloutIntegration:
    """Testes de integração com RolloutStrategy."""

    @pytest.mark.asyncio
    async def test_evaluate_with_gradual_rollout(self, mock_mongodb, mock_redis):
        """Testa avaliação com rollout gradual (delegado para RolloutStrategy)."""
        flag_data = {
            "flag_name": "test_flag",
            "enabled": True,
            "rollout_strategy": "gradual",
            "rollout_config": {
                "percentage": 50,
            },
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(flag_data))

        with patch("src.services.rollout_strategy.RolloutStrategy.evaluate") as mock_evaluate:
            mock_evaluate.return_value = True

            service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)
            result = await service.evaluate_flag("test_flag", context={"tenant_id": "tenant-123"})

            assert result is True
            mock_evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_with_whitelist_strategy(self, mock_mongodb, mock_redis):
        """Testa avaliação com estratégia whitelist."""
        flag_data = {
            "flag_name": "test_flag",
            "enabled": True,
            "rollout_strategy": "whitelist",
            "rollout_config": {
                "whitelist": ["tenant-123", "tenant-456"],
            },
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(flag_data))

        service = FeatureFlagService(mongodb=mock_mongodb, redis=mock_redis)

        # Tenant na whitelist
        result = await service.evaluate_flag("test_flag", context={"tenant_id": "tenant-123"})
        assert result is True

        # Tenant fora da whitelist
        result = await service.evaluate_flag("test_flag", context={"tenant_id": "tenant-999"})
        assert result is False
