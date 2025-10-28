"""Client for MCP Tool Catalog Service."""
from typing import Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()


class MCPToolCatalogClient:
    """REST client for MCP Tool Catalog Service."""

    def __init__(self, host: str = "mcp-tool-catalog", port: int = 8080):
        """Initialize MCP Tool Catalog client."""
        self.base_url = f"http://{host}:{port}"
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Initialize HTTP client."""
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        logger.info("mcp_tool_catalog_client_initialized", base_url=self.base_url)

    async def stop(self):
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()

    async def request_tool_selection(self, request_data: Dict) -> Optional[Dict]:
        """Request tool selection via synchronous REST API.

        Args:
            request_data: Tool selection request (ToolSelectionRequest format)

        Returns:
            Tool selection response dict or None if failed
        """
        try:
            response = await self.client.post("/api/v1/selections", json=request_data)
            response.raise_for_status()
            result = response.json()

            logger.info(
                "tool_selection_received",
                request_id=request_data.get("request_id"),
                selected_tools_count=len(result.get("selected_tools", [])),
                selection_method=result.get("selection_method"),
            )

            return result

        except httpx.HTTPError as e:
            logger.error(
                "tool_selection_request_failed",
                error=str(e),
                request_id=request_data.get("request_id"),
            )
            return None

    async def get_tool(self, tool_id: str) -> Optional[Dict]:
        """Get tool descriptor by ID."""
        try:
            response = await self.client.get(f"/api/v1/tools/{tool_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None

    async def list_tools(self, category: Optional[str] = None) -> List[Dict]:
        """List tools, optionally filtered by category."""
        try:
            params = {"category": category} if category else {}
            response = await self.client.get("/api/v1/tools", params=params)
            response.raise_for_status()
            return response.json().get("tools", [])
        except httpx.HTTPError:
            return []

    async def send_tool_feedback(self, tool_id: str, success: bool, metadata: Dict):
        """Send feedback about tool execution."""
        try:
            feedback_data = {"tool_id": tool_id, "success": success, "metadata": metadata}
            await self.client.post(f"/api/v1/tools/{tool_id}/feedback", json=feedback_data)

            logger.info("tool_feedback_sent", tool_id=tool_id, success=success)

        except httpx.HTTPError as e:
            logger.warning("tool_feedback_failed", error=str(e), tool_id=tool_id)
