"""
Analisador de gargalos para testes de carga do Fluxo C.

Identifica bottlenecks em CPU, memoria, I/O, Kafka, MongoDB e Temporal
com base em metricas coletadas.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from tests.performance.prometheus_client import MetricsSnapshot

logger = logging.getLogger(__name__)


class BottleneckSeverity(str, Enum):
    """Severidade do bottleneck identificado."""
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'


class BottleneckType(str, Enum):
    """Tipo de bottleneck."""
    CPU = 'cpu'
    MEMORY = 'memory'
    IO = 'io'
    NETWORK = 'network'
    KAFKA = 'kafka'
    MONGODB = 'mongodb'
    TEMPORAL = 'temporal'
    REDIS = 'redis'


@dataclass
class Bottleneck:
    """Representacao de um bottleneck identificado."""
    type: BottleneckType
    severity: BottleneckSeverity
    metric_name: str
    current_value: float
    threshold: float
    description: str
    recommendation: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type.value,
            'severity': self.severity.value,
            'metric_name': self.metric_name,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'description': self.description,
            'recommendation': self.recommendation,
            'timestamp': self.timestamp.isoformat(),
        }


@dataclass
class BottleneckThresholds:
    """Thresholds configuraveis para deteccao de bottlenecks."""
    # CPU
    cpu_warning_percent: float = 70.0
    cpu_critical_percent: float = 85.0

    # Memoria
    memory_warning_percent: float = 75.0
    memory_critical_percent: float = 85.0

    # Kafka
    kafka_lag_warning: int = 500
    kafka_lag_critical: int = 1000

    # MongoDB
    mongodb_pool_warning_percent: float = 80.0
    mongodb_pool_critical_percent: float = 90.0

    # Temporal
    temporal_queue_warning: int = 500
    temporal_queue_critical: int = 1000

    # Latencia
    latency_p95_warning_seconds: float = 10800  # 3h
    latency_p95_critical_seconds: float = 14400  # 4h (SLO)

    # I/O
    io_utilization_warning_percent: float = 70.0
    io_utilization_critical_percent: float = 85.0
    io_time_warning_seconds: float = 0.5  # 50% do tempo em I/O
    io_time_critical_seconds: float = 0.8  # 80% do tempo em I/O

    # Network
    network_errors_warning_rate: float = 1.0  # erros/s
    network_errors_critical_rate: float = 10.0  # erros/s
    inter_service_latency_warning_seconds: float = 1.0  # 1s
    inter_service_latency_critical_seconds: float = 5.0  # 5s


class BottleneckAnalyzer:
    """Analisador de bottlenecks para testes de carga."""

    def __init__(self, thresholds: Optional[BottleneckThresholds] = None):
        """
        Inicializa o analisador.

        Args:
            thresholds: Thresholds customizados (usa padrao se nao fornecido)
        """
        self.thresholds = thresholds or BottleneckThresholds()
        self.bottlenecks: List[Bottleneck] = []
        self.snapshots: List[MetricsSnapshot] = []

    def add_snapshot(self, snapshot: MetricsSnapshot) -> None:
        """Adiciona snapshot de metricas para analise."""
        self.snapshots.append(snapshot)

    def add_snapshots(self, snapshots: List[MetricsSnapshot]) -> None:
        """Adiciona multiplos snapshots."""
        self.snapshots.extend(snapshots)

    def analyze_cpu_bottleneck(
        self,
        cpu_usage: Optional[float],
    ) -> Optional[Bottleneck]:
        """
        Analisa bottleneck de CPU.

        Args:
            cpu_usage: Uso de CPU em porcentagem

        Returns:
            Bottleneck se detectado, None caso contrario
        """
        if cpu_usage is None:
            return None

        if cpu_usage >= self.thresholds.cpu_critical_percent:
            return Bottleneck(
                type=BottleneckType.CPU,
                severity=BottleneckSeverity.CRITICAL,
                metric_name='cpu_usage_percent',
                current_value=cpu_usage,
                threshold=self.thresholds.cpu_critical_percent,
                description=f'CPU saturada: {cpu_usage:.1f}% (limite: {self.thresholds.cpu_critical_percent}%)',
                recommendation='Aumentar CPU limits ou adicionar mais replicas via HPA',
            )
        elif cpu_usage >= self.thresholds.cpu_warning_percent:
            return Bottleneck(
                type=BottleneckType.CPU,
                severity=BottleneckSeverity.WARNING,
                metric_name='cpu_usage_percent',
                current_value=cpu_usage,
                threshold=self.thresholds.cpu_warning_percent,
                description=f'CPU elevada: {cpu_usage:.1f}% (alerta: {self.thresholds.cpu_warning_percent}%)',
                recommendation='Monitorar tendencia; considerar scale-up preventivo',
            )

        return None

    def analyze_memory_bottleneck(
        self,
        memory_usage: Optional[float],
    ) -> Optional[Bottleneck]:
        """
        Analisa bottleneck de memoria.

        Args:
            memory_usage: Uso de memoria em porcentagem

        Returns:
            Bottleneck se detectado, None caso contrario
        """
        if memory_usage is None:
            return None

        if memory_usage >= self.thresholds.memory_critical_percent:
            return Bottleneck(
                type=BottleneckType.MEMORY,
                severity=BottleneckSeverity.CRITICAL,
                metric_name='memory_usage_percent',
                current_value=memory_usage,
                threshold=self.thresholds.memory_critical_percent,
                description=f'Memoria critica: {memory_usage:.1f}% (limite: {self.thresholds.memory_critical_percent}%)',
                recommendation='Aumentar memory limits imediatamente; risco de OOM',
            )
        elif memory_usage >= self.thresholds.memory_warning_percent:
            return Bottleneck(
                type=BottleneckType.MEMORY,
                severity=BottleneckSeverity.WARNING,
                metric_name='memory_usage_percent',
                current_value=memory_usage,
                threshold=self.thresholds.memory_warning_percent,
                description=f'Memoria elevada: {memory_usage:.1f}% (alerta: {self.thresholds.memory_warning_percent}%)',
                recommendation='Verificar memory leaks; considerar aumentar limits',
            )

        return None

    def analyze_kafka_bottleneck(
        self,
        consumer_lag: Optional[int],
    ) -> Optional[Bottleneck]:
        """
        Analisa bottleneck do Kafka.

        Args:
            consumer_lag: Lag do consumer em mensagens

        Returns:
            Bottleneck se detectado, None caso contrario
        """
        if consumer_lag is None:
            return None

        if consumer_lag >= self.thresholds.kafka_lag_critical:
            return Bottleneck(
                type=BottleneckType.KAFKA,
                severity=BottleneckSeverity.CRITICAL,
                metric_name='kafka_consumer_lag',
                current_value=float(consumer_lag),
                threshold=float(self.thresholds.kafka_lag_critical),
                description=f'Kafka lag critico: {consumer_lag} msgs (limite: {self.thresholds.kafka_lag_critical})',
                recommendation='Aumentar consumers ou particoes; verificar throughput de processamento',
            )
        elif consumer_lag >= self.thresholds.kafka_lag_warning:
            return Bottleneck(
                type=BottleneckType.KAFKA,
                severity=BottleneckSeverity.WARNING,
                metric_name='kafka_consumer_lag',
                current_value=float(consumer_lag),
                threshold=float(self.thresholds.kafka_lag_warning),
                description=f'Kafka lag elevado: {consumer_lag} msgs (alerta: {self.thresholds.kafka_lag_warning})',
                recommendation='Monitorar tendencia; otimizar processamento de mensagens',
            )

        return None

    def analyze_mongodb_bottleneck(
        self,
        pool_utilization: Optional[float],
    ) -> Optional[Bottleneck]:
        """
        Analisa bottleneck do MongoDB.

        Args:
            pool_utilization: Utilizacao do pool em porcentagem

        Returns:
            Bottleneck se detectado, None caso contrario
        """
        if pool_utilization is None:
            return None

        if pool_utilization >= self.thresholds.mongodb_pool_critical_percent:
            return Bottleneck(
                type=BottleneckType.MONGODB,
                severity=BottleneckSeverity.CRITICAL,
                metric_name='mongodb_pool_utilization',
                current_value=pool_utilization,
                threshold=self.thresholds.mongodb_pool_critical_percent,
                description=f'MongoDB pool saturado: {pool_utilization:.1f}% (limite: {self.thresholds.mongodb_pool_critical_percent}%)',
                recommendation='Aumentar maxPoolSize de 100 para 200; otimizar queries lentas',
            )
        elif pool_utilization >= self.thresholds.mongodb_pool_warning_percent:
            return Bottleneck(
                type=BottleneckType.MONGODB,
                severity=BottleneckSeverity.WARNING,
                metric_name='mongodb_pool_utilization',
                current_value=pool_utilization,
                threshold=self.thresholds.mongodb_pool_warning_percent,
                description=f'MongoDB pool elevado: {pool_utilization:.1f}% (alerta: {self.thresholds.mongodb_pool_warning_percent}%)',
                recommendation='Monitorar conexoes ativas; considerar connection pooling',
            )

        return None

    def analyze_temporal_bottleneck(
        self,
        queue_depth: Optional[int],
    ) -> Optional[Bottleneck]:
        """
        Analisa bottleneck do Temporal.

        Args:
            queue_depth: Profundidade da fila de tasks

        Returns:
            Bottleneck se detectado, None caso contrario
        """
        if queue_depth is None:
            return None

        if queue_depth >= self.thresholds.temporal_queue_critical:
            return Bottleneck(
                type=BottleneckType.TEMPORAL,
                severity=BottleneckSeverity.CRITICAL,
                metric_name='temporal_task_queue_depth',
                current_value=float(queue_depth),
                threshold=float(self.thresholds.temporal_queue_critical),
                description=f'Temporal queue profunda: {queue_depth} tasks (limite: {self.thresholds.temporal_queue_critical})',
                recommendation='Aumentar workers Temporal; verificar activities lentas',
            )
        elif queue_depth >= self.thresholds.temporal_queue_warning:
            return Bottleneck(
                type=BottleneckType.TEMPORAL,
                severity=BottleneckSeverity.WARNING,
                metric_name='temporal_task_queue_depth',
                current_value=float(queue_depth),
                threshold=float(self.thresholds.temporal_queue_warning),
                description=f'Temporal queue elevada: {queue_depth} tasks (alerta: {self.thresholds.temporal_queue_warning})',
                recommendation='Monitorar acumulo de tasks; otimizar duracao de activities',
            )

        return None

    def analyze_circuit_breakers(
        self,
        cb_states: Dict[str, str],
    ) -> List[Bottleneck]:
        """
        Analisa estado dos circuit breakers.

        Args:
            cb_states: Dict com estado de cada circuit breaker

        Returns:
            Lista de bottlenecks para circuit breakers abertos
        """
        bottlenecks = []

        for component, state in cb_states.items():
            if state == 'open':
                cb_type = BottleneckType.KAFKA
                if component == 'mongodb':
                    cb_type = BottleneckType.MONGODB
                elif component == 'temporal':
                    cb_type = BottleneckType.TEMPORAL
                elif component == 'redis':
                    cb_type = BottleneckType.REDIS

                bottlenecks.append(Bottleneck(
                    type=cb_type,
                    severity=BottleneckSeverity.CRITICAL,
                    metric_name=f'circuit_breaker_{component}_state',
                    current_value=1.0,  # open
                    threshold=0.0,  # closed
                    description=f'Circuit breaker {component} ABERTO',
                    recommendation=f'Verificar disponibilidade do {component}; aguardar recovery',
                ))
            elif state == 'half_open':
                cb_type = BottleneckType.KAFKA
                if component == 'mongodb':
                    cb_type = BottleneckType.MONGODB
                elif component == 'temporal':
                    cb_type = BottleneckType.TEMPORAL
                elif component == 'redis':
                    cb_type = BottleneckType.REDIS

                bottlenecks.append(Bottleneck(
                    type=cb_type,
                    severity=BottleneckSeverity.WARNING,
                    metric_name=f'circuit_breaker_{component}_state',
                    current_value=2.0,  # half_open
                    threshold=0.0,  # closed
                    description=f'Circuit breaker {component} em HALF_OPEN (recuperando)',
                    recommendation=f'Monitorar recovery do {component}',
                ))

        return bottlenecks

    def analyze_latency(
        self,
        latency_p95: Optional[float],
    ) -> Optional[Bottleneck]:
        """
        Analisa bottleneck de latencia.

        Args:
            latency_p95: Latencia P95 em segundos

        Returns:
            Bottleneck se detectado, None caso contrario
        """
        if latency_p95 is None:
            return None

        if latency_p95 >= self.thresholds.latency_p95_critical_seconds:
            return Bottleneck(
                type=BottleneckType.NETWORK,  # Usado como proxy para latencia geral
                severity=BottleneckSeverity.CRITICAL,
                metric_name='flow_c_latency_p95_seconds',
                current_value=latency_p95,
                threshold=self.thresholds.latency_p95_critical_seconds,
                description=f'Latencia P95 critica: {latency_p95/3600:.2f}h (SLO: {self.thresholds.latency_p95_critical_seconds/3600:.1f}h)',
                recommendation='Identificar step mais lento; otimizar pipeline end-to-end',
            )
        elif latency_p95 >= self.thresholds.latency_p95_warning_seconds:
            return Bottleneck(
                type=BottleneckType.NETWORK,
                severity=BottleneckSeverity.WARNING,
                metric_name='flow_c_latency_p95_seconds',
                current_value=latency_p95,
                threshold=self.thresholds.latency_p95_warning_seconds,
                description=f'Latencia P95 elevada: {latency_p95/3600:.2f}h (alerta: {self.thresholds.latency_p95_warning_seconds/3600:.1f}h)',
                recommendation='Analisar distribuicao de latencia por step',
            )

        return None

    def analyze_io_bottleneck(
        self,
        io_utilization: Optional[float],
        io_time_rate: Optional[float],
    ) -> List[Bottleneck]:
        """
        Analisa bottleneck de I/O.

        Args:
            io_utilization: Utilizacao de disco I/O em porcentagem
            io_time_rate: Taxa de tempo gasto em I/O (segundos/s)

        Returns:
            Lista de bottlenecks se detectados
        """
        bottlenecks = []

        # Analise de utilizacao de disco
        if io_utilization is not None:
            if io_utilization >= self.thresholds.io_utilization_critical_percent:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.IO,
                    severity=BottleneckSeverity.CRITICAL,
                    metric_name='disk_io_utilization_percent',
                    current_value=io_utilization,
                    threshold=self.thresholds.io_utilization_critical_percent,
                    description=f'Disco I/O saturado: {io_utilization:.1f}% (limite: {self.thresholds.io_utilization_critical_percent}%)',
                    recommendation='Usar volumes SSD; aumentar IOPS; considerar cache local',
                ))
            elif io_utilization >= self.thresholds.io_utilization_warning_percent:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.IO,
                    severity=BottleneckSeverity.WARNING,
                    metric_name='disk_io_utilization_percent',
                    current_value=io_utilization,
                    threshold=self.thresholds.io_utilization_warning_percent,
                    description=f'Disco I/O elevado: {io_utilization:.1f}% (alerta: {self.thresholds.io_utilization_warning_percent}%)',
                    recommendation='Monitorar tendencia; otimizar operacoes de disco',
                ))

        # Analise de tempo em I/O
        if io_time_rate is not None:
            if io_time_rate >= self.thresholds.io_time_critical_seconds:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.IO,
                    severity=BottleneckSeverity.CRITICAL,
                    metric_name='io_time_seconds_rate',
                    current_value=io_time_rate,
                    threshold=self.thresholds.io_time_critical_seconds,
                    description=f'Tempo I/O critico: {io_time_rate*100:.1f}% do tempo (limite: {self.thresholds.io_time_critical_seconds*100:.0f}%)',
                    recommendation='Revisar padrao de acesso a disco; implementar buffering',
                ))
            elif io_time_rate >= self.thresholds.io_time_warning_seconds:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.IO,
                    severity=BottleneckSeverity.WARNING,
                    metric_name='io_time_seconds_rate',
                    current_value=io_time_rate,
                    threshold=self.thresholds.io_time_warning_seconds,
                    description=f'Tempo I/O elevado: {io_time_rate*100:.1f}% do tempo (alerta: {self.thresholds.io_time_warning_seconds*100:.0f}%)',
                    recommendation='Otimizar batch de escrita/leitura',
                ))

        return bottlenecks

    def analyze_network_bottleneck(
        self,
        tx_errors_rate: Optional[float],
        rx_errors_rate: Optional[float],
        inter_service_latencies: Optional[Dict[str, float]],
    ) -> List[Bottleneck]:
        """
        Analisa bottleneck de rede.

        Args:
            tx_errors_rate: Taxa de erros de transmissao (erros/s)
            rx_errors_rate: Taxa de erros de recepcao (erros/s)
            inter_service_latencies: Latencias P95 entre servicos (segundos)

        Returns:
            Lista de bottlenecks se detectados
        """
        bottlenecks = []

        # Analise de erros de transmissao
        if tx_errors_rate is not None:
            if tx_errors_rate >= self.thresholds.network_errors_critical_rate:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.NETWORK,
                    severity=BottleneckSeverity.CRITICAL,
                    metric_name='network_transmit_errors_rate',
                    current_value=tx_errors_rate,
                    threshold=self.thresholds.network_errors_critical_rate,
                    description=f'Erros de rede (TX) criticos: {tx_errors_rate:.2f}/s (limite: {self.thresholds.network_errors_critical_rate})',
                    recommendation='Verificar conectividade de rede; revisar configuracao de MTU/TCP',
                ))
            elif tx_errors_rate >= self.thresholds.network_errors_warning_rate:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.NETWORK,
                    severity=BottleneckSeverity.WARNING,
                    metric_name='network_transmit_errors_rate',
                    current_value=tx_errors_rate,
                    threshold=self.thresholds.network_errors_warning_rate,
                    description=f'Erros de rede (TX) elevados: {tx_errors_rate:.2f}/s (alerta: {self.thresholds.network_errors_warning_rate})',
                    recommendation='Monitorar erros de rede; verificar saturacao de interface',
                ))

        # Analise de erros de recepcao
        if rx_errors_rate is not None:
            if rx_errors_rate >= self.thresholds.network_errors_critical_rate:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.NETWORK,
                    severity=BottleneckSeverity.CRITICAL,
                    metric_name='network_receive_errors_rate',
                    current_value=rx_errors_rate,
                    threshold=self.thresholds.network_errors_critical_rate,
                    description=f'Erros de rede (RX) criticos: {rx_errors_rate:.2f}/s (limite: {self.thresholds.network_errors_critical_rate})',
                    recommendation='Verificar configuracao de buffer de rede; aumentar capacidade',
                ))
            elif rx_errors_rate >= self.thresholds.network_errors_warning_rate:
                bottlenecks.append(Bottleneck(
                    type=BottleneckType.NETWORK,
                    severity=BottleneckSeverity.WARNING,
                    metric_name='network_receive_errors_rate',
                    current_value=rx_errors_rate,
                    threshold=self.thresholds.network_errors_warning_rate,
                    description=f'Erros de rede (RX) elevados: {rx_errors_rate:.2f}/s (alerta: {self.thresholds.network_errors_warning_rate})',
                    recommendation='Monitorar erros de rede; verificar congestao',
                ))

        # Analise de latencia entre servicos
        if inter_service_latencies:
            for service, latency in inter_service_latencies.items():
                if latency >= self.thresholds.inter_service_latency_critical_seconds:
                    bottlenecks.append(Bottleneck(
                        type=BottleneckType.NETWORK,
                        severity=BottleneckSeverity.CRITICAL,
                        metric_name=f'inter_service_latency_{service}',
                        current_value=latency,
                        threshold=self.thresholds.inter_service_latency_critical_seconds,
                        description=f'Latencia inter-servico {service} critica: {latency*1000:.0f}ms (limite: {self.thresholds.inter_service_latency_critical_seconds*1000:.0f}ms)',
                        recommendation=f'Verificar conectividade com {service}; considerar co-localizacao',
                    ))
                elif latency >= self.thresholds.inter_service_latency_warning_seconds:
                    bottlenecks.append(Bottleneck(
                        type=BottleneckType.NETWORK,
                        severity=BottleneckSeverity.WARNING,
                        metric_name=f'inter_service_latency_{service}',
                        current_value=latency,
                        threshold=self.thresholds.inter_service_latency_warning_seconds,
                        description=f'Latencia inter-servico {service} elevada: {latency*1000:.0f}ms (alerta: {self.thresholds.inter_service_latency_warning_seconds*1000:.0f}ms)',
                        recommendation=f'Otimizar comunicacao com {service}; usar cache ou batch',
                    ))

        return bottlenecks

    def analyze_snapshot(self, snapshot: MetricsSnapshot) -> List[Bottleneck]:
        """
        Analisa um snapshot de metricas.

        Args:
            snapshot: MetricsSnapshot a analisar

        Returns:
            Lista de bottlenecks identificados
        """
        bottlenecks = []

        # CPU
        cpu_bn = self.analyze_cpu_bottleneck(snapshot.cpu_usage_percent)
        if cpu_bn:
            bottlenecks.append(cpu_bn)

        # Memoria
        mem_bn = self.analyze_memory_bottleneck(snapshot.memory_usage_percent)
        if mem_bn:
            bottlenecks.append(mem_bn)

        # Kafka
        kafka_bn = self.analyze_kafka_bottleneck(snapshot.kafka_lag)
        if kafka_bn:
            bottlenecks.append(kafka_bn)

        # MongoDB
        mongo_bn = self.analyze_mongodb_bottleneck(snapshot.mongodb_pool_utilization)
        if mongo_bn:
            bottlenecks.append(mongo_bn)

        # Temporal
        temporal_bn = self.analyze_temporal_bottleneck(snapshot.temporal_queue_depth)
        if temporal_bn:
            bottlenecks.append(temporal_bn)

        # Circuit Breakers
        cb_bottlenecks = self.analyze_circuit_breakers(snapshot.circuit_breaker_states)
        bottlenecks.extend(cb_bottlenecks)

        # Latencia
        latency_bn = self.analyze_latency(snapshot.flow_c_latency_p95)
        if latency_bn:
            bottlenecks.append(latency_bn)

        # I/O
        io_bottlenecks = self.analyze_io_bottleneck(
            io_utilization=snapshot.disk_io_utilization,
            io_time_rate=snapshot.io_time_seconds_rate,
        )
        bottlenecks.extend(io_bottlenecks)

        # Network
        network_bottlenecks = self.analyze_network_bottleneck(
            tx_errors_rate=snapshot.network_transmit_errors_rate,
            rx_errors_rate=snapshot.network_receive_errors_rate,
            inter_service_latencies=snapshot.inter_service_latencies,
        )
        bottlenecks.extend(network_bottlenecks)

        return bottlenecks

    def analyze_all(self) -> List[Bottleneck]:
        """
        Analisa todos os snapshots coletados.

        Returns:
            Lista consolidada de bottlenecks
        """
        all_bottlenecks = []

        for snapshot in self.snapshots:
            snapshot_bns = self.analyze_snapshot(snapshot)
            all_bottlenecks.extend(snapshot_bns)

        # Deduplicar bottlenecks similares
        self.bottlenecks = self._deduplicate_bottlenecks(all_bottlenecks)
        return self.bottlenecks

    def _deduplicate_bottlenecks(
        self,
        bottlenecks: List[Bottleneck],
    ) -> List[Bottleneck]:
        """
        Remove bottlenecks duplicados, mantendo o mais severo.

        Args:
            bottlenecks: Lista de bottlenecks

        Returns:
            Lista deduplicada
        """
        unique: Dict[str, Bottleneck] = {}

        severity_order = {
            BottleneckSeverity.INFO: 0,
            BottleneckSeverity.WARNING: 1,
            BottleneckSeverity.CRITICAL: 2,
        }

        for bn in bottlenecks:
            key = f'{bn.type.value}_{bn.metric_name}'

            if key not in unique:
                unique[key] = bn
            else:
                # Manter o mais severo ou mais recente se igual
                existing = unique[key]
                if severity_order[bn.severity] > severity_order[existing.severity]:
                    unique[key] = bn
                elif (
                    severity_order[bn.severity] == severity_order[existing.severity]
                    and bn.current_value > existing.current_value
                ):
                    unique[key] = bn

        return list(unique.values())

    def get_critical_bottlenecks(self) -> List[Bottleneck]:
        """Retorna apenas bottlenecks criticos."""
        return [
            bn for bn in self.bottlenecks
            if bn.severity == BottleneckSeverity.CRITICAL
        ]

    def get_warnings(self) -> List[Bottleneck]:
        """Retorna apenas warnings."""
        return [
            bn for bn in self.bottlenecks
            if bn.severity == BottleneckSeverity.WARNING
        ]

    def has_critical_issues(self) -> bool:
        """Verifica se ha bottlenecks criticos."""
        return len(self.get_critical_bottlenecks()) > 0

    def generate_summary(self) -> Dict[str, Any]:
        """
        Gera resumo da analise de bottlenecks.

        Returns:
            Dict com resumo
        """
        critical = self.get_critical_bottlenecks()
        warnings = self.get_warnings()

        return {
            'total_bottlenecks': len(self.bottlenecks),
            'critical_count': len(critical),
            'warning_count': len(warnings),
            'has_critical': self.has_critical_issues(),
            'bottlenecks_by_type': self._group_by_type(),
            'recommendations': [bn.recommendation for bn in self.bottlenecks],
            'critical_details': [bn.to_dict() for bn in critical],
            'warning_details': [bn.to_dict() for bn in warnings],
        }

    def _group_by_type(self) -> Dict[str, int]:
        """Agrupa bottlenecks por tipo."""
        groups: Dict[str, int] = {}
        for bn in self.bottlenecks:
            key = bn.type.value
            groups[key] = groups.get(key, 0) + 1
        return groups

    def generate_report(self) -> str:
        """
        Gera relatorio markdown de bottlenecks.

        Returns:
            String com relatorio em formato markdown
        """
        lines = ['## Analise de Bottlenecks', '']

        if not self.bottlenecks:
            lines.append('Nenhum bottleneck identificado durante o teste.')
            return '\n'.join(lines)

        critical = self.get_critical_bottlenecks()
        warnings = self.get_warnings()

        lines.append(f'**Total:** {len(self.bottlenecks)} bottlenecks identificados')
        lines.append(f'- Criticos: {len(critical)}')
        lines.append(f'- Warnings: {len(warnings)}')
        lines.append('')

        # Agrupar por categoria
        by_type = self._group_by_type()
        lines.append('**Por categoria:**')
        for type_name, count in by_type.items():
            lines.append(f'- {type_name.upper()}: {count}')
        lines.append('')

        if critical:
            lines.append('### Bottlenecks Criticos')
            lines.append('')
            for i, bn in enumerate(critical, 1):
                lines.append(f'{i}. **{bn.type.value.upper()}** - {bn.description}')
                lines.append(f'   - Valor atual: {bn.current_value:.2f}')
                lines.append(f'   - Limite: {bn.threshold:.2f}')
                lines.append(f'   - Recomendacao: {bn.recommendation}')
                lines.append('')

        if warnings:
            lines.append('### Warnings')
            lines.append('')
            for i, bn in enumerate(warnings, 1):
                lines.append(f'{i}. **{bn.type.value.upper()}** - {bn.description}')
                lines.append(f'   - Recomendacao: {bn.recommendation}')
                lines.append('')

        # Secao de I/O (Comment 5)
        io_bottlenecks = [bn for bn in self.bottlenecks if bn.type == BottleneckType.IO]
        if io_bottlenecks:
            lines.append('### Bottlenecks de I/O')
            lines.append('')
            for bn in io_bottlenecks:
                lines.append(f'- {bn.description}')
                lines.append(f'  - Recomendacao: {bn.recommendation}')
            lines.append('')

        # Secao de Rede (Comment 5)
        network_bottlenecks = [bn for bn in self.bottlenecks if bn.type == BottleneckType.NETWORK]
        if network_bottlenecks:
            lines.append('### Bottlenecks de Rede')
            lines.append('')
            for bn in network_bottlenecks:
                lines.append(f'- {bn.description}')
                lines.append(f'  - Recomendacao: {bn.recommendation}')
            lines.append('')

        return '\n'.join(lines)
