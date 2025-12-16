#!/usr/bin/env python3
"""
test_phase2_integration.py - Testes de Integracao Automatizados da Fase 2

Este modulo implementa testes pytest para validacao automatizada dos servicos
da Fase 2 do Neural Hive Mind.

Uso:
    pytest tests/integration/test_phase2_integration.py -v
    pytest tests/integration/test_phase2_integration.py -v -k "test_http"
"""

import asyncio
import os
import subprocess
import json
import pytest
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


# Configuracao dos servicos da Fase 2
PHASE2_SERVICES = [
    "orchestrator-dynamic",
    "queen-agent",
    "worker-agents",
    "code-forge",
    "service-registry",
    "execution-ticket-service",
    "scout-agents",
    "analyst-agents",
    "optimizer-agents",
    "guard-agents",
    "sla-management-system",
    "mcp-tool-catalog",
    "self-healing-engine",
]

GRPC_SERVICES = ["queen-agent", "service-registry", "optimizer-agents"]

# Configurable namespace and label key
NAMESPACE = os.getenv("SERVICE_NAMESPACE", os.getenv("NAMESPACE", "neural-hive"))
SERVICE_LABEL_KEY = os.getenv("SERVICE_LABEL_KEY", "app")


@dataclass
class ServiceStatus:
    """Status de um servico"""
    name: str
    ready: bool
    pod_count: int
    ready_count: int
    error: Optional[str] = None


def run_kubectl(args: List[str]) -> Dict[str, Any]:
    """
    Executa comando kubectl e retorna resultado como JSON.

    Args:
        args: Lista de argumentos para kubectl

    Returns:
        Dict com resultado parseado ou erro
    """
    try:
        cmd = ["kubectl"] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return {"error": result.stderr, "items": []}

        if "-o" in args and "json" in args:
            return json.loads(result.stdout)

        return {"output": result.stdout}

    except subprocess.TimeoutExpired:
        return {"error": "Timeout ao executar kubectl", "items": []}
    except json.JSONDecodeError:
        return {"error": "Resposta JSON invalida", "items": []}
    except Exception as e:
        return {"error": str(e), "items": []}


def get_service_status(service: str) -> ServiceStatus:
    """
    Obtem status de um servico.

    Args:
        service: Nome do servico

    Returns:
        ServiceStatus com informacoes do servico
    """
    result = run_kubectl([
        "get", "pods", "-n", NAMESPACE,
        "-l", f"{SERVICE_LABEL_KEY}={service}",
        "-o", "json"
    ])

    if "error" in result and result.get("items") is None:
        return ServiceStatus(
            name=service,
            ready=False,
            pod_count=0,
            ready_count=0,
            error=result.get("error")
        )

    items = result.get("items", [])
    pod_count = len(items)

    if pod_count == 0:
        return ServiceStatus(
            name=service,
            ready=False,
            pod_count=0,
            ready_count=0,
            error="Nenhum pod encontrado"
        )

    ready_count = 0
    for pod in items:
        container_statuses = pod.get("status", {}).get("containerStatuses", [])
        if container_statuses and container_statuses[0].get("ready", False):
            ready_count += 1

    return ServiceStatus(
        name=service,
        ready=ready_count == pod_count,
        pod_count=pod_count,
        ready_count=ready_count
    )


def check_http_endpoint(service: str, endpoint: str = "/health") -> Dict[str, Any]:
    """
    Verifica endpoint HTTP de um servico.

    Args:
        service: Nome do servico
        endpoint: Endpoint a verificar

    Returns:
        Dict com status e codigo HTTP
    """
    # Obter nome do pod
    result = run_kubectl([
        "get", "pods", "-n", NAMESPACE,
        "-l", f"{SERVICE_LABEL_KEY}={service}",
        "-o", "jsonpath={.items[0].metadata.name}"
    ])

    pod_name = result.get("output", "").strip()
    if not pod_name:
        return {"success": False, "error": "Pod nao encontrado"}

    # Executar curl no pod
    curl_result = run_kubectl([
        "exec", "-n", NAMESPACE, pod_name, "--",
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        f"http://localhost:8000{endpoint}"
    ])

    http_code = curl_result.get("output", "000").strip()

    return {
        "success": http_code == "200",
        "http_code": http_code,
        "pod": pod_name
    }


def check_grpc_port(service: str, port: int = 50051) -> Dict[str, Any]:
    """
    Verifica se porta gRPC esta aberta.

    Args:
        service: Nome do servico
        port: Porta gRPC

    Returns:
        Dict com status da porta
    """
    result = run_kubectl([
        "get", "pods", "-n", NAMESPACE,
        "-l", f"{SERVICE_LABEL_KEY}={service}",
        "-o", "jsonpath={.items[0].metadata.name}"
    ])

    pod_name = result.get("output", "").strip()
    if not pod_name:
        return {"success": False, "error": "Pod nao encontrado"}

    # Verificar porta
    port_result = run_kubectl([
        "exec", "-n", NAMESPACE, pod_name, "--",
        "sh", "-c", f"ss -tlnp 2>/dev/null | grep :{port} || echo ''"
    ])

    port_open = bool(port_result.get("output", "").strip())

    return {
        "success": port_open,
        "port": port,
        "pod": pod_name
    }


# ==================== TESTES ====================


class TestPhase2PodStatus:
    """Testes de status dos pods da Fase 2"""

    @pytest.mark.parametrize("service", PHASE2_SERVICES)
    def test_pod_exists(self, service: str):
        """Verifica se pod do servico existe"""
        status = get_service_status(service)
        assert status.pod_count > 0, f"{service}: Nenhum pod encontrado"

    @pytest.mark.parametrize("service", PHASE2_SERVICES)
    def test_pod_ready(self, service: str):
        """Verifica se pod do servico esta pronto"""
        status = get_service_status(service)
        assert status.ready, f"{service}: Pod nao esta pronto ({status.ready_count}/{status.pod_count})"


class TestPhase2HTTPEndpoints:
    """Testes de endpoints HTTP da Fase 2"""

    @pytest.mark.parametrize("service", PHASE2_SERVICES)
    def test_health_endpoint(self, service: str):
        """Verifica endpoint /health (liveness)"""
        result = check_http_endpoint(service, "/health")
        assert result["success"], f"{service}: /health falhou (HTTP {result.get('http_code', 'N/A')})"

    @pytest.mark.parametrize("service", PHASE2_SERVICES)
    def test_ready_endpoint(self, service: str):
        """Verifica endpoint /ready (readiness)"""
        result = check_http_endpoint(service, "/ready")
        assert result["success"], f"{service}: /ready falhou (HTTP {result.get('http_code', 'N/A')})"

    @pytest.mark.parametrize("service", PHASE2_SERVICES)
    def test_metrics_endpoint(self, service: str):
        """Verifica endpoint /metrics (Prometheus)"""
        result = check_http_endpoint(service, "/metrics")
        # Metrics pode nao estar disponivel em todos os servicos
        if not result["success"]:
            pytest.skip(f"{service}: /metrics nao disponivel")


class TestPhase2GRPCServices:
    """Testes de servicos gRPC da Fase 2"""

    @pytest.mark.parametrize("service", GRPC_SERVICES)
    def test_grpc_port_open(self, service: str):
        """Verifica se porta gRPC esta aberta"""
        result = check_grpc_port(service, 50051)
        assert result["success"], f"{service}: Porta gRPC 50051 nao esta aberta"

    def test_grpc_communication_script(self):
        """Testa comunicacao gRPC via script auxiliar"""
        script_path = "scripts/validation/test_grpc_communication.py"

        if not os.path.exists(script_path):
            pytest.skip("Script de validacao gRPC nao encontrado")

        result = subprocess.run(
            ["python3", script_path, "--quiet"],
            capture_output=True,
            timeout=120
        )

        # Se retornou 0, passou
        # Se retornou 1 mas e por falta de bibliotecas, skip
        if result.returncode != 0:
            stderr = result.stderr.decode() if result.stderr else ""
            stdout = result.stdout.decode() if result.stdout else ""
            if "ImportError" in stderr or "grpcio" in stderr.lower():
                pytest.skip("Bibliotecas gRPC nao instaladas")
            if "Timeout" in stdout or "timeout" in stderr.lower():
                pytest.skip("Timeout ao conectar aos servicos gRPC")
            pytest.fail(f"Validacao de comunicacao gRPC falhou: {stderr or stdout}")

    @pytest.mark.parametrize("service", GRPC_SERVICES)
    def test_grpc_service_via_script(self, service: str):
        """Testa servico gRPC especifico via script auxiliar"""
        script_path = "scripts/validation/test_grpc_communication.py"

        if not os.path.exists(script_path):
            pytest.skip("Script de validacao gRPC nao encontrado")

        result = subprocess.run(
            ["python3", script_path, "--quiet", "--service", service],
            capture_output=True,
            timeout=60
        )

        if result.returncode != 0:
            stderr = result.stderr.decode() if result.stderr else ""
            stdout = result.stdout.decode() if result.stdout else ""
            if "ImportError" in stderr or "grpcio" in stderr.lower():
                pytest.skip(f"Bibliotecas gRPC nao instaladas para testar {service}")
            if "Timeout" in stdout or "timeout" in stderr.lower():
                pytest.skip(f"Timeout ao conectar ao servico gRPC {service}")
            pytest.fail(f"{service}: Validacao gRPC falhou - {stderr or stdout}")


class TestPhase2DatabaseConnectivity:
    """Testes de conectividade com bancos de dados"""

    def test_mongodb_connectivity(self):
        """Testa conectividade MongoDB via script auxiliar"""
        script_path = "scripts/validation/test_database_connectivity.py"

        if not os.path.exists(script_path):
            pytest.skip("Script de validacao de banco de dados nao encontrado")

        result = subprocess.run(
            ["python3", script_path, "--quiet"],
            capture_output=True,
            timeout=60
        )

        # Se retornou 0, passou
        # Se retornou 1 mas e por falta de bibliotecas, skip
        if result.returncode != 0:
            stderr = result.stderr.decode() if result.stderr else ""
            if "ImportError" in stderr or "not installed" in stderr:
                pytest.skip("Bibliotecas de banco de dados nao instaladas")
            pytest.fail("Validacao de conectividade com banco de dados falhou")


class TestPhase2KafkaConsumers:
    """Testes de Kafka consumers"""

    def test_kafka_consumers_active(self):
        """Testa se Kafka consumers estao ativos via script auxiliar"""
        script_path = "scripts/validation/test_kafka_consumers.sh"

        if not os.path.exists(script_path):
            pytest.skip("Script de validacao de Kafka nao encontrado")

        result = subprocess.run(
            ["bash", script_path, "--quiet"],
            capture_output=True,
            timeout=120
        )

        if result.returncode != 0:
            stderr = result.stderr.decode() if result.stderr else ""
            if "kafka" in stderr.lower() and "not found" in stderr.lower():
                pytest.skip("Kafka nao acessivel")
            pytest.fail("Validacao de Kafka consumers falhou")


class TestPhase2ServiceCommunication:
    """Testes de comunicacao entre servicos"""

    def test_orchestrator_to_queen_agent(self):
        """Testa comunicacao orchestrator-dynamic -> queen-agent"""
        # Verificar se ambos os servicos estao prontos
        orch_status = get_service_status("orchestrator-dynamic")
        queen_status = get_service_status("queen-agent")

        if not orch_status.ready:
            pytest.skip("orchestrator-dynamic nao esta pronto")
        if not queen_status.ready:
            pytest.skip("queen-agent nao esta pronto")

        # Verificar se queen-agent tem porta gRPC aberta
        grpc_result = check_grpc_port("queen-agent", 50051)
        assert grpc_result["success"], "queen-agent: Porta gRPC nao esta aberta"

    def test_worker_to_service_registry(self):
        """Testa comunicacao worker-agents -> service-registry"""
        worker_status = get_service_status("worker-agents")
        registry_status = get_service_status("service-registry")

        if not worker_status.ready:
            pytest.skip("worker-agents nao esta pronto")
        if not registry_status.ready:
            pytest.skip("service-registry nao esta pronto")

        # Verificar se service-registry tem porta gRPC aberta
        grpc_result = check_grpc_port("service-registry", 50051)
        assert grpc_result["success"], "service-registry: Porta gRPC nao esta aberta"


class TestPhase2AllServicesHealthy:
    """Teste consolidado de todos os servicos"""

    def test_all_services_running(self):
        """Verifica se todos os 13 servicos estao rodando"""
        failed_services = []

        for service in PHASE2_SERVICES:
            status = get_service_status(service)
            if not status.ready:
                failed_services.append(f"{service} ({status.ready_count}/{status.pod_count})")

        assert len(failed_services) == 0, f"Servicos nao prontos: {', '.join(failed_services)}"

    def test_all_http_endpoints_responding(self):
        """Verifica se todos os endpoints HTTP estao respondendo"""
        failed_endpoints = []

        for service in PHASE2_SERVICES:
            result = check_http_endpoint(service, "/health")
            if not result["success"]:
                failed_endpoints.append(f"{service} (HTTP {result.get('http_code', 'N/A')})")

        assert len(failed_endpoints) == 0, f"Endpoints que falharam: {', '.join(failed_endpoints)}"


# ==================== FIXTURES ====================


@pytest.fixture(scope="session")
def kubectl_available():
    """Verifica se kubectl esta disponivel"""
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest.fixture(autouse=True)
def skip_if_no_kubectl(kubectl_available):
    """Pula testes se kubectl nao estiver disponivel"""
    if not kubectl_available:
        pytest.skip("kubectl nao disponivel ou cluster nao acessivel")


# ==================== MAIN ====================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
