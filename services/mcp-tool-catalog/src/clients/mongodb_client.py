"""MongoDB client for tool catalog persistence."""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from src.models.tool_descriptor import ToolCategory, ToolDescriptor

logger = structlog.get_logger()


class MongoDBClient:
    """Async MongoDB client using Motor."""

    def __init__(
        self,
        mongodb_url: str,
        database_name: str,
        server_selection_timeout_ms: int = 5000,
        connect_timeout_ms: int = 10000,
        socket_timeout_ms: int = 10000,
    ):
        """Initialize MongoDB client.

        Args:
            mongodb_url: MongoDB connection URL
            database_name: Database name
            server_selection_timeout_ms: Server selection timeout in milliseconds
            connect_timeout_ms: Connection timeout in milliseconds
            socket_timeout_ms: Socket timeout in milliseconds
        """
        self.mongodb_url = mongodb_url
        self.database_name = database_name
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self.connect_timeout_ms = connect_timeout_ms
        self.socket_timeout_ms = socket_timeout_ms
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0):
        """Connect to MongoDB with retry logic.

        Args:
            max_retries: Maximum number of connection attempts
            initial_delay: Initial delay between retries (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "connecting_to_mongodb",
                    url=self.mongodb_url,
                    database=self.database_name,
                    attempt=attempt + 1,
                )

                self.client = AsyncIOMotorClient(
                    self.mongodb_url,
                    serverSelectionTimeoutMS=self.server_selection_timeout_ms,
                    connectTimeoutMS=self.connect_timeout_ms,
                    socketTimeoutMS=self.socket_timeout_ms,
                )

                # Test connection
                await self.client.admin.command("ping")

                self.db = self.client[self.database_name]

                # Create indexes (non-critical, continue if fails)
                try:
                    await self._create_indexes()
                except Exception as idx_err:
                    logger.warning(
                        "mongodb_indexes_creation_failed",
                        error=str(idx_err),
                        note="Continuing without indexes - may affect query performance",
                    )

                logger.info("mongodb_connected")
                return

            except Exception as e:
                delay = initial_delay * (2**attempt)  # Exponential backoff
                logger.warning(
                    "mongodb_connection_failed",
                    error=str(e),
                    attempt=attempt + 1,
                    retry_in_seconds=delay,
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("mongodb_connection_exhausted_retries")
                    raise

    async def stop(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("mongodb_disconnected")

    async def _create_indexes(self):
        """Create necessary indexes."""
        tools_collection = self.db.tools

        # Unique index on tool_id
        await tools_collection.create_index("tool_id", unique=True)

        # Index on category
        await tools_collection.create_index("category")

        # Index on reputation_score (descending for performance)
        await tools_collection.create_index([("reputation_score", DESCENDING)])

        # Multikey index on capabilities
        await tools_collection.create_index("capabilities")

        logger.info("mongodb_indexes_created")

    async def save_tool(self, tool: ToolDescriptor) -> str:
        """Save or update tool in catalog.

        Args:
            tool: Tool descriptor to save

        Returns:
            Tool ID
        """
        tool_dict = tool.to_dict()

        await self.db.tools.update_one(
            {"tool_id": tool.tool_id}, {"$set": tool_dict}, upsert=True
        )

        logger.debug("tool_saved", tool_id=tool.tool_id, tool_name=tool.tool_name)
        return tool.tool_id

    async def get_tool(self, tool_id: str) -> Optional[ToolDescriptor]:
        """Get tool by ID.

        Args:
            tool_id: Tool unique identifier

        Returns:
            ToolDescriptor if found, None otherwise
        """
        tool_dict = await self.db.tools.find_one({"tool_id": tool_id})

        if not tool_dict:
            return None

        return ToolDescriptor.from_avro(tool_dict)

    async def list_tools(
        self, category: Optional[ToolCategory] = None, filters: Optional[Dict] = None
    ) -> List[ToolDescriptor]:
        """List tools with optional filters.

        Args:
            category: Filter by category
            filters: Additional MongoDB filters

        Returns:
            List of tool descriptors
        """
        query = filters or {}

        if category:
            query["category"] = category.value

        cursor = self.db.tools.find(query).sort("reputation_score", DESCENDING)

        tools = []
        async for tool_dict in cursor:
            tools.append(ToolDescriptor.from_avro(tool_dict))

        return tools

    async def update_tool_reputation(self, tool_id: str, new_score: float) -> bool:
        """Update tool reputation score.

        Uses exponential moving average: new_reputation = (old * 0.9) + (feedback * 0.1)

        Args:
            tool_id: Tool unique identifier
            new_score: New feedback score (0.0-1.0)

        Returns:
            True if updated successfully
        """
        tool = await self.get_tool(tool_id)
        if not tool:
            logger.warning("tool_not_found_for_reputation_update", tool_id=tool_id)
            return False

        # Exponential moving average
        updated_reputation = (tool.reputation_score * 0.9) + (new_score * 0.1)

        result = await self.db.tools.update_one(
            {"tool_id": tool_id},
            {
                "$set": {
                    "reputation_score": updated_reputation,
                    "updated_at": int(datetime.utcnow().timestamp() * 1000),
                }
            },
        )

        logger.info(
            "tool_reputation_updated",
            tool_id=tool_id,
            old_score=tool.reputation_score,
            new_score=updated_reputation,
        )

        return result.modified_count > 0

    async def save_selection_history(self, request: Dict, response: Dict) -> str:
        """Save selection history for learning.

        Args:
            request: Tool selection request
            response: Tool selection response

        Returns:
            History entry ID
        """
        history_entry = {
            "request_id": request.get("request_id"),
            "ticket_id": request.get("ticket_id"),
            "artifact_type": request.get("artifact_type"),
            "language": request.get("language"),
            "complexity_score": request.get("complexity_score"),
            "selected_tools": response.get("selected_tools"),
            "total_fitness_score": response.get("total_fitness_score"),
            "selection_method": response.get("selection_method"),
            "cached": response.get("cached", False),
            "created_at": int(datetime.utcnow().timestamp() * 1000),
        }

        result = await self.db.selections_history.insert_one(history_entry)
        return str(result.inserted_id)

    async def get_selection_history(self, filters: Optional[Dict] = None) -> List[Dict]:
        """Query selection history.

        Args:
            filters: MongoDB query filters

        Returns:
            List of history entries
        """
        query = filters or {}
        cursor = self.db.selections_history.find(query).sort("created_at", DESCENDING).limit(100)

        history = []
        async for entry in cursor:
            history.append(entry)

        return history

    async def get_tool_usage_stats(self, tool_id: str) -> Dict:
        """Get tool usage statistics.

        Args:
            tool_id: Tool unique identifier

        Returns:
            Usage statistics
        """
        pipeline = [
            {"$unwind": "$selected_tools"},
            {"$match": {"selected_tools.tool_id": tool_id}},
            {
                "$group": {
                    "_id": tool_id,
                    "usage_count": {"$sum": 1},
                    "avg_fitness": {"$avg": "$total_fitness_score"},
                }
            },
        ]

        cursor = self.db.selections_history.aggregate(pipeline)
        stats = await cursor.to_list(length=1)

        if not stats:
            return {"usage_count": 0, "avg_fitness": 0.0}

        return stats[0]
