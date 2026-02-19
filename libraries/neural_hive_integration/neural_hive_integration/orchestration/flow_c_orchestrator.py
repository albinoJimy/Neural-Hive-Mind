"""
Flow C Orchestrator - Complete implementation of Flow C (C1-C6).

Coordinates Intent → Decision → Orchestration → Tickets → Workers → Code Forge → Deploy → Telemetry.
"""

import structlog
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from opentelemetry import trace
from prometheus_client import Counter, Histogram, Gauge

from neural_hive_integration.clients.orchestrator_client import OrchestratorClient
from neural_hive_integration.clients.service_registry_client import ServiceRegistryClient, AgentInfo
from neural_hive_integration.clients.execution_ticket_client import ExecutionTicketClient
from neural_hive_integration.clients.worker_agent_client import WorkerAgentClient
from neural_hive_integration.clients.code_forge_client import CodeForgeClient
from neural_hive_integration.clients.sla_management_client import SLAManagementClient
from neural_hive_integration.models.flow_c_context import FlowCContext, FlowCStep, FlowCResult
from neural_hive_integration.telemetry.flow_c_telemetry import FlowCTelemetryPublisher
from neural_hive_resilience.circuit_breaker import MonitoredCircuitBreaker, CircuitBreakerError
from aiokafka import AIOKafkaProducer
import os
import json

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)

# Metrics
flow_c_duration = Histogram(
    "neural_hive_flow_c_duration_seconds",
    "Flow C end-to-end duration",
    buckets=[60, 300, 900, 1800, 3600, 7200, 14400],  # 1min to 4h
)
flow_c_steps_duration = Histogram(
    "neural_hive_flow_c_steps_duration_seconds",
    "Flow C individual step duration",
    ["step"],
)
flow_c_success = Counter("neural_hive_flow_c_success_total", "Flow C successful executions")
flow_c_failures = Counter("neural_hive_flow_c_failures_total", "Flow C failed executions", ["reason"])
flow_c_sla_violations = Counter("neural_hive_flow_c_sla_violations_total", "Flow C SLA violations")
flow_c_workflow_query_duration = Histogram(
    "neural_hive_flow_c_workflow_query_duration_seconds",
    "Duration of workflow state queries",
    ["query_name"],
)
flow_c_workflow_query_failures = Counter(
    "neural_hive_flow_c_workflow_query_failures_total",
    "Failed workflow state queries",
    ["query_name", "reason"],
)
flow_c_ticket_validation_failures = Counter(
    "neural_hive_flow_c_ticket_validation_failures_total",
    "Ticket schema validation failures",
)
flow_c_ticket_schema_version = Counter(
    "neural_hive_flow_c_ticket_schema_version_total",
    "Ticket schema versions processed",
    ["schema_version"],
)

# C3 - Discover Workers Metrics (P1-002)
worker_discovery_duration = Histogram(
    "neural_hive_flow_c_worker_discovery_duration_seconds",
    "Duration of worker discovery operations",
    ["status"],
)
workers_discovered_total = Counter(
    "neural_hive_flow_c_workers_discovered_total",
    "Total number of workers discovered",
)
worker_discovery_failures_total = Counter(
    "neural_hive_flow_c_worker_discovery_failures_total",
    "Total number of worker discovery failures",
    ["reason"],
)

# C4 - Assign Tickets Metrics (P1-002)
tickets_assigned_total = Counter(
    "neural_hive_flow_c_tickets_assigned_total",
    "Total number of tickets assigned to workers",
)
assignment_duration = Histogram(
    "neural_hive_flow_c_assignment_duration_seconds",
    "Duration of ticket assignment operations",
    ["status"],
)
assignment_failures_total = Counter(
    "neural_hive_flow_c_assignment_failures_total",
    "Total number of assignment failures",
    ["reason"],
)
worker_load_gauge = None  # Will be initialized as Gauge in __init__

# C5 - Monitor Execution Metrics (P1-002)
tickets_completed_total = Counter(
    "neural_hive_flow_c_tickets_completed_total",
    "Total number of tickets completed",
)
tickets_failed_total = Counter(
    "neural_hive_flow_c_tickets_failed_total",
    "Total number of tickets failed",
    ["reason"],
)
execution_duration = Histogram(
    "neural_hive_flow_c_execution_duration_seconds",
    "Duration of ticket execution",
    ["status", "task_type"],
)


class FlowCOrchestrator:
    """Orchestrator for complete Flow C integration (C1-C6)."""

    def __init__(self):
        self.orchestrator_client = OrchestratorClient()
        self.service_registry = ServiceRegistryClient()
        self.ticket_client = ExecutionTicketClient()
        self.sla_client = SLAManagementClient()
        self.telemetry = FlowCTelemetryPublisher()
        self.logger = logger.bind(service="flow_c_orchestrator")
        self.approval_producer: AIOKafkaProducer = None
        self.kafka_bootstrap_servers = os.getenv(
            'KAFKA_BOOTSTRAP_SERVERS',
            'neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092'
        )
        self.approval_requests_topic = os.getenv(
            'APPROVAL_REQUESTS_TOPIC',
            'cognitive-plans-approval-requests'
        )

        # Circuit breaker para status checks (C5)
        self.status_check_breaker = MonitoredCircuitBreaker(
            service_name="flow_c_orchestrator",
            circuit_name="ticket_status_check",
            fail_max=5,
            reset_timeout=60,
        )

        # Initialize worker load gauge (P1-002)
        global worker_load_gauge
        if worker_load_gauge is None:
            worker_load_gauge = Gauge(
                "neural_hive_flow_c_worker_load",
                "Current number of tickets assigned to each worker",
                ["worker_id"]
            )
        self.worker_load_gauge = worker_load_gauge

    async def initialize(self):
        """Initialize all clients."""
        await self.sla_client.initialize()
        await self.telemetry.initialize()

        # Initialize Kafka producer for approval requests
        producer_config = {
            'bootstrap_servers': self.kafka_bootstrap_servers,
            'value_serializer': lambda v: json.dumps(v).encode('utf-8'),
        }
        self.approval_producer = AIOKafkaProducer(**producer_config)
        await self.approval_producer.start()
        self.logger.info(
            "approval_producer_initialized",
            topic=self.approval_requests_topic,
            bootstrap_servers=self.kafka_bootstrap_servers
        )

    async def close(self):
        """Close all clients."""
        await self.orchestrator_client.close()
        await self.service_registry.close()
        await self.ticket_client.close()
        await self.sla_client.close()
        await self.telemetry.close()
        if self.approval_producer:
            await self.approval_producer.stop()
            self.logger.info("approval_producer_closed")

    async def _publish_approval_request(self, consolidated_decision: Dict[str, Any]) -> None:
        """
        Publica o plano no tópico de approval requests quando review_required.

        Args:
            consolidated_decision: Decisão consolidada do Consensus Engine
        """
        plan_id = consolidated_decision.get("plan_id")
        intent_id = consolidated_decision.get("intent_id")
        cognitive_plan = consolidated_decision.get("cognitive_plan", {})

        # Construir ApprovalRequest
        approval_request = {
            "plan_id": plan_id,
            "intent_id": intent_id,
            "risk_score": consolidated_decision.get("aggregated_risk", 0.5),
            "risk_band": cognitive_plan.get("risk_band", "medium"),
            "is_destructive": cognitive_plan.get("is_destructive", False),
            "destructive_tasks": cognitive_plan.get("destructive_tasks", []),
            "risk_matrix": consolidated_decision.get("risk_matrix"),
            "cognitive_plan": cognitive_plan,
            "requested_at": datetime.utcnow().isoformat(),
            "status": "pending"
        }

        self.logger.info(
            "publishing_approval_request",
            plan_id=plan_id,
            intent_id=intent_id,
            topic=self.approval_requests_topic
        )

        await self.approval_producer.send_and_wait(
            self.approval_requests_topic,
            value=approval_request
        )

        self.logger.info(
            "approval_request_published",
            plan_id=plan_id,
            topic=self.approval_requests_topic
        )

    @tracer.start_as_current_span("flow_c.execute")
    async def execute_flow_c(self, consolidated_decision: Dict[str, Any]) -> FlowCResult:
        """
        Execute complete Flow C (C1-C6).

        Flow:
        C0: Check if human approval required (review_required)
        C1: Validate consolidated decision
        C2: Start Temporal workflow and generate tickets
        C3: Discover available workers
        C4: Assign tickets to workers
        C5: Monitor execution and collect results
        C6: Publish telemetry

        Args:
            consolidated_decision: Consolidated decision from Phase 1

        Returns:
            Flow C execution result
        """
        start_time = datetime.utcnow()
        steps: List[FlowCStep] = []

        intent_id = consolidated_decision.get("intent_id")
        plan_id = consolidated_decision.get("plan_id")
        decision_id = consolidated_decision.get("decision_id")
        final_decision = consolidated_decision.get("final_decision", "")

        self.logger.info(
            "starting_flow_c_execution",
            intent_id=intent_id,
            plan_id=plan_id,
            decision_id=decision_id,
            final_decision=final_decision,
        )

        # C0: Verificar se requer aprovação humana
        if final_decision == "review_required":
            self.logger.info(
                "decision_requires_human_approval",
                plan_id=plan_id,
                decision_id=decision_id,
                final_decision=final_decision,
                action="Publishing to approval requests topic and awaiting approval"
            )

            # Publicar no tópico de approval requests
            await self._publish_approval_request(consolidated_decision)

            # Retornar resultado indicando que aguarda aprovação
            end_time = datetime.utcnow()
            total_duration = int((end_time - start_time).total_seconds() * 1000)

            self.logger.info(
                "flow_c_awaiting_human_approval",
                plan_id=plan_id,
                decision_id=decision_id,
                duration_ms=total_duration,
                note="Plan submitted for human approval - not executing tickets"
            )

            return FlowCResult(
                success=True,
                steps=[],
                total_duration_ms=total_duration,
                tickets_generated=0,
                tickets_completed=0,
                tickets_failed=0,
                telemetry_published=False,
                sla_compliant=True,
                sla_remaining_seconds=14400,  # 4 horas
                awaiting_approval=True  # Novo campo
            )

        # Extract correlation_id with fallback chain FIRST (before context is used)
        # 1. From consolidated_decision
        # 2. From cognitive_plan inside decision
        # 3. Auto-generated by FlowCContext validator
        correlation_id = consolidated_decision.get("correlation_id")
        if not correlation_id:
            cognitive_plan = consolidated_decision.get("cognitive_plan", {})
            correlation_id = cognitive_plan.get("correlation_id")

        if not correlation_id:
            self.logger.warning(
                "correlation_id_missing",
                intent_id=consolidated_decision.get("intent_id"),
                plan_id=consolidated_decision.get("plan_id"),
                decision_id=consolidated_decision.get("decision_id"),
                message="correlation_id ausente na decisão e no plano - será gerado automaticamente"
            )

        # Create context - FlowCContext validará e gerará correlation_id se necessário
        # IMPORTANT: Create context BEFORE using it for telemetry events
        context = FlowCContext(
            intent_id=consolidated_decision["intent_id"],
            plan_id=consolidated_decision["plan_id"],
            decision_id=consolidated_decision["decision_id"],
            correlation_id=correlation_id,  # Pode ser None - validator tratará
            trace_id=format(trace.get_current_span().get_span_context().trace_id, '032x'),
            span_id=format(trace.get_current_span().get_span_context().span_id, '016x'),
            started_at=start_time,
            sla_deadline=start_time + timedelta(hours=4),
            priority=consolidated_decision.get("priority", 5),
            risk_band=consolidated_decision.get("risk_band", "medium"),
        )

        # Publicar evento FLOW_C_STARTED (P0-003) - NOW context is defined
        try:
            await self.telemetry.publish_flow_started(
                intent_id=context.intent_id,
                plan_id=context.plan_id,
                decision_id=context.decision_id,
                correlation_id=context.correlation_id,
            )
        except Exception as e:
            self.logger.warning("flow_started_event_failed", error=str(e))

        # Log se correlation_id foi gerado automaticamente
        if not correlation_id:
            self.logger.info(
                "correlation_id_generated",
                generated_correlation_id=context.correlation_id,
                intent_id=context.intent_id,
            )

        self.logger.info(
            "starting_flow_c",
            intent_id=context.intent_id,
            plan_id=context.plan_id,
            decision_id=context.decision_id,
        )

        try:
            # P3-001: Helper function para calcular SLA restante
            def calculate_sla_remaining() -> float:
                """Calcula SLA restante em segundos."""
                now = datetime.utcnow()
                remaining = (context.sla_deadline - now).total_seconds()
                return remaining

            def log_sla_status(step_name: str, step_duration_ms: int):
                """Loga status do SLA após cada step."""
                sla_remaining_seconds = calculate_sla_remaining()
                total_elapsed_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

                if sla_remaining_seconds < 0:
                    self.logger.error(
                        "step_sla_violated",
                        step=step_name,
                        step_duration_ms=step_duration_ms,
                        total_elapsed_ms=total_elapsed_ms,
                        sla_violation_seconds=abs(sla_remaining_seconds),
                        sla_deadline=context.sla_deadline.isoformat(),
                    )
                elif sla_remaining_seconds < 300:  # Menos de 5 minutos
                    self.logger.warning(
                        "step_sla_critical",
                        step=step_name,
                        step_duration_ms=step_duration_ms,
                        total_elapsed_ms=total_elapsed_ms,
                        sla_remaining_seconds=int(sla_remaining_seconds),
                        sla_deadline=context.sla_deadline.isoformat(),
                        message="Menos de 5 minutos de SLA restante",
                    )
                elif sla_remaining_seconds < 1800:  # Menos de 30 minutos
                    self.logger.warning(
                        "step_sla_warning",
                        step=step_name,
                        step_duration_ms=step_duration_ms,
                        total_elapsed_ms=total_elapsed_ms,
                        sla_remaining_seconds=int(sla_remaining_seconds),
                        sla_deadline=context.sla_deadline.isoformat(),
                        message="Menos de 30 minutos de SLA restante",
                    )
                else:
                    self.logger.info(
                        "step_sla_ok",
                        step=step_name,
                        step_duration_ms=step_duration_ms,
                        total_elapsed_ms=total_elapsed_ms,
                        sla_remaining_seconds=int(sla_remaining_seconds),
                        sla_deadline=context.sla_deadline.isoformat(),
                    )

            # C1: Validate Decision
            step_c1 = await self._execute_c1_validate(consolidated_decision, context)
            log_sla_status("C1", step_c1.duration_ms)
            steps.append(step_c1)

            # C2: Start Workflow and Generate Tickets
            step_c2_start = datetime.utcnow()
            workflow_id, tickets = await self._execute_c2_generate_tickets(
                consolidated_decision, context
            )
            step_c2_end = datetime.utcnow()
            step_c2_duration = int((step_c2_end - step_c2_start).total_seconds() * 1000)
            log_sla_status("C2", step_c2_duration)
            step_c2 = FlowCStep(
                step_name="C2",
                status="completed",
                started_at=step_c2_start,
                completed_at=step_c2_end,
                duration_ms=step_c2_duration,
                metadata={"workflow_id": workflow_id, "tickets_count": len(tickets)},
            )
            steps.append(step_c2)

            # C3: Discover Workers
            step_c3_start = datetime.utcnow()
            workers = await self._execute_c3_discover_workers(tickets, context)
            step_c3_end = datetime.utcnow()
            step_c3_duration = int((step_c3_end - step_c3_start).total_seconds() * 1000)
            log_sla_status("C3", step_c3_duration)
            step_c3 = FlowCStep(
                step_name="C3",
                status="completed",
                started_at=step_c3_start,
                completed_at=step_c3_end,
                duration_ms=step_c3_duration,
                metadata={"workers_found": len(workers)},
            )
            steps.append(step_c3)

            # C4: Assign Tickets to Workers
            step_c4_start = datetime.utcnow()
            assignments = await self._execute_c4_assign_tickets(tickets, workers, context)
            step_c4_end = datetime.utcnow()
            step_c4_duration = int((step_c4_end - step_c4_start).total_seconds() * 1000)
            log_sla_status("C4", step_c4_duration)
            step_c4 = FlowCStep(
                step_name="C4",
                status="completed",
                started_at=step_c4_start,
                completed_at=step_c4_end,
                duration_ms=step_c4_duration,
                metadata={"assignments_count": len(assignments)},
            )
            steps.append(step_c4)

            # C5: Monitor Execution
            step_c5_start = datetime.utcnow()
            results = await self._execute_c5_monitor_execution(tickets, context)
            step_c5_end = datetime.utcnow()
            step_c5_duration = int((step_c5_end - step_c5_start).total_seconds() * 1000)
            log_sla_status("C5", step_c5_duration)
            step_c5 = FlowCStep(
                step_name="C5",
                status="completed",
                started_at=step_c5_start,
                completed_at=step_c5_end,
                duration_ms=step_c5_duration,
                metadata={"completed": results["completed"], "failed": results["failed"]},
            )
            steps.append(step_c5)

            # C6: Publish Telemetry
            step_c6_start = datetime.utcnow()
            await self._execute_c6_publish_telemetry(context, workflow_id, tickets, results)
            step_c6_end = datetime.utcnow()
            step_c6_duration = int((step_c6_end - step_c6_start).total_seconds() * 1000)
            log_sla_status("C6", step_c6_duration)
            step_c6 = FlowCStep(
                step_name="C6",
                status="completed",
                started_at=step_c6_start,
                completed_at=step_c6_end,
                duration_ms=step_c6_duration,
            )
            steps.append(step_c6)

            # Calculate metrics
            end_time = datetime.utcnow()
            total_duration = int((end_time - start_time).total_seconds() * 1000)

            # Calculate metrics
            end_time = datetime.utcnow()
            total_duration = int((end_time - start_time).total_seconds() * 1000)
            sla_remaining_seconds = (context.sla_deadline - end_time).total_seconds()

            # Check SLA com logging detalhado
            if sla_remaining_seconds < 0:
                flow_c_sla_violations.inc()
                violation_seconds = abs(sla_remaining_seconds)
                self.logger.error(
                    "flow_c_sla_violated",
                    duration_ms=total_duration,
                    duration_seconds=total_duration / 1000,
                    sla_deadline=context.sla_deadline.isoformat(),
                    completed_at=end_time.isoformat(),
                    violation_seconds=int(violation_seconds),
                    violation_minutes=round(violation_seconds / 60, 2),
                    sla_compliant=False,
                    tickets_completed=results["completed"],
                    tickets_failed=results["failed"],
                )
            elif sla_remaining_seconds < 300:  # Menos de 5 minutos de margem
                self.logger.warning(
                    "flow_c_completed_critical_sla",
                    duration_ms=total_duration,
                    duration_seconds=total_duration / 1000,
                    sla_deadline=context.sla_deadline.isoformat(),
                    completed_at=end_time.isoformat(),
                    sla_remaining_seconds=int(sla_remaining_seconds),
                    sla_remaining_minutes=round(sla_remaining_seconds / 60, 2),
                    sla_compliant=True,
                    margin_critical=True,
                    tickets_completed=results["completed"],
                    tickets_failed=results["failed"],
                )
            else:
                self.logger.info(
                    "flow_c_completed_success",
                    duration_ms=total_duration,
                    duration_seconds=total_duration / 1000,
                    sla_deadline=context.sla_deadline.isoformat(),
                    completed_at=end_time.isoformat(),
                    sla_remaining_seconds=int(sla_remaining_seconds),
                    sla_remaining_minutes=round(sla_remaining_seconds / 60, 2),
                    sla_compliant=True,
                    tickets_completed=results["completed"],
                    tickets_failed=results["failed"],
                )

            result = FlowCResult(
                success=True,
                steps=steps,
                total_duration_ms=total_duration,
                tickets_generated=len(tickets),
                tickets_completed=results["completed"],
                tickets_failed=results["failed"],
                telemetry_published=True,
                sla_compliant=sla_remaining_seconds >= 0,
                sla_remaining_seconds=int(sla_remaining_seconds) if sla_remaining_seconds >= 0 else int(sla_remaining_seconds),
            )

            flow_c_success.inc()
            flow_c_duration.observe(total_duration / 1000)

            return result

        except Exception as e:
            flow_c_failures.labels(reason=type(e).__name__).inc()
            self.logger.error("flow_c_failed", error=str(e))

            # Calcular duração e SLA mesmo em caso de erro
            end_time = datetime.utcnow()
            total_duration = int((end_time - start_time).total_seconds() * 1000)
            sla_remaining_seconds = (context.sla_deadline - end_time).total_seconds()

            return FlowCResult(
                success=False,
                steps=steps,
                total_duration_ms=total_duration,
                tickets_generated=0,
                tickets_completed=0,
                tickets_failed=0,
                telemetry_published=False,
                error=str(e),
                sla_compliant=sla_remaining_seconds >= 0,
                sla_remaining_seconds=int(sla_remaining_seconds) if sla_remaining_seconds >= 0 else int(sla_remaining_seconds),
            )

    async def _execute_c1_validate(
        self, decision: Dict[str, Any], context: FlowCContext
    ) -> FlowCStep:
        """C1: Validate consolidated decision."""
        step_start = datetime.utcnow()

        self.logger.info(
            "step_c1_starting_validate_decision",
            decision_id=context.decision_id,
            plan_id=context.plan_id,
        )

        with flow_c_steps_duration.labels(step="C1").time():
            # Validate required fields
            required_fields = ["intent_id", "plan_id", "decision_id", "cognitive_plan"]
            for field in required_fields:
                if field not in decision:
                    raise ValueError(f"Missing required field: {field}")

            self.logger.info(
                "step_c1_decision_validated",
                decision_id=context.decision_id,
                all_required_fields_present=True,
            )

            await self.telemetry.publish_event(
                event_type="step_completed",
                step="C1",
                intent_id=context.intent_id,
                plan_id=context.plan_id,
                decision_id=context.decision_id,
                workflow_id="",
                ticket_ids=[],
                duration_ms=0,
                status="completed",
                metadata={},
            )

            step_end = datetime.utcnow()
            return FlowCStep(
                step_name="C1",
                status="completed",
                started_at=step_start,
                completed_at=step_end,
                duration_ms=int((step_end - step_start).total_seconds() * 1000),
            )

    async def _execute_c2_generate_tickets(
        self, decision: Dict[str, Any], context: FlowCContext
    ) -> tuple[str, List[Dict[str, Any]]]:
        """C2: Start workflow and generate execution tickets."""

        cognitive_plan = decision.get("cognitive_plan", {})
        tasks_count = len(cognitive_plan.get("tasks", []))

        self.logger.info(
            "step_c2_starting_generate_tickets",
            plan_id=context.plan_id,
            tasks_count=tasks_count,
        )

        with flow_c_steps_duration.labels(step="C2").time():
            # Start Temporal workflow
            workflow_id = await self.orchestrator_client.start_workflow(
                cognitive_plan=cognitive_plan,
                correlation_id=context.correlation_id,
                priority=context.priority,
                sla_deadline_seconds=14400,
            )

            self.logger.info(
                "step_c2_workflow_started",
                workflow_id=workflow_id,
            )

            # Aguardar geração de tickets pelo workflow
            await asyncio.sleep(2)

            # Obter tickets do workflow state via query Temporal
            tickets = await self._get_tickets_from_workflow(
                workflow_id=workflow_id,
                cognitive_plan=cognitive_plan,
                context=context,
            )

            self.logger.info(
                "step_c2_tickets_generated",
                workflow_id=workflow_id,
                tickets_count=len(tickets),
            )

            return workflow_id, tickets

    async def _get_tickets_from_workflow(
        self,
        workflow_id: str,
        cognitive_plan: Dict[str, Any],
        context: FlowCContext,
    ) -> List[Dict[str, Any]]:
        """
        Obtém tickets do workflow state via query Temporal.

        Args:
            workflow_id: ID do workflow Temporal
            cognitive_plan: Plano cognitivo para fallback
            context: Contexto do Flow C

        Returns:
            Lista de tickets em formato dict
        """
        import time

        start_time = time.time()
        tickets = []

        try:
            # Query workflow for tickets via Temporal query
            query_result = await self.orchestrator_client.query_workflow(
                workflow_id=workflow_id,
                query_name="get_tickets",
            )

            # Extrair tickets do resultado
            if isinstance(query_result, dict):
                tickets = query_result.get("tickets", [])
            elif isinstance(query_result, list):
                tickets = query_result
            else:
                tickets = []

            duration = time.time() - start_time
            flow_c_workflow_query_duration.labels(query_name="get_tickets").observe(duration)

            if not tickets:
                self.logger.warning(
                    "no_tickets_from_workflow",
                    workflow_id=workflow_id,
                    plan_id=context.plan_id,
                    reason="workflow returned empty tickets list",
                )
                # Fallback para extração do cognitive_plan
                tickets = await self._extract_tickets_from_plan(cognitive_plan, context)
            else:
                # Validar schema dos tickets
                for ticket in tickets:
                    is_valid, errors = self._validate_ticket_schema(ticket)
                    if not is_valid:
                        self.logger.warning(
                            "ticket_schema_validation_warning",
                            ticket_id=ticket.get("ticket_id", "unknown"),
                            errors=errors,
                        )
                        flow_c_ticket_validation_failures.inc()

                self.logger.info(
                    "tickets_retrieved_from_workflow",
                    workflow_id=workflow_id,
                    tickets_count=len(tickets),
                )

        except Exception as e:
            duration = time.time() - start_time
            flow_c_workflow_query_duration.labels(query_name="get_tickets").observe(duration)
            flow_c_workflow_query_failures.labels(
                query_name="get_tickets",
                reason=type(e).__name__,
            ).inc()

            self.logger.error(
                "failed_to_query_workflow_tickets",
                workflow_id=workflow_id,
                plan_id=context.plan_id,
                error=str(e),
            )
            # Fallback para extração do cognitive_plan
            tickets = await self._extract_tickets_from_plan(cognitive_plan, context)

        return tickets

    async def _extract_tickets_from_plan(
        self,
        cognitive_plan: Dict[str, Any],
        context: FlowCContext,
    ) -> List[Dict[str, Any]]:
        """
        Extrai tickets do cognitive_plan como fallback.

        Args:
            cognitive_plan: Plano cognitivo contendo tasks
            context: Contexto do Flow C

        Returns:
            Lista de tickets criados via ticket_client
        """
        self.logger.info(
            "extracting_tickets_from_plan_fallback",
            plan_id=context.plan_id,
            reason="workflow query failed or returned empty",
        )

        tickets = []
        tasks = cognitive_plan.get("tasks", [])

        if not tasks:
            # Fallback: criar ticket genérico
            tasks = [{"type": "code_generation", "description": "Generate code based on plan"}]

        for task in tasks:
            ticket_data = {
                "plan_id": context.plan_id,
                "task_type": task.get("type", "code_generation"),
                "required_capabilities": task.get("required_capabilities", task.get("capabilities", ["python", "read", "write", "compute", "code"])),
                "payload": {
                    "template_id": task.get("template_id", "default_template"),
                    "parameters": task.get("parameters", {}),
                    "description": task.get("description", ""),
                },
                "sla_deadline": context.sla_deadline.isoformat(),
                "priority": context.priority,
            }
            ticket = await self.ticket_client.create_ticket(ticket_data)

            # Adicionar ticket_id ao payload para workers/Code Forge
            ticket_dict = ticket.model_dump()
            ticket_dict["payload"]["ticket_id"] = ticket.ticket_id
            tickets.append(ticket_dict)

        self.logger.info(
            "tickets_extracted_from_plan",
            plan_id=context.plan_id,
            tickets_count=len(tickets),
        )

        return tickets

    def _validate_ticket_schema(self, ticket: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Valida schema do ticket conforme execution-ticket.avsc.

        Campos obrigatórios conforme schema Avro:
        - ticket_id, plan_id, intent_id, decision_id, task_id, task_type,
          description, status, priority, risk_band, sla, qos, security_level, created_at

        Args:
            ticket: Ticket a validar

        Returns:
            Tuple (is_valid, errors)
        """
        errors = []

        # Campos obrigatórios conforme execution-ticket.avsc
        required_fields = [
            "ticket_id",
            "plan_id",
            "intent_id",
            "decision_id",
            "task_id",
            "task_type",
            "status",
            "priority",
            "risk_band",
        ]

        for field in required_fields:
            if field not in ticket:
                errors.append(f"Campo obrigatório ausente: {field}")

        # Validar enums conforme schema Avro
        valid_task_types = ["BUILD", "DEPLOY", "TEST", "VALIDATE", "EXECUTE", "COMPENSATE"]
        task_type = ticket.get("task_type")
        if task_type:
            if isinstance(task_type, str) and task_type.upper() not in valid_task_types:
                # Permitir valores legados (ex: code_generation) com warning
                self.logger.debug(
                    "legacy_task_type_detected",
                    ticket_id=ticket.get("ticket_id"),
                    task_type=task_type,
                )

        valid_statuses = ["PENDING", "RUNNING", "COMPLETED", "FAILED", "COMPENSATING", "COMPENSATED"]
        status = ticket.get("status")
        if status and isinstance(status, str) and status.upper() not in valid_statuses:
            errors.append(f"Status inválido: {status}")

        valid_priorities = ["LOW", "NORMAL", "HIGH", "CRITICAL"]
        priority = ticket.get("priority")
        if priority is not None:
            if isinstance(priority, int):
                # Aceitar prioridade numérica (1-10) para compatibilidade legada
                if priority < 1 or priority > 10:
                    errors.append(f"Prioridade numérica deve estar entre 1-10: {priority}")
            elif isinstance(priority, str) and priority.upper() not in valid_priorities:
                errors.append(f"Prioridade inválida: {priority}")

        # Validar risk_band conforme schema Avro
        valid_risk_bands = ["low", "medium", "high", "critical"]
        risk_band = ticket.get("risk_band")
        if risk_band:
            if isinstance(risk_band, str) and risk_band.lower() not in valid_risk_bands:
                errors.append(f"risk_band inválido: {risk_band}")

        # Validar estrutura SLA (obrigatória conforme schema)
        sla = ticket.get("sla")
        if sla is None:
            errors.append("Campo obrigatório ausente: sla")
        elif not isinstance(sla, dict):
            errors.append("SLA deve ser um objeto")
        else:
            # Validar campos obrigatórios do SLA
            if "deadline" not in sla:
                errors.append("Campo SLA ausente: deadline")
            elif not isinstance(sla["deadline"], (int, float)):
                errors.append("SLA.deadline deve ser timestamp numérico (long)")

            if "timeout_ms" not in sla:
                errors.append("Campo SLA ausente: timeout_ms")
            elif not isinstance(sla["timeout_ms"], (int, float)):
                errors.append("SLA.timeout_ms deve ser numérico (long)")

            if "max_retries" not in sla:
                errors.append("Campo SLA ausente: max_retries")
            elif not isinstance(sla["max_retries"], int):
                errors.append("SLA.max_retries deve ser inteiro (int)")

        # Validar estrutura QoS (obrigatória conforme schema)
        qos = ticket.get("qos")
        if qos is None:
            errors.append("Campo obrigatório ausente: qos")
        elif not isinstance(qos, dict):
            errors.append("QoS deve ser um objeto")
        else:
            # Validar delivery_mode enum
            valid_delivery_modes = ["AT_MOST_ONCE", "AT_LEAST_ONCE", "EXACTLY_ONCE"]
            if "delivery_mode" not in qos:
                errors.append("Campo QoS ausente: delivery_mode")
            elif qos["delivery_mode"] not in valid_delivery_modes:
                errors.append(f"QoS.delivery_mode inválido: {qos['delivery_mode']}")

            # Validar consistency enum
            valid_consistencies = ["EVENTUAL", "STRONG"]
            if "consistency" not in qos:
                errors.append("Campo QoS ausente: consistency")
            elif qos["consistency"] not in valid_consistencies:
                errors.append(f"QoS.consistency inválido: {qos['consistency']}")

            # Validar durability enum
            valid_durabilities = ["TRANSIENT", "PERSISTENT"]
            if "durability" not in qos:
                errors.append("Campo QoS ausente: durability")
            elif qos["durability"] not in valid_durabilities:
                errors.append(f"QoS.durability inválido: {qos['durability']}")

        # Verificar e registrar schema_version
        schema_version = ticket.get("schema_version", 1)
        supported_versions = [1, 2]

        # Registrar métrica de versão
        flow_c_ticket_schema_version.labels(schema_version=str(schema_version)).inc()

        if schema_version not in supported_versions:
            self.logger.warning(
                "unknown_ticket_schema_version",
                ticket_id=ticket.get("ticket_id"),
                schema_version=schema_version,
                supported_versions=supported_versions,
            )
            errors.append(f"schema_version não suportado: {schema_version} (suportados: {supported_versions})")

        return (len(errors) == 0, errors)

    async def _execute_c3_discover_workers(
        self, tickets: List[Dict[str, Any]], context: FlowCContext
    ) -> List[AgentInfo]:
        """C3: Discover available workers via Service Registry."""

        # Collect all required capabilities
        all_capabilities = set()
        for ticket in tickets:
            all_capabilities.update(ticket.get("required_capabilities", []))

        self.logger.info(
            "step_c3_starting_discover_workers",
            plan_id=context.plan_id,
            tickets_count=len(tickets),
            required_capabilities=list(all_capabilities),
        )

        with worker_discovery_duration.labels(status="success").time():  # P1-002: Métrica C3
            try:
                # Discover workers (com cache Redis se disponível)
                # Nota: O match_agents já filtra apenas agentes HEALTHY, então não precisamos do filtro status
                workers = await self.service_registry.discover_agents_cached(
                    capabilities=list(all_capabilities),
                    filters={"agent_type": "worker"},
                )

                workers_discovered_total.inc(len(workers))

                self.logger.info(
                    "step_c3_workers_discovered",
                    workers_count=len(workers),
                    workers_healthy=[w.agent_id for w in workers],
                )

                if not workers:
                    self.logger.warning("step_c3_no_healthy_workers_available")

                return workers

            except Exception as e:
                worker_discovery_failures_total.labels(reason=type(e).__name__).inc()
                worker_discovery_duration.labels(status="error").observe(0)
                raise

    def _calculate_worker_weights(self, workers: List[AgentInfo]) -> Dict[str, float]:
        """
        Calcular pesos para weighted round-robin baseado em telemetria dos workers.

        Fatores considerados:
        - success_rate: Taxa de sucesso histórica (0.0 - 1.0)
        - avg_duration_ms: Duração média das tarefas
        - current_load: Carga atual (número de tarefas em execução)

        Returns:
            Dict mapeando agent_id para peso (maior = mais preferido)
        """
        weights = {}
        for worker in workers:
            telemetry = worker.metadata.get('telemetry', {})

            # Extrair métricas (com defaults conservadores)
            success_rate = float(telemetry.get('success_rate', 0.8))
            avg_duration = float(telemetry.get('avg_duration_ms', 1000))
            current_load = int(telemetry.get('current_load', 0))
            max_capacity = int(telemetry.get('max_capacity', 10))

            # Fator de duração: workers mais rápidos têm peso maior
            # Normalizado para evitar divisão por zero
            duration_factor = max(0.1, 1.0 - (avg_duration / 10000.0))

            # Fator de carga: workers com menos carga têm peso maior
            load_factor = max(0.1, 1.0 - (current_load / max(max_capacity, 1)))

            # Peso final: combinação dos fatores
            weight = success_rate * duration_factor * load_factor
            weights[worker.agent_id] = max(0.1, weight)  # Peso mínimo de 0.1

        return weights

    def _select_worker_weighted_round_robin(
        self,
        workers: List[AgentInfo],
        weights: Dict[str, float],
        current_weights: Dict[str, float],
    ) -> Optional[AgentInfo]:
        """
        Selecionar worker usando weighted round-robin.

        Algoritmo:
        1. Incrementar current_weight de cada worker pelo seu peso
        2. Selecionar o worker com maior current_weight
        3. Decrementar o current_weight do selecionado pela soma total dos pesos

        Args:
            workers: Lista de workers disponíveis
            weights: Pesos calculados por worker
            current_weights: Estado atual dos pesos (modificado in-place)

        Returns:
            Worker selecionado
        """
        weight_sum = sum(weights.values())
        selected_worker = None
        max_weight = -float('inf')

        for worker in workers:
            current_weights[worker.agent_id] += weights.get(worker.agent_id, 1.0)
            if current_weights[worker.agent_id] > max_weight:
                max_weight = current_weights[worker.agent_id]
                selected_worker = worker

        if selected_worker:
            current_weights[selected_worker.agent_id] -= weight_sum

        return selected_worker

    async def _execute_c4_assign_tickets(
        self,
        tickets: List[Dict[str, Any]],
        workers: List[AgentInfo],
        context: FlowCContext,
    ) -> List[Dict[str, Any]]:
        """C4: Assign tickets to workers via weighted round-robin load balancing."""

        self.logger.info(
            "step_c4_starting_assign_tickets",
            plan_id=context.plan_id,
            tickets_count=len(tickets),
            workers_count=len(workers),
            workers_available=[w.agent_id for w in workers],
        )

        with flow_c_steps_duration.labels(step="C4").time():
            assignments = []

            if not workers:
                self.logger.error("step_c4_no_workers_available_for_assignment")
                return assignments

            # Calcular pesos baseados em telemetria dos workers
            worker_weights = self._calculate_worker_weights(workers)
            current_weights = {w.agent_id: 0.0 for w in workers}

            self.logger.info(
                "worker_weights_calculated",
                weights={w.agent_id: round(worker_weights[w.agent_id], 3) for w in workers},
            )

            for ticket in tickets:
                # Weighted round-robin selection
                worker = self._select_worker_weighted_round_robin(
                    workers, worker_weights, current_weights
                )

                if not worker:
                    self.logger.error(
                        "no_worker_selected",
                        ticket_id=ticket["ticket_id"],
                    )
                    continue

                # Criar cliente para o worker específico
                worker_client = WorkerAgentClient(base_url=worker.endpoint)

                try:
                    # Criar TaskAssignment
                    from neural_hive_integration.clients.worker_agent_client import TaskAssignment

                    task = TaskAssignment(
                        task_id=f"task_{ticket['ticket_id']}",
                        ticket_id=ticket["ticket_id"],
                        task_type=ticket.get("task_type", "code_generation"),
                        payload=ticket.get("payload", {}),
                        sla_deadline=ticket.get("sla_deadline", context.sla_deadline.isoformat()),
                    )

                    # Despachar tarefa para o worker
                    await worker_client.assign_task(task)

                    # Atualizar status do ticket para 'assigned'
                    await self.ticket_client.update_ticket_status(
                        ticket_id=ticket["ticket_id"],
                        status="assigned",
                        assigned_worker=worker.agent_id,
                    )

                    # Atualizar métrica de carga do worker (P1-002)
                    self.worker_load_gauge.labels(worker_id=worker.agent_id).inc()

                    tickets_assigned_total.inc()  # P1-002: Métrica C4

                    assignments.append({
                        "ticket_id": ticket["ticket_id"],
                        "worker_id": worker.agent_id,
                        "task_id": task.task_id,
                    })

                    self.logger.info(
                        "ticket_assigned",
                        ticket_id=ticket["ticket_id"],
                        worker_id=worker.agent_id,
                    )

                    # Publicar evento TICKET_ASSIGNED (P0-003)
                    try:
                        await self.telemetry.publish_ticket_assigned(
                            ticket_id=ticket["ticket_id"],
                            task_type=ticket.get("task_type", "unknown"),
                            worker_id=worker.agent_id,
                            intent_id=context.intent_id,
                            plan_id=context.plan_id,
                        )
                    except Exception as e:
                        self.logger.warning("ticket_assigned_event_failed", ticket_id=ticket["ticket_id"], error=str(e))
                except Exception as e:
                    assignment_failures_total.labels(reason=type(e).__name__).inc()  # P1-002: Métrica C4
                    self.logger.error(
                        "failed_to_assign_ticket",
                        ticket_id=ticket["ticket_id"],
                        worker_id=worker.agent_id,
                        error=str(e),
                    )
                finally:
                    await worker_client.close()

            self.logger.info(
                "step_c4_tickets_assigned",
                assignments_count=len(assignments),
                assignment_details=[(a["ticket_id"], a["worker_id"]) for a in assignments],
            )

            # P2-003: Validar balanceamento de distribuição round-robin
            if len(workers) > 1 and len(assignments) > 0:
                # Contar tickets por worker
                tickets_per_worker = {}
                for assignment in assignments:
                    worker_id = assignment["worker_id"]
                    tickets_per_worker[worker_id] = tickets_per_worker.get(worker_id, 0) + 1

                # Calcular métricas de distribuição
                max_tickets = max(tickets_per_worker.values())
                min_tickets = min(tickets_per_worker.values())

                if max_tickets - min_tickets > 1:
                    self.logger.warning(
                        "step_c4_round_robin_imbalanced",
                        workers_count=len(workers),
                        tickets_per_worker=tickets_per_worker,
                        max_tickets=max_tickets,
                        min_tickets=min_tickets,
                        message="Distribuição desbalanceada detectada",
                    )
                else:
                    self.logger.info(
                        "step_c4_round_robin_balanced",
                        workers_count=len(workers),
                        tickets_per_worker=tickets_per_worker,
                        distribution="balanced",
                    )

            return assignments

    async def _execute_c5_monitor_execution(
        self, tickets: List[Dict[str, Any]], context: FlowCContext
    ) -> Dict[str, int]:
        """C5: Monitor ticket execution até deadline SLA ou conclusão com polling adaptativo."""

        # P3-002: Polling adaptativo com exponential backoff
        base_interval = 10  # Começa com 10 segundos
        max_interval = 120  # Máximo de 2 minutos
        current_interval = base_interval

        # Calcular deadline baseado no SLA (4h) menos tempo já decorrido
        remaining_time = (context.sla_deadline - datetime.utcnow()).total_seconds()
        max_iterations = int(remaining_time / base_interval) if remaining_time > 0 else 1440  # Max 4h

        self.logger.info(
            "step_c5_starting_monitor_execution",
            plan_id=context.plan_id,
            tickets_count=len(tickets),
            base_interval=base_interval,
            max_interval=max_interval,
            max_iterations=max_iterations,
            sla_deadline=context.sla_deadline.isoformat(),
            polling_strategy="adaptive",
        )

        with flow_c_steps_duration.labels(step="C5").time():
            completed = 0
            failed = 0

            # Poll ticket status até conclusão ou deadline
            for iteration in range(max_iterations):
                statuses = []
                for ticket in tickets:
                    try:
                        # Usar circuit breaker para proteger chamadas de status
                        ticket_obj = await self.status_check_breaker.call_async(
                            self.ticket_client.get_ticket,
                            ticket["ticket_id"]
                        )
                        statuses.append(ticket_obj.status)
                    except CircuitBreakerError:
                        self.logger.warning(
                            "status_check_circuit_open",
                            ticket_id=ticket["ticket_id"],
                        )
                        statuses.append("unknown")  # Degradação graciosa
                    except Exception as e:
                        self.logger.error(
                            "failed_to_get_ticket_status",
                            ticket_id=ticket["ticket_id"],
                            error=str(e),
                        )
                        statuses.append("unknown")

                # Verificar se todos os tickets foram concluídos
                terminal_statuses = [s for s in statuses if s in ["completed", "failed"]]
                completed = statuses.count("completed")
                failed = statuses.count("failed")

                # P3-002: Ajustar intervalo baseado em progresso
                completion_ratio = len(terminal_statuses) / len(tickets) if tickets else 0

                if completion_ratio < 0.25:
                    # Poucos completados: polling rápido (10s)
                    new_interval = base_interval
                    reason = "early_stage_low_completion"
                elif completion_ratio < 0.5:
                    # Alguns completados: polling moderado (20s)
                    new_interval = 20
                    reason = "mid_stage_some_completion"
                elif completion_ratio < 0.75:
                    # Mais da metade completados: aumentar para 40s
                    new_interval = 40
                    reason = "late_stage_most_completion"
                elif completion_ratio < 0.9:
                    # Quase todos: polling mais lento (60s)
                    new_interval = 60
                    reason = "almost_done_slow_polling"
                else:
                    # Muito próximo do fim: polling mais lento ainda (max_interval)
                    new_interval = max_interval
                    reason = "final_stage_slow_polling"

                # Garantir que o intervalo não exceda o máximo
                current_interval = min(new_interval, max_interval)

                self.logger.debug(
                    "step_c5_polling_adaptive",
                    iteration=iteration,
                    completion_ratio=round(completion_ratio, 2),
                    completed=completed,
                    failed=failed,
                    unknown=statuses.count("unknown"),
                    current_interval=current_interval,
                    next_interval=reason,
                )

                if all(s in ["completed", "failed"] for s in statuses):
                    # P1-002: Atualizar métricas de conclusão
                    for idx, ticket in enumerate(tickets):
                        status = statuses[idx]
                        if status == "completed":
                            tickets_completed_total.inc()
                            task_type = ticket.get("task_type", "unknown")
                            execution_duration.labels(status="completed", task_type=task_type).observe(0)
                        elif status == "failed":
                            tickets_failed_total.labels(reason="execution_failed").inc()

                    self.logger.info(
                        "step_c5_all_tickets_completed",
                        completed=completed,
                        failed=failed,
                        total_tickets=len(tickets),
                        iteration=iteration,
                        final_poll_interval=current_interval,
                    )
                    break

                # Verificar se deadline foi ultrapassado
                if datetime.utcnow() >= context.sla_deadline:
                    self.logger.warning(
                        "step_c5_sla_deadline_reached",
                        completed=completed,
                        failed=failed,
                        total_tickets=len(tickets),
                        completion_ratio=round(completion_ratio, 2),
                    )
                    break

                # Aguardar com intervalo adaptativo
                await asyncio.sleep(current_interval)

            self.logger.info(
                "step_c5_monitoring_completed",
                tickets_completed=completed,
                tickets_failed=failed,
                total_tickets=len(tickets),
                total_iterations=iteration + 1,
                adaptive_polling_used=True,
            )

            return {"completed": completed, "failed": failed}

    async def _execute_c6_publish_telemetry(
        self,
        context: FlowCContext,
        workflow_id: str,
        tickets: List[Dict[str, Any]],
        results: Dict[str, int],
    ) -> None:
        """C6: Publish telemetry events."""

        self.logger.info(
            "step_c6_starting_publish_telemetry",
            plan_id=context.plan_id,
            workflow_id=workflow_id,
            tickets_count=len(tickets),
        )

        with flow_c_steps_duration.labels(step="C6").time():
            # Validar integridade de metadata
            completed_count = results.get("completed", 0)
            failed_count = results.get("failed", 0)
            total_tickets = len(tickets)

            if completed_count != total_tickets - failed_count:
                self.logger.warning(
                    "step_c6_metadata_integrity_warning",
                    completed_count=completed_count,
                    failed_count=failed_count,
                    total_tickets=total_tickets,
                    ticket_ids_count=len([t["ticket_id"] for t in tickets]),
                    message="Completed count does not match expected value"
                )

            # Garantir que tickets_completed está correto
            tickets_completed = max(completed_count, total_tickets - failed_count)

            self.logger.info(
                "step_c6_publishing_telemetry_event",
                event_type="flow_completed",
                tickets_completed=tickets_completed,
                tickets_failed=failed_count,
            )

            await self.telemetry.publish_event(
                event_type="flow_completed",
                step="C6",
                intent_id=context.intent_id,
                plan_id=context.plan_id,
                decision_id=context.decision_id,
                workflow_id=workflow_id,
                ticket_ids=[t["ticket_id"] for t in tickets],
                duration_ms=0,
                status="completed",
                metadata={
                    "tickets_completed": tickets_completed,
                    "tickets_failed": failed_count,
                    "total_tickets": total_tickets,
                },
            )

            self.logger.info(
                "step_c6_telemetry_published",
                flow_completed=True,
            )
