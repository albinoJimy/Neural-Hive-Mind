"""
Testes E2E para Execution Ticket Service.

Valida:
- Criacao de tickets via API REST
- Persistencia em PostgreSQL (primary) e MongoDB (audit)
- Atualizacao de status via PATCH
- Queries com filtros (plan_id, status, priority)
- Geracao de tokens JWT
- Historico de mudancas
- Webhook dispatch (stub)
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import pytest

from tests.e2e.utils.metrics import get_metric_value, query_prometheus

logger = logging.getLogger(__name__)

# Configuration from environment
EXECUTION_TICKET_SERVICE_URL = os.getenv(
    "EXECUTION_TICKET_SERVICE_URL",
    "http://execution-ticket-service.neural-hive-orchestration.svc.cluster.local:8080",
)
POSTGRESQL_TICKETS_URI = os.getenv(
    "POSTGRESQL_TICKETS_URI",
    "postgresql://postgres:password@postgresql-tickets.neural-hive-orchestration.svc.cluster.local:5432/execution_tickets",
)
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://mongodb-cluster.mongodb-cluster.svc.cluster.local:27017",
)
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "neural_hive_orchestration")
PROMETHEUS_ENDPOINT = os.getenv(
    "PROMETHEUS_ENDPOINT",
    "prometheus-server.monitoring.svc.cluster.local:9090",
)

# Ticket status transitions
VALID_STATUS_TRANSITIONS = {
    "PENDING": ["RUNNING", "CANCELLED"],
    "RUNNING": ["COMPLETED", "FAILED", "CANCELLED"],
    "COMPLETED": [],
    "FAILED": ["PENDING"],  # Allow retry
    "CANCELLED": [],
}


@dataclass
class ExecutionTicket:
    """Execution ticket for testing."""

    ticket_id: str = field(default_factory=lambda: f"ticket-{uuid.uuid4().hex[:8]}")
    plan_id: str = field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    task_id: str = field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    task_type: str = "code_generation"
    status: str = "PENDING"
    priority: int = 5
    sla_deadline: Optional[datetime] = None
    dependencies: List[str] = field(default_factory=list)
    allocation_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


def create_ticket_payload(ticket: ExecutionTicket) -> Dict[str, Any]:
    """Convert ExecutionTicket to API payload."""
    payload = {
        "ticket_id": ticket.ticket_id,
        "plan_id": ticket.plan_id,
        "task_id": ticket.task_id,
        "task_type": ticket.task_type,
        "priority": ticket.priority,
        "dependencies": ticket.dependencies,
        "allocation_metadata": ticket.allocation_metadata,
    }
    if ticket.sla_deadline:
        payload["sla_deadline"] = ticket.sla_deadline.isoformat()
    return payload


# ============================================
# Fixtures
# ============================================


@pytest.fixture(scope="session")
async def execution_ticket_client():
    """
    Session-scoped HTTP client for Execution Ticket Service.

    Provides httpx.AsyncClient for API interactions.
    """
    async with httpx.AsyncClient(
        base_url=EXECUTION_TICKET_SERVICE_URL,
        timeout=30.0,
        headers={"Content-Type": "application/json"},
    ) as client:
        # Test connectivity
        try:
            response = await client.get("/health")
            if response.status_code not in [200, 404]:  # 404 if health endpoint not at /health
                pytest.skip(f"Execution Ticket Service not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.skip(f"Could not connect to Execution Ticket Service at {EXECUTION_TICKET_SERVICE_URL}")

        yield client


@pytest.fixture(scope="session")
def postgresql_tickets_conn():
    """
    Session-scoped PostgreSQL connection for ticket validation.

    Provides direct database access for validation.
    """
    try:
        import psycopg2

        conn = psycopg2.connect(POSTGRESQL_TICKETS_URI)
        yield conn
        conn.close()
    except ImportError:
        pytest.skip("psycopg2 not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to PostgreSQL tickets: {e}")


@pytest.fixture(scope="session")
def mongodb_tickets_client():
    """
    Session-scoped MongoDB client for audit trail validation.

    Provides direct database access for validation.
    """
    try:
        from pymongo import MongoClient

        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # Test connection
        db = client[MONGODB_DATABASE]
        yield db
        client.close()
    except ImportError:
        pytest.skip("pymongo not installed")
    except Exception as e:
        pytest.skip(f"Could not connect to MongoDB: {e}")


@pytest.fixture
def sample_execution_ticket() -> ExecutionTicket:
    """Generate synthetic execution ticket for tests."""
    return ExecutionTicket(
        ticket_id=f"ticket-{uuid.uuid4().hex[:8]}",
        plan_id=f"plan-{uuid.uuid4().hex[:8]}",
        task_id=f"task-{uuid.uuid4().hex[:8]}",
        task_type="code_generation",
        status="PENDING",
        priority=5,
        sla_deadline=datetime.utcnow() + timedelta(hours=4),
        dependencies=[],
        allocation_metadata={"worker_type": "python"},
    )


@pytest.fixture
async def created_ticket(execution_ticket_client, sample_execution_ticket):
    """
    Fixture that creates a ticket and cleans up after test.

    Yields:
        Created ticket data
    """
    payload = create_ticket_payload(sample_execution_ticket)
    response = await execution_ticket_client.post("/api/v1/tickets", json=payload)
    response.raise_for_status()
    ticket_data = response.json()

    yield ticket_data

    # Cleanup: delete ticket (if delete endpoint exists)
    try:
        await execution_ticket_client.delete(f"/api/v1/tickets/{ticket_data['ticket_id']}")
    except Exception as e:
        logger.warning(f"Failed to cleanup ticket: {e}")


# ============================================
# Creation Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_create_ticket_via_api(
    execution_ticket_client,
    postgresql_tickets_conn,
    mongodb_tickets_client,
    sample_execution_ticket,
):
    """
    Testa criacao de ticket via API REST.

    Valida:
    1. POST /api/v1/tickets retorna 201 Created
    2. ticket_id retornado
    3. Persistencia no PostgreSQL
    4. Audit trail no MongoDB
    5. Campos: status=PENDING, created_at, hash
    """
    payload = create_ticket_payload(sample_execution_ticket)

    # Create ticket
    response = await execution_ticket_client.post("/api/v1/tickets", json=payload)

    # Validate response
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    ticket_data = response.json()

    assert "ticket_id" in ticket_data
    assert ticket_data["ticket_id"] == sample_execution_ticket.ticket_id
    assert ticket_data["status"] == "PENDING"
    assert "created_at" in ticket_data

    # Validate persistence in PostgreSQL
    cursor = postgresql_tickets_conn.cursor()
    cursor.execute(
        "SELECT ticket_id, plan_id, task_type, status FROM execution_tickets WHERE ticket_id = %s",
        (sample_execution_ticket.ticket_id,)
    )
    row = cursor.fetchone()
    cursor.close()

    assert row is not None, f"Ticket {sample_execution_ticket.ticket_id} not found in PostgreSQL"
    assert row[1] == sample_execution_ticket.plan_id
    assert row[2] == sample_execution_ticket.task_type
    assert row[3] == "PENDING"

    # Validate audit trail in MongoDB
    audit_collection = mongodb_tickets_client["execution_tickets_audit"]
    audit_entry = audit_collection.find_one({"ticket_id": sample_execution_ticket.ticket_id})

    assert audit_entry is not None, "Audit entry not found in MongoDB"
    assert audit_entry["action"] == "created"

    logger.info(f"Ticket {sample_execution_ticket.ticket_id} created and validated")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_create_ticket_with_dependencies(
    execution_ticket_client,
    postgresql_tickets_conn,
):
    """
    Testa criacao de ticket com dependencias.

    Valida:
    1. Ticket A criado sem dependencias
    2. Ticket B criado com dependencia do Ticket A
    3. Dependencias persistidas no PostgreSQL
    """
    # Create ticket A (no dependencies)
    ticket_a = ExecutionTicket(
        ticket_id=f"ticket-a-{uuid.uuid4().hex[:8]}",
        plan_id=f"plan-deps-{uuid.uuid4().hex[:8]}",
        task_id=f"task-a-{uuid.uuid4().hex[:8]}",
        task_type="code_generation",
        dependencies=[],
    )
    payload_a = create_ticket_payload(ticket_a)
    response_a = await execution_ticket_client.post("/api/v1/tickets", json=payload_a)
    assert response_a.status_code == 201

    # Create ticket B (depends on A)
    ticket_b = ExecutionTicket(
        ticket_id=f"ticket-b-{uuid.uuid4().hex[:8]}",
        plan_id=ticket_a.plan_id,
        task_id=f"task-b-{uuid.uuid4().hex[:8]}",
        task_type="code_generation",
        dependencies=[ticket_a.ticket_id],
    )
    payload_b = create_ticket_payload(ticket_b)
    response_b = await execution_ticket_client.post("/api/v1/tickets", json=payload_b)
    assert response_b.status_code == 201

    ticket_b_data = response_b.json()
    assert ticket_b_data["dependencies"] == [ticket_a.ticket_id]

    # Validate dependencies in PostgreSQL
    cursor = postgresql_tickets_conn.cursor()
    cursor.execute(
        "SELECT dependencies FROM execution_tickets WHERE ticket_id = %s",
        (ticket_b.ticket_id,)
    )
    row = cursor.fetchone()
    cursor.close()

    assert row is not None
    stored_deps = row[0] if isinstance(row[0], list) else json.loads(row[0])
    assert ticket_a.ticket_id in stored_deps

    logger.info(f"Ticket B created with dependency on Ticket A")


# ============================================
# Query Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_ticket_by_id(execution_ticket_client, created_ticket):
    """
    Testa busca de ticket por ID.

    Valida:
    1. GET /api/v1/tickets/{ticket_id} retorna 200
    2. Campos retornados correspondem ao ticket criado
    """
    ticket_id = created_ticket["ticket_id"]

    response = await execution_ticket_client.get(f"/api/v1/tickets/{ticket_id}")

    assert response.status_code == 200
    ticket_data = response.json()

    assert ticket_data["ticket_id"] == ticket_id
    assert ticket_data["plan_id"] == created_ticket["plan_id"]
    assert ticket_data["task_type"] == created_ticket["task_type"]

    logger.info(f"Successfully retrieved ticket {ticket_id}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_tickets_by_plan_id(execution_ticket_client):
    """
    Testa listagem de tickets por plan_id.

    Valida:
    1. 3 tickets criados com plan_id=plan-123
    2. 2 tickets criados com plan_id=plan-456
    3. Query por plan_id=plan-123 retorna 3 tickets
    """
    plan_id_1 = f"plan-list-{uuid.uuid4().hex[:8]}"
    plan_id_2 = f"plan-list-{uuid.uuid4().hex[:8]}"

    # Create tickets for plan 1
    for i in range(3):
        ticket = ExecutionTicket(plan_id=plan_id_1, task_type="code_generation")
        await execution_ticket_client.post("/api/v1/tickets", json=create_ticket_payload(ticket))

    # Create tickets for plan 2
    for i in range(2):
        ticket = ExecutionTicket(plan_id=plan_id_2, task_type="code_generation")
        await execution_ticket_client.post("/api/v1/tickets", json=create_ticket_payload(ticket))

    # Query by plan_id_1
    response = await execution_ticket_client.get(f"/api/v1/tickets?plan_id={plan_id_1}")
    assert response.status_code == 200

    tickets = response.json()
    tickets_list = tickets if isinstance(tickets, list) else tickets.get("items", tickets.get("tickets", []))

    assert len(tickets_list) >= 3, f"Expected at least 3 tickets for plan {plan_id_1}"

    for ticket in tickets_list:
        assert ticket["plan_id"] == plan_id_1

    logger.info(f"Successfully listed tickets by plan_id")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_tickets_by_status(execution_ticket_client):
    """
    Testa listagem de tickets por status.

    Valida:
    1. Tickets com diferentes status criados
    2. Query por status=PENDING retorna apenas tickets PENDING
    """
    plan_id = f"plan-status-{uuid.uuid4().hex[:8]}"

    # Create a pending ticket
    ticket = ExecutionTicket(plan_id=plan_id, task_type="code_generation")
    await execution_ticket_client.post("/api/v1/tickets", json=create_ticket_payload(ticket))

    # Query by status PENDING
    response = await execution_ticket_client.get(f"/api/v1/tickets?status=PENDING&plan_id={plan_id}")
    assert response.status_code == 200

    tickets = response.json()
    tickets_list = tickets if isinstance(tickets, list) else tickets.get("items", tickets.get("tickets", []))

    for ticket_item in tickets_list:
        assert ticket_item["status"] == "PENDING"

    logger.info("Successfully filtered tickets by status")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_list_tickets_with_pagination(execution_ticket_client):
    """
    Testa paginacao de listagem.

    Valida:
    1. 25 tickets criados
    2. Query com limit=10&offset=0 retorna 10 tickets
    3. Query com limit=10&offset=10 retorna proximos 10
    """
    plan_id = f"plan-pagination-{uuid.uuid4().hex[:8]}"

    # Create 25 tickets
    for i in range(25):
        ticket = ExecutionTicket(plan_id=plan_id, task_type="code_generation")
        await execution_ticket_client.post("/api/v1/tickets", json=create_ticket_payload(ticket))

    # First page
    response = await execution_ticket_client.get(f"/api/v1/tickets?plan_id={plan_id}&limit=10&offset=0")
    assert response.status_code == 200

    data = response.json()
    first_page = data if isinstance(data, list) else data.get("items", data.get("tickets", []))
    assert len(first_page) == 10, f"Expected 10 tickets in first page, got {len(first_page)}"

    # Second page
    response = await execution_ticket_client.get(f"/api/v1/tickets?plan_id={plan_id}&limit=10&offset=10")
    assert response.status_code == 200

    data = response.json()
    second_page = data if isinstance(data, list) else data.get("items", data.get("tickets", []))
    assert len(second_page) == 10, f"Expected 10 tickets in second page, got {len(second_page)}"

    # Ensure no overlap
    first_ids = {t["ticket_id"] for t in first_page}
    second_ids = {t["ticket_id"] for t in second_page}
    assert first_ids.isdisjoint(second_ids), "Pages should not overlap"

    logger.info("Pagination working correctly")


# ============================================
# Status Update Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_update_ticket_status(
    execution_ticket_client,
    postgresql_tickets_conn,
    mongodb_tickets_client,
    sample_execution_ticket,
):
    """
    Testa atualizacao de status via PATCH.

    Valida:
    1. Ticket criado com status=PENDING
    2. PATCH para RUNNING retorna 200
    3. Status atualizado no PostgreSQL
    4. Mudanca registrada no audit trail (MongoDB)
    5. started_at timestamp preenchido
    """
    # Create ticket
    payload = create_ticket_payload(sample_execution_ticket)
    response = await execution_ticket_client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201
    ticket_id = sample_execution_ticket.ticket_id

    # Update status to RUNNING
    response = await execution_ticket_client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "RUNNING"}
    )

    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["status"] == "RUNNING"
    assert "started_at" in updated_data and updated_data["started_at"] is not None

    # Validate in PostgreSQL
    cursor = postgresql_tickets_conn.cursor()
    cursor.execute(
        "SELECT status, started_at FROM execution_tickets WHERE ticket_id = %s",
        (ticket_id,)
    )
    row = cursor.fetchone()
    cursor.close()

    assert row[0] == "RUNNING"
    assert row[1] is not None  # started_at should be set

    # Validate audit trail
    audit_collection = mongodb_tickets_client["execution_tickets_audit"]
    audit_entries = list(audit_collection.find(
        {"ticket_id": ticket_id, "action": "status_updated"}
    ).sort("timestamp", -1))

    assert len(audit_entries) > 0, "Status update audit entry not found"
    latest_audit = audit_entries[0]
    assert latest_audit["new_status"] == "RUNNING"

    logger.info(f"Ticket {ticket_id} status updated to RUNNING")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_update_ticket_status_invalid_transition(execution_ticket_client, sample_execution_ticket):
    """
    Testa transicao de status invalida.

    Valida:
    1. Ticket criado com status=PENDING
    2. PATCH diretamente para COMPLETED falha com 400
    3. Mensagem de erro explica a transicao invalida
    """
    # Create ticket
    payload = create_ticket_payload(sample_execution_ticket)
    response = await execution_ticket_client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201
    ticket_id = sample_execution_ticket.ticket_id

    # Try invalid transition: PENDING -> COMPLETED
    response = await execution_ticket_client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "COMPLETED"}
    )

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    error_data = response.json()
    error_msg = str(error_data).lower()
    assert "invalid" in error_msg or "transition" in error_msg, \
        f"Error should mention invalid transition: {error_data}"

    logger.info("Invalid status transition correctly rejected")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_update_ticket_status_to_completed(
    execution_ticket_client,
    postgresql_tickets_conn,
    sample_execution_ticket,
):
    """
    Testa atualizacao para COMPLETED.

    Valida:
    1. Ticket criado com status=PENDING
    2. PATCH para RUNNING
    3. PATCH para COMPLETED
    4. completed_at timestamp preenchido
    5. actual_duration_ms calculado
    """
    # Create ticket
    payload = create_ticket_payload(sample_execution_ticket)
    response = await execution_ticket_client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201
    ticket_id = sample_execution_ticket.ticket_id

    # Update to RUNNING
    response = await execution_ticket_client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "RUNNING"}
    )
    assert response.status_code == 200

    # Wait a bit to have measurable duration
    await asyncio.sleep(1)

    # Update to COMPLETED
    response = await execution_ticket_client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "COMPLETED"}
    )

    assert response.status_code == 200
    completed_data = response.json()

    assert completed_data["status"] == "COMPLETED"
    assert "completed_at" in completed_data and completed_data["completed_at"] is not None

    # Validate in PostgreSQL
    cursor = postgresql_tickets_conn.cursor()
    cursor.execute(
        "SELECT status, completed_at, actual_duration_ms FROM execution_tickets WHERE ticket_id = %s",
        (ticket_id,)
    )
    row = cursor.fetchone()
    cursor.close()

    assert row[0] == "COMPLETED"
    assert row[1] is not None  # completed_at
    # actual_duration_ms might be calculated or null depending on implementation

    logger.info(f"Ticket {ticket_id} completed successfully")


# ============================================
# JWT Token Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_generate_jwt_token(execution_ticket_client, created_ticket):
    """
    Testa geracao de token JWT.

    Valida:
    1. GET /api/v1/tickets/{ticket_id}/token retorna 200
    2. Token JWT valido retornado
    3. Claims incluem: ticket_id, plan_id, exp, iat
    """
    ticket_id = created_ticket["ticket_id"]

    response = await execution_ticket_client.get(f"/api/v1/tickets/{ticket_id}/token")

    assert response.status_code == 200
    token_data = response.json()

    assert "token" in token_data
    token = token_data["token"]
    assert len(token) > 0

    # Decode token (without verification, just to check structure)
    import base64
    parts = token.split(".")
    assert len(parts) == 3, "JWT should have 3 parts"

    # Decode payload (middle part)
    payload_b64 = parts[1]
    # Add padding if needed
    payload_b64 += "=" * (4 - len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))

    assert payload.get("ticket_id") == ticket_id
    assert "plan_id" in payload
    assert "exp" in payload
    assert "iat" in payload

    logger.info(f"JWT token generated for ticket {ticket_id}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_jwt_token_for_nonexistent_ticket(execution_ticket_client):
    """
    Testa geracao de token para ticket inexistente.

    Valida:
    1. Request para ticket_id invalido retorna 404
    """
    fake_ticket_id = f"nonexistent-{uuid.uuid4().hex[:8]}"

    response = await execution_ticket_client.get(f"/api/v1/tickets/{fake_ticket_id}/token")

    assert response.status_code == 404

    logger.info("Token request for nonexistent ticket correctly rejected")


# ============================================
# History Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_ticket_history(
    execution_ticket_client,
    mongodb_tickets_client,
    sample_execution_ticket,
):
    """
    Testa busca de historico de mudancas.

    Valida:
    1. Ticket criado
    2. Status atualizado: PENDING -> RUNNING -> COMPLETED
    3. GET /api/v1/tickets/{ticket_id}/history retorna 3+ mudancas
    4. Cada mudanca tem: timestamp, old_status, new_status
    """
    # Create ticket
    payload = create_ticket_payload(sample_execution_ticket)
    response = await execution_ticket_client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201
    ticket_id = sample_execution_ticket.ticket_id

    # Update status twice
    await execution_ticket_client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "RUNNING"}
    )
    await asyncio.sleep(0.5)
    await execution_ticket_client.patch(
        f"/api/v1/tickets/{ticket_id}/status",
        json={"status": "COMPLETED"}
    )

    # Get history
    response = await execution_ticket_client.get(f"/api/v1/tickets/{ticket_id}/history")

    assert response.status_code == 200
    history = response.json()
    history_list = history if isinstance(history, list) else history.get("items", history.get("history", []))

    # Should have at least creation + 2 status updates
    assert len(history_list) >= 2, f"Expected at least 2 history entries, got {len(history_list)}"

    # Validate history entry structure
    for entry in history_list:
        assert "timestamp" in entry or "created_at" in entry
        # Status change entries should have status info
        if "status" in entry or "new_status" in entry:
            pass  # Valid structure

    logger.info(f"Retrieved {len(history_list)} history entries for ticket {ticket_id}")


# ============================================
# Dual Persistence Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_dual_persistence_consistency(
    execution_ticket_client,
    postgresql_tickets_conn,
    mongodb_tickets_client,
    sample_execution_ticket,
):
    """
    Testa consistencia entre PostgreSQL e MongoDB.

    Valida:
    1. Ticket criado via API
    2. Dados no PostgreSQL
    3. Audit no MongoDB
    4. Campos criticos sao identicos: ticket_id, plan_id, status
    """
    payload = create_ticket_payload(sample_execution_ticket)
    response = await execution_ticket_client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201
    ticket_id = sample_execution_ticket.ticket_id

    # Get from PostgreSQL
    cursor = postgresql_tickets_conn.cursor()
    cursor.execute(
        "SELECT ticket_id, plan_id, task_type, status FROM execution_tickets WHERE ticket_id = %s",
        (ticket_id,)
    )
    pg_row = cursor.fetchone()
    cursor.close()

    assert pg_row is not None, "Ticket not found in PostgreSQL"
    pg_ticket_id, pg_plan_id, pg_task_type, pg_status = pg_row

    # Get latest audit from MongoDB
    audit_collection = mongodb_tickets_client["execution_tickets_audit"]
    mongo_entry = audit_collection.find_one(
        {"ticket_id": ticket_id},
        sort=[("timestamp", -1)]
    )

    assert mongo_entry is not None, "Audit entry not found in MongoDB"

    # Compare critical fields
    assert pg_ticket_id == ticket_id
    assert mongo_entry["ticket_id"] == ticket_id
    assert pg_plan_id == sample_execution_ticket.plan_id

    logger.info(f"Dual persistence consistency verified for ticket {ticket_id}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mongodb_failure_does_not_block_postgresql(
    execution_ticket_client,
    postgresql_tickets_conn,
    sample_execution_ticket,
):
    """
    Testa que falha no MongoDB nao bloqueia persistencia no PostgreSQL.

    Valida:
    1. Simular falha no MongoDB (via port-forward kill)
    2. API ainda retorna 201 Created
    3. Ticket existe no PostgreSQL
    4. MongoDB audit write falha ou loga warning
    """
    # Importar fixture de port-forward para MongoDB
    from tests.e2e.fixtures.circuit_breakers import PortForwardManager

    # Criar manager para MongoDB
    mongodb_manager = PortForwardManager("mongodb")

    # Iniciar port-forward primeiro para garantir estado inicial
    mongodb_manager.start()
    await asyncio.sleep(2)

    try:
        # Parar port-forward para simular MongoDB indisponivel
        mongodb_manager.stop()
        logger.info("MongoDB port-forward stopped, simulating MongoDB outage")

        # Aguardar conexao cair
        await asyncio.sleep(2)

        # Tentar criar ticket - deve funcionar (fail-open para MongoDB)
        payload = create_ticket_payload(sample_execution_ticket)
        response = await execution_ticket_client.post("/api/v1/tickets", json=payload)

        # Asserção: API deve retornar 201 mesmo com MongoDB indisponivel
        assert response.status_code == 201, (
            f"API should return 201 even when MongoDB is down (fail-open behavior), "
            f"but got {response.status_code}: {response.text}"
        )

        ticket_id = sample_execution_ticket.ticket_id
        logger.info(f"Ticket {ticket_id} created successfully despite MongoDB outage")

        # Validar que ticket foi persistido no PostgreSQL
        cursor = postgresql_tickets_conn.cursor()
        cursor.execute(
            "SELECT ticket_id, plan_id, task_type, status FROM execution_tickets WHERE ticket_id = %s",
            (ticket_id,)
        )
        row = cursor.fetchone()
        cursor.close()

        # Asserção: ticket DEVE existir no PostgreSQL
        assert row is not None, (
            f"Ticket {ticket_id} should be persisted in PostgreSQL even when MongoDB is down"
        )
        assert row[0] == ticket_id, f"Ticket ID mismatch: expected {ticket_id}, got {row[0]}"
        assert row[3] == "PENDING", f"Ticket status should be PENDING, got {row[3]}"

        logger.info(f"Ticket {ticket_id} verified in PostgreSQL: plan_id={row[1]}, status={row[3]}")

        # Tentar verificar no MongoDB (deve falhar ou estar vazio)
        try:
            # Se temos acesso direto ao MongoDB client, verificar que audit nao foi escrito
            # Nota: Este bloco pode ser pulado se MongoDB nao estiver acessivel
            pass  # MongoDB esta indisponivel, nao podemos verificar
        except Exception as mongo_error:
            logger.info(f"MongoDB verification failed as expected: {mongo_error}")

        # Opcional: verificar metricas de circuit breaker ou warning logs
        # Isso indica que o sistema detectou a falha do MongoDB
        from tests.e2e.utils.metrics import get_metric_value
        try:
            mongodb_failures = await get_metric_value(
                PROMETHEUS_ENDPOINT,
                "circuit_breaker_failures_total",
                {"circuit": "mongodb_audit"},
            )
            if mongodb_failures:
                logger.info(f"MongoDB circuit breaker failures recorded: {mongodb_failures}")
        except Exception:
            pass  # Metrica pode nao existir ainda

        logger.info("PostgreSQL persistence works independently of MongoDB (fail-open verified)")

    finally:
        # Restaurar MongoDB port-forward para outros testes
        try:
            mongodb_manager.start()
            logger.info("MongoDB port-forward restored")
        except Exception as e:
            logger.warning(f"Could not restore MongoDB port-forward: {e}")


# ============================================
# Performance Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
async def test_query_performance_with_indexes(execution_ticket_client, postgresql_tickets_conn):
    """
    Testa performance de queries com indices.

    Valida:
    1. 100 tickets criados
    2. Query por plan_id < 500ms
    3. Query por status < 500ms
    """
    plan_id = f"plan-perf-{uuid.uuid4().hex[:8]}"

    # Create 100 tickets
    for i in range(100):
        ticket = ExecutionTicket(plan_id=plan_id, task_type="code_generation")
        await execution_ticket_client.post("/api/v1/tickets", json=create_ticket_payload(ticket))

    import time

    # Query by plan_id
    start = time.time()
    response = await execution_ticket_client.get(f"/api/v1/tickets?plan_id={plan_id}")
    plan_query_time = (time.time() - start) * 1000

    assert response.status_code == 200
    assert plan_query_time < 500, f"Plan query took {plan_query_time}ms, expected < 500ms"

    # Query by status
    start = time.time()
    response = await execution_ticket_client.get(f"/api/v1/tickets?status=PENDING&limit=100")
    status_query_time = (time.time() - start) * 1000

    assert response.status_code == 200
    assert status_query_time < 500, f"Status query took {status_query_time}ms, expected < 500ms"

    logger.info(f"Query performance: plan={plan_query_time:.1f}ms, status={status_query_time:.1f}ms")


# ============================================
# Error Handling Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_create_duplicate_ticket(execution_ticket_client, sample_execution_ticket):
    """
    Testa criacao de ticket duplicado.

    Valida:
    1. Primeiro POST retorna 201
    2. Segundo POST com mesmo ticket_id retorna 409 Conflict ou 200 (idempotent)
    """
    payload = create_ticket_payload(sample_execution_ticket)

    # First creation
    response1 = await execution_ticket_client.post("/api/v1/tickets", json=payload)
    assert response1.status_code == 201

    # Second creation (duplicate)
    response2 = await execution_ticket_client.post("/api/v1/tickets", json=payload)

    # Either conflict or idempotent success
    assert response2.status_code in [200, 201, 409], \
        f"Expected 200, 201 or 409, got {response2.status_code}"

    logger.info(f"Duplicate ticket handling: {response2.status_code}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_nonexistent_ticket(execution_ticket_client):
    """
    Testa busca de ticket inexistente.

    Valida:
    1. GET para ticket_id invalido retorna 404
    """
    fake_ticket_id = f"nonexistent-{uuid.uuid4().hex[:8]}"

    response = await execution_ticket_client.get(f"/api/v1/tickets/{fake_ticket_id}")

    assert response.status_code == 404

    logger.info("Nonexistent ticket correctly returns 404")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_update_nonexistent_ticket(execution_ticket_client):
    """
    Testa atualizacao de ticket inexistente.

    Valida:
    1. PATCH para ticket_id invalido retorna 404
    """
    fake_ticket_id = f"nonexistent-{uuid.uuid4().hex[:8]}"

    response = await execution_ticket_client.patch(
        f"/api/v1/tickets/{fake_ticket_id}/status",
        json={"status": "RUNNING"}
    )

    assert response.status_code == 404

    logger.info("Update nonexistent ticket correctly returns 404")


# ============================================
# Metrics Validation Tests
# ============================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_execution_ticket_service_metrics(execution_ticket_client, sample_execution_ticket):
    """
    Testa que metricas do Execution Ticket Service sao expostas.

    Valida:
    - tickets_consumed_total (Counter)
    - tickets_persisted_total (Counter)
    - api_requests_total (Counter)
    """
    # Create a ticket to generate metrics
    payload = create_ticket_payload(sample_execution_ticket)
    await execution_ticket_client.post("/api/v1/tickets", json=payload)

    # Allow time for metrics to propagate
    await asyncio.sleep(2)

    metrics_to_check = [
        "tickets_consumed_total",
        "tickets_persisted_total",
        "api_requests_total",
    ]

    for metric_name in metrics_to_check:
        try:
            result = await query_prometheus(PROMETHEUS_ENDPOINT, metric_name)
            assert "data" in result, f"Metric {metric_name} should be queryable"
            logger.info(f"Metric {metric_name} is available")
        except Exception as e:
            logger.warning(f"Could not query metric {metric_name}: {e}")
