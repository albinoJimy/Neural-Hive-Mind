"""
Testes para os endpoints principais do Self-Healing Engine.

Cobre health, readiness, metrics e chaos endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import os


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock variaveis de ambiente para os testes."""
    env_vars = {"KAFKA_BOOTSTRAP_SERVERS": "localhost:9092"}

    # Salvar valores originais
    original_values = {k: os.environ.get(k) for k in env_vars.keys()}

    # Definir valores mock
    for k, v in env_vars.items():
        os.environ[k] = v

    yield

    # Restaurar valores originais
    for k, v in original_values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.mark.asyncio
async def test_health_endpoint(mock_env_vars):
    """Health check deve retornar status healthy."""
    from src.api.health import health

    response = await health()

    assert response.status == "healthy"
    assert "timestamp" in str(response)
    assert "version" in str(response)


@pytest.mark.asyncio
async def test_liveness_endpoint(mock_env_vars):
    """Liveness probe deve retornar healthy."""
    from src.api.health import liveness

    response = await liveness()

    assert response["status"] == "healthy"
    assert "timestamp" in response


@pytest.mark.asyncio
async def test_readiness_endpoint(mock_env_vars):
    """Readiness probe deve retornar healthy."""
    from src.api.health import readiness

    response = await readiness()

    assert response["status"] == "healthy"
    assert "timestamp" in response


@pytest.mark.asyncio
async def test_health_with_chaos_disabled():
    """Chaos health endpoint deve retornar disabled quando chaos nao habilitado."""
    from src.api.chaos import chaos_health

    request = MagicMock()
    request.app.state.chaos_engine = None

    response = await chaos_health(request)

    assert response["status"] == "disabled"
    assert "Chaos Engine não está habilitado" in response["message"]


@pytest.mark.asyncio
async def test_health_with_chaos_enabled():
    """Chaos health endpoint deve retornar healthy quando chaos habilitado."""
    from src.api.chaos import chaos_health

    mock_engine = MagicMock()
    mock_engine.get_active_experiments = MagicMock(return_value=[])
    mock_engine.max_concurrent_experiments = 5
    mock_engine.require_opa_approval = True
    mock_engine.list_scenarios = MagicMock(return_value=["pod_kill", "network_delay"])

    request = MagicMock()
    request.app.state.chaos_engine = mock_engine

    response = await chaos_health(request)

    assert response["status"] == "healthy"
    assert response["active_experiments"] == 0
    assert response["max_concurrent_experiments"] == 5
    assert response["opa_enabled"] is True
    assert response["scenarios_available"] == 2


@pytest.mark.asyncio
async def test_list_scenarios_success():
    """Listar cenarios deve retornar lista de cenarios disponiveis."""
    from src.api.chaos import list_scenarios, get_chaos_engine

    mock_engine = MagicMock()
    mock_engine.list_scenarios = MagicMock(return_value=["pod_kill", "network_delay", "high_cpu"])
    mock_engine.get_scenario_info = MagicMock(
        side_effect=lambda name: {"description": f"Scenario {name}", "severity": "medium"}
    )

    request = MagicMock()
    request.app.state.chaos_engine = mock_engine

    response = await list_scenarios(chaos_engine=mock_engine)

    assert response["total"] == 3
    assert len(response["scenarios"]) == 3
    assert response["scenarios"][0]["name"] in ["pod_kill", "network_delay", "high_cpu"]


@pytest.mark.asyncio
async def test_list_scenarios_chaos_disabled(mock_env_vars):
    """Listar cenarios deve retornar 503 quando chaos desabilitado."""
    from src.api.chaos import list_scenarios
    from fastapi import HTTPException

    mock_engine = None

    with pytest.raises(HTTPException) as exc_info:
        await list_scenarios(chaos_engine=mock_engine)

    assert exc_info.value.status_code == 503
    assert "Chaos Engine não está habilitado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_scenario_info():
    """Obter info de cenario deve retornar detalhes."""
    from src.api.chaos import get_scenario

    mock_engine = MagicMock()
    mock_engine.get_scenario_info = MagicMock(
        return_value={
            "description": "Kill pods to test resilience",
            "severity": "high",
            "parameters": {"namespace": "default"},
        }
    )

    response = await get_scenario("pod_kill", chaos_engine=mock_engine)

    assert response["name"] == "pod_kill"
    assert response["description"] == "Kill pods to test resilience"
    assert response["severity"] == "high"


@pytest.mark.asyncio
async def test_get_scenario_not_found():
    """Obter info de cenario inexistente deve retornar 404."""
    from src.api.chaos import get_scenario
    from fastapi import HTTPException

    mock_engine = MagicMock()
    mock_engine.get_scenario_info = MagicMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_scenario("nonexistent", chaos_engine=mock_engine)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_active_experiments():
    """Listar experimentos ativos deve retornar lista."""
    from src.api.chaos import list_active_experiments

    mock_engine = MagicMock()
    mock_exp1 = MagicMock()
    mock_exp1.model_dump = MagicMock(return_value={"id": "exp-1", "status": "running"})
    mock_exp2 = MagicMock()
    mock_exp2.model_dump = MagicMock(return_value={"id": "exp-2", "status": "running"})
    mock_engine.get_active_experiments = MagicMock(return_value=[mock_exp1, mock_exp2])

    response = await list_active_experiments(chaos_engine=mock_engine)

    assert response["active_count"] == 2
    assert len(response["experiments"]) == 2


@pytest.mark.asyncio
async def test_create_experiment(mock_env_vars):
    """Criar experimento deve retornar response com experiment_id."""
    from src.api.chaos import create_experiment
    from src.chaos.chaos_models import (
        ChaosExperimentRequest,
        FaultInjection,
        FaultType,
        TargetSelector,
    )

    mock_engine = AsyncMock()
    mock_engine.create_experiment = AsyncMock(
        return_value=MagicMock(experiment_id="exp-123", status="created")
    )

    target = TargetSelector(namespace="default", service_name="test-service")

    injection = FaultInjection(fault_type=FaultType.POD_KILL, target=target, duration_seconds=60)

    request = ChaosExperimentRequest(
        name="Test experiment",
        description="Test description",
        environment="staging",
        fault_injections=[injection],
    )

    response = await create_experiment(request, chaos_engine=mock_engine)

    assert response.experiment_id == "exp-123"
    assert response.status == "created"


@pytest.mark.asyncio
async def test_execute_scenario():
    """Executar cenario deve retornar relatorio."""
    from src.api.chaos import execute_scenario, ScenarioRequest

    mock_engine = AsyncMock()
    mock_engine.execute_scenario = AsyncMock(
        return_value=MagicMock(experiment_id="exp-123", status="completed", successful=True)
    )

    request = ScenarioRequest(
        scenario_name="pod_kill", target_service="test-service", target_namespace="default"
    )

    response = await execute_scenario(request, chaos_engine=mock_engine)

    assert response.status == "completed"
    assert response.successful is True


@pytest.mark.asyncio
async def test_rollback_experiment():
    """Rollback de experimento deve retornar sucesso."""
    from src.api.chaos import rollback_experiment

    mock_engine = AsyncMock()
    mock_engine.rollback_experiment = AsyncMock(return_value=True)

    response = await rollback_experiment("exp-123", chaos_engine=mock_engine)

    assert response["success"] is True
    assert response["experiment_id"] == "exp-123"


@pytest.mark.asyncio
async def test_validate_playbook():
    """Validar playbook deve retornar resultado."""
    from src.api.chaos import validate_playbook, PlaybookValidationRequest

    mock_engine = AsyncMock()
    mock_engine.validate_playbook = AsyncMock(
        return_value=MagicMock(valid=True, recovery_time_seconds=30)
    )

    request = PlaybookValidationRequest(
        playbook_name="test-playbook", target_service="test-service"
    )

    response = await validate_playbook(request, chaos_engine=mock_engine)

    assert response.valid is True
    assert response.recovery_time_seconds == 30


@pytest.mark.asyncio
async def test_metrics_endpoint(mock_env_vars):
    """Metrics endpoint deve retornar texto Prometheus."""
    from src.api.health import metrics
    from starlette.responses import Response

    response = await metrics()

    assert isinstance(response, Response)
    assert "text/plain" in response.headers["content-type"]
