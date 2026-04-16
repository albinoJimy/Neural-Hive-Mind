"""
Workflow Temporal para Fluxo G (Idea → Software).

Este workflow estende o OrchestrationWorkflow padrão com as etapas
do Fluxo G: Requirements Engineering, Documentation Generation,
Knowledge Graph integration e Approvals.
"""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

# Import activities
with workflow.unsafe.imports_passed_through():
    from opentelemetry import trace

    from neural_hive_observability import get_tracer
    from neural_hive_observability.context import set_baggage
    from src.activities.fluxo_g_integration import (
        generate_requirements,
        generate_documentation,
        update_knowledge_graph,
        request_approval,
        query_knowledge_graph,
    )
    from src.activities.plan_validation import validate_cognitive_plan
    from src.activities.result_consolidation import consolidate_results
    from src.config.settings import get_settings


@workflow.defn
class FluxoGWorkflow:
    """
    Workflow para Fluxo G (Idea → Software).

    Etapas:
    G1. Requirements Engineering - Gerar requisitos e user stories
    G2. Documentation Generation - Gerar README, diagramas, docs técnicas
    G3. Knowledge Graph - Indexar artefatos no grafo de conhecimento
    G4. Approvals - Solicitar aprovações quando necessário
    G5. Query RAG - Usar conhecimento acumulado para enriquecer respostas
    """

    def __init__(self):
        self._status = "initializing"
        self._requirements_set = None
        self._documentation = None
        self._graph_update_result = None
        self._approvals = []
        self._workflow_result = {}

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Executa o workflow Fluxo G.

        Args:
            input_data: Dicionário contendo:
                - cognitive_plan: Plano cognitivo
                - original_intent: Intent original (opcional)
                - consolidated_decision: Decisão consolidada (opcional)
                - skip_approvals: Pular aprovações (default: False)

        Returns:
            Dicionário com resultado completo incluindo requisitos, docs e aprovações
        """
        cognitive_plan = input_data.get("cognitive_plan", {})
        original_intent = input_data.get("original_intent")
        consolidated_decision = input_data.get("consolidated_decision")
        skip_approvals = input_data.get("skip_approvals", False)

        workflow_id = workflow.info().workflow_id
        plan_id = cognitive_plan.get("plan_id", "unknown")
        intent_id = cognitive_plan.get("intent_id", "")

        if plan_id:
            set_baggage("plan_id", plan_id)
        if intent_id:
            set_baggage("intent_id", intent_id)

        tracer = get_tracer()
        workflow.logger.info(
            f"Iniciando Fluxo G workflow: workflow_id={workflow_id}, plan_id={plan_id}"
        )

        with tracer.start_as_current_span(
            "fluxo_g_workflow.run",
            attributes={
                "neural.hive.workflow.id": workflow_id,
                "neural.hive.plan.id": plan_id,
                "neural.hive.workflow.type": "fluxo_g",
            },
        ) as span:
            try:
                # === G1: Requirements Engineering ===
                self._status = "generating_requirements"
                workflow.logger.info("G1: Gerando requisitos")

                requirements_result = await workflow.execute_activity(
                    generate_requirements,
                    args=[cognitive_plan, original_intent],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2, initial_interval=timedelta(seconds=1)
                    ),
                )

                self._requirements_set = requirements_result
                span.add_event("requirements_generated")

                # === G2: Documentation Generation ===
                self._status = "generating_documentation"
                workflow.logger.info("G2: Gerando documentação")

                docs_result = await workflow.execute_activity(
                    generate_documentation,
                    args=[cognitive_plan, requirements_result, None],
                    start_to_close_timeout=timedelta(seconds=120),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2, initial_interval=timedelta(seconds=2)
                    ),
                )

                self._documentation = docs_result
                span.add_event("documentation_generated")

                # === G3: Knowledge Graph Update ===
                self._status = "updating_knowledge_graph"
                workflow.logger.info("G3: Atualizando grafo de conhecimento")

                graph_result = await workflow.execute_activity(
                    update_knowledge_graph,
                    args=[cognitive_plan, requirements_result, docs_result],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=1),  # Não é crítico
                )

                self._graph_update_result = graph_result
                span.add_event("knowledge_graph_updated")

                # === G4: Approvals (se não skip) ===
                if not skip_approvals:
                    self._status = "requesting_approvals"
                    workflow.logger.info("G4: Solicitando aprovações")

                    # Solicitar aprovação para requisitos
                    req_approval = await workflow.execute_activity(
                        request_approval,
                        args=[
                            "requirement",
                            {
                                "title": f"Requisitos - {plan_id}",
                                "description": f"Requisitos gerados para plano {plan_id}",
                                "context": {
                                    "requirements_count": len(
                                        requirements_result.get("requirements", [])
                                    ),
                                    "plan_id": plan_id,
                                },
                            },
                            "fluxo-g-workflow",
                        ],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )

                    self._approvals.append({"type": "requirement", "result": req_approval})

                    # Solicitar aprovação para documentação
                    docs_approval = await workflow.execute_activity(
                        request_approval,
                        args=[
                            "documentation",
                            {
                                "title": f"Documentação - {plan_id}",
                                "description": f"Documentação gerada para plano {plan_id}",
                                "context": {
                                    "documentation_id": docs_result.get("documentation_id"),
                                    "plan_id": plan_id,
                                },
                            },
                            "fluxo-g-workflow",
                        ],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )

                    self._approvals.append({"type": "documentation", "result": docs_approval})

                    # Verificar se alguma aprovação requer intervenção humana
                    human_review_required = any(
                        a.get("result", {}).get("requires_human_review")
                        for a in self._approvals
                    )

                    if human_review_required:
                        workflow.logger.warning(
                            "Fluxo G requer revisão humana - aguardando aprovação"
                        )
                        span.add_event("human_review_required")

                        # TODO: Implementar mecanismo de espera por aprovação humana
                        # Por ora, continuar com warning

                    span.add_event("approvals_processed")

                # === G5: Query RAG (opcional - enriquecer resultado) ===
                self._status = "enriching_with_rag"
                workflow.logger.info("G5: Enriquecendo com RAG")

                # Exemplo: buscar contexto similar no grafo
                rag_query = f"Planos similares a {plan_id}"
                rag_result = await workflow.execute_activity(
                    query_knowledge_graph,
                    args=[rag_query, f"Contexto do plano {plan_id}", 5],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

                span.add_event("rag_enrichment_complete")

                # === Consolidar Resultado ===
                self._status = "consolidating"
                self._workflow_result = {
                    "workflow_id": workflow_id,
                    "plan_id": plan_id,
                    "status": "completed",
                    "requirements": {
                        "set_id": requirements_result.get("requirements_set_id"),
                        "count": len(requirements_result.get("requirements", [])),
                    },
                    "documentation": {
                        "doc_id": docs_result.get("documentation_id"),
                        "readme_generated": bool(docs_result.get("readme")),
                    },
                    "knowledge_graph": {
                        "nodes_created": graph_result.get("nodes_created", 0),
                        "relations_created": graph_result.get("relations_created", 0),
                    },
                    "approvals": self._approvals if not skip_approvals else "skipped",
                    "rag_enrichment": rag_result.get("response", "") if rag_result else None,
                    "completed_at": workflow.now().isoformat(),
                }

                workflow.logger.info("Fluxo G workflow concluído com sucesso")
                self._status = "completed"

                return self._workflow_result

            except ApplicationError:
                # Re-raise ApplicationError (não retryable)
                raise
            except Exception as e:
                workflow.logger.exception(f"Fluxo G workflow failed: {str(e)}")
                self._status = "failed"
                raise
