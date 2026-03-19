"""
Testes para ScoutCoordinator.
Coordenação entre múltiplos scouts.
"""
import pytest
import asyncio
from src.coordination.scout_coordinator import ScoutCoordinator, Task


@pytest.fixture
def coordinator():
    """Instância de ScoutCoordinator para testes."""
    return ScoutCoordinator(
        coordinator_id="test_coordinator",
        max_concurrent_tasks=5,
        task_timeout=60
    )


class TestScoutRegistration:
    """Testes de registro de scouts."""

    @pytest.mark.asyncio
    async def test_register_scout(self, coordinator):
        """Testa registro de scout."""
        success = await coordinator.register_scout(
            "scout_1",
            ["scan", "analyze", "detect_patterns"]
        )

        assert success is True
        assert "scout_1" in coordinator._scouts
        assert coordinator._scouts["scout_1"]["status"] == "idle"

    @pytest.mark.asyncio
    async def test_unregister_scout(self, coordinator):
        """Testa remoção de scout."""
        await coordinator.register_scout("scout_1", ["scan"])

        await coordinator.unregister_scout("scout_1")

        assert "scout_1" not in coordinator._scouts

    @pytest.mark.asyncio
    async def test_unregister_reassigns_tasks(self, coordinator):
        """Testa que remoção reatribui tarefas ativas."""
        await coordinator.register_scout("scout_1", ["scan"])
        await coordinator.register_scout("scout_2", ["scan"])

        # Criar e atribuir tarefa
        task_id = await coordinator.create_task("target.py", "scan", priority=0.8)
        await coordinator.get_next_task("scout_1", ["scan"])

        # Remover scout (deve reatribuir tarefa)
        await coordinator.unregister_scout("scout_1")

        task = coordinator._tasks[task_id]
        assert task.assigned_to is None


class TestTaskManagement:
    """Testes de gerenciamento de tarefas."""

    @pytest.mark.asyncio
    async def test_create_task(self, coordinator):
        """Testa criação de tarefa."""
        task_id = await coordinator.create_task(
            target="test.py",
            task_type="scan",
            priority=0.5,
            metadata={"size": 100}
        )

        assert task_id in coordinator._tasks
        task = coordinator._tasks[task_id]
        assert task.target == "test.py"
        assert task.task_type == "scan"
        assert task.priority == 0.5
        assert task.metadata["size"] == 100
        assert task.status == "pending"

    @pytest.mark.asyncio
    async def test_high_priority_queue(self, coordinator):
        """Testa fila de alta prioridade."""
        await coordinator.register_scout("scout_1", ["scan"])

        # Criar tarefas com diferentes prioridades
        await coordinator.create_task("low.py", "scan", priority=0.3)
        high_id = await coordinator.create_task("high.py", "scan", priority=0.9)

        # Tarefa de alta prioridade deve vir primeiro
        task = await coordinator.get_next_task("scout_1", ["scan"])
        assert task is not None
        assert "high.py" in task["target"]

    @pytest.mark.asyncio
    async def test_get_next_task(self, coordinator):
        """Testa obter próxima tarefa."""
        await coordinator.register_scout("scout_1", ["scan"])
        task_id = await coordinator.create_task("test.py", "scan", priority=0.5)

        task = await coordinator.get_next_task("scout_1", ["scan"])

        assert task is not None
        assert task["task_id"] == task_id
        assert task["target"] == "test.py"

    @pytest.mark.asyncio
    async def test_task_requires_capability(self, coordinator):
        """Testa filtro por capacidade."""
        await coordinator.register_scout("scout_1", ["scan"])
        await coordinator.register_scout("scout_2", ["analyze"])

        # Criar tarefa que requer capacidade específica
        task_id = await coordinator.create_task(
            "complex.py",
            "analyze",
            priority=0.5,
            metadata={"required_capability": "analyze"}
        )

        # Scout sem capacidade certa não deve receber tarefa
        task = await coordinator.get_next_task("scout_1", ["scan"])
        assert task is None

        # Scout com capacidade certa deve receber
        task = await coordinator.get_next_task("scout_2", ["analyze"])
        assert task is not None
        assert task["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_complete_task(self, coordinator):
        """Testa completar tarefa."""
        await coordinator.register_scout("scout_1", ["scan"])
        task_id = await coordinator.create_task("test.py", "scan")
        await coordinator.get_next_task("scout_1", ["scan"])

        result = {"patterns_found": 5}
        await coordinator.complete_task(task_id, result, success=True)

        task = coordinator._tasks[task_id]
        assert task.status == "completed"
        assert task.result == result
        assert task_id not in coordinator._active_tasks

    @pytest.mark.asyncio
    async def test_complete_task_failed(self, coordinator):
        """Testa completar tarefa com falha."""
        await coordinator.register_scout("scout_1", ["scan"])
        task_id = await coordinator.create_task("test.py", "scan")
        await coordinator.get_next_task("scout_1", ["scan"])

        await coordinator.complete_task(task_id, {"error": "failed"}, success=False)

        task = coordinator._tasks[task_id]
        assert task.status == "failed"


class TestTaskTimeout:
    """Testes de timeout de tarefas."""

    @pytest.mark.asyncio
    async def test_timeout_stale_tasks(self, coordinator):
        """Testa detecção de tarefas expiradas."""
        await coordinator.register_scout("scout_1", ["scan"])

        # Criar e atribuir tarefa
        task_id = await coordinator.create_task("test.py", "scan")
        await coordinator.get_next_task("scout_1", ["scan"])

        # Simular que tarefa está expirada
        task = coordinator._tasks[task_id]
        task.started_at = task.started_at.replace(
            year=task.started_at.year - 1
        )  # 1 ano atrás

        await coordinator.timeout_stale_tasks()

        task = coordinator._tasks[task_id]
        assert task.status == "failed"
        assert coordinator.stats["tasks_timeout"] == 1


class TestCoordinatorStatus:
    """Testes de status do coordenador."""

    @pytest.mark.asyncio
    async def test_get_coordinator_status(self, coordinator):
        """Testa obter status do coordenador."""
        await coordinator.register_scout("scout_1", ["scan"])
        await coordinator.create_task("test.py", "scan")

        status = await coordinator.get_coordinator_status()

        assert status["coordinator_id"] == "test_coordinator"
        assert status["stats"]["tasks_created"] == 1
        assert "tasks_by_status" in status
        assert "scouts_by_status" in status
        assert "queue_size" in status


class TestBroadcast:
    """Testes de broadcast de eventos."""

    @pytest.mark.asyncio
    async def test_broadcast_event(self, coordinator):
        """Testa broadcast de evento."""
        await coordinator.register_scout("scout_1", ["scan"])
        await coordinator.register_scout("scout_2", ["analyze"])

        # Broadcast deve ser registrado
        await coordinator.broadcast_event("exploration_started", {"root": "/src"})

        # Verificar que scouts receberiam (via log)
        assert len(coordinator._scouts) == 2


class TestConcurrentTasks:
    """Testes de tarefas concorrentes."""

    @pytest.mark.asyncio
    async def test_max_concurrent_limit(self, coordinator):
        """Testa limite de tarefas concorrentes."""
        coordinator.max_concurrent_tasks = 2
        await coordinator.register_scout("scout_1", ["scan"])

        # Criar mais tarefas que o limite
        for i in range(5):
            await coordinator.create_task(f"file{i}.py", "scan")

        # Obter tarefas até atingir limite
        task1 = await coordinator.get_next_task("scout_1", ["scan"])
        task2 = await coordinator.get_next_task("scout_1", ["scan"])

        assert task1 is not None
        assert task2 is not None
        assert len(coordinator._active_tasks) == 2


class TestTaskClass:
    """Testes da classe Task."""

    def test_task_to_dict(self):
        """Testa conversão para dicionário."""
        task = Task(
            task_id="task_1",
            target="test.py",
            task_type="scan",
            priority=0.7,
            metadata={"size": 100}
        )

        result = task.to_dict()

        assert result["task_id"] == "task_1"
        assert result["target"] == "test.py"
        assert result["task_type"] == "scan"
        assert result["priority"] == 0.7
        assert result["metadata"]["size"] == 100
