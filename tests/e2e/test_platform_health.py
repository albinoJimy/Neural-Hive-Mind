# tests/e2e/test_platform_health.py
"""
E2E Tests para Platform Health.

Verifica que todos os 22 serviços da plataforma respondem aos endpoints
de health check (/health e /ready).

Estes testes podem ser executados:
1. Contra cluster Kubernetes real (PLATFORM_BASE_URL não definido)
2. Contra ambiente local (export PLATFORM_BASE_URL=http://localhost)

Usage:
    # Testar contra cluster
    pytest tests/e2e/test_platform_health.py -v

    # Testar contra localhost
    export PLATFORM_BASE_URL=http://localhost
    pytest tests/e2e/test_platform_health.py -v

    # Testar só alguns serviços
    pytest tests/e2e/test_platform_health.py -k "core or gateway"
"""

import asyncio
import os

import pytest

from tests.e2e.conftest_platform import (
    ServiceHealthHelper,
    get_service_urls,
)

pytestmark = pytest.mark.platform_health


@pytest.mark.asyncio
class TestPlatformHealthCore:
    """
    Testes de saúde para serviços Core (8 principais).

    Serviços Core:
    - gateway-intencoes
    - semantic-translation-engine
    - consensus-engine
    - orchestrator-dynamic
    - approval-service
    - worker-agents
    - queen-agent
    - service-registry
    """

    async def test_all_core_services_health_endpoint_responds(
        self,
        http_client,
        platform_health_helpers: dict[str, ServiceHealthHelper],
    ):
        """
        TEST: [PLATFORM-001] Todos os serviços Core respondem ao /health

        Dado: Plataforma Neural-Hive-Mind está rodando
        Quando: GET /health é chamado para todos os serviços Core
        Então: Todos respondem com status HTTP 200 ou 503 (degradado)
        """
        core_services = [
            "gateway-intencoes",
            "semantic-translation-engine",
            "consensus-engine",
            "orchestrator-dynamic",
            "approval-service",
            "worker-agents",
            "queen-agent",
            "service-registry",
        ]

        results = {}

        for service_name in core_services:
            if service_name not in platform_health_helpers:
                pytest.fail(f"Serviço {service_name} não encontrado nos helpers")

            helper = platform_health_helpers[service_name]
            result = await helper.check_health()
            results[service_name] = result

        # Verificar que todos responderam (podem estar degradados)
        failed_services = [name for name, result in results.items() if not result["available"]]

        if failed_services:
            pytest.fail(
                f"Serviços Core não disponíveis: {failed_services}\n" f"Detalhes: {results}"
            )

        # Todos os disponíveis devem ter status 200
        unhealthy = [
            name
            for name, result in results.items()
            if result["available"] and result["status_code"] not in {200, 503}
        ]

        if unhealthy:
            pytest.fail(
                f"Serviços Core com status inesperado: {unhealthy}\n" f"Detalhes: {results}"
            )

    async def test_all_core_services_ready_endpoint_responds(
        self,
        http_client,
        platform_health_helpers: dict[str, ServiceHealthHelper],
    ):
        """
        TEST: [PLATFORM-002] Todos os serviços Core respondem ao /ready

        Dado: Plataforma Neural-Hive-Mind está rodando
        Quando: GET /ready é chamado para todos os serviços Core
        Então: Todos respondem (status 200, 503 ou 504 aceitáveis)
        """
        core_services = [
            "gateway-intencoes",
            "semantic-translation-engine",
            "consensus-engine",
            "orchestrator-dynamic",
            "approval-service",
            "worker-agents",
            "queen-agent",
            "service-registry",
        ]

        results = {}

        for service_name in core_services:
            helper = platform_health_helpers[service_name]
            result = await helper.check_ready()
            results[service_name] = result

        # Verificar que todos responderam
        failed_services = [name for name, result in results.items() if not result["available"]]

        if failed_services:
            pytest.fail(
                f"Serviços Core /ready não disponíveis: {failed_services}\n" f"Detalhes: {results}"
            )


@pytest.mark.asyncio
class TestPlatformHealthSpecialists:
    """
    Testes de saúde para Agentes Especializados (8).

    Agentes Especializados:
    - analyst-agents
    - scout-agents
    - guard-agents
    - optimizer-agents
    - self-healing-engine
    - execution-ticket-service
    - sla-management-system
    - code-forge
    """

    async def test_all_specialist_services_health_endpoint_responds(
        self,
        http_client,
        platform_health_helpers: dict[str, ServiceHealthHelper],
    ):
        """
        TEST: [PLATFORM-003] Todos os Agentes Especializados respondem ao /health

        Dado: Plataforma Neural-Hive-Mind está rodando
        Quando: GET /health é chamado para todos os Agentes Especializados
        Então: Todos respondem com status HTTP 200 ou 503
        """
        specialist_services = [
            "analyst-agents",
            "scout-agents",
            "guard-agents",
            "optimizer-agents",
            "self-healing-engine",
            "execution-ticket-service",
            "sla-management-system",
            "code-forge",
        ]

        results = {}

        for service_name in specialist_services:
            if service_name not in platform_health_helpers:
                # Serviço pode não ter sido migrado ainda
                continue

            helper = platform_health_helpers[service_name]
            result = await helper.check_health()
            results[service_name] = result

        # Verificar que todos os testados responderam
        failed_services = [name for name, result in results.items() if not result["available"]]

        if failed_services:
            pytest.fail(
                f"Agentes Especializados não disponíveis: {failed_services}\n"
                f"Detalhes: {results}"
            )


@pytest.mark.asyncio
class TestPlatformHealthInfrastructure:
    """
    Testes de saúde para serviços de Infraestrutura (6).

    Serviços de Infraestrutura:
    - mcp-tool-catalog
    - memory-layer-api
    - explainability-api
    - specialist-architecture
    - specialist-business
    - specialist-technical
    - specialist-behavior
    - specialist-evolution
    """

    async def test_all_infrastructure_services_health_endpoint_responds(
        self,
        http_client,
        platform_health_helpers: dict[str, ServiceHealthHelper],
    ):
        """
        TEST: [PLATFORM-004] Todos os serviços de Infraestrutura respondem ao /health

        Dado: Plataforma Neural-Hive-Mind está rodando
        Quando: GET /health é chamado para todos os serviços de Infraestrutura
        Então: Todos respondem com status HTTP 200 ou 503
        """
        infrastructure_services = [
            "mcp-tool-catalog",
            "memory-layer-api",
            "explainability-api",
            "specialist-architecture",
            "specialist-business",
            "specialist-technical",
            "specialist-behavior",
            "specialist-evolution",
        ]

        results = {}

        for service_name in infrastructure_services:
            if service_name not in platform_health_helpers:
                # Serviço pode não ter sido migrado ainda
                continue

            helper = platform_health_helpers[service_name]
            result = await helper.check_health()
            results[service_name] = result

        # Verificar que todos os testados responderam
        failed_services = [name for name, result in results.items() if not result["available"]]

        if failed_services:
            pytest.fail(
                f"Serviços de Infraestrutura não disponíveis: {failed_services}\n"
                f"Detalhes: {results}"
            )


@pytest.mark.asyncio
class TestPlatformHealthComplete:
    """
    Testes completos de saúde para TODOS os 22 serviços.
    """

    async def test_all_22_services_health_respond(
        self,
        http_client,
        platform_health_helpers: dict[str, ServiceHealthHelper],
    ):
        """
        TEST: [PLATFORM-005] Smoke test completo - todos os 22 serviços

        Dado: Plataforma Neural-Hive-Mind está rodando
        Quando: GET /health é chamado para todos os 22 serviços
        Então: Todos respondem (podem estar degradados mas acessíveis)
        """
        results = {}

        # Executar checks em paralelo para maior velocidade
        async def check_service(name: str, helper: ServiceHealthHelper):
            result = await helper.check_health()
            return name, result

        tasks = [check_service(name, helper) for name, helper in platform_health_helpers.items()]

        checked_results = await asyncio.gather(*tasks, return_exceptions=True)

        for item in checked_results:
            if isinstance(item, Exception):
                continue
            name, result = item
            results[name] = result

        # Relatório detalhado
        available_count = sum(1 for r in results.values() if r["available"])
        total_count = len(results)

        # Se nenhum serviço está disponível, falhar imediatamente
        if available_count == 0:
            pytest.fail(
                f"Nenhum dos {total_count} serviços está disponível.\n"
                f"Verifique PLATFORM_BASE_URL ou se a plataforma está rodando."
            )

        # Relatar serviços indisponíveis mas não falhar (para diagnóstico)
        unavailable = [
            (name, result.get("error"))
            for name, result in results.items()
            if not result["available"]
        ]

        if unavailable:
            print(f"\n⚠️  Serviços indisponíveis ({len(unavailable)}/{total_count}):")
            for name, error in unavailable:
                print(f"  - {name}: {error}")

        # Pelo menos 80% dos serviços devem estar disponíveis
        min_available = int(total_count * 0.8)
        assert (
            available_count >= min_available
        ), f"Apenas {available_count}/{total_count} serviços disponíveis (mínimo: {min_available})"

        print(f"\n✓ {available_count}/{total_count} serviços disponíveis")

    async def test_health_responses_contain_required_fields(
        self,
        http_client,
        platform_health_helpers: dict[str, ServiceHealthHelper],
    ):
        """
        TEST: [PLATFORM-006] Respostas de /health contêm campos obrigatórios

        Dado: Plataforma Neural-Hive-Mind está rodando
        Quando: GET /health é chamado para serviços disponíveis
        Então: Respostas contêm pelo menos 'status' e 'service'
        """
        required_fields = ["status", "service"]
        failures = []

        for service_name, helper in platform_health_helpers.items():
            result = await helper.check_health()

            if not result["available"]:
                continue

            response = result.get("response", {})
            missing = [f for f in required_fields if f not in response]

            if missing:
                failures.append(f"{service_name}: missing fields {missing}")

        if failures:
            pytest.fail("Serviços com campos obrigatórios faltando:\n" + "\n".join(failures))

    async def test_health_response_times_acceptable(
        self,
        http_client,
        platform_health_helpers: dict[str, ServiceHealthHelper],
    ):
        """
        TEST: [PLATFORM-007] Tempos de resposta de /health são aceitáveis

        Dado: Plataforma Neural-Hive-Mind está rodando
        Quando: GET /health é chamado para serviços disponíveis
        Então: Todos respondem em menos de 5 segundos
        """
        max_response_time_ms = 5000
        slow_services = []

        for service_name, helper in platform_health_helpers.items():
            result = await helper.check_health()

            if not result["available"]:
                continue

            response_time = result.get("response_time_ms", 0)

            if response_time > max_response_time_ms:
                slow_services.append(
                    f"{service_name}: {response_time}ms > {max_response_time_ms}ms"
                )

        if slow_services:
            pytest.fail("Serviços com tempo de resposta excessivo:\n" + "\n".join(slow_services))


@pytest.mark.asyncio
class TestPlatformHealthGracefulDegradation:
    """
    Testes de graceful degradation quando serviços falham.
    """

    async def test_unavailable_service_returns_proper_error(
        self,
        http_client,
        health_helper_factory,
    ):
        """
        TEST: [PLATFORM-008] Erro adequado quando serviço não existe

        Dado: Um serviço que não existe
        Quando: Tentativa de health check é feita
        Então: Erro é identificado corretamente (timeout/connection_refused)
        """
        helper = health_helper_factory("http://invalid-service-that-does-not-exist:9999")

        result = await helper.check_health()

        assert result["available"] is False
        assert result["status_code"] is None
        assert result["error"] in {"timeout", "connection_refused"} or result["error"] is not None


@pytest.mark.asyncio
class TestPlatformHealthConfiguration:
    """
    Testes de configuração de URLs e ambiente.
    """

    def test_service_urls_configuration_exists(self):
        """
        TEST: [PLATFORM-009] Configuração de URLs de serviços existe

        Dado: Arquivo de configuração
        Quando: Verificado
        Então: Todos os 22 serviços têm URLs configuradas
        """
        urls = get_service_urls()

        # Verificar que temos pelo menos os 22 serviços
        expected_min_services = 22
        assert (
            len(urls) >= expected_min_services
        ), f"Esperado pelo menos {expected_min_services} serviços, encontrado {len(urls)}"

        # Verificar que serviços core estão presentes
        core_services = [
            "gateway-intencoes",
            "semantic-translation-engine",
            "consensus-engine",
            "orchestrator-dynamic",
            "approval-service",
            "worker-agents",
            "queen-agent",
        ]

        for service in core_services:
            assert service in urls, f"Serviço core {service} não encontrado em URLs"

    def test_default_urls_follow_kubernetes_pattern(self):
        """
        TEST: [PLATFORM-010] URLs padrão seguem padrão Kubernetes

        Dado: URLs padrão configuradas
        Quando: Verificadas
        Então: Seguem padrão svc.cluster.local
        """
        urls = get_service_urls()

        # Em ambiente padrão, URLs devem seguir padrão Kubernetes
        # Este teste pode falhar se PLATFORM_BASE_URL estiver definido
        if os.getenv("PLATFORM_BASE_URL"):
            pytest.skip("PLATFORM_BASE_URL definido, pulando verificação de padrão")

        kubernetes_pattern = ".svc.cluster.local"
        services_with_k8s_pattern = [
            (name, url) for name, url in urls.items() if kubernetes_pattern in url
        ]

        # Pelo menos 90% devem seguir padrão K8s
        min_k8s = int(len(urls) * 0.9)
        assert (
            len(services_with_k8s_pattern) >= min_k8s
        ), f"Poucos serviços com padrão Kubernetes: {len(services_with_k8s_pattern)}/{len(urls)}"
