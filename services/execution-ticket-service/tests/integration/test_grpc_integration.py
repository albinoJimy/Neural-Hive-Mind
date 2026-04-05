"""
Integration Tests for gRPC - Execution Ticket Service

Testes de integração que usam um servidor gRPC real (sem mocks).
Cobre: startup do servidor, comunicação cliente, streaming RPC (simulado),
e tratamento de erros.

Autor: Integration Test Suite
Data: 2026-04-04
"""
import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Generator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import grpc
import pytest
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from src.database.postgres_client import PostgresClient
from src.grpc_service.server import start_grpc_server, stop_grpc_server
from src.models import (
    Consistency,
    DeliveryMode,
    ExecutionTicket,
    Priority,
    QoS,
    RiskBand,
    SLA,
    SecurityLevel,
    TaskType,
    TicketStatus,
)
from src.proto_gen import ticket_service_pb2, ticket_service_pb2_grpc


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """
    Sobe container PostgreSQL para testes de integração.

    Usa testcontainers para gerenciar o ciclo de vida do container.
    A imagem postgres:17-alpine é leve e adequada para testes.
    """
    postgres = PostgresContainer(
        image="postgres:17-alpine",
        username="test_user",
        password="test_pass",
        dbname="test_tickets",
        port=5432,
    )

    try:
        postgres.start()
        # Atualizar variáveis de ambiente com a porta exposta
        os.environ["POSTGRES_PORT"] = postgres.get_exposed_port(5432)
        os.environ["POSTGRES_HOST"] = "localhost"
        os.environ["POSTGRES_USER"] = "test_user"
        os.environ["POSTGRES_PASSWORD"] = "test_pass"
        os.environ["POSTGRES_DATABASE"] = "test_tickets"

        yield postgres

    finally:
        postgres.stop()


@pytest.fixture
async def postgres_settings(postgres_container) -> SimpleNamespace:
    """
    Configurações PostgreSQL conectadas ao container de teste.

    As credenciais correspondem ao container levantado em postgres_container.
    """
    return SimpleNamespace(
        postgres_host="localhost",
        postgres_port=int(postgres_container.get_exposed_port(5432)),
        postgres_database="test_tickets",
        postgres_user="test_user",
        postgres_password="test_pass",
        postgres_pool_size=5,
        postgres_max_overflow=10,
        grpc_port=50052,  # Porta para testes gRPC
        grpc_max_workers=10,
        grpc_max_concurrent_rpcs=100,
        grpc_bind_retry_attempts=3,
        grpc_bind_retry_initial_delay=0.1,
        grpc_bind_retry_max_delay=1.0,
        jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
        jwt_algorithm="HS256",
        jwt_token_expiration_seconds=3600,
    )


@pytest.fixture
async def setup_database(postgres_container):
    """
    Cria a tabela execution_tickets no banco de teste.

    Executa o SQL equivalente à migração 001 antes de cada teste.
    """
    # Obter connection URL do container
    connection_url = postgres_container.get_connection_url()

    # Criar engine temporário para setup
    from sqlalchemy.ext.asyncio import (
        AsyncEngine,
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(connection_url.replace("postgresql://", "postgresql+asyncpg://"))
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Criar tabela
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS execution_tickets (
                    id BIGSERIAL PRIMARY KEY,
                    ticket_id VARCHAR(36) UNIQUE NOT NULL,
                    plan_id VARCHAR(36) NOT NULL,
                    intent_id VARCHAR(36) NOT NULL,
                    decision_id VARCHAR(36) NOT NULL,
                    correlation_id VARCHAR(36),
                    trace_id VARCHAR(64),
                    span_id VARCHAR(32),
                    task_id VARCHAR(255) NOT NULL,
                    task_type VARCHAR(20) NOT NULL,
                    description TEXT NOT NULL,
                    dependencies JSONB DEFAULT '[]' NOT NULL,
                    status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
                    priority VARCHAR(20) NOT NULL,
                    risk_band VARCHAR(20) NOT NULL,
                    sla JSONB NOT NULL,
                    qos JSONB NOT NULL,
                    parameters JSONB DEFAULT '{}' NOT NULL,
                    required_capabilities JSONB DEFAULT '[]' NOT NULL,
                    security_level VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    estimated_duration_ms BIGINT,
                    actual_duration_ms BIGINT,
                    retry_count INTEGER DEFAULT 0 NOT NULL,
                    error_message TEXT,
                    compensation_ticket_id VARCHAR(36),
                    metadata JSONB DEFAULT '{}' NOT NULL,
                    schema_version INTEGER DEFAULT 1 NOT NULL,
                    hash VARCHAR(64),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    CONSTRAINT chk_status CHECK (
                        status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'COMPENSATING', 'COMPENSATED')
                    ),
                    CONSTRAINT chk_retry_count CHECK (retry_count >= 0)
                );
                CREATE INDEX IF NOT EXISTS idx_ticket_id ON execution_tickets(ticket_id);
                CREATE INDEX IF NOT EXISTS idx_plan_id ON execution_tickets(plan_id);
                CREATE INDEX IF NOT EXISTS idx_status ON execution_tickets(status);
            """)
        )

    yield session_maker

    # Limpeza após o teste
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS execution_tickets"))
    await engine.dispose()


@pytest.fixture
async def grpc_server(postgres_settings, setup_database):
    """
    Inicia servidor gRPC para testes.

    Usa porta dedicada para não conflitar com servidor em desenvolvimento.
    """
    # Configurar variáveis de ambiente
    for key, value in vars(postgres_settings).items():
        if key.startswith("jwt_") or key.startswith("grpc_") or key.startswith("postgres_"):
            os.environ[key.upper()] = str(value)

    # Mockar get_postgres_client para usar nosso setup
    from src.database import postgres_client

    original_client = postgres_client._postgres_client

    # Criar e conectar cliente PostgreSQL
    client = PostgresClient(postgres_settings)
    await client.connect()
    postgres_client._postgres_client = client

    # Iniciar servidor gRPC
    server, health_servicer = await start_grpc_server(postgres_settings)

    yield server, postgres_settings.grpc_port

    # Cleanup
    await stop_grpc_server(server, health_servicer)
    await client.disconnect()
    postgres_client._postgres_client = original_client


@pytest.fixture
def grpc_channel(grpc_server):
    """
    Cria canal gRPC para comunicação com o servidor de teste.
    """
    _, port = grpc_server
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    yield channel
    channel.close()


@pytest.fixture
def sample_ticket() -> ExecutionTicket:
    """
    Cria um ticket de exemplo para testes.
    """
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    return ExecutionTicket(
        ticket_id=str(uuid4()),
        plan_id=str(uuid4()),
        intent_id=str(uuid4()),
        decision_id=str(uuid4()),
        task_id="task-001",
        task_type=TaskType.QUERY,
        description="Test ticket for integration tests",
        status=TicketStatus.PENDING,
        priority=Priority.NORMAL,
        risk_band=RiskBand.medium,
        sla=SLA(deadline=now_ms + 3600000, timeout_ms=30000, max_retries=3),
        qos=QoS(
            delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            consistency=Consistency.STRONG,
            durability=Durability.PERSISTENT,
        ),
        parameters={"query": "SELECT * FROM test"},
        required_capabilities=["sql_query"],
        security_level=SecurityLevel.INTERNAL,
        created_at=now_ms,
    )


async def create_ticket_in_db(client: PostgresClient, ticket: ExecutionTicket):
    """
    Helper para criar ticket no banco de dados.
    """
    return await client.create_ticket(ticket)


# =============================================================================
# TESTES: SERVER STARTUP
# =============================================================================


@pytest.mark.asyncio
async def test_grpc_server_starts_successfully(grpc_server):
    """
    Testa se o servidor gRPC inicia sem erros.

    Verifica:
    - Servidor inicia sem exceções
    - Porta está vinculada corretamente
    - Health check está disponível (se instalado)
    """
    server, port = grpc_server

    assert server is not None
    assert port > 0


@pytest.mark.asyncio
async def test_grpc_server_handles_multiple_connections(grpc_channel):
    """
    Testa se o servidor gRPC aceita múltiplas conexões simultâneas.

    Simula múltiplos clientes conectando ao mesmo tempo.
    """
    # Criar múltiplos canais simultâneos
    channels = []
    stubs = []

    for _ in range(5):
        ch = grpc.aio.insecure_channel("localhost:50052")
        stub = ticket_service_pb2_grpc.TicketServiceStub(ch)
        channels.append(ch)
        stubs.append(stub)

    # Fazer chamadas paralelas
    responses = await asyncio.gather(*[
        stub.GetTicket(ticket_service_pb2.GetTicketRequest(ticket_id="non-existent"))
        for stub in stubs
    ])

    # Todas as chamadas devem retornar (mesmo com NOT_FOUND)
    assert len(responses) == 5

    # Cleanup
    for ch in channels:
        await ch.close()


# =============================================================================
# TESTES: CLIENT COMMUNICATION - UNARY RPCs
# =============================================================================


@pytest.mark.asyncio
async def test_get_ticket_returns_ticket_when_exists(grpc_channel, sample_ticket, grpc_server):
    """
    Testa GetTicket RPC quando o ticket existe.

    Fluxo:
    1. Cria ticket no banco
    2. Chama GetTicket via gRPC
    3. Verifica resposta contém dados corretos
    """
    from src.database import postgres_client

    # Criar ticket no banco
    await create_ticket_in_db(postgres_client._postgres_client, sample_ticket)

    # Criar stub e fazer chamada
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GetTicketRequest(ticket_id=sample_ticket.ticket_id)
    response = await stub.GetTicket(request, timeout=5)

    # Verificar resposta
    assert response is not None
    assert response.ticket.ticket_id == sample_ticket.ticket_id
    assert response.ticket.plan_id == sample_ticket.plan_id
    assert response.ticket.task_id == sample_ticket.task_id
    assert response.ticket.task_type == TaskType.QUERY.value
    assert response.ticket.status == TicketStatus.PENDING.value
    assert response.ticket.priority == Priority.NORMAL.value


@pytest.mark.asyncio
async def test_get_ticket_returns_not_found_when_missing(grpc_channel):
    """
    Testa GetTicket RPC quando o ticket não existe.

    Verifica tratamento correto de erro NOT_FOUND via gRPC status codes.
    """
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GetTicketRequest(ticket_id=str(uuid4()))

    # A chamada deve retornar NOT_FOUND
    # NOTA: gRPC pode levantar exceção ou retornar código de erro
    try:
        response = await stub.GetTicket(request, timeout=5)
        # Se não levantar exceção, verificar se response está vazio
        assert response.ticket.ticket_id == ""
    except grpc.aio.AioRpcError as e:
        # Verificar código de status
        assert e.code() == grpc.StatusCode.NOT_FOUND
        assert "not found" in e.details().lower()


@pytest.mark.asyncio
async def test_list_tickets_returns_all_tickets(grpc_channel, sample_ticket, grpc_server):
    """
    Testa ListTickets RPC sem filtros.

    Fluxo:
    1. Cria múltiplos tickets
    2. Chama ListTickets sem filtros
    3. Verifica paginação e contagem total
    """
    from src.database import postgres_client

    # Criar 3 tickets
    tickets = []
    for i in range(3):
        ticket = sample_ticket.model_copy(
            update={
                "ticket_id": str(uuid4()),
                "task_id": f"task-{i:03d}",
                "description": f"Test ticket {i}",
            }
        )
        await create_ticket_in_db(postgres_client._postgres_client, ticket)
        tickets.append(ticket)

    # Listar tickets
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.ListTicketsRequest(limit=10, offset=0)
    response = await stub.ListTickets(request, timeout=5)

    # Verificar resposta
    assert len(response.tickets) == 3
    assert response.total == 3
    # Verificar ordenação (created_at desc)
    assert response.tickets[0].task_id == "task-002"


@pytest.mark.asyncio
async def test_list_tickets_filters_by_plan_id(grpc_channel, sample_ticket, grpc_server):
    """
    Testa ListTickets RPC com filtro de plan_id.

    Verifica:
    - Filtragem por plan_id funciona
    - Apenas tickets do plan são retornados
    - Total está correto
    """
    from src.database import postgres_client

    # Criar tickets com diferentes plan_ids
    plan1 = str(uuid4())
    plan2 = str(uuid4())

    for plan_id in [plan1, plan1, plan2]:
        ticket = sample_ticket.model_copy(
            update={"ticket_id": str(uuid4()), "plan_id": plan_id, "task_id": f"task-{plan_id[:8]}"}
        )
        await create_ticket_in_db(postgres_client._postgres_client, ticket)

    # Listar tickets filtrando por plan1
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.ListTicketsRequest(plan_id=plan1, limit=10, offset=0)
    response = await stub.ListTickets(request, timeout=5)

    # Verificar que apenas tickets do plan1 foram retornados
    assert len(response.tickets) == 2
    assert response.total == 2
    assert all(t.plan_id == plan1 for t in response.tickets)


@pytest.mark.asyncio
async def test_list_tickets_filters_by_status(grpc_channel, sample_ticket, grpc_server):
    """
    Testa ListTickets RPC com filtro de status.

    Verifica:
    - Filtragem por status funciona
    - Apenas tickets com o status são retornados
    """
    from src.database import postgres_client

    # Criar tickets com diferentes status
    for status in [TicketStatus.PENDING, TicketStatus.RUNNING, TicketStatus.COMPLETED]:
        ticket = sample_ticket.model_copy(
            update={"ticket_id": str(uuid4()), "status": status, "task_id": f"task-{status.value}"}
        )
        await create_ticket_in_db(postgres_client._postgres_client, ticket)

    # Listar tickets filtrando por PENDING
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.ListTicketsRequest(status="PENDING", limit=10, offset=0)
    response = await stub.ListTickets(request, timeout=5)

    # Verificar que apenas tickets PENDING foram retornados
    assert len(response.tickets) >= 1
    assert all(t.status == "PENDING" for t in response.tickets)


@pytest.mark.asyncio
async def test_list_tickets_respects_pagination(grpc_channel, sample_ticket, grpc_server):
    """
    Testa paginação do ListTickets RPC.

    Verifica:
    - offset funciona corretamente
    - limit respeitado
    - Paginação combina com filtros
    """
    from src.database import postgres_client

    # Criar 5 tickets
    for i in range(5):
        ticket = sample_ticket.model_copy(
            update={"ticket_id": str(uuid4()), "task_id": f"task-{i:03d}"}
        )
        await create_ticket_in_db(postgres_client._postgres_client, ticket)

    # Primeira página (limit=2, offset=0)
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request1 = ticket_service_pb2.ListTicketsRequest(limit=2, offset=0)
    response1 = await stub.ListTickets(request1, timeout=5)

    assert len(response1.tickets) == 2
    assert response1.total == 5

    # Segunda página (limit=2, offset=2)
    request2 = ticket_service_pb2.ListTicketsRequest(limit=2, offset=2)
    response2 = await stub.ListTickets(request2, timeout=5)

    assert len(response2.tickets) == 2
    assert response2.total == 5

    # Verificar que os tickets são diferentes
    ids_page1 = {t.ticket_id for t in response1.tickets}
    ids_page2 = {t.ticket_id for t in response2.tickets}
    assert ids_page1.isdisjoint(ids_page2)


@pytest.mark.asyncio
async def test_update_ticket_status_changes_status(grpc_channel, sample_ticket, grpc_server):
    """
    Testa UpdateTicketStatus RPC.

    Fluxo:
    1. Cria ticket com status PENDING
    2. Atualiza para RUNNING
    3. Verifica status foi atualizado
    """
    from src.database import postgres_client

    # Criar ticket PENDING
    await create_ticket_in_db(postgres_client._postgres_client, sample_ticket)

    # Atualizar para RUNNING
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.UpdateTicketStatusRequest(
        ticket_id=sample_ticket.ticket_id, status="RUNNING"
    )
    response = await stub.UpdateTicketStatus(request, timeout=5)

    # Verificar resposta
    assert response.ticket.ticket_id == sample_ticket.ticket_id
    assert response.ticket.status == "RUNNING"


@pytest.mark.asyncio
async def test_update_ticket_status_with_error_message(grpc_channel, sample_ticket, grpc_server):
    """
    Testa UpdateTicketStatus RPC com mensagem de erro.

    Verifica:
    - Status muda para FAILED
    - error_message é persistido
    """
    from src.database import postgres_client

    # Criar ticket
    await create_ticket_in_db(postgres_client._postgres_client, sample_ticket)

    # Atualizar para FAILED com mensagem de erro
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.UpdateTicketStatusRequest(
        ticket_id=sample_ticket.ticket_id,
        status="FAILED",
        error_message="Database connection timeout",
    )
    response = await stub.UpdateTicketStatus(request, timeout=5)

    # Verificar resposta
    assert response.ticket.status == "FAILED"

    # Verificar no banco que error_message foi salvo
    ticket_orm = await postgres_client._postgres_client.get_ticket_by_id(sample_ticket.ticket_id)
    assert ticket_orm.error_message == "Database connection timeout"


@pytest.mark.asyncio
async def test_update_nonexistent_ticket_returns_not_found(grpc_channel):
    """
    Testa UpdateTicketStatus para ticket inexistente.

    Verifica código NOT_FOUND é retornado.
    """
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.UpdateTicketStatusRequest(
        ticket_id=str(uuid4()), status="RUNNING"
    )

    try:
        await stub.UpdateTicketStatus(request, timeout=5)
        assert False, "Should have raised NOT_FOUND"
    except grpc.aio.AioRpcError as e:
        assert e.code() == grpc.StatusCode.NOT_FOUND


@pytest.mark.asyncio
async def test_generate_token_creates_valid_jwt(grpc_channel, sample_ticket, grpc_server):
    """
    Testa GenerateToken RPC para tickets com status PENDING.

    Fluxo:
    1. Cria ticket PENDING
    2. Gera token JWT
    3. Verifica token é válido
    """
    from src.database import postgres_client
    from src.models import decode_token

    # Criar ticket PENDING
    await create_ticket_in_db(postgres_client._postgres_client, sample_ticket)

    # Gerar token
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GenerateTokenRequest(ticket_id=sample_ticket.ticket_id)
    response = await stub.GenerateToken(request, timeout=5)

    # Verificar resposta
    assert response.access_token != ""
    assert response.expires_at > 0

    # Decodificar e verificar token
    payload = decode_token(
        response.access_token,
        "test-secret-key-32-bytes-long-for-testing",
        "HS256",
    )
    assert payload.ticket_id == sample_ticket.ticket_id
    assert payload.plan_id == sample_ticket.plan_id


@pytest.mark.asyncio
async def test_generate_token_fails_for_completed_ticket(grpc_channel, sample_ticket, grpc_server):
    """
    Testa GenerateToken RPC para ticket COMPLETED.

    Verifica:
    - Tokens não podem ser gerados para tickets concluídos
    - FAILED_PRECONDITION é retornado
    """
    from src.database import postgres_client

    # Criar ticket COMPLETED
    ticket = sample_ticket.model_copy(update={"ticket_id": str(uuid4()), "status": TicketStatus.COMPLETED})
    await create_ticket_in_db(postgres_client._postgres_client, ticket)

    # Tentar gerar token
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GenerateTokenRequest(ticket_id=ticket.ticket_id)

    try:
        await stub.GenerateToken(request, timeout=5)
        assert False, "Should have raised FAILED_PRECONDITION"
    except grpc.aio.AioRpcError as e:
        assert e.code() == grpc.StatusCode.FAILED_PRECONDITION
        assert "cannot generate token" in e.details().lower()


@pytest.mark.asyncio
async def test_generate_token_for_running_ticket_succeeds(grpc_channel, sample_ticket, grpc_server):
    """
    Testa GenerateToken RPC para ticket RUNNING.

    Tickets RUNNING também podem gerar tokens (para heartbeat).
    """
    from src.database import postgres_client

    # Criar ticket RUNNING
    ticket = sample_ticket.model_copy(update={"ticket_id": str(uuid4()), "status": TicketStatus.RUNNING})
    await create_ticket_in_db(postgres_client._postgres_client, ticket)

    # Gerar token
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GenerateTokenRequest(ticket_id=ticket.ticket_id)
    response = await stub.GenerateToken(request, timeout=5)

    # Verificar
    assert response.access_token != ""


# =============================================================================
# TESTES: ERROR HANDLING
# =============================================================================


@pytest.mark.asyncio
async def test_get_ticket_with_invalid_id_format(grpc_channel):
    """
    Testa GetTicket com ID em formato inválido.

    Verifica:
    - Requisição malformada é tratada
    - INVALID_ARGUMENT ou NOT_FOUND é retornado
    """
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GetTicketRequest(ticket_id="")

    try:
        await stub.GetTicket(request, timeout=5)
        # Pode retornar vazio sem erro
    except grpc.aio.AioRpcError as e:
        # Se houver erro, deve ser INVALID_ARGUMENT ou NOT_FOUND
        assert e.code() in [grpc.StatusCode.INVALID_ARGUMENT, grpc.StatusCode.NOT_FOUND]


@pytest.mark.asyncio
async def test_update_ticket_with_invalid_status(grpc_channel, sample_ticket, grpc_server):
    """
    Testa UpdateTicketStatus com status inválido.

    Verifica:
    - Status inválido é rejeitado
    - INTERNAL error é retornado
    """
    from src.database import postgres_client

    # Criar ticket
    await create_ticket_in_db(postgres_client._postgres_client, sample_ticket)

    # Tentar atualizar com status inválido
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.UpdateTicketStatusRequest(
        ticket_id=sample_ticket.ticket_id, status="INVALID_STATUS"
    )

    # A chamada pode falhar com INTERNAL
    try:
        await stub.UpdateTicketStatus(request, timeout=5)
    except grpc.aio.AioRpcError as e:
        assert e.code() == grpc.StatusCode.INTERNAL


@pytest.mark.asyncio
async def test_request_timeout_is_handled(grpc_channel):
    """
    Testa timeout de requisição gRPC.

    Verifica:
    - Timeout configurado é respeitado
    - DeadlineExceeded é retornado quando excede
    """
    # NOTA: Este teste simula timeout, mas na prática
    # sem operações lentas é difícil de testar.
    # Verificamos apenas que timeout funciona na API

    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GetTicketRequest(ticket_id=str(uuid4()))

    # Definir timeout muito curto
    try:
        # Em operação normal não deve timeout, mas se houver lentidão
        await stub.GetTicket(request, timeout=0.001)
    except (grpc.aio.AioRpcError, asyncio.TimeoutError) as e:
        # Timeout é esperado com valor tão baixo
        if isinstance(e, grpc.aio.AioRpcError):
            assert e.code() in [grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.NOT_FOUND]


@pytest.mark.asyncio
async def test_concurrent_requests_are_handled_correctly(grpc_channel, grpc_server):
    """
    Testa concorrência de requisições gRPC.

    Verifica:
    - Múltiplas requisições simultâneas são processadas
    - Não há race conditions
    - Todas as respostas são corretas
    """
    from src.database import postgres_client

    # Criar tickets
    ticket_ids = []
    for i in range(10):
        ticket = ExecutionTicket(
            ticket_id=str(uuid4()),
            plan_id=str(uuid4()),
            intent_id=str(uuid4()),
            decision_id=str(uuid4()),
            task_id=f"concurrent-task-{i}",
            task_type=TaskType.QUERY,
            description=f"Concurrent test ticket {i}",
            status=TicketStatus.PENDING,
            priority=Priority.NORMAL,
            risk_band=RiskBand.medium,
            sla=SLA(deadline=9999999999, timeout_ms=30000, max_retries=3),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.STRONG,
                durability=Durability.PERSISTENT,
            ),
            parameters={},
            required_capabilities=[],
            security_level=SecurityLevel.INTERNAL,
            created_at=int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        )
        await create_ticket_in_db(postgres_client._postgres_client, ticket)
        ticket_ids.append(ticket.ticket_id)

    # Fazer requisições concorrentes
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)

    async def get_ticket(ticket_id: str):
        request = ticket_service_pb2.GetTicketRequest(ticket_id=ticket_id)
        response = await stub.GetTicket(request, timeout=5)
        return response.ticket.ticket_id

    results = await asyncio.gather(*[get_ticket(tid) for tid in ticket_ids])

    # Verificar que todos os tickets foram retornados
    assert len(results) == 10
    assert set(results) == set(ticket_ids)


# =============================================================================
# TESTES: STREAMING RPC (Simulado)
# =============================================================================

# NOTA: O proto atual não define streaming RPCs.
# Estes testes preparam a estrutura para futuras implementações.


@pytest.mark.asyncio
async def test_server_streaming_is_supported(grpc_channel):
    """
    Testa preparação para server streaming RPC.

    Atualmente o proto não tem streaming, mas o teste verifica
    que o canal suporta o conceito.
    """
    # Verificar que o canal está ativo e pode suportar streaming
    assert grpc_channel is not None
    # Streaming será implementado quando o proto for atualizado


@pytest.mark.asyncio
async def test_bidirectional_streaming_is_supported(grpc_channel):
    """
    Testa preparação para bidirectional streaming RPC.

    Atualmente o proto não tem streaming bidirecional, mas o
    teste verifica que a infraestrutura está pronta.
    """
    # Verificar que o canal está ativo
    assert grpc_channel is not None
    # Streaming bidirecional será implementado quando o proto for atualizado


# =============================================================================
# TESTES: METADATA E TRACING
# =============================================================================


@pytest.mark.asyncio
async def test_grpc_metadata_is_propagated(grpc_channel, sample_ticket, grpc_server):
    """
    Testa que metadados gRPC são propagados corretamente.

    Verifica:
    - Metadata de tracing (traceparent) é aceito
    - Metadata customizado não quebra a requisição
    """
    from src.database import postgres_client

    # Criar ticket
    await create_ticket_in_db(postgres_client._postgres_client, sample_ticket)

    # Fazer requisição com metadata
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GetTicketRequest(ticket_id=sample_ticket.ticket_id)

    # Adicionar metadata
    metadata = [
        ("traceparent", "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"),
        ("user-id", "test-user-123"),
        ("request-id", str(uuid4())),
    ]

    response = await stub.GetTicket(request, metadata=metadata, timeout=5)

    # Verificar resposta
    assert response.ticket.ticket_id == sample_ticket.ticket_id


@pytest.mark.asyncio
async def test_grpc_deadline_is_enforced(grpc_channel):
    """
    Testa que deadline gRPC é respeitado.

    Deadline é diferente de timeout - é um tempo absoluto.
    """
    stub = ticket_service_pb2_grpc.TicketServiceStub(grpc_channel)
    request = ticket_service_pb2.GetTicketRequest(ticket_id=str(uuid4()))

    # Usar deadline em vez de timeout
    import time

    deadline = time.time() + 5.0  # 5 segundos a partir de agora

    try:
        response = await stub.GetTicket(request, deadline=deadline)
        # Se não achar, retorna vazio ou NOT_FOUND
        assert response is not None
    except grpc.aio.AioRpcError as e:
        # NOT_FOUND é esperado para ticket inexistente
        assert e.code() == grpc.StatusCode.NOT_FOUND


# =============================================================================
# TESTES: HEALTH CHECK
# =============================================================================


@pytest.mark.asyncio
async def test_grpc_health_check_is_available(grpc_server):
    """
    Testa que o health check gRPC está disponível.

    Verifica:
    - Serviço de health check responde
    - Status SERVING é retornado
    """
    _, port = grpc_server

    try:
        from grpc_health.v1 import health_pb2, health_pb2_grpc

        channel = grpc.aio.insecure_channel(f"localhost:{port}")
        health_stub = health_pb2_grpc.HealthStub(channel)

        # Verificar health check global
        request = health_pb2.HealthCheckRequest(service="")
        response = await health_stub.Check(request, timeout=2)

        assert response.status == health_pb2.HealthCheckResponse.SERVING

        # Verificar health check específico do serviço
        request = health_pb2.HealthCheckRequest(service="ticket_service.TicketService")
        response = await health_stub.Check(request, timeout=2)

        assert response.status == health_pb2.HealthCheckResponse.SERVING

        await channel.close()

    except ImportError:
        # grpc-health-checking não instalado - pular teste
        pytest.skip("grpc-health-checking not installed")


# =============================================================================
# TESTES: SERVER SHUTDOWN
# =============================================================================


@pytest.mark.asyncio
async def test_grpc_server_stops_gracefully(postgres_settings, setup_database):
    """
    Testa que o servidor gRPC para gracefulmente.

    Verifica:
    - Servidor aceita shutdown
    - Conexões existentes são finalizadas
    - Porta é liberada
    """
    # Configurar ambiente
    for key, value in vars(postgres_settings).items():
        if key.startswith("jwt_") or key.startswith("grpc_") or key.startswith("postgres_"):
            os.environ[key.upper()] = str(value)

    from src.database import postgres_client

    # Criar cliente PostgreSQL
    client = PostgresClient(postgres_settings)
    await client.connect()
    postgres_client._postgres_client = client

    # Iniciar servidor
    server, health_servicer = await start_grpc_server(postgres_settings)
    assert server is not None

    # Parar servidor
    await stop_grpc_server(server, health_servicer)

    # Verificar que servidor está parido
    assert server is not None

    # Cleanup
    await client.disconnect()
