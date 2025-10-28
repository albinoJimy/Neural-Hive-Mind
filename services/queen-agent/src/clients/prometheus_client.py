import structlog
import httpx
from typing import Any, Dict, List
from datetime import datetime

from ..config import Settings


logger = structlog.get_logger()


class PrometheusClient:
    """Cliente Prometheus para consultar métricas agregadas"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.PROMETHEUS_URL
        self.timeout = settings.PROMETHEUS_QUERY_TIMEOUT_SECONDS

    async def query(self, query: str) -> Dict[str, Any]:
        """Executar query PromQL"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/query",
                    params={"query": query}
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error("prometheus_query_failed", query=query, error=str(e))
            return {"status": "error", "data": {}}

    async def get_sla_compliance(self, service: str, window: str = "5m") -> float:
        """Obter compliance de SLA de um serviço"""
        query = f'sum(rate(http_requests_total{{service="{service}",status=~"2.."}}[{window}])) / sum(rate(http_requests_total{{service="{service}"}}[{window}]))'
        result = await self.query(query)

        if result.get("status") == "success" and result.get("data", {}).get("result"):
            return float(result["data"]["result"][0]["value"][1])

        return 0.0

    async def get_error_rates(self, services: List[str]) -> Dict[str, float]:
        """Obter taxas de erro de múltiplos serviços"""
        error_rates = {}

        for service in services:
            query = f'sum(rate(http_requests_total{{service="{service}",status=~"5.."}}[5m])) by (service)'
            result = await self.query(query)

            if result.get("status") == "success" and result.get("data", {}).get("result"):
                error_rates[service] = float(result["data"]["result"][0]["value"][1])
            else:
                error_rates[service] = 0.0

        return error_rates

    async def get_resource_saturation(self) -> Dict[str, float]:
        """Obter saturação de recursos"""
        saturation = {}

        # CPU
        cpu_query = 'avg(node_cpu_seconds_total)'
        cpu_result = await self.query(cpu_query)
        if cpu_result.get("status") == "success" and cpu_result.get("data", {}).get("result"):
            saturation['cpu'] = float(cpu_result["data"]["result"][0]["value"][1])
        else:
            saturation['cpu'] = 0.0

        # Memory
        mem_query = 'avg(node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)'
        mem_result = await self.query(mem_query)
        if mem_result.get("status") == "success" and mem_result.get("data", {}).get("result"):
            saturation['memory'] = 1.0 - float(mem_result["data"]["result"][0]["value"][1])
        else:
            saturation['memory'] = 0.0

        return saturation
