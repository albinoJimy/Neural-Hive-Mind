"""
Health checks distribuídos para Neural Hive-Mind.

Implementa health checks padronizados com endpoint /health e integração
com métricas Prometheus para monitoramento de componentes críticos.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import threading

from .config import ObservabilityConfig

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Status de health check."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Resultado de health check."""
    name: str
    status: HealthStatus
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    duration_seconds: float = 0.0
    timestamp: float = 0.0


class HealthCheck(ABC):
    """Interface base para health checks."""

    def __init__(self, name: str, timeout_seconds: float = 5.0):
        """
        Inicializa health check.

        Args:
            name: Nome do health check
            timeout_seconds: Timeout em segundos
        """
        self.name = name
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """
        Executa health check.

        Returns:
            Resultado do health check
        """
        pass

    def _create_result(
        self,
        status: HealthStatus,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        start_time: float = 0.0
    ) -> HealthCheckResult:
        """Cria resultado padronizado."""
        return HealthCheckResult(
            name=self.name,
            status=status,
            message=message,
            details=details or {},
            duration_seconds=time.time() - start_time if start_time > 0 else 0.0,
            timestamp=time.time()
        )


class DatabaseHealthCheck(HealthCheck):
    """Health check para conexão com banco de dados."""

    def __init__(self, name: str = "database", connection_check: Optional[Callable] = None):
        """
        Inicializa health check de database.

        Args:
            name: Nome do check
            connection_check: Função que retorna True se conectado
        """
        super().__init__(name)
        self.connection_check = connection_check

    async def check(self) -> HealthCheckResult:
        """Verifica conexão com database."""
        start_time = time.time()

        try:
            if self.connection_check:
                if await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self.connection_check
                    ),
                    timeout=self.timeout_seconds
                ):
                    return self._create_result(
                        HealthStatus.HEALTHY,
                        "Conexão com database OK",
                        start_time=start_time
                    )
                else:
                    return self._create_result(
                        HealthStatus.UNHEALTHY,
                        "Falha na conexão com database",
                        start_time=start_time
                    )
            else:
                return self._create_result(
                    HealthStatus.UNKNOWN,
                    "Health check de database não configurado",
                    start_time=start_time
                )

        except asyncio.TimeoutError:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Timeout na conexão com database ({self.timeout_seconds}s)",
                start_time=start_time
            )
        except Exception as e:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Erro na conexão com database: {str(e)}",
                start_time=start_time
            )


class KafkaHealthCheck(HealthCheck):
    """Health check para conexão com Kafka."""

    def __init__(self, name: str = "kafka", producer_check: Optional[Callable] = None):
        """
        Inicializa health check do Kafka.

        Args:
            name: Nome do check
            producer_check: Função que verifica producer
        """
        super().__init__(name)
        self.producer_check = producer_check

    async def check(self) -> HealthCheckResult:
        """Verifica conexão com Kafka."""
        start_time = time.time()

        try:
            if self.producer_check:
                if await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self.producer_check
                    ),
                    timeout=self.timeout_seconds
                ):
                    return self._create_result(
                        HealthStatus.HEALTHY,
                        "Conexão com Kafka OK",
                        start_time=start_time
                    )
                else:
                    return self._create_result(
                        HealthStatus.UNHEALTHY,
                        "Falha na conexão com Kafka",
                        start_time=start_time
                    )
            else:
                return self._create_result(
                    HealthStatus.UNKNOWN,
                    "Health check do Kafka não configurado",
                    start_time=start_time
                )

        except asyncio.TimeoutError:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Timeout na conexão com Kafka ({self.timeout_seconds}s)",
                start_time=start_time
            )
        except Exception as e:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Erro na conexão com Kafka: {str(e)}",
                start_time=start_time
            )


class MemoryHealthCheck(HealthCheck):
    """Health check para uso de memória."""

    def __init__(self, name: str = "memory", max_memory_percent: float = 80.0):
        """
        Inicializa health check de memória.

        Args:
            name: Nome do check
            max_memory_percent: Percentual máximo de memória
        """
        super().__init__(name)
        self.max_memory_percent = max_memory_percent

    async def check(self) -> HealthCheckResult:
        """Verifica uso de memória."""
        start_time = time.time()

        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()

            details = {
                "memory_rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                "memory_vms_mb": round(memory_info.vms / 1024 / 1024, 2),
                "memory_percent": round(memory_percent, 2),
                "max_memory_percent": self.max_memory_percent
            }

            if memory_percent > self.max_memory_percent:
                return self._create_result(
                    HealthStatus.UNHEALTHY,
                    f"Alto uso de memória: {memory_percent:.1f}%",
                    details=details,
                    start_time=start_time
                )
            elif memory_percent > self.max_memory_percent * 0.8:
                return self._create_result(
                    HealthStatus.DEGRADED,
                    f"Uso de memória elevado: {memory_percent:.1f}%",
                    details=details,
                    start_time=start_time
                )
            else:
                return self._create_result(
                    HealthStatus.HEALTHY,
                    f"Uso de memória normal: {memory_percent:.1f}%",
                    details=details,
                    start_time=start_time
                )

        except ImportError:
            return self._create_result(
                HealthStatus.UNKNOWN,
                "psutil não disponível para check de memória",
                start_time=start_time
            )
        except Exception as e:
            return self._create_result(
                HealthStatus.UNHEALTHY,
                f"Erro ao verificar memória: {str(e)}",
                start_time=start_time
            )


class HealthChecker:
    """Gerenciador de health checks."""

    def __init__(self, config: ObservabilityConfig):
        """
        Inicializa health checker.

        Args:
            config: Configuração de observabilidade
        """
        self.config = config
        self.checks: Dict[str, HealthCheck] = {}
        self._last_results: Dict[str, HealthCheckResult] = {}
        self._lock = threading.Lock()

    def register_check(self, check: HealthCheck) -> None:
        """
        Registra health check.

        Args:
            check: Health check a ser registrado
        """
        with self._lock:
            self.checks[check.name] = check
            logger.info(f"Health check '{check.name}' registrado")

    def register_default_checks(self) -> None:
        """Registra health checks padrão."""
        # Memory check
        self.register_check(MemoryHealthCheck())

        logger.info(f"Health checks padrão registrados: {list(self.checks.keys())}")

    async def check_all(self) -> Dict[str, HealthCheckResult]:
        """
        Executa todos os health checks.

        Returns:
            Dicionário com resultados de todos os checks
        """
        results = {}

        for name, check in self.checks.items():
            try:
                result = await check.check()
                results[name] = result

                # Atualizar cache de resultados
                with self._lock:
                    self._last_results[name] = result

                # Atualizar métrica se disponível
                self._update_health_metric(name, result.status == HealthStatus.HEALTHY)

            except Exception as e:
                logger.error(f"Erro ao executar health check '{name}': {e}")
                result = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Erro interno: {str(e)}",
                    timestamp=time.time()
                )
                results[name] = result

        return results

    async def check_single(self, check_name: str) -> Optional[HealthCheckResult]:
        """
        Executa um health check específico.

        Args:
            check_name: Nome do check

        Returns:
            Resultado do check ou None se não encontrado
        """
        check = self.checks.get(check_name)
        if not check:
            return None

        try:
            result = await check.check()
            with self._lock:
                self._last_results[check_name] = result

            self._update_health_metric(check_name, result.status == HealthStatus.HEALTHY)
            return result

        except Exception as e:
            logger.error(f"Erro ao executar health check '{check_name}': {e}")
            return HealthCheckResult(
                name=check_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Erro interno: {str(e)}",
                timestamp=time.time()
            )

    def get_last_results(self) -> Dict[str, HealthCheckResult]:
        """Retorna últimos resultados dos health checks."""
        with self._lock:
            return self._last_results.copy()

    def get_overall_status(self) -> HealthStatus:
        """
        Retorna status geral de saúde.

        Returns:
            Status consolidado de todos os checks
        """
        with self._lock:
            if not self._last_results:
                return HealthStatus.UNKNOWN

            statuses = [result.status for result in self._last_results.values()]

            # Se qualquer check está unhealthy, sistema está unhealthy
            if HealthStatus.UNHEALTHY in statuses:
                return HealthStatus.UNHEALTHY

            # Se qualquer check está degraded, sistema está degraded
            if HealthStatus.DEGRADED in statuses:
                return HealthStatus.DEGRADED

            # Se todos estão healthy, sistema está healthy
            if all(status == HealthStatus.HEALTHY for status in statuses):
                return HealthStatus.HEALTHY

            return HealthStatus.UNKNOWN

    def _update_health_metric(self, check_name: str, is_healthy: bool):
        """Atualiza métrica de health check."""
        try:
            from . import get_metrics
            metrics = get_metrics()
            if metrics:
                metrics.set_health_status(check_name, is_healthy)
        except Exception as e:
            logger.debug(f"Erro ao atualizar métrica de health: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """
        Converte estado atual para dicionário.

        Returns:
            Dicionário com status e detalhes
        """
        with self._lock:
            results_dict = {}
            for name, result in self._last_results.items():
                results_dict[name] = {
                    "status": result.status.value,
                    "message": result.message,
                    "details": result.details,
                    "duration_seconds": result.duration_seconds,
                    "timestamp": result.timestamp,
                }

            return {
                "overall_status": self.get_overall_status().value,
                "service": {
                    "name": self.config.service_name,
                    "version": self.config.service_version,
                    "component": self.config.neural_hive_component,
                    "layer": self.config.neural_hive_layer,
                },
                "checks": results_dict,
                "timestamp": time.time(),
            }