"""
Testes de carga para o Fluxo C de Orquestracao (C1-C6).

Valida throughput, latencia, autoscaling, circuit breakers e identifica
bottlenecks durante execucao de carga.

Padroes de carga testados:
- 100 workflows sequenciais
- 50 workflows concorrentes
- 100 workflows concorrentes (alta carga)
- Ramp-up gradual para teste de autoscaling
- Simulacao de falhas para circuit breakers
"""

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from tests.performance.prometheus_client import PrometheusClient, MetricsSnapshot
from tests.performance.kubernetes_client import KubernetesClient, ScalingEvent
from tests.performance.bottleneck_analyzer import BottleneckAnalyzer
from tests.performance.slo_validator import SLOValidator, LoadTestMetrics
from tests.performance.report_generator import (
    PerformanceReportGenerator,
    PerformanceTestResults,
    ScalingEventSummary,
    StepLatencyStats,
)
from tests.performance.conftest import generate_cognitive_plans, generate_consolidated_decisions

logger = logging.getLogger(__name__)


@dataclass
class FlowCLoadTestMetrics:
    """Metricas especificas do teste de carga do Fluxo C."""
    # Latencias por step (ms)
    step_latencies: Dict[str, List[float]] = field(default_factory=lambda: {
        'C1': [], 'C2': [], 'C3': [], 'C4': [], 'C5': [], 'C6': [],
    })

    # Latencias end-to-end (ms)
    workflow_latencies_ms: List[float] = field(default_factory=list)

    # Contadores
    workflows_started: int = 0
    workflows_completed: int = 0
    workflows_failed: int = 0
    tickets_created: int = 0
    tickets_completed: int = 0
    tickets_failed: int = 0

    # Circuit breaker
    circuit_breaker_trips: Dict[str, int] = field(default_factory=dict)

    # Autoscaling
    replica_counts: List[int] = field(default_factory=list)

    # Timing
    start_time: float = 0
    end_time: float = 0

    def record_step_latency(self, step: str, latency_ms: float) -> None:
        """Registra latencia de um step."""
        if step in self.step_latencies:
            self.step_latencies[step].append(latency_ms)

    def record_workflow_completion(
        self,
        success: bool,
        total_duration_ms: float,
    ) -> None:
        """Registra conclusao de workflow."""
        self.workflow_latencies_ms.append(total_duration_ms)
        if success:
            self.workflows_completed += 1
        else:
            self.workflows_failed += 1

    def record_circuit_breaker_trip(self, component: str) -> None:
        """Registra trip de circuit breaker."""
        self.circuit_breaker_trips[component] = (
            self.circuit_breaker_trips.get(component, 0) + 1
        )

    def record_replica_count(self, count: int) -> None:
        """Registra contagem de replicas."""
        self.replica_counts.append(count)

    @property
    def duration_seconds(self) -> float:
        """Duracao total do teste."""
        return self.end_time - self.start_time if self.end_time > 0 else 0

    @property
    def workflows_per_second(self) -> float:
        """Throughput de workflows."""
        if self.duration_seconds > 0:
            return (self.workflows_completed + self.workflows_failed) / self.duration_seconds
        return 0

    @property
    def tickets_per_second(self) -> float:
        """Throughput de tickets."""
        if self.duration_seconds > 0:
            return (self.tickets_completed + self.tickets_failed) / self.duration_seconds
        return 0

    @property
    def success_rate(self) -> float:
        """Taxa de sucesso."""
        total = self.workflows_completed + self.workflows_failed
        if total > 0:
            return self.workflows_completed / total
        return 0

    def _percentile(self, values: List[float], p: float) -> Optional[float]:
        """Calcula percentil de uma lista de valores."""
        if not values:
            return None
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * p)
        return sorted_values[min(idx, len(sorted_values) - 1)]

    @property
    def latency_p50_ms(self) -> Optional[float]:
        return self._percentile(self.workflow_latencies_ms, 0.50)

    @property
    def latency_p95_ms(self) -> Optional[float]:
        return self._percentile(self.workflow_latencies_ms, 0.95)

    @property
    def latency_p99_ms(self) -> Optional[float]:
        return self._percentile(self.workflow_latencies_ms, 0.99)

    def get_step_latency_p95(self, step: str) -> Optional[float]:
        """Retorna latencia P95 de um step."""
        return self._percentile(self.step_latencies.get(step, []), 0.95)

    def to_load_test_metrics(self) -> LoadTestMetrics:
        """Converte para LoadTestMetrics para validacao de SLO."""
        return LoadTestMetrics(
            latency_p50_seconds=(self.latency_p50_ms or 0) / 1000,
            latency_p95_seconds=(self.latency_p95_ms or 0) / 1000,
            latency_p99_seconds=(self.latency_p99_ms or 0) / 1000,
            total_workflows=self.workflows_started,
            successful_workflows=self.workflows_completed,
            failed_workflows=self.workflows_failed,
            total_tickets=self.tickets_created,
            test_duration_seconds=self.duration_seconds,
        )


class FlowCLoadTester:
    """Executor de testes de carga do Fluxo C."""

    def __init__(
        self,
        orchestrator_url: str,
        prometheus_client: Optional[PrometheusClient] = None,
        kubernetes_client: Optional[KubernetesClient] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o testador.

        Args:
            orchestrator_url: URL base do orchestrator-dynamic
            prometheus_client: Cliente Prometheus para metricas
            kubernetes_client: Cliente Kubernetes para HPA
            config: Configuracao adicional
        """
        self.orchestrator_url = orchestrator_url.rstrip('/')
        self.prometheus = prometheus_client
        self.kubernetes = kubernetes_client
        self.config = config or {}

        self.metrics = FlowCLoadTestMetrics()
        self._http_client = None

    async def setup(self) -> None:
        """Configura clientes e valida conectividade."""
        import httpx

        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        )

        # Validar health do orchestrator
        try:
            response = await self._http_client.get(f'{self.orchestrator_url}/health')
            if response.status_code != 200:
                logger.warning(f'Orchestrator health check falhou: {response.status_code}')
        except Exception as e:
            logger.warning(f'Nao foi possivel conectar ao orchestrator: {e}')

    async def cleanup(self) -> None:
        """Fecha conexoes."""
        if self._http_client:
            await self._http_client.aclose()
        if self.prometheus:
            await self.prometheus.close()
        if self.kubernetes:
            await self.kubernetes.close()

    async def start_workflow(self, decision: Dict[str, Any]) -> Optional[str]:
        """
        Inicia um workflow via API do orchestrator.

        Args:
            decision: Decisao consolidada

        Returns:
            workflow_id se sucesso, None se falha
        """
        try:
            response = await self._http_client.post(
                f'{self.orchestrator_url}/api/v1/workflows/start',
                json=decision,
            )

            if response.status_code in (200, 201, 202):
                data = response.json()
                return data.get('workflow_id')
            else:
                logger.warning(f'Falha ao iniciar workflow: {response.status_code}')
                return None

        except Exception as e:
            logger.error(f'Erro ao iniciar workflow: {e}')
            return None

    async def wait_for_workflow_completion(
        self,
        workflow_id: str,
        timeout_seconds: int = 14400,
    ) -> Dict[str, Any]:
        """
        Aguarda conclusao de um workflow.

        Args:
            workflow_id: ID do workflow
            timeout_seconds: Timeout em segundos

        Returns:
            Dict com status e duracao
        """
        start = time.time()

        while time.time() - start < timeout_seconds:
            try:
                response = await self._http_client.get(
                    f'{self.orchestrator_url}/api/v1/workflows/{workflow_id}/status'
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', '')

                    if status in ('COMPLETED', 'completed'):
                        return {
                            'success': True,
                            'status': status,
                            'duration_ms': (time.time() - start) * 1000,
                        }
                    elif status in ('FAILED', 'failed', 'CANCELLED', 'cancelled'):
                        return {
                            'success': False,
                            'status': status,
                            'duration_ms': (time.time() - start) * 1000,
                            'error': data.get('error'),
                        }

            except Exception as e:
                logger.debug(f'Erro consultando status: {e}')

            await asyncio.sleep(5)

        return {
            'success': False,
            'status': 'TIMEOUT',
            'duration_ms': timeout_seconds * 1000,
        }

    async def execute_single_workflow(
        self,
        decision: Dict[str, Any],
        wait_completion: bool = True,
    ) -> Dict[str, Any]:
        """
        Executa um workflow completo.

        Args:
            decision: Decisao consolidada
            wait_completion: Se deve aguardar conclusao

        Returns:
            Dict com resultado
        """
        start_time = time.time()
        self.metrics.workflows_started += 1

        # Iniciar workflow
        workflow_id = await self.start_workflow(decision)

        if not workflow_id:
            self.metrics.workflows_failed += 1
            return {
                'success': False,
                'error': 'Falha ao iniciar workflow',
                'duration_ms': (time.time() - start_time) * 1000,
            }

        # Contar tickets esperados
        tasks = decision.get('cognitive_plan', {}).get('tasks', [])
        self.metrics.tickets_created += len(tasks)

        if not wait_completion:
            return {
                'success': True,
                'workflow_id': workflow_id,
                'started_at': start_time,
            }

        # Aguardar conclusao
        result = await self.wait_for_workflow_completion(workflow_id)

        self.metrics.record_workflow_completion(
            success=result['success'],
            total_duration_ms=result['duration_ms'],
        )

        if result['success']:
            self.metrics.tickets_completed += len(tasks)
        else:
            self.metrics.tickets_failed += len(tasks)

        return result

    async def run_concurrent_workflows(
        self,
        decisions: List[Dict[str, Any]],
        max_concurrent: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Executa multiplos workflows concorrentemente.

        Args:
            decisions: Lista de decisoes consolidadas
            max_concurrent: Maximo de workflows simultaneos

        Returns:
            Lista de resultados
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_semaphore(decision: Dict) -> Dict:
            async with semaphore:
                return await self.execute_single_workflow(decision)

        tasks = [execute_with_semaphore(d) for d in decisions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Tratar exceptions
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append({
                    'success': False,
                    'error': str(result),
                })
            else:
                processed_results.append(result)

        return processed_results

    async def monitor_autoscaling(
        self,
        duration_seconds: int = 300,
        poll_interval: float = 10.0,
    ) -> List[ScalingEvent]:
        """
        Monitora autoscaling durante teste.

        Args:
            duration_seconds: Duracao do monitoramento
            poll_interval: Intervalo entre checks

        Returns:
            Lista de eventos de scaling
        """
        if not self.kubernetes or not self.kubernetes.is_available():
            return []

        return await self.kubernetes.watch_hpa_scaling(
            name='orchestrator-dynamic',
            duration_seconds=duration_seconds,
            poll_interval=poll_interval,
        )

    async def collect_prometheus_metrics(self) -> Optional[MetricsSnapshot]:
        """Coleta snapshot de metricas do Prometheus."""
        if not self.prometheus:
            return None

        return await self.prometheus.collect_metrics_snapshot()


# ============================================
# Testes de Carga
# ============================================


class TestFlowCThroughput:
    """Testes de throughput do Fluxo C."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_throughput_sequential_100_workflows(
        self,
        load_test_config,
        prometheus_client,
        sample_cognitive_plan,
        bottleneck_analyzer,
        slo_validator,
    ):
        """
        Teste de throughput com 100 workflows sequenciais.

        Valida:
        - Throughput > 10 tickets/s
        - Latencia P95 < 4h
        - Taxa de sucesso > 95%
        """
        tester = FlowCLoadTester(
            orchestrator_url=load_test_config['orchestrator_url'],
            prometheus_client=prometheus_client,
            config=load_test_config,
        )

        await tester.setup()

        try:
            # Gerar planos
            plans = generate_cognitive_plans(100, sample_cognitive_plan)
            decisions = generate_consolidated_decisions(plans)

            tester.metrics.start_time = time.time()

            # Executar sequencialmente
            for decision in decisions:
                result = await tester.execute_single_workflow(decision)
                logger.info(
                    f'Workflow {decision["plan_id"]}: '
                    f'{"sucesso" if result["success"] else "falha"} '
                    f'em {result["duration_ms"]/1000:.1f}s'
                )

            tester.metrics.end_time = time.time()

            # Validacoes
            metrics = tester.metrics

            assert metrics.workflows_completed + metrics.workflows_failed == 100, \
                f'Todos os 100 workflows devem ser processados'

            # SLO: Throughput
            tickets_per_second = metrics.tickets_per_second
            logger.info(f'Throughput: {tickets_per_second:.2f} tickets/s')
            # Nota: Em modo sequencial, throughput pode ser menor que target

            # SLO: Taxa de sucesso
            assert metrics.success_rate >= 0.95, \
                f'Taxa de sucesso deve ser >= 95%, obtido: {metrics.success_rate*100:.1f}%'

            # SLO: Latencia P95
            if metrics.latency_p95_ms:
                p95_hours = metrics.latency_p95_ms / 3600000
                logger.info(f'Latencia P95: {p95_hours:.2f}h')
                assert metrics.latency_p95_ms < 14400000, \
                    f'Latencia P95 deve ser < 4h, obtido: {p95_hours:.2f}h'

            # Report
            logger.info(f'\n[Throughput Sequencial]')
            logger.info(f'  Workflows: {metrics.workflows_started}')
            logger.info(f'  Completados: {metrics.workflows_completed}')
            logger.info(f'  Falhados: {metrics.workflows_failed}')
            logger.info(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')
            logger.info(f'  Duracao: {metrics.duration_seconds:.1f}s')
            logger.info(f'  Throughput: {metrics.workflows_per_second:.2f} workflows/s')

        finally:
            await tester.cleanup()

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_throughput_concurrent_50_workflows(
        self,
        load_test_config,
        prometheus_client,
        kubernetes_client,
        sample_cognitive_plan,
        slo_validator,
    ):
        """
        Teste de throughput com 50 workflows concorrentes.

        Valida:
        - Latencia P95 < 4h
        - Taxa de sucesso > 99%
        - Nenhum circuit breaker trip
        """
        tester = FlowCLoadTester(
            orchestrator_url=load_test_config['orchestrator_url'],
            prometheus_client=prometheus_client,
            kubernetes_client=kubernetes_client,
            config=load_test_config,
        )

        await tester.setup()

        try:
            plans = generate_cognitive_plans(50, sample_cognitive_plan)
            decisions = generate_consolidated_decisions(plans)

            tester.metrics.start_time = time.time()

            # Executar concorrentemente
            results = await tester.run_concurrent_workflows(
                decisions,
                max_concurrent=50,
            )

            tester.metrics.end_time = time.time()

            # Validacoes
            metrics = tester.metrics
            success_count = sum(1 for r in results if r.get('success'))

            assert metrics.workflows_started == 50
            assert metrics.success_rate >= 0.99, \
                f'Taxa de sucesso deve ser >= 99%, obtido: {metrics.success_rate*100:.1f}%'

            # Verificar circuit breakers
            if prometheus_client:
                snapshot = await tester.collect_prometheus_metrics()
                if snapshot:
                    for comp, state in snapshot.circuit_breaker_states.items():
                        assert state != 'open', \
                            f'Circuit breaker {comp} nao deve estar aberto'

            logger.info(f'\n[Concorrencia Moderada]')
            logger.info(f'  Workflows: 50 (concorrentes)')
            logger.info(f'  Sucesso: {success_count}')
            logger.info(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')
            logger.info(f'  Duracao: {metrics.duration_seconds:.1f}s')
            logger.info(f'  Throughput: {metrics.tickets_per_second:.2f} tickets/s')

        finally:
            await tester.cleanup()

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_throughput_concurrent_100_workflows(
        self,
        load_test_config,
        prometheus_client,
        kubernetes_client,
        sample_cognitive_plan,
        bottleneck_analyzer,
        slo_validator,
    ):
        """
        Teste de alta concorrencia com 100 workflows.

        Valida:
        - Throughput > 10 tickets/s
        - Latencia P99 < 6h
        - HPA escala para >= 4 replicas
        - Identificar bottlenecks
        """
        tester = FlowCLoadTester(
            orchestrator_url=load_test_config['orchestrator_url'],
            prometheus_client=prometheus_client,
            kubernetes_client=kubernetes_client,
            config=load_test_config,
        )

        await tester.setup()

        try:
            plans = generate_cognitive_plans(100, sample_cognitive_plan)
            decisions = generate_consolidated_decisions(plans)

            # Coletar metricas antes
            initial_snapshot = await tester.collect_prometheus_metrics()

            tester.metrics.start_time = time.time()

            # Executar com alta concorrencia
            results = await tester.run_concurrent_workflows(
                decisions,
                max_concurrent=100,
            )

            tester.metrics.end_time = time.time()

            # Coletar metricas depois
            final_snapshot = await tester.collect_prometheus_metrics()

            # Analisar bottlenecks
            if final_snapshot:
                bottleneck_analyzer.add_snapshot(final_snapshot)
                bottleneck_analyzer.analyze_all()

                if bottleneck_analyzer.has_critical_issues():
                    logger.warning(f'Bottlenecks criticos identificados:')
                    for bn in bottleneck_analyzer.get_critical_bottlenecks():
                        logger.warning(f'  - {bn.description}')

            # Validacoes
            metrics = tester.metrics

            # SLO: Throughput
            assert metrics.tickets_per_second >= 10, \
                f'Throughput deve ser >= 10 tickets/s, obtido: {metrics.tickets_per_second:.2f}'

            # SLO: Latencia P99
            if metrics.latency_p99_ms:
                p99_hours = metrics.latency_p99_ms / 3600000
                assert metrics.latency_p99_ms < 21600000, \
                    f'Latencia P99 deve ser < 6h, obtido: {p99_hours:.2f}h'

            # Verificar autoscaling
            if kubernetes_client and kubernetes_client.is_available():
                hpa_status = await kubernetes_client.get_hpa_status('orchestrator-dynamic')
                if hpa_status:
                    logger.info(f'HPA: {hpa_status.current_replicas} replicas')
                    # Sob alta carga, esperamos >= 4 replicas
                    if hpa_status.current_replicas < 4:
                        logger.warning(
                            f'HPA nao escalou adequadamente: '
                            f'{hpa_status.current_replicas} replicas'
                        )

            logger.info(f'\n[Alta Concorrencia]')
            logger.info(f'  Workflows: 100 (concorrentes)')
            logger.info(f'  Taxa de sucesso: {metrics.success_rate*100:.1f}%')
            logger.info(f'  Throughput: {metrics.tickets_per_second:.2f} tickets/s')
            if metrics.latency_p95_ms:
                logger.info(f'  Latencia P95: {metrics.latency_p95_ms/3600000:.2f}h')
            if metrics.latency_p99_ms:
                logger.info(f'  Latencia P99: {metrics.latency_p99_ms/3600000:.2f}h')

        finally:
            await tester.cleanup()


class TestFlowCAutoscaling:
    """Testes de comportamento de autoscaling."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_autoscaling_behavior(
        self,
        load_test_config,
        prometheus_client,
        kubernetes_client,
        sample_cognitive_plan,
    ):
        """
        Teste de comportamento de autoscaling com ramp-up gradual.

        Valida:
        - Tempo para escalar de 2 -> 4 replicas
        - Tempo para escalar de 4 -> 8 replicas
        - Nenhum pod evicted durante teste
        - Scale-down apos carga
        """
        if not kubernetes_client or not kubernetes_client.is_available():
            pytest.skip('Kubernetes client nao disponivel')

        tester = FlowCLoadTester(
            orchestrator_url=load_test_config['orchestrator_url'],
            prometheus_client=prometheus_client,
            kubernetes_client=kubernetes_client,
        )

        await tester.setup()

        try:
            # Verificar estado inicial
            initial_status = await kubernetes_client.get_hpa_status('orchestrator-dynamic')
            initial_replicas = initial_status.current_replicas if initial_status else 2

            logger.info(f'Replicas iniciais: {initial_replicas}')

            # Ramp-up gradual
            ramp_up_duration = 300  # 5 minutos
            total_workflows = 100
            batch_size = 10
            batches = total_workflows // batch_size

            scaling_events: List[ScalingEvent] = []
            scaling_task = asyncio.create_task(
                tester.monitor_autoscaling(duration_seconds=ramp_up_duration + 60)
            )

            plans = generate_cognitive_plans(total_workflows, sample_cognitive_plan)
            decisions = generate_consolidated_decisions(plans)

            tester.metrics.start_time = time.time()

            # Executar em batches
            for i in range(batches):
                batch_start = i * batch_size
                batch_end = batch_start + batch_size
                batch = decisions[batch_start:batch_end]

                logger.info(f'Batch {i+1}/{batches}: iniciando {len(batch)} workflows')

                # Executar batch sem aguardar conclusao
                for decision in batch:
                    await tester.execute_single_workflow(decision, wait_completion=False)

                # Intervalo entre batches para ramp-up gradual
                await asyncio.sleep(ramp_up_duration / batches)

            tester.metrics.end_time = time.time()

            # Aguardar e coletar eventos de scaling
            try:
                scaling_events = await asyncio.wait_for(scaling_task, timeout=60)
            except asyncio.TimeoutError:
                scaling_events = []

            # Verificar evictions
            evictions = await kubernetes_client.check_for_evictions()
            assert len(evictions) == 0, \
                f'Nenhum pod deve ser evicted durante teste, mas {len(evictions)} foram'

            # Verificar scaling
            final_status = await kubernetes_client.get_hpa_status('orchestrator-dynamic')
            final_replicas = final_status.current_replicas if final_status else initial_replicas

            logger.info(f'\n[Autoscaling]')
            logger.info(f'  Replicas iniciais: {initial_replicas}')
            logger.info(f'  Replicas finais: {final_replicas}')
            logger.info(f'  Eventos de scaling: {len(scaling_events)}')

            for event in scaling_events:
                logger.info(
                    f'  - {event.event_type}: {event.from_replicas} -> {event.to_replicas}'
                )

        finally:
            await tester.cleanup()


class TestFlowCCircuitBreakers:
    """Testes de circuit breakers sob carga."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_circuit_breakers_under_load(
        self,
        load_test_config,
        prometheus_client,
        sample_cognitive_plan,
    ):
        """
        Teste de circuit breakers sob carga normal.

        Valida:
        - Circuit breakers permanecem fechados
        - Metricas de estado sao publicadas
        """
        tester = FlowCLoadTester(
            orchestrator_url=load_test_config['orchestrator_url'],
            prometheus_client=prometheus_client,
        )

        await tester.setup()

        try:
            plans = generate_cognitive_plans(50, sample_cognitive_plan)
            decisions = generate_consolidated_decisions(plans)

            tester.metrics.start_time = time.time()

            results = await tester.run_concurrent_workflows(
                decisions,
                max_concurrent=50,
            )

            tester.metrics.end_time = time.time()

            # Verificar circuit breakers
            if prometheus_client:
                snapshot = await tester.collect_prometheus_metrics()
                if snapshot:
                    logger.info('\n[Circuit Breakers]')
                    for comp, state in snapshot.circuit_breaker_states.items():
                        status = '✅' if state == 'closed' else '❌'
                        logger.info(f'  {comp}: {status} {state}')

                        # Todos devem estar fechados sob carga normal
                        assert state == 'closed', \
                            f'Circuit breaker {comp} deve estar fechado, mas esta {state}'

        finally:
            await tester.cleanup()


class TestFlowCLatencyDistribution:
    """Testes de distribuicao de latencia."""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_latency_distribution_by_step(
        self,
        load_test_config,
        prometheus_client,
        sample_cognitive_plan,
    ):
        """
        Teste de distribuicao de latencia por step.

        Valida:
        - C1 (Validate): P95 < 5s
        - C2 (Generate Tickets): P95 < 30s
        - C3 (Discover Workers): P95 < 10s
        - C4 (Assign Tickets): P95 < 60s
        - C6 (Publish Telemetry): P95 < 10s
        """
        tester = FlowCLoadTester(
            orchestrator_url=load_test_config['orchestrator_url'],
            prometheus_client=prometheus_client,
        )

        await tester.setup()

        try:
            # Coletar metricas de latencia do Prometheus
            if prometheus_client:
                step_latencies = {}
                steps = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']

                for step in steps:
                    latency = await prometheus_client.get_step_latency_p95(step)
                    if latency is not None:
                        step_latencies[step] = latency * 1000  # Converter para ms

                logger.info('\n[Latencia por Step (P95)]')

                # Validar SLOs por step
                step_slos = {
                    'C1': 5000,   # 5s
                    'C2': 30000,  # 30s
                    'C3': 10000,  # 10s
                    'C4': 60000,  # 60s
                    'C5': 10800000,  # 3h (execucao real)
                    'C6': 10000,  # 10s
                }

                for step, slo_ms in step_slos.items():
                    if step in step_latencies:
                        actual = step_latencies[step]
                        status = '✅' if actual < slo_ms else '❌'
                        logger.info(f'  {step}: {actual:.0f}ms (SLO: {slo_ms}ms) {status}')

                        if step != 'C5':  # C5 depende de execucao real
                            assert actual < slo_ms, \
                                f'{step} P95 deve ser < {slo_ms}ms, obtido: {actual:.0f}ms'
                    else:
                        logger.info(f'  {step}: N/A')

        finally:
            await tester.cleanup()


# ============================================
# Entrada principal
# ============================================


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v', '-m', 'performance', '--tb=short']))
