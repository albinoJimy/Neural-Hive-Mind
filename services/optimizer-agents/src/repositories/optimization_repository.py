"""Repository MongoDB para recomendações de otimização."""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


class OptimizationRepository:
    """Repository para gerenciar recomendações de otimização no MongoDB."""

    def __init__(self, client: AsyncIOMotorClient, database_name: str = "neural_hive"):
        """
        Inicializa repository.

        Args:
            client: Cliente Motor MongoDB
            database_name: Nome do database
        """
        self.client = client
        self.database = client[database_name]
        self.collection = self.database.optimization_recommendations

    async def create_indexes(self) -> None:
        """Cria índices para a coleção de recomendações."""
        await self.collection.create_index([("ticket_id", 1)], name="idx_ticket_id")
        await self.collection.create_index(
            [("workflow_id", 1), ("created_at", -1)],
            name="idx_workflow_created"
        )
        await self.collection.create_index(
            [("status", 1), ("created_at", -1)],
            name="idx_status_created"
        )
        await self.collection.create_index(
            [("recommendations.status", 1), ("recommendations.auto_apply", 1)],
            name="idx_pending_auto_apply"
        )
        await self.collection.create_index(
            [("performance_analysis.bottlenecks.issue", 1)],
            name="idx_bottleneck_issues"
        )
        logger.info("optimization_indexes_created")

    async def create(self, data: Dict[str, Any]) -> str:
        """
        Cria nova recomendação de otimização.

        Args:
            data: Dados da recomendação

        Returns:
            ID do documento criado
        """
        data["created_at"] = datetime.utcnow()
        data["updated_at"] = datetime.utcnow()

        result = await self.collection.insert_one(data)
        logger.info(f"optimization_created id={result.inserted_id}")
        return str(result.inserted_id)

    async def get_by_id(self, recommendation_id: str) -> Optional[Dict[str, Any]]:
        """
        Busca recomendação por ID.

        Args:
            recommendation_id: ID da recomendação

        Returns:
            Dados da recomendação ou None
        """
        try:
            obj_id = ObjectId(recommendation_id)
            doc = await self.collection.find_one({"_id": obj_id})
            if doc:
                doc["id"] = str(doc.pop("_id"))
            return doc
        except Exception:
            return None

    async def list_by_filters(
        self,
        status: Optional[str] = None,
        workflow_id: Optional[str] = None,
        target_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Lista recomendações com filtros.

        Args:
            status: Filtrar por status
            workflow_id: Filtrar por workflow ID
            target_type: Filtrar por tipo de target
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Dict com total, offset, limit e items
        """
        query = {}

        if status:
            query["status"] = status
        if workflow_id:
            query["workflow_id"] = workflow_id
        if target_type:
            query["recommendations.target_type"] = target_type

        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        items = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            items.append(doc)

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": items,
        }

    async def update_status(
        self,
        recommendation_id: str,
        status: str,
        approved_by: Optional[str] = None,
    ) -> bool:
        """
        Atualiza status de uma recomendação.

        Args:
            recommendation_id: ID da recomendação
            status: Novo status
            approved_by: Usuário que aprovou (opcional)

        Returns:
            True se atualizado com sucesso
        """
        try:
            obj_id = ObjectId(recommendation_id)
            update_data = {
                "status": status,
                "updated_at": datetime.utcnow(),
            }

            if approved_by:
                update_data["approved_by"] = approved_by
                update_data["approved_at"] = datetime.utcnow()

            if status == "applied":
                update_data["applied_at"] = datetime.utcnow()

            result = await self.collection.update_one(
                {"_id": obj_id}, {"$set": update_data}
            )

            return result.modified_count > 0
        except Exception as e:
            logger.error(f"error_updating_status id={recommendation_id} error={e}")
            return False

    async def update_validation(
        self,
        recommendation_id: str,
        before_duration_ms: int,
        after_duration_ms: int,
        improvement_pct: float,
    ) -> bool:
        """
        Atualiza dados de validação pós-aplicação.

        Args:
            recommendation_id: ID da recomendação
            before_duration_ms: Duração antes da otimização
            after_duration_ms: Duração após otimização
            improvement_pct: Percentual de melhoria

        Returns:
            True se atualizado com sucesso
        """
        try:
            obj_id = ObjectId(recommendation_id)
            result = await self.collection.update_one(
                {"_id": obj_id},
                {
                    "$set": {
                        "validation": {
                            "before_duration_ms": before_duration_ms,
                            "after_duration_ms": after_duration_ms,
                            "improvement_pct": improvement_pct,
                            "validated_at": datetime.utcnow(),
                        },
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

            return result.modified_count > 0
        except Exception as e:
            logger.error(f"error_updating_validation id={recommendation_id} error={e}")
            return False

    async def get_metrics(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Retorna métricas agregadas de otimizações.

        Args:
            from_date: Data inicial (opcional)
            to_date: Data final (opcional)

        Returns:
            Dict com métricas agregadas
        """
        query = {}
        if from_date or to_date:
            query["created_at"] = {}
            if from_date:
                query["created_at"]["$gte"] = from_date
            if to_date:
                query["created_at"]["$lte"] = to_date

        total = await self.collection.count_documents(query)

        pipeline = [
            {"$match": query},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                }
            },
        ]

        status_counts = {}
        async for doc in self.collection.aggregate(pipeline):
            status_counts[doc["_id"]] = doc["count"]

        # Calcular métricas de performance (simplificado)
        applied_pipeline = [
            {"$match": {**query, "status": "applied"}},
            {"$group": {"_id": None, "avg_improvement": {"$avg": "$validation.improvement_pct"}}},
        ]

        avg_improvement = 0.0
        async for doc in self.collection.aggregate(applied_pipeline):
            avg_improvement = doc.get("avg_improvement", 0.0)

        return {
            "total": total,
            "by_status": status_counts,
            "avg_improvement_pct": avg_improvement,
        }

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Retorna dados agregados para dashboard.

        Returns:
            Dict com dados do dashboard
        """
        total = await self.collection.count_documents({})

        pending = await self.collection.count_documents({"status": "pending"})
        applied = await self.collection.count_documents({"status": "applied"})

        # Top issue types
        pipeline = [
            {"$unwind": "$performance_analysis.bottlenecks"},
            {
                "$group": {
                    "_id": "$performance_analysis.bottlenecks.issue",
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]

        top_issues = []
        async for doc in self.collection.aggregate(pipeline):
            top_issues.append({"type": doc["_id"], "count": doc["count"]})

        # Recomendações recentes
        cursor = (
            self.collection.find({})
            .sort("created_at", -1)
            .limit(5)
        )

        recent = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            recent.append(doc)

        return {
            "total_recommendations": total,
            "pending_approval": pending,
            "applied": applied,
            "avg_improvement_pct": await self._get_avg_improvement(),
            "top_issue_types": top_issues,
            "recent_recommendations": recent,
        }

    async def _get_avg_improvement(self) -> float:
        """Calcula melhoria média das otimizações aplicadas."""
        pipeline = [
            {"$match": {"status": "applied", "validation.improvement_pct": {"$exists": True}}},
            {
                "$group": {
                    "_id": None,
                    "avg_improvement": {"$avg": "$validation.improvement_pct"},
                }
            },
        ]

        async for doc in self.collection.aggregate(pipeline):
            return round(doc.get("avg_improvement", 0.0), 2)

        return 0.0

    async def get_timeline(self, workflow_id: str) -> List[Dict[str, Any]]:
        """
        Retorna timeline de otimizações para um workflow.

        Args:
            workflow_id: ID do workflow

        Returns:
            Lista de otimizações ordenadas por data
        """
        cursor = (
            self.collection.find({"workflow_id": workflow_id})
            .sort("created_at", 1)
        )

        timeline = []
        async for doc in cursor:
            timeline.append({
                "id": str(doc.pop("_id")),
                "ticket_id": doc.get("ticket_id"),
                "status": doc.get("status"),
                "applied_at": doc.get("applied_at"),
                "improvement_pct": doc.get("validation", {}).get("improvement_pct"),
            })

        return timeline


# Singleton instance
_repository: Optional[OptimizationRepository] = None


async def get_repository(
    client: AsyncIOMotorClient,
    database_name: str = "neural_hive",
) -> OptimizationRepository:
    """Retorna instância singleton do repository."""
    global _repository
    if _repository is None:
        _repository = OptimizationRepository(client, database_name)
        await _repository.create_indexes()
    return _repository
