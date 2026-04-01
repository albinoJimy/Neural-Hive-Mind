"""
PriorityQueues - Implementação de filas por prioridade com weighted round-robin.

Fornece 4 níveis de prioridade: CRITICAL, HIGH, NORMAL, LOW.
Utiliza weighted round-robin para dequeue: CRITICAL=4, HIGH=3, NORMAL=2, LOW=1.
"""

import asyncio
from collections import deque
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PriorityLevel(Enum):
    """Níveis de prioridade suportados."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class PriorityQueues:
    """
    Gerenciador de filas por prioridade com weighted round-robin.

    Características:
    - 4 níveis de prioridade (CRITICAL, HIGH, NORMAL, LOW)
    - Weighted round-robin para dequeue balanceado
    - Thread-safe para uso com asyncio
    - Métodos para inspeção e gestão das filas
    """

    # Pesos para weighted round-robin
    QUEUE_WEIGHTS = {
        PriorityLevel.CRITICAL: 4,
        PriorityLevel.HIGH: 3,
        PriorityLevel.NORMAL: 2,
        PriorityLevel.LOW: 1,
    }

    def __init__(self):
        """Inicializa as filas de prioridade."""
        self.queues: dict[PriorityLevel, deque] = {level: deque() for level in PriorityLevel}
        self._round_robin_counters: dict[PriorityLevel, int] = dict.fromkeys(PriorityLevel, 0)
        self._lock = asyncio.Lock()
        self.logger = logger.bind(component="priority_queues")

    def enqueue(self, ticket: dict[str, Any], priority_score: float) -> str:
        """
        Adiciona ticket à fila apropriada baseado no priority_score.

        Mapeamento de prioridade:
        - CRITICAL: score >= 0.9
        - HIGH: score >= 0.7
        - NORMAL: score >= 0.4 (default)
        - LOW: score < 0.4

        Args:
            ticket: Execution ticket
            priority_score: Score calculado pelo PriorityCalculator [0.0, 1.0]

        Returns:
            Nome da fila onde o ticket foi enfileirado
        """
        queue_name = self._map_score_to_queue(priority_score)

        # Enfileirar
        self.queues[queue_name].append(ticket)

        self.logger.debug(
            "ticket_enqueued",
            ticket_id=ticket.get("ticket_id", "unknown"),
            queue=queue_name.value,
            priority_score=priority_score,
            queue_size=len(self.queues[queue_name]),
        )

        return queue_name.value

    def _map_score_to_queue(self, priority_score: float) -> PriorityLevel:
        """
        Mapeia priority_score para PriorityLevel.

        Args:
            priority_score: Score calculado [0.0, 1.0]

        Returns:
            PriorityLevel correspondente
        """
        if priority_score >= 0.9:
            return PriorityLevel.CRITICAL
        if priority_score >= 0.7:
            return PriorityLevel.HIGH
        if priority_score >= 0.4:
            return PriorityLevel.NORMAL
        return PriorityLevel.LOW

    def map_risk_band_to_queue(self, risk_band: str, sla_urgency: float = 0.0) -> PriorityLevel:
        """
        Mapeia risk_band e sla_urgency diretamente para PriorityLevel.

        Método alternativo de mapeamento que considera risk_band e urgência SLA.

        Args:
            risk_band: Banda de risco (critical/high/normal/low)
            sla_urgency: Urgência SLA [0.0, 1.0]

        Returns:
            PriorityLevel correspondente
        """
        risk_band_lower = risk_band.lower() if isinstance(risk_band, str) else "normal"

        # CRITICAL: risk='critical' ou (risk='high' e sla_urgency > 0.8)
        if risk_band_lower == "critical" or (risk_band_lower == "high" and sla_urgency > 0.8):
            return PriorityLevel.CRITICAL
        # HIGH: risk='high' ou sla_urgency > 0.5
        if risk_band_lower == "high" or sla_urgency > 0.5:
            return PriorityLevel.HIGH
        # LOW: risk='low'
        if risk_band_lower == "low":
            return PriorityLevel.LOW
        # NORMAL: default
        return PriorityLevel.NORMAL

    async def dequeue(self, queue_name: str | None = None) -> dict[str, Any] | None:
        """
        Remove próximo ticket usando weighted round-robin.

        Se queue_name for especificado, retira dessa fila específica.
        Caso contrário, usa weighted round-robin para selecionar a fila.

        Args:
            queue_name: Nome da fila específica (opcional)

        Returns:
            Ticket removido ou None se todas as filas vazias
        """
        async with self._lock:
            if queue_name:
                # Dequeue de fila específica
                level = self._parse_queue_name(queue_name)
                if self.queues[level]:
                    ticket = self.queues[level].popleft()
                    self.logger.debug(
                        "ticket_dequeued",
                        ticket_id=ticket.get("ticket_id", "unknown"),
                        queue=level.value,
                    )
                    return ticket
                return None

            # Weighted round-robin para selecionar próxima fila
            return self._dequeue_round_robin()

    def _dequeue_round_robin(self) -> dict[str, Any] | None:
        """
        Implementa weighted round-robin para dequeue.

        Algoritmo:
        1. Iterar por níveis em ordem de prioridade (CRITICAL -> LOW)
        2. Para cada nível, verificar se counter < weight
        3. Se sim, incrementar counter e tentar dequeue
        4. Se counter >= weight ou fila vazia, resetar counter e continuar
        5. Se todas as filas vazias, retornar None

        Returns:
            Ticket removido ou None
        """
        for level in PriorityLevel:
            weight = self.QUEUE_WEIGHTS[level]
            counter = self._round_robin_counters[level]

            # Verificar se ainda pode selecionar esta fila neste ciclo
            if counter < weight and self.queues[level]:
                # Incrementar counter
                self._round_robin_counters[level] += 1

                # Dequeue
                ticket = self.queues[level].popleft()

                self.logger.debug(
                    "ticket_dequeued_round_robin",
                    ticket_id=ticket.get("ticket_id", "unknown"),
                    queue=level.value,
                    counter=self._round_robin_counters[level],
                    weight=weight,
                )

                return ticket
            # Reset counter e continuar para próxima fila
            self._round_robin_counters[level] = 0

        # Todos os contadores resetados, tentar novamente (início de novo ciclo)
        for level in PriorityLevel:
            if self.queues[level]:
                self._round_robin_counters[level] = 1
                ticket = self.queues[level].popleft()

                self.logger.debug(
                    "ticket_dequeued_new_cycle",
                    ticket_id=ticket.get("ticket_id", "unknown"),
                    queue=level.value,
                )

                return ticket

        return None

    def peek(self, queue_name: str) -> dict[str, Any] | None:
        """
        Retorna próximo ticket de uma fila sem remover.

        Args:
            queue_name: Nome da fila

        Returns:
            Próximo ticket ou None se fila vazia
        """
        level = self._parse_queue_name(queue_name)

        if self.queues[level]:
            return self.queues[level][0]

        return None

    def get_queue_size(self, queue_name: str) -> int:
        """
        Retorna tamanho de uma fila específica.

        Args:
            queue_name: Nome da fila

        Returns:
            Número de tickets na fila
        """
        level = self._parse_queue_name(queue_name)
        return len(self.queues[level])

    def get_all_sizes(self) -> dict[str, int]:
        """
        Retorna tamanho de todas as filas.

        Returns:
            Dict com tamanho de cada fila
        """
        return {level.value: len(self.queues[level]) for level in PriorityLevel}

    def clear_queue(self, queue_name: str) -> int:
        """
        Limpa todos os tickets de uma fila.

        Args:
            queue_name: Nome da fila

        Returns:
            Número de tickets removidos
        """
        level = self._parse_queue_name(queue_name)
        size = len(self.queues[level])
        self.queues[level].clear()

        self.logger.info("queue_cleared", queue=level.value, tickets_removed=size)

        return size

    def has_pending_tickets(self) -> bool:
        """
        Verifica se há tickets pendentes em qualquer fila.

        Returns:
            True se há tickets pendentes
        """
        return any(len(q) > 0 for q in self.queues.values())

    def get_total_pending(self) -> int:
        """
        Retorna total de tickets pendentes em todas as filas.

        Returns:
            Soma de tickets em todas as filas
        """
        return sum(len(q) for q in self.queues.values())

    def _parse_queue_name(self, queue_name: str) -> PriorityLevel:
        """
        Parse nome da fila para PriorityLevel.

        Args:
            queue_name: Nome da fila (string ou PriorityLevel)

        Returns:
            PriorityLevel correspondente

        Raises:
            ValueError: Se queue_name inválido
        """
        if isinstance(queue_name, PriorityLevel):
            return queue_name

        try:
            return PriorityLevel(queue_name.upper())
        except ValueError:
            valid_levels = [level.value for level in PriorityLevel]
            raise ValueError(
                f"Invalid queue_name: {queue_name}. " f"Must be one of: {valid_levels}"
            )

    def reset_counters(self):
        """Reset todos os contadores de round-robin."""
        self._round_robin_counters = dict.fromkeys(PriorityLevel, 0)
        self.logger.debug("round_robin_counters_reset")
