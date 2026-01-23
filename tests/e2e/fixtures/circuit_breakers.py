"""
Fixtures para testes de circuit breakers.

Fornece:
- Port-forward managers para simular indisponibilidade
- Helpers para validar estado de circuit breakers
- Helpers para validar metricas
"""

import contextlib
import logging
import os
import signal
import subprocess
import time
from typing import Dict, Generator, Optional

import httpx
import pytest

logger = logging.getLogger(__name__)

# Configuracao padrao
PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://prometheus-server.monitoring.svc.cluster.local:9090",
)

# Mapeamento de servicos para port-forward
SERVICE_PORT_CONFIGS: Dict[str, tuple] = {
    "mongodb": ("mongodb-cluster", "mongodb-cluster", 27017, 27017),
    "opa": ("neural-hive-orchestration", "opa", 8181, 8181),
    "service_registry": ("neural-hive", "service-registry", 50051, 50051),
    "etcd": ("neural-hive", "etcd", 2379, 2379),
    "postgresql_tickets": ("neural-hive-orchestration", "postgresql-tickets", 5432, 5432),
    "redis": ("redis-cluster", "redis-cluster", 6379, 6379),
}


def _start_port_forward(
    namespace: str,
    service: str,
    local_port: int,
    remote_port: int,
) -> subprocess.Popen:
    """
    Inicia port-forward para um servico Kubernetes.

    Args:
        namespace: Namespace do Kubernetes
        service: Nome do servico
        local_port: Porta local para bind
        remote_port: Porta remota do servico

    Returns:
        Processo subprocess do port-forward
    """
    cmd = [
        "kubectl",
        "port-forward",
        f"-n{namespace}",
        f"svc/{service}",
        f"{local_port}:{remote_port}",
    ]
    env = os.environ.copy()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        preexec_fn=os.setsid,
    )
    return proc


def _stop_port_forward(proc: subprocess.Popen) -> None:
    """
    Para processo de port-forward.

    Args:
        proc: Processo a ser terminado
    """
    with contextlib.suppress(Exception):
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)


class PortForwardManager:
    """
    Gerenciador de port-forwards para testes de circuit breaker.

    Permite iniciar e parar port-forwards dinamicamente
    para simular falhas de servicos.
    """

    def __init__(self, service_name: str):
        """
        Inicializa o gerenciador.

        Args:
            service_name: Nome do servico (chave em SERVICE_PORT_CONFIGS)
        """
        if service_name not in SERVICE_PORT_CONFIGS:
            raise ValueError(f"Unknown service: {service_name}")

        self.service_name = service_name
        self.config = SERVICE_PORT_CONFIGS[service_name]
        self.process: Optional[subprocess.Popen] = None
        self._is_running = False

    @property
    def namespace(self) -> str:
        return self.config[0]

    @property
    def service(self) -> str:
        return self.config[1]

    @property
    def local_port(self) -> int:
        return self.config[2]

    @property
    def remote_port(self) -> int:
        return self.config[3]

    def start(self, wait_seconds: float = 2.0) -> None:
        """
        Inicia port-forward.

        Args:
            wait_seconds: Tempo de espera apos iniciar
        """
        if self._is_running:
            logger.warning(f"Port-forward for {self.service_name} already running")
            return

        self.process = _start_port_forward(
            self.namespace,
            self.service,
            self.local_port,
            self.remote_port,
        )
        time.sleep(wait_seconds)
        self._is_running = True
        logger.info(f"Started port-forward for {self.service_name}")

    def stop(self) -> None:
        """Para port-forward."""
        if self.process and self._is_running:
            _stop_port_forward(self.process)
            self._is_running = False
            self.process = None
            logger.info(f"Stopped port-forward for {self.service_name}")

    def restart(self, wait_seconds: float = 2.0) -> None:
        """
        Reinicia port-forward.

        Args:
            wait_seconds: Tempo de espera apos reiniciar
        """
        self.stop()
        time.sleep(1)
        self.start(wait_seconds)

    @property
    def is_running(self) -> bool:
        return self._is_running


class CircuitBreakerValidator:
    """
    Helper para validar estado de circuit breakers via metricas Prometheus.
    """

    def __init__(self, prometheus_url: str = PROMETHEUS_URL):
        self.prometheus_url = prometheus_url

    async def get_state(self, circuit_name: str) -> Optional[str]:
        """
        Busca estado atual do circuit breaker.

        Args:
            circuit_name: Nome do circuit breaker

        Returns:
            "closed", "open", ou "half_open"
        """
        queries = [
            f'circuit_breaker_state{{circuit="{circuit_name}"}}',
            f'circuit_breaker_status{{name="{circuit_name}"}}',
        ]

        for query in queries:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        f"{self.prometheus_url}/api/v1/query",
                        params={"query": query},
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    results = data.get("data", {}).get("result", [])
                    if results:
                        value = results[0].get("value", [None, None])[1]
                        return self._state_from_value(value)
            except Exception as e:
                logger.debug(f"Query failed for {query}: {e}")
                continue

        return None

    async def get_failures(self, circuit_name: str) -> int:
        """
        Busca total de falhas do circuit breaker.

        Args:
            circuit_name: Nome do circuit breaker

        Returns:
            Numero de falhas
        """
        query = f'circuit_breaker_failures_total{{circuit="{circuit_name}"}}'
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query},
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("data", {}).get("result", [])
                if results:
                    return int(results[0].get("value", [None, 0])[1])
        except Exception as e:
            logger.debug(f"Could not get failures: {e}")

        return 0

    async def get_transitions(
        self,
        circuit_name: str,
        from_state: str,
        to_state: str,
    ) -> int:
        """
        Busca numero de transicoes entre estados.

        Args:
            circuit_name: Nome do circuit breaker
            from_state: Estado de origem
            to_state: Estado de destino

        Returns:
            Numero de transicoes
        """
        query = (
            f'circuit_breaker_transitions_total{{'
            f'circuit="{circuit_name}",from="{from_state}",to="{to_state}"'
            f'}}'
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.prometheus_url}/api/v1/query",
                    params={"query": query},
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("data", {}).get("result", [])
                if results:
                    return int(results[0].get("value", [None, 0])[1])
        except Exception as e:
            logger.debug(f"Could not get transitions: {e}")

        return 0

    async def wait_for_state(
        self,
        circuit_name: str,
        expected_state: str,
        timeout_seconds: int = 60,
        poll_interval: float = 2.0,
    ) -> bool:
        """
        Aguarda circuit breaker atingir estado esperado.

        Args:
            circuit_name: Nome do circuit breaker
            expected_state: Estado esperado ("closed", "open", "half_open")
            timeout_seconds: Timeout maximo
            poll_interval: Intervalo entre verificacoes

        Returns:
            True se estado foi atingido, False se timeout
        """
        import asyncio

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            state = await self.get_state(circuit_name)
            if state == expected_state:
                return True
            await asyncio.sleep(poll_interval)

        return False

    def _state_from_value(self, value: str) -> str:
        """Converte valor numerico para nome de estado."""
        state_map = {
            "0": "closed",
            "1": "open",
            "2": "half_open",
            "closed": "closed",
            "open": "open",
            "half_open": "half_open",
        }
        return state_map.get(str(value).lower(), "unknown")


# ============================================
# Fixtures
# ============================================


@pytest.fixture
def mongodb_port_forward() -> Generator[PortForwardManager, None, None]:
    """
    Port-forward para MongoDB.

    Pode ser parado para simular falha do MongoDB.

    Yields:
        PortForwardManager para controle do port-forward
    """
    manager = PortForwardManager("mongodb")
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
def opa_port_forward() -> Generator[PortForwardManager, None, None]:
    """
    Port-forward para OPA.

    Pode ser parado para simular falha do OPA.

    Yields:
        PortForwardManager para controle do port-forward
    """
    manager = PortForwardManager("opa")
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
def service_registry_port_forward() -> Generator[PortForwardManager, None, None]:
    """
    Port-forward para Service Registry.

    Pode ser parado para simular falha do Service Registry.

    Yields:
        PortForwardManager para controle do port-forward
    """
    manager = PortForwardManager("service_registry")
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
def etcd_port_forward() -> Generator[PortForwardManager, None, None]:
    """
    Port-forward para etcd.

    Pode ser parado para simular falha do etcd.

    Yields:
        PortForwardManager para controle do port-forward
    """
    manager = PortForwardManager("etcd")
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
def postgresql_tickets_port_forward() -> Generator[PortForwardManager, None, None]:
    """
    Port-forward para PostgreSQL tickets.

    Pode ser parado para simular falha do PostgreSQL.

    Yields:
        PortForwardManager para controle do port-forward
    """
    manager = PortForwardManager("postgresql_tickets")
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
def redis_port_forward() -> Generator[PortForwardManager, None, None]:
    """
    Port-forward para Redis.

    Pode ser parado para simular falha do Redis.

    Yields:
        PortForwardManager para controle do port-forward
    """
    manager = PortForwardManager("redis")
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
async def circuit_breaker_validator() -> CircuitBreakerValidator:
    """
    Fixture que fornece CircuitBreakerValidator.

    Returns:
        Instancia de CircuitBreakerValidator
    """
    return CircuitBreakerValidator()
