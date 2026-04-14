"""
Testes E2E para verificar health endpoints em todos os serviços.

Valida que os endpoints /health, /ready e /health/startup respondem
correctamente conforme implementação HA-001-PROBES.

Services:
- consensus-engine
- semantic-translation-engine
- worker-agents
- scout-agents
- optimizer-agents
- queen-agent
- guard-agents
- self-healing-engine
- analyst-agents
- execution-ticket-service
"""

import os
from typing import Any

import httpx
import pytest


# =============================================================================
# Service Configuration
# =============================================================================

# URLs base dos serviços - usa formato Kubernetes DNS interno
# Pode ser sobrescrito via environment variables
SERVICES_CONFIG = {
    "consensus-engine": {
        "url": os.getenv(
            "CONSENSUS_ENGINE_URL",
            "http://consensus-engine.neural-hive-consensus.svc.cluster.local:8002",
        ),
        "has_startup": True,
    },
    "semantic-translation-engine": {
        "url": os.getenv(
            "STE_URL",
            "http://semantic-translation-engine.neural-hive-semantic.svc.cluster.local:8001",
        ),
        "has_startup": True,
    },
    "worker-agents": {
        "url": os.getenv(
            "WORKER_AGENTS_URL",
            "http://worker-agents.neural-hive-execution.svc.cluster.local:8005",
        ),
        "has_startup": True,
    },
    "scout-agents": {
        "url": os.getenv(
            "SCOUT_AGENTS_URL",
            "http://scout-agents.neural-hive-scout.svc.cluster.local:8005",
        ),
        "has_startup": True,
    },
    "optimizer-agents": {
        "url": os.getenv(
            "OPTIMIZER_AGENTS_URL",
            "http://optimizer-agents.neural-hive-optimizer.svc.cluster.local:8005",
        ),
        "has_startup": True,
    },
    "queen-agent": {
        "url": os.getenv(
            "QUEEN_AGENT_URL",
            "http://queen-agent.neural-hive-agents.svc.cluster.local:8006",
        ),
        "has_startup": True,
    },
    "guard-agents": {
        "url": os.getenv(
            "GUARD_AGENTS_URL",
            "http://guard-agents.neural-hive-guard.svc.cluster.local:8005",
        ),
        "has_startup": True,
    },
    "self-healing-engine": {
        "url": os.getenv(
            "SELF_HEALING_ENGINE_URL",
            "http://self-healing-engine.neural-hive-healing.svc.cluster.local:8005",
        ),
        "has_startup": True,
    },
    "analyst-agents": {
        "url": os.getenv(
            "ANALYST_AGENTS_URL",
            "http://analyst-agents.neural-hive-analyst.svc.cluster.local:8005",
        ),
        "has_startup": False,  # Ainda sem /health/startup
    },
    "execution-ticket-service": {
        "url": os.getenv(
            "EXECUTION_TICKET_SERVICE_URL",
            "http://execution-ticket-service.neural-hive-execution.svc.cluster.local:8008",
        ),
        "has_startup": False,  # Ainda sem /health/startup
    },
}

SERVICE_NAMES = list(SERVICES_CONFIG.keys())


# =============================================================================
# Test Helpers
# =============================================================================


class ServiceHealthClient:
    """
    Cliente para verificar health endpoints de serviços.

    Suporta verificações de /health, /ready e /health/startup.
    """

    def __init__(self, service_name: str, base_url: str, timeout: float = 5.0):
        self.service_name = service_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def check_health(self) -> dict[str, Any]:
        """
        Verifica endpoint /health do serviço.

        Returns:
            Dict com:
                - success (bool): se a requisição foi bem sucedida
                - status_code (int): HTTP status code
                - data (dict|None): corpo da resposta JSON
                - error (str|None): mensagem de erro se houver
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/health")

                data = None
                if response.content:
                    try:
                        data = response.json()
                    except Exception:
                        data = response.text

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": data,
                    "error": None,
                }
        except httpx.TimeoutException:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": "timeout",
            }
        except httpx.ConnectError as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"connection_error: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": str(e),
            }

    async def check_ready(self) -> dict[str, Any]:
        """
        Verifica endpoint /ready do serviço.

        Returns:
            Dict com mesma estrutura de check_health.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/ready")

                data = None
                if response.content:
                    try:
                        data = response.json()
                    except Exception:
                        data = response.text

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": data,
                    "error": None,
                }
        except httpx.TimeoutException:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": "timeout",
            }
        except httpx.ConnectError as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"connection_error: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": str(e),
            }

    async def check_startup(self) -> dict[str, Any]:
        """
        Verifica endpoint /health/startup do serviço.

        Returns:
            Dict com mesma estrutura de check_health.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/health/startup")

                data = None
                if response.content:
                    try:
                        data = response.json()
                    except Exception:
                        data = response.text

                return {
                    "success": True,
                    "status_code": response.status_code,
                    "data": data,
                    "error": None,
                }
        except httpx.TimeoutException:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": "timeout",
            }
        except httpx.ConnectError as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": f"connection_error: {e}",
            }
        except Exception as e:
            return {
                "success": False,
                "status_code": None,
                "data": None,
                "error": str(e),
            }


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def service_clients():
    """
    Retorna dict de ServiceHealthClient para todos os serviços.

    Usado para iterar sobre todos os serviços nos testes parametrizados.
    """
    return {
        service_name: ServiceHealthClient(
            service_name, config["url"], timeout=float(os.getenv("HEALTH_CHECK_TIMEOUT", "5.0"))
        )
        for service_name, config in SERVICES_CONFIG.items()
    }


@pytest.fixture
def service_client(service_clients, service):
    """
    Retorna ServiceHealthClient para um serviço específico.

    Usado em testes parametrizados.
    """
    return service_clients[service]


# =============================================================================
# /health Endpoint Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("service", SERVICE_NAMES)
class TestHealthEndpoint:
    """Testes para o endpoint /health em todos os serviços."""

    async def test_health_endpoint_exists(self, service_client: ServiceHealthClient):
        """
        TEST: [HEALTH-001] Endpoint /health existe e responde

        Dado: Serviço está rodando
        Quando: GET /health é chamado
        Então: Response com status 200 e campo 'status' presente
        """
        result = await service_client.check_health()

        assert result["success"] is True, f"Serviço {service_client.service_name} não respondeu: {result['error']}"
        assert result["status_code"] == 200, f"Status code esperado 200, recebido {result['status_code']}"
        assert result["data"] is not None, "Response body está vazio"

        data = result["data"]
        assert "status" in data or "service" in data, "Response deve conter 'status' ou 'service'"

    async def test_health_response_contains_service_name(self, service_client: ServiceHealthClient):
        """
        TEST: [HEALTH-002] Response de /health contém nome do serviço

        Dado: Serviço está rodando
        Quando: GET /health é chamado
        Então: Response contém campo 'service' com nome do serviço
        """
        result = await service_client.check_health()

        if not result["success"]:
            pytest.skip(f"Serviço {service_client.service_name} não disponível")

        data = result["data"]
        if "service" in data:
            assert isinstance(data["service"], str), "Campo 'service' deve ser string"
            assert len(data["service"]) > 0, "Campo 'service' não pode ser vazio"

    async def test_health_status_is_healthy(self, service_client: ServiceHealthClient):
        """
        TEST: [HEALTH-003] Status em /health indica saúde

        Dado: Serviço está rodando
        Quando: GET /health é chamado
        Então: Campo 'status' é 'healthy' ou similar
        """
        result = await service_client.check_health()

        if not result["success"]:
            pytest.skip(f"Serviço {service_client.service_name} não disponível")

        data = result["data"]
        if "status" in data:
            valid_statuses = ["healthy", "alive", "ok", "started"]
            assert data["status"].lower() in valid_statuses, f"Status inválido: {data['status']}"


# =============================================================================
# /ready Endpoint Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("service", SERVICE_NAMES)
class TestReadyEndpoint:
    """Testes para o endpoint /ready em todos os serviços."""

    async def test_ready_endpoint_exists(self, service_client: ServiceHealthClient):
        """
        TEST: [READY-001] Endpoint /ready existe e responde

        Dado: Serviço está rodando
        Quando: GET /ready é chamado
        Então: Response com status 200 ou 503
        """
        result = await service_client.check_ready()

        assert result["success"] is True, f"Serviço {service_client.service_name} não respondeu: {result['error']}"
        assert result["status_code"] in [200, 503], f"Status code esperado 200 ou 503, recebido {result['status_code']}"

    async def test_ready_response_contains_status(self, service_client: ServiceHealthClient):
        """
        TEST: [READY-002] Response de /ready contém status de prontidão

        Dado: Serviço está rodando
        Quando: GET /ready é chamado
        Então: Response contém 'ready', 'status' ou 'checks'
        """
        result = await service_client.check_ready()

        if not result["success"]:
            pytest.skip(f"Serviço {service_client.service_name} não disponível")

        data = result["data"]
        assert data is not None, "Response body está vazio"

        # Diferentes serviços podem ter formatos diferentes
        has_ready_field = "ready" in data or "status" in data or "checks" in data
        assert has_ready_field, "Response deve conter 'ready', 'status' ou 'checks'"

    async def test_ready_checks_dependencies(self, service_client: ServiceHealthClient):
        """
        TEST: [READY-003] /ready verifica dependências quando críticas

        Dado: Serviço está rodando
        Quando: GET /ready é chamado
        Então: Response contém checks de dependências ou status
        """
        result = await service_client.check_ready()

        if not result["success"]:
            pytest.skip(f"Serviço {service_client.service_name} não disponível")

        data = result["data"]
        # Alguns serviços podem não ter checks se todas deps estão OK
        # Apenas validar que a estrutura é válida
        if result["status_code"] == 503:
            # Se não está ready, deve ter explicações
            assert "checks" in data or "ready" in data or "status" in data


# =============================================================================
# /health/startup Endpoint Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("service", [s for s in SERVICE_NAMES if SERVICES_CONFIG[s]["has_startup"]])
class TestStartupEndpoint:
    """Testes para o endpoint /health/startup em serviços que o implementam."""

    async def test_startup_endpoint_exists(self, service_client: ServiceHealthClient):
        """
        TEST: [STARTUP-001] Endpoint /health/startup existe e responde

        Dado: Serviço está rodando
        Quando: GET /health/startup é chamado
        Então: Response com status 200
        """
        result = await service_client.check_startup()

        assert result["success"] is True, f"Serviço {service_client.service_name} não respondeu: {result['error']}"
        assert result["status_code"] == 200, f"Status code esperado 200, recebido {result['status_code']}"

    async def test_startup_response_contains_status(self, service_client: ServiceHealthClient):
        """
        TEST: [STARTUP-002] Response de /health/startup contém status

        Dado: Serviço está rodando
        Quando: GET /health/startup é chamado
        Então: Response contém 'status' com valor 'started' ou 'starting'
        """
        result = await service_client.check_startup()

        if not result["success"]:
            pytest.skip(f"Serviço {service_client.service_name} não disponível")

        data = result["data"]
        assert data is not None, "Response body está vazio"
        assert "status" in data, "Response deve conter campo 'status'"

        valid_statuses = ["started", "starting"]
        assert data["status"] in valid_statuses, f"Status inválido: {data['status']}"

    async def test_startup_response_contains_timestamp(self, service_client: ServiceHealthClient):
        """
        TEST: [STARTUP-003] Response de /health/startup contém timestamp

        Dado: Serviço está rodando
        Quando: GET /health/startup é chamado
        Então: Response contém 'started_at' ou timestamp
        """
        result = await service_client.check_startup()

        if not result["success"]:
            pytest.skip(f"Serviço {service_client.service_name} não disponível")

        data = result["data"]
        # started_at é opcional para serviços em estado 'starting'
        if data.get("status") == "started":
            assert "started_at" in data, "Response com status 'started' deve conter 'started_at'"


# =============================================================================
# Comprehensive Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_services_health_accessible(service_clients):
    """
    TEST: [ALL-001] Todos os serviços têm /health acessível

    Dado: Cluster está rodando
    Quando: /health é verificado em todos os serviços
    Então: Todos respondem com sucesso
    """
    failed_services = []

    for service_name, client in service_clients.items():
        result = await client.check_health()
        if not result["success"] or result["status_code"] != 200:
            failed_services.append({
                "service": service_name,
                "error": result.get("error"),
                "status_code": result.get("status_code"),
            })

    assert len(failed_services) == 0, f"Serviços com health falhando: {failed_services}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_services_ready_responds(service_clients):
    """
    TEST: [ALL-002] Todos os serviços têm /ready respondendo

    Dado: Cluster está rodando
    Quando: /ready é verificado em todos os serviços
    Então: Todos respondem (200 ou 503 são válidos)
    """
    failed_services = []

    for service_name, client in service_clients.items():
        result = await client.check_ready()
        if not result["success"] or result["status_code"] not in [200, 503]:
            failed_services.append({
                "service": service_name,
                "error": result.get("error"),
                "status_code": result.get("status_code"),
            })

    assert len(failed_services) == 0, f"Serviços com ready falhando: {failed_services}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_services_with_startup_implement_it(service_clients):
    """
    TEST: [ALL-003] Serviços com /health/startup implementado

    Dado: Cluster está rodando
    Quando: /health/startup é verificado em serviços configurados
    Então: Todos respondem com sucesso
    """
    failed_services = []

    for service_name, config in SERVICES_CONFIG.items():
        if config["has_startup"]:
            client = service_clients[service_name]
            result = await client.check_startup()
            if not result["success"] or result["status_code"] != 200:
                failed_services.append({
                    "service": service_name,
                    "error": result.get("error"),
                    "status_code": result.get("status_code"),
                })

    assert len(failed_services) == 0, f"Serviços com startup falhando: {failed_services}"


# =============================================================================
# Marker Registration
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Registra marcadores customizados."""
    config.addinivalue_line(
        "markers", "integration: Testes de integração que requerem serviços rodando"
    )
    config.addinivalue_line(
        "markers", "e2e: Testes E2E que validam fluxos completos entre serviços"
    )
    config.addinivalue_line(
        "markers", "health: Testes de health checks em todos os serviços"
    )
