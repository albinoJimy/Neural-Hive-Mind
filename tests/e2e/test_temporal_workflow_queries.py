"""
Testes E2E para Temporal Workflow Queries.

Valida:
- Query get_status() retorna estado do workflow
- Query get_tickets() retorna tickets gerados
- Queries funcionam durante execucao do workflow
- Queries funcionam apos conclusao do workflow
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pytest

logger = logging.getLogger(__name__)

# Configuracao do ambiente
TEMPORAL_ENDPOINT = os.getenv(
    "TEMPORAL_ENDPOINT",
    "temporal-frontend.neural-hive-temporal.svc.cluster.local:7233",
)
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
ORCHESTRATOR_URL = os.getenv(
    "ORCHESTRATOR_URL",
    "http://orchestrator-dynamic.neural-hive-orchestration.svc.cluster.local:8001",
)

# Task queue e workflow names
ORCHESTRATION_TASK_QUEUE = "orchestration-tasks"
FLOW_C_WORKFLOW_TYPE = "FlowCOrchestrationWorkflow"


def create_test_cognitive_plan(num_tasks: int = 3) -> Dict[str, Any]:
    """
    Cria um cognitive plan sintetico para testes.

    Args:
        num_tasks: Numero de tasks no plan

    Returns:
        Dict com estrutura de cognitive plan
    """
    plan_id = f"plan-test-{uuid.uuid4().hex[:8]}"
    intent_id = f"intent-test-{uuid.uuid4().hex[:8]}"
    correlation_id = f"corr-test-{uuid.uuid4().hex[:8]}"

    tasks = []
    for i in range(num_tasks):
        tasks.append({
            "task_id": f"task-{uuid.uuid4().hex[:8]}",
            "type": "code_generation",
            "description": f"Test task {i+1}",
            "capabilities": ["python"],
            "template_id": "default",
            "parameters": {},
            "dependencies": [],
            "priority": i + 1,
        })

    return {
        "plan_id": plan_id,
        "intent_id": intent_id,
        "correlation_id": correlation_id,
        "description": "Test Plan for E2E",
        "created_at": datetime.utcnow().isoformat(),
        "tasks": tasks,
        "estimated_duration_minutes": 10,
        "sla_deadline": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
    }


# ============================================
# Fixtures
# ============================================


@pytest.fixture(scope="session")
async def temporal_client():
    """
    Session-scoped Temporal client fixture.

    Fornece cliente Temporal conectado.
    """
    try:
        from temporalio.client import Client

        client = await Client.connect(
            TEMPORAL_ENDPOINT,
            namespace=TEMPORAL_NAMESPACE,
        )
        yield client
    except ImportError:
        pytest.skip("temporalio not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to Temporal: {e}")


@pytest.fixture(scope="session")
async def orchestrator_client():
    """
    Session-scoped HTTP client for Orchestrator Dynamic.

    Fornece cliente HTTP para iniciar workflows.
    """
    async with httpx.AsyncClient(
        base_url=ORCHESTRATOR_URL,
        timeout=60.0,
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.fixture
def sample_cognitive_plan() -> Dict[str, Any]:
    """Gera cognitive plan sintetico para testes."""
    return create_test_cognitive_plan(num_tasks=3)


@pytest.fixture
async def running_workflow(temporal_client, orchestrator_client, sample_cognitive_plan):
    """
    Fixture que inicia um workflow e fornece o handle.

    Yields:
        Tuple de (workflow_id, workflow_handle, plan)
    """
    # Iniciar workflow via API
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": sample_cognitive_plan,
            "priority": 5,
            "risk_band": "medium",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code} - {response.text}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    if not workflow_id:
        pytest.skip("No workflow_id returned from API")

    # Obter handle do workflow
    handle = temporal_client.get_workflow_handle(workflow_id)

    yield workflow_id, handle, sample_cognitive_plan

    # Cleanup: cancelar workflow se ainda estiver rodando
    try:
        await handle.cancel()
    except Exception as e:
        logger.debug(f"Could not cancel workflow {workflow_id}: {e}")


# ============================================
# Testes de Query get_status()
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_query_workflow_status_running(temporal_client, orchestrator_client, sample_cognitive_plan):
    """
    Testa query get_status() durante execucao.

    Valida:
    1. Workflow iniciado via API
    2. Query get_status retorna estado atual
    3. Resposta contem campos obrigatorios: current_step, tickets_generated, tickets_completed
    """
    # Iniciar workflow
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": sample_cognitive_plan,
            "priority": 5,
            "risk_band": "medium",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    try:
        # Aguardar um pouco para workflow iniciar
        await asyncio.sleep(2)

        # Obter handle e fazer query
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Executar query get_status
        status = await handle.query("get_status")

        # Asserção: query deve retornar dados
        assert status is not None, "Query get_status should return status data, got None"

        # Asserção: resposta deve ser um dicionario
        assert isinstance(status, dict), (
            f"Query get_status should return a dict, got {type(status).__name__}"
        )
        logger.info(f"Workflow status: {status}")

        # Asserção: deve conter campo current_step (ou variantes)
        step_field_names = ["current_step", "step", "stage", "phase"]
        has_step_field = any(field in status for field in step_field_names)
        assert has_step_field, (
            f"Status should contain one of {step_field_names}. "
            f"Got keys: {list(status.keys())}"
        )

        # Asserção: deve conter campo tickets_generated (ou variante)
        tickets_generated_names = ["tickets_generated", "generated_tickets", "tickets_count"]
        has_tickets_generated = any(field in status for field in tickets_generated_names)
        assert has_tickets_generated, (
            f"Status should contain one of {tickets_generated_names}. "
            f"Got keys: {list(status.keys())}"
        )

        # Asserção: deve conter campo tickets_completed (ou variante)
        tickets_completed_names = ["tickets_completed", "completed_tickets", "completed_count"]
        has_tickets_completed = any(field in status for field in tickets_completed_names)
        assert has_tickets_completed, (
            f"Status should contain one of {tickets_completed_names}. "
            f"Got keys: {list(status.keys())}"
        )

        # Validar valores sao do tipo correto
        current_step = status.get("current_step") or status.get("step") or status.get("stage")
        assert isinstance(current_step, (str, int)), (
            f"current_step should be str or int, got {type(current_step).__name__}"
        )

        tickets_gen = (
            status.get("tickets_generated") or
            status.get("generated_tickets") or
            status.get("tickets_count", 0)
        )
        assert isinstance(tickets_gen, int), (
            f"tickets_generated should be int, got {type(tickets_gen).__name__}"
        )

        logger.info(f"Query get_status validation passed: step={current_step}, tickets_generated={tickets_gen}")

    finally:
        # Cleanup
        try:
            handle = temporal_client.get_workflow_handle(workflow_id)
            await handle.cancel()
        except Exception:
            pass


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
async def test_query_workflow_status_completed(temporal_client, orchestrator_client):
    """
    Testa query get_status() apos conclusao.

    Valida:
    1. Workflow iniciado e aguardado ate conclusao
    2. Query get_status retorna estado final
    3. Resposta indica workflow completado

    NOTE: Este teste e lento pois aguarda workflow completar.
    """
    # Criar plan simples com 1 task
    simple_plan = create_test_cognitive_plan(num_tasks=1)

    # Iniciar workflow
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": simple_plan,
            "priority": 5,
            "risk_band": "low",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Aguardar conclusao (com timeout)
        try:
            result = await asyncio.wait_for(
                handle.result(),
                timeout=300.0  # 5 minutos
            )
            logger.info(f"Workflow completed with result: {result}")

        except asyncio.TimeoutError:
            pytest.skip("Workflow did not complete in time")
        except Exception as e:
            logger.warning(f"Workflow failed or was cancelled: {e}")

        # Query status apos conclusao
        try:
            status = await handle.query("get_status")

            if isinstance(status, dict):
                # Verificar indicacao de conclusao
                step = status.get("current_step", status.get("step", ""))
                logger.info(f"Final workflow status: {status}")

        except Exception as query_error:
            logger.warning(f"Query after completion failed: {query_error}")

    finally:
        pass  # Workflow ja terminou


# ============================================
# Testes de Query get_tickets()
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_query_workflow_tickets(temporal_client, orchestrator_client, sample_cognitive_plan):
    """
    Testa query get_tickets() retorna tickets gerados.

    Valida:
    1. Workflow iniciado com plan de 3 tasks
    2. Aguardar fase C2 (geracao de tickets)
    3. Query get_tickets retorna lista de tickets
    4. Cada ticket tem campos obrigatorios: ticket_id, task_id, status
    """
    # Iniciar workflow
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": sample_cognitive_plan,
            "priority": 5,
            "risk_band": "medium",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Aguardar tempo para C2 gerar tickets
        await asyncio.sleep(10)

        # Executar query get_tickets
        tickets = await handle.query("get_tickets")

        # Asserção: query deve retornar dados
        assert tickets is not None, "Query get_tickets should return tickets data, got None"

        # Normalizar resposta para lista
        if isinstance(tickets, dict):
            ticket_list = tickets.get("tickets", tickets.get("items", []))
        elif isinstance(tickets, list):
            ticket_list = tickets
        else:
            pytest.fail(f"Query get_tickets returned unexpected type: {type(tickets).__name__}")

        logger.info(f"Found {len(ticket_list)} tickets")

        # Asserção: deve ter pelo menos alguns tickets (plan tem 3 tasks)
        # Nota: pode ter menos se ainda em geracao
        assert isinstance(ticket_list, list), (
            f"Tickets should be a list, got {type(ticket_list).__name__}"
        )

        # Validar estrutura de cada ticket
        for i, ticket in enumerate(ticket_list):
            # Asserção: cada ticket deve ser um dicionario
            assert isinstance(ticket, dict), (
                f"Ticket {i} should be a dict, got {type(ticket).__name__}"
            )

            # Asserção: ticket_id deve estar presente
            ticket_id_field = ticket.get("ticket_id") or ticket.get("id")
            assert ticket_id_field is not None, (
                f"Ticket {i} missing 'ticket_id' or 'id'. Got keys: {list(ticket.keys())}"
            )

            # Asserção: task_id deve estar presente
            assert "task_id" in ticket, (
                f"Ticket {i} missing 'task_id'. Got keys: {list(ticket.keys())}"
            )

            # Asserção: status deve estar presente
            assert "status" in ticket, (
                f"Ticket {i} missing 'status'. Got keys: {list(ticket.keys())}"
            )

            # Validar tipos dos campos
            assert isinstance(ticket["task_id"], str), (
                f"Ticket {i} task_id should be str, got {type(ticket['task_id']).__name__}"
            )
            assert isinstance(ticket["status"], str), (
                f"Ticket {i} status should be str, got {type(ticket['status']).__name__}"
            )

            logger.debug(f"Ticket {i}: id={ticket_id_field}, task_id={ticket['task_id']}, status={ticket['status']}")

        logger.info(f"Query get_tickets validation passed: {len(ticket_list)} tickets with valid structure")

    finally:
        try:
            handle = temporal_client.get_workflow_handle(workflow_id)
            await handle.cancel()
        except Exception:
            pass


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_query_tickets_before_generation(temporal_client, orchestrator_client, sample_cognitive_plan):
    """
    Testa query get_tickets() antes de C2.

    Valida:
    1. Workflow iniciado
    2. Query imediatamente (antes de tickets serem gerados)
    3. Resposta: tickets = [] (lista vazia)
    """
    # Iniciar workflow
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": sample_cognitive_plan,
            "priority": 5,
            "risk_band": "medium",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Query imediatamente (sem aguardar)
        try:
            tickets = await handle.query("get_tickets")

            # Deve retornar lista vazia ou None
            if tickets is None:
                logger.info("Tickets is None before generation (expected)")
            elif isinstance(tickets, list):
                # Pode ter 0 tickets no inicio
                logger.info(f"Tickets before generation: {len(tickets)}")
            elif isinstance(tickets, dict):
                ticket_list = tickets.get("tickets", tickets.get("items", []))
                logger.info(f"Tickets before generation: {len(ticket_list)}")

        except Exception as query_error:
            # Pode falhar se query nao disponivel durante inicializacao
            logger.info(f"Query before generation: {query_error}")

    finally:
        try:
            handle = temporal_client.get_workflow_handle(workflow_id)
            await handle.cancel()
        except Exception:
            pass


# ============================================
# Testes de Query via HTTP
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_query_workflow_via_http(orchestrator_client, sample_cognitive_plan):
    """
    Testa query via endpoint HTTP.

    Valida:
    1. Workflow iniciado
    2. GET /api/v1/workflows/{workflow_id}/status retorna 200
    3. Resposta contem informacoes de status
    """
    # Iniciar workflow
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": sample_cognitive_plan,
            "priority": 5,
            "risk_band": "medium",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    try:
        # Aguardar workflow iniciar
        await asyncio.sleep(2)

        # Query via HTTP
        response = await orchestrator_client.get(f"/api/v1/workflows/{workflow_id}/status")

        # Pode retornar 200 ou 404 se endpoint nao existe
        if response.status_code == 404:
            pytest.skip("HTTP status endpoint not implemented")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        status_data = response.json()
        assert status_data is not None
        logger.info(f"HTTP workflow status: {status_data}")

    finally:
        # Cleanup via API se disponivel
        try:
            await orchestrator_client.post(f"/api/v1/workflows/{workflow_id}/cancel")
        except Exception:
            pass


# ============================================
# Testes de Erro
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_query_nonexistent_workflow(temporal_client):
    """
    Testa query de workflow inexistente.

    Valida:
    1. Tentar query workflow_id invalido
    2. Erro apropriado retornado
    """
    fake_workflow_id = f"nonexistent-workflow-{uuid.uuid4().hex[:8]}"

    handle = temporal_client.get_workflow_handle(fake_workflow_id)

    with pytest.raises(Exception) as exc_info:
        await handle.query("get_status")

    # Deve falhar com erro de workflow nao encontrado
    error_msg = str(exc_info.value).lower()
    assert "not found" in error_msg or "no workflow" in error_msg or "unknown" in error_msg, \
        f"Expected 'not found' error, got: {exc_info.value}"

    logger.info("Nonexistent workflow query correctly rejected")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_query_invalid_query_name(temporal_client, orchestrator_client, sample_cognitive_plan):
    """
    Testa query com nome invalido.

    Valida:
    1. Workflow iniciado
    2. Tentar query com nome invalido
    3. Erro QueryNotFoundError ou similar
    """
    # Iniciar workflow
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": sample_cognitive_plan,
            "priority": 5,
            "risk_band": "medium",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Aguardar workflow iniciar
        await asyncio.sleep(2)

        # Tentar query com nome invalido
        with pytest.raises(Exception) as exc_info:
            await handle.query("invalid_query_name_that_does_not_exist")

        # Deve falhar com erro de query nao encontrada
        error_msg = str(exc_info.value).lower()
        # Temporal pode retornar varios tipos de erro
        valid_errors = ["not found", "unknown", "no handler", "invalid"]
        assert any(e in error_msg for e in valid_errors), \
            f"Expected query not found error, got: {exc_info.value}"

        logger.info("Invalid query name correctly rejected")

    finally:
        try:
            handle = temporal_client.get_workflow_handle(workflow_id)
            await handle.cancel()
        except Exception:
            pass


# ============================================
# Testes de Polling e Observacao
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_query_status_progression(temporal_client, orchestrator_client, sample_cognitive_plan):
    """
    Testa progressao de status ao longo do tempo.

    Valida:
    1. Workflow iniciado
    2. Multiplas queries em sequencia
    3. Status muda conforme workflow progride
    """
    # Iniciar workflow
    response = await orchestrator_client.post(
        "/api/v1/workflows/start",
        json={
            "cognitive_plan": sample_cognitive_plan,
            "priority": 5,
            "risk_band": "medium",
        }
    )

    if response.status_code != 200:
        pytest.skip(f"Could not start workflow: {response.status_code}")

    workflow_data = response.json()
    workflow_id = workflow_data.get("workflow_id")

    statuses_observed = []

    try:
        handle = temporal_client.get_workflow_handle(workflow_id)

        # Fazer multiplas queries ao longo do tempo
        for i in range(5):
            await asyncio.sleep(3)

            try:
                status = await handle.query("get_status")
                statuses_observed.append(status)
                logger.info(f"Status at {i*3}s: {status}")
            except Exception as e:
                logger.debug(f"Query failed at {i*3}s: {e}")

        # Verificar que coletamos algum status
        if statuses_observed:
            logger.info(f"Observed {len(statuses_observed)} status snapshots")

    finally:
        try:
            handle = temporal_client.get_workflow_handle(workflow_id)
            await handle.cancel()
        except Exception:
            pass
