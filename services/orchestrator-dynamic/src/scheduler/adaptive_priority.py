"""
AdaptivePriorityCalculator - Ajuste dinâmico de prioridade baseado em histórico.

Ajusta prioridade de tickets considerando histórico de execução:
- Tempo médio de execução
- Taxa de falha
- Consumo de recursos
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from neural_hive_domain import UTC
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AdaptivePriorityCalculator:
    """
    Calcula ajustes adaptativos de prioridade.

    Considera histórico de execução dos últimos 7 dias para
    ajustar a prioridade baseada em:
    - Tempo de execução médio vs esperado
    - Taxa de falha
    - Consumo de recursos
    """

    # Janela de histórico (dias)
    HISTORY_WINDOW_DAYS = 7

    # Thresholds para ajuste
    EXECUTION_TIME_THRESHOLD = 1.5  # 1.5x do esperado → aumentar prioridade
    FAILURE_RATE_THRESHOLD = 0.20  # 20% de falha → diminuir prioridade

    # Fatores de ajuste
    PRIORITY_BOOST_FACTOR = 0.15  # +15% para tickets lentos
    PRIORITY_PENALTY_FACTOR = 0.10  # -10% para tickets com muitas falhas

    def __init__(self, config=None):
        """
        Inicializa o calculador adaptativo.

        Args:
            config: Configurações (opcional)
        """
        self.config = config
        self.logger = logger.bind(component="adaptive_priority")

        # Histórico de execuções (em produção, viria do MongoDB/Redis)
        self.execution_history: dict[str, list[dict[str, Any]]] = defaultdict(list)

        # Configurações customizáveis
        self.history_window_days = getattr(
            config, "adaptive_history_window_days", self.HISTORY_WINDOW_DAYS
        )

        self.execution_time_threshold = getattr(
            config, "adaptive_execution_time_threshold", self.EXECUTION_TIME_THRESHOLD
        )

        self.failure_rate_threshold = getattr(
            config, "adaptive_failure_rate_threshold", self.FAILURE_RATE_THRESHOLD
        )

        self.enabled = getattr(config, "adaptive_priority_enabled", True)

    def calculate_adaptive_adjustment(self, ticket: dict[str, Any]) -> float:
        """
        Calcula ajuste adaptativo de prioridade.

        Args:
            ticket: Execution ticket

        Returns:
            Ajuste a aplicar na prioridade base [-0.2, +0.2]
            Valores positivos aumentam prioridade, negativos diminuem
        """
        if not self.enabled:
            return 0.0

        ticket_id = ticket.get("ticket_id", "unknown")
        ticket_type = self._get_ticket_type(ticket)

        # Obter histórico deste tipo de ticket
        history = self._get_recent_history(ticket_type)

        if not history:
            self.logger.debug(
                "adaptive_priority_no_history", ticket_id=ticket_id, ticket_type=ticket_type
            )
            return 0.0

        # Calcular fatores
        execution_time_factor = self._calculate_execution_time_factor(history, ticket)
        failure_rate_factor = self._calculate_failure_rate_factor(history)
        resource_factor = self._calculate_resource_factor(history)

        # Combinar fatores
        total_adjustment = execution_time_factor + failure_rate_factor + resource_factor

        # Limitar ajuste
        total_adjustment = max(min(total_adjustment, 0.2), -0.2)

        self.logger.debug(
            "adaptive_priority_calculated",
            ticket_id=ticket_id,
            ticket_type=ticket_type,
            execution_time_factor=execution_time_factor,
            failure_rate_factor=failure_rate_factor,
            resource_factor=resource_factor,
            total_adjustment=total_adjustment,
        )

        return total_adjustment

    def _get_ticket_type(self, ticket: dict[str, Any]) -> str:
        """
        Identifica tipo do ticket para agrupar histórico.

        Args:
            ticket: Execution ticket

        Returns:
            Tipo do ticket (para agrupamento de histórico)
        """
        # Usar task_type ou action como tipo
        task_type = ticket.get("task_type")
        if task_type:
            return task_type

        action = ticket.get("action", "")
        if action:
            return action

        # Fallback: usar risk_band
        return f"risk_{ticket.get('risk_band', 'normal')}"

    def _get_recent_history(self, ticket_type: str) -> list[dict[str, Any]]:
        """
        Obtém histórico recente de um tipo de ticket.

        Args:
            ticket_type: Tipo do ticket

        Returns:
            Lista de execuções recentes
        """
        history = self.execution_history.get(ticket_type, [])

        # Filtrar por janela de tempo
        cutoff = datetime.now(UTC) - timedelta(days=self.history_window_days)

        return [
            entry
            for entry in history
            if datetime.fromtimestamp(entry.get("timestamp", 0) / 1000, UTC) > cutoff
        ]

    def _calculate_execution_time_factor(
        self, history: list[dict[str, Any]], ticket: dict[str, Any]
    ) -> float:
        """
        Calcula fator de ajuste baseado em tempo de execução.

        Args:
            history: Histórico de execuções
            ticket: Ticket atual

        Returns:
            Ajuste de prioridade baseado em tempo de execução
        """
        if not history:
            return 0.0

        # Calcular tempo médio de execução
        execution_times = [
            entry.get("execution_time_ms", 0)
            for entry in history
            if entry.get("execution_time_ms", 0) > 0
        ]

        if not execution_times:
            return 0.0

        avg_execution_time = sum(execution_times) / len(execution_times)

        # Obter tempo esperado do ticket
        expected_time_ms = ticket.get("sla", {}).get("timeout_ms", 300000)  # 5 min default

        # Calcular razão
        if expected_time_ms == 0:
            return 0.0

        time_ratio = avg_execution_time / expected_time_ms

        # Se tempo médio > threshold, aumentar prioridade
        if time_ratio > self.execution_time_threshold:
            # Ajuste proporcional ao excesso
            excess = (time_ratio - self.execution_time_threshold) / self.execution_time_threshold
            adjustment = excess * self.PRIORITY_BOOST_FACTOR
            return min(adjustment, self.PRIORITY_BOOST_FACTOR)

        return 0.0

    def _calculate_failure_rate_factor(self, history: list[dict[str, Any]]) -> float:
        """
        Calcula fator de ajuste baseado em taxa de falha.

        Args:
            history: Histórico de execuções

        Returns:
            Ajuste de prioridade (penalidade por alta taxa de falha)
        """
        if not history:
            return 0.0

        # Contar falhas
        failures = sum(1 for entry in history if entry.get("status") == "FAILED")

        failure_rate = failures / len(history)

        # Se taxa de falha > threshold, diminuir prioridade
        if failure_rate > self.failure_rate_threshold:
            # Penalidade proporcional ao excesso
            excess = (failure_rate - self.failure_rate_threshold) / self.failure_rate_threshold
            penalty = excess * self.PRIORITY_PENALTY_FACTOR
            return -min(penalty, self.PRIORITY_PENALTY_FACTOR)

        return 0.0

    def _calculate_resource_factor(self, history: list[dict[str, Any]]) -> float:
        """
        Calcula fator de ajuste baseado em consumo de recursos.

        Args:
            history: Histórico de execuções

        Returns:
            Ajuste de prioridade baseado em recursos
        """
        if not history:
            return 0.0

        # Calcular consumo médio de recursos
        resource_usages = [
            entry.get("resource_usage", 0.5)
            for entry in history
            if entry.get("resource_usage") is not None
        ]

        if not resource_usages:
            return 0.0

        avg_resource_usage = sum(resource_usages) / len(resource_usages)

        # Se consumo muito alto, pode diminuir prioridade (para não sobrecarregar)
        # Se consumo muito baixo, pode aumentar (tickets leves primeiro)
        if avg_resource_usage > 0.8:
            return -0.05  # Penalidade leve para tickets pesados
        if avg_resource_usage < 0.3:
            return 0.03  # Pequeno boost para tickets leves

        return 0.0

    def record_execution(
        self,
        ticket: dict[str, Any],
        execution_time_ms: int,
        status: str,
        resource_usage: float | None = None,
    ):
        """
        Registra execução de um ticket no histórico.

        Args:
            ticket: Execution ticket
            execution_time_ms: Tempo de execução em ms
            status: Status da execução (COMPLETED/FAILED)
            resource_usage: Uso de recursos [0.0, 1.0] (opcional)
        """
        ticket_type = self._get_ticket_type(ticket)
        ticket_id = ticket.get("ticket_id", "unknown")

        entry = {
            "ticket_id": ticket_id,
            "timestamp": self._get_timestamp(),
            "execution_time_ms": execution_time_ms,
            "status": status,
            "resource_usage": resource_usage,
        }

        self.execution_history[ticket_type].append(entry)

        self.logger.debug(
            "adaptive_priority_execution_recorded",
            ticket_id=ticket_id,
            ticket_type=ticket_type,
            execution_time_ms=execution_time_ms,
            status=status,
        )

    def _get_timestamp(self) -> int:
        """Retorna timestamp atual em milissegundos."""
        return int(datetime.now(UTC).timestamp() * 1000)

    def get_history_statistics(self) -> dict[str, Any]:
        """
        Retorna estatísticas do histórico.

        Returns:
            Dict com estatísticas agregadas
        """
        total_entries = sum(len(entries) for entries in self.execution_history.values())

        # Contar por status
        completed = sum(
            sum(1 for e in entries if e.get("status") == "COMPLETED")
            for entries in self.execution_history.values()
        )
        failed = sum(
            sum(1 for e in entries if e.get("status") == "FAILED")
            for entries in self.execution_history.values()
        )

        # Calcular tempo médio geral
        all_times = []
        for entries in self.execution_history.values():
            all_times.extend(
                e.get("execution_time_ms", 0) for e in entries if e.get("execution_time_ms", 0) > 0
            )

        avg_execution_time = sum(all_times) / len(all_times) if all_times else 0

        return {
            "total_entries": total_entries,
            "ticket_types": len(self.execution_history),
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / total_entries * 100, 1) if total_entries > 0 else 0,
            "avg_execution_time_ms": round(avg_execution_time, 0),
        }

    def clear_old_history(self, days: int | None = None):
        """
        Limpa entradas antigas do histórico.

        Args:
            days: Dias de retenção (default: history_window_days)
        """
        retention_days = days or self.history_window_days
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        cutoff_ms = int(cutoff.timestamp() * 1000)

        removed = 0
        for ticket_type, entries in self.execution_history.items():
            original_len = len(entries)
            self.execution_history[ticket_type] = [
                e for e in entries if e.get("timestamp", 0) > cutoff_ms
            ]
            removed += original_len - len(self.execution_history[ticket_type])

        self.logger.info(
            "adaptive_priority_history_cleaned",
            entries_removed=removed,
            retention_days=retention_days,
        )
