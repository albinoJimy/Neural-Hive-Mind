"""
Testes de extensibilidade multi-linguagem da capacidade GENERATE (Task 4 / Fase 3).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 4 (extensibilidade).

Provam a PROPRIEDADE já existente: registar uma `GenerationStrategy` nova atrás
da fronteira do `StackRegistry` é suficiente para suportar uma stack nova —
SEM alterar o contrato (`GenerateRequest`/`GenerateResult`/`GenerateTarget`) nem
o routing. Uma stack "fake" (elixir/phoenix) registada APENAS aqui:

1. é selecionada pela capacidade via `target` e percorre o MESMO caminho de
   contrato (workflow Temporal mockado), propagando os valores da estratégia
   FAKE (provando que não há valores FastAPI hardcoded);
2. usa exatamente os MESMOS modelos de contrato (sem subclasses/flags novas);
   `map_result` é stack-agnóstico;
3. (anti-verde-falso) stack desconhecida → `UnsupportedStackError` sem iniciar
   o workflow — NUNCA cai silenciosamente para FastAPI.
"""

from unittest.mock import AsyncMock

import pytest
from src.capabilities.generate.capability import GenerateCapability, GenerateHandle
from src.capabilities.generate.contract import (
    GenerateRequest,
    GenerateResult,
    GenerateTarget,
)
from src.capabilities.generate.stacks import (
    GenerationStrategy,
    StackRegistry,
    UnsupportedStackError,
    default_stack_registry,
)
from src.workflows.fluxo_g_workflow import FluxoGWorkflow

PLAN_ID = "plan-fake-999"
JOURNEY = "J3_BUILD"
TASK_QUEUE = "fluxo-g-queue"
PREFIX = "fluxo-g-"

# Stack FAKE com valores DISTINTOS de FastAPI — registada SÓ neste teste.
FAKE_LANGUAGE = "elixir"
FAKE_FRAMEWORK = "phoenix"
FAKE_TEMPLATE_REF = "phoenix"
FAKE_BUILDER = "buildpacks"
FAKE_HEALTH_PATH = "/healthz"
FAKE_CONTAINER_PORT = 4000


def _fake_strategy() -> GenerationStrategy:
    return GenerationStrategy(
        language=FAKE_LANGUAGE,
        framework=FAKE_FRAMEWORK,
        template_ref=FAKE_TEMPLATE_REF,
        builder=FAKE_BUILDER,
        health_path=FAKE_HEALTH_PATH,
        container_port=FAKE_CONTAINER_PORT,
    )


def _registry_so_fake() -> StackRegistry:
    """Registry FRESCO com SÓ a estratégia fake (sem FastAPI)."""
    registry = StackRegistry()
    registry.register(_fake_strategy())
    return registry


def _request_fake() -> GenerateRequest:
    return GenerateRequest(
        plan_id=PLAN_ID,
        journey=JOURNEY,
        cognitive_plan={"plan_id": PLAN_ID, "parameters": {"existing": "keep"}},
        target=GenerateTarget(language=FAKE_LANGUAGE, framework=FAKE_FRAMEWORK),
    )


# =============================================================================
# 1. fake registada → selecionada via target (sem valores FastAPI hardcoded)
# =============================================================================


@pytest.mark.asyncio
async def test_fake_registada_selecionada_via_target():
    """Registry SÓ-fake → start seleciona a estratégia fake e propaga os SEUS valores."""
    temporal_client = AsyncMock()
    capability = GenerateCapability(
        temporal_client=temporal_client,
        task_queue=TASK_QUEUE,
        workflow_id_prefix=PREFIX,
        registry=_registry_so_fake(),
    )

    handle = await capability.start(_request_fake())

    # Workflow iniciado exatamente uma vez, no MESMO caminho de contrato.
    temporal_client.start_workflow.assert_called_once()
    call = temporal_client.start_workflow.call_args
    assert call.args[0] is FluxoGWorkflow.run
    assert call.kwargs["id"] == f"{PREFIX}{PLAN_ID}"
    assert call.kwargs["task_queue"] == TASK_QUEUE

    # Os parameters refletem a estratégia FAKE (não há FastAPI hardcoded).
    params = call.args[1]["cognitive_plan"]["parameters"]
    assert params["language"] == FAKE_LANGUAGE
    assert params["framework"] == FAKE_FRAMEWORK
    assert params["template_ref"] == FAKE_TEMPLATE_REF
    assert params["builder"] == FAKE_BUILDER
    assert params["health_path"] == FAKE_HEALTH_PATH
    assert params["container_port"] == FAKE_CONTAINER_PORT

    # Nenhum valor FastAPI escapou para a stack fake.
    assert params["framework"] != "fastapi"
    assert params["health_path"] != "/health"
    assert params["container_port"] != 8080

    # Não sobrepõe o que o plano já tinha.
    assert params["existing"] == "keep"

    # Handle durável devolvido.
    assert isinstance(handle, GenerateHandle)
    assert handle.workflow_id == f"{PREFIX}{PLAN_ID}"
    assert handle.journey == JOURNEY


# =============================================================================
# 2. contrato inalterado — mesmos modelos servem a stack não-FastAPI
# =============================================================================


def _output_sucesso_fake() -> dict:
    """Output de workflow da stack fake (completed/deployed/verified)."""
    return {
        "status": "completed",
        "code_generation": {
            "artifact_id": "artifact-elixir-1",
            "language": FAKE_LANGUAGE,
            "framework": FAKE_FRAMEWORK,
            "lines_of_code": 200,
        },
        "build": {
            "pipeline_id": "pipe-elixir-1",
            "image_tag": "ghcr.io/nhm/phoenix-app:def456",
            "quality_score": 0.95,
            "test_pass_rate": 1.0,
        },
        "deployment": {
            "deployment_id": "dep-elixir-1",
            "namespace": "nhm-ephemeral-fake",
            "service_url": "http://phoenix.local:4000",
            "status": "deployed",
            "verified": True,
        },
    }


def test_contrato_inalterado_map_result_stack_agnostico():
    """map_result de output da stack fake → MESMO GenerateResult.completed (stack-agnóstico)."""
    result = GenerateCapability.map_result(_output_sucesso_fake(), JOURNEY)

    # A class do contrato é EXATAMENTE a mesma importada (sem subclasses/flags novas).
    assert type(result) is GenerateResult
    assert result.status == "completed"
    assert result.journey == JOURNEY
    assert result.code_artifact_id == "artifact-elixir-1"
    assert result.container_image_ref == "ghcr.io/nhm/phoenix-app:def456"
    assert result.deployment is not None
    assert result.deployment.namespace == "nhm-ephemeral-fake"
    assert result.deployment.service_url == "http://phoenix.local:4000"
    assert result.deployment.health == "healthy"


def test_contrato_inalterado_request_aceita_stack_nao_fastapi():
    """O MESMO GenerateRequest/GenerateTarget serve a stack não-FastAPI sem alteração."""
    request = _request_fake()

    # Tipos do contrato inalterados (sem subclasses por stack).
    assert type(request) is GenerateRequest
    assert type(request.target) is GenerateTarget
    assert request.target.language == FAKE_LANGUAGE
    assert request.target.framework == FAKE_FRAMEWORK


# =============================================================================
# 3. ausência/remoção da stack → FAILED sem fallback FastAPI (anti-verde-falso)
# =============================================================================


@pytest.mark.asyncio
async def test_registry_vazio_stack_fake_falha_sem_iniciar():
    """Registry FRESCO sem a fake e sem FastAPI → UnsupportedStackError sem iniciar."""
    temporal_client = AsyncMock()
    capability = GenerateCapability(
        temporal_client=temporal_client,
        task_queue=TASK_QUEUE,
        registry=StackRegistry(),  # vazio: nem fake nem FastAPI
    )

    with pytest.raises(UnsupportedStackError):
        await capability.start(_request_fake())

    # Anti-verde-falso: NÃO cai em FastAPI — o workflow não chega a iniciar.
    temporal_client.start_workflow.assert_not_called()


@pytest.mark.asyncio
async def test_registar_fake_nao_reintroduz_fastapi():
    """Registry SÓ-fake ao resolver python/fastapi → UnsupportedStackError (sem magia)."""
    temporal_client = AsyncMock()
    capability = GenerateCapability(
        temporal_client=temporal_client,
        task_queue=TASK_QUEUE,
        registry=_registry_so_fake(),
    )

    request = GenerateRequest(
        plan_id=PLAN_ID,
        journey=JOURNEY,
        cognitive_plan={"parameters": {}},
        target=GenerateTarget(language="python", framework="fastapi"),
    )

    # Registar a fake NÃO re-introduz FastAPI por magia.
    with pytest.raises(UnsupportedStackError):
        await capability.start(request)

    temporal_client.start_workflow.assert_not_called()


# =============================================================================
# 4. (reforço) caminho de contrato idêntico: start(fake) → map_result(output_fake)
# =============================================================================


@pytest.mark.asyncio
async def test_caminho_de_contrato_identico_fake():
    """start(fake) + map_result(output_fake) produz o MESMO tipo de fronteira que FastAPI."""
    temporal_client = AsyncMock()
    capability = GenerateCapability(
        temporal_client=temporal_client,
        task_queue=TASK_QUEUE,
        registry=_registry_so_fake(),
    )

    handle = await capability.start(_request_fake())
    assert isinstance(handle, GenerateHandle)

    # A mesma função pura map_result fecha o ciclo de contrato para a stack fake.
    result = GenerateCapability.map_result(_output_sucesso_fake(), handle.journey)
    assert type(result) is GenerateResult
    assert result.status == "completed"
    assert result.journey == JOURNEY


# =============================================================================
# 5. (anti-verde-falso) map_result stack-agnóstico TAMBÉM no caminho FALHADO:
#    a stack fake NÃO recebe leniência especial — output incompleto → FAILED.
# =============================================================================


def _output_falhado_fake() -> dict:
    """Output da stack fake com deploy NÃO verificado (healthcheck não confirmado)."""
    return {
        "status": "completed",
        "code_generation": {
            "artifact_id": "artifact-elixir-2",
            "language": FAKE_LANGUAGE,
            "framework": FAKE_FRAMEWORK,
        },
        "build": {"image_tag": "ghcr.io/nhm/phoenix-app:bad"},
        "deployment": {
            "deployment_id": "dep-elixir-2",
            "namespace": "nhm-ephemeral-fake",
            "service_url": "http://phoenix.local:4000",
            "status": "deployed",
            "verified": False,  # healthcheck não confirmado → fail-closed
        },
    }


def test_map_result_stack_agnostico_falha_fake_sem_lenidade():
    """Output FALHADO da stack fake → MESMO GenerateResult.failed (sem caso especial por stack)."""
    result = GenerateCapability.map_result(_output_falhado_fake(), JOURNEY)

    # O contrato de saída é EXATAMENTE o mesmo modelo, no estado failed.
    assert type(result) is GenerateResult
    assert result.status == "failed"
    assert result.journey == JOURNEY
    # Fail-closed: failure_reason presente e sem reivindicar artefacto/deploy.
    assert result.failure_reason
    assert result.failure_reason.strip()
    assert result.code_artifact_id is None
    assert result.container_image_ref is None
    assert result.deployment is None


# =============================================================================
# 6. registar a fake NÃO contamina o default_stack_registry (isolamento):
#    o default continua a conhecer SÓ python/fastapi e NÃO a fake.
# =============================================================================


def test_registar_fake_nao_contamina_default_registry():
    """Registar a fake num registry à parte deixa o default_stack_registry intacto."""
    # Regista a fake APENAS num registry local fresco.
    local = default_stack_registry()
    local.register(_fake_strategy())
    assert local.is_registered(FAKE_LANGUAGE, FAKE_FRAMEWORK)

    # Um default RECÉM-construído continua a NÃO conhecer a fake (sem estado global).
    fresh_default = default_stack_registry()
    assert fresh_default.is_registered("python", "fastapi") is True
    assert fresh_default.is_registered(FAKE_LANGUAGE, FAKE_FRAMEWORK) is False
    with pytest.raises(UnsupportedStackError):
        fresh_default.resolve(FAKE_LANGUAGE, FAKE_FRAMEWORK)

    # E a estratégia default mantém os valores FastAPI provados (não mutados).
    fastapi = fresh_default.resolve("python", "fastapi")
    assert fastapi.framework == "fastapi"
    assert fastapi.health_path == "/health"
    assert fastapi.container_port == 8080
