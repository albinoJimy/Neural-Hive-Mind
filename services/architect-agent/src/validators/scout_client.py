"""Cliente HTTP para Scout Agents."""

import httpx
from typing import Dict, Any
from src.config.settings import get_settings


class ScoutAgentsClient:
    """Cliente para comunicação com Scout Agents."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.scout_agents.url
        self.timeout = settings.scout_agents.timeout_seconds

    async def get_patterns(
        self, repo_url: str, branch: str = "main"
    ) -> list[Dict[str, Any]]:
        """Obtém padrões de código detectados."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/patterns",
                params={"repo_url": repo_url, "branch": branch}
            )
            response.raise_for_status()
            return response.json().get("patterns", [])

    async def get_insights(
        self, repo_url: str, branch: str = "main"
    ) -> Dict[str, Any]:
        """Obtém insights de análise do código."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/insights",
                params={"repo_url": repo_url, "branch": branch}
            )
            response.raise_for_status()
            return response.json()

    async def check_duplication(
        self, repo_url: str, branch: str = "main"
    ) -> Dict[str, Any]:
        """Verifica duplicação de código."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/duplication",
                params={"repo_url": repo_url, "branch": branch}
            )
            response.raise_for_status()
            return response.json()
