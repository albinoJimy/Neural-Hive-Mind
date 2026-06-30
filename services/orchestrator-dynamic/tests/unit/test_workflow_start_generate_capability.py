"""Testes do resume pós-aprovação via capacidade GENERATE (Task 3 / Fase 2).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 3.

O endpoint POST /api/v1/workflows/start (resume pós-aprovação, chamado pelo
FlowCOrchestrator) passa a honrar a capacidade GENERATE para jornadas de
geração (J3_BUILD), em vez de iniciar FluxoGWorkflow diretamente. Como a
``GenerateCapability`` usa o ``app_state.temporal_client`` injetado, o caminho
real preserva-se: ``start_workflow(FluxoGWorkflow.run, ...)`` com o
``workflow_id`` (flow-c-{correlation_id}) intacto.

Anti-verde-falso: stack explícita não suportada -> 422 (sem arrancar nada).
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


class TestGenerateCapabilityResume:
    """O resume J3_BUILD exerce a capacidade GENERATE preservando o caminho real."""

    @pytest.mark.asyncio()
    async def test_j3_build_exercises_generate_capability(self, mock_app_state, mock_settings):
        """J3_BUILD -> 200; capability usa app_state.temporal_client (FluxoGWorkflow.run)."""
        from src.workflows.fluxo_g_workflow import FluxoGWorkflow

        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start({"plan_id": "p-j3", "journey": "J3_BUILD"})

        assert resp.status_code == 200
        mock_temporal.start_workflow.assert_called_once()
        # A capacidade arranca o FluxoGWorkflow via o cliente injetado (caminho real).
        assert mock_temporal.start_workflow.call_args.args[0] == FluxoGWorkflow.run
        # workflow_id preservado no formato flow-c-{correlation_id} (id do resume),
        # NÃO o default da capacidade baseado em plan_id ({prefix}p-j3). Asserção
        # por sufixo: robusta à origem do prefixo (get_settings) na suíte completa.
        wid = mock_temporal.start_workflow.call_args.kwargs["id"]
        assert wid.endswith("flow-c-corr-1")
        assert "p-j3" not in wid

    @pytest.mark.asyncio()
    async def test_unsupported_stack_returns_422(self, mock_app_state, mock_settings):
        """J3_BUILD com stack explícita não suportada -> 422 (anti-verde-falso)."""
        mock_temporal = AsyncMock()
        mock_temporal.start_workflow = AsyncMock()
        mock_app_state.temporal_client = mock_temporal

        resp = await _post_start(
            {
                "plan_id": "p-rust",
                "journey": "J3_BUILD",
                "parameters": {"language": "rust", "framework": "actix"},
            }
        )

        assert resp.status_code == 422
        mock_temporal.start_workflow.assert_not_called()
