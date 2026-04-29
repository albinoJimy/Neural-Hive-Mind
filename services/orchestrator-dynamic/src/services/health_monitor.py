"""
Health Monitor para monitorar saúde do sistema durante cutover.

Coleta métricas de ambos os sistemas (legacy e target), detecta anomalias,
e triggera rollback automático se thresholds forem excedidos.

Métricas coletadas:
1. Error Rate - HTTP 5xx / total requests
2. Latência - P50, P95, P99 response times
3. Business Metrics - Throughput, sessions, conversions
4. Infrastructure - CPU, Memory, Disk, Network
"""

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
UTC = timezone.utc
from enum import Enum
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field, field_validator

UTC = timezone.utc
logger = structlog.get_logger(__name__)


class HealthStatus(str, Enum):
    """Status de saúde do sistema."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DOWN = "down"


class MetricType(str, Enum):
    """Tipos de métricas coletadas."""

    ERROR_RATE = "error_rate"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    INFRASTRUCTURE = "infrastructure"
    BUSINESS = "business"


@dataclass(frozen=True)
class HealthThreshold:
    """Thresholds para avaliação de saúde."""

    # Error rate thresholds
    error_rate_warning: float = 0.01  # 1%
    error_rate_critical: float = 0.05  # 5%
    error_rate_rollback: float = 0.05  # 5%

    # Latency thresholds (ms)
    p95_latency_warning_ms: int = 1000
    p95_latency_critical_ms: int = 2000
    p95_latency_rollback_ms: int = 2000
    p99_latency_warning_ms: int = 2000
    p99_latency_critical_ms: int = 5000

    # Throughput thresholds
    throughput_drop_warning: float = 0.20  # 20% drop
    throughput_drop_critical: float = 0.50  # 50% drop

    # Infrastructure thresholds
    cpu_warning: float = 0.70  # 70%
    cpu_critical: float = 0.90  # 90%
    memory_warning: float = 0.80  # 80%
    memory_critical: float = 0.95  # 95%
    disk_warning: float = 0.80  # 80%
    disk_critical: float = 0.90  # 90%

    # Availability
    consecutive_failures_warning: int = 3
    consecutive_failures_critical: int = 5
    consecutive_failures_rollback: int = 5


class SystemHealth(BaseModel):
    """Modelo de saúde de um sistema."""

    service_name: str = Field(..., description="Nome do serviço")
    status: HealthStatus = Field(default=HealthStatus.HEALTHY, description="Status atual")

    # Métricas de erro
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Taxa de erro (0-1)")

    # Métricas de latência (ms)
    latency_p50_ms: float = Field(default=0.0, ge=0.0, description="Latência P50 em ms")
    latency_p95_ms: float = Field(default=0.0, ge=0.0, description="Latência P95 em ms")
    latency_p99_ms: float = Field(default=0.0, ge=0.0, description="Latência P99 em ms")

    # Métricas de volume
    throughput_rps: float = Field(default=0.0, ge=0.0, description="Requisições por segundo")

    # Métricas de infraestrutura
    cpu_usage: float = Field(default=0.0, ge=0.0, le=1.0, description="Uso de CPU (0-1)")
    memory_usage: float = Field(default=0.0, ge=0.0, le=1.0, description="Uso de memória (0-1)")
    disk_usage: float = Field(default=0.0, ge=0.0, le=1.0, description="Uso de disco (0-1)")

    # Timestamp
    last_check: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Anomalias detectadas
    anomalies: list[str] = Field(default_factory=list, description="Anomalias detectadas")

    @field_validator("status")
    @classmethod
    def validate_status_consistency(cls, v: HealthStatus) -> HealthStatus:
        """Valida consistência do status com as métricas."""
        # Validador passivo - apenas logging, não altera status
        # O status deve ser definido explicitamente pelo monitor
        return v


class HealthComparison(BaseModel):
    """Comparação de saúde entre legacy e target."""

    legacy_health: SystemHealth
    target_health: SystemHealth

    # Métricas de comparação
    error_rate_delta: float = Field(default=0.0, description="Diferença de error rate")
    latency_p95_ratio: float = Field(default=1.0, description="Ratio P95 target/legacy")
    throughput_ratio: float = Field(default=1.0, description="Ratio throughput target/legacy")

    # Status geral
    overall_status: HealthStatus = Field(default=HealthStatus.HEALTHY)
    should_rollback: bool = Field(default=False)
    rollback_reason: str | None = Field(default=None)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HealthMonitorConfig(BaseModel):
    """Configuração do Health Monitor."""

    # URLs dos serviços
    legacy_service_url: str
    target_service_url: str

    # Intervalo de coleta (segundos)
    collection_interval_seconds: int = Field(default=30, ge=10, le=300)

    # Timeout para health checks (segundos)
    health_check_timeout_seconds: int = Field(default=5, ge=1, le=30)

    # Thresholds
    thresholds: HealthThreshold = Field(default_factory=HealthThreshold)

    # Flags
    enable_auto_rollback: bool = Field(default=True)
    enable_prometheus_metrics: bool = Field(default=True)
    enable_infrastructure_monitoring: bool = Field(default=True)

    # Métricas Prometheus (opcional)
    prometheus_url: str | None = Field(default=None)
    prometheus_query_timeout_seconds: int = Field(default=10, ge=1, le=60)


class HealthMonitor:
    """
    Monitor de saúde para cutover.

    Responsável por:
    - Coletar métricas de ambos os sistemas (legacy e target)
    - Comparar métricas e detectar anomalias
    - Triggerar rollback automático se thresholds excedidos
    - Fornecer dashboard de health em tempo real
    """

    def __init__(
        self,
        config: HealthMonitorConfig,
        rollback_callback=None,
        metrics_client=None,
    ):
        """
        Inicializa o HealthMonitor.

        Args:
            config: Configuração do monitor
            rollback_callback: Callback para executar rollback (opcional)
            metrics_client: Cliente Prometheus/OpenTelemetry (opcional)
        """
        self.config = config
        self.rollback_callback = rollback_callback
        self.metrics_client = metrics_client

        # Estado do monitor
        self._running = False
        self._monitor_task: asyncio.Task | None = None

        # Histórico de métricas
        self._legacy_health: SystemHealth | None = None
        self._target_health: SystemHealth | None = None
        self._comparison_history: list[HealthComparison] = []

        # Contadores de falhas consecutivas
        self._legacy_consecutive_failures = 0
        self._target_consecutive_failures = 0

        # HTTP client para health checks
        self._http_client = httpx.AsyncClient(
            timeout=self.config.health_check_timeout_seconds,
        )

        self.logger = logger.bind(component="health_monitor")

    async def start_monitoring(self) -> None:
        """
        Inicia coleta de métricas em background.

        Inicia uma tarefa assíncrona que coleta métricas periodicamente.
        """
        if self._running:
            self.logger.warning("monitor_already_running")
            return

        self._running = True
        self.logger.info(
            "health_monitor_started",
            interval_seconds=self.config.collection_interval_seconds,
            legacy_url=self.config.legacy_service_url,
            target_url=self.config.target_service_url,
        )

        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitoring(self) -> None:
        """
        Para coleta de métricas.

        Cancela a tarefa de monitoramento em background.
        """
        self._running = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task

        self.logger.info("health_monitor_stopped")

    async def get_health_status(self) -> HealthComparison:
        """
        Retorna status atual de saúde.

        Coleta métricas frescas e retorna comparação entre sistemas.

        Returns:
            HealthComparison com status atual
        """
        legacy_health = await self._check_system_health(
            service_url=self.config.legacy_service_url,
            service_name="legacy",
        )
        target_health = await self._check_system_health(
            service_url=self.config.target_service_url,
            service_name="target",
        )

        # Atualizar cache
        self._legacy_health = legacy_health
        self._target_health = target_health

        comparison = self._compare_health(legacy_health, target_health)
        return comparison

    async def check_rollback_conditions(self) -> tuple[bool, str | None]:
        """
        Avalia se rollback é necessário.

        Returns:
            Tupla (should_rollback, reason)
        """
        comparison = await self.get_health_status()

        if comparison.should_rollback:
            return True, comparison.rollback_reason

        return False, None

    async def _monitor_loop(self) -> None:
        """
        Loop de monitoramento em background.

        Coleta métricas periodicamente e avalia condições.
        """
        while self._running:
            try:
                comparison = await self.get_health_status()

                # Adicionar ao histórico
                self._comparison_history.append(comparison)

                # Manter histórico limitado (últimas 1000 comparações)
                if len(self._comparison_history) > 1000:
                    self._comparison_history = self._comparison_history[-1000:]

                # Registrar métricas
                self._record_metrics(comparison)

                # Verificar condições de rollback
                if comparison.should_rollback and self.config.enable_auto_rollback:
                    self.logger.warning(
                        "rollback_condition_detected",
                        reason=comparison.rollback_reason,
                        target_status=comparison.target_health.status.value,
                        error_rate=comparison.target_health.error_rate,
                        p95_latency_ms=comparison.target_health.latency_p95_ms,
                    )

                    # Executar rollback
                    if self.rollback_callback:
                        await self.rollback_callback(comparison.rollback_reason)

                await asyncio.sleep(self.config.collection_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.exception("monitor_loop_error", error=str(e))
                await asyncio.sleep(self.config.collection_interval_seconds)

    async def _check_system_health(
        self,
        service_url: str,
        service_name: str,
    ) -> SystemHealth:
        """
        Verifica saúde de um sistema específico.

        Coleta métricas via health check endpoint.

        Args:
            service_url: URL do serviço
            service_name: Nome do serviço

        Returns:
            SystemHealth com métricas coletadas
        """
        health_url = f"{service_url.rstrip('/')}/health"
        anomalies: list[str] = []

        try:
            response = await self._http_client.get(health_url)
            response.raise_for_status()

            # Reset contador de falhas
            if service_name == "legacy":
                self._legacy_consecutive_failures = 0
            else:
                self._target_consecutive_failures = 0

            # Parse response JSON
            data = response.json()

            return SystemHealth(
                service_name=service_name,
                status=self._determine_status_from_response(data),
                error_rate=data.get("error_rate", 0.0),
                latency_p50_ms=data.get("latency_p50_ms", 0.0),
                latency_p95_ms=data.get("latency_p95_ms", 0.0),
                latency_p99_ms=data.get("latency_p99_ms", 0.0),
                throughput_rps=data.get("throughput_rps", 0.0),
                cpu_usage=data.get("cpu_usage", 0.0),
                memory_usage=data.get("memory_usage", 0.0),
                disk_usage=data.get("disk_usage", 0.0),
                anomalies=anomalies,
            )

        except httpx.HTTPStatusError as e:
            # Servidor respondeu com erro
            anomalies.append(f"HTTP {e.response.status_code}")

            if service_name == "legacy":
                self._legacy_consecutive_failures += 1
            else:
                self._target_consecutive_failures += 1

            return SystemHealth(
                service_name=service_name,
                status=(
                    HealthStatus.CRITICAL
                    if e.response.status_code >= 500
                    else HealthStatus.DEGRADED
                ),
                anomalies=anomalies,
            )

        except httpx.ConnectError:
            # Servidor não responde
            anomalies.append("connection_refused")

            if service_name == "legacy":
                self._legacy_consecutive_failures += 1
            else:
                self._target_consecutive_failures += 1

            return SystemHealth(
                service_name=service_name,
                status=HealthStatus.DOWN,
                anomalies=anomalies,
            )

        except httpx.TimeoutException:
            # Timeout
            anomalies.append("timeout")

            if service_name == "legacy":
                self._legacy_consecutive_failures += 1
            else:
                self._target_consecutive_failures += 1

            return SystemHealth(
                service_name=service_name,
                status=HealthStatus.DOWN,
                anomalies=anomalies,
            )

        except Exception as e:
            # Erro genérico
            anomalies.append(f"unknown_error: {e!s}")

            if service_name == "legacy":
                self._legacy_consecutive_failures += 1
            else:
                self._target_consecutive_failures += 1

            return SystemHealth(
                service_name=service_name,
                status=HealthStatus.DOWN,
                anomalies=anomalies,
            )

    def _determine_status_from_response(self, data: dict[str, Any]) -> HealthStatus:
        """
        Determina status baseado na response do health check.

        Args:
            data: Dados do health check

        Returns:
            HealthStatus determinado
        """
        thresholds = self.config.thresholds

        # Error rate crítico
        error_rate = data.get("error_rate", 0.0)
        if error_rate >= thresholds.error_rate_critical:
            return HealthStatus.CRITICAL

        # Latência crítica
        p95_latency = data.get("latency_p95_ms", 0)
        if p95_latency >= thresholds.p95_latency_critical_ms:
            return HealthStatus.CRITICAL

        # CPU/Memória críticos
        cpu = data.get("cpu_usage", 0.0)
        memory = data.get("memory_usage", 0.0)
        if cpu >= thresholds.cpu_critical or memory >= thresholds.memory_critical:
            return HealthStatus.CRITICAL

        # Error rate warning
        if error_rate >= thresholds.error_rate_warning:
            return HealthStatus.DEGRADED

        # Latência warning
        if p95_latency >= thresholds.p95_latency_warning_ms:
            return HealthStatus.DEGRADED

        # CPU/Memória warning
        if cpu >= thresholds.cpu_warning or memory >= thresholds.memory_warning:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    def _compare_health(
        self,
        legacy_health: SystemHealth,
        target_health: SystemHealth,
    ) -> HealthComparison:
        """
        Compara saúde entre legacy e target.

        Args:
            legacy_health: Saúde do sistema legado
            target_health: Saúde do sistema alvo

        Returns:
            HealthComparison com análise comparativa
        """
        thresholds = self.config.thresholds

        # Calcular deltas
        error_rate_delta = target_health.error_rate - legacy_health.error_rate

        if legacy_health.latency_p95_ms > 0:
            latency_p95_ratio = target_health.latency_p95_ms / legacy_health.latency_p95_ms
        else:
            latency_p95_ratio = 1.0

        if legacy_health.throughput_rps > 0:
            throughput_ratio = target_health.throughput_rps / legacy_health.throughput_rps
        else:
            throughput_ratio = 1.0

        # Determinar status geral
        should_rollback = False
        rollback_reason: str | None = None
        overall_status = HealthStatus.HEALTHY

        # Verificar rollback conditions
        if target_health.status == HealthStatus.DOWN:
            should_rollback = True
            rollback_reason = "Target system is DOWN"
            overall_status = HealthStatus.CRITICAL
        elif target_health.error_rate >= thresholds.error_rate_rollback:
            should_rollback = True
            rollback_reason = (
                f"Error rate {target_health.error_rate:.2%} exceeds rollback threshold "
                f"{thresholds.error_rate_rollback:.2%}"
            )
            overall_status = HealthStatus.CRITICAL
        elif target_health.latency_p95_ms >= thresholds.p95_latency_rollback_ms:
            should_rollback = True
            rollback_reason = (
                f"P95 latency {target_health.latency_p95_ms:.0f}ms exceeds rollback threshold "
                f"{thresholds.p95_latency_rollback_ms}ms"
            )
            overall_status = HealthStatus.CRITICAL
        elif self._target_consecutive_failures >= thresholds.consecutive_failures_rollback:
            should_rollback = True
            rollback_reason = (
                f"Target system has {self._target_consecutive_failures} consecutive failures"
            )
            overall_status = HealthStatus.CRITICAL
        elif latency_p95_ratio >= 2.0:
            # Latência P95 > 2x legacy
            should_rollback = True
            rollback_reason = f"P95 latency is {latency_p95_ratio:.1f}x legacy (threshold: 2x)"
            overall_status = HealthStatus.CRITICAL

        # Se não é rollback, verificar degraded
        if not should_rollback:
            if target_health.status == HealthStatus.CRITICAL:
                overall_status = HealthStatus.CRITICAL
            elif (
                target_health.status == HealthStatus.DEGRADED
                or error_rate_delta > 0.02
                or latency_p95_ratio > 1.5
            ):
                overall_status = HealthStatus.DEGRADED

        return HealthComparison(
            legacy_health=legacy_health,
            target_health=target_health,
            error_rate_delta=error_rate_delta,
            latency_p95_ratio=latency_p95_ratio,
            throughput_ratio=throughput_ratio,
            overall_status=overall_status,
            should_rollback=should_rollback,
            rollback_reason=rollback_reason,
        )

    def _record_metrics(self, comparison: HealthComparison) -> None:
        """
        Registra métricas no Prometheus/OpenTelemetry.

        Args:
            comparison: Comparação de saúde a registrar
        """
        if not self.metrics_client or not self.config.enable_prometheus_metrics:
            return

        try:
            # Implementação depende do cliente de métricas
            # Exemplo com Prometheus:
            # self.metrics_client.gauge("health_error_rate").labels(
            #     service="legacy"
            # ).set(comparison.legacy_health.error_rate)
            # self.metrics_client.gauge("health_error_rate").labels(
            #     service="target"
            # ).set(comparison.target_health.error_rate)
            pass
        except Exception as e:
            self.logger.warning("record_metrics_failed", error=str(e))

    def get_metrics_history(self, limit: int = 100) -> list[HealthComparison]:
        """
        Retorna histórico de comparações de saúde.

        Args:
            limit: Número máximo de registros

        Returns:
            Lista de comparações históricas
        """
        return self._comparison_history[-limit:]

    def get_current_health(self) -> tuple[SystemHealth | None, SystemHealth | None]:
        """
        Retorna saúde atual de ambos os sistemas.

        Returns:
            Tupla (legacy_health, target_health)
        """
        return self._legacy_health, self._target_health

    async def close(self) -> None:
        """
        Limpa recursos do monitor.
        """
        await self.stop_monitoring()
        await self._http_client.aclose()

        self.logger.info("health_monitor_closed")
