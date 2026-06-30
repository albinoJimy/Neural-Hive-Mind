"""
Contrato da capacidade GENERATE (fronteira in/out explícita).

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 1.

Este módulo define o contrato lógico `GenerateRequest → GenerateResult` da
capacidade GENERATE. É **stack-neutro** (sem enum fechado a fastapi): o
`target{language, framework}` é livre e a seleção de template/builder vive no
registry (`stacks.py`). Sem lógica de orquestração — apenas modelos Pydantic v2.

Princípio anti-verde-falso (FAIL-CLOSED): um `GenerateResult` não pode
reivindicar `completed` sem um `code_artifact_id` (não há sucesso sem
artefacto), nem `failed` sem um `failure_reason`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GenerateTarget(BaseModel):
    """Stack-alvo da geração (neutra: qualquer linguagem/framework)."""

    language: str
    framework: str
    options: dict = Field(default_factory=dict)

    @field_validator("language", "framework")
    @classmethod
    def _nao_vazio(cls, value: str) -> str:
        """Garante que language/framework não são vazios; normaliza (strip)."""
        if not value or not value.strip():
            raise ValueError("language e framework não podem ser vazios")
        return value.strip()


class GenerateRequest(BaseModel):
    """Entrada da capacidade GENERATE."""

    plan_id: str
    journey: str
    cognitive_plan: dict
    target: GenerateTarget


class DeploymentInfo(BaseModel):
    """Informação de deployment resultante de uma geração bem-sucedida."""

    namespace: str | None = None
    service_url: str | None = None
    health: str | None = None


class GenerateResult(BaseModel):
    """
    Saída da capacidade GENERATE (fail-closed).

    Invariantes (anti-verde-falso):
    - status == "failed"  ⇒ failure_reason presente e não-vazio.
    - status == "completed" ⇒ code_artifact_id presente e não-vazio (não se
      reivindica sucesso sem artefacto; um id só com espaços é tão "sem
      artefacto" como ausente), e SEM failure_reason (estado contraditório).
    """

    status: Literal["completed", "failed"]
    journey: str
    code_artifact_id: str | None = None
    container_image_ref: str | None = None
    deployment: DeploymentInfo | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _validar_fail_closed(self) -> GenerateResult:
        """Aplica os invariantes fail-closed do contrato."""
        if self.status == "failed" and (not self.failure_reason or not self.failure_reason.strip()):
            raise ValueError("status='failed' exige failure_reason não-vazio")
        if self.status == "completed":
            if not self.code_artifact_id or not self.code_artifact_id.strip():
                raise ValueError(
                    "status='completed' exige code_artifact_id não-vazio "
                    "(não se reivindica sucesso sem artefacto)"
                )
            if self.failure_reason and self.failure_reason.strip():
                raise ValueError(
                    "status='completed' não pode ter failure_reason (estado contraditório)"
                )
        return self

    @classmethod
    def failed(cls, journey: str, reason: str) -> GenerateResult:
        """Construtor-helper para um resultado falhado."""
        return cls(status="failed", journey=journey, failure_reason=reason)

    @classmethod
    def completed(
        cls,
        journey: str,
        code_artifact_id: str,
        container_image_ref: str | None = None,
        deployment: DeploymentInfo | None = None,
    ) -> GenerateResult:
        """Construtor-helper para um resultado concluído com sucesso."""
        return cls(
            status="completed",
            journey=journey,
            code_artifact_id=code_artifact_id,
            container_image_ref=container_image_ref,
            deployment=deployment,
        )
