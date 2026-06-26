"""
Testes unitários do contrato da capacidade GENERATE (Task 1 / Fase 0).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 1 (Contrato).

Provam que o contrato in/out (GenerateRequest → GenerateResult) é:
- explícito e validado (campos obrigatórios, target stack-neutro);
- FAIL-CLOSED (anti-verde-falso): não se pode reivindicar "completed" sem
  artefacto, nem "failed" sem razão.
Sem lógica de orquestração — apenas modelos Pydantic v2.
"""

import pytest
from pydantic import ValidationError
from src.capabilities.generate.contract import (
    DeploymentInfo,
    GenerateRequest,
    GenerateResult,
    GenerateTarget,
)

# =============================================================================
# GenerateTarget — stack-neutro
# =============================================================================


def test_generate_target_valido():
    target = GenerateTarget(language="python", framework="fastapi")
    assert target.language == "python"
    assert target.framework == "fastapi"
    assert target.options == {}


def test_generate_target_aceita_options():
    target = GenerateTarget(language="python", framework="fastapi", options={"k": "v"})
    assert target.options == {"k": "v"}


def test_generate_target_language_vazio_falha():
    with pytest.raises(ValidationError):
        GenerateTarget(language="", framework="fastapi")


def test_generate_target_framework_vazio_falha():
    with pytest.raises(ValidationError):
        GenerateTarget(language="python", framework="   ")


def test_generate_target_normaliza_strip():
    """language/framework são normalizados (strip) — valor canónico guardado."""
    target = GenerateTarget(language="  python  ", framework="  fastapi  ")
    assert target.language == "python"
    assert target.framework == "fastapi"


# =============================================================================
# GenerateRequest — campos obrigatórios
# =============================================================================


def test_generate_request_valido():
    req = GenerateRequest(
        plan_id="plan-1",
        journey="J3_BUILD",
        cognitive_plan={"steps": []},
        target=GenerateTarget(language="python", framework="fastapi"),
    )
    assert req.plan_id == "plan-1"
    assert req.journey == "J3_BUILD"
    assert req.target.framework == "fastapi"


def test_generate_request_sem_target_falha():
    with pytest.raises(ValidationError):
        GenerateRequest(
            plan_id="plan-1",
            journey="J3_BUILD",
            cognitive_plan={},
        )


# =============================================================================
# GenerateResult — FAIL-CLOSED (anti-verde-falso)
# =============================================================================


def test_generate_result_failed_sem_failure_reason_falha():
    with pytest.raises(ValidationError):
        GenerateResult(status="failed", journey="J3_BUILD")


def test_generate_result_failed_failure_reason_vazio_falha():
    with pytest.raises(ValidationError):
        GenerateResult(status="failed", journey="J3_BUILD", failure_reason="  ")


def test_generate_result_completed_sem_code_artifact_id_falha():
    with pytest.raises(ValidationError):
        GenerateResult(status="completed", journey="J3_BUILD")


def test_generate_result_completed_code_artifact_id_so_espacos_falha():
    """code_artifact_id só com espaços é tão 'sem artefacto' como ausente → FAIL."""
    with pytest.raises(ValidationError):
        GenerateResult(status="completed", journey="J3_BUILD", code_artifact_id="   ")


def test_generate_result_completed_com_failure_reason_falha():
    """status='completed' com failure_reason é estado contraditório → FAIL."""
    with pytest.raises(ValidationError):
        GenerateResult(
            status="completed",
            journey="J3_BUILD",
            code_artifact_id="artifact-123",
            failure_reason="isto não devia existir",
        )


def test_generate_result_completed_valido():
    res = GenerateResult(
        status="completed",
        journey="J3_BUILD",
        code_artifact_id="artifact-123",
    )
    assert res.status == "completed"
    assert res.code_artifact_id == "artifact-123"


def test_generate_result_failed_valido():
    res = GenerateResult(
        status="failed",
        journey="J3_BUILD",
        failure_reason="stack não suportada",
    )
    assert res.status == "failed"
    assert res.failure_reason == "stack não suportada"


# =============================================================================
# Construtores-helper
# =============================================================================


def test_helper_failed_produz_objeto_correto():
    res = GenerateResult.failed(journey="J3_BUILD", reason="stack não suportada")
    assert res.status == "failed"
    assert res.journey == "J3_BUILD"
    assert res.failure_reason == "stack não suportada"
    assert res.code_artifact_id is None


def test_helper_completed_produz_objeto_correto():
    deployment = DeploymentInfo(namespace="ns-1", service_url="http://svc", health="/health")
    res = GenerateResult.completed(
        journey="J3_BUILD",
        code_artifact_id="artifact-123",
        container_image_ref="ghcr.io/x:tag",
        deployment=deployment,
    )
    assert res.status == "completed"
    assert res.journey == "J3_BUILD"
    assert res.code_artifact_id == "artifact-123"
    assert res.container_image_ref == "ghcr.io/x:tag"
    assert res.deployment is not None
    assert res.deployment.namespace == "ns-1"
    assert res.failure_reason is None
