"""
Processa eventos de SLA e dispara workflows.

Responsável por monitorar eventos de SLO violations e budget changes,
acionando workflows de remediação e avaliação de políticas.
"""

from typing import Any, Optional

import structlog

from src.models.schedule import SchedulePriority, ScheduleTrigger, ScheduleType
from src.services.scheduler import ScheduleManager

logger = structlog.get_logger(__name__)


class SLAEventHandler:
    """
    Processa eventos de SLA e dispara workflows.

    Monitora:
    - Violations de SLO → dispara workflows de remediação
    - Budget crítico → dispara workflows de avaliação de políticas
    - Freeze triggers → dispara workflows de congelação
    """

    def __init__(self, schedule_manager: ScheduleManager):
        self.schedule_manager = schedule_manager
        self.logger = logger

    async def on_budget_updated(
        self, slo_id: str, service_name: str, budget_status: str, remaining_budget: float
    ) -> Optional[str]:
        """
        Handler para evento de budget atualizado.

        Aciona PolicyEvaluationWorkflow quando budget atinge status crítico.

        Args:
            slo_id: ID do SLO
            service_name: Nome do serviço
            budget_status: Status do budget (OK, WARNING, CRITICAL, EXHAUSTED)
            remaining_budget: Budget restante em porcentagem

        Returns:
            ID do schedule criado ou None
        """
        self.logger.info(
            "budget_updated",
            slo_id=slo_id,
            service_name=service_name,
            budget_status=budget_status,
            remaining_budget=remaining_budget,
        )

        # Verificar se precisa acionar policy evaluation
        if budget_status in ("CRITICAL", "EXHAUSTED"):
            return await self._trigger_policy_evaluation(
                slo_id, service_name, budget_status, remaining_budget
            )

        return None

    async def on_slo_violation(self, violation: dict[str, Any]) -> Optional[str]:
        """
        Handler para evento de violação de SLO.

        Aciona RemediationWorkflow quando violação é detectada.

        Args:
            violation: Dados da violação

        Returns:
            ID do schedule criado ou None
        """
        slo_id = violation.get("slo_id")
        service_name = violation.get("service_name")
        severity = violation.get("severity", "MEDIUM")

        self.logger.warning(
            "slo_violation_detected", slo_id=slo_id, service_name=service_name, severity=severity
        )

        # Acionar workflow de remediação
        return await self._trigger_remediation_workflow(violation)

    async def on_freeze_trigger(self, slo_id: str, service_name: str, reason: str) -> Optional[str]:
        """
        Handler para trigger de congelação.

        Aciona FreezeWorkflow quando freeze é necessário.

        Args:
            slo_id: ID do SLO
            service_name: Nome do serviço
            reason: Razão da congelação

        Returns:
            ID do schedule criado ou None
        """
        self.logger.error(
            "freeze_triggered", slo_id=slo_id, service_name=service_name, reason=reason
        )

        try:
            schedule_id = await self.schedule_manager.create_schedule(
                workflow="FreezeWorkflow",
                schedule_type=ScheduleType.EVENT,
                trigger=ScheduleTrigger(
                    event_type="sla.freeze",
                    event_filter={"slo_id": slo_id},
                    parameters={"slo_id": slo_id, "service_name": service_name, "reason": reason},
                ),
                priority=SchedulePriority.CRITICAL,
                metadata={"trigger_reason": reason, "slo_id": slo_id},
            )

            return schedule_id

        except Exception as e:
            self.logger.error("freeze_schedule_failed", slo_id=slo_id, error=str(e))
            return None

    async def _trigger_policy_evaluation(
        self, slo_id: str, service_name: str, budget_status: str, remaining_budget: float
    ) -> Optional[str]:
        """
        Dispara workflow de avaliação de políticas.

        Args:
            slo_id: ID do SLO
            service_name: Nome do serviço
            budget_status: Status do budget
            remaining_budget: Budget restante

        Returns:
            ID do schedule criado ou None
        """
        try:
            schedule_id = await self.schedule_manager.create_schedule(
                workflow="PolicyEvaluationWorkflow",
                schedule_type=ScheduleType.EVENT,
                trigger=ScheduleTrigger(
                    event_type="sla.budgets",
                    event_filter={"slo_id": slo_id, "status": budget_status},
                    parameters={
                        "slo_id": slo_id,
                        "service_name": service_name,
                        "budget_status": budget_status,
                        "remaining_budget": remaining_budget,
                    },
                ),
                priority=SchedulePriority.HIGH,
                metadata={"trigger": "budget_critical", "slo_id": slo_id},
            )

            self.logger.info(
                "policy_evaluation_triggered",
                schedule_id=schedule_id,
                slo_id=slo_id,
                budget_status=budget_status,
            )

            return schedule_id

        except Exception as e:
            self.logger.error("policy_evaluation_failed", slo_id=slo_id, error=str(e))
            return None

    async def _trigger_remediation_workflow(self, violation: dict[str, Any]) -> Optional[str]:
        """
        Dispara workflow de remediação.

        Args:
            violation: Dados da violação

        Returns:
            ID do schedule criado ou None
        """
        try:
            severity = violation.get("severity", "MEDIUM")
            priority = (
                SchedulePriority.CRITICAL if severity == "CRITICAL" else SchedulePriority.HIGH
            )

            schedule_id = await self.schedule_manager.create_schedule(
                workflow="RemediationWorkflow",
                schedule_type=ScheduleType.EVENT,
                trigger=ScheduleTrigger(
                    event_type="slo.violation",
                    event_filter={"slo_id": violation.get("slo_id"), "severity": severity},
                    parameters=violation,
                ),
                priority=priority,
                metadata={"trigger": "slo_violation", "severity": severity},
            )

            self.logger.info(
                "remediation_triggered",
                schedule_id=schedule_id,
                slo_id=violation.get("slo_id"),
                severity=severity,
            )

            return schedule_id

        except Exception as e:
            self.logger.error("remediation_trigger_failed", violation=violation, error=str(e))
            return None

    async def create_default_schedules(self) -> dict[str, str]:
        """
        Cria schedules padrão do sistema.

        Schedules criados:
        - BudgetRecalculationWorkflow: Hora em hora
        - ReportGenerationWorkflow: Diário à meia-noite
        - MaintenanceWorkflow: Semanal (domingo 2h)

        Returns:
            Dict com IDs dos schedules criados
        """
        schedules = {}

        # Budget recalculation - hora em hora
        schedules["budget_recalculation"] = await self.schedule_manager.create_schedule(
            workflow="BudgetRecalculationWorkflow",
            schedule_type=ScheduleType.CRON,
            trigger=ScheduleTrigger(
                cron_expression="0 * * * *", parameters={"force_recalculate": False}
            ),
            priority=SchedulePriority.MEDIUM,
            metadata={"description": "Recalcula budgets hora em hora"},
        )

        # Report generation - diário
        schedules["report_generation"] = await self.schedule_manager.create_schedule(
            workflow="ReportGenerationWorkflow",
            schedule_type=ScheduleType.CRON,
            trigger=ScheduleTrigger(
                cron_expression="0 0 * * *",
                parameters={"report_types": ["slo", "budget", "performance"]},
            ),
            priority=SchedulePriority.LOW,
            metadata={"description": "Gera relatórios diários"},
        )

        # Maintenance - semanal
        schedules["maintenance"] = await self.schedule_manager.create_schedule(
            workflow="MaintenanceWorkflow",
            schedule_type=ScheduleType.CRON,
            trigger=ScheduleTrigger(
                cron_expression="0 2 * * 0", parameters={"tasks": ["cleanup", "vacuum", "stats"]}
            ),
            priority=SchedulePriority.LOW,
            metadata={"description": "Manutenção semanal"},
        )

        self.logger.info("default_schedules_created", schedules_count=len(schedules))

        return schedules
