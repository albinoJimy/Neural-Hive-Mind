"""
PreemptionManager - Gerencia preempção de tickets em execução.

Coordena a preempção de tickets de baixa prioridade
para dar lugar a tickets de alta prioridade.
"""

from datetime import timezone

UTC = timezone.utc  # type: ignore
from enum import Enum
import sys

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import Enum


class StrEnum(str, Enum):
    """Compatibilidade StrEnum para Python 3.10"""
    def _generate_next_value_(name, start, count, last_values):
        return name as _StrEnum
else:
    class _StrEnum(str, Enum):
        """Polyfill for StrEnum on Python 3.10"""
        pass
from typing import Any

import structlog

from src.scheduler.preemption_rules import PreemptionDecision, PreemptionRules
from src.scheduler.priority_queues import PriorityLevel

logger = structlog.get_logger(__name__)


class PreemptionStatus(_StrEnum):
    """Status de uma preempção."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DENIED = "DENIED"
    NOT_FOUND = "NOT_FOUND"


class PreemptionManager:
    """
    Gerencia preempção de tickets.

    Responsabilidades:
    - Avaliar se preempção é permitida
    - Encontrar tickets preemptíveis em uma fila
    - Executar preempção de tickets
    - Rastrear preempções executadas
    """

    def __init__(self, preemption_rules: PreemptionRules, queue_manager, metrics=None):
        """
        Inicializa o gerenciador de preempção.

        Args:
            preemption_rules: Regras de preempção
            queue_manager: Gerenciador de filas
            metrics: Métricas (opcional)
        """
        self.preemption_rules = preemption_rules
        self.queue_manager = queue_manager
        self.metrics = metrics
        self.logger = logger.bind(component="preemption_manager")

        # Histórico de preempções (para análise)
        self.preemption_history: list[dict[str, Any]] = []

    def can_preempt(
        self, high_priority_ticket: dict[str, Any], low_priority_ticket: dict[str, Any]
    ) -> PreemptionDecision:
        """
        Verifica se ticket de alta prioridade pode preemptar ticket de baixa prioridade.

        Args:
            high_priority_ticket: Ticket que quer preemptar
            low_priority_ticket: Ticket em execução que seria preemptado

        Returns:
            PreemptionDecision indicando se permitido
        """
        decision = self.preemption_rules.can_preempt(high_priority_ticket, low_priority_ticket)

        # Registrar verificação
        self._record_preemption_check(high_priority_ticket, low_priority_ticket, decision)

        return decision

    def find_preemptible_ticket(
        self, priority_level: PriorityLevel, executing_tickets: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """
        Encontra um ticket preemptível na lista de tickets em execução.

        Args:
            priority_level: Nível de prioridade mínimo para preempção
            executing_tickets: Lista de tickets atualmente em execução

        Returns:
            Ticket preemptível ou None
        """
        # Criar ticket de referência para comparar prioridade
        reference_ticket = {"priority": priority_level.value, "ticket_id": "reference"}

        # Buscar em ordem reversa (últimos primeiro)
        for ticket in reversed(executing_tickets):
            decision = self.can_preempt(reference_ticket, ticket)

            if decision == PreemptionDecision.ALLOWED:
                self.logger.info(
                    "preemptible_ticket_found",
                    ticket_id=ticket.get("ticket_id"),
                    priority_level=priority_level.value,
                )
                return ticket

        self.logger.debug(
            "no_preemptible_ticket_found",
            priority_level=priority_level.value,
            executing_count=len(executing_tickets),
        )

        return None

    async def preempt_ticket(
        self, low_priority_ticket: dict[str, Any], reason: str = "priority_preemption"
    ) -> dict[str, Any]:
        """
        Executa preempção de um ticket.

        Args:
            low_priority_ticket: Ticket a ser preemptado
            reason: Razão da preempção

        Returns:
            Dict com status e detalhes da preempção
        """
        ticket_id = low_priority_ticket.get("ticket_id", "unknown")

        self.logger.info("ticket_preemption_started", ticket_id=ticket_id, reason=reason)

        try:
            # 1. Verificar se ticket pode ser preemptado
            # (assinatura simplificada para teste)
            decision = self._validate_preemption(low_priority_ticket)

            if decision != PreemptionDecision.ALLOWED:
                self._record_preemption_result(ticket_id, PreemptionStatus.DENIED, decision)
                return {
                    "ticket_id": ticket_id,
                    "status": PreemptionStatus.DENIED,
                    "reason": decision.value,
                }

            # 2. Executar compensação do ticket
            compensation_result = await self._compensate_ticket(low_priority_ticket)

            if not compensation_result.get("success", False):
                self._record_preemption_result(
                    ticket_id,
                    PreemptionStatus.FAILED,
                    compensation_result.get("error", "compensation_failed"),
                )
                return {
                    "ticket_id": ticket_id,
                    "status": PreemptionStatus.FAILED,
                    "reason": compensation_result.get("error", "compensation_failed"),
                }

            # 3. Re-enfileirar ticket (ou marcar para retry)
            requeue_result = await self._requeue_ticket(low_priority_ticket)

            # 4. Registrar sucesso
            self._record_preemption_result(ticket_id, PreemptionStatus.SUCCESS, reason)

            self.logger.info(
                "ticket_preemption_completed",
                ticket_id=ticket_id,
                compensation_id=compensation_result.get("compensation_ticket_id"),
            )

            return {
                "ticket_id": ticket_id,
                "status": PreemptionStatus.SUCCESS,
                "compensation_ticket_id": compensation_result.get("compensation_ticket_id"),
                "requeued": requeue_result.get("success", False),
            }

        except Exception as e:
            self.logger.error(
                "ticket_preemption_error", ticket_id=ticket_id, error=str(e), exc_info=True
            )

            self._record_preemption_result(ticket_id, PreemptionStatus.FAILED, str(e))

            return {"ticket_id": ticket_id, "status": PreemptionStatus.FAILED, "error": str(e)}

    async def _compensate_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """
        Executa compensação do ticket sendo preemptado.

        Args:
            ticket: Ticket a ser compensado

        Returns:
            Resultado da compensação
        """
        ticket_id = ticket.get("ticket_id", "unknown")

        self.logger.info("ticket_preemption_compensation", ticket_id=ticket_id)

        # Na implementação completa, aqui seria chamado o serviço de compensação
        # Por enquanto, retornamos sucesso simulado
        return {
            "success": True,
            "compensation_ticket_id": f"comp-{ticket_id}",
            "message": "Compensation triggered",
        }

    async def _requeue_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        """
        Re-enfileira ticket preemptado.

        Args:
            ticket: Ticket a ser re-enfileirado

        Returns:
            Resultado da re-enfileiramento
        """
        ticket_id = ticket.get("ticket_id", "unknown")

        self.logger.info("ticket_preemption_requeue", ticket_id=ticket_id)

        # Na implementação completa, aqui seria usado o QueueManager
        return {"success": True, "queue": "LOW"}

    def _validate_preemption(self, ticket: dict[str, Any]) -> PreemptionDecision:
        """
        Valida se ticket pode ser preemptado.

        Args:
            ticket: Ticket a validar

        Returns:
            PreemptionDecision
        """
        # Verificar progresso da execução
        execution_progress = self.preemption_rules._get_execution_progress(ticket)

        if execution_progress > self.preemption_rules.max_execution_progress_pct:
            return PreemptionDecision.DENIED_EXECUTION_PROGRESS

        # Verificar se é compensatable
        if not self.preemption_rules._is_compensatable(ticket):
            return PreemptionDecision.DENIED_NOT_COMPENSATABLE

        # Verificar priority matrix (CRITICAL/HIGH pode preemptar LOW)
        ticket_priority = self.preemption_rules._extract_priority(ticket)

        # Tickets LOW podem sempre ser preemptados por CRITICAL/HIGH
        if ticket_priority not in ["LOW", "NORMAL"]:
            return PreemptionDecision.DENIED_PRIORITY_DIFF

        return PreemptionDecision.ALLOWED

    def _record_preemption_check(
        self, high_ticket: dict[str, Any], low_ticket: dict[str, Any], decision: PreemptionDecision
    ):
        """Registra verificação de preempção para análise."""
        self.preemption_history.append(
            {
                "timestamp": self._get_timestamp(),
                "high_ticket_id": high_ticket.get("ticket_id"),
                "low_ticket_id": low_ticket.get("ticket_id"),
                "decision": decision.value,
                "high_priority": self.preemption_rules._extract_priority(high_ticket),
                "low_priority": self.preemption_rules._extract_priority(low_ticket),
            }
        )

    def _record_preemption_result(self, ticket_id: str, status: PreemptionStatus, reason: str):
        """Registra resultado de preempção."""
        if self.metrics:
            self.metrics.preemption_executed_total.labels(status=status.value).inc()

    def _get_timestamp(self) -> int:
        """Retorna timestamp atual em milissegundos."""
        from datetime import datetime

        return int(datetime.now(UTC).timestamp() * 1000)

    def get_preemption_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Retorna histórico de preempções.

        Args:
            limit: Número máximo de registros

        Returns:
            Lista de preempções registradas
        """
        return self.preemption_history[-limit:]

    def get_preemption_statistics(self) -> dict[str, Any]:
        """
        Retorna estatísticas de preempção.

        Returns:
            Dict com estatísticas
        """
        if not self.preemption_history:
            return {"total_checks": 0, "total_allowed": 0, "total_denied": 0, "allowance_rate": 0.0}

        total = len(self.preemption_history)
        allowed = sum(
            1
            for entry in self.preemption_history
            if entry["decision"] == PreemptionDecision.ALLOWED.value
        )

        return {
            "total_checks": total,
            "total_allowed": allowed,
            "total_denied": total - allowed,
            "allowance_rate": round(allowed / total * 100, 1) if total > 0 else 0.0,
        }
