"""
Repositório MongoDB para Insights.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient

from ..models.insight_extended import (
    AnalysisType,
    InsightCreate,
    InsightMetrics,
    InsightResponse,
    InsightSource,
    InsightStatus,
    TimeSeriesCacheEntry,
)

logger = structlog.get_logger()


class InsightRepository:
    """Repositório para persistência de insights."""

    def __init__(
        self,
        client: AsyncIOMotorClient,
        database: str,
        collection: str = "insights",
        cache_collection: str = "time_series_cache",
        ttl_days: int = 90,
        cache_ttl_hours: int = 24,
    ):
        self.client = client
        self.database = database
        self.collection = collection
        self.cache_collection = cache_collection
        self.ttl_days = ttl_days
        self.cache_ttl_hours = cache_ttl_hours
        self._db = None

    async def initialize(self):
        """Inicializa conexão."""
        self._db = self.client[self.database]

    async def create(self, insight: InsightCreate) -> InsightResponse:
        """Criar novo insight."""
        doc = insight.dict()
        doc["insight_id"] = str(uuid.uuid4())
        doc["status"] = InsightStatus.PENDING
        doc["created_at"] = datetime.now(timezone.utc)
        doc["expires_at"] = datetime.now(timezone.utc) + timedelta(days=self.ttl_days)

        # Initialize default metrics (required field)
        doc["metrics"] = InsightMetrics(
            processing_time_ms=0,
            confidence_score=0.0,
            data_points=0,
        ).dict()

        await self._db[self.collection].insert_one(doc)

        return InsightResponse(**doc)

    async def get_by_id(self, insight_id: str) -> Optional[InsightResponse]:
        """Obter insight por ID."""
        doc = await self._db[self.collection].find_one({"insight_id": insight_id})
        if not doc:
            return None
        return InsightResponse(**doc)

    async def list(
        self,
        analysis_type: Optional[AnalysisType] = None,
        source: Optional[InsightSource] = None,
        tags: Optional[list[str]] = None,
        status: Optional[InsightStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[InsightResponse], int]:
        """Listar insights com filtros."""
        filters = {}

        if analysis_type:
            filters["analysis_type"] = analysis_type.value
        if source:
            filters["metadata.source"] = source.value
        if tags:
            filters["tags"] = {"$in": tags}
        if status:
            filters["status"] = status.value
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            filters["created_at"] = date_filter

        # Total count
        total = await self._db[self.collection].count_documents(filters)

        # Query with pagination
        cursor = (
            self._db[self.collection].find(filters).sort("created_at", -1).skip(offset).limit(limit)
        )

        items = []
        async for doc in cursor:
            items.append(InsightResponse(**doc))

        return items, total

    async def update_status(
        self, insight_id: str, status: InsightStatus, data: Optional[dict[str, Any]] = None
    ) -> Optional[InsightResponse]:
        """Atualizar status do insight."""
        update_doc = {"status": status.value}
        if data:
            update_doc["data"] = data

        result = await self._db[self.collection].update_one(
            {"insight_id": insight_id}, {"$set": update_doc}
        )

        if result.modified_count == 0:
            return None

        return await self.get_by_id(insight_id)

    async def update_metrics(
        self, insight_id: str, metrics: dict[str, Any]
    ) -> Optional[InsightResponse]:
        """Atualizar métricas do insight."""
        result = await self._db[self.collection].update_one(
            {"insight_id": insight_id}, {"$set": {"metrics": metrics}}
        )

        if result.modified_count == 0:
            return None

        return await self.get_by_id(insight_id)

    async def delete(self, insight_id: str) -> bool:
        """Deletar insight."""
        result = await self._db[self.collection].delete_one({"insight_id": insight_id})
        return result.deleted_count > 0

    # Time-series cache methods

    async def cache_get(self, cache_key: str) -> Optional[TimeSeriesCacheEntry]:
        """Obter do cache de série temporal."""
        doc = await self._db[self.cache_collection].find_one({"cache_key": cache_key})
        if not doc:
            return None
        return TimeSeriesCacheEntry(**doc)

    async def cache_set(
        self,
        cache_key: str,
        metric_name: str,
        data: List[dict[str, Any]],
        statistics: dict[str, float],
    ) -> TimeSeriesCacheEntry:
        """Salvar no cache de série temporal."""
        doc = {
            "cache_key": cache_key,
            "metric_name": metric_name,
            "data": data,
            "statistics": statistics,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=self.cache_ttl_hours),
        }

        await self._db[self.cache_collection].update_one(
            {"cache_key": cache_key}, {"$set": doc}, upsert=True
        )

        return TimeSeriesCacheEntry(**doc)

    async def cache_delete(self, cache_key: str) -> bool:
        """Deletar do cache."""
        result = await self._db[self.cache_collection].delete_one({"cache_key": cache_key})
        return result.deleted_count > 0

    async def get_analytics_summary(self, time_range_hours: int = 24) -> dict[str, Any]:
        """Obter resumo agregado para dashboard."""
        start_date = datetime.now(timezone.utc) - timedelta(hours=time_range_hours)

        pipeline = [
            {"$match": {"created_at": {"$gte": start_date}}},
            {
                "$group": {
                    "_id": "$analysis_type",
                    "count": {"$sum": 1},
                }
            },
        ]

        insights_by_type = {}
        async for doc in self._db[self.collection].aggregate(pipeline):
            insights_by_type[doc["_id"]] = doc["count"]

        # Count anomalies
        anomalies_count = await self._db[self.collection].count_documents(
            {"created_at": {"$gte": start_date}, "timeseries.anomalies.0": {"$exists": True}}
        )

        # Avg processing time
        pipeline_avg = [
            {
                "$match": {
                    "created_at": {"$gte": start_date},
                    "metrics.processing_time_ms": {"$exists": True},
                }
            },
            {"$group": {"_id": None, "avg": {"$avg": "$metrics.processing_time_ms"}}},
        ]

        avg_time = 0
        async for doc in self._db[self.collection].aggregate(pipeline_avg):
            avg_time = doc.get("avg", 0)

        # Confidence distribution
        pipeline_conf = [
            {
                "$match": {
                    "created_at": {"$gte": start_date},
                    "metrics.confidence_score": {"$exists": True},
                }
            },
            {
                "$bucket": {
                    "groupBy": "$metrics.confidence_score",
                    "boundaries": [0.0, 0.5, 0.8, 1.0],
                    "default": "other",
                    "output": {"count": {"$sum": 1}},
                }
            },
        ]

        confidence_dist = {"high": 0, "medium": 0, "low": 0}
        async for doc in self._db[self.collection].aggregate(pipeline_conf):
            if doc["_id"] < 0.5:
                confidence_dist["low"] = doc["count"]
            elif doc["_id"] < 0.8:
                confidence_dist["medium"] = doc["count"]
            else:
                confidence_dist["high"] = doc["count"]

        # Top sources
        pipeline_sources = [
            {"$match": {"created_at": {"$gte": start_date}}},
            {"$group": {"_id": "$metadata.source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]

        top_sources = []
        async for doc in self._db[self.collection].aggregate(pipeline_sources):
            top_sources.append({"source": doc["_id"], "count": doc["count"]})

        return {
            "insights_by_type": insights_by_type,
            "anomalies_detected": anomalies_count,
            "avg_processing_time_ms": avg_time,
            "confidence_distribution": confidence_dist,
            "top_sources": top_sources,
        }
