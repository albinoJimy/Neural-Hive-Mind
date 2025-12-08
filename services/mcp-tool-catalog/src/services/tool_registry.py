"""Tool Registry service for managing 87 MCP tools."""
from typing import Dict, List, Optional

import structlog

from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient
from src.models.tool_descriptor import ToolCategory, ToolDescriptor
from src.services.tool_catalog_bootstrap import ToolCatalogBootstrap

logger = structlog.get_logger()


class ToolRegistry:
    """Registry for managing MCP tool catalog."""

    def __init__(self, mongodb_client: MongoDBClient, redis_client: RedisClient, metrics=None):
        """Initialize Tool Registry."""
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.bootstrap = ToolCatalogBootstrap()
        self.metrics = metrics

    async def bootstrap_initial_catalog(self):
        """Bootstrap catalog with initial 87 tools."""
        # Check if catalog already populated
        existing_tools = await self.mongodb_client.list_tools()

        if len(existing_tools) >= 87:
            logger.info("tool_catalog_already_populated", count=len(existing_tools))
            return

        logger.info("bootstrapping_tool_catalog")

        # Get initial tool definitions
        initial_tools = self.bootstrap.get_initial_tools()

        # Save each tool
        for tool in initial_tools:
            await self.mongodb_client.save_tool(tool)

        logger.info("tool_catalog_bootstrapped", total_tools=len(initial_tools))

        # Update metrics
        await self._update_metrics()

    async def register_tool(self, tool: ToolDescriptor) -> str:
        """Register new tool in catalog."""
        tool_id = await self.mongodb_client.save_tool(tool)

        # Invalidate relevant caches
        await self.redis_client.invalidate_cache(f"mcp:tools:category:{tool.category.value}*")

        logger.info("tool_registered", tool_id=tool_id, tool_name=tool.tool_name)
        return tool_id

    async def update_tool(self, tool_id: str, updates: Dict) -> bool:
        """Update existing tool."""
        tool = await self.mongodb_client.get_tool(tool_id)
        if not tool:
            logger.warning("tool_not_found_for_update", tool_id=tool_id)
            return False

        # Apply updates
        for key, value in updates.items():
            if hasattr(tool, key):
                setattr(tool, key, value)

        await self.mongodb_client.save_tool(tool)

        # Invalidate caches
        await self.redis_client.invalidate_cache(f"mcp:tools:*")

        logger.info("tool_updated", tool_id=tool_id)
        return True

    async def deactivate_tool(self, tool_id: str) -> bool:
        """Deactivate tool (soft delete)."""
        result = await self.mongodb_client.db.tools.update_one(
            {"tool_id": tool_id},
            {"$set": {"metadata.active": False}}
        )

        if result.modified_count > 0:
            # Invalidate caches
            await self.redis_client.invalidate_cache("mcp:tool:*")
            logger.info("tool_deactivated", tool_id=tool_id)
            return True

        logger.warning("tool_not_found_for_deactivation", tool_id=tool_id)
        return False

    async def get_tool(self, tool_id: str) -> Optional[ToolDescriptor]:
        """Get tool by ID with Redis caching."""
        # Try cache first
        cache_key = f"mcp:tool:{tool_id}"
        # Simplified caching - should implement proper serialization
        tool = await self.mongodb_client.get_tool(tool_id)
        return tool

    async def list_tools_by_category(self, category: ToolCategory) -> List[ToolDescriptor]:
        """List tools by category."""
        return await self.mongodb_client.list_tools(category=category)

    async def search_tools(self, query: str, filters: Optional[Dict] = None) -> List[ToolDescriptor]:
        """Search tools by text query and filters."""
        # Simplified search - should implement full-text search
        mongo_filters = filters or {}
        return await self.mongodb_client.list_tools(filters=mongo_filters)

    async def get_tools_by_capabilities(self, capabilities: List[str]) -> List[ToolDescriptor]:
        """Get tools matching required capabilities."""
        filters = {"capabilities": {"$all": capabilities}}
        return await self.mongodb_client.list_tools(filters=filters)

    async def update_tool_reputation(self, tool_id: str, success: bool) -> bool:
        """Update tool reputation based on feedback.

        Args:
            tool_id: Tool identifier
            success: Whether execution was successful

        Returns:
            True if updated successfully
        """
        feedback_score = 1.0 if success else 0.0
        updated = await self.mongodb_client.update_tool_reputation(tool_id, feedback_score)

        if updated:
            # Invalidate caches
            await self.redis_client.invalidate_cache(f"mcp:tool:{tool_id}")

        return updated

    async def get_tool_statistics(self, tool_id: str) -> Dict:
        """Get usage statistics for a tool."""
        stats = await self.mongodb_client.get_tool_usage_stats(tool_id)
        usage_count = await self.redis_client.get_tool_usage(tool_id)

        return {
            **stats,
            "redis_usage_count": usage_count,
        }

    async def get_all_tools(self) -> List[ToolDescriptor]:
        """Get all tools from catalog."""
        return await self.mongodb_client.list_tools()

    async def get_tool_by_id(self, tool_id: str) -> Optional[ToolDescriptor]:
        """Get tool by ID (alias for get_tool)."""
        return await self.get_tool(tool_id)

    async def get_tools_by_category(self, category: ToolCategory) -> List[ToolDescriptor]:
        """Get tools by category (alias for list_tools_by_category)."""
        return await self.list_tools_by_category(category)

    async def _update_metrics(self):
        """Update Prometheus metrics for tool registry."""
        if not self.metrics:
            return

        # Update metrics per category
        for category in ToolCategory:
            tools = await self.list_tools_by_category(category)
            total_count = len(tools)

            # Count healthy tools (check Redis health)
            healthy_count = 0
            for tool in tools:
                health = await self.redis_client.get_tool_health(tool.tool_id)
                if health is None or health is True:
                    healthy_count += 1

                self.metrics.update_tool_registry(
                    category=category.value,
                    total=total_count,
                    healthy=healthy_count
                )

        logger.debug("tool_registry_metrics_updated")

    async def update_tool_metrics(
        self,
        tool_id: str,
        category: str,
        success: bool,
        execution_time_ms: int,
        metadata: Dict
    ) -> None:
        """Atualiza métricas de feedback de ferramentas."""
        try:
            await self.redis_client.increment_tool_usage(tool_id)
            await self.redis_client.increment_tool_feedback(tool_id, success)

            if self.metrics:
                status = "success" if success else "failure"
                duration_seconds = max(execution_time_ms, 0) / 1000.0
                self.metrics.record_tool_execution(
                    tool_id=tool_id,
                    category=category,
                    status=status,
                    duration=duration_seconds
                )
                self.metrics.record_feedback(tool_id, success)

            await self.update_tool_reputation(tool_id, success)
            logger.info(
                "tool_metrics_updated",
                tool_id=tool_id,
                category=category,
                success=success,
                execution_time_ms=execution_time_ms,
                metadata=metadata
            )
        except Exception as e:
            logger.warning("update_tool_metrics_failed", tool_id=tool_id, error=str(e))
