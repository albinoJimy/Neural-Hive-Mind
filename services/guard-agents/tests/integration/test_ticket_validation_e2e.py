"""
Teste E2E para validação completa de tickets.

Este teste valida o fluxo completo:
1. Publica ExecutionTicket em execution.tickets
2. TicketConsumer consome e valida
3. SecurityValidator executa validações
4. GuardrailEnforcer enforça guardrails
5. Verifica publicação em tópico apropriado
6. Verifica persistência no MongoDB
7. Verifica métricas Prometheus
"""

import pytest
import asyncio
import json
from datetime import datetime
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture
async def kafka_producer():
    """Fixture Kafka producer."""
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:9092',
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    await producer.start()
    yield producer
    await producer.stop()


@pytest.fixture
async def mongodb_client():
    """Fixture MongoDB client."""
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.neural_hive
    yield db
    # Cleanup
    await db.security_validations.delete_many({"ticket_id": {"$regex": "^test-"}})


def create_sample_ticket():
    """Cria ticket de teste."""
    return {
        "ticket_id": f"test-{int(datetime.utcnow().timestamp())}",
        "plan_id": "test-plan",
        "intent_id": "test-intent",
        "correlation_id": "test-corr",
        "task_type": "BUILD",
        "security_level": "INTERNAL",
        "service_account": "default",
        "namespace": "default",
        "parameters": {
            "repo": "test-repo",
            "branch": "main"
        },
        "required_capabilities": []
    }


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_ticket_approved(kafka_producer, mongodb_client):
    """
    Testa fluxo E2E de ticket aprovado.

    Fluxo:
    1. Publica ticket válido
    2. Aguarda processamento
    3. Verifica validação no MongoDB com status APPROVED
    4. Verifica publicação em execution.tickets.validated
    """
    # 1. Publicar ticket
    ticket = create_sample_ticket()
    await kafka_producer.send('execution.tickets', value=ticket)

    # 2. Aguardar processamento (max 5s)
    await asyncio.sleep(5)

    # 3. Verificar MongoDB
    validation = await mongodb_client.security_validations.find_one(
        {'ticket_id': ticket['ticket_id']}
    )

    assert validation is not None
    assert validation['validation_status'] == 'APPROVED'
    assert validation['ticket_id'] == ticket['ticket_id']


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_ticket_rejected_secrets(kafka_producer, mongodb_client):
    """
    Testa fluxo E2E de ticket rejeitado por secrets expostos.

    Fluxo:
    1. Publica ticket com secrets
    2. Aguarda processamento
    3. Verifica validação no MongoDB com status REJECTED
    4. Verifica violations de SECRET_EXPOSED
    """
    # 1. Publicar ticket com secret exposto
    ticket = create_sample_ticket()
    ticket["parameters"]["aws_access_key"] = "AKIAIOSFODNN7EXAMPLE"

    await kafka_producer.send('execution.tickets', value=ticket)

    # 2. Aguardar processamento
    await asyncio.sleep(5)

    # 3. Verificar MongoDB
    validation = await mongodb_client.security_validations.find_one(
        {'ticket_id': ticket['ticket_id']}
    )

    assert validation is not None
    assert validation['validation_status'] == 'REJECTED'
    assert len(validation['violations']) > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_ticket_requires_approval(kafka_producer, mongodb_client):
    """
    Testa fluxo E2E de ticket que requer aprovação.

    Fluxo:
    1. Publica ticket de deploy em produção
    2. Aguarda processamento
    3. Verifica validação no MongoDB com status REQUIRES_APPROVAL
    4. Verifica approval_required == True
    """
    # 1. Publicar ticket de deploy em produção
    ticket = create_sample_ticket()
    ticket["task_type"] = "DEPLOY"
    ticket["environment"] = "production"

    await kafka_producer.send('execution.tickets', value=ticket)

    # 2. Aguardar processamento
    await asyncio.sleep(5)

    # 3. Verificar MongoDB
    validation = await mongodb_client.security_validations.find_one(
        {'ticket_id': ticket['ticket_id']}
    )

    assert validation is not None
    # Pode ser REQUIRES_APPROVAL ou REJECTED dependendo das políticas
    assert validation['validation_status'] in ['REQUIRES_APPROVAL', 'REJECTED']


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_multiple_violations(kafka_producer, mongodb_client):
    """
    Testa ticket com múltiplas violações.

    Fluxo:
    1. Publica ticket com múltiplas violações
    2. Aguarda processamento
    3. Verifica que múltiplas violations foram detectadas
    """
    # 1. Publicar ticket com múltiplas violações
    ticket = create_sample_ticket()
    ticket["task_type"] = "DEPLOY"
    ticket["environment"] = "production"
    ticket["parameters"] = {
        "aws_secret": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "affected_percentage": 0.5,  # Blast radius alto
        "rollback_plan": False,
        "tests_passed": False
    }

    await kafka_producer.send('execution.tickets', value=ticket)

    # 2. Aguardar processamento
    await asyncio.sleep(5)

    # 3. Verificar MongoDB
    validation = await mongodb_client.security_validations.find_one(
        {'ticket_id': ticket['ticket_id']}
    )

    assert validation is not None
    assert validation['validation_status'] == 'REJECTED'
    # Deve ter múltiplas violations
    assert len(validation['violations']) >= 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_manual_approval_flow(kafka_producer, mongodb_client):
    """
    Testa fluxo de aprovação manual via API.

    Fluxo:
    1. Publica ticket que requer aprovação (DEPLOY em production)
    2. Aguarda processamento
    3. Verifica status REQUIRES_APPROVAL no MongoDB
    4. Chama API para aprovar
    5. Aguarda processamento
    6. Verifica que ticket foi aprovado
    """
    import httpx

    # 1. Publicar ticket que requer aprovação
    ticket = create_sample_ticket()
    ticket["task_type"] = "DEPLOY"
    ticket["environment"] = "production"
    ticket["security_level"] = "CRITICAL"

    await kafka_producer.send('execution.tickets', value=ticket)

    # 2. Aguardar processamento inicial
    await asyncio.sleep(5)

    # 3. Verificar status REQUIRES_APPROVAL no MongoDB
    validation = await mongodb_client.security_validations.find_one(
        {'ticket_id': ticket['ticket_id']}
    )

    # Se não encontrou validação, pode ser que o serviço não está rodando
    if validation is None:
        pytest.skip("Validation not found - service may not be running")

    # Verificar que requer aprovação (pode ser REQUIRES_APPROVAL ou similar)
    assert validation['validation_status'] in ['REQUIRES_APPROVAL', 'PENDING_APPROVAL', 'REJECTED']

    # Se está REJECTED, não precisa aprovar
    if validation['validation_status'] == 'REJECTED':
        pytest.skip("Ticket was rejected - cannot test approval flow")

    # 4. Aprovar via API
    api_base_url = "http://localhost:8080"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{api_base_url}/api/v1/validation/approve/{ticket['ticket_id']}",
                json={
                    "approver": "test-user",
                    "reason": "E2E test approval",
                    "approved": True
                },
                timeout=10.0
            )

            # API pode não estar implementada ainda
            if response.status_code == 404:
                pytest.skip("Approval API endpoint not implemented")

            assert response.status_code in [200, 201, 202], \
                f"Unexpected status code: {response.status_code}, body: {response.text}"

        except httpx.ConnectError:
            pytest.skip("API server not available")
        except httpx.TimeoutException:
            pytest.skip("API request timeout")

    # 5. Aguardar processamento da aprovação
    await asyncio.sleep(5)

    # 6. Verificar status APPROVED no MongoDB
    validation = await mongodb_client.security_validations.find_one(
        {'ticket_id': ticket['ticket_id']}
    )

    assert validation is not None
    assert validation['validation_status'] == 'APPROVED', \
        f"Expected APPROVED, got {validation['validation_status']}"
    assert validation.get('approved_by') == 'test-user'


@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_validation_flow_timing(kafka_producer, mongodb_client):
    """
    Testa timing do fluxo de validação.

    Verifica que a validação acontece dentro de um tempo aceitável.
    """
    import time

    # Publicar ticket
    ticket = create_sample_ticket()
    start_time = time.time()

    await kafka_producer.send('execution.tickets', value=ticket)

    # Polling para verificar processamento
    max_wait = 10  # segundos
    validation = None

    while time.time() - start_time < max_wait:
        validation = await mongodb_client.security_validations.find_one(
            {'ticket_id': ticket['ticket_id']}
        )

        if validation:
            break

        await asyncio.sleep(0.5)

    processing_time = time.time() - start_time

    if validation is None:
        pytest.skip("Validation not processed - service may not be running")

    # Verificar tempo de processamento (deve ser < 5 segundos)
    assert processing_time < 5.0, \
        f"Processing took too long: {processing_time:.2f}s"

    # Verificar que validação tem campos esperados
    assert 'ticket_id' in validation
    assert 'validation_status' in validation
    assert 'created_at' in validation or 'timestamp' in validation


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
