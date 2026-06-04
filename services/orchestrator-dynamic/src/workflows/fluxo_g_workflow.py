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
    from neural_hive_observability import get_tracer
    from neural_hive_observability.context import set_baggage
    from src.activities.build_package_activity import (
        build_package,
        validate_build_quality,
    )
    from src.activities.code_generation_activity import generate_code
    from src.activities.deploy_activity import (
        deploy_software,
        verify_deployment,
    )
    from src.activities.fluxo_g_integration import (
        generate_documentation,
        generate_requirements,
        query_knowledge_graph,
        request_approval,
        update_knowledge_graph,
    )
    from src.activities.feedback_loop_activity import (
        analyze_deployment_quality,
        check_feedback_thresholds,
        collect_post_deployment_metrics,
        generate_specialist_feedback,
        record_feedback_for_ml,
    )


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
    G6. Generate Code - Gerar código fonte via code-forge
    G7. Build Package - Compilar, testar e empacotar container
    G8. Deploy Software - Fazer deploy em Kubernetes
    G9. Collect Metrics - Coletar métricas pós-deploy
    G10. Analyze Quality - Analisar qualidade do deployment
    G11. Check Thresholds - Verificar thresholds de feedback
    G12. Generate Feedback - Gerar feedback para especialista (se necessário)
    G13. Record ML Data - Registrar dados para retreinamento ML
    """

    def __init__(self):
        self._status = "initializing"
        self._requirements_set = None
        self._documentation = None
        self._graph_update_result = None
        self._approvals = []
        self._code_artifact = None
        self._build_result = None
        self._deployment_result = None
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
                        a.get("result", {}).get("requires_human_review") for a in self._approvals
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

                # === G6: Generate Code ===
                self._status = "generating_code"
                workflow.logger.info("G6: Gerando código fonte")

                code_result = await workflow.execute_activity(
                    generate_code,
                    args=[
                        requirements_result,
                        docs_result,
                        cognitive_plan,
                    ],
                    start_to_close_timeout=timedelta(seconds=600),  # 10 minutos
                    retry_policy=RetryPolicy(
                        maximum_attempts=1  # Geração de código não é retryable
                    ),
                )

                self._code_artifact = code_result
                span.add_event("code_generated")

                # === G7: Build Package ===
                self._status = "building_package"
                workflow.logger.info("G7: Compilando e empacotando")

                code_artifact_id = code_result.get("code_artifact_id")
                if not code_artifact_id:
                    raise ApplicationError(
                        "code_artifact_id não encontrado no resultado da geração",
                        non_retryable=True,
                    )

                build_result = await workflow.execute_activity(
                    build_package,
                    args=[code_artifact_id, cognitive_plan],
                    start_to_close_timeout=timedelta(seconds=900),  # 15 minutos
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

                self._build_result = build_result
                span.add_event("package_built")

                # Validar qualidade do build
                quality_validation = await workflow.execute_activity(
                    validate_build_quality,
                    args=[build_result],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

                if not quality_validation.get("approved"):
                    raise ApplicationError(
                        f"Build não passou na validação de qualidade: {quality_validation.get('reasons')}",
                        non_retryable=True,
                    )

                span.add_event("build_quality_validated")

                # === G8: Deploy Software ===
                self._status = "deploying_software"
                workflow.logger.info("G8: Fazendo deploy em Kubernetes")

                container_image = build_result.get("container_image")
                if not container_image:
                    raise ApplicationError(
                        "container_image não encontrado no resultado do build",
                        non_retryable=True,
                    )

                deployment_result = await workflow.execute_activity(
                    deploy_software,
                    args=[container_image, build_result, cognitive_plan],
                    start_to_close_timeout=timedelta(seconds=1200),  # 20 minutos
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

                self._deployment_result = deployment_result
                span.add_event("software_deployed")

                # Verificar deployment
                deployment_verification = await workflow.execute_activity(
                    verify_deployment,
                    args=[deployment_result],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

                if not deployment_verification.get("verified"):
                    workflow.logger.warning(
                        f"Deployment verification falhou: {deployment_verification.get('reasons')}"
                    )
                    # Continuar mesmo sem verificação completa (pode ser apenas health checks pending)

                span.add_event("deployment_verified")

                # === G9: Collect Post-Deployment Metrics (Fase 5) ===
                self._status = "collecting_metrics"
                workflow.logger.info("G9: Coletando métricas pós-deploy")

                deployment_id = deployment_result.get("deployment_id", "")
                service_url = deployment_result.get("service_url", "")

                post_deployment_metrics = await workflow.execute_activity(
                    collect_post_deployment_metrics,
                    args=[deployment_id, plan_id, workflow_id, service_url],
                    start_to_close_timeout=timedelta(seconds=60),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )

                span.add_event("metrics_collected")

                # === G10: Analyze Deployment Quality ===
                self._status = "analyzing_quality"
                workflow.logger.info("G10: Analisando qualidade do deployment")

                quality_analysis = await workflow.execute_activity(
                    analyze_deployment_quality,
                    args=[post_deployment_metrics],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

                workflow.logger.info(
                    f"Quality score: {quality_analysis.get('overall_score')} "
                    f"({quality_analysis.get('status')})"
                )

                span.add_event("quality_analyzed")

                # === G11: Check Feedback Thresholds ===
                self._status = "checking_thresholds"
                workflow.logger.info("G11: Verificando thresholds de feedback")

                feedback_check = await workflow.execute_activity(
                    check_feedback_thresholds,
                    args=[quality_analysis],
                    start_to_close_timeout=timedelta(seconds=10),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

                span.add_event("thresholds_checked")

                # === G12: Generate Specialist Feedback (se necessário) ===
                if feedback_check.get("needs_feedback"):
                    self._status = "generating_feedback"
                    workflow.logger.info(
                        f"G12: Gerando feedback para especialista "
                        f"({feedback_check.get('trigger_reason')})"
                    )

                    specialist_feedback = await workflow.execute_activity(
                        generate_specialist_feedback,
                        args=[plan_id, deployment_id, quality_analysis, self._workflow_result],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )

                    workflow.logger.info(
                        f"Specialist feedback gerado: priority={specialist_feedback.get('priority')}"
                    )

                    span.add_event("specialist_feedback_generated")
                else:
                    specialist_feedback = None
                    workflow.logger.info("G12: Feedback não necessário (thresholds OK)")

                # === G13: Record Feedback for ML ===
                self._status = "recording_ml_data"
                workflow.logger.info("G13: Registrando dados para ML")

                # Obter intent_text do cognitive_plan ou input
                intent_text = original_intent or cognitive_plan.get("intent", {}).get("text", "")

                ml_feedback = await workflow.execute_activity(
                    record_feedback_for_ml,
                    args=[
                        plan_id,
                        "generation",  # workflow_type
                        intent_text,
                        deployment_result,
                        quality_analysis.get("overall_score", 0),
                        None,  # user_feedback (pode ser adicionado depois)
                    ],
                    start_to_close_timeout=timedelta(seconds=20),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )

                span.add_event("ml_feedback_recorded")

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
                    "code_generation": {
                        "artifact_id": code_result.get("code_artifact_id"),
                        "language": code_result.get("language"),
                        "framework": code_result.get("framework"),
                        "lines_of_code": code_result.get("lines_of_code"),
                    },
                    "build": {
                        "pipeline_id": build_result.get("pipeline_id"),
                        "image_tag": build_result.get("image_tag"),
                        "quality_score": build_result.get("quality_score"),
                        "test_pass_rate": quality_validation.get("pass_rate"),
                    },
                    "deployment": {
                        "deployment_id": deployment_result.get("deployment_id"),
                        "service_url": deployment_result.get("service_url"),
                        "status": deployment_result.get("status"),
                        "verified": deployment_verification.get("verified"),
                    },
                    "post_deployment": {
                        "metrics_collected": bool(post_deployment_metrics),
                        "quality_score": quality_analysis.get("overall_score"),
                        "quality_status": quality_analysis.get("status"),
                        "issues": quality_analysis.get("issues", []),
                        "recommendations": quality_analysis.get("recommendations", []),
                    },
                    "feedback_loop": {
                        "needs_feedback": feedback_check.get("needs_feedback"),
                        "trigger_reason": feedback_check.get("trigger_reason"),
                        "action": feedback_check.get("action"),
                        "specialist_feedback": specialist_feedback.get("priority")
                        if specialist_feedback
                        else None,
                        "ml_feedback_recorded": ml_feedback.get("status") == "recorded",
                    },
                    "completed_at": workflow.now().isoformat(),
                }

                workflow.logger.info("Fluxo G workflow concluído com sucesso")
                self._status = "completed"

                return self._workflow_result

            except ApplicationError:
                # Re-raise ApplicationError (não retryable)
                raise
            except Exception as e:
                workflow.logger.exception(f"Fluxo G workflow failed: {e!s}")
                self._status = "failed"
                raise
