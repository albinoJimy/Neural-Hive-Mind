"""Cliente HTTP para Open Policy Agent."""

from typing import Any

import httpx

from src.config.settings import get_settings


class OPAClient:
    """Cliente para comunicação com OPA."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.opa.url
        self.timeout = settings.opa.timeout_seconds
        self.policy_path = settings.opa.policy_path

    async def evaluate_policy(self, policy_path: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Avalia política no OPA."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/data/{policy_path}", json={"input": input_data}
            )
            response.raise_for_status()
            return response.json()

    async def check_architecture_rules(
        self, patterns: list[dict[str, Any]], insights: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Verifica regras arquiteturais no OPA."""
        input_data = {"patterns": patterns, "insights": insights}
        result = await self.evaluate_policy(self.policy_path, input_data)
        return result.get("violations", [])
