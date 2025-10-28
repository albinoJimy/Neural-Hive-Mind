"""Cliente HTTP para consultas ao Prometheus"""
from typing import Dict, Any, Optional, List
import httpx
import structlog
from datetime import datetime, timedelta, timezone

logger = structlog.get_logger()


class PrometheusClient:
    """
    Cliente HTTP para consultas ao Prometheus.
    Usado para validação de SLA e coleta de métricas pós-remediação.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        """Inicializa cliente HTTP assíncrono"""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )

        # Verifica conectividade
        try:
            response = await self._client.get("/-/healthy")
            if response.status_code == 200:
                logger.info("prometheus_client.connected", base_url=self.base_url)
            else:
                logger.warning(
                    "prometheus_client.health_check_failed",
                    status_code=response.status_code
                )
        except Exception as e:
            logger.error(
                "prometheus_client.connect_failed",
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def close(self):
        """Fecha cliente HTTP"""
        if self._client:
            await self._client.aclose()
            logger.info("prometheus_client.closed")

    async def query(
        self,
        query: str,
        time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Executa query instantânea no Prometheus.

        Args:
            query: PromQL query
            time: Timestamp para avaliação (default: now)

        Returns:
            Dict com resultado da query
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            params = {"query": query}
            if time:
                params["time"] = time.timestamp()

            response = await self._client.get("/api/v1/query", params=params)
            response.raise_for_status()

            result = response.json()

            if result.get("status") != "success":
                logger.error(
                    "prometheus_client.query_failed",
                    query=query,
                    error=result.get("error")
                )
                return {"status": "error", "data": {}}

            return result

        except Exception as e:
            logger.error(
                "prometheus_client.query_error",
                query=query,
                error=str(e)
            )
            raise

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s"
    ) -> Dict[str, Any]:
        """
        Executa range query no Prometheus.

        Args:
            query: PromQL query
            start: Início do período
            end: Fim do período
            step: Intervalo entre pontos

        Returns:
            Dict com série temporal
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            params = {
                "query": query,
                "start": start.timestamp(),
                "end": end.timestamp(),
                "step": step
            }

            response = await self._client.get("/api/v1/query_range", params=params)
            response.raise_for_status()

            result = response.json()

            if result.get("status") != "success":
                logger.error(
                    "prometheus_client.range_query_failed",
                    query=query,
                    error=result.get("error")
                )
                return {"status": "error", "data": {}}

            return result

        except Exception as e:
            logger.error(
                "prometheus_client.range_query_error",
                query=query,
                error=str(e)
            )
            raise

    async def get_availability_metrics(
        self,
        service: str,
        lookback_minutes: int = 5
    ) -> Dict[str, float]:
        """
        Obtém métricas de disponibilidade de um serviço.

        Args:
            service: Nome do serviço
            lookback_minutes: Janela de tempo para análise

        Returns:
            Dict com success_rate, latency_p99, error_rate
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=lookback_minutes)

        metrics = {}

        try:
            # Taxa de sucesso
            success_query = f'rate(http_requests_total{{service="{service}",status=~"2.."}}[{lookback_minutes}m])'
            total_query = f'rate(http_requests_total{{service="{service}"}}[{lookback_minutes}m])'

            success_result = await self.query(success_query)
            total_result = await self.query(total_query)

            success_rate = self._extract_value(success_result)
            total_rate = self._extract_value(total_result)

            if total_rate and total_rate > 0:
                metrics["success_rate"] = (success_rate / total_rate) * 100
            else:
                metrics["success_rate"] = 100.0

            # Latência P99
            latency_query = f'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{service="{service}"}}[{lookback_minutes}m]))'
            latency_result = await self.query(latency_query)
            metrics["latency_p99"] = self._extract_value(latency_result)

            # Taxa de erro
            error_query = f'rate(http_requests_total{{service="{service}",status=~"5.."}}[{lookback_minutes}m])'
            error_result = await self.query(error_query)
            error_rate = self._extract_value(error_result)

            if total_rate and total_rate > 0:
                metrics["error_rate"] = (error_rate / total_rate) * 100
            else:
                metrics["error_rate"] = 0.0

            logger.info(
                "prometheus_client.availability_metrics",
                service=service,
                metrics=metrics
            )

            return metrics

        except Exception as e:
            logger.error(
                "prometheus_client.availability_metrics_failed",
                service=service,
                error=str(e)
            )
            return {
                "success_rate": 0.0,
                "latency_p99": 0.0,
                "error_rate": 100.0
            }

    async def validate_sla_restoration(
        self,
        service: str,
        sla_targets: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Valida se SLA foi restaurado após remediação.

        Args:
            service: Nome do serviço
            sla_targets: Alvos de SLA (default: 99.9% success, <500ms p99, <0.1% error)

        Returns:
            Dict com resultado da validação
        """
        if not sla_targets:
            sla_targets = {
                "min_success_rate": 99.9,
                "max_latency_p99": 0.5,  # 500ms
                "max_error_rate": 0.1
            }

        metrics = await self.get_availability_metrics(service, lookback_minutes=2)

        violations = []

        if metrics["success_rate"] < sla_targets["min_success_rate"]:
            violations.append({
                "metric": "success_rate",
                "value": metrics["success_rate"],
                "target": sla_targets["min_success_rate"]
            })

        if metrics["latency_p99"] > sla_targets["max_latency_p99"]:
            violations.append({
                "metric": "latency_p99",
                "value": metrics["latency_p99"],
                "target": sla_targets["max_latency_p99"]
            })

        if metrics["error_rate"] > sla_targets["max_error_rate"]:
            violations.append({
                "metric": "error_rate",
                "value": metrics["error_rate"],
                "target": sla_targets["max_error_rate"]
            })

        sla_restored = len(violations) == 0

        result = {
            "sla_restored": sla_restored,
            "metrics": metrics,
            "targets": sla_targets,
            "violations": violations,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        logger.info(
            "prometheus_client.sla_validation",
            service=service,
            restored=sla_restored,
            violations_count=len(violations)
        )

        return result

    def _extract_value(self, query_result: Dict[str, Any]) -> float:
        """Extrai valor numérico de resultado de query Prometheus"""
        try:
            data = query_result.get("data", {})
            result = data.get("result", [])

            if not result:
                return 0.0

            # Pegar primeiro resultado
            first_result = result[0]
            value = first_result.get("value", [None, "0"])

            # value é [timestamp, "valor"]
            if len(value) >= 2:
                return float(value[1])

            return 0.0

        except (ValueError, IndexError, KeyError) as e:
            logger.warning(
                "prometheus_client.value_extraction_failed",
                error=str(e)
            )
            return 0.0

    def is_connected(self) -> bool:
        """Verifica se cliente está conectado"""
        return self._client is not None
