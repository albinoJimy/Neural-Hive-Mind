"""
Cliente Prometheus para coleta de metricas durante testes de carga.

Fornece queries PromQL para metricas do Fluxo C, autoscaling e circuit breakers.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


# Queries PromQL para metricas do Fluxo C
PROMQL_QUERIES = {
    'flow_c_latency_p50': 'histogram_quantile(0.50, sum(rate(neural_hive_flow_c_duration_seconds_bucket[5m])) by (le))',
    'flow_c_latency_p95': 'histogram_quantile(0.95, sum(rate(neural_hive_flow_c_duration_seconds_bucket[5m])) by (le))',
    'flow_c_latency_p99': 'histogram_quantile(0.99, sum(rate(neural_hive_flow_c_duration_seconds_bucket[5m])) by (le))',
    'flow_c_success_total': 'sum(increase(neural_hive_flow_c_success_total[5m]))',
    'flow_c_failures_total': 'sum(increase(neural_hive_flow_c_failures_total[5m]))',
    'flow_c_success_rate': '''
        sum(rate(neural_hive_flow_c_success_total[5m])) /
        (sum(rate(neural_hive_flow_c_success_total[5m])) + sum(rate(neural_hive_flow_c_failures_total[5m])))
    ''',
    'flow_c_step_latency_p95': '''
        histogram_quantile(0.95, sum(rate(neural_hive_flow_c_steps_duration_seconds_bucket{{step="{step}"}}[5m])) by (le))
    ''',
    'circuit_breaker_state': 'neural_hive_circuit_breaker_state{{component="{component}"}}',
    'circuit_breaker_trips': 'sum(increase(neural_hive_circuit_breaker_trips_total{{component="{component}"}}[5m]))',
    'replica_count': 'count(kube_pod_info{{pod=~"orchestrator-dynamic-.*", namespace="neural-hive-orchestration", phase="Running"}})',
    'cpu_usage': '''
        avg(rate(container_cpu_usage_seconds_total{{pod=~"orchestrator-dynamic-.*", namespace="neural-hive-orchestration"}}[5m])) * 100
    ''',
    'memory_usage': '''
        avg(
            container_memory_working_set_bytes{{pod=~"orchestrator-dynamic-.*", namespace="neural-hive-orchestration"}} /
            container_spec_memory_limit_bytes{{pod=~"orchestrator-dynamic-.*", namespace="neural-hive-orchestration"}}
        ) * 100
    ''',
    'kafka_consumer_lag': 'sum(kafka_consumer_lag{{group="orchestrator-dynamic"}})',
    'mongodb_pool_size': 'neural_hive_mongodb_connection_pool_size',
    'mongodb_pool_utilization': '''
        neural_hive_mongodb_connection_pool_in_use / neural_hive_mongodb_connection_pool_size * 100
    ''',
    'temporal_task_queue_depth': 'temporal_task_queue_depth{{task_queue="orchestration-tasks"}}',
    'tickets_created_rate': 'sum(rate(neural_hive_execution_tickets_created_total[5m]))',
    'tickets_completed_rate': 'sum(rate(neural_hive_execution_tickets_completed_total[5m]))',
    'hpa_current_replicas': 'kube_horizontalpodautoscaler_status_current_replicas{{horizontalpodautoscaler="orchestrator-dynamic"}}',
    'hpa_desired_replicas': 'kube_horizontalpodautoscaler_status_desired_replicas{{horizontalpodautoscaler="orchestrator-dynamic"}}',
}


@dataclass
class PrometheusQueryResult:
    """Resultado de uma query Prometheus."""
    query: str
    value: Optional[float] = None
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.value is not None


@dataclass
class MetricsSnapshot:
    """Snapshot de metricas em um ponto no tempo."""
    timestamp: datetime
    flow_c_latency_p50: Optional[float] = None
    flow_c_latency_p95: Optional[float] = None
    flow_c_latency_p99: Optional[float] = None
    flow_c_success_rate: Optional[float] = None
    replica_count: Optional[int] = None
    cpu_usage_percent: Optional[float] = None
    memory_usage_percent: Optional[float] = None
    kafka_lag: Optional[int] = None
    mongodb_pool_utilization: Optional[float] = None
    temporal_queue_depth: Optional[int] = None
    tickets_per_second: Optional[float] = None
    circuit_breaker_states: Dict[str, str] = field(default_factory=dict)
    step_latencies: Dict[str, float] = field(default_factory=dict)


class PrometheusClient:
    """Cliente para consultar metricas do Prometheus."""

    def __init__(
        self,
        url: str = 'http://prometheus:9090',
        timeout_seconds: float = 10.0,
    ):
        """
        Inicializa o cliente Prometheus.

        Args:
            url: URL base do Prometheus
            timeout_seconds: Timeout para requests
        """
        self.url = url.rstrip('/')
        self.timeout = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtem ou cria cliente HTTP."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Fecha o cliente HTTP."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def query(self, query: str) -> PrometheusQueryResult:
        """
        Executa query PromQL instantanea.

        Args:
            query: Query PromQL

        Returns:
            PrometheusQueryResult com valor ou erro
        """
        client = await self._get_client()
        result = PrometheusQueryResult(query=query)

        try:
            response = await client.get(
                f'{self.url}/api/v1/query',
                params={'query': query.strip()},
            )
            response.raise_for_status()
            data = response.json()

            if data.get('status') != 'success':
                result.error = data.get('error', 'Unknown error')
                return result

            results = data.get('data', {}).get('result', [])
            if results:
                # Pegar primeiro resultado
                first = results[0]
                result.labels = first.get('metric', {})

                # Value pode ser [timestamp, value] ou scalar
                value_data = first.get('value', [])
                if len(value_data) >= 2:
                    try:
                        result.value = float(value_data[1])
                        result.timestamp = datetime.fromtimestamp(float(value_data[0]))
                    except (ValueError, TypeError) as e:
                        # Pode ser 'NaN' ou 'Inf'
                        if value_data[1] == 'NaN':
                            result.value = None
                        else:
                            result.error = f'Invalid value: {value_data[1]}'
            else:
                result.value = None  # Query retornou vazio

        except httpx.HTTPStatusError as e:
            result.error = f'HTTP error: {e.response.status_code}'
            logger.warning(f'Prometheus query failed: {e}')
        except httpx.RequestError as e:
            result.error = f'Request error: {str(e)}'
            logger.warning(f'Prometheus request failed: {e}')
        except Exception as e:
            result.error = f'Unexpected error: {str(e)}'
            logger.exception('Unexpected error in Prometheus query')

        return result

    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = '30s',
    ) -> List[PrometheusQueryResult]:
        """
        Executa query PromQL em range de tempo.

        Args:
            query: Query PromQL
            start: Inicio do range
            end: Fim do range
            step: Intervalo entre pontos

        Returns:
            Lista de resultados
        """
        client = await self._get_client()
        results = []

        try:
            response = await client.get(
                f'{self.url}/api/v1/query_range',
                params={
                    'query': query.strip(),
                    'start': start.timestamp(),
                    'end': end.timestamp(),
                    'step': step,
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get('status') != 'success':
                return [PrometheusQueryResult(query=query, error=data.get('error'))]

            for series in data.get('data', {}).get('result', []):
                labels = series.get('metric', {})
                for value_data in series.get('values', []):
                    try:
                        result = PrometheusQueryResult(
                            query=query,
                            value=float(value_data[1]) if value_data[1] != 'NaN' else None,
                            labels=labels,
                            timestamp=datetime.fromtimestamp(float(value_data[0])),
                        )
                        results.append(result)
                    except (ValueError, TypeError):
                        continue

        except Exception as e:
            logger.warning(f'Prometheus range query failed: {e}')
            return [PrometheusQueryResult(query=query, error=str(e))]

        return results

    async def get_flow_c_latency_p95(self) -> Optional[float]:
        """Obtem latencia P95 do Fluxo C em segundos."""
        result = await self.query(PROMQL_QUERIES['flow_c_latency_p95'])
        return result.value

    async def get_flow_c_latency_p99(self) -> Optional[float]:
        """Obtem latencia P99 do Fluxo C em segundos."""
        result = await self.query(PROMQL_QUERIES['flow_c_latency_p99'])
        return result.value

    async def get_flow_c_success_rate(self) -> Optional[float]:
        """Obtem taxa de sucesso do Fluxo C."""
        result = await self.query(PROMQL_QUERIES['flow_c_success_rate'])
        return result.value

    async def get_step_latency_p95(self, step: str) -> Optional[float]:
        """
        Obtem latencia P95 de um step especifico.

        Args:
            step: Nome do step (C1, C2, C3, C4, C5, C6)
        """
        query = PROMQL_QUERIES['flow_c_step_latency_p95'].format(step=step)
        result = await self.query(query)
        return result.value

    async def get_circuit_breaker_state(self, component: str) -> Optional[str]:
        """
        Obtem estado do circuit breaker.

        Args:
            component: Nome do componente (kafka, temporal, redis, mongodb)

        Returns:
            Estado: 'closed', 'open', 'half_open'
        """
        query = PROMQL_QUERIES['circuit_breaker_state'].format(component=component)
        result = await self.query(query)

        if result.value is not None:
            # 0 = closed, 1 = open, 2 = half_open
            state_map = {0: 'closed', 1: 'open', 2: 'half_open'}
            return state_map.get(int(result.value), 'unknown')
        return None

    async def get_circuit_breaker_trips(self, component: str) -> Optional[int]:
        """Obtem numero de trips do circuit breaker."""
        query = PROMQL_QUERIES['circuit_breaker_trips'].format(component=component)
        result = await self.query(query)
        return int(result.value) if result.value is not None else None

    async def get_replica_count(self) -> Optional[int]:
        """Obtem numero de replicas do orchestrator-dynamic."""
        result = await self.query(PROMQL_QUERIES['replica_count'])
        return int(result.value) if result.value is not None else None

    async def get_cpu_usage(self) -> Optional[float]:
        """Obtem uso de CPU em porcentagem."""
        result = await self.query(PROMQL_QUERIES['cpu_usage'])
        return result.value

    async def get_memory_usage(self) -> Optional[float]:
        """Obtem uso de memoria em porcentagem."""
        result = await self.query(PROMQL_QUERIES['memory_usage'])
        return result.value

    async def get_kafka_lag(self) -> Optional[int]:
        """Obtem lag do consumer Kafka."""
        result = await self.query(PROMQL_QUERIES['kafka_consumer_lag'])
        return int(result.value) if result.value is not None else None

    async def get_mongodb_pool_utilization(self) -> Optional[float]:
        """Obtem utilizacao do pool MongoDB em porcentagem."""
        result = await self.query(PROMQL_QUERIES['mongodb_pool_utilization'])
        return result.value

    async def get_temporal_queue_depth(self) -> Optional[int]:
        """Obtem profundidade da fila Temporal."""
        result = await self.query(PROMQL_QUERIES['temporal_task_queue_depth'])
        return int(result.value) if result.value is not None else None

    async def get_tickets_per_second(self) -> Optional[float]:
        """Obtem taxa de tickets criados por segundo."""
        result = await self.query(PROMQL_QUERIES['tickets_created_rate'])
        return result.value

    async def get_hpa_status(self) -> Dict[str, int]:
        """Obtem status do HPA."""
        current = await self.query(PROMQL_QUERIES['hpa_current_replicas'])
        desired = await self.query(PROMQL_QUERIES['hpa_desired_replicas'])

        return {
            'current_replicas': int(current.value) if current.value else 0,
            'desired_replicas': int(desired.value) if desired.value else 0,
        }

    async def collect_metrics_snapshot(self) -> MetricsSnapshot:
        """
        Coleta snapshot completo de metricas.

        Returns:
            MetricsSnapshot com todas as metricas disponiveis
        """
        snapshot = MetricsSnapshot(timestamp=datetime.utcnow())

        # Coletar metricas em paralelo
        tasks = {
            'flow_c_latency_p50': self.query(PROMQL_QUERIES['flow_c_latency_p50']),
            'flow_c_latency_p95': self.get_flow_c_latency_p95(),
            'flow_c_latency_p99': self.get_flow_c_latency_p99(),
            'flow_c_success_rate': self.get_flow_c_success_rate(),
            'replica_count': self.get_replica_count(),
            'cpu_usage': self.get_cpu_usage(),
            'memory_usage': self.get_memory_usage(),
            'kafka_lag': self.get_kafka_lag(),
            'mongodb_pool': self.get_mongodb_pool_utilization(),
            'temporal_queue': self.get_temporal_queue_depth(),
            'tickets_per_sec': self.get_tickets_per_second(),
        }

        # Adicionar circuit breakers
        components = ['kafka', 'temporal', 'redis', 'mongodb']
        for comp in components:
            tasks[f'cb_{comp}'] = self.get_circuit_breaker_state(comp)

        # Adicionar step latencies
        steps = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']
        for step in steps:
            tasks[f'step_{step}'] = self.get_step_latency_p95(step)

        # Executar todas as queries
        results = {}
        for name, coro in tasks.items():
            try:
                results[name] = await coro
            except Exception as e:
                logger.debug(f'Failed to collect {name}: {e}')
                results[name] = None

        # Popular snapshot
        p50_result = results.get('flow_c_latency_p50')
        if isinstance(p50_result, PrometheusQueryResult):
            snapshot.flow_c_latency_p50 = p50_result.value
        else:
            snapshot.flow_c_latency_p50 = p50_result

        snapshot.flow_c_latency_p95 = results.get('flow_c_latency_p95')
        snapshot.flow_c_latency_p99 = results.get('flow_c_latency_p99')
        snapshot.flow_c_success_rate = results.get('flow_c_success_rate')
        snapshot.replica_count = results.get('replica_count')
        snapshot.cpu_usage_percent = results.get('cpu_usage')
        snapshot.memory_usage_percent = results.get('memory_usage')
        snapshot.kafka_lag = results.get('kafka_lag')
        snapshot.mongodb_pool_utilization = results.get('mongodb_pool')
        snapshot.temporal_queue_depth = results.get('temporal_queue')
        snapshot.tickets_per_second = results.get('tickets_per_sec')

        # Circuit breaker states
        for comp in components:
            state = results.get(f'cb_{comp}')
            if state:
                snapshot.circuit_breaker_states[comp] = state

        # Step latencies
        for step in steps:
            latency = results.get(f'step_{step}')
            if latency is not None:
                snapshot.step_latencies[step] = latency

        return snapshot

    async def watch_metrics(
        self,
        interval_seconds: float = 10.0,
        duration_seconds: float = 60.0,
    ) -> List[MetricsSnapshot]:
        """
        Coleta snapshots de metricas periodicamente.

        Args:
            interval_seconds: Intervalo entre coletas
            duration_seconds: Duracao total do monitoramento

        Returns:
            Lista de snapshots coletados
        """
        snapshots = []
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < duration_seconds:
            try:
                snapshot = await self.collect_metrics_snapshot()
                snapshots.append(snapshot)
                logger.debug(
                    f'Metrics snapshot: replicas={snapshot.replica_count}, '
                    f'cpu={snapshot.cpu_usage_percent:.1f}%, '
                    f'mem={snapshot.memory_usage_percent:.1f}%'
                )
            except Exception as e:
                logger.warning(f'Failed to collect metrics snapshot: {e}')

            await asyncio.sleep(interval_seconds)

        return snapshots
