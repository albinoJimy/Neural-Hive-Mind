"""
QueueManager - Gerenciador central de filas de prioridade.

Coordena multiple priority queues e fornece interface unificada
para enqueue/dequeue de tickets com priorização automática.
"""

from typing import Any

import structlog

from src.config.settings import OrchestratorSettings
from src.scheduler.priority_calculator import PriorityCalculator
from src.scheduler.priority_queues import PriorityLevel, PriorityQueues

logger = structlog.get_logger(__name__)


class QueueManager:
    """
    Gerenciador central de filas de prioridade.

    Responsabilidades:
    - Gerenciar multiple priority queues
    - Integrar com PriorityCalculator para priorização automática
    - Fornecer interface simplificada para enqueue/dequeue
    - Coordenar weighted round-robin entre filas
    """

    def __init__(self, config: OrchestratorSettings):
        """
        Inicializa o gerenciador de filas.

        Args:
            config: Configurações do orchestrator
        """
        self.config = config
        self.priority_queues = PriorityQueues()
        self.priority_calculator = PriorityCalculator(config)
        self.logger = logger.bind(component="queue_manager")

    def enqueue_ticket(self, ticket: dict[str, Any], priority_score: float | None = None) -> str:
        """
        Enfileira ticket calculando prioridade automaticamente.

        Args:
            ticket: Execution ticket
            priority_score: Score pré-calculado (opcional, será calculado se omitido)

        Returns:
            Nome da fila onde o ticket foi enfileirado
        """
        # Calcular priority_score se não fornecido
        if priority_score is None:
            priority_score = self.priority_calculator.calculate_priority_score(ticket)

        # Enfileirar
        queue_name = self.priority_queues.enqueue(ticket, priority_score)

        self.logger.info(
            "ticket_enqueued",
            ticket_id=ticket.get("ticket_id", "unknown"),
            queue=queue_name,
            priority_score=priority_score,
        )

        return queue_name

    async def get_next_ticket(self, queue_name: str | None = None) -> dict[str, Any] | None:
        """
        Retorna próximo ticket usando weighted round-robin.

        Args:
            queue_name: Nome da fila específica (opcional)

        Returns:
            Próximo ticket ou None se todas as filas vazias
        """
        ticket = await self.priority_queues.dequeue(queue_name)

        if ticket:
            self.logger.info(
                "next_ticket_retrieved",
                ticket_id=ticket.get("ticket_id", "unknown"),
                queue=queue_name or "round_robin",
            )

        return ticket

    def peek_queue(self, queue_name: str) -> dict[str, Any] | None:
        """
        Retorna próximo ticket de uma fila sem remover.

        Args:
            queue_name: Nome da fila

        Returns:
            Próximo ticket ou None se fila vazia
        """
        return self.priority_queues.peek(queue_name)

    def get_queue_sizes(self) -> dict[str, int]:
        """
        Retorna tamanho de todas as filas.

        Returns:
            Dict com tamanho de cada fila
        """
        return self.priority_queues.get_all_sizes()

    def get_queue_size(self, queue_name: str) -> int:
        """
        Retorna tamanho de uma fila específica.

        Args:
            queue_name: Nome da fila

        Returns:
            Número de tickets na fila
        """
        return self.priority_queues.get_queue_size(queue_name)

    def clear_queue(self, queue_name: str) -> int:
        """
        Limpa todos os tickets de uma fila.

        Args:
            queue_name: Nome da fila

        Returns:
            Número de tickets removidos
        """
        return self.priority_queues.clear_queue(queue_name)

    def has_pending_tickets(self) -> bool:
        """
        Verifica se há tickets pendentes em qualquer fila.

        Returns:
            True se há tickets pendentes
        """
        return self.priority_queues.has_pending_tickets()

    def get_total_pending(self) -> int:
        """
        Retorna total de tickets pendentes em todas as filas.

        Returns:
            Soma de tickets em todas as filas
        """
        return self.priority_queues.get_total_pending()

    def calculate_priority(self, ticket: dict[str, Any]) -> float:
        """
        Calcula priority_score para um ticket.

        Args:
            ticket: Execution ticket

        Returns:
            Priority score [0.0, 1.0]
        """
        return self.priority_calculator.calculate_priority_score(ticket)

    def map_risk_to_priority(self, risk_band: str, sla_urgency: float = 0.0) -> PriorityLevel:
        """
        Mapeia risk_band e sla_urgency para PriorityLevel.

        Args:
            risk_band: Banda de risco
            sla_urgency: Urgência SLA

        Returns:
            PriorityLevel correspondente
        """
        return self.priority_queues.map_risk_band_to_queue(risk_band, sla_urgency)

    def enqueue_by_risk(
        self, ticket: dict[str, Any], risk_band: str, sla_urgency: float = 0.0
    ) -> str:
        """
        Enfileira ticket baseado em risk_band e sla_urgency.

        Método alternativo que não usa PriorityCalculator,
        mapeando diretamente risk_band para fila.

        Args:
            ticket: Execution ticket
            risk_band: Banda de risco
            sla_urgency: Urgência SLA (default 0.0)

        Returns:
            Nome da fila onde o ticket foi enfileirado
        """
        # Mapear para PriorityLevel
        level = self.priority_queues.map_risk_band_to_queue(risk_band, sla_urgency)

        # Enfileirar diretamente
        self.priority_queues.queues[level].append(ticket)

        self.logger.info(
            "ticket_enqueued_by_risk",
            ticket_id=ticket.get("ticket_id", "unknown"),
            queue=level.value,
            risk_band=risk_band,
            sla_urgency=sla_urgency,
        )

        return level.value

    def get_queue_statistics(self) -> dict[str, Any]:
        """
        Retorna estatísticas detalhadas das filas.

        Returns:
            Dict com estatísticas de todas as filas
        """
        sizes = self.get_queue_sizes()
        total = self.get_total_pending()

        return {
            "total_pending": total,
            "queues": {
                "CRITICAL": {
                    "size": sizes.get("CRITICAL", 0),
                    "percentage": (
                        round(sizes.get("CRITICAL", 0) / total * 100, 1) if total > 0 else 0
                    ),
                },
                "HIGH": {
                    "size": sizes.get("HIGH", 0),
                    "percentage": round(sizes.get("HIGH", 0) / total * 100, 1) if total > 0 else 0,
                },
                "NORMAL": {
                    "size": sizes.get("NORMAL", 0),
                    "percentage": (
                        round(sizes.get("NORMAL", 0) / total * 100, 1) if total > 0 else 0
                    ),
                },
                "LOW": {
                    "size": sizes.get("LOW", 0),
                    "percentage": round(sizes.get("LOW", 0) / total * 100, 1) if total > 0 else 0,
                },
            },
            "weights": {"CRITICAL": 4, "HIGH": 3, "NORMAL": 2, "LOW": 1},
        }
