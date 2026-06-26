"""
GenerateCapability — adaptador fino capacidade GENERATE → FluxoGWorkflow.

Spec: docs/specs/2026-06-26-extrair-capacidade-generate — Scope 2 (Capability).

A capacidade é a **fronteira de contrato** da geração: recebe um
`GenerateRequest`, resolve a estratégia de stack (`StackRegistry`) e **inicia**
o `FluxoGWorkflow` no Temporal (start durável — não bloqueia à espera do
resultado). O mapeamento `output do workflow → GenerateResult` é uma **função
pura** (`map_result`).

NOTA de runtime (honestidade — auditoria Task 5, CR-001): hoje `map_result`
define o **contrato de saída** e é alvo dos testes de bloco, mas ainda **não tem
chamador de produção** — o resultado do FluxoGWorkflow é consumido via
signals/ExecutionResultConsumer (cadência durável do Temporal). Logo o
fail-closed do *output* aqui descrito é garantido pela função isolada, não
imposto em runtime; a prova anti-verde-falso E2E da Fase 4 vem da observação
directa do software a correr (curl `/health` 200), não de `map_result`. O wiring
de `map_result` ao consumo de resultado fica para evolução futura da fronteira.

Princípios:
- Não reimplementa G1–G8 (o FluxoGWorkflow continua a ser a implementação).
- Fail-closed: stack desconhecida levanta `UnsupportedStackError` e o workflow
  **não** é iniciado; qualquer G-step falhado / output incompleto → `failed`.
- Retrocompatível: enriquece `parameters` com `language`/`framework` via
  `setdefault` (não sobrepõe o que o plano já fixou).
"""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from src.capabilities.generate.contract import (
    DeploymentInfo,
    GenerateRequest,
    GenerateResult,
)
from src.capabilities.generate.stacks import StackRegistry, default_stack_registry
from src.workflows.fluxo_g_workflow import FluxoGWorkflow


def _json_safe(obj: dict) -> dict:
    """
    Normaliza datetimes recursivamente (JSON-safe) — paridade com o consumer legado.

    Planos diretos do STE contêm `datetime`, que o data-converter default do
    Temporal não serializa. O `decision_consumer` faz a mesma normalização antes
    do `start_workflow`; replicamo-la aqui para equivalência comportamental.
    """

    def _convert(o: object) -> str:
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Type {type(o)} not serializable")

    return json.loads(json.dumps(obj, default=_convert))


class GenerateHandle(BaseModel):
    """Referência durável a uma geração iniciada (start não-bloqueante)."""

    workflow_id: str
    journey: str


class GenerateCapability:
    """
    Capacidade GENERATE: inicia o FluxoGWorkflow e traduz o seu resultado.

    O cliente Temporal é injetado (testável sem Temporal real). A capacidade
    mantém-se um adaptador fino: `start` (start durável) + `map_result`
    (tradução pura de contrato).
    """

    def __init__(
        self,
        temporal_client,
        task_queue: str,
        workflow_id_prefix: str = "fluxo-g-",
        registry: StackRegistry | None = None,
    ) -> None:
        self._temporal_client = temporal_client
        self._task_queue = task_queue
        self._workflow_id_prefix = workflow_id_prefix
        self._registry = registry or default_stack_registry()

    async def start(
        self, request: GenerateRequest, workflow_id: str | None = None
    ) -> GenerateHandle:
        """
        Resolve a estratégia e **inicia** o FluxoGWorkflow (start durável).

        Stack desconhecida → `UnsupportedStackError` propaga e o workflow NÃO é
        iniciado (FAILED sem iniciar — anti-verde-falso). Não espera o resultado.

        `workflow_id` opcional (retrocompatível): quando fornecido, preserva um id
        já estabelecido (ex: resume pós-aprovação usa `flow-c-{correlation_id}`);
        na ausência usa-se o id por plano `{prefix}{plan_id}` (comportamento legado).
        """
        # 1. Resolve a estratégia (fail-closed: desconhecida → erro antes de iniciar)
        strategy = self._registry.resolve(request.target.language, request.target.framework)

        # 2. Enriquece o cognitive_plan com a estratégia de stack (setdefault: não
        #    sobrepõe o que o plano já fixou). Propaga a estratégia COMPLETA para a
        #    fronteira ficar multi-linguagem-ready: registar uma stack nova passa a
        #    governar template/builder/health-path/porta a jusante, não só a seleção.
        plan = {**request.cognitive_plan}
        params = {**(plan.get("parameters") or {})}
        params.setdefault("language", strategy.language)
        params.setdefault("framework", strategy.framework)
        params.setdefault("template_ref", strategy.template_ref)
        params.setdefault("builder", strategy.builder)
        params.setdefault("health_path", strategy.health_path)
        params.setdefault("container_port", strategy.container_port)
        plan["parameters"] = params

        # Normaliza datetimes (JSON-safe) tal como o consumer legado faz antes do
        # start_workflow — evita divergência de serialização para planos do STE.
        input_data = {
            "consolidated_decision": None,
            "cognitive_plan": _json_safe(plan),
            "is_direct_plan": True,
        }

        # 3. id por plano (ou id preservado, se fornecido pelo chamador)
        wid = workflow_id or f"{self._workflow_id_prefix}{request.plan_id}"

        # 4. Start durável (não bloqueia à espera do resultado)
        await self._temporal_client.start_workflow(
            FluxoGWorkflow.run,
            input_data,
            id=wid,
            task_queue=self._task_queue,
        )

        # 5. Handle durável
        return GenerateHandle(workflow_id=wid, journey=request.journey)

    @staticmethod
    def map_result(workflow_output: dict, journey: str) -> GenerateResult:
        """
        Traduz o output do FluxoGWorkflow → GenerateResult (função pura, fail-closed).

        - output não-dict / `status != "completed"` → failed;
        - sem `code_generation.artifact_id` → failed;
        - `deployment.status != "deployed"` → failed;
        - `deployment.verified != True` (healthcheck não confirmado) → failed;
        - caso contrário → completed (com artifact/image/deployment).
        """
        if not isinstance(workflow_output, dict):
            return GenerateResult.failed(
                journey, "workflow não concluído: status=<output inválido>"
            )

        status = workflow_output.get("status")
        if status != "completed":
            return GenerateResult.failed(journey, f"workflow não concluído: status={status}")

        artifact_id = (workflow_output.get("code_generation") or {}).get("artifact_id")
        if not artifact_id or not str(artifact_id).strip():
            return GenerateResult.failed(journey, "geração sem code_artifact_id")

        dep = workflow_output.get("deployment") or {}
        dep_status = dep.get("status")
        if dep_status != "deployed":
            return GenerateResult.failed(journey, f"deploy não concluído: status={dep_status}")

        # verify_deployment (healthcheck) é um G-step do contrato fail-closed: um
        # rollout pronto (status=deployed) mas com healthcheck não confirmado
        # (verified != True) NÃO é sucesso. A capacidade (fronteira) é mais estrita
        # que o FluxoGWorkflow, que é leniente e continua sem verificação completa.
        if dep.get("verified") is not True:
            return GenerateResult.failed(
                journey, "deploy não verificado: healthcheck não confirmado"
            )

        return GenerateResult.completed(
            journey,
            code_artifact_id=artifact_id,
            container_image_ref=(workflow_output.get("build") or {}).get("image_tag"),
            deployment=DeploymentInfo(
                namespace=dep.get("namespace"),
                service_url=dep.get("service_url"),
                health="healthy",
            ),
        )
