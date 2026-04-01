"""
RePrioritizer - Reavaliação dinâmica de prioridade de tickets.

Monitora tickets enfileirados e ajusta prioridade com base em mudanças
de contexto (SLA, risk band, eventos externos).
"""
from typing import Any

import structlog

from src.scheduler.priority_calculator import PriorityCalculator
from src.scheduler.queue_manager import QueueManager

logger = structlog.get_logger(__name__)


class RePrioritizer:
    """
    Gerencia reavaliação dinâmica de prioridades de tickets.

    Responsabilidades:
    - Recalcular priority_score de tickets enfileirados
    - Mover tickets entre filas quando prioridade muda
    - Disparar re-prioritização baseada em eventos
    """

    # Threshold para considerar mudança significativa de prioridade
    PRIORITY_CHANGE_THRESHOLD = 0.15  # 15% de mudança

    def __init__(self, priority_calculator: PriorityCalculator, queue_manager: QueueManager):
        """
        Inicializa o re-priorizador.

        Args:
            priority_calculator: Calculador de prioridade
            queue_manager: Gerenciador de filas
        """
        self.priority_calculator = priority_calculator
        self.queue_manager = queue_manager
        self.logger = logger.bind(component="reprioritizer")

    def reprioritize_ticket(self, ticket: dict[str, Any], current_queue: str) -> str | None:
        """
        Reavalia prioridade de um ticket e move se necessário.

        Args:
            ticket: Execution ticket
            current_queue: Fila atual do ticket

        Returns:
            Nova fila se movido, None se prioridade não mudou significativamente
        """
        ticket_id = ticket.get("ticket_id", "unknown")

        # Recalcular priority_score
        new_score = self.priority_calculator.calculate_priority_score(ticket)

        # Obter score atual aproximado baseado na fila
        current_score = self._estimate_score_from_queue(current_queue)

        # Verificar se mudança é significativa
        score_diff = abs(new_score - current_score)

        if score_diff < self.PRIORITY_CHANGE_THRESHOLD:
            self.logger.debug(
                "ticket_priority_unchanged",
                ticket_id=ticket_id,
                current_score=current_score,
                new_score=new_score,
                diff=score_diff,
            )
            return None

        # Mapear nova score para fila
        new_queue = self._map_score_to_queue(new_score)

        if new_queue == current_queue:
            self.logger.debug(
                "ticket_remains_in_same_queue",
                ticket_id=ticket_id,
                queue=current_queue,
                new_score=new_score,
            )
            return None

        self.logger.info(
            "ticket_reprioritized",
            ticket_id=ticket_id,
            old_queue=current_queue,
            new_queue=new_queue,
            old_score=current_score,
            new_score=new_score,
            diff=score_diff,
        )

        return new_queue

    def reprioritize_by_sla_urgency(self, ticket: dict[str, Any], sla_urgency: float) -> str | None:
        """
        Reavalia prioridade baseado em urgência de SLA.

        Args:
            ticket: Execution ticket
            sla_urgency: Nova urgência SLA [0.0, 1.0]

        Returns:
            Nova fila se movido, None caso contrário
        """
        ticket_id = ticket.get("ticket_id", "unknown")

        # Atualizar SLA no ticket
        if "sla" not in ticket:
            ticket["sla"] = {}
        ticket["sla"]["urgency"] = sla_urgency

        # Mapear diretamente para fila baseado em risk_band + sla_urgency
        risk_band = ticket.get("risk_band", "normal")
        new_level = self.queue_manager.map_risk_to_priority(risk_band, sla_urgency)
        new_queue = new_level.value

        # Estimar fila atual
        current_queue = self._estimate_queue_from_ticket(ticket)

        if new_queue == current_queue:
            return None

        self.logger.info(
            "ticket_reprioritized_by_sla",
            ticket_id=ticket_id,
            old_queue=current_queue,
            new_queue=new_queue,
            risk_band=risk_band,
            sla_urgency=sla_urgency,
        )

        return new_queue

    def reprioritize_by_risk_band(self, ticket: dict[str, Any], new_risk_band: str) -> str | None:
        """
        Reavalia prioridade baseado em mudança de risk_band.

        Args:
            ticket: Execution ticket
            new_risk_band: Nova banda de risco

        Returns:
            Nova fila se movido, None caso contrário
        """
        ticket_id = ticket.get("ticket_id", "unknown")

        # Atualizar risk_band
        old_risk_band = ticket.get("risk_band", "normal")
        ticket["risk_band"] = new_risk_band

        # Obter sla_urgency atual
        sla = ticket.get("sla", {})
        sla_urgency = sla.get("urgency", 0.0)

        # Mapear para nova fila
        new_level = self.queue_manager.map_risk_to_priority(new_risk_band, sla_urgency)
        new_queue = new_level.value

        # Estimar fila atual
        current_queue = self._estimate_queue_from_ticket(ticket)

        if new_queue == current_queue:
            return None

        self.logger.info(
            "ticket_reprioritized_by_risk_band",
            ticket_id=ticket_id,
            old_queue=current_queue,
            new_queue=new_queue,
            old_risk_band=old_risk_band,
            new_risk_band=new_risk_band,
        )

        return new_queue

    def reprioritize_batch(
        self, tickets: list[dict[str, Any]], reason: str = "batch_update"
    ) -> dict[str, Any]:
        """
        Reavalia prioridade de um lote de tickets.

        Args:
            tickets: Lista de tickets
            reason: Razão da re-priorização

        Returns:
            Estatísticas da re-priorização
        """
        reprioritized = []
        unchanged = []

        for ticket in tickets:
            ticket_id = ticket.get("ticket_id", "unknown")
            current_queue = self._estimate_queue_from_ticket(ticket)

            new_queue = self.reprioritize_ticket(ticket, current_queue)

            if new_queue:
                reprioritized.append(
                    {"ticket_id": ticket_id, "old_queue": current_queue, "new_queue": new_queue}
                )
            else:
                unchanged.append(ticket_id)

        self.logger.info(
            "batch_reprioritization_complete",
            reason=reason,
            total=len(tickets),
            reprioritized=len(reprioritized),
            unchanged=len(unchanged),
        )

        return {
            "total": len(tickets),
            "reprioritized": len(reprioritized),
            "unchanged": len(unchanged),
            "changes": reprioritized,
        }

    def should_reprioritize_on_sla_warning(
        self, sla_urgency: float, deadline_remaining_pct: float
    ) -> bool:
        """
        Determina se SLA warning deve disparar re-prioritização.

        Args:
            sla_urgency: Urgência SLA atual [0.0, 1.0]
            deadline_remaining_pct: % de deadline restante [0.0, 1.0]

        Returns:
            True se deve re-priorizar
        """
        # SLA urgency > 0.8 → CRITICAL
        if sla_urgency > 0.8:
            return True

        # Menos de 30% restante → re-priorizar
        return deadline_remaining_pct < 0.3

    def calculate_priority_increase(self, ticket: dict[str, Any], sla_urgency: float) -> float:
        """
        Calcula aumento de prioridade baseado em SLA urgency.

        Args:
            ticket: Execution ticket
            sla_urgency: Nova urgência SLA

        Returns:
            Ajuste de prioridade a aplicar
        """
        base_score = self.priority_calculator.calculate_priority_score(ticket)

        # Ajuste baseado em urgência
        if sla_urgency > 0.9:
            # Crítico - boost significativo
            adjustment = 0.3
        elif sla_urgency > 0.8:
            # Alta urgência - boost moderado
            adjustment = 0.2
        elif sla_urgency > 0.6:
            # Urgência média - pequeno boost
            adjustment = 0.1
        else:
            # Sem ajuste
            adjustment = 0.0

        new_score = min(base_score + adjustment, 1.0)

        self.logger.debug(
            "priority_increase_calculated",
            ticket_id=ticket.get("ticket_id", "unknown"),
            base_score=base_score,
            sla_urgency=sla_urgency,
            adjustment=adjustment,
            new_score=new_score,
        )

        return new_score

    def _estimate_score_from_queue(self, queue_name: str) -> float:
        """
        Estima priority_score baseado na fila.

        Args:
            queue_name: Nome da fila

        Returns:
            Score estimado
        """
        queue_scores = {"CRITICAL": 0.95, "HIGH": 0.75, "NORMAL": 0.55, "LOW": 0.25}
        return queue_scores.get(queue_name.upper(), 0.5)

    def _estimate_queue_from_ticket(self, ticket: dict[str, Any]) -> str:
        """
        Estima fila atual do ticket baseado em seus atributos.

        Args:
            ticket: Execution ticket

        Returns:
            Nome da fila estimada
        """
        risk_band = ticket.get("risk_band", "normal").lower()
        sla = ticket.get("sla", {})
        sla_urgency = sla.get("urgency", 0.0)

        # Mesma lógica de mapeamento do PriorityQueues
        if risk_band == "critical" or (risk_band == "high" and sla_urgency > 0.8):
            return "CRITICAL"
        if risk_band == "high" or sla_urgency > 0.5:
            return "HIGH"
        if risk_band == "low":
            return "LOW"
        return "NORMAL"

    def _map_score_to_queue(self, score: float) -> str:
        """
        Mapea priority_score para nome de fila.

        Args:
            score: Priority score [0.0, 1.0]

        Returns:
            Nome da fila
        """
        if score >= 0.9:
            return "CRITICAL"
        if score >= 0.7:
            return "HIGH"
        if score >= 0.4:
            return "NORMAL"
        return "LOW"
