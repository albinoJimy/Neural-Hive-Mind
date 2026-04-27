"""
TemporalTracker - Tracking de evolução temporal de decisões.

Responsável por:
- Análise de sessão (mesmo plan_id)
- Análise de janela temporal (7d, 30d)
- Tracking de mudanças de senioridade
- Distribuição de senioridade por período

Explainability API v3 - Task 5
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

logger = structlog.get_logger(__name__)


class TemporalTracker:
    """
    Tracker para análise temporal de decisões.

    Fornece métricas e insights sobre a evolução das decisões
    ao longo do tempo, incluindo:
    - Análise de sessão (decisões do mesmo plan)
    - Análise de janela (7d, 30d)
    - Histórico de mudanças de senioridade
    """

    def __init__(self, mongo_client: AsyncIOMotorClient):
        """
        Inicializa o TemporalTracker.

        Args:
            mongo_client: Cliente MongoDB para queries
        """
        self.db = mongo_client["neural_hive"]
        self.explainability_collection = self.db.explainability_ledger
        self.seniority_collection = self.db.seniority_history
        self.logger = logger

    async def get_current_session(self, decision_id: str) -> dict[str, Any]:
        """
        Analisa decisões da mesma sessão (mesmo plan_id).

        Args:
            decision_id: ID da decisão de referência

        Returns:
            Dicionário com análise da sessão:
                - session_id: plan_id da sessão
                - decision_count: número de decisões na sessão
                - timeline: lista de decisões ordenadas
                - first_decision: primeira decisão da sessão
                - last_decision: última decisão da sessão
                - duration_hours: duração em horas
        """
        # Buscar a decisão de referência para obter o plan_id
        reference = await self.explainability_collection.find_one({"decision_id": decision_id})

        if not reference:
            self.logger.warning(
                "temporal_tracker.reference_decision_not_found", decision_id=decision_id
            )
            return {
                "session_id": None,
                "decision_count": 0,
                "timeline": [],
                "first_decision": None,
                "last_decision": None,
                "duration_hours": 0.0,
            }

        # Extrair plan_id da decisão
        plan_id = reference.get("plan_id")

        if not plan_id:
            # Se não tiver plan_id, usar o próprio decision_id como sessão
            plan_id = decision_id

        # Buscar todas as decisões do mesmo plan_id
        cursor = self.explainability_collection.find({"plan_id": plan_id}).sort("generated_at", 1)

        timeline = await self._parse_cursor(cursor)

        if not timeline:
            return {
                "session_id": plan_id,
                "decision_count": 0,
                "timeline": [],
                "first_decision": None,
                "last_decision": None,
                "duration_hours": 0.0,
            }

        # Extrair timestamps
        first_timestamp = timeline[0].get("generated_at")
        last_timestamp = timeline[-1].get("generated_at")

        # Calcular duração em horas
        duration_hours = 0.0
        if first_timestamp and last_timestamp:
            try:
                first_dt = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
                last_dt = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
                duration_hours = (last_dt - first_dt).total_seconds() / 3600
            except (ValueError, AttributeError):
                pass

        return {
            "session_id": plan_id,
            "decision_count": len(timeline),
            "timeline": timeline,
            "first_decision": timeline[0] if timeline else None,
            "last_decision": timeline[-1] if timeline else None,
            "duration_hours": round(duration_hours, 2),
        }

    async def get_window_analysis(self, days: int = 7) -> dict[str, Any]:
        """
        Analisa decisões dentro de uma janela temporal.

        Args:
            days: Número de dias para a janela (padrão: 7)

        Returns:
            Dicionário com análise da janela:
                - window_days: tamanho da janela
                - decision_count: número de decisões
                - approve_count: decisões approve
                - reject_count: decisões reject
                - approve_rate: taxa de aprovação
                - daily_breakdown: decisões por dia
        """
        # Calcular data de corte
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Buscar decisões dentro da janela
        cursor = self.explainability_collection.find(
            {"generated_at": {"$gte": since.isoformat()}}
        ).sort("generated_at", -1)

        decisions = await self._parse_cursor(cursor)

        # Contar decisões por tipo
        approve_count = 0
        reject_count = 0
        daily_breakdown: dict[str, int] = {}

        for decision in decisions:
            # Contar por tipo
            final_decision = decision.get("final_decision", {})
            decision_type = final_decision.get("decision", "unknown")

            if decision_type == "approve":
                approve_count += 1
            elif decision_type == "reject":
                reject_count += 1

            # Agrupar por dia
            generated_at = decision.get("generated_at", "")
            if generated_at:
                try:
                    dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                    day_key = dt.strftime("%Y-%m-%d")
                    daily_breakdown[day_key] = daily_breakdown.get(day_key, 0) + 1
                except (ValueError, AttributeError):
                    pass

        total = approve_count + reject_count
        approve_rate = round(approve_count / total, 3) if total > 0 else 0.0

        return {
            "window_days": days,
            "decision_count": total,
            "approve_count": approve_count,
            "reject_count": reject_count,
            "approve_rate": approve_rate,
            "daily_breakdown": daily_breakdown,
        }

    async def get_seniority_changes(self, specialists: list[str], days: int = 30) -> dict[str, Any]:
        """
        Busca mudanças de senioridade recentes para os especialistas.

        Args:
            specialists: Lista de IDs de especialistas
            days: Número de dias para buscar (padrão: 30)

        Returns:
            Dicionário com mudanças de senioridade:
                - period_days: período analisado
                - change_count: número de mudanças
                - changes: lista de mudanças com detalhes
                - specialists_with_changes: IDs com mudanças
        """
        # Calcular data de corte
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Buscar mudanças recentes
        cursor = self.seniority_collection.find(
            {"specialist_id": {"$in": specialists}, "changed_at": {"$gte": since}}
        ).sort("changed_at", -1)

        changes = await self._parse_cursor(cursor)

        # Extrair especialistas únicos com mudanças
        specialists_with_changes = list(set(c.get("specialist_id") for c in changes))

        return {
            "period_days": days,
            "change_count": len(changes),
            "changes": changes,
            "specialists_with_changes": specialists_with_changes,
        }

    async def _get_seniority_distribution(self, since: Optional[datetime] = None) -> dict[str, Any]:
        """
        Calcula distribuição de senioridade desde uma data.

        Args:
            since: Data de início (opcional, padrão: 30 dias atrás)

        Returns:
            Dicionário com distribuição por nível:
                - period_start: início do período
                - total_count: total de especialistas
                - by_level: contagem por nível
                - percentages: porcentagem por nível
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=30)

        # Buscar mudanças no período, ordenadas por data (mais recente primeiro)
        cursor = self.seniority_collection.find({"changed_at": {"$gte": since}}).sort(
            "changed_at", -1
        )

        changes = await self._parse_cursor(cursor)

        # Para cada especialista, pegar o último nível conhecido
        latest_levels: dict[str, str] = {}

        for change in changes:
            specialist_id = change.get("specialist_id")
            new_level = change.get("new_level")

            if specialist_id and new_level:
                # Manter apenas a primeira ocorrência (mais recente, pois ordenamos desc)
                # Não sobrescrever se já existe
                if specialist_id not in latest_levels:
                    latest_levels[specialist_id] = new_level

        # Contar por nível
        by_level: dict[str, int] = {
            "trainee": 0,
            "junior": 0,
            "mid_level": 0,
            "senior": 0,
            "expert": 0,
        }

        for level in latest_levels.values():
            if level in by_level:
                by_level[level] += 1
            else:
                # Nível desconhecido
                by_level["mid_level"] += 1

        total = sum(by_level.values())

        # Calcular porcentagens
        percentages = {}
        if total > 0:
            for level, count in by_level.items():
                percentages[level] = round(count / total, 3)

        return {
            "period_start": since.isoformat(),
            "total_count": total,
            "by_level": by_level,
            "percentages": percentages,
        }

    async def _parse_cursor(self, cursor) -> list[dict[str, Any]]:
        """
        Helper para converter cursor MongoDB em lista.

        Remove _id dos documentos.

        Args:
            cursor: Cursor MongoDB

        Returns:
            Lista de documentos sem _id
        """
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
        return results
