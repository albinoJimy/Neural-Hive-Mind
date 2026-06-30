"""
Testes unitários da GenerateCapability (Task 2 / Fase 1).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 2 (Capability).

Provam que:
- `start` resolve a estratégia e **inicia** o FluxoGWorkflow com o input certo
  (id por plano, task_queue, cognitive_plan enriquecido com language/framework),
  devolvendo um GenerateHandle (cliente Temporal mockado);
- stack desconhecida → UnsupportedStackError sem iniciar o workflow (FAILED sem
  iniciar — anti-verde-falso);
- `map_result` (função pura) traduz o output do FluxoGWorkflow:
  sucesso deployed → completed; status != completed / sem artifact_id /
  deployment não deployed → failed com razão.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from src.capabilities.generate.capability import GenerateCapability, GenerateHandle
from src.capabilities.generate.contract import GenerateRequest, GenerateResult, GenerateTarget
from src.capabilities.generate.stacks import UnsupportedStackError
from src.workflows.fluxo_g_workflow import FluxoGWorkflow

PLAN_ID = "plan-abc-123"
JOURNEY = "J3_BUILD"
TASK_QUEUE = "fluxo-g-queue"
PREFIX = "fluxo-g-"


def _request(language: str = "python", framework: str = "fastapi") -> GenerateRequest:
    return GenerateRequest(
        plan_id=PLAN_ID,
        journey=JOURNEY,
        cognitive_plan={"plan_id": PLAN_ID, "parameters": {"existing": "keep"}},
        target=GenerateTarget(language=language, framework=framework),
    )


# =============================================================================
# start — inicia o FluxoGWorkflow com o input certo
# =============================================================================


@pytest.mark.asyncio
async def test_start_inicia_workflow_com_input_certo():
    temporal_client = AsyncMock()
    capability = GenerateCapability(
        temporal_client=temporal_client,
        task_queue=TASK_QUEUE,
        workflow_id_prefix=PREFIX,
    )

    handle = await capability.start(_request())

    # Iniciado exatamente uma vez
    temporal_client.start_workflow.assert_called_once()
    call = temporal_client.start_workflow.call_args

    # 1.º arg posicional é FluxoGWorkflow.run
    assert call.args[0] is FluxoGWorkflow.run

    # id por plano e task_queue injetado
    assert call.kwargs["id"] == f"{PREFIX}{PLAN_ID}"
    assert call.kwargs["task_queue"] == TASK_QUEUE

    # input_data (2.º arg posicional) com cognitive_plan enriquecido
    input_data = call.args[1]
    assert input_data["consolidated_decision"] is None
    assert input_data["is_direct_plan"] is True
    params = input_data["cognitive_plan"]["parameters"]
    assert params["framework"] == "fastapi"
    assert params["language"] == "python"
    # não sobrepõe o que o plano já tinha
    assert params["existing"] == "keep"

    # Handle devolvido
    assert isinstance(handle, GenerateHandle)
    assert handle.workflow_id == f"{PREFIX}{PLAN_ID}"
    assert handle.journey == JOURNEY


@pytest.mark.asyncio
async def test_start_nao_sobrepoe_language_framework_do_plano():
    temporal_client = AsyncMock()
    capability = GenerateCapability(temporal_client=temporal_client, task_queue=TASK_QUEUE)

    request = GenerateRequest(
        plan_id=PLAN_ID,
        journey=JOURNEY,
        cognitive_plan={"parameters": {"language": "python", "framework": "django"}},
        target=GenerateTarget(language="python", framework="fastapi"),
    )

    await capability.start(request)

    input_data = temporal_client.start_workflow.call_args.args[1]
    params = input_data["cognitive_plan"]["parameters"]
    # setdefault não sobrepõe o que o plano já fixou
    assert params["framework"] == "django"
    assert params["language"] == "python"


@pytest.mark.asyncio
async def test_start_stack_desconhecida_falha_sem_iniciar():
    temporal_client = AsyncMock()
    capability = GenerateCapability(temporal_client=temporal_client, task_queue=TASK_QUEUE)

    with pytest.raises(UnsupportedStackError):
        await capability.start(_request(language="rust", framework="actix"))

    # FAILED sem iniciar o workflow (fail-closed)
    temporal_client.start_workflow.assert_not_called()


# =============================================================================
# map_result — função pura (fail-closed)
# =============================================================================


def _output_sucesso() -> dict:
    return {
        "status": "completed",
        "code_generation": {
            "artifact_id": "artifact-xyz",
            "language": "python",
            "framework": "fastapi",
            "lines_of_code": 120,
        },
        "build": {
            "pipeline_id": "pipe-1",
            "image_tag": "ghcr.io/nhm/app:abc123",
            "quality_score": 0.9,
            "test_pass_rate": 1.0,
        },
        "deployment": {
            "deployment_id": "dep-1",
            "namespace": "nhm-ephemeral-1",
            "service_url": "http://svc.local:8080",
            "status": "deployed",
            "verified": True,
        },
    }


def test_map_result_sucesso():
    result = GenerateCapability.map_result(_output_sucesso(), JOURNEY)

    assert isinstance(result, GenerateResult)
    assert result.status == "completed"
    assert result.journey == JOURNEY
    assert result.code_artifact_id == "artifact-xyz"
    assert result.container_image_ref == "ghcr.io/nhm/app:abc123"
    assert result.deployment is not None
    assert result.deployment.namespace == "nhm-ephemeral-1"
    assert result.deployment.service_url == "http://svc.local:8080"
    assert result.deployment.health == "healthy"


def test_map_result_status_nao_completed_falha():
    output = _output_sucesso()
    output["status"] = "failed"

    result = GenerateCapability.map_result(output, JOURNEY)

    assert result.status == "failed"
    assert result.journey == JOURNEY
    assert result.failure_reason
    assert "workflow não concluído" in result.failure_reason


def test_map_result_output_nao_dict_falha():
    result = GenerateCapability.map_result(None, JOURNEY)

    assert result.status == "failed"
    assert result.failure_reason


def test_map_result_sem_artifact_id_falha():
    output = _output_sucesso()
    output["code_generation"] = {"language": "python"}

    result = GenerateCapability.map_result(output, JOURNEY)

    assert result.status == "failed"
    assert "code_artifact_id" in result.failure_reason


def test_map_result_deployment_nao_deployed_falha():
    output = _output_sucesso()
    output["deployment"]["status"] = "rolling_back"

    result = GenerateCapability.map_result(output, JOURNEY)

    assert result.status == "failed"
    assert "deploy não concluído" in result.failure_reason


def test_map_result_deployed_mas_nao_verificado_falha():
    """Rollout pronto (deployed) mas healthcheck não confirmado (verified=False) → FAILED."""
    output = _output_sucesso()
    output["deployment"]["verified"] = False

    result = GenerateCapability.map_result(output, JOURNEY)

    assert result.status == "failed"
    assert "não verificado" in result.failure_reason


def test_map_result_deployed_sem_verified_falha():
    """Ausência do flag verified é tratada como não-verificado → FAILED (fail-closed)."""
    output = _output_sucesso()
    del output["deployment"]["verified"]

    result = GenerateCapability.map_result(output, JOURNEY)

    assert result.status == "failed"
    assert "não verificado" in result.failure_reason


# =============================================================================
# start — fidelidade ao caminho legado (estratégia, datetime, não-mutação)
# =============================================================================


@pytest.mark.asyncio
async def test_start_propaga_estrategia_completa():
    """A estratégia de stack inteira flui para parameters (multi-linguagem-ready)."""
    temporal_client = AsyncMock()
    capability = GenerateCapability(temporal_client=temporal_client, task_queue=TASK_QUEUE)

    await capability.start(_request())

    params = temporal_client.start_workflow.call_args.args[1]["cognitive_plan"]["parameters"]
    assert params["template_ref"] == "fastapi"
    assert params["builder"] == "kaniko"
    assert params["health_path"] == "/health"
    assert params["container_port"] == 8080


@pytest.mark.asyncio
async def test_start_normaliza_datetime_no_plano():
    """cognitive_plan com datetime → input_data JSON-safe (paridade com o consumer legado)."""
    temporal_client = AsyncMock()
    capability = GenerateCapability(temporal_client=temporal_client, task_queue=TASK_QUEUE)

    request = GenerateRequest(
        plan_id=PLAN_ID,
        journey=JOURNEY,
        cognitive_plan={"created_at": datetime(2026, 6, 26, 9, 0, 0), "parameters": {}},
        target=GenerateTarget(language="python", framework="fastapi"),
    )

    await capability.start(request)

    plan = temporal_client.start_workflow.call_args.args[1]["cognitive_plan"]
    # datetime convertido para string ISO (JSON-safe)
    assert plan["created_at"] == "2026-06-26T09:00:00"


@pytest.mark.asyncio
async def test_start_nao_muta_o_request():
    """start não muta o cognitive_plan do chamador (cópia, não referência)."""
    temporal_client = AsyncMock()
    capability = GenerateCapability(temporal_client=temporal_client, task_queue=TASK_QUEUE)

    request = _request()
    original_params = dict(request.cognitive_plan["parameters"])

    await capability.start(request)

    # O dict original do request permanece intacto.
    assert request.cognitive_plan["parameters"] == original_params
    assert "framework" not in request.cognitive_plan["parameters"]
