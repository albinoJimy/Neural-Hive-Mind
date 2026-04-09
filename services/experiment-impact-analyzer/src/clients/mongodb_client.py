"""MongoDB client for Experiment Impact Analyzer."""

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.config.settings import Settings, get_settings

logger = structlog.get_logger()

UTC = timezone.utc


class MongoDBClient:
    """Client for MongoDB operations."""

    def __init__(self, settings: Settings | None = None):
        """Initialize MongoDB client.

        Args:
            settings: Configuration settings. Uses defaults if None.
        """
        self.settings = settings or get_settings()
        self._client: AsyncIOMotorClient | None = None
        self._database: AsyncIOMotorDatabase | None = None
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to MongoDB."""
        try:
            self._client = AsyncIOMotorClient(
                self.settings.mongodb_uri,
                maxPoolSize=self.settings.mongodb_max_pool_size,
                minPoolSize=self.settings.mongodb_min_pool_size,
            )

            # Test connection
            await self._client.admin.command("ping")

            self._database = self._client[self.settings.mongodb_database]
            self._connected = True

            logger.info(
                "mongodb_connected",
                database=self.settings.mongodb_database,
                uri=self.settings.mongodb_uri.split("@")[-1] if "@" in self.settings.mongodb_uri else "localhost",
            )

        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._connected = False
            logger.info("mongodb_disconnected")

    def get_client(self) -> AsyncIOMotorClient:
        """Get raw motor client.

        Returns:
            AsyncIOMotorClient instance
        """
        if not self._connected or not self._client:
            raise RuntimeError("MongoDB client not connected")
        return self._client

    def get_database(self) -> AsyncIOMotorDatabase:
        """Get database instance.

        Returns:
            AsyncIOMotorDatabase instance
        """
        if not self._connected or not self._database:
            raise RuntimeError("MongoDB not connected")
        return self._database

    async def save_impact(self, impact: dict[str, Any]) -> str:
        """Save impact analysis to MongoDB.

        Args:
            impact: Impact document to save

        Returns:
            Inserted document ID
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_impacts_collection]

        result = await collection.insert_one(impact)
        return str(result.inserted_id)

    async def get_impact(self, impact_id: str) -> dict[str, Any] | None:
        """Get impact analysis by ID.

        Args:
            impact_id: Impact ID

        Returns:
            Impact document or None
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_impacts_collection]

        return await collection.find_one({"impact_id": impact_id})

    async def get_impact_by_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Get latest impact analysis for an experiment.

        Args:
            experiment_id: Experiment ID

        Returns:
            Impact document or None
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_impacts_collection]

        return await collection.find_one(
            {"experiment_id": experiment_id},
            sort=[("created_at", -1)]
        )

    async def update_impact(
        self, impact_id: str, updates: dict[str, Any]
    ) -> bool:
        """Update impact analysis.

        Args:
            impact_id: Impact ID
            updates: Fields to update

        Returns:
            True if updated, False otherwise
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_impacts_collection]

        updates["updated_at"] = updates.get("updated_at", datetime.now(UTC))

        result = await collection.update_one(
            {"impact_id": impact_id},
            {"$set": updates}
        )
        return result.modified_count > 0

    async def list_impacts(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: int = -1,
    ) -> list[dict[str, Any]]:
        """List impact analyses.

        Args:
            filters: Query filters
            limit: Max results
            offset: Skip results
            sort_by: Sort field
            sort_order: Sort direction (1=asc, -1=desc)

        Returns:
            List of impact documents
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_impacts_collection]

        query = filters or {}

        cursor = collection.find(query).sort(sort_by, sort_order).skip(offset).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Get experiment by ID.

        Args:
            experiment_id: Experiment ID

        Returns:
            Experiment document or None
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_experiments_collection]

        return await collection.find_one({"experiment_id": experiment_id})

    async def list_experiments(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List experiments.

        Args:
            filters: Query filters
            limit: Max results

        Returns:
            List of experiment documents
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_experiments_collection]

        query = filters or {}
        cursor = collection.find(query).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_hypothesis(self, hypothesis_id: str) -> dict[str, Any] | None:
        """Get hypothesis by ID.

        Args:
            hypothesis_id: Hypothesis ID

        Returns:
            Hypothesis document or None
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_hypotheses_collection]

        return await collection.find_one({"hypothesis_id": hypothesis_id})

    async def get_metrics_history(
        self,
        metric_names: list[str],
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Get historical metrics data.

        Args:
            metric_names: List of metric names
            start_date: Start date
            end_date: End date

        Returns:
            List of metric data points
        """
        # This would query a metrics collection (e.g., Prometheus, TimescaleDB)
        # For now, return empty list - to be implemented based on actual metrics storage
        db = self.get_database()

        # Check if metrics collection exists
        collection_names = await db.list_collection_names()
        if "metrics_history" not in collection_names:
            return []

        collection = db["metrics_history"]

        query = {
            "metric_name": {"$in": metric_names},
            "timestamp": {"$gte": start_date, "$lte": end_date},
        }

        cursor = collection.find(query).sort("timestamp", 1)
        return await cursor.to_list(length=None)

    async def aggregate_impacts_by_category(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate impacts by category.

        Args:
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Aggregated data by category
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_impacts_collection]

        match_stage = {}
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            match_stage["created_at"] = date_filter

        pipeline = []
        if match_stage:
            pipeline.append({"$match": match_stage})

        pipeline.extend([
            {"$unwind": "$categories"},
            {
                "$group": {
                    "_id": "$categories",
                    "count": {"$sum": 1},
                    "positive_count": {
                        "$sum": {"$cond": [{"$eq": ["$overall_direction", "positive"]}, 1, 0]}
                    },
                    "negative_count": {
                        "$sum": {"$cond": [{"$eq": ["$overall_direction", "negative"]}, 1, 0]}
                    },
                    "avg_confidence": {"$avg": "$confidence_level"},
                }
            },
            {"$sort": {"count": -1}},
        ])

        return await collection.aggregate(pipeline).to_list(length=None)

    async def find_correlated_experiments(
        self,
        experiment_id: str,
        categories: list[str],
        min_correlation: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Find experiments with overlapping categories (potential correlations).

        Args:
            experiment_id: Current experiment ID
            categories: Impact categories
            min_correlation: Minimum correlation threshold

        Returns:
            List of potentially correlated experiments
        """
        db = self.get_database()
        collection = db[self.settings.mongodb_impacts_collection]

        query = {
            "experiment_id": {"$ne": experiment_id},
            "categories": {"$in": categories},
        }

        cursor = collection.find(query).sort("created_at", -1).limit(20)
        return await cursor.to_list(length=None)
