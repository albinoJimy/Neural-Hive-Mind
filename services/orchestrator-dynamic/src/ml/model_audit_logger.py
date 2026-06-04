"""
Model Lifecycle Audit Logger.

Tracks all critical events in the ML model lifecycle from training to retirement.
Provides full traceability for compliance, debugging, and operational insights.
"""

import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
from enum import Enum
from typing import Any, Optional

UTC = timezone.utc  # type: ignore, timedelta

# Python 3.10 compatibility: StrEnum was added in Python 3.11
if sys.version_info >= (3, 11):
    from enum import StrEnum as _StrEnum
else:

    class _StrEnum(str, Enum):
        """Polyfill for StrEnum on Python 3.10"""

        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            return name


import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

logger = structlog.get_logger(__name__)


class ModelLifecycleEvent(_StrEnum):
    """Types of model lifecycle events."""

    TRAINING_STARTED = "training_started"
    TRAINING_COMPLETED = "training_completed"
    TRAINING_FAILED = "training_failed"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    PROMOTION_INITIATED = "promotion_initiated"
    SHADOW_MODE_STARTED = "shadow_mode_started"
    SHADOW_MODE_COMPLETED = "shadow_mode_completed"
    CANARY_DEPLOYED = "canary_deployed"
    ROLLOUT_STAGE_COMPLETED = "rollout_stage_completed"
    ROLLBACK_EXECUTED = "rollback_executed"
    MODEL_PROMOTED = "model_promoted"
    MODEL_RETIRED = "model_retired"
    DRIFT_DETECTED = "drift_detected"
    RETRAINING_TRIGGERED = "retraining_triggered"


@dataclass
class AuditEventContext:
    """Rich context for audit events."""

    user_id: Optional[str] = None
    reason: Optional[str] = None
    duration_seconds: Optional[float] = None
    environment: str = "production"
    triggered_by: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelAuditLogger:
    """
    Audit logger for ML model lifecycle.

    Features:
    - Complete event tracking (training -> production -> retirement)
    - Rich context (user_id, reason, metrics, duration)
    - MongoDB persistence with optimized indexes
    - Efficient queries by model, event, period
    - Automatic retention via TTL index
    """

    def __init__(self, mongodb_client: AsyncIOMotorClient, config, metrics=None):
        """
        Initialize ModelAuditLogger.

        Args:
            mongodb_client: Async MongoDB client
            config: Orchestrator configuration
            metrics: OrchestratorMetrics (optional)
        """
        self.mongodb_client = mongodb_client
        self.config = config
        self.metrics = metrics
        self.logger = logger.bind(component="model_audit_logger")

        # Configuration
        self.collection_name = getattr(config, "ml_audit_log_collection", "model_audit_log")
        self.retention_days = getattr(config, "ml_audit_retention_days", 365)
        self.enabled = getattr(config, "ml_audit_enabled", True)

        # Collection will be initialized lazily
        self._collection = None
        self._indexes_created = False

    async def _ensure_collection(self):
        """Ensure collection and indexes exist."""
        if self._collection is None:
            self._collection = self.mongodb_client.db[self.collection_name]

        if not self._indexes_created:
            await self._create_indexes()
            self._indexes_created = True

    async def _create_indexes(self):
        """Create optimized indexes for queries."""
        try:
            # Index by timestamp (temporal queries)
            await self._collection.create_index([("timestamp", DESCENDING)])

            # Index by model_name + timestamp (queries per model)
            await self._collection.create_index(
                [("model_name", ASCENDING), ("timestamp", DESCENDING)]
            )

            # Index by event_type + timestamp (queries by event type)
            await self._collection.create_index(
                [("event_type", ASCENDING), ("timestamp", DESCENDING)]
            )

            # Index by model_version (track specific version)
            await self._collection.create_index([("model_version", ASCENDING)])

            # TTL index for automatic retention
            ttl_seconds = self.retention_days * 24 * 3600
            await self._collection.create_index(
                [("timestamp", ASCENDING)],
                expireAfterSeconds=ttl_seconds,
                name="ttl_retention_index",
            )

            self.logger.info(
                "model_audit_indexes_created",
                collection=self.collection_name,
                retention_days=self.retention_days,
            )
        except Exception as e:
            self.logger.exception("failed_to_create_audit_indexes", error=str(e))

    async def log_training_started(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        training_config: dict[str, Any],
    ) -> str:
        """
        Log training start.

        Args:
            model_name: Model name
            model_version: Version being trained
            context: Event context
            training_config: Training configuration

        Returns:
            audit_id of the event
        """
        return await self._log_event(
            event_type=ModelLifecycleEvent.TRAINING_STARTED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "training_config": training_config,
                "dataset_info": training_config.get("dataset_info", {}),
                "hyperparameters": training_config.get("hyperparameters", {}),
            },
        )

    async def log_training_completed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        metrics: dict[str, float],
    ) -> str:
        """
        Log training completion.

        Args:
            model_name: Model name
            model_version: Trained version
            context: Context (include duration_seconds)
            metrics: Training metrics (F1, precision, recall, etc)

        Returns:
            audit_id of the event
        """
        return await self._log_event(
            event_type=ModelLifecycleEvent.TRAINING_COMPLETED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={"metrics": metrics, "training_duration_seconds": context.duration_seconds},
        )

    async def log_training_failed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        error_message: str,
        error_details: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Log training failure.

        Args:
            model_name: Model name
            model_version: Version that failed
            context: Event context
            error_message: Error message
            error_details: Additional error details

        Returns:
            audit_id of the event
        """
        return await self._log_event(
            event_type=ModelLifecycleEvent.TRAINING_FAILED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "error_message": error_message,
                "error_details": error_details or {},
                "training_duration_seconds": context.duration_seconds,
            },
        )

    async def log_validation_passed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        validation_results: dict[str, Any],
    ) -> str:
        """Log successful validation."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.VALIDATION_PASSED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data=validation_results,
        )

    async def log_validation_failed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        validation_results: dict[str, Any],
        failure_reasons: list[str],
    ) -> str:
        """Log failed validation."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.VALIDATION_FAILED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "validation_results": validation_results,
                "failure_reasons": failure_reasons,
            },
        )

    async def log_promotion_initiated(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        promotion_config: dict[str, Any],
    ) -> str:
        """Log promotion initiation."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.PROMOTION_INITIATED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "promotion_config": promotion_config,
                "current_production_version": promotion_config.get("current_version"),
            },
        )

    async def log_shadow_mode_started(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        shadow_config: dict[str, Any],
    ) -> str:
        """Log shadow mode start."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.SHADOW_MODE_STARTED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data=shadow_config,
        )

    async def log_shadow_mode_completed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        shadow_results: dict[str, Any],
    ) -> str:
        """Log shadow mode completion."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.SHADOW_MODE_COMPLETED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "agreement_rate": shadow_results.get("agreement_rate"),
                "prediction_count": shadow_results.get("prediction_count"),
                "avg_latency_ms": shadow_results.get("avg_latency_ms"),
            },
        )

    async def log_canary_deployed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        canary_config: dict[str, Any],
    ) -> str:
        """Log canary deployment."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.CANARY_DEPLOYED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "traffic_percentage": canary_config.get("traffic_percentage"),
                "duration_minutes": canary_config.get("duration_minutes"),
            },
        )

    async def log_rollout_stage_completed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        stage_info: dict[str, Any],
    ) -> str:
        """Log rollout stage completion."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.ROLLOUT_STAGE_COMPLETED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "stage": stage_info.get("stage"),
                "traffic_percentage": stage_info.get("traffic_percentage"),
                "metrics": stage_info.get("metrics", {}),
            },
        )

    async def log_rollback_executed(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        rollback_reason: str,
        previous_version: str,
    ) -> str:
        """Log model rollback."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.ROLLBACK_EXECUTED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={
                "rollback_reason": rollback_reason,
                "previous_version": previous_version,
                "severity": "critical",
            },
        )

    async def log_model_promoted(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        promotion_summary: dict[str, Any],
    ) -> str:
        """Log successful promotion to production."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.MODEL_PROMOTED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data=promotion_summary,
        )

    async def log_model_retired(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        retirement_reason: str,
    ) -> str:
        """Log model retirement."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.MODEL_RETIRED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data={"retirement_reason": retirement_reason},
        )

    async def log_drift_detected(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        drift_info: dict[str, Any],
    ) -> str:
        """Log drift detection."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.DRIFT_DETECTED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data=drift_info,
        )

    async def log_retraining_triggered(
        self,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        trigger_info: dict[str, Any],
    ) -> str:
        """Log retraining trigger."""
        return await self._log_event(
            event_type=ModelLifecycleEvent.RETRAINING_TRIGGERED,
            model_name=model_name,
            model_version=model_version,
            context=context,
            event_data=trigger_info,
        )

    async def _log_event(
        self,
        event_type: ModelLifecycleEvent,
        model_name: str,
        model_version: str,
        context: AuditEventContext,
        event_data: dict[str, Any],
    ) -> str:
        """
        Log audit event to MongoDB.

        Returns:
            audit_id of the created event
        """
        if not self.enabled:
            return ""

        try:
            await self._ensure_collection()

            audit_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc)

            document = {
                "audit_id": audit_id,
                "timestamp": timestamp,
                "event_type": event_type.value,
                "model_name": model_name,
                "model_version": model_version,
                "user_id": context.user_id,
                "reason": context.reason,
                "duration_seconds": context.duration_seconds,
                "environment": context.environment,
                "triggered_by": context.triggered_by,
                "event_data": event_data,
                "metadata": context.metadata,
            }

            await self._collection.insert_one(document)

            # Record Prometheus metric
            if self.metrics:
                self.metrics.increment_model_audit_event(
                    model_name=model_name, event_type=event_type.value
                )

            self.logger.info(
                "model_audit_event_logged",
                audit_id=audit_id,
                event_type=event_type.value,
                model_name=model_name,
                model_version=model_version,
            )

            return audit_id

        except Exception as e:
            self.logger.exception(
                "failed_to_log_audit_event",
                event_type=event_type.value,
                model_name=model_name,
                error=str(e),
            )
            return ""

    async def get_model_history(
        self, model_name: str, limit: int = 100, event_types: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """
        Get event history for a model.

        Args:
            model_name: Model name
            limit: Maximum number of events
            event_types: Filter by event types (optional)

        Returns:
            List of events ordered by timestamp (most recent first)
        """
        if not self.enabled:
            return []

        try:
            await self._ensure_collection()

            query = {"model_name": model_name}
            if event_types:
                query["event_type"] = {"$in": event_types}

            cursor = self._collection.find(query).sort("timestamp", DESCENDING).limit(limit)
            events = await cursor.to_list(length=limit)

            # Convert ObjectId to string
            for event in events:
                if "_id" in event:
                    event["_id"] = str(event["_id"])

            return events

        except Exception as e:
            self.logger.exception(
                "failed_to_get_model_history", model_name=model_name, error=str(e)
            )
            return []

    async def get_events_by_type(
        self,
        event_type: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get events by type and period.

        Args:
            event_type: Event type
            start_date: Start date (optional)
            end_date: End date (optional)
            limit: Maximum number of events

        Returns:
            List of events
        """
        if not self.enabled:
            return []

        try:
            await self._ensure_collection()

            query: dict[str, Any] = {"event_type": event_type}

            if start_date or end_date:
                query["timestamp"] = {}
                if start_date:
                    query["timestamp"]["$gte"] = start_date
                if end_date:
                    query["timestamp"]["$lte"] = end_date

            cursor = self._collection.find(query).sort("timestamp", DESCENDING).limit(limit)
            events = await cursor.to_list(length=limit)

            for event in events:
                if "_id" in event:
                    event["_id"] = str(event["_id"])

            return events

        except Exception as e:
            self.logger.exception(
                "failed_to_get_events_by_type", event_type=event_type, error=str(e)
            )
            return []

    async def get_audit_summary(
        self, model_name: Optional[str] = None, days: int = 30
    ) -> dict[str, Any]:
        """
        Generate audit summary.

        Args:
            model_name: Model name (optional, None = all)
            days: Days window

        Returns:
            Aggregated statistics
        """
        if not self.enabled:
            return {}

        try:
            await self._ensure_collection()

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            match_stage: dict[str, Any] = {"timestamp": {"$gte": cutoff}}
            if model_name:
                match_stage["model_name"] = model_name

            pipeline = [
                {"$match": match_stage},
                {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
            ]

            results = await self._collection.aggregate(pipeline).to_list(length=None)

            return {
                "period_days": days,
                "model_name": model_name or "all",
                "events_by_type": {r["_id"]: r["count"] for r in results},
                "total_events": sum(r["count"] for r in results),
            }

        except Exception as e:
            self.logger.exception("failed_to_get_audit_summary", error=str(e))
            return {}

    async def get_model_timeline(self, model_name: str, days: int = 90) -> dict[str, Any]:
        """
        Generate visual timeline of model events.

        Args:
            model_name: Model name
            days: Days window

        Returns:
            Structured timeline for visualization
        """
        if not self.enabled:
            return {}

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            events = await self.get_model_history(model_name=model_name, limit=1000)

            # Filter by period
            events = [e for e in events if e.get("timestamp") and e["timestamp"] >= cutoff]

            # Group by version
            versions: dict[str, list[dict[str, Any]]] = {}
            for event in events:
                version = event.get("model_version", "unknown")
                if version not in versions:
                    versions[version] = []
                timestamp = event.get("timestamp")
                versions[version].append(
                    {
                        "timestamp": timestamp.isoformat() if timestamp else None,
                        "event_type": event.get("event_type"),
                        "duration_seconds": event.get("duration_seconds"),
                        "reason": event.get("reason"),
                    }
                )

            return {
                "model_name": model_name,
                "period_days": days,
                "versions": versions,
                "total_events": len(events),
            }

        except Exception as e:
            self.logger.exception(
                "failed_to_get_model_timeline", model_name=model_name, error=str(e)
            )
            return {}

    async def get_event_by_id(self, audit_id: str) -> Optional[dict[str, Any]]:
        """
        Get specific event by audit_id.

        Args:
            audit_id: Audit event ID

        Returns:
            Event document or None
        """
        if not self.enabled:
            return None

        try:
            await self._ensure_collection()

            event = await self._collection.find_one({"audit_id": audit_id})
            if event and "_id" in event:
                event["_id"] = str(event["_id"])

            return event

        except Exception as e:
            self.logger.exception("failed_to_get_event_by_id", audit_id=audit_id, error=str(e))
            return None
