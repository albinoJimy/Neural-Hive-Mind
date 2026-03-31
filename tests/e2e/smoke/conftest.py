"""
Fixtures para Smoke Tests E2E.

Smoke tests validam rapidamente (<10min) que os serviços core estão operacionais.
Foco: health checks, readiness probes, conectividade básica.
"""

import asyncio
import os
from typing import AsyncGenerator, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


# Service URLs from environment or defaults
SERVICE_URLS = {
    "gateway": os.getenv(
        "GATEWAY_URL",
        "http://gateway-intencoes.neural-hive-gateway.svc.cluster.local:8000",
    ),
    "ste": os.getenv(
        "STE_URL",
        "http://semantic-translation-engine.neural-hive-semantic.svc.cluster.local:8001",
    ),
    "consensus": os.getenv(
        "CONSENSUS_URL",
        "http://consensus-engine.neural-hive-consensus.svc.cluster.local:8002",
    ),
    "orchestrator": os.getenv(
        "ORCHESTRATOR_URL",
        "http://orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local:8003",
    ),
    "approval": os.getenv(
        "APPROVAL_URL",
        "http://approval-service.neural-hive-approval.svc.cluster.local:8004",
    ),
    "worker": os.getenv(
        "WORKER_URL",
        "http://worker-agents.neural-hive-execution.svc.cluster.local:8005",
    ),
    "queen": os.getenv(
        "QUEEN_URL", "http://queen-agent.neural-hive-agents.svc.cluster.local:8006"
    ),
}


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    HTTP client assíncrono para requisições.

    Usa timeout curto (5s) para smoke tests falharem rápido se serviços
    não responderem.
    """
    timeout = httpx.Timeout(5.0, connect=2.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        yield client


@pytest.fixture
def services_base_url() -> Dict[str, str]:
    """
    URLs base dos serviços para smoke tests.

    Retorna dict com service_name -> base_url.
    """
    return SERVICE_URLS


@pytest.fixture
def mock_services() -> Dict[str, MagicMock]:
    """
    Mocks dos serviços para testes de fallback.

    Usado quando serviço real não está disponível mas teste precisa
    validar lógica de fallback/graceful degradation.
    """
    return {
        "gateway": MagicMock(),
        "ste": MagicMock(),
        "consensus": MagicMock(),
        "orchestrator": MagicMock(),
        "approval": MagicMock(),
        "worker": MagicMock(),
        "queen": MagicMock(),
    }


class ServiceHealthHelper:
    """
    Helper para verificar saúde de serviços.

    Métodos:
        check_health: Verifica endpoint /health
        check_ready: Verifica endpoint /ready
        check_all: Verifica ambos os endpoints
    """

    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def check_health(self) -> Dict[str, any]:
        """
        Verifica endpoint /health do serviço.

        Returns:
            Dict com:
                - available (bool): serviço respondeu
                - status_code (int|None): HTTP status ou None se timeout
                - response (dict|None): corpo da resposta JSON ou None
                - error (str|None): mensagem de erro se houver
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return {
                "available": True,
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
                "error": None,
            }
        except httpx.TimeoutException:
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "timeout",
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "connection_refused",
            }
        except Exception as e:
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": str(e),
            }

    async def check_ready(self) -> Dict[str, any]:
        """
        Verifica endpoint /ready do serviço.

        Returns:
            Dict com mesma estrutura de check_health.
        """
        try:
            response = await self.client.get(f"{self.base_url}/ready")
            return {
                "available": True,
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
                "error": None,
            }
        except httpx.TimeoutException:
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "timeout",
            }
        except httpx.ConnectError:
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": "connection_refused",
            }
        except Exception as e:
            return {
                "available": False,
                "status_code": None,
                "response": None,
                "error": str(e),
            }

    async def check_all(self) -> Dict[str, any]:
        """
        Verifica ambos endpoints (/health e /ready).

        Returns:
            Dict com health e ready results.
        """
        health_result, ready_result = await asyncio.gather(
            self.check_health(),
            self.check_ready(),
            return_exceptions=True,
        )

        # Handle exceptions from gather
        if isinstance(health_result, Exception):
            health_result = {"available": False, "error": str(health_result)}
        if isinstance(ready_result, Exception):
            ready_result = {"available": False, "error": str(ready_result)}

        return {
            "health": health_result,
            "ready": ready_result,
        }


@pytest.fixture
def service_health_helper(http_client: httpx.AsyncClient) -> type[ServiceHealthHelper]:
    """
    Factory para criar ServiceHealthHelper.

    Usage:
        helper = service_health_helper()
        result = await helper.check_health("http://service:8000")
    """

    def _create_helper(base_url: str) -> ServiceHealthHelper:
        return ServiceHealthHelper(http_client, base_url)

    return _create_helper


@pytest.fixture
async def gateway_health_helper(
    http_client: httpx.AsyncClient,
    services_base_url: Dict[str, str],
) -> ServiceHealthHelper:
    """ServiceHealthHelper para Gateway de Intenções."""
    return ServiceHealthHelper(http_client, services_base_url["gateway"])


@pytest.fixture
async def ste_health_helper(
    http_client: httpx.AsyncClient,
    services_base_url: Dict[str, str],
) -> ServiceHealthHelper:
    """ServiceHealthHelper para Semantic Translation Engine."""
    return ServiceHealthHelper(http_client, services_base_url["ste"])


@pytest.fixture
async def consensus_health_helper(
    http_client: httpx.AsyncClient,
    services_base_url: Dict[str, str],
) -> ServiceHealthHelper:
    """ServiceHealthHelper para Consensus Engine."""
    return ServiceHealthHelper(http_client, services_base_url["consensus"])


@pytest.fixture
async def orchestrator_health_helper(
    http_client: httpx.AsyncClient,
    services_base_url: Dict[str, str],
) -> ServiceHealthHelper:
    """ServiceHealthHelper para Orchestrator Dynamic."""
    return ServiceHealthHelper(http_client, services_base_url["orchestrator"])


@pytest.fixture
async def approval_health_helper(
    http_client: httpx.AsyncClient,
    services_base_url: Dict[str, str],
) -> ServiceHealthHelper:
    """ServiceHealthHelper para Approval Service."""
    return ServiceHealthHelper(http_client, services_base_url["approval"])


@pytest.fixture
async def worker_health_helper(
    http_client: httpx.AsyncClient,
    services_base_url: Dict[str, str],
) -> ServiceHealthHelper:
    """ServiceHealthHelper para Worker Agents."""
    return ServiceHealthHelper(http_client, services_base_url["worker"])


@pytest.fixture
async def queen_health_helper(
    http_client: httpx.AsyncClient,
    services_base_url: Dict[str, str],
) -> ServiceHealthHelper:
    """ServiceHealthHelper para Queen Agent."""
    return ServiceHealthHelper(http_client, services_base_url["queen"])


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with smoke marker."""
    config.addinivalue_line(
        "markers", "smoke: Quick smoke tests (<10min) for core service validation"
    )
