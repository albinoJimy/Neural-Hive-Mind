"""
Workflow Temporal principal para orquestração de execução (Fluxo C).
Implementa as etapas C1-C6 conforme documento-06.
"""

import contextlib
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

# Import activities (serão definidos posteriormente)
with workflow.unsafe.imports_passed_through():
    from opentelemetry import trace

    from neural_hive_observability import get_tracer
    from neural_hive_observability.context import set_baggage
    from src.activities.compensation import (
        build_compensation_order,
        compensate_ticket,
        update_ticket_compensation_status,
    )
    from src.activities.optimization_event import (
        publish_ticket_completed_event,
        publish_workflow_optimization_events,
    )
    from src.activities.plan_validation import (
        audit_validation,
        validate_cognitive_plan,
    )
    from src.activities.result_consolidation import (
        buffer_telemetry,
        consolidate_results,
        publish_telemetry,
        trigger_self_healing,
    )
    from src.activities.sla_monitoring import check_workflow_sla_proactive
    from src.activities.ticket_generation import (
        allocate_resources,
        generate_execution_tickets,
        publish_ticket_to_kafka,
    )
    from src.config.settings import get_settings


def _safe_set_baggage(key: str, value: Any) -> None:
    """Define baggage OTEL de forma REPLAY-SAFE.

    set_baggage não emite comandos Temporal (só manipula contexto OTEL), mas no
    sandbox/REPLAY o tracing pode estar inactivo. Nunca deixar uma falha de
    baggage quebrar o workflow.
    """
    if value is None:
        return
    # Tracing inactivo no sandbox/REPLAY — ignorar silenciosamente.
    with contextlib.suppress(Exception):
        set_baggage(key, value)


def _safe_span_event(span: Any, name: str, attributes: dict | None = None) -> None:
    """Emite um span event de forma REPLAY-SAFE.

    Quando o tracer é None (REPLAY/QUERY no sandbox), span é None — não fazer nada.
    """
    if span is None:
        return
    try:
        if attributes is not None:
            span.add_event(name, attributes)
        else:
            span.add_event(name)
    except Exception:
        pass


@workflow.defn
class OrchestrationWorkflow:
    """
    Workflow de orquestração que converte Cognitive Plans em Execution Tickets.

    Implementa o Fluxo C (Orquestração de Execução Adaptativa) conforme
    documento-06-fluxos-processos-neural-hive-mind.md Seção 6.
    """

    def __init__(self):
        self._status = "initializing"
        self._tickets_generated = []
        self._rejected_tickets = []
        self._workflow_result = {}
        self._sla_warnings = []
        self._saga_id = None
        self._compensation_order = []
        # Atribuído em run() a partir de workflow.info().workflow_id; inicializado
        # aqui por robustez para o signal handler ticket_completed nunca crashar
        # com AttributeError caso seja invocado antes de run() o atribuir.
        self._workflow_id = None

    @workflow.run
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Executa o workflow de orquestração.

        Args:
            input_data: Dicionário contendo:
                - consolidated_decision: Decisão consolidada do Consensus Engine
                - cognitive_plan: Plano cognitivo a ser executado

        Returns:
            Dicionário com resultado da orquestração (tickets, status, métricas)
        """
        consolidated_decision = input_data["consolidated_decision"]
        cognitive_plan = input_data["cognitive_plan"]

        workflow_id = workflow.info().workflow_id
        # FIX-2 (C1): expor o workflow_id no estado para que o signal handler
        # ticket_completed o possa propagar ao evento de otimização. run() só
        # tinha a variável local, deixando self._workflow_id por atribuir.
        self._workflow_id = workflow_id
        plan_id = cognitive_plan.get("plan_id")
        intent_id = cognitive_plan.get("intent_id")

        # set_baggage não emite comandos Temporal (apenas contexto OTEL), mas no
        # sandbox/REPLAY pode receber/produzir None — proteger para não crashar.
        _safe_set_baggage("plan_id", plan_id)
        _safe_set_baggage("intent_id", intent_id)

        # FIX-1 (BLOQUEADOR): get_tracer() devolve None durante REPLAY/QUERY no
        # sandbox Temporal. Usar nullcontext quando tracer é None para nunca
        # crashar com AttributeError ('NoneType'.start_as_current_span). Spans
        # OTEL não emitem comandos Temporal, logo o guard não quebra determinismo.
        tracer = get_tracer()
        workflow.logger.info(
            f"Iniciando workflow de orquestração: workflow_id={workflow_id}, plan_id={plan_id}, intent_id={intent_id}"
        )

        span_cm = (
            tracer.start_as_current_span(
                "orchestration_workflow.run",
                attributes={
                    "neural.hive.workflow.id": workflow_id,
                    "neural.hive.plan.id": plan_id,
                    "neural.hive.intent.id": intent_id,
                    "neural.hive.workflow.type": "orchestration",
                },
            )
            if tracer
            else contextlib.nullcontext()
        )
        with span_cm as span:
            try:
                # === C1: Validar Plano Cognitivo ===
                self._status = "validating_plan"
                workflow.logger.info("C1: Validando plano cognitivo")

                validation_result = await workflow.execute_activity(
                    validate_cognitive_plan,
                    args=[plan_id, cognitive_plan],
                    start_to_close_timeout=timedelta(seconds=5),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2,
                        initial_interval=timedelta(milliseconds=500),
                        non_retryable_error_types=["InvalidSchemaError"],
                    ),
                )

                if not validation_result["valid"]:
                    workflow.logger.error(
                        f'Plano cognitivo inválido: errors={validation_result["errors"]}'
                    )
                    raise ApplicationError(
                        f'Plano cognitivo inválido: {validation_result["errors"]}',
                        non_retryable=True,
                    )

                # Auditar validação
                await workflow.execute_activity(
                    audit_validation,
                    args=[plan_id, validation_result],
                    start_to_close_timeout=timedelta(seconds=3),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

                workflow.logger.info("Plano cognitivo validado com sucesso")
                _safe_span_event(span, "plan_validated")

                # === C2: Quebrar Plano em Tickets ===
                self._status = "generating_tickets"
                workflow.logger.info("C2: Gerando execution tickets")

                tickets = await workflow.execute_activity(
                    generate_execution_tickets,
                    args=[cognitive_plan, consolidated_decision],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(
                        maximum_attempts=2, initial_interval=timedelta(seconds=1)
                    ),
                )

                self._tickets_generated = tickets
                workflow.logger.info(f"Gerados {len(tickets)} execution tickets")
                _safe_span_event(span, "tickets_generated", {"count": len(tickets)})

                # === Verificação Proativa de SLA (pós C2) ===
                get_settings()
                # Monitoramento proativo de SLA sempre executado (habilitado por default)
                try:
                    sla_check_result = await workflow.execute_activity(
                        check_workflow_sla_proactive,
                        args=[workflow_id, tickets, "post_ticket_generation"],
                        start_to_close_timeout=timedelta(seconds=5),
                        retry_policy=RetryPolicy(
                            maximum_attempts=2,
                            non_retryable_error_types=["SLAMonitorUnavailable"],
                        ),
                    )

                    if sla_check_result.get("deadline_approaching"):
                        warning_msg = f'SLA proativo: deadline se aproximando, restam {sla_check_result.get("remaining_seconds")}s, critical_tickets={sla_check_result.get("critical_tickets")}'
                        workflow.logger.warning(warning_msg)
                        self._sla_warnings.append(
                            {
                                "checkpoint": "post_ticket_generation",
                                "warning": warning_msg,
                                "data": sla_check_result,
                            }
                        )
                except Exception as e:
                    error_msg = str(e)
                    # Verificar se erro é de activity não registrada
                    if "not registered" in error_msg.lower():
                        # Extrair nome da activity do erro
                        activity_name = "check_workflow_sla_proactive"

                        # Registrar métrica de activity não registrada
                        from src.observability.metrics import get_metrics

                        workflow_metrics = get_metrics()
                        workflow_metrics.record_temporal_activity_registration_error(
                            activity_name=activity_name,
                            workflow_name="OrchestrationWorkflow",
                        )

                    workflow.logger.warning(
                        f"sla_proactive_check_failed_continuing: checkpoint=post_ticket_generation, error={error_msg}"
                    )

                # === C3: Alocar Recursos ===
                self._status = "allocating_resources"
                workflow.logger.info("C3: Alocando recursos")

                allocated_tickets = []
                for ticket in tickets:
                    allocated_ticket = await workflow.execute_activity(
                        allocate_resources,
                        args=[ticket],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(
                            maximum_attempts=3, initial_interval=timedelta(seconds=2)
                        ),
                    )
                    allocated_tickets.append(allocated_ticket)

                workflow.logger.info("Recursos alocados para todos os tickets")
                _safe_span_event(span, "resources_allocated")

                # === C4: Executar Tarefas (publicar tickets) ===
                self._status = "publishing_tickets"
                workflow.logger.info("C4: Publicando tickets no Kafka")

                published_tickets = []
                rejected_tickets = []
                for ticket in allocated_tickets:
                    publish_result = await workflow.execute_activity(
                        publish_ticket_to_kafka,
                        args=[ticket],
                        start_to_close_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(
                            maximum_attempts=5,
                            initial_interval=timedelta(seconds=1),
                            backoff_coefficient=2.0,
                        ),
                    )
                    # Separar tickets publicados dos rejeitados
                    if publish_result.get("rejected"):
                        rejected_tickets.append(publish_result)
                        workflow.logger.warning(
                            f'ticket_rejected_by_scheduler: ticket_id={publish_result.get("ticket_id")}, rejection_reason={publish_result.get("rejection_reason")}'
                        )
                    else:
                        published_tickets.append(publish_result)

                workflow.logger.info(
                    f"Publicados {len(published_tickets)} tickets no Kafka, {len(rejected_tickets)} rejeitados"
                )
                _safe_span_event(
                    span,
                    "tickets_published",
                    {
                        "count": len(published_tickets),
                        "rejected_count": len(rejected_tickets),
                    },
                )

                # Armazenar rejected_tickets para incluir no resultado final
                self._rejected_tickets = rejected_tickets

                # === Verificação Proativa de SLA (pós C4) ===
                # Monitoramento proativo de SLA sempre executado (habilitado por default)
                try:
                    sla_check_result = await workflow.execute_activity(
                        check_workflow_sla_proactive,
                        args=[workflow_id, published_tickets, "post_ticket_publishing"],
                        start_to_close_timeout=timedelta(seconds=5),
                        retry_policy=RetryPolicy(
                            maximum_attempts=2,
                            non_retryable_error_types=["SLAMonitorUnavailable"],
                        ),
                    )

                    if sla_check_result.get("deadline_approaching"):
                        warning_msg = f'SLA proativo: deadline se aproximando, restam {sla_check_result.get("remaining_seconds")}s, critical_tickets={sla_check_result.get("critical_tickets")}'
                        workflow.logger.warning(warning_msg)
                        self._sla_warnings.append(
                            {
                                "checkpoint": "post_ticket_publishing",
                                "warning": warning_msg,
                                "data": sla_check_result,
                            }
                        )

                    if sla_check_result.get("budget_critical"):
                        budget_warning = "SLA proativo: budget crítico detectado"
                        workflow.logger.warning(budget_warning)
                        self._sla_warnings.append(
                            {
                                "checkpoint": "post_ticket_publishing",
                                "warning": budget_warning,
                                "data": sla_check_result,
                            }
                        )
                except Exception as e:
                    workflow.logger.warning(
                        f"Falha na verificação proativa de SLA (pós C4): {e}"
                    )

                # === C5: Consolidar Resultado ===
                self._status = "consolidating_results"
                workflow.logger.info("C5: Consolidando resultados")

                workflow_result = await workflow.execute_activity(
                    consolidate_results,
                    args=[published_tickets, workflow_id],
                    start_to_close_timeout=timedelta(seconds=20),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )

                self._workflow_result = workflow_result

                # Publicar eventos de otimização para tickets completados
                try:
                    optimization_result = await workflow.execute_activity(
                        publish_workflow_optimization_events,
                        args=[published_tickets, workflow_id],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
                    workflow.logger.info(
                        f'Optimization events published: {optimization_result.get("successful_count")} successful, '
                        f'{optimization_result.get("failed_count")} failed'
                    )
                except Exception as e:
                    workflow.logger.warning(
                        f"Falha ao publicar eventos de otimização em massa: {e}"
                    )

                # Se resultado inconsistente, acionar compensacao (Saga Pattern) e autocura
                if not workflow_result.get("consistent", True):
                    workflow.logger.warning(
                        "Resultado inconsistente detectado, acionando compensacao"
                    )

                    # Identificar tickets que falharam
                    failed_tickets = [
                        t
                        for t in published_tickets
                        if t.get("ticket", {}).get("status") == "FAILED"
                    ]

                    compensation_results = []
                    if failed_tickets:
                        # Ordenacao topologica reversa para compensacao
                        # Compensar na ordem inversa de execucao
                        try:
                            tickets_to_compensate = await workflow.execute_activity(
                                build_compensation_order,
                                args=[failed_tickets, published_tickets],
                                start_to_close_timeout=timedelta(seconds=10),
                            )

                            # Executar compensacao para cada ticket
                            for ticket_to_compensate in tickets_to_compensate:
                                try:
                                    compensation_ticket_id = (
                                        await workflow.execute_activity(
                                            compensate_ticket,
                                            args=[
                                                ticket_to_compensate,
                                                "workflow_inconsistent",
                                            ],
                                            start_to_close_timeout=timedelta(
                                                seconds=30
                                            ),
                                            retry_policy=RetryPolicy(
                                                maximum_attempts=3,
                                                initial_interval=timedelta(seconds=2),
                                            ),
                                        )
                                    )

                                    # Atualizar ticket original com referencia
                                    await workflow.execute_activity(
                                        update_ticket_compensation_status,
                                        args=[
                                            ticket_to_compensate.get("ticket_id"),
                                            compensation_ticket_id,
                                        ],
                                        start_to_close_timeout=timedelta(seconds=5),
                                    )

                                    compensation_results.append(
                                        {
                                            "original_ticket_id": ticket_to_compensate.get(
                                                "ticket_id"
                                            ),
                                            "compensation_ticket_id": compensation_ticket_id,
                                            "status": "triggered",
                                        }
                                    )
                                except Exception as comp_err:
                                    workflow.logger.error(
                                        f'Falha ao compensar ticket {ticket_to_compensate.get("ticket_id")}: {comp_err}'
                                    )
                                    compensation_results.append(
                                        {
                                            "original_ticket_id": ticket_to_compensate.get(
                                                "ticket_id"
                                            ),
                                            "compensation_ticket_id": None,
                                            "status": "failed",
                                            "error": str(comp_err),
                                        }
                                    )
                        except Exception as build_order_err:
                            workflow.logger.error(
                                f"Falha ao construir ordem de compensacao: {build_order_err}"
                            )

                        # Adicionar resultados de compensacao ao workflow_result
                        workflow_result["compensation_results"] = compensation_results
                        workflow_result["compensation_triggered"] = len(
                            [
                                c
                                for c in compensation_results
                                if c["status"] == "triggered"
                            ]
                        )

                    # Ainda acionar self-healing para analise
                    workflow.logger.info("Acionando self-healing apos compensacao")
                    await workflow.execute_activity(
                        trigger_self_healing,
                        args=[
                            workflow_id,
                            workflow_result.get("errors", []),
                            published_tickets,
                            workflow_result,
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                _safe_span_event(span, "results_consolidated")

                # === C6: Publicar Telemetria ===
                self._status = "publishing_telemetry"
                workflow.logger.info("C6: Publicando telemetria")

                try:
                    await workflow.execute_activity(
                        publish_telemetry,
                        args=[workflow_result],
                        start_to_close_timeout=timedelta(seconds=15),
                        retry_policy=RetryPolicy(
                            maximum_attempts=5,
                            initial_interval=timedelta(seconds=1),
                            backoff_coefficient=2.0,
                        ),
                    )
                except Exception as e:
                    workflow.logger.warning(
                        f"Falha ao publicar telemetria, usando buffer: {e}"
                    )
                    await workflow.execute_activity(
                        buffer_telemetry,
                        args=[workflow_result],
                        start_to_close_timeout=timedelta(seconds=5),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                _safe_span_event(span, "telemetry_published")

                # Workflow concluído com sucesso
                self._status = "completed"
                workflow.logger.info("Workflow de orquestração concluído com sucesso")

                return {
                    "workflow_id": workflow_id,
                    "plan_id": plan_id,
                    "intent_id": intent_id,
                    "status": "success",
                    "tickets_generated": len(tickets),
                    "result": workflow_result,
                    "sla_warnings": self._sla_warnings,
                }

            except Exception as e:
                self._status = "failed"
                # REPLAY-SAFE: span pode ser None quando tracer é None (sandbox).
                if span is not None:
                    try:
                        span.record_exception(e)
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    except Exception:
                        pass
                workflow.logger.error(
                    f"Erro no workflow de orquestração: {e}", exc_info=True
                )
                raise

    @workflow.signal
    async def ticket_completed(self, ticket_id: str, result: dict[str, Any]):
        """
        Signal para notificar conclusão de um ticket.

        Publica evento ticket.completed no Kafka para análise de otimização
        pelo optimizer-agents.

        Args:
            ticket_id: ID do ticket concluído
            result: Resultado da execução do ticket
        """
        workflow.logger.info(f"Ticket {ticket_id} concluído: result={result}")

        # Publicar evento para otimização (não-bloqueante)
        try:
            await workflow.execute_activity(
                publish_ticket_completed_event,
                args=[result, self._workflow_id],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as e:
            # Não falhar o workflow se a publicação falhar
            workflow.logger.warning(f"Falha ao publicar evento de otimização: {e}")

    @workflow.signal
    async def cancel_workflow(self):
        """Signal para cancelar workflow manualmente."""
        workflow.logger.info("Recebida solicitação de cancelamento do workflow")
        self._status = "cancelled"

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """
        Query para consultar status atual do workflow.

        Returns:
            Dicionário com status e informações do workflow
        """
        return {
            "status": self._status,
            "tickets_generated": len(self._tickets_generated),
            "workflow_result": self._workflow_result,
            "sla_warnings": self._sla_warnings,
        }

    @workflow.query
    def get_tickets(self) -> list:
        """
        Query para listar tickets gerados.

        Returns:
            Lista de tickets gerados
        """
        return self._tickets_generated

    @workflow.query
    def get_saga_state(self) -> dict[str, Any]:
        """
        Query para consultar estado da Saga.

        Retorna informações sobre o estado da Saga associada ao workflow,
        incluindo status, steps e ordem de compensação.

        Returns:
            Dict com estado da Saga contendo:
                - saga_id: ID da Saga associada
                - status: Status atual do workflow
                - steps: Lista de steps (tickets) gerados
                - compensation_order: Ordem de compensação
                - completed_steps: Steps completados com sucesso
                - pending_steps: Steps pendentes
                - rejected_tickets: Tickets rejeitados pelo scheduler
        """
        # Identificar steps completados vs pendentes
        completed_steps = [
            ticket
            for ticket in self._tickets_generated
            if ticket.get("status") == "COMPLETED"
        ]
        pending_steps = [
            ticket
            for ticket in self._tickets_generated
            if ticket.get("status") in ["PENDING", "IN_PROGRESS"]
        ]

        # Construir ordem de compensação (ordem reversa dos completados)
        if not self._compensation_order and completed_steps:
            self._compensation_order = [
                ticket.get("ticket_id") for ticket in reversed(completed_steps)
            ]

        return {
            "saga_id": self._saga_id,
            "status": self._status,
            "steps": self._tickets_generated,
            "compensation_order": self._compensation_order,
            "completed_steps": completed_steps,
            "pending_steps": pending_steps,
            "rejected_tickets": self._rejected_tickets,
            "total_steps": len(self._tickets_generated),
            "completed_count": len(completed_steps),
            "pending_count": len(pending_steps),
            "rejected_count": len(self._rejected_tickets),
        }
