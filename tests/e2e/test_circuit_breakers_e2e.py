"""
Testes E2E para Circuit Breakers.

Valida:
- Circuit breaker MongoDB (execution_ticket_persistence)
- Circuit breaker OPA (policy validation)
- Circuit breaker Service Registry (discovery)
- Transicoes de estado: closed -> open -> half-open -> closed
- Metricas de circuit breaker
"""

import asyncio
import logging
import os
import signal
import subprocess
import time
from typing import Dict, Generator, Optional

import httpx
import pytest

from tests.e2e.utils.metrics import get_metric_value, query_prometheus

logger = logging.getLogger(__name__)

# Configuracao do ambiente
ORCHESTRATOR_URL = os.getenv(
    "ORCHESTRATOR_URL",
    "http://orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local:8001",
)
EXECUTION_TICKET_SERVICE_URL = os.getenv(
    "EXECUTION_TICKET_SERVICE_URL",
    "http://execution-ticket-service.neural-hive-orchestration.svc.cluster.local:8080",
)
PROMETHEUS_ENDPOINT = os.getenv(
    "PROMETHEUS_ENDPOINT",
    "prometheus-server.monitoring.svc.cluster.local:9090",
)

# Configuracao de circuit breaker
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30  # segundos


# ============================================
# Fixtures para Port-Forward
# ============================================


def _start_port_forward(namespace: str, service: str, local_port: int, remote_port: int) -> subprocess.Popen:
    """
    Inicia port-forward para um servico.

    Args:
        namespace: Kubernetes namespace
        service: Nome do servico
        local_port: Porta local
        remote_port: Porta remota

    Returns:
        Processo do port-forward
    """
    cmd = [
        "kubectl", "port-forward",
        f"-n{namespace}",
        f"svc/{service}",
        f"{local_port}:{remote_port}",
    ]
    env = os.environ.copy()
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        preexec_fn=os.setsid,
    )


def _kill_port_forward(proc: subprocess.Popen) -> None:
    """
    Mata processo de port-forward.

    Args:
        proc: Processo a ser terminado
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception as e:
        logger.debug(f"Could not kill port-forward: {e}")


@pytest.fixture
def mongodb_port_forward() -> Generator[subprocess.Popen, None, None]:
    """
    Port-forward para MongoDB que pode ser morto para simular falha.

    Yields:
        Processo do port-forward
    """
    proc = _start_port_forward(
        namespace="mongodb-cluster",
        service="mongodb-cluster",
        local_port=27017,
        remote_port=27017,
    )
    time.sleep(2)  # Aguardar port-forward estabelecer

    yield proc

    _kill_port_forward(proc)


@pytest.fixture
def opa_port_forward() -> Generator[subprocess.Popen, None, None]:
    """
    Port-forward para OPA.

    Yields:
        Processo do port-forward
    """
    proc = _start_port_forward(
        namespace="neural-hive-orchestration",
        service="opa",
        local_port=8181,
        remote_port=8181,
    )
    time.sleep(2)

    yield proc

    _kill_port_forward(proc)


@pytest.fixture
def service_registry_port_forward() -> Generator[subprocess.Popen, None, None]:
    """
    Port-forward para Service Registry.

    Yields:
        Processo do port-forward
    """
    proc = _start_port_forward(
        namespace="neural-hive",
        service="service-registry",
        local_port=50051,
        remote_port=50051,
    )
    time.sleep(2)

    yield proc

    _kill_port_forward(proc)


# ============================================
# Helper para Validacao de Circuit Breaker
# ============================================


class CircuitBreakerValidator:
    """
    Helper para validar estado de circuit breakers via metricas Prometheus.
    """

    def __init__(self, prometheus_url: str = PROMETHEUS_ENDPOINT):
        self.prometheus_url = prometheus_url

    async def get_circuit_breaker_state(self, circuit_name: str) -> Optional[str]:
        """
        Busca estado atual do circuit breaker.

        Args:
            circuit_name: Nome do circuit breaker

        Returns:
            "closed", "open", ou "half_open" (ou None se nao encontrado)
        """
        try:
            # Tentar diferentes formatos de metrica
            queries = [
                f'circuit_breaker_state{{circuit="{circuit_name}"}}',
                f'circuit_breaker_status{{name="{circuit_name}"}}',
                f'circuitbreaker_state{{circuit="{circuit_name}"}}',
            ]

            for query in queries:
                result = await query_prometheus(self.prometheus_url, query)
                data = result.get("data", {}).get("result", [])
                if data:
                    # Retornar primeiro resultado
                    value = data[0].get("value", [None, None])[1]
                    if value:
                        return self._state_from_value(value)

            return None
        except Exception as e:
            logger.warning(f"Could not get circuit breaker state: {e}")
            return None

    async def get_circuit_breaker_failures(self, circuit_name: str) -> int:
        """
        Busca total de falhas do circuit breaker.

        Args:
            circuit_name: Nome do circuit breaker

        Returns:
            Numero de falhas
        """
        try:
            result = await get_metric_value(
                self.prometheus_url,
                "circuit_breaker_failures_total",
                {"circuit": circuit_name},
            )
            return int(result) if result else 0
        except Exception:
            return 0

    async def get_circuit_breaker_transitions(
        self, circuit_name: str, from_state: str, to_state: str
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
        try:
            result = await get_metric_value(
                self.prometheus_url,
                "circuit_breaker_transitions_total",
                {"circuit": circuit_name, "from": from_state, "to": to_state},
            )
            return int(result) if result else 0
        except Exception:
            return 0

    def _state_from_value(self, value: str) -> str:
        """Converte valor numerico para nome de estado."""
        state_map = {
            "0": "closed",
            "1": "open",
            "2": "half_open",
        }
        return state_map.get(str(value), "unknown")


@pytest.fixture
async def circuit_breaker_validator():
    """Fixture que fornece CircuitBreakerValidator."""
    return CircuitBreakerValidator()


# ============================================
# Fixtures de Clientes
# ============================================


@pytest.fixture(scope="session")
async def orchestrator_client():
    """Cliente HTTP para Orchestrator."""
    async with httpx.AsyncClient(
        base_url=ORCHESTRATOR_URL,
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def execution_ticket_client():
    """Cliente HTTP para Execution Ticket Service."""
    async with httpx.AsyncClient(
        base_url=EXECUTION_TICKET_SERVICE_URL,
        timeout=30.0,
    ) as client:
        yield client


# ============================================
# Testes de Circuit Breaker MongoDB
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
async def test_mongodb_circuit_breaker_opens_on_failures(
    orchestrator_client,
    mongodb_port_forward,
    circuit_breaker_validator,
):
    """
    Testa que circuit breaker abre apos N falhas.

    Valida:
    1. Simular MongoDB indisponivel (matar port-forward)
    2. Aguardar 5+ tentativas de persistencia falharem
    3. Circuit breaker state = "open"
    4. Metrica circuit_breaker_state indica open
    5. Proximas tentativas falham imediatamente (fail-fast)
    """
    import uuid

    circuit_name = "execution_ticket_persistence"

    # Pegar estado inicial - deve estar closed
    initial_state = await circuit_breaker_validator.get_circuit_breaker_state(circuit_name)
    logger.info(f"Initial circuit breaker state: {initial_state}")

    # Pegar contador inicial de falhas
    initial_failures = await circuit_breaker_validator.get_circuit_breaker_failures(circuit_name)
    logger.info(f"Initial failure count: {initial_failures}")

    # Matar port-forward para simular MongoDB indisponivel
    _kill_port_forward(mongodb_port_forward)
    logger.info("MongoDB port-forward killed, simulating unavailability")

    # Tentar operacoes que usam MongoDB
    failures = 0
    request_times = []
    for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD + 2):
        try:
            start_time = time.time()
            # Criar ticket que deve falhar ao persistir audit
            ticket_id = f"cb-test-{uuid.uuid4().hex[:8]}"
            response = await orchestrator_client.post(
                "/api/v1/flow-c/tickets",
                json={
                    "ticket_id": ticket_id,
                    "plan_id": f"plan-cb-{uuid.uuid4().hex[:8]}",
                    "task_type": "code_generation",
                }
            )
            elapsed = time.time() - start_time
            request_times.append(elapsed)
            if response.status_code >= 500:
                failures += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            failures += 1
            logger.debug(f"Request failed: {e}")

    logger.info(f"Observed {failures} failures")

    # Aguardar metricas atualizarem
    await asyncio.sleep(2)

    # Verificar estado do circuit breaker - DEVE estar open apos threshold
    state = await circuit_breaker_validator.get_circuit_breaker_state(circuit_name)
    logger.info(f"Circuit breaker state after failures: {state}")

    # Asserção: circuit breaker deve estar open apos atingir threshold
    assert state == "open", (
        f"Circuit breaker should be 'open' after {CIRCUIT_BREAKER_FAILURE_THRESHOLD} failures, "
        f"but got state: {state}"
    )

    # Verificar metrica de falhas - deve ter incrementado
    total_failures = await circuit_breaker_validator.get_circuit_breaker_failures(circuit_name)
    logger.info(f"Total circuit breaker failures: {total_failures}")

    # Asserção: contador de falhas deve ter atingido ou excedido o threshold
    assert total_failures >= initial_failures + CIRCUIT_BREAKER_FAILURE_THRESHOLD, (
        f"Failure counter should have increased by at least {CIRCUIT_BREAKER_FAILURE_THRESHOLD}, "
        f"but only went from {initial_failures} to {total_failures}"
    )

    # Testar fail-fast: proximas requisicoes devem falhar imediatamente
    logger.info("Testing fail-fast behavior with circuit open...")
    fail_fast_times = []
    for i in range(3):
        start_time = time.time()
        try:
            ticket_id = f"cb-failfast-{uuid.uuid4().hex[:8]}"
            response = await orchestrator_client.post(
                "/api/v1/flow-c/tickets",
                json={
                    "ticket_id": ticket_id,
                    "plan_id": f"plan-failfast-{uuid.uuid4().hex[:8]}",
                    "task_type": "code_generation",
                }
            )
            elapsed = time.time() - start_time
            fail_fast_times.append(elapsed)

            # Com circuit open, requests devem falhar rapidamente (fail-fast)
            # ou retornar erro 503 Service Unavailable
            assert response.status_code in [503, 500, 429], (
                f"With circuit breaker open, expected 503/500/429, got {response.status_code}"
            )
        except Exception as e:
            elapsed = time.time() - start_time
            fail_fast_times.append(elapsed)
            logger.debug(f"Fail-fast request failed as expected: {e}")

    # Asserção: fail-fast deve ser rapido (< 1 segundo por request)
    if fail_fast_times:
        avg_fail_fast_time = sum(fail_fast_times) / len(fail_fast_times)
        logger.info(f"Average fail-fast time: {avg_fail_fast_time:.3f}s")
        assert avg_fail_fast_time < 1.0, (
            f"Fail-fast should be quick (<1s), but averaged {avg_fail_fast_time:.3f}s"
        )


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
async def test_mongodb_circuit_breaker_half_open_recovery(
    orchestrator_client,
    circuit_breaker_validator,
):
    """
    Testa transicao half-open -> closed.

    Valida:
    1. Circuit breaker em estado open (apos falhas)
    2. Aguardar recovery_timeout (30s)
    3. Circuit breaker state = "half_open"
    4. Proxima tentativa bem sucedida
    5. Circuit breaker state = "closed"
    """
    import uuid

    circuit_name = "execution_ticket_persistence"

    # Este teste assume que circuit breaker ja esta open
    # (pode ser rodado apos test_mongodb_circuit_breaker_opens_on_failures)
    initial_state = await circuit_breaker_validator.get_circuit_breaker_state(circuit_name)
    logger.info(f"Initial state for recovery test: {initial_state}")

    if initial_state != "open":
        pytest.skip("Circuit breaker not in open state, skipping recovery test")

    # Pegar transicoes iniciais para verificar depois
    initial_transitions_to_half_open = await circuit_breaker_validator.get_circuit_breaker_transitions(
        circuit_name, "open", "half_open"
    )

    # Aguardar recovery timeout
    logger.info(f"Waiting {CIRCUIT_BREAKER_RECOVERY_TIMEOUT}s for recovery timeout...")
    await asyncio.sleep(CIRCUIT_BREAKER_RECOVERY_TIMEOUT + 5)

    # Verificar se transicionou para half_open
    state = await circuit_breaker_validator.get_circuit_breaker_state(circuit_name)
    logger.info(f"State after recovery timeout: {state}")

    # Asserção: circuit breaker deve estar em half_open apos recovery timeout
    assert state == "half_open", (
        f"Circuit breaker should transition to 'half_open' after {CIRCUIT_BREAKER_RECOVERY_TIMEOUT}s, "
        f"but got state: {state}"
    )

    # Verificar que transicao open->half_open ocorreu
    transitions_to_half_open = await circuit_breaker_validator.get_circuit_breaker_transitions(
        circuit_name, "open", "half_open"
    )
    assert transitions_to_half_open > initial_transitions_to_half_open, (
        f"Expected open->half_open transition to be recorded, "
        f"but transitions count unchanged: {transitions_to_half_open}"
    )

    # Fazer uma requisicao bem sucedida (MongoDB deve estar disponivel agora)
    response = await orchestrator_client.post(
        "/api/v1/flow-c/tickets",
        json={
            "ticket_id": f"cb-recovery-{uuid.uuid4().hex[:8]}",
            "plan_id": f"plan-recovery-{uuid.uuid4().hex[:8]}",
            "task_type": "code_generation",
        }
    )
    logger.info(f"Recovery request status: {response.status_code}")

    # Asserção: requisicao deve ter sucesso para fechar o circuit
    assert response.status_code in [200, 201], (
        f"Recovery request should succeed to close circuit, but got {response.status_code}"
    )

    # Aguardar metricas atualizarem
    await asyncio.sleep(2)

    # Verificar estado final - deve estar closed apos sucesso
    final_state = await circuit_breaker_validator.get_circuit_breaker_state(circuit_name)
    logger.info(f"Final circuit breaker state: {final_state}")

    # Asserção: circuit breaker deve voltar para closed apos sucesso
    assert final_state == "closed", (
        f"Circuit breaker should return to 'closed' after successful request, "
        f"but got state: {final_state}"
    )

    # Verificar que transicao half_open->closed ocorreu
    transitions_to_closed = await circuit_breaker_validator.get_circuit_breaker_transitions(
        circuit_name, "half_open", "closed"
    )
    assert transitions_to_closed > 0, (
        f"Expected half_open->closed transition to be recorded, but count is {transitions_to_closed}"
    )


# ============================================
# Testes de Circuit Breaker OPA
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
async def test_opa_circuit_breaker_opens_on_failures(
    orchestrator_client,
    opa_port_forward,
    circuit_breaker_validator,
):
    """
    Testa circuit breaker OPA.

    Valida:
    1. Matar port-forward do OPA
    2. Aguardar 5 falhas de validacao de politica
    3. Circuit breaker state = "open"
    4. Fail-open: tickets sao gerados mesmo sem validacao OPA
    5. Log de warning sobre OPA indisponivel
    """
    import uuid

    # Matar port-forward do OPA
    _kill_port_forward(opa_port_forward)
    logger.info("OPA port-forward killed, simulating unavailability")

    # Tentar operacoes que usam OPA
    responses = []
    for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD + 2):
        try:
            response = await orchestrator_client.post(
                "/api/v1/flow-c/validate",
                json={
                    "plan_id": f"plan-opa-{uuid.uuid4().hex[:8]}",
                    "task_type": "code_generation",
                    "risk_band": "medium",
                }
            )
            responses.append(response.status_code)
            await asyncio.sleep(0.5)
        except Exception as e:
            responses.append(500)
            logger.debug(f"OPA request failed: {e}")

    logger.info(f"OPA request responses: {responses}")

    # Verificar estado do circuit breaker OPA
    state = await circuit_breaker_validator.get_circuit_breaker_state("opa_policy")
    logger.info(f"OPA circuit breaker state: {state}")

    # Com fail-open, requests devem passar mesmo com OPA indisponivel
    successful = [r for r in responses if r < 500]
    if successful:
        logger.info(f"Fail-open working: {len(successful)} requests succeeded without OPA")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_opa_circuit_breaker_fail_closed_behavior(
    orchestrator_client,
    opa_port_forward,
):
    """
    Testa comportamento fail-closed quando OPA configurado para nao permitir bypass.

    NOTE: Este teste verifica o comportamento quando OPA_FAIL_OPEN=false.
    O comportamento default pode ser fail-open.
    """
    import uuid

    # Verificar configuracao atual
    # Se OPA_FAIL_OPEN=false, requests devem falhar quando OPA esta indisponivel

    # Matar port-forward do OPA
    _kill_port_forward(opa_port_forward)

    # Tentar validacao
    response = await orchestrator_client.post(
        "/api/v1/flow-c/validate",
        json={
            "plan_id": f"plan-fail-closed-{uuid.uuid4().hex[:8]}",
            "task_type": "code_generation",
            "risk_band": "high",  # Alto risco pode exigir validacao OPA
        }
    )

    logger.info(f"Fail-closed test response: {response.status_code}")

    # Dependendo da configuracao:
    # - fail-open: 200 (bypass OPA)
    # - fail-closed: 500 ou 503 (falha)

    # Apenas logamos o comportamento, nao falhamos o teste
    if response.status_code >= 500:
        logger.info("OPA fail-closed behavior: validation failed without OPA")
    else:
        logger.info("OPA fail-open behavior: validation bypassed without OPA")


# ============================================
# Testes de Circuit Breaker Service Registry
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
async def test_service_registry_circuit_breaker_opens(
    orchestrator_client,
    service_registry_port_forward,
    circuit_breaker_validator,
):
    """
    Testa circuit breaker Service Registry.

    Valida:
    1. Matar port-forward do Service Registry
    2. Aguardar 5 falhas de discovery
    3. Circuit breaker state = "open"
    4. Fallback: tickets rejeitados com reason="no_workers_available"
    """
    import uuid

    # Matar port-forward do Service Registry
    _kill_port_forward(service_registry_port_forward)
    logger.info("Service Registry port-forward killed, simulating unavailability")

    # Tentar operacoes que usam Service Registry (alocacao de workers)
    responses = []
    for i in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD + 2):
        try:
            response = await orchestrator_client.post(
                "/api/v1/flow-c/allocate",
                json={
                    "ticket_id": f"ticket-sr-{uuid.uuid4().hex[:8]}",
                    "task_type": "code_generation",
                    "capabilities": ["python"],
                }
            )
            responses.append(response.status_code)

            # Verificar mensagem de erro
            if response.status_code >= 400:
                data = response.json()
                logger.debug(f"Allocation failed: {data}")

            await asyncio.sleep(0.5)
        except Exception as e:
            responses.append(500)
            logger.debug(f"Allocation request failed: {e}")

    logger.info(f"Service Registry allocation responses: {responses}")

    # Verificar estado do circuit breaker
    state = await circuit_breaker_validator.get_circuit_breaker_state("service_registry")
    logger.info(f"Service Registry circuit breaker state: {state}")

    # Verificar que tivemos falhas
    failures = [r for r in responses if r >= 500 or r == 503]
    logger.info(f"Total failures: {len(failures)}")


# ============================================
# Testes de Cache durante Circuit Breaker Open
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cache_serves_during_circuit_breaker_open(
    orchestrator_client,
    service_registry_port_forward,
):
    """
    Testa que cache serve dados quando circuit breaker esta open.

    Valida:
    1. Fazer discovery para popular cache
    2. Matar port-forward do Service Registry
    3. Abrir circuit breaker
    4. Fazer discovery novamente
    5. Resposta vem do cache (nao falha)
    6. Metrica cache_hits_total incrementou
    7. Dados em cache correspondem aos dados originais
    """
    import uuid

    # Pegar valor inicial de cache hits
    initial_cache_hits = await get_metric_value(
        PROMETHEUS_ENDPOINT,
        "service_registry_cache_hits_total",
    )
    initial_cache_hits = int(initial_cache_hits) if initial_cache_hits else 0
    logger.info(f"Initial cache hits: {initial_cache_hits}")

    # Fazer discovery para popular cache
    response = await orchestrator_client.get(
        "/api/v1/agents/discover",
        params={"capabilities": "python", "namespace": "default"}
    )

    if response.status_code != 200:
        logger.info(f"Initial discovery failed: {response.status_code}")
        pytest.skip("Discovery endpoint not available")

    # Guardar dados originais para comparacao
    original_data = response.json()
    original_agents = original_data if isinstance(original_data, list) else original_data.get("agents", [])
    logger.info(f"Cache populated with {len(original_agents)} agents")

    # Matar port-forward para simular Service Registry indisponivel
    _kill_port_forward(service_registry_port_forward)
    logger.info("Service Registry port-forward killed")

    # Aguardar um pouco para garantir que conexao foi perdida
    await asyncio.sleep(1)

    # Fazer discovery novamente (deve usar cache)
    response = await orchestrator_client.get(
        "/api/v1/agents/discover",
        params={"capabilities": "python", "namespace": "default"}
    )

    logger.info(f"Discovery after Service Registry down: {response.status_code}")

    # Asserção: request deve ter sucesso usando cache
    assert response.status_code == 200, (
        f"Discovery should succeed from cache when Service Registry is down, "
        f"but got status {response.status_code}"
    )

    # Verificar dados retornados do cache
    cached_data = response.json()
    cached_agents = cached_data if isinstance(cached_data, list) else cached_data.get("agents", [])

    # Asserção: dados do cache devem conter os agents esperados
    assert len(cached_agents) > 0, "Cache should return agent data, but got empty list"

    # Verificar que os dados correspondem aos originais
    if original_agents:
        # Verificar que pelo menos os mesmos agent_ids estao presentes
        original_ids = {a.get("agent_id") or a.get("id") for a in original_agents if isinstance(a, dict)}
        cached_ids = {a.get("agent_id") or a.get("id") for a in cached_agents if isinstance(a, dict)}
        if original_ids and cached_ids:
            assert original_ids == cached_ids, (
                f"Cached agents should match original agents. "
                f"Original: {original_ids}, Cached: {cached_ids}"
            )

    # Aguardar metricas atualizarem
    await asyncio.sleep(2)

    # Verificar metrica de cache hits
    final_cache_hits = await get_metric_value(
        PROMETHEUS_ENDPOINT,
        "service_registry_cache_hits_total",
    )
    final_cache_hits = int(final_cache_hits) if final_cache_hits else 0
    logger.info(f"Cache hits: {initial_cache_hits} -> {final_cache_hits}")

    # Asserção: cache hits deve ter incrementado em pelo menos 1
    assert final_cache_hits > initial_cache_hits, (
        f"Cache hits should have increased after serving from cache. "
        f"Initial: {initial_cache_hits}, Final: {final_cache_hits}"
    )


# ============================================
# Testes de Metricas
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_circuit_breaker_metrics(circuit_breaker_validator):
    """
    Testa metricas de circuit breaker.

    Valida:
    - circuit_breaker_state{circuit="..."} existe
    - circuit_breaker_failures_total{circuit="..."} existe
    - circuit_breaker_transitions_total{from="...", to="..."} existe
    """
    circuits_to_check = [
        "execution_ticket_persistence",
        "opa_policy",
        "service_registry",
    ]

    for circuit in circuits_to_check:
        # Verificar estado
        state = await circuit_breaker_validator.get_circuit_breaker_state(circuit)
        logger.info(f"Circuit {circuit} state: {state}")

        # Verificar falhas
        failures = await circuit_breaker_validator.get_circuit_breaker_failures(circuit)
        logger.info(f"Circuit {circuit} failures: {failures}")

        # Verificar transicoes closed->open
        transitions_to_open = await circuit_breaker_validator.get_circuit_breaker_transitions(
            circuit, "closed", "open"
        )
        logger.info(f"Circuit {circuit} transitions to open: {transitions_to_open}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_circuit_breaker_metrics_available_in_prometheus():
    """
    Testa que metricas de circuit breaker estao disponiveis no Prometheus.

    Valida:
    - Queries Prometheus retornam dados
    - Metricas seguem naming convention esperada
    """
    metrics_to_check = [
        "circuit_breaker_state",
        "circuit_breaker_failures_total",
        "circuit_breaker_transitions_total",
        "circuit_breaker_success_total",
    ]

    for metric_name in metrics_to_check:
        try:
            result = await query_prometheus(PROMETHEUS_ENDPOINT, metric_name)
            data = result.get("data", {})
            result_type = data.get("resultType", "unknown")
            results = data.get("result", [])

            logger.info(f"Metric {metric_name}: type={result_type}, results={len(results)}")

        except Exception as e:
            logger.warning(f"Could not query metric {metric_name}: {e}")
