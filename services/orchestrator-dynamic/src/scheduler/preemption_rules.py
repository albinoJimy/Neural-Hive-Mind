"""
PreemptionRules - Regras para preempção de tickets de baixa prioridade.

Define quando um ticket de alta prioridade pode preemptar
um ticket de baixa prioridade que está em execução.
"""

from datetime import UTC

UTC = UTC  # type: ignore
import sys
from enum import Enum

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum as _StrEnum
else:

    class _StrEnum(str, Enum):
        """Polyfill for StrEnum on Python 3.10"""

        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name


from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PreemptionDecision(_StrEnum):
    """Decisão de preempção."""

    ALLOWED = "ALLOWED"
    DENIED_EXECUTION_PROGRESS = "DENIED_EXECUTION_PROGRESS"
    DENIED_NOT_COMPENSATABLE = "DENIED_NOT_COMPENSATABLE"
    DENIED_PRIORITY_DIFF = "DENIED_PRIORITY_DIFF"
    DENIED_SAME_PRIORITY = "DENIED_SAME_PRIORITY"


class PreemptionRules:
    """
    Define regras para preempção de tickets.

    Regras:
    1. CRITICAL pode preemptar LOW e NORMAL
    2. HIGH pode preemptar LOW
    3. Preempção só permitida se execution_time < 30%
    4. Preempção só permitida se ticket é compensatable
    5. Mesma prioridade nunca pode preemptar
    """

    # Threshold máximo de progresso para permitir preempção
    MAX_EXECUTION_PROGRESS_PCT = 0.30  # 30%

    # Mapeamento de quais prioridades podem preemptar quais
    # Nota: HIGH NÃO pode preemptar NORMAL
    PREEMPTION_MATRIX = {
        "CRITICAL": ["HIGH", "NORMAL", "LOW"],
        "HIGH": ["LOW"],  # Apenas LOW
        "NORMAL": ["LOW"],
        "LOW": [],
    }

    def __init__(self, config=None):
        """
        Inicializa as regras de preempção.

        Args:
            config: Configurações (opcional)
        """
        self.config = config
        self.logger = logger.bind(component="preemption_rules")

        # Configurações customizáveis
        self.max_execution_progress_pct = getattr(
            config, "preemption_max_execution_progress_pct", self.MAX_EXECUTION_PROGRESS_PCT
        )

        self.enable_preemption = getattr(config, "preemption_enabled", True)

    def can_preempt(
        self, high_priority_ticket: dict[str, Any], low_priority_ticket: dict[str, Any]
    ) -> PreemptionDecision:
        """
        Verifica se ticket de alta prioridade pode preemptar ticket de baixa prioridade.

        Args:
            high_priority_ticket: Ticket que quer preemptar
            low_priority_ticket: Ticket em execução que seria preemptado

        Returns:
            PreemptionDecision indicando se permitido e motivo se negado
        """
        high_ticket_id = high_priority_ticket.get("ticket_id", "unknown")
        low_ticket_id = low_priority_ticket.get("ticket_id", "unknown")

        if not self.enable_preemption:
            self.logger.debug(
                "preemption_disabled", high_ticket_id=high_ticket_id, low_ticket_id=low_ticket_id
            )
            return PreemptionDecision.DENIED_PRIORITY_DIFF

        # Regra 1: Verificar diferença de prioridade
        high_priority = self._extract_priority(high_priority_ticket)
        low_priority = self._extract_priority(low_priority_ticket)

        if not self._is_preemption_allowed(high_priority, low_priority):
            self.logger.debug(
                "preemption_denied_priority_matrix",
                high_ticket_id=high_ticket_id,
                low_ticket_id=low_ticket_id,
                high_priority=high_priority,
                low_priority=low_priority,
            )
            return PreemptionDecision.DENIED_PRIORITY_DIFF

        # Regra 2: Verificar progresso da execução
        execution_progress = self._get_execution_progress(low_priority_ticket)
        if execution_progress > self.max_execution_progress_pct:
            self.logger.debug(
                "preemption_denied_execution_progress",
                high_ticket_id=high_ticket_id,
                low_ticket_id=low_ticket_id,
                execution_progress=execution_progress,
                max_allowed=self.max_execution_progress_pct,
            )
            return PreemptionDecision.DENIED_EXECUTION_PROGRESS

        # Regra 3: Verificar se ticket é compensatable
        if not self._is_compensatable(low_priority_ticket):
            self.logger.debug(
                "preemption_denied_not_compensatable",
                high_ticket_id=high_ticket_id,
                low_ticket_id=low_ticket_id,
            )
            return PreemptionDecision.DENIED_NOT_COMPENSATABLE

        self.logger.info(
            "preemption_allowed",
            high_ticket_id=high_ticket_id,
            low_ticket_id=low_ticket_id,
            high_priority=high_priority,
            low_priority=low_priority,
        )

        return PreemptionDecision.ALLOWED

    def _is_preemption_allowed(self, high_priority: str, low_priority: str) -> bool:
        """
        Verifica se matrix de preempção permite.

        Args:
            high_priority: Prioridade do ticket preemptor
            low_priority: Prioridade do ticket a ser preemptado

        Returns:
            True se preempção é permitida pela matrix
        """
        high = high_priority.upper()
        low = low_priority.upper()

        # Mesma prioridade nunca pode preemptar
        if high == low:
            return False

        # Verificar matrix
        allowed_targets = self.PREEMPTION_MATRIX.get(high, [])
        return low in allowed_targets

    def _get_execution_progress(self, ticket: dict[str, Any]) -> float:
        """
        Obtém progresso de execução do ticket.

        Args:
            ticket: Execution ticket

        Returns:
            Progresso [0.0, 1.0] ou 0.0 se não disponível
        """
        # Tentar obter de campo direto (se existir explicitamente)
        if "execution_progress" in ticket:
            execution_progress = ticket["execution_progress"]
            if isinstance(execution_progress, (int, float)):
                return min(max(execution_progress, 0.0), 1.0)

        # Tentar calcular baseado em timestamps
        started_at = ticket.get("started_at")
        timeout_ms = ticket.get("sla", {}).get("timeout_ms", 300000)

        if started_at and timeout_ms:
            from datetime import datetime

            now_ms = int(datetime.now(UTC).timestamp() * 1000)
            elapsed_ms = now_ms - started_at
            return min(elapsed_ms / timeout_ms, 1.0)

        return 0.0

    def _is_compensatable(self, ticket: dict[str, Any]) -> bool:
        """
        Verifica se ticket é compensatable.

        Args:
            ticket: Execution ticket

        Returns:
            True se ticket pode ser compensado
        """
        # Verificar flag explícita
        compensatable = ticket.get("compensatable", True)

        if isinstance(compensatable, bool):
            return compensatable

        # Verificar presença de compensatable_transaction
        compensation_action = ticket.get("compensation_action")
        return compensation_action is not None and len(compensation_action) > 0

    def _extract_priority(self, ticket: dict[str, Any]) -> str:
        """
        Extrai prioridade do ticket.

        Args:
            ticket: Execution ticket

        Returns:
            Nível de prioridade (CRITICAL/HIGH/NORMAL/LOW)
        """
        # Tentar obter de campo direto
        priority = ticket.get("priority")

        if priority:
            return priority.upper()

        # Tentar obter de risk_band
        risk_band = ticket.get("risk_band", "normal")
        return risk_band.upper()

    def get_preemption_cost(self, low_priority_ticket: dict[str, Any]) -> dict[str, Any]:
        """
        Estima custo da preempção de um ticket.

        Args:
            low_priority_ticket: Ticket que seria preemptado

        Returns:
            Dict com estimativa de custo
        """
        execution_progress = self._get_execution_progress(low_priority_ticket)
        compensatable = self._is_compensatable(low_priority_ticket)

        # Custo base
        base_cost = {
            "progress_lost": execution_progress,
            "needs_compensation": compensatable,
            "estimated_rollback_ms": int(execution_progress * 1000),  # Estimativa grosseira
            "resource_waste": execution_progress,  # % de recursos desperdiçados
        }

        # Ajustar se não compensatable (custo mais alto)
        if not compensatable:
            base_cost["estimated_rollback_ms"] = -1  # Indeterminado/maior
            base_cost["resource_waste"] = execution_progress * 1.5  # Penalidade

        return base_cost

    def should_allow_preemption(
        self,
        high_priority_ticket: dict[str, Any],
        low_priority_ticket: dict[str, Any],
        max_cost_threshold: float = 0.5,
    ) -> PreemptionDecision:
        """
        Decisão completa de preempção considerando custos.

        Args:
            high_priority_ticket: Ticket preemptor
            low_priority_ticket: Ticket a ser preemptado
            max_cost_threshold: Custo máximo aceitável [0.0, 1.0]

        Returns:
            PreemptionDecision
        """
        # Verificar regras base
        decision = self.can_preempt(high_priority_ticket, low_priority_ticket)

        if decision != PreemptionDecision.ALLOWED:
            return decision

        # Verificar custo
        cost = self.get_preemption_cost(low_priority_ticket)
        resource_waste = cost.get("resource_waste", 0.0)

        if resource_waste > max_cost_threshold:
            self.logger.debug(
                "preemption_denied_cost_too_high",
                resource_waste=resource_waste,
                max_cost_threshold=max_cost_threshold,
            )
            return PreemptionDecision.DENIED_EXECUTION_PROGRESS

        return PreemptionDecision.ALLOWED
