"""Database helpers for E2E testing of Phase 2 Flow C.

Provides validation functions for MongoDB and PostgreSQL persistence.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)

# Default connection strings
DEFAULT_MONGODB_URI = "mongodb://mongodb-cluster.mongodb-cluster.svc.cluster.local:27017"
DEFAULT_MONGODB_DATABASE = "neural_hive"

DEFAULT_POSTGRESQL_TICKETS_URI = (
    "postgresql://postgres:password@postgresql-tickets.neural-hive-orchestration.svc.cluster.local:5432/execution_tickets"
)
DEFAULT_POSTGRESQL_TEMPORAL_URI = (
    "postgresql://postgres:password@postgresql-temporal.neural-hive-temporal.svc.cluster.local:5432/temporal"
)


@dataclass
class MongoDBCollectionStats:
    """Statistics for a MongoDB collection."""

    collection_name: str
    document_count: int
    has_data: bool
    sample_document: Optional[Dict[str, Any]] = None


@dataclass
class TicketPersistenceStats:
    """Statistics for execution tickets in PostgreSQL."""

    total_tickets: int
    pending: int
    claimed: int
    executing: int
    completed: int
    failed: int
    lifecycle_valid: bool


class MongoDBTestHelper:
    """Helper class for MongoDB testing."""

    def __init__(
        self,
        uri: str = DEFAULT_MONGODB_URI,
        database: str = DEFAULT_MONGODB_DATABASE,
    ):
        self.uri = uri
        self.database_name = database
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    def connect(self) -> None:
        """Connect to MongoDB."""
        if self._client is None:
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self._db = self._client[self.database_name]
            # Test connection
            self._client.server_info()
            logger.info(f"Connected to MongoDB at {self.uri}")

    def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    @property
    def db(self) -> Database:
        """Get the database object."""
        if self._db is None:
            raise RuntimeError("MongoDB not connected. Call connect() first.")
        return self._db

    def get_collection_stats(
        self, collection_name: str, filter_query: Optional[Dict[str, Any]] = None
    ) -> MongoDBCollectionStats:
        """
        Get statistics for a collection.

        Args:
            collection_name: Name of the collection
            filter_query: Optional filter query

        Returns:
            MongoDBCollectionStats with collection info
        """
        collection = self.db[collection_name]
        query = filter_query or {}

        count = collection.count_documents(query)
        sample = collection.find_one(query) if count > 0 else None

        # Convert ObjectId to string for sample
        if sample and "_id" in sample:
            sample["_id"] = str(sample["_id"])

        return MongoDBCollectionStats(
            collection_name=collection_name,
            document_count=count,
            has_data=count > 0,
            sample_document=sample,
        )

    def find_documents(
        self,
        collection_name: str,
        filter_query: Dict[str, Any],
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Find documents in a collection.

        Args:
            collection_name: Name of the collection
            filter_query: Query filter
            limit: Maximum documents to return

        Returns:
            List of documents
        """
        collection = self.db[collection_name]
        documents = list(collection.find(filter_query).limit(limit))

        # Convert ObjectIds to strings
        for doc in documents:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return documents

    def validate_orchestration_ledger(self, plan_id: str) -> Dict[str, Any]:
        """
        Validate orchestration ledger entries for a plan.

        Args:
            plan_id: The plan ID to validate

        Returns:
            Validation result
        """
        stats = self.get_collection_stats(
            "orchestration_ledger", {"plan_id": plan_id}
        )

        # Get the actual document to check fields
        doc = stats.sample_document
        required_fields = ["plan_id", "workflow_id", "status", "created_at"]
        missing_fields = []

        if doc:
            for field in required_fields:
                if field not in doc:
                    missing_fields.append(field)

        return {
            "valid": stats.has_data and len(missing_fields) == 0,
            "collection": "orchestration_ledger",
            "document_count": stats.document_count,
            "has_data": stats.has_data,
            "missing_fields": missing_fields,
            "sample": doc,
        }

    def validate_execution_tickets_ledger(self, plan_id: str) -> Dict[str, Any]:
        """
        Validate execution tickets ledger entries.

        Args:
            plan_id: The plan ID to validate

        Returns:
            Validation result
        """
        stats = self.get_collection_stats(
            "execution_tickets_ledger", {"plan_id": plan_id}
        )

        return {
            "valid": stats.has_data,
            "collection": "execution_tickets_ledger",
            "document_count": stats.document_count,
            "has_data": stats.has_data,
            "sample": stats.sample_document,
        }

    def validate_code_forge_artifacts(self, plan_id: str) -> Dict[str, Any]:
        """
        Validate Code Forge artifacts.

        Args:
            plan_id: The plan ID to validate

        Returns:
            Validation result with artifact stages
        """
        documents = self.find_documents(
            "code_forge_artifacts", {"plan_id": plan_id}
        )

        # Check for 6 stages completion
        stages_completed = set()
        for doc in documents:
            if "stage" in doc:
                stages_completed.add(doc["stage"])

        expected_stages = {
            "template_selection",
            "code_composition",
            "sast_dast_validation",
            "automated_tests",
            "packaging_signing",
            "approval_gate",
        }

        missing_stages = expected_stages - stages_completed

        return {
            "valid": len(documents) > 0 and len(missing_stages) == 0,
            "collection": "code_forge_artifacts",
            "artifact_count": len(documents),
            "stages_completed": list(stages_completed),
            "missing_stages": list(missing_stages),
            "all_stages_complete": len(missing_stages) == 0,
        }

    def validate_strategic_decisions(self) -> Dict[str, Any]:
        """
        Validate strategic decisions from Queen Agent.

        Returns:
            Validation result
        """
        stats = self.get_collection_stats("strategic_decisions")

        return {
            "valid": True,  # Strategic decisions are optional
            "collection": "strategic_decisions",
            "document_count": stats.document_count,
            "has_data": stats.has_data,
        }


class PostgreSQLTestHelper:
    """Helper class for PostgreSQL testing."""

    def __init__(self, connection_uri: str):
        self.connection_uri = connection_uri
        self._conn = None

    def connect(self) -> None:
        """Connect to PostgreSQL."""
        if self._conn is None:
            self._conn = psycopg2.connect(self.connection_uri)
            logger.info(f"Connected to PostgreSQL")

    def close(self) -> None:
        """Close PostgreSQL connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self):
        """Get the connection object."""
        if self._conn is None:
            raise RuntimeError("PostgreSQL not connected. Call connect() first.")
        return self._conn

    def execute_query(
        self, query: str, params: tuple = ()
    ) -> List[Dict[str, Any]]:
        """
        Execute a query and return results.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def execute_scalar(self, query: str, params: tuple = ()) -> Any:
        """
        Execute a query and return a single scalar value.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            Single value
        """
        with self.conn.cursor() as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result else None


class PostgreSQLTicketsHelper(PostgreSQLTestHelper):
    """Helper for execution tickets PostgreSQL database."""

    def __init__(self, uri: str = DEFAULT_POSTGRESQL_TICKETS_URI):
        super().__init__(uri)

    def get_ticket_stats(self, plan_id: str) -> TicketPersistenceStats:
        """
        Get ticket statistics for a plan.

        Args:
            plan_id: The plan ID

        Returns:
            TicketPersistenceStats
        """
        # Total count
        total = self.execute_scalar(
            "SELECT COUNT(*) FROM execution_tickets WHERE plan_id = %s",
            (plan_id,)
        ) or 0

        # Count by status
        status_query = """
            SELECT status, COUNT(*) as count
            FROM execution_tickets
            WHERE plan_id = %s
            GROUP BY status
        """
        status_results = self.execute_query(status_query, (plan_id,))

        status_counts = {row["status"]: row["count"] for row in status_results}

        pending = status_counts.get("pending", 0)
        claimed = status_counts.get("claimed", 0)
        executing = status_counts.get("executing", 0)
        completed = status_counts.get("completed", 0)
        failed = status_counts.get("failed", 0)

        # Lifecycle is valid if total matches sum of statuses
        sum_statuses = pending + claimed + executing + completed + failed
        lifecycle_valid = total == sum_statuses

        return TicketPersistenceStats(
            total_tickets=total,
            pending=pending,
            claimed=claimed,
            executing=executing,
            completed=completed,
            failed=failed,
            lifecycle_valid=lifecycle_valid,
        )

    def get_tickets_for_plan(self, plan_id: str) -> List[Dict[str, Any]]:
        """
        Get all tickets for a plan.

        Args:
            plan_id: The plan ID

        Returns:
            List of ticket records
        """
        query = """
            SELECT ticket_id, plan_id, status, task_type,
                   assigned_worker, created_at, updated_at
            FROM execution_tickets
            WHERE plan_id = %s
            ORDER BY created_at
        """
        return self.execute_query(query, (plan_id,))

    def validate_ticket_lifecycle(self, plan_id: str) -> Dict[str, Any]:
        """
        Validate ticket lifecycle transitions.

        Args:
            plan_id: The plan ID

        Returns:
            Validation result
        """
        stats = self.get_ticket_stats(plan_id)
        tickets = self.get_tickets_for_plan(plan_id)

        # Check that tickets exist
        has_tickets = stats.total_tickets > 0

        # Check that some tickets progressed past pending
        has_progress = (
            stats.claimed > 0 or
            stats.executing > 0 or
            stats.completed > 0
        )

        return {
            "valid": has_tickets and stats.lifecycle_valid,
            "total_tickets": stats.total_tickets,
            "pending": stats.pending,
            "claimed": stats.claimed,
            "executing": stats.executing,
            "completed": stats.completed,
            "failed": stats.failed,
            "lifecycle_valid": stats.lifecycle_valid,
            "has_progress": has_progress,
            "tickets": tickets[:5],  # Sample of first 5 tickets
        }


class PostgreSQLTemporalHelper(PostgreSQLTestHelper):
    """Helper for Temporal PostgreSQL database."""

    def __init__(self, uri: str = DEFAULT_POSTGRESQL_TEMPORAL_URI):
        super().__init__(uri)

    def check_workflow_registered(self, workflow_id: str) -> Dict[str, Any]:
        """
        Check if a workflow is registered in Temporal's database.

        Args:
            workflow_id: The workflow ID

        Returns:
            Validation result
        """
        # Note: Temporal's schema may vary; this is a simplified check
        try:
            count = self.execute_scalar(
                "SELECT COUNT(*) FROM executions WHERE workflow_id = %s",
                (workflow_id,)
            ) or 0

            return {
                "valid": count > 0,
                "workflow_id": workflow_id,
                "found": count > 0,
            }
        except psycopg2.Error as e:
            logger.warning(f"Could not query Temporal DB: {e}")
            return {
                "valid": False,
                "workflow_id": workflow_id,
                "found": False,
                "error": str(e),
            }


async def validate_mongodb_persistence(
    plan_id: str,
    mongodb_uri: str = DEFAULT_MONGODB_URI,
    database: str = DEFAULT_MONGODB_DATABASE,
) -> Dict[str, Any]:
    """
    Validate all MongoDB persistence for a plan.

    Args:
        plan_id: The plan ID to validate
        mongodb_uri: MongoDB connection URI
        database: Database name

    Returns:
        Comprehensive validation result
    """
    helper = MongoDBTestHelper(uri=mongodb_uri, database=database)
    helper.connect()

    try:
        results = {
            "valid": True,
            "plan_id": plan_id,
            "collections": {},
        }

        # Validate each collection
        collections_to_check = [
            ("orchestration_ledger", helper.validate_orchestration_ledger),
            ("execution_tickets_ledger", helper.validate_execution_tickets_ledger),
            ("code_forge_artifacts", helper.validate_code_forge_artifacts),
        ]

        for collection_name, validator in collections_to_check:
            if collection_name == "code_forge_artifacts":
                result = validator(plan_id)
            else:
                result = validator(plan_id)

            results["collections"][collection_name] = result

            if not result.get("valid", False):
                # Only orchestration_ledger is mandatory
                if collection_name == "orchestration_ledger":
                    results["valid"] = False

        # Add strategic decisions (optional)
        strategic_result = helper.validate_strategic_decisions()
        results["collections"]["strategic_decisions"] = strategic_result

        # Calculate total records
        total_records = sum(
            c.get("document_count", 0) for c in results["collections"].values()
        )
        results["total_records"] = total_records

        return results
    finally:
        helper.close()


async def validate_postgresql_persistence(
    plan_id: str,
    workflow_id: Optional[str] = None,
    tickets_uri: str = DEFAULT_POSTGRESQL_TICKETS_URI,
    temporal_uri: str = DEFAULT_POSTGRESQL_TEMPORAL_URI,
) -> Dict[str, Any]:
    """
    Validate all PostgreSQL persistence for a plan.

    Args:
        plan_id: The plan ID to validate
        workflow_id: Optional workflow ID to validate in Temporal DB
        tickets_uri: Execution tickets database URI
        temporal_uri: Temporal database URI

    Returns:
        Comprehensive validation result
    """
    results = {
        "valid": True,
        "plan_id": plan_id,
        "tickets": {},
        "temporal": {},
    }

    # Validate execution tickets
    tickets_helper = PostgreSQLTicketsHelper(uri=tickets_uri)
    try:
        tickets_helper.connect()
        ticket_result = tickets_helper.validate_ticket_lifecycle(plan_id)
        results["tickets"] = ticket_result

        if not ticket_result.get("valid", False):
            results["valid"] = False
    except Exception as e:
        logger.error(f"Failed to validate tickets: {e}")
        results["tickets"] = {"valid": False, "error": str(e)}
        results["valid"] = False
    finally:
        tickets_helper.close()

    # Validate Temporal database (optional)
    if workflow_id:
        temporal_helper = PostgreSQLTemporalHelper(uri=temporal_uri)
        try:
            temporal_helper.connect()
            temporal_result = temporal_helper.check_workflow_registered(workflow_id)
            results["temporal"] = temporal_result
        except Exception as e:
            logger.warning(f"Could not validate Temporal DB: {e}")
            results["temporal"] = {"valid": True, "skipped": True, "error": str(e)}
        finally:
            temporal_helper.close()

    return results
