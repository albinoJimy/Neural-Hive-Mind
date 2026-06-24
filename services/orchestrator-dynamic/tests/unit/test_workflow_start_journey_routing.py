"""Testes do roteamento por Journey no endpoint POST /api/v1/workflows/start.

Este endpoint é o ponto de resume pós-aprovação: é chamado pelo
``FlowCOrchestrator`` (via ``OrchestratorClient.start_workflow``) depois de um
plano ``review_required`` ser aprovado. Antes da Fase 1 da spec j3-build-generate
o endpoint iniciava **sempre** ``OrchestrationWorkflow`` (hardcoded), pelo que
planos ``J3_BUILD`` aprovados caíam em orquestração genérica em vez do
``FluxoGWorkflow`` (gerando tickets query/transform parasitas).

Contrato esperado (espelha ``decision_consumer._select_workflow_class_by_journey``):
    - J3_BUILD       -> FluxoGWorkflow (geração / fluxo G)
    - J2_ORCHESTRATE -> OrchestrationWorkflow
    - J4_MIGRATE     -> OrchestrationWorkflow
    - J1_PLAN_ONLY   -> sem execução (não inicia workflow)
    - sem journey / UNKNOWN -> fallback por workflow_type (retrocompatível)
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def mock_app_state():
    with patch("src.main.app_state") as mock_state:
        yield mock_state


@pytest.fixture()
def mock_settings():
    from src.config.settings import OrchestratorSettings

    with patch("src.main.get_settings") as mock_get_settings:
        mock_config = OrchestratorSettings(
            kafka_bootstrap_servers="localhost:9092",
            postgres_host="localhost",
            postgres_user="test",
            postgres_password="test",
            mongodb_uri="mongodb://localhost:27017",
            redis_cluster_nodes="localhost:6379",
            temporal_workflow_id_prefix="nhm-",
            temporal_task_queue="orchestration-tasks",
        )
        mock_get_settings.return_value = mock_config
        yield mock_config


async def _post_start(cognitive_plan: dict, correlation_id: str = "corr-1"):
    from src.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(
            "/api/v1/workflows/start",
            json={"cognitive_plan": cognitive_plan, "correlation_id": correlation_id},
        )


class TestJourneyRoutingPostApproval:
    """O endpoint deve honrar a journey do plano (não hardcodear Orchestration)."""

    @pytest.mark.asyncio()
    async def test_j3_build_starts_fluxo_g_workflow(self, mock_app_state, mock_settings):
        """J3_BUILD -> FluxoGWorkflow (caminho real de geração)."""
        from src.workflows.fluxo_g_workflow import FluxoGWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-j3", "journey": "J3_BUILD"})

        assert resp.status_code == 200
        mock_temporal.start_workflow.assert_called_once()
        assert mock_temporal.start_workflow.call_args.args[0] == FluxoGWorkflow.run

    @pytest.mark.asyncio()
    async def test_j3_build_case_insensitive(self, mock_app_state, mock_settings):
        """journey minúscula ('j3_build') também roteia para FluxoG."""
        from src.workflows.fluxo_g_workflow import FluxoGWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-j3b", "journey": "j3_build"})

        assert resp.status_code == 200
        assert mock_temporal.start_workflow.call_args.args[0] == FluxoGWorkflow.run

    @pytest.mark.asyncio()
    async def test_j2_orchestrate_starts_orchestration(self, mock_app_state, mock_settings):
        """J2_ORCHESTRATE -> OrchestrationWorkflow."""
        from src.workflows.orchestration_workflow import OrchestrationWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-j2", "journey": "J2_ORCHESTRATE"})

        assert resp.status_code == 200
        assert mock_temporal.start_workflow.call_args.args[0] == OrchestrationWorkflow.run

    @pytest.mark.asyncio()
    async def test_j4_migrate_starts_orchestration(self, mock_app_state, mock_settings):
        """J4_MIGRATE -> OrchestrationWorkflow (cutover é sub-fluxo da orquestração)."""
        from src.workflows.orchestration_workflow import OrchestrationWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-j4", "journey": "J4_MIGRATE"})

        assert resp.status_code == 200
        assert mock_temporal.start_workflow.call_args.args[0] == OrchestrationWorkflow.run

    @pytest.mark.asyncio()
    async def test_j1_plan_only_does_not_start_workflow(self, mock_app_state, mock_settings):
        """J1_PLAN_ONLY -> sem execução (anti-verde-falso: não inicia workflow silenciosamente)."""
        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-j1", "journey": "J1_PLAN_ONLY"})

        assert resp.status_code == 200
        mock_temporal.start_workflow.assert_not_called()
        assert resp.json()["status"] != "started"

    @pytest.mark.asyncio()
    async def test_no_journey_falls_back_to_orchestration(self, mock_app_state, mock_settings):
        """Plano legado sem journey -> fallback por workflow_type (retrocompat preservada)."""
        from src.workflows.orchestration_workflow import OrchestrationWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-legacy"})

        assert resp.status_code == 200
        mock_temporal.start_workflow.assert_called_once()
        assert mock_temporal.start_workflow.call_args.args[0] == OrchestrationWorkflow.run

    @pytest.mark.asyncio()
    async def test_unknown_journey_falls_back_to_orchestration(self, mock_app_state, mock_settings):
        """journey='UNKNOWN' explícita -> fallback por workflow_type (default Orchestration)."""
        from src.workflows.orchestration_workflow import OrchestrationWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-unknown", "journey": "UNKNOWN"})

        assert resp.status_code == 200
        mock_temporal.start_workflow.assert_called_once()
        assert mock_temporal.start_workflow.call_args.args[0] == OrchestrationWorkflow.run

    @pytest.mark.asyncio()
    async def test_generation_workflow_type_without_journey_falls_back_to_fluxo_g(
        self, mock_app_state, mock_settings
    ):
        """Fallback honra workflow_type=generation -> FluxoGWorkflow (sem journey)."""
        from src.workflows.fluxo_g_workflow import FluxoGWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-gen", "workflow_type": "generation"})

        assert resp.status_code == 200
        assert mock_temporal.start_workflow.call_args.args[0] == FluxoGWorkflow.run
