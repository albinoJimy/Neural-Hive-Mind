"""Rastreador de evolução de arquitetura."""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClientSession

from src.models.evolution import EvolutionHistory, DriftDetection, ArchitectureDiff
from src.models.architecture import ArchitecturePlan
from src.evolution.drift_detector import DriftDetector
from src.evolution.diff_calculator import DiffCalculator
from src.config.settings import get_settings
import structlog


logger = structlog.get_logger(__name__)


class EvolutionTracker:
    """Rastreia evolução e detecta divergências em planos arquiteturais."""

    def __init__(self, db_session: AsyncIOMotorClientSession):
        """Inicializa tracker com sessão de banco de dados.

        Args:
            db_session: Sessão MongoDB para transações
        """
        self.db = db_session.client
        settings = get_settings()
        self.db_name = settings.mongodb.database
        self.collection = settings.mongodb.collection_evolution
        self.drift_detector = DriftDetector()
        self.diff_calculator = DiffCalculator()

    async def record_evolution(
        self,
        plan_id: str,
        version: int,
        changes: List[str],
        drifts: List[DriftDetection],
        created_by: str = "architect-agent"
    ) -> EvolutionHistory:
        """Registra entrada de histórico de evolução.

        Args:
            plan_id: ID do plano de arquitetura
            version: Versão do plano
            changes: Lista de mudanças aplicadas
            drifts: Lista de divergências detectadas
            created_by: Autor da mudança

        Returns:
            EvolutionHistory criado
        """
        history = EvolutionHistory(
            history_id=f"evo-{uuid.uuid4().hex[:8]}",
            plan_id=plan_id,
            version=version,
            changes=changes,
            drifts=drifts,
            created_at=datetime.now(timezone.utc),
            created_by=created_by
        )

        await self.db[self.db_name][self.collection].insert_one(
            history.model_dump(by_alias=True, exclude_none=True)
        )

        logger.info(
            "evolution_recorded",
            history_id=history.history_id,
            plan_id=plan_id,
            version=version,
            changes_count=len(changes),
            drifts_count=len(drifts)
        )

        return history

    async def detect_and_record_drifts(
        self,
        planned: ArchitecturePlan,
        implemented: Dict[str, Any],
        version: int,
        created_by: str = "architect-agent"
    ) -> List[DriftDetection]:
        """Detecta divergências e registra no histórico.

        Args:
            planned: Plano arquitetural planejado
            implemented: Implementação detectada
            version: Versão atual
            created_by: Autor da detecção

        Returns:
            Lista de divergências detectadas
        """
        drifts = self.drift_detector.detect_drifts(planned, implemented)

        if drifts:
            changes = [f"Drift detection: {len(drifts)} divergências encontradas"]
            await self.record_evolution(
                plan_id=planned.plan_id,
                version=version,
                changes=changes,
                drifts=drifts,
                created_by=created_by
            )

        return drifts

    async def calculate_diff(
        self, plan_old_id: str, plan_new_id: str
    ) -> Optional[ArchitectureDiff]:
        """Calcula diferença entre dois planos.

        Args:
            plan_old_id: ID do plano antigo
            plan_new_id: ID do novo plano

        Returns:
            ArchitectureDiff se ambos os planos existirem
        """
        # Implementação placeholder - na prática buscaria do banco
        # Por simplicidade, retorna diff vazio
        return ArchitectureDiff(
            plan_id_old=plan_old_id,
            plan_id_new=plan_new_id,
            additions=[],
            removals=[],
            modifications=[],
            requires_migration=False
        )

    async def get_history(
        self, plan_id: str, limit: int = 10
    ) -> List[EvolutionHistory]:
        """Obtém histórico de evolução de um plano.

        Args:
            plan_id: ID do plano
            limit: Número máximo de entradas

        Returns:
            Lista de EvolutionHistory
        """
        cursor = (
            self.db[self.db_name][self.collection]
            .find({"plan_id": plan_id})
            .sort("created_at", -1)
            .limit(limit)
        )

        results = await cursor.to_list(length=limit)
        return [EvolutionHistory(**item) for item in results]
