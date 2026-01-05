import structlog
from typing import Dict, List, Any
import statistics
from datetime import datetime

from ..config import Settings
from ..clients import PrometheusClient, RedisClient


logger = structlog.get_logger()


class TelemetryAggregator:
    """Agregador de telemetria de múltiplas fontes"""

    def __init__(
        self,
        prometheus_client: PrometheusClient,
        redis_client: RedisClient,
        settings: Settings
    ):
        self.prometheus_client = prometheus_client
        self.redis_client = redis_client
        self.settings = settings

    async def aggregate_system_health(self) -> Dict[str, Any]:
        """Agregar saúde geral do sistema"""
        try:
            # Buscar cache primeiro
            cached = await self.get_cached_snapshot()
            if cached:
                return cached

            # Coletar métricas
            sla_compliance = await self._get_overall_sla_compliance()
            error_rate = await self._get_overall_error_rate()
            resource_saturation = await self._get_resource_saturation()
            active_incidents = 0  # Placeholder - viria do Prometheus Alertmanager

            # Calcular system score
            system_score = await self.calculate_system_score()

            health = {
                'system_score': system_score,
                'sla_compliance': sla_compliance,
                'error_rate': error_rate,
                'resource_saturation': resource_saturation,
                'active_incidents': active_incidents,
                'timestamp': int(datetime.now().timestamp() * 1000)
            }

            # Cachear
            await self.cache_telemetry_snapshot(health)

            return health

        except Exception as e:
            logger.error("aggregate_system_health_failed", error=str(e))
            return {}

    async def aggregate_workflow_metrics(self, workflow_ids: List[str]) -> Dict[str, Any]:
        """Agregar métricas de workflows específicos"""
        metrics = {}

        try:
            for workflow_id in workflow_ids[:10]:  # Limitar a 10
                sla = await self.prometheus_client.get_sla_compliance(workflow_id, '5m')
                metrics[workflow_id] = {
                    'sla_compliance': sla
                }

            return metrics

        except Exception as e:
            logger.error("aggregate_workflow_metrics_failed", error=str(e))
            return {}

    async def detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detectar anomalias em métricas (threshold-based MVP)"""
        anomalies = []

        try:
            health = await self.aggregate_system_health()

            # Threshold-based detection
            if health.get('error_rate', 0) > 0.05:
                anomalies.append({
                    'type': 'high_error_rate',
                    'value': health['error_rate'],
                    'threshold': 0.05
                })

            if health.get('sla_compliance', 1.0) < 0.95:
                anomalies.append({
                    'type': 'low_sla_compliance',
                    'value': health['sla_compliance'],
                    'threshold': 0.95
                })

            if health.get('resource_saturation', 0) > 0.8:
                anomalies.append({
                    'type': 'high_resource_saturation',
                    'value': health['resource_saturation'],
                    'threshold': 0.8
                })

            if anomalies:
                logger.warning("anomalies_detected", count=len(anomalies))

            return anomalies

        except Exception as e:
            logger.error("detect_anomalies_failed", error=str(e))
            return []

    async def calculate_system_score(self) -> float:
        """
        Calcular score geral do sistema (0-1)

        Fórmula:
        system_score = (
            sla_compliance * 0.3 +
            (1 - error_rate) * 0.3 +
            (1 - resource_saturation) * 0.2 +
            workflow_success_rate * 0.2
        )
        """
        try:
            sla_compliance = await self._get_overall_sla_compliance()
            error_rate = await self._get_overall_error_rate()
            resource_data = await self.prometheus_client.get_resource_saturation()
            resource_saturation = max(resource_data.values()) if resource_data else 0.0

            # Calcular workflow success rate de métricas reais
            workflow_success_rate = await self._get_workflow_success_rate()

            score = (
                sla_compliance * 0.3 +
                (1 - error_rate) * 0.3 +
                (1 - resource_saturation) * 0.2 +
                workflow_success_rate * 0.2
            )

            return max(0.0, min(1.0, score))

        except Exception as e:
            logger.error("calculate_system_score_failed", error=str(e))
            return 0.5

    async def _get_workflow_success_rate(self) -> float:
        """
        Calcular taxa de sucesso de workflows dos últimos 5 minutos

        Returns:
            Taxa de sucesso (0.0 a 1.0)
        """
        try:
            # Query PromQL para workflows completados com sucesso vs total
            query = '''
            sum(rate(temporal_workflow_completed_total{status="COMPLETED"}[5m])) /
            sum(rate(temporal_workflow_completed_total[5m]))
            '''

            result = await self.prometheus_client.query(query)

            if result.get('status') == 'success' and result.get('data', {}).get('result'):
                value = result['data']['result'][0].get('value', [])
                if len(value) > 1:
                    success_rate = float(value[1])
                    # Tratar NaN (divisão por zero)
                    if success_rate != success_rate:  # NaN check
                        return 0.95
                    logger.debug("workflow_success_rate_calculated", rate=success_rate)
                    return success_rate

            # Fallback: tentar query alternativa para execution tickets
            fallback_query = '''
            sum(rate(execution_tickets_completed_total{status="COMPLETED"}[5m])) /
            sum(rate(execution_tickets_completed_total[5m]))
            '''

            fallback_result = await self.prometheus_client.query(fallback_query)

            if fallback_result.get('status') == 'success' and fallback_result.get('data', {}).get('result'):
                value = fallback_result['data']['result'][0].get('value', [])
                if len(value) > 1:
                    success_rate = float(value[1])
                    if success_rate != success_rate:  # NaN check
                        return 0.95
                    logger.debug("workflow_success_rate_calculated_fallback", rate=success_rate)
                    return success_rate

            # Se não há dados, assumir taxa otimista
            logger.warning("workflow_success_rate_no_data_available")
            return 0.95

        except Exception as e:
            logger.error("get_workflow_success_rate_failed", error=str(e))
            return 0.95

    async def cache_telemetry_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Cachear snapshot de telemetria no Redis"""
        try:
            cache_key = "telemetry:snapshot:latest"
            await self.redis_client.cache_strategic_context(
                cache_key,
                snapshot,
                ttl_seconds=self.settings.REDIS_CACHE_TTL_SECONDS
            )

        except Exception as e:
            logger.error("cache_telemetry_snapshot_failed", error=str(e))

    async def get_cached_snapshot(self) -> Dict[str, Any] | None:
        """Recuperar snapshot cacheado"""
        try:
            cache_key = "telemetry:snapshot:latest"
            return await self.redis_client.get_cached_context(cache_key)

        except Exception as e:
            logger.error("get_cached_snapshot_failed", error=str(e))
            return None

    async def _get_overall_sla_compliance(self) -> float:
        """Obter SLA compliance geral"""
        try:
            # Query agregada do Prometheus
            result = await self.prometheus_client.query(
                'avg(rate(http_requests_total{status=~"2.."}[5m])) / avg(rate(http_requests_total[5m]))'
            )

            if result.get('status') == 'success' and result.get('data', {}).get('result'):
                return float(result['data']['result'][0]['value'][1])

            return 0.95  # Default otimista

        except Exception as e:
            logger.error("get_overall_sla_compliance_failed", error=str(e))
            return 0.95

    async def _get_overall_error_rate(self) -> float:
        """Obter taxa de erro geral"""
        try:
            result = await self.prometheus_client.query(
                'avg(rate(http_requests_total{status=~"5.."}[5m]))'
            )

            if result.get('status') == 'success' and result.get('data', {}).get('result'):
                return float(result['data']['result'][0]['value'][1])

            return 0.0

        except Exception as e:
            logger.error("get_overall_error_rate_failed", error=str(e))
            return 0.0

    async def _get_resource_saturation(self) -> float:
        """Obter saturação média de recursos"""
        try:
            resource_data = await self.prometheus_client.get_resource_saturation()
            if resource_data:
                return statistics.mean(resource_data.values())

            return 0.0

        except Exception as e:
            logger.error("get_resource_saturation_failed", error=str(e))
            return 0.0
