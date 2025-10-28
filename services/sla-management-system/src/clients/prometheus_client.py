"""
Cliente para Prometheus HTTP API.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import httpx
import structlog

from ..config.settings import PrometheusSettings
from ..models.slo_definition import SLODefinition


class PrometheusQueryError(Exception):
    """Erro em query ao Prometheus."""
    pass


class PrometheusConnectionError(Exception):
    """Erro de conexão com Prometheus."""
    pass


class PrometheusClient:
    """Cliente para Prometheus HTTP API."""

    def __init__(self, settings: PrometheusSettings):
        self.base_url = settings.url
        self.timeout = settings.timeout_seconds
        self.max_retries = settings.max_retries
        self.session: Optional[httpx.AsyncClient] = None
        self.logger = structlog.get_logger(__name__)

    async def connect(self):
        """Inicializa cliente HTTP."""
        self.session = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        self.logger.info("prometheus_client_connected", base_url=self.base_url)

    async def disconnect(self):
        """Fecha cliente HTTP."""
        if self.session:
            await self.session.aclose()
            self.logger.info("prometheus_client_disconnected")

    async def query(
        self,
        query: str,
        time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Executa query PromQL instantânea."""
        params = {"query": query}
        if time:
            params["time"] = time.isoformat()

        for attempt in range(self.max_retries):
            try:
                response = await self.session.get("/api/v1/query", params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "success":
                    raise PrometheusQueryError(
                        f"Query failed: {data.get('error', 'unknown error')}"
                    )

                return data.get("data", {})

            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise PrometheusConnectionError(f"Failed after {self.max_retries} retries: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "1m"
    ) -> Dict[str, Any]:
        """Executa query PromQL em range temporal."""
        params = {
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": step
        }

        for attempt in range(self.max_retries):
            try:
                response = await self.session.get("/api/v1/query_range", params=params)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "success":
                    raise PrometheusQueryError(
                        f"Query range failed: {data.get('error', 'unknown error')}"
                    )

                return data.get("data", {})

            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise PrometheusConnectionError(f"Failed after {self.max_retries} retries: {e}")
                await asyncio.sleep(2 ** attempt)

    async def calculate_sli(
        self,
        slo_definition: SLODefinition,
        window_days: int = 30
    ) -> float:
        """Calcula SLI atual baseado na definição do SLO."""
        end = datetime.utcnow()
        start = end - timedelta(days=window_days)

        try:
            result = await self.query_range(
                query=slo_definition.sli_query.query,
                start=start,
                end=end,
                step="5m"
            )

            # Extrai valor agregado
            if result.get("resultType") == "matrix":
                results = result.get("result", [])
                if results:
                    # Pega último valor da primeira série
                    values = results[0].get("values", [])
                    if values:
                        # values[-1] = [timestamp, value]
                        sli_value = float(values[-1][1])
                        self.logger.info(
                            "sli_calculated",
                            slo_id=slo_definition.slo_id,
                            sli_value=sli_value
                        )
                        return sli_value

            self.logger.warning(
                "sli_calculation_no_data",
                slo_id=slo_definition.slo_id
            )
            return slo_definition.target  # Default to target if no data

        except Exception as e:
            self.logger.error(
                "sli_calculation_failed",
                slo_id=slo_definition.slo_id,
                error=str(e)
            )
            raise

    async def calculate_error_rate(
        self,
        service: str,
        window_days: int = 30
    ) -> float:
        """Calcula taxa de erro para um serviço."""
        query = f'''
        sum(rate(neural_hive_request_errors_total{{service="{service}"}}[{window_days}d])) /
        sum(rate(neural_hive_requests_total{{service="{service}"}}[{window_days}d]))
        '''

        try:
            result = await self.query(query)
            if result.get("resultType") == "vector":
                results = result.get("result", [])
                if results:
                    return float(results[0].get("value", [0, 0])[1])
            return 0.0

        except Exception as e:
            self.logger.error(
                "error_rate_calculation_failed",
                service=service,
                error=str(e)
            )
            return 0.0

    async def calculate_burn_rate(
        self,
        service: str,
        window_hours: int,
        baseline_days: int = 30
    ) -> float:
        """Calcula burn rate comparando janela curta vs baseline."""
        # Error rate na janela curta
        query_window = f'''
        sum(rate(neural_hive_request_errors_total{{service="{service}"}}[{window_hours}h])) /
        sum(rate(neural_hive_requests_total{{service="{service}"}}[{window_hours}h]))
        '''

        # Error rate no baseline
        query_baseline = f'''
        sum(rate(neural_hive_request_errors_total{{service="{service}"}}[{baseline_days}d])) /
        sum(rate(neural_hive_requests_total{{service="{service}"}}[{baseline_days}d]))
        '''

        try:
            error_rate_window = 0.0
            error_rate_baseline = 0.0

            # Query window
            result_window = await self.query(query_window)
            if result_window.get("resultType") == "vector":
                results = result_window.get("result", [])
                if results:
                    error_rate_window = float(results[0].get("value", [0, 0])[1])

            # Query baseline
            result_baseline = await self.query(query_baseline)
            if result_baseline.get("resultType") == "vector":
                results = result_baseline.get("result", [])
                if results:
                    error_rate_baseline = float(results[0].get("value", [0, 0])[1])

            # Calcula burn rate
            if error_rate_baseline > 0:
                burn_rate = (error_rate_window / error_rate_baseline) * \
                           (baseline_days * 24 / window_hours)
                return burn_rate

            return 0.0

        except Exception as e:
            self.logger.error(
                "burn_rate_calculation_failed",
                service=service,
                window_hours=window_hours,
                error=str(e)
            )
            return 0.0

    async def health_check(self) -> bool:
        """Verifica conectividade com Prometheus."""
        try:
            response = await self.session.get("/-/healthy")
            return response.status_code == 200
        except Exception as e:
            self.logger.error("prometheus_health_check_failed", error=str(e))
            return False
