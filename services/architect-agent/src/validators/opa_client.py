"""Cliente HTTP para Open Policy Agent."""

import httpx
from typing import Dict, Any
from src.config.settings import get_settings


class OPAClient:
    """Cliente para comunicação com OPA."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.opa.url
        self.timeout = settings.opa.timeout_seconds

    async def evaluate_policy(
        self, policy_path: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Avalia política no OPA."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/data/{policy_path}",
                json={"input": input_data}
            )
            response.raise_for_status()
            return response.json()

    async def check_architecture_rules(
        self, patterns: list[Dict[str, Any]], insights: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        """Verifica regras arquiteturais no OPA."""
        input_data = {
            "patterns": patterns,
            "insights": insights
        }
        result = await self.evaluate_policy("architecture/rules", input_data)
        return result.get("violations", [])
