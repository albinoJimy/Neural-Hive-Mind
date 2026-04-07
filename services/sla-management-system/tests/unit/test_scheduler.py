"""
Unit tests para ScheduleManager.

Testa gerenciamento de schedules de workflows Temporal.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from src.models.schedule import (
    Schedule,
    ScheduleType,
    ScheduleStatus,
    ScheduleTrigger,
    SchedulePriority,
    ScheduleExecution,
)
from src.services.scheduler import ScheduleManager


@pytest.fixture
def mock_postgresql_client():
    """PostgreSQL client mock."""
    client = AsyncMock()
    client.fetchrow = AsyncMock(return_value=None)
    client.fetch_all = AsyncMock(return_value=[])
    client.execute = AsyncMock()
    return client


@pytest.fixture
def mock_temporal_client():
    """Temporal client mock."""
    client = AsyncMock()
    handle = MagicMock()
    handle.id = "test-workflow-id"
    client.start_workflow = AsyncMock(return_value=handle)
    return client


@pytest.fixture
def schedule_manager(mock_postgresql_client, mock_temporal_client):
    """ScheduleManager instance para testes."""
    return ScheduleManager(
        postgresql_client=mock_postgresql_client,
        temporal_client=mock_temporal_client,
        temporal_namespace="default",
        temporal_task_queue="sla-tasks",
    )


@pytest.fixture
def sample_trigger():
    """Trigger de exemplo."""
    return ScheduleTrigger(cron_expression="0 * * * *", parameters={"slo_id": "test-slo"})


class TestScheduleManagerCreation:
    """Testes de criação de schedules."""

    @pytest.mark.asyncio
    async def test_create_cron_schedule(
        self, schedule_manager, mock_postgresql_client, sample_trigger
    ):
        """Deve criar schedule cron com sucesso."""
        mock_postgresql_client.fetchrow.return_value = None

        schedule_id = await schedule_manager.create_schedule(
            workflow="BudgetRecalculationWorkflow",
            schedule_type=ScheduleType.CRON,
            trigger=sample_trigger,
            priority=SchedulePriority.MEDIUM,
        )

        assert schedule_id is not None
        assert len(schedule_id) > 0

    @pytest.mark.asyncio
    async def test_create_event_schedule(self, schedule_manager):
        """Deve criar schedule baseado em evento."""
        trigger = ScheduleTrigger(
            event_type="slo.violation",
            event_filter={"severity": "CRITICAL"},
            parameters={"slo_id": "test-slo"},
        )

        schedule_id = await schedule_manager.create_schedule(
            workflow="RemediationWorkflow",
            schedule_type=ScheduleType.EVENT,
            trigger=trigger,
            priority=SchedulePriority.HIGH,
        )

        assert schedule_id is not None

    @pytest.mark.asyncio
    async def test_create_manual_schedule(self, schedule_manager):
        """Deve criar schedule manual."""
        trigger = ScheduleTrigger(parameters={"manual_trigger": True})

        schedule_id = await schedule_manager.create_schedule(
            workflow="ManualWorkflow",
            schedule_type=ScheduleType.MANUAL,
            trigger=trigger,
            priority=SchedulePriority.LOW,
        )

        assert schedule_id is not None


class TestScheduleManagerRetrieval:
    """Testes de recuperação de schedules."""

    @pytest.mark.asyncio
    async def test_get_schedule_found(self, schedule_manager, mock_postgresql_client):
        """Deve retornar schedule quando encontrado."""
        from json import dumps

        mock_row = {
            "schedule_id": "test-id",
            "workflow": "TestWorkflow",
            "schedule_type": "cron",
            "trigger_data": dumps({"cron_expression": "0 * * * *", "parameters": {}}),
            "priority": "medium",
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_run_at": None,
            "next_run_at": None,
            "total_runs": 0,
            "failure_count": 0,
            "metadata": "{}",
        }
        mock_postgresql_client.fetchrow.return_value = mock_row

        schedule = await schedule_manager.get_schedule("test-id")

        assert schedule is not None
        assert schedule.schedule_id == "test-id"
        assert schedule.workflow == "TestWorkflow"
        assert schedule.status == ScheduleStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_get_schedule_not_found(self, schedule_manager, mock_postgresql_client):
        """Deve retornar None quando não encontrado."""
        mock_postgresql_client.fetchrow.return_value = None

        schedule = await schedule_manager.get_schedule("non-existent")

        assert schedule is None

    @pytest.mark.asyncio
    async def test_list_schedules(self, schedule_manager, mock_postgresql_client):
        """Deve listar schedules."""
        from json import dumps

        mock_rows = [
            {
                "schedule_id": "test-id",
                "workflow": "TestWorkflow",
                "schedule_type": "cron",
                "trigger_data": dumps({"cron_expression": "0 * * * *"}),
                "priority": "medium",
                "status": "active",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "last_run_at": None,
                "next_run_at": None,
                "total_runs": 0,
                "failure_count": 0,
                "metadata": "{}",
            }
        ]
        mock_postgresql_client.fetch_all.return_value = mock_rows

        schedules = await schedule_manager.list_schedules()

        assert len(schedules) == 1
        assert schedules[0].schedule_id == "test-id"


class TestScheduleManagerTrigger:
    """Testes de trigger de workflows."""

    @pytest.mark.asyncio
    async def test_trigger_workflow_success(
        self, schedule_manager, mock_postgresql_client, mock_temporal_client
    ):
        """Deve disparar workflow com sucesso."""
        from json import dumps

        # Mock get_schedule
        mock_row = {
            "schedule_id": "test-id",
            "workflow": "TestWorkflow",
            "schedule_type": "cron",
            "trigger_data": dumps({"parameters": {"test": "value"}}),
            "priority": "medium",
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_run_at": None,
            "next_run_at": None,
            "total_runs": 0,
            "failure_count": 0,
            "metadata": "{}",
        }
        mock_postgresql_client.fetchrow.return_value = mock_row

        result = await schedule_manager.trigger_workflow("test-id", manual=True)

        assert result["schedule_id"] == "test-id"
        assert result["workflow_id"] == "test-workflow-id"
        assert result["manual"] is True

    @pytest.mark.asyncio
    async def test_trigger_workflow_not_found(self, schedule_manager, mock_postgresql_client):
        """Deve falhar quando schedule não existe."""
        mock_postgresql_client.fetchrow.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await schedule_manager.trigger_workflow("non-existent")

    @pytest.mark.asyncio
    async def test_trigger_workflow_paused(self, schedule_manager, mock_postgresql_client):
        """Deve falhar quando schedule está pausado."""
        from json import dumps

        mock_row = {
            "schedule_id": "test-id",
            "workflow": "TestWorkflow",
            "schedule_type": "cron",
            "trigger_data": dumps({}),
            "priority": "medium",
            "status": "paused",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_run_at": None,
            "next_run_at": None,
            "total_runs": 0,
            "failure_count": 0,
            "metadata": "{}",
        }
        mock_postgresql_client.fetchrow.return_value = mock_row

        with pytest.raises(ValueError, match="not active"):
            await schedule_manager.trigger_workflow("test-id")


class TestScheduleManagerPauseResume:
    """Testes de pausa e retomada de schedules."""

    @pytest.mark.asyncio
    async def test_pause_schedule(self, schedule_manager, mock_postgresql_client):
        """Deve pausar schedule com sucesso."""
        result = await schedule_manager.pause_schedule("test-id")

        assert result["status"] == "paused"
        assert result["schedule_id"] == "test-id"

    @pytest.mark.asyncio
    async def test_resume_schedule(self, schedule_manager, mock_postgresql_client):
        """Deve retomar schedule pausado."""
        from json import dumps

        # Mock get_schedule
        mock_row = {
            "schedule_id": "test-id",
            "workflow": "TestWorkflow",
            "schedule_type": "cron",
            "trigger_data": dumps({"cron_expression": "0 * * * *"}),
            "priority": "medium",
            "status": "paused",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_run_at": None,
            "next_run_at": None,
            "total_runs": 0,
            "failure_count": 0,
            "metadata": "{}",
        }
        mock_postgresql_client.fetchrow.return_value = mock_row

        result = await schedule_manager.resume_schedule("test-id")

        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_delete_schedule(self, schedule_manager, mock_postgresql_client):
        """Deve deletar schedule com sucesso."""
        result = await schedule_manager.delete_schedule("test-id")

        assert result["deleted"] is True
        assert result["schedule_id"] == "test-id"


class TestNextRunCalculation:
    """Testes de cálculo de próxima execução."""

    def test_calculate_next_run_hourly(self, schedule_manager):
        """Deve calcular próxima execução para hourly."""
        next_run = schedule_manager._calculate_next_run("0 * * * *")

        assert next_run is not None
        assert next_run > datetime.now(timezone.utc)
        # Deve ser dentro de 1-2 horas
        diff = (next_run - datetime.now(timezone.utc)).total_seconds()
        assert 0 < diff <= 7200

    def test_calculate_next_run_daily(self, schedule_manager):
        """Deve calcular próxima execução para diário."""
        next_run = schedule_manager._calculate_next_run("0 0 * * *")

        assert next_run is not None
        # Deve ser no próximo dia (hora = 0, minuto = 0)
        assert next_run.hour == 0
        assert next_run.minute == 0
        # Deve ser no futuro
        assert next_run > datetime.now(timezone.utc)

    def test_calculate_next_run_weekly(self, schedule_manager):
        """Deve calcular próxima execução para semanal."""
        next_run = schedule_manager._calculate_next_run("0 2 * * 0")

        assert next_run is not None
        # Deve ser dentro de 1-7 dias
        diff = (next_run - datetime.now(timezone.utc)).total_seconds()
        assert 0 < diff <= 604800


class TestScheduleManagerShutdown:
    """Testes de shutdown do scheduler."""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_running_schedules(self, schedule_manager):
        """Deve cancelar tasks em execução no shutdown."""
        # Criar task mock
        task = AsyncMock()
        task.cancel = MagicMock()
        schedule_manager._running_schedules["test-id"] = task

        await schedule_manager.shutdown()

        task.cancel.assert_called_once()
        assert "test-id" not in schedule_manager._running_schedules
