import structlog
import httpx
from typing import List, Dict, Optional

logger = structlog.get_logger()


class PrometheusClient:
    def __init__(self, url: str):
        self.url = url
        self.client = None

    def initialize(self):
        """Configurar cliente HTTP"""
        self.client = httpx.AsyncClient(base_url=self.url, timeout=10.0)
        logger.info('prometheus_client_initialized', url=self.url)

    async def close(self):
        """Fechar cliente"""
        if self.client:
            await self.client.aclose()
            logger.info('prometheus_client_closed')

    async def query(self, promql: str, time: Optional[int] = None) -> List[dict]:
        """Executar consulta PromQL instantânea"""
        try:
            params = {'query': promql}
            if time:
                params['time'] = time

            response = await self.client.get('/api/v1/query', params=params)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'success':
                return data['data']['result']
            return []
        except Exception as e:
            logger.error('prometheus_query_failed', error=str(e), query=promql[:100])
            return []

    async def query_range(self, promql: str, start: int, end: int, step: str = '60s') -> List[dict]:
        """Executar consulta PromQL em range temporal"""
        try:
            params = {'query': promql, 'start': start, 'end': end, 'step': step}
            response = await self.client.get('/api/v1/query_range', params=params)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'success':
                return data['data']['result']
            return []
        except Exception as e:
            logger.error('prometheus_query_range_failed', error=str(e))
            return []

    async def get_metric_current_value(self, metric_name: str, labels: dict = None) -> Optional[float]:
        """Obter valor atual de métrica"""
        label_selector = ','.join([f'{k}="{v}"' for k, v in (labels or {}).items()])
        query = f'{metric_name}{{{label_selector}}}' if label_selector else metric_name

        results = await self.query(query)
        if results and len(results) > 0:
            return float(results[0]['value'][1])
        return None

    async def get_metric_statistics(self, metric_name: str, start: int, end: int, aggregation: str = 'avg') -> Dict:
        """Estatísticas de métrica"""
        queries = {
            'avg': f'avg_over_time({metric_name}[5m])',
            'max': f'max_over_time({metric_name}[5m])',
            'min': f'min_over_time({metric_name}[5m])',
            'sum': f'sum_over_time({metric_name}[5m])'
        }

        query = queries.get(aggregation, queries['avg'])
        results = await self.query_range(query, start, end)

        if results:
            values = [float(v[1]) for r in results for v in r.get('values', [])]
            return {
                'avg': sum(values) / len(values) if values else 0,
                'max': max(values) if values else 0,
                'min': min(values) if values else 0,
                'count': len(values)
            }
        return {}
