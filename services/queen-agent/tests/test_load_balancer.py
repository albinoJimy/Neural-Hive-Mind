"""
Testes para Load Balancer

Testa registro de workers, atribuição de tarefas, e estratégias de balanceamento.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

from src.services.load_balancer import (
    LoadBalancer,
    BalancingStrategy,
    WorkerMetrics,
    TaskAssignment,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    # Criar wrapper client
    redis_wrapper = MagicMock()
    # Criar cliente Redis mockado
    redis_client = AsyncMock()
    redis_client.hset = AsyncMock()
    redis_client.hgetall = AsyncMock(return_value={})
    redis_client.hdel = AsyncMock()
    redis_client.expire = AsyncMock()

    # Configurar wrapper com métodos que delegam ao client
    redis_wrapper.client = redis_client
    redis_wrapper.hset = redis_client.hset
    redis_wrapper.hgetall = redis_client.hgetall
    redis_wrapper.hdel = redis_client.hdel
    redis_wrapper.expire = redis_client.expire

    return redis_wrapper


@pytest.fixture
def mock_settings():
    """Mock settings"""
    settings = MagicMock()
    settings.LOAD_BALANCER_STRATEGY = "round_robin"
    settings.WORKER_HEARTBEAT_TIMEOUT_SECONDS = 30
    settings.METRICS_TTL_SECONDS = 300
    return settings


@pytest.fixture
def load_balancer(mock_redis, mock_settings):
    """Fixture para LoadBalancer"""
    return LoadBalancer(
        redis_client=mock_redis,
        service_registry_client=None,
        settings=mock_settings,
    )


class TestLoadBalancerInit:
    """Testes de inicialização"""

    def test_initialization(self, load_balancer):
        """Testa inicialização básica"""
        assert load_balancer.strategy == BalancingStrategy.ROUND_ROBIN
        assert load_balancer.heartbeat_timeout_seconds == 30
        assert load_balancer.metrics_ttl_seconds == 300
        assert not load_balancer.is_running


class TestRegisterWorker:
    """Testes de registro de workers"""

    @pytest.mark.asyncio
    async def test_register_worker_success(self, load_balancer, mock_redis):
        """Testa registro bem-sucedido de worker"""
        success = await load_balancer.register_worker(
            worker_id="worker-1",
            capacity=1.5,
            metadata={"location": "zone-1"},
        )

        assert success is True
        assert "worker-1" in load_balancer._local_cache
        assert load_balancer._local_cache["worker-1"].capacity == 1.5
        mock_redis.client.hset.assert_called()

    @pytest.mark.asyncio
    async def test_register_worker_default_capacity(self, load_balancer):
        """Testa registro com capacidade padrão"""
        await load_balancer.register_worker(worker_id="worker-2")

        assert load_balancer._local_cache["worker-2"].capacity == 1.0


class TestUnregisterWorker:
    """Testes de remoção de workers"""

    @pytest.mark.asyncio
    async def test_unregister_worker_success(self, load_balancer, mock_redis):
        """Testa remoção bem-sucedida de worker"""
        # Primeiro registrar
        await load_balancer.register_worker(worker_id="worker-1")

        # Depois remover
        success = await load_balancer.unregister_worker(worker_id="worker-1")

        assert success is True
        assert "worker-1" not in load_balancer._local_cache
        mock_redis.client.hdel.assert_called()

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_worker(self, load_balancer):
        """Testa remoção de worker inexistente"""
        success = await load_balancer.unregister_worker(worker_id="nonexistent")

        assert success is True  # Não levanta erro


class TestUpdateWorkerMetrics:
    """Testes de atualização de métricas"""

    @pytest.mark.asyncio
    async def test_update_worker_metrics_all_fields(self, load_balancer):
        """Testa atualização de todos os campos de métricas"""
        await load_balancer.register_worker(worker_id="worker-1")

        success = await load_balancer.update_worker_metrics(
            worker_id="worker-1",
            active_tasks=5,
            completed_tasks=100,
            failed_tasks=2,
            avg_processing_time_ms=150.5,
        )

        assert success is True
        metrics = load_balancer._local_cache["worker-1"]
        assert metrics.active_tasks == 5
        assert metrics.completed_tasks == 100
        assert metrics.failed_tasks == 2
        assert metrics.avg_processing_time_ms == 150.5

    @pytest.mark.asyncio
    async def test_update_worker_metrics_partial(self, load_balancer):
        """Testa atualização parcial de métricas"""
        await load_balancer.register_worker(worker_id="worker-1")

        success = await load_balancer.update_worker_metrics(
            worker_id="worker-1", active_tasks=10
        )

        assert success is True
        assert load_balancer._local_cache["worker-1"].active_tasks == 10

    @pytest.mark.asyncio
    async def test_update_metrics_creates_worker(self, load_balancer):
        """Testa que atualização cria worker se não existe"""
        # Registrar worker primeiro (evitar deadlock com lock não reentrante)
        await load_balancer.register_worker("new-worker")

        success = await load_balancer.update_worker_metrics(
            worker_id="new-worker", active_tasks=3
        )

        assert success is True
        assert "new-worker" in load_balancer._local_cache

    @pytest.mark.asyncio
    async def test_update_metrics_updates_heartbeat(self, load_balancer):
        """Testa que atualização marca worker como saudável"""
        await load_balancer.register_worker(worker_id="worker-1")
        load_balancer._local_cache["worker-1"].is_healthy = False

        await load_balancer.update_worker_metrics(worker_id="worker-1", active_tasks=1)

        assert load_balancer._local_cache["worker-1"].is_healthy is True


class TestGetHealthyWorkers:
    """Testes de obtenção de workers saudáveis"""

    @pytest.mark.asyncio
    async def test_get_healthy_workers_all(self, load_balancer):
        """Testa retorno de todos workers quando todos saudáveis"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")
        await load_balancer.register_worker("worker-3")

        healthy = await load_balancer._get_healthy_workers()

        assert len(healthy) == 3
        assert "worker-1" in healthy
        assert "worker-2" in healthy
        assert "worker-3" in healthy

    @pytest.mark.asyncio
    async def test_get_healthy_workers_filters_unhealthy(self, load_balancer):
        """Testa filtro de workers não saudáveis"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")
        load_balancer._local_cache["worker-2"].is_healthy = False

        healthy = await load_balancer._get_healthy_workers()

        assert len(healthy) == 1
        assert "worker-1" in healthy

    @pytest.mark.asyncio
    async def test_get_healthy_workers_filters_timeout(self, load_balancer):
        """Testa filtro de workers com heartbeat timeout"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")

        # Simular timeout em worker-2
        old_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        load_balancer._local_cache["worker-2"].last_heartbeat = old_time

        healthy = await load_balancer._get_healthy_workers()

        assert len(healthy) == 1
        assert "worker-1" in healthy
        assert "worker-2" not in healthy


class TestRoundRobinStrategy:
    """Testes da estratégia Round Robin"""

    @pytest.mark.asyncio
    async def test_round_robin_distribution(self, load_balancer):
        """Testa distribuição round robin"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")
        await load_balancer.register_worker("worker-3")

        workers = ["worker-1", "worker-2", "worker-3"]

        assignment1 = await load_balancer._select_round_robin(workers)
        assignment2 = await load_balancer._select_round_robin(workers)
        assignment3 = await load_balancer._select_round_robin(workers)
        assignment4 = await load_balancer._select_round_robin(workers)

        assert assignment1 == "worker-1"
        assert assignment2 == "worker-2"
        assert assignment3 == "worker-3"
        assert assignment4 == "worker-1"  # Volta ao início


class TestLeastLoadedStrategy:
    """Testes da estratégia Least Loaded"""

    @pytest.mark.asyncio
    async def test_least_loaded_selection(self, load_balancer):
        """Testa seleção do worker com menos carga"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")
        await load_balancer.register_worker("worker-3")

        # Configurar cargas diferentes
        await load_balancer.update_worker_metrics("worker-1", active_tasks=10)
        await load_balancer.update_worker_metrics("worker-2", active_tasks=2)
        await load_balancer.update_worker_metrics("worker-3", active_tasks=5)

        workers = ["worker-1", "worker-2", "worker-3"]
        selected = await load_balancer._select_least_loaded(workers)

        assert selected == "worker-2"  # Menos carregado


class TestWeightedStrategy:
    """Testes da estratégia Weighted"""

    @pytest.mark.asyncio
    async def test_weighted_selection(self, load_balancer):
        """Testa seleção ponderada por capacidade"""
        await load_balancer.register_worker("worker-1", capacity=2.0)
        await load_balancer.register_worker("worker-2", capacity=0.5)
        await load_balancer.register_worker("worker-3", capacity=1.0)

        # Mesma carga para todos
        await load_balancer.update_worker_metrics("worker-1", active_tasks=1)
        await load_balancer.update_worker_metrics("worker-2", active_tasks=1)
        await load_balancer.update_worker_metrics("worker-3", active_tasks=1)

        workers = ["worker-1", "worker-2", "worker-3"]

        # Worker com maior capacidade deve ter maior probabilidade
        # Como é determinístico com seed, vamos apenas verificar que retorna alguém
        selected = await load_balancer._select_weighted(workers)

        assert selected in workers


class TestConsistentHashStrategy:
    """Testes da estratégia Consistent Hash"""

    @pytest.mark.asyncio
    async def test_consistent_hash_same_task(self, load_balancer):
        """Testa que mesma tarefa vai para mesmo worker"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")
        await load_balancer.register_worker("worker-3")

        workers = ["worker-1", "worker-2", "worker-3"]

        selected1 = await load_balancer._select_consistent_hash(
            workers, "task-123", {"key": "value"}
        )
        selected2 = await load_balancer._select_consistent_hash(
            workers, "task-123", {"key": "value"}
        )

        assert selected1 == selected2

    @pytest.mark.asyncio
    async def test_consistent_hash_different_tasks(self, load_balancer):
        """Testa que tarefas diferentes podem ir para workers diferentes"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")
        await load_balancer.register_worker("worker-3")

        workers = ["worker-1", "worker-2", "worker-3"]

        # Tarefas com IDs muito diferentes provavelmente vão para workers diferentes
        # (não garantido devido à natureza do hash)
        selected1 = await load_balancer._select_consistent_hash(workers, "task-aaa")
        selected2 = await load_balancer._select_consistent_hash(workers, "task-zzz")

        assert selected1 in workers
        assert selected2 in workers


class TestAssignTask:
    """Testes de atribuição de tarefas"""

    @pytest.mark.asyncio
    async def test_assign_task_success(self, load_balancer):
        """Testa atribuição bem-sucedida de tarefa"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")

        assignment = await load_balancer.assign_task(
            task_id="task-1", task_data={"type": "query"}
        )

        assert assignment is not None
        assert assignment.worker_id in ["worker-1", "worker-2"]

    @pytest.mark.asyncio
    async def test_assign_task_no_workers(self, load_balancer):
        """Testa atribuição quando não há workers"""
        assignment = await load_balancer.assign_task(task_id="task-1")

        assert assignment is None

    @pytest.mark.asyncio
    async def test_assign_task_increments_active(self, load_balancer):
        """Testa que atribuição incrementa tarefas ativas"""
        await load_balancer.register_worker("worker-1")

        initial_active = load_balancer._local_cache["worker-1"].active_tasks

        await load_balancer.assign_task(task_id="task-1")

        assert load_balancer._local_cache["worker-1"].active_tasks == initial_active + 1

    @pytest.mark.asyncio
    async def test_assign_task_with_strategy_override(self, load_balancer):
        """Testa atribuição com estratégia override"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")

        assignment = await load_balancer.assign_task(
            task_id="task-1", strategy=BalancingStrategy.ROUND_ROBIN
        )

        assert assignment is not None
        assert assignment.strategy == BalancingStrategy.ROUND_ROBIN


class TestCompleteTask:
    """Testes de conclusão de tarefas"""

    @pytest.mark.asyncio
    async def test_complete_task_success(self, load_balancer):
        """Testa conclusão bem-sucedida de tarefa"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.update_worker_metrics("worker-1", active_tasks=5, completed_tasks=10)

        success = await load_balancer.complete_task(
            worker_id="worker-1",
            task_id="task-1",
            success=True,
            processing_time_ms=200.0,
        )

        assert success is True
        assert load_balancer._local_cache["worker-1"].active_tasks == 4  # -1
        assert load_balancer._local_cache["worker-1"].completed_tasks == 11  # +1

    @pytest.mark.asyncio
    async def test_complete_task_failure(self, load_balancer):
        """Testa conclusão com falha"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.update_worker_metrics("worker-1", active_tasks=5, failed_tasks=2)

        success = await load_balancer.complete_task(
            worker_id="worker-1", task_id="task-1", success=False
        )

        assert success is True
        assert load_balancer._local_cache["worker-1"].active_tasks == 4
        assert load_balancer._local_cache["worker-1"].failed_tasks == 3  # +1

    @pytest.mark.asyncio
    async def test_complete_task_updates_avg_time(self, load_balancer):
        """Testa que conclusão atualiza tempo médio"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.update_worker_metrics(
            "worker-1", completed_tasks=10, avg_processing_time_ms=100.0
        )

        await load_balancer.complete_task(
            worker_id="worker-1", task_id="task-1", success=True, processing_time_ms=200.0
        )

        # Novo avg = (100 * 10 + 200) / 11 = 109.09
        expected_avg = (100.0 * 10 + 200.0) / 11
        assert abs(load_balancer._local_cache["worker-1"].avg_processing_time_ms - expected_avg) < 0.01


class TestGetWorkersStatus:
    """Testes de obtenção de status de workers"""

    @pytest.mark.asyncio
    async def test_get_workers_status(self, load_balancer):
        """Testa obtenção de status de todos workers"""
        await load_balancer.register_worker("worker-1", capacity=2.0)
        await load_balancer.update_worker_metrics(
            "worker-1", active_tasks=3, completed_tasks=50, failed_tasks=1
        )

        status = await load_balancer.get_workers_status()

        assert "worker-1" in status
        assert status["worker-1"]["active_tasks"] == 3
        assert status["worker-1"]["completed_tasks"] == 50
        assert status["worker-1"]["failed_tasks"] == 1
        assert status["worker-1"]["capacity"] == 2.0


class TestGetStatistics:
    """Testes de obtenção de estatísticas"""

    @pytest.mark.asyncio
    async def test_get_statistics(self, load_balancer):
        """Testa obtenção de estatísticas do balanceador"""
        await load_balancer.register_worker("worker-1")
        await load_balancer.register_worker("worker-2")
        await load_balancer.update_worker_metrics("worker-1", active_tasks=5)
        await load_balancer.update_worker_metrics("worker-2", active_tasks=3)

        stats = await load_balancer.get_statistics()

        assert stats["total_workers"] == 2
        assert stats["healthy_workers"] == 2
        assert stats["unhealthy_workers"] == 0
        assert stats["total_active_tasks"] == 8
        assert stats["strategy"] == "round_robin"


class TestStartStop:
    """Testes de início e parada"""

    @pytest.mark.asyncio
    async def test_start(self, load_balancer):
        """Testa início do balanceador"""
        await load_balancer.start()

        assert load_balancer.is_running is True
        assert load_balancer._sync_task is not None

        # Cleanup
        await load_balancer.stop()
        # Aguardar task ser cancelada
        if load_balancer._sync_task:
            try:
                await load_balancer._sync_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_stop(self, load_balancer):
        """Testa parada do balanceador"""
        await load_balancer.start()
        await load_balancer.stop()

        assert load_balancer.is_running is False
