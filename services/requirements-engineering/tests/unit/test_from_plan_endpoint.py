"""
Teste do endpoint POST /requirements/from-plan (Task 5 — Fluxo G G1).

O orchestrator (activity generate_requirements) faz POST JSON para
/api/v1/requirements/from-plan, mas o serviço só expunha /generate com
query params. Este teste cobre o novo endpoint com JSON body.

Monta uma app FastAPI mínima apenas com o router de requirements para
evitar dependências de infra carregadas por src.main.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Garantir que o diretório do serviço está no path (para `import src...`)
_SERVICE_ROOT = Path(__file__).parent.parent.parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))


@pytest.fixture
def client_with_mocks():
    """
    Monta TestClient com o RequirementsEngineer e o repository mockados,
    de forma a testar apenas o contrato HTTP do endpoint /from-plan.
    """
    from src import dependencies
    from src.api.routers import requirements as requirements_router
    from src.models.requirements import RequirementsSet

    fake_set = RequirementsSet(
        id="REQ-SET-PLAN-1",
        cognitive_plan_id="PLAN-1",
        requirements=[],
        functional_count=0,
        non_functional_count=0,
    )

    engineer = MagicMock()
    engineer.generate_from_cognitive_plan = AsyncMock(return_value=fake_set)

    repository = MagicMock()
    repository.save_set = AsyncMock(return_value=fake_set)
    repository.create = AsyncMock(return_value=None)

    dependencies.set_requirements_engineer(engineer)

    app = FastAPI()
    app.include_router(requirements_router.router, prefix="/api/v1")
    app.dependency_overrides[requirements_router.get_repository] = lambda: repository

    with TestClient(app) as client:
        yield client, engineer

    app.dependency_overrides.clear()


def test_from_plan_accepts_json_body_returns_200(client_with_mocks):
    client, engineer = client_with_mocks

    resp = client.post(
        "/api/v1/requirements/from-plan",
        json={
            "plan_id": "PLAN-1",
            "plan_text": "Construir um serviço de notificações",
            "context": {"original_intent": "notificações", "intent_id": "INT-1"},
            "generate_user_stories": True,
            "generate_acceptance_criteria": True,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["requirements_set_id"] == "REQ-SET-PLAN-1"
    assert data["cognitive_plan_id"] == "PLAN-1"

    engineer.generate_from_cognitive_plan.assert_awaited_once()
    call = engineer.generate_from_cognitive_plan.await_args
    assert call.kwargs.get("plan_id") == "PLAN-1"
    assert call.kwargs.get("plan_text") == "Construir um serviço de notificações"


def test_generate_endpoint_still_works_with_query_params(client_with_mocks):
    """O endpoint /generate original (query params) não deve quebrar."""
    client, engineer = client_with_mocks

    resp = client.post(
        "/api/v1/requirements/generate",
        params={"plan_id": "PLAN-2", "plan_text": "outro plano"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["requirements_set_id"] == "REQ-SET-PLAN-1"
