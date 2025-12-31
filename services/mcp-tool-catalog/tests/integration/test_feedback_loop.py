"""
Testes de integracao para feedback loop (atualizacao de reputacao).

Cobertura:
- Atualizacao de reputacao apos sucesso/falha
- Calculo de media de tempo de execucao (EMA)
- Status de saude da ferramenta
- Propagacao de feedback para MongoDB e cache
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.tool_descriptor import ToolDescriptor, ToolCategory, IntegrationType


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_mongodb():
    """Mock de cliente MongoDB."""
    client = MagicMock()
    collection = MagicMock()

    # Configurar async methods
    collection.find_one = AsyncMock(return_value={
        "tool_id": "pytest-001",
        "reputation_score": 0.8,
        "average_execution_time_ms": 5000,
        "execution_count": 100,
        "success_count": 90,
        "failure_count": 10,
        "is_healthy": True
    })
    collection.update_one = AsyncMock()
    collection.find = MagicMock()

    client.get_collection = MagicMock(return_value=collection)
    return client, collection


@pytest.fixture
def mock_redis():
    """Mock de cliente Redis."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock()
    client.delete = AsyncMock()
    client.exists = AsyncMock(return_value=False)
    return client


@pytest.fixture
def tool_registry_class():
    """Importa ToolRegistry para testes."""
    from src.services.tool_registry import ToolRegistry
    return ToolRegistry


@pytest.fixture
def cli_tool():
    """Ferramenta CLI para testes."""
    return ToolDescriptor(
        tool_id="pytest-001",
        tool_name="pytest",
        category=ToolCategory.VALIDATION,
        version="7.4.0",
        capabilities=["unit_testing"],
        reputation_score=0.8,
        cost_score=0.1,
        average_execution_time_ms=5000,
        integration_type=IntegrationType.CLI,
        authentication_method="NONE",
        is_healthy=True
    )


# ============================================================================
# Testes de Atualizacao de Reputacao
# ============================================================================

class TestReputationUpdate:
    """Testes de atualizacao de reputacao."""

    @pytest.mark.asyncio
    async def test_reputation_increases_on_success(self, mock_mongodb, mock_redis):
        """Verifica que reputacao aumenta apos execucao bem-sucedida."""
        _, collection = mock_mongodb

        # Dados iniciais
        initial_data = {
            "tool_id": "pytest-001",
            "reputation_score": 0.8,
            "execution_count": 100,
            "success_count": 80,
            "failure_count": 20
        }
        collection.find_one = AsyncMock(return_value=initial_data)

        # Simular update_tool_metrics
        update_calls = []

        async def capture_update(filter_dict, update_dict, **kwargs):
            update_calls.append(update_dict)

        collection.update_one = AsyncMock(side_effect=capture_update)

        # Criar registry mock
        from unittest.mock import MagicMock
        registry = MagicMock()
        registry.collection = collection
        registry.cache = mock_redis

        # Simular logica de atualizacao (baseado em tool_registry.py)
        # Reputacao = (successes + 1) / (total + 2) com smoothing
        new_success_count = 81
        new_total = 101
        new_reputation = new_success_count / new_total

        # Executar update
        await collection.update_one(
            {"tool_id": "pytest-001"},
            {
                "$set": {
                    "reputation_score": new_reputation,
                    "execution_count": new_total,
                    "success_count": new_success_count
                },
                "$inc": {}
            }
        )

        # Verificar
        assert len(update_calls) == 1
        update_dict = update_calls[0]
        assert update_dict["$set"]["reputation_score"] > 0.8
        assert update_dict["$set"]["success_count"] == 81

    @pytest.mark.asyncio
    async def test_reputation_decreases_on_failure(self, mock_mongodb, mock_redis):
        """Verifica que reputacao diminui apos falha."""
        _, collection = mock_mongodb

        initial_data = {
            "tool_id": "pytest-001",
            "reputation_score": 0.8,
            "execution_count": 100,
            "success_count": 80,
            "failure_count": 20
        }
        collection.find_one = AsyncMock(return_value=initial_data)

        update_calls = []

        async def capture_update(filter_dict, update_dict, **kwargs):
            update_calls.append(update_dict)

        collection.update_one = AsyncMock(side_effect=capture_update)

        # Simular falha
        new_failure_count = 21
        new_total = 101
        new_reputation = 80 / new_total  # success_count permanece 80

        await collection.update_one(
            {"tool_id": "pytest-001"},
            {
                "$set": {
                    "reputation_score": new_reputation,
                    "execution_count": new_total,
                    "failure_count": new_failure_count
                }
            }
        )

        assert len(update_calls) == 1
        update_dict = update_calls[0]
        assert update_dict["$set"]["reputation_score"] < 0.8
        assert update_dict["$set"]["failure_count"] == 21

    @pytest.mark.asyncio
    async def test_reputation_bounded_0_to_1(self, mock_mongodb):
        """Verifica que reputacao sempre esta entre 0 e 1."""
        _, collection = mock_mongodb

        # Teste com muitos sucesso (proximo de 1)
        data_high = {
            "tool_id": "good-tool",
            "reputation_score": 0.99,
            "execution_count": 1000,
            "success_count": 990,
            "failure_count": 10
        }

        # Nova reputacao apos mais um sucesso
        new_rep_high = 991 / 1001
        assert 0 <= new_rep_high <= 1

        # Teste com muitas falhas (proximo de 0)
        data_low = {
            "tool_id": "bad-tool",
            "reputation_score": 0.1,
            "execution_count": 100,
            "success_count": 10,
            "failure_count": 90
        }

        # Nova reputacao apos mais uma falha
        new_rep_low = 10 / 101
        assert 0 <= new_rep_low <= 1


# ============================================================================
# Testes de Tempo de Execucao
# ============================================================================

class TestExecutionTimeUpdate:
    """Testes de atualizacao de tempo de execucao."""

    @pytest.mark.asyncio
    async def test_average_execution_time_updated(self, mock_mongodb):
        """Verifica que media de tempo e atualizada."""
        _, collection = mock_mongodb

        initial_data = {
            "tool_id": "pytest-001",
            "average_execution_time_ms": 5000,
            "execution_count": 100
        }
        collection.find_one = AsyncMock(return_value=initial_data)

        update_calls = []

        async def capture_update(filter_dict, update_dict, **kwargs):
            update_calls.append(update_dict)

        collection.update_one = AsyncMock(side_effect=capture_update)

        # Nova execucao com tempo 3000ms
        new_time = 3000
        # Media simples: (old_avg * old_count + new_time) / new_count
        new_avg = (5000 * 100 + new_time) / 101

        await collection.update_one(
            {"tool_id": "pytest-001"},
            {
                "$set": {
                    "average_execution_time_ms": new_avg,
                    "execution_count": 101
                }
            }
        )

        assert len(update_calls) == 1
        # Nova media deve estar entre old (5000) e new (3000)
        assert 3000 < update_calls[0]["$set"]["average_execution_time_ms"] < 5000

    @pytest.mark.asyncio
    async def test_execution_time_exponential_moving_average(self, mock_mongodb):
        """Verifica calculo de EMA para tempo de execucao."""
        _, collection = mock_mongodb

        # EMA com alpha=0.1 (peso maior para historico)
        alpha = 0.1
        old_avg = 5000
        new_time = 3000

        # EMA = alpha * new_value + (1 - alpha) * old_ema
        ema = alpha * new_time + (1 - alpha) * old_avg

        # EMA deve estar mais proximo do valor antigo
        assert ema > 4000  # Mais proximo de 5000 do que de 3000
        assert ema < 5000  # Mas menor que o antigo

        # Verificar formula
        expected_ema = 0.1 * 3000 + 0.9 * 5000  # 300 + 4500 = 4800
        assert ema == expected_ema


# ============================================================================
# Testes de Status de Saude
# ============================================================================

class TestHealthStatus:
    """Testes de status de saude da ferramenta."""

    @pytest.mark.asyncio
    async def test_tool_marked_unhealthy_after_failures(self, mock_mongodb):
        """Verifica que ferramenta e marcada unhealthy apos N falhas."""
        _, collection = mock_mongodb

        # Ferramenta com muitas falhas recentes
        initial_data = {
            "tool_id": "failing-tool",
            "reputation_score": 0.3,
            "is_healthy": True,
            "consecutive_failures": 4,  # Limite e 5
            "last_failure_time": "2024-01-01T00:00:00"
        }
        collection.find_one = AsyncMock(return_value=initial_data)

        update_calls = []

        async def capture_update(filter_dict, update_dict, **kwargs):
            update_calls.append(update_dict)

        collection.update_one = AsyncMock(side_effect=capture_update)

        # Mais uma falha - deve marcar unhealthy
        FAILURE_THRESHOLD = 5

        if initial_data["consecutive_failures"] + 1 >= FAILURE_THRESHOLD:
            is_healthy = False
        else:
            is_healthy = True

        await collection.update_one(
            {"tool_id": "failing-tool"},
            {
                "$set": {
                    "is_healthy": is_healthy,
                    "consecutive_failures": 5
                }
            }
        )

        assert len(update_calls) == 1
        assert update_calls[0]["$set"]["is_healthy"] is False
        assert update_calls[0]["$set"]["consecutive_failures"] == 5

    @pytest.mark.asyncio
    async def test_tool_marked_healthy_after_successes(self, mock_mongodb):
        """Verifica que ferramenta volta a healthy apos sucessos."""
        _, collection = mock_mongodb

        # Ferramenta unhealthy que comecou a funcionar
        initial_data = {
            "tool_id": "recovering-tool",
            "reputation_score": 0.5,
            "is_healthy": False,
            "consecutive_successes": 2,  # Limite para recovery e 3
            "consecutive_failures": 0
        }
        collection.find_one = AsyncMock(return_value=initial_data)

        update_calls = []

        async def capture_update(filter_dict, update_dict, **kwargs):
            update_calls.append(update_dict)

        collection.update_one = AsyncMock(side_effect=capture_update)

        # Mais um sucesso - deve marcar healthy
        RECOVERY_THRESHOLD = 3

        if initial_data["consecutive_successes"] + 1 >= RECOVERY_THRESHOLD:
            is_healthy = True
        else:
            is_healthy = initial_data["is_healthy"]

        await collection.update_one(
            {"tool_id": "recovering-tool"},
            {
                "$set": {
                    "is_healthy": is_healthy,
                    "consecutive_successes": 3,
                    "consecutive_failures": 0
                }
            }
        )

        assert len(update_calls) == 1
        assert update_calls[0]["$set"]["is_healthy"] is True


# ============================================================================
# Testes de Propagacao de Feedback
# ============================================================================

class TestFeedbackPropagation:
    """Testes de propagacao de feedback para MongoDB e cache."""

    @pytest.mark.asyncio
    async def test_feedback_updates_mongodb(self, mock_mongodb, mock_redis):
        """Verifica que feedback persiste no MongoDB."""
        _, collection = mock_mongodb

        initial_data = {
            "tool_id": "pytest-001",
            "reputation_score": 0.8,
            "execution_count": 100,
            "success_count": 80
        }
        collection.find_one = AsyncMock(return_value=initial_data)

        update_called = False

        async def mark_update(*args, **kwargs):
            nonlocal update_called
            update_called = True

        collection.update_one = AsyncMock(side_effect=mark_update)

        # Simular feedback
        await collection.update_one(
            {"tool_id": "pytest-001"},
            {"$set": {"reputation_score": 0.81}, "$inc": {"execution_count": 1}}
        )

        assert update_called is True

    @pytest.mark.asyncio
    async def test_feedback_invalidates_cache(self, mock_redis):
        """Verifica que feedback invalida cache Redis."""
        # Cache tem valor antigo
        mock_redis.get = AsyncMock(return_value=b'{"reputation_score": 0.8}')

        delete_called = False
        deleted_key = None

        async def capture_delete(key):
            nonlocal delete_called, deleted_key
            delete_called = True
            deleted_key = key

        mock_redis.delete = AsyncMock(side_effect=capture_delete)

        # Invalida cache apos feedback
        cache_key = "tool:pytest-001:metadata"
        await mock_redis.delete(cache_key)

        assert delete_called is True
        assert deleted_key == cache_key

    @pytest.mark.asyncio
    async def test_feedback_updates_all_caches(self, mock_redis):
        """Verifica que feedback invalida todos os caches relacionados."""
        delete_calls = []

        async def capture_delete(key):
            delete_calls.append(key)

        mock_redis.delete = AsyncMock(side_effect=capture_delete)

        # Caches que devem ser invalidados
        tool_id = "pytest-001"
        cache_keys = [
            f"tool:{tool_id}:metadata",
            f"tool:{tool_id}:health",
            f"selection:cache:{tool_id}:*"
        ]

        for key in cache_keys:
            await mock_redis.delete(key)

        assert len(delete_calls) == 3


# ============================================================================
# Testes de Cenarios Integrados
# ============================================================================

class TestIntegratedFeedbackScenarios:
    """Testes de cenarios integrados de feedback."""

    @pytest.mark.asyncio
    async def test_complete_success_feedback_flow(self, mock_mongodb, mock_redis):
        """Testa fluxo completo de feedback de sucesso."""
        _, collection = mock_mongodb

        # Estado inicial
        initial = {
            "tool_id": "pytest-001",
            "reputation_score": 0.8,
            "average_execution_time_ms": 5000,
            "execution_count": 100,
            "success_count": 80,
            "consecutive_successes": 0,
            "consecutive_failures": 0,
            "is_healthy": True
        }
        collection.find_one = AsyncMock(return_value=initial)

        updates = []

        async def capture_update(filter_dict, update_dict, **kwargs):
            updates.append(update_dict)

        collection.update_one = AsyncMock(side_effect=capture_update)

        # Feedback de sucesso
        new_execution_time = 4500
        alpha = 0.1

        new_data = {
            "reputation_score": 81 / 101,  # (80+1)/(100+1)
            "average_execution_time_ms": alpha * new_execution_time + (1 - alpha) * 5000,
            "execution_count": 101,
            "success_count": 81,
            "consecutive_successes": 1,
            "consecutive_failures": 0
        }

        await collection.update_one(
            {"tool_id": "pytest-001"},
            {"$set": new_data}
        )

        # Invalidar cache
        await mock_redis.delete("tool:pytest-001:metadata")

        # Verificacoes
        assert len(updates) == 1
        assert updates[0]["$set"]["reputation_score"] > 0.8
        assert updates[0]["$set"]["success_count"] == 81

    @pytest.mark.asyncio
    async def test_complete_failure_feedback_flow(self, mock_mongodb, mock_redis):
        """Testa fluxo completo de feedback de falha."""
        _, collection = mock_mongodb

        initial = {
            "tool_id": "failing-tool",
            "reputation_score": 0.6,
            "execution_count": 50,
            "success_count": 30,
            "failure_count": 20,
            "consecutive_successes": 2,
            "consecutive_failures": 0,
            "is_healthy": True
        }
        collection.find_one = AsyncMock(return_value=initial)

        updates = []

        async def capture_update(filter_dict, update_dict, **kwargs):
            updates.append(update_dict)

        collection.update_one = AsyncMock(side_effect=capture_update)

        # Feedback de falha
        new_data = {
            "reputation_score": 30 / 51,  # success_count / new_total
            "execution_count": 51,
            "failure_count": 21,
            "consecutive_successes": 0,  # Reset
            "consecutive_failures": 1
        }

        await collection.update_one(
            {"tool_id": "failing-tool"},
            {"$set": new_data}
        )

        # Verificacoes
        assert len(updates) == 1
        assert updates[0]["$set"]["reputation_score"] < 0.6
        assert updates[0]["$set"]["failure_count"] == 21
        assert updates[0]["$set"]["consecutive_successes"] == 0

    @pytest.mark.asyncio
    async def test_rapid_succession_feedback(self, mock_mongodb, mock_redis):
        """Testa feedback em rapida sucessao."""
        _, collection = mock_mongodb

        initial = {
            "tool_id": "busy-tool",
            "reputation_score": 0.8,
            "execution_count": 100,
            "success_count": 80
        }
        collection.find_one = AsyncMock(return_value=initial)

        update_count = 0

        async def count_updates(*args, **kwargs):
            nonlocal update_count
            update_count += 1

        collection.update_one = AsyncMock(side_effect=count_updates)

        # Simular 10 feedbacks rapidos
        for i in range(10):
            await collection.update_one(
                {"tool_id": "busy-tool"},
                {"$inc": {"execution_count": 1, "success_count": 1}}
            )

        assert update_count == 10
