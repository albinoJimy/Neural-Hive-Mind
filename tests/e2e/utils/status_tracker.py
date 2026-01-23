"""Rastreador de transições de status para testes E2E do Fluxo C.

Fornece funcionalidades para monitorar e validar transições de status
de tickets durante a execução do fluxo de orquestração.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TicketStatus(str, Enum):
    """Status possíveis de um ticket de execução."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Transições de status válidas
VALID_TRANSITIONS: Dict[TicketStatus, Set[TicketStatus]] = {
    TicketStatus.PENDING: {TicketStatus.RUNNING, TicketStatus.FAILED, TicketStatus.CANCELLED},
    TicketStatus.RUNNING: {TicketStatus.COMPLETED, TicketStatus.FAILED, TicketStatus.CANCELLED},
    TicketStatus.COMPLETED: set(),  # Estado final
    TicketStatus.FAILED: set(),  # Estado final
    TicketStatus.CANCELLED: set(),  # Estado final
}


@dataclass
class StatusTransition:
    """Representa uma transição de status."""

    from_status: Optional[str]
    to_status: str
    timestamp: datetime
    duration_ms: Optional[int] = None


@dataclass
class TicketStatusHistory:
    """Histórico de status de um ticket."""

    ticket_id: str
    transitions: List[StatusTransition] = field(default_factory=list)
    current_status: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    def add_transition(self, new_status: str) -> None:
        """Adiciona uma transição ao histórico."""
        now = datetime.utcnow()

        if self.first_seen is None:
            self.first_seen = now

        duration_ms = None
        if self.last_updated:
            duration_ms = int((now - self.last_updated).total_seconds() * 1000)

        transition = StatusTransition(
            from_status=self.current_status,
            to_status=new_status,
            timestamp=now,
            duration_ms=duration_ms,
        )
        self.transitions.append(transition)
        self.current_status = new_status
        self.last_updated = now

    def get_status_sequence(self) -> List[str]:
        """Retorna sequência de status observados."""
        return [t.to_status for t in self.transitions]

    def total_duration_ms(self) -> Optional[int]:
        """Retorna duração total desde primeira observação."""
        if self.first_seen and self.last_updated:
            return int((self.last_updated - self.first_seen).total_seconds() * 1000)
        return None


class TicketStatusTracker:
    """Rastreador de status de tickets para testes E2E.

    Permite monitorar transições de status em tempo real consultando
    MongoDB e PostgreSQL periodicamente.
    """

    def __init__(
        self,
        mongodb_helper=None,
        postgresql_helper=None,
        poll_interval_seconds: float = 1.0,
    ):
        """
        Inicializa o rastreador.

        Args:
            mongodb_helper: MongoDBTestHelper para consultar MongoDB
            postgresql_helper: PostgreSQLTicketsHelper para consultar PostgreSQL
            poll_interval_seconds: Intervalo entre consultas
        """
        self.mongodb_helper = mongodb_helper
        self.postgresql_helper = postgresql_helper
        self.poll_interval = poll_interval_seconds
        self._tracked_tickets: Dict[str, TicketStatusHistory] = {}
        self._tracking_tasks: Dict[str, asyncio.Task] = {}

    def track_ticket(self, ticket_id: str) -> None:
        """Inicia rastreamento de um ticket."""
        if ticket_id not in self._tracked_tickets:
            self._tracked_tickets[ticket_id] = TicketStatusHistory(ticket_id=ticket_id)
            logger.info(f"Iniciado rastreamento do ticket {ticket_id}")

    def stop_tracking(self, ticket_id: str) -> None:
        """Para rastreamento de um ticket."""
        if ticket_id in self._tracking_tasks:
            task = self._tracking_tasks.pop(ticket_id)
            task.cancel()
            logger.info(f"Parado rastreamento do ticket {ticket_id}")

    async def _query_ticket_status(self, ticket_id: str) -> Optional[str]:
        """Consulta status atual do ticket."""
        # Tentar PostgreSQL primeiro (fonte primária)
        if self.postgresql_helper:
            try:
                tickets = self.postgresql_helper.get_tickets_for_plan(ticket_id[:36])
                for ticket in tickets:
                    if ticket.get("ticket_id") == ticket_id:
                        return ticket.get("status")

                # Busca direta por ticket_id
                query = "SELECT status FROM execution_tickets WHERE ticket_id = %s"
                result = self.postgresql_helper.execute_query(query, (ticket_id,))
                if result:
                    return result[0].get("status")
            except Exception as e:
                logger.debug(f"PostgreSQL query falhou: {e}")

        # Fallback para MongoDB
        if self.mongodb_helper:
            try:
                docs = self.mongodb_helper.find_documents(
                    "execution_tickets_ledger",
                    {"ticket_id": ticket_id},
                    limit=1,
                )
                if docs:
                    return docs[0].get("status")
            except Exception as e:
                logger.debug(f"MongoDB query falhou: {e}")

        return None

    async def wait_for_status(
        self,
        ticket_id: str,
        expected_status: str,
        timeout_seconds: int = 60,
    ) -> bool:
        """
        Aguarda ticket atingir status esperado.

        Args:
            ticket_id: ID do ticket
            expected_status: Status esperado (PENDING, RUNNING, COMPLETED, FAILED)
            timeout_seconds: Timeout máximo em segundos

        Returns:
            True se status foi atingido, False se timeout
        """
        self.track_ticket(ticket_id)
        history = self._tracked_tickets[ticket_id]
        start_time = time.time()

        logger.info(
            f"Aguardando ticket {ticket_id} atingir status {expected_status}"
        )

        while time.time() - start_time < timeout_seconds:
            current_status = await self._query_ticket_status(ticket_id)

            if current_status and current_status != history.current_status:
                history.add_transition(current_status)
                logger.info(
                    f"Ticket {ticket_id}: {history.current_status}"
                )

            if current_status == expected_status:
                logger.info(
                    f"Ticket {ticket_id} atingiu status {expected_status} "
                    f"em {int((time.time() - start_time) * 1000)}ms"
                )
                return True

            await asyncio.sleep(self.poll_interval)

        logger.warning(
            f"Timeout aguardando ticket {ticket_id} atingir {expected_status}. "
            f"Status atual: {history.current_status}"
        )
        return False

    async def wait_for_any_status(
        self,
        ticket_id: str,
        expected_statuses: List[str],
        timeout_seconds: int = 60,
    ) -> Optional[str]:
        """
        Aguarda ticket atingir qualquer um dos status esperados.

        Args:
            ticket_id: ID do ticket
            expected_statuses: Lista de status válidos
            timeout_seconds: Timeout máximo

        Returns:
            Status atingido ou None se timeout
        """
        self.track_ticket(ticket_id)
        history = self._tracked_tickets[ticket_id]
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            current_status = await self._query_ticket_status(ticket_id)

            if current_status and current_status != history.current_status:
                history.add_transition(current_status)

            if current_status in expected_statuses:
                return current_status

            await asyncio.sleep(self.poll_interval)

        return None

    def get_status_history(self, ticket_id: str) -> Optional[TicketStatusHistory]:
        """Retorna histórico de status de um ticket."""
        return self._tracked_tickets.get(ticket_id)

    def validate_status_sequence(
        self,
        ticket_id: str,
        expected_sequence: List[str],
    ) -> bool:
        """
        Valida se sequência de status observada corresponde à esperada.

        Args:
            ticket_id: ID do ticket
            expected_sequence: Sequência esperada de status

        Returns:
            True se sequência é válida
        """
        history = self._tracked_tickets.get(ticket_id)
        if not history:
            logger.warning(f"Ticket {ticket_id} não está sendo rastreado")
            return False

        actual_sequence = history.get_status_sequence()

        if actual_sequence == expected_sequence:
            return True

        # Verificar se sequência atual é prefixo válido da esperada
        if len(actual_sequence) <= len(expected_sequence):
            for i, status in enumerate(actual_sequence):
                if status != expected_sequence[i]:
                    logger.warning(
                        f"Sequência inválida no índice {i}: "
                        f"esperado {expected_sequence[i]}, obtido {status}"
                    )
                    return False
            return True

        logger.warning(
            f"Sequência observada ({actual_sequence}) não corresponde "
            f"à esperada ({expected_sequence})"
        )
        return False

    def validate_transitions(self, ticket_id: str) -> Dict[str, Any]:
        """
        Valida se todas as transições do ticket são válidas.

        Args:
            ticket_id: ID do ticket

        Returns:
            Dict com resultado da validação
        """
        history = self._tracked_tickets.get(ticket_id)
        if not history:
            return {"valid": False, "error": "Ticket não rastreado"}

        invalid_transitions = []
        for transition in history.transitions:
            if transition.from_status:
                from_status = TicketStatus(transition.from_status)
                to_status = TicketStatus(transition.to_status)
                valid_next = VALID_TRANSITIONS.get(from_status, set())
                if to_status not in valid_next:
                    invalid_transitions.append({
                        "from": transition.from_status,
                        "to": transition.to_status,
                        "timestamp": transition.timestamp.isoformat(),
                    })

        return {
            "valid": len(invalid_transitions) == 0,
            "ticket_id": ticket_id,
            "total_transitions": len(history.transitions),
            "sequence": history.get_status_sequence(),
            "invalid_transitions": invalid_transitions,
            "total_duration_ms": history.total_duration_ms(),
        }

    async def track_multiple_tickets(
        self,
        ticket_ids: List[str],
        expected_final_status: str,
        timeout_seconds: int = 180,
    ) -> Dict[str, Any]:
        """
        Rastreia múltiplos tickets até atingirem status final.

        Args:
            ticket_ids: Lista de IDs de tickets
            expected_final_status: Status final esperado
            timeout_seconds: Timeout total

        Returns:
            Dict com resultado consolidado
        """
        for ticket_id in ticket_ids:
            self.track_ticket(ticket_id)

        start_time = time.time()
        completed = set()
        final_statuses = ["COMPLETED", "FAILED", "CANCELLED"]

        while time.time() - start_time < timeout_seconds:
            for ticket_id in ticket_ids:
                if ticket_id in completed:
                    continue

                current_status = await self._query_ticket_status(ticket_id)
                history = self._tracked_tickets[ticket_id]

                if current_status and current_status != history.current_status:
                    history.add_transition(current_status)

                if current_status in final_statuses:
                    completed.add(ticket_id)

            if len(completed) == len(ticket_ids):
                break

            await asyncio.sleep(self.poll_interval)

        # Consolidar resultados
        results = {
            "total_tickets": len(ticket_ids),
            "completed": len(completed),
            "timed_out": len(ticket_ids) - len(completed),
            "success_count": 0,
            "failed_count": 0,
            "tickets": {},
        }

        for ticket_id in ticket_ids:
            history = self._tracked_tickets.get(ticket_id)
            if history:
                ticket_result = {
                    "final_status": history.current_status,
                    "sequence": history.get_status_sequence(),
                    "duration_ms": history.total_duration_ms(),
                }
                results["tickets"][ticket_id] = ticket_result

                if history.current_status == expected_final_status:
                    results["success_count"] += 1
                elif history.current_status == "FAILED":
                    results["failed_count"] += 1

        results["all_successful"] = results["success_count"] == len(ticket_ids)
        return results

    def clear_history(self, ticket_id: Optional[str] = None) -> None:
        """Limpa histórico de rastreamento."""
        if ticket_id:
            self._tracked_tickets.pop(ticket_id, None)
        else:
            self._tracked_tickets.clear()


class FlowCStatusTracker:
    """Rastreador especializado para Fluxo C (C1-C6).

    Monitora status em cada etapa do fluxo de orquestração.
    """

    def __init__(self, ticket_tracker: TicketStatusTracker):
        self.ticket_tracker = ticket_tracker
        self._step_times: Dict[str, Dict[str, datetime]] = {}

    def record_step_start(self, step_name: str) -> None:
        """Registra início de uma etapa."""
        if step_name not in self._step_times:
            self._step_times[step_name] = {}
        self._step_times[step_name]["start"] = datetime.utcnow()

    def record_step_end(self, step_name: str) -> None:
        """Registra fim de uma etapa."""
        if step_name in self._step_times:
            self._step_times[step_name]["end"] = datetime.utcnow()

    def get_step_duration_ms(self, step_name: str) -> Optional[int]:
        """Retorna duração de uma etapa em millisegundos."""
        if step_name not in self._step_times:
            return None
        times = self._step_times[step_name]
        if "start" in times and "end" in times:
            return int((times["end"] - times["start"]).total_seconds() * 1000)
        return None

    async def validate_flow_c_execution(
        self,
        ticket_ids: List[str],
        timeout_seconds: int = 300,
    ) -> Dict[str, Any]:
        """
        Valida execução completa do Fluxo C.

        Args:
            ticket_ids: IDs dos tickets gerados
            timeout_seconds: Timeout total

        Returns:
            Dict com validação de cada etapa
        """
        # C2-C4: Aguardar PENDING -> RUNNING
        self.record_step_start("C2_C4")
        running_results = await self.ticket_tracker.track_multiple_tickets(
            ticket_ids,
            "RUNNING",
            timeout_seconds=60,
        )
        self.record_step_end("C2_C4")

        # C5: Aguardar RUNNING -> COMPLETED
        self.record_step_start("C5")
        completed_results = await self.ticket_tracker.track_multiple_tickets(
            ticket_ids,
            "COMPLETED",
            timeout_seconds=timeout_seconds,
        )
        self.record_step_end("C5")

        return {
            "valid": completed_results.get("all_successful", False),
            "c2_c4_duration_ms": self.get_step_duration_ms("C2_C4"),
            "c5_duration_ms": self.get_step_duration_ms("C5"),
            "running_results": running_results,
            "completed_results": completed_results,
            "step_times": {
                k: {
                    "start": v.get("start", "").isoformat() if v.get("start") else None,
                    "end": v.get("end", "").isoformat() if v.get("end") else None,
                }
                for k, v in self._step_times.items()
            },
        }
