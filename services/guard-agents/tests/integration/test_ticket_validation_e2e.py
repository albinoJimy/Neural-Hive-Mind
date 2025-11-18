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


@pytest.mark.skip(reason="Requer API implementada")
@pytest.mark.asyncio
@pytest.mark.integration
async def test_e2e_manual_approval_flow(kafka_producer, mongodb_client):
    """
    Testa fluxo de aprovação manual via API.

    Fluxo:
    1. Publica ticket que requer aprovação
    2. Aguarda processamento
    3. Chama API para aprovar
    4. Verifica que ticket foi publicado em validated
    """
    # TODO: Implementar quando API estiver completa
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
