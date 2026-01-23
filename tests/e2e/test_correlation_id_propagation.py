"""
E2E Test: Validação de propagação de correlation_id através do pipeline completo.

Valida:
- Gateway → STE: correlation_id preservado (camelCase → snake_case)
- STE → Consensus: correlation_id no cognitive_plan
- Consensus → Orchestrator: correlation_id na decisão consolidada
- Orchestrator → Tickets: correlation_id em todos os execution tickets
"""

import pytest
import uuid
import asyncio
from typing import Dict, Any, List, Optional

from tests.e2e.utils.kafka_helpers import (
    wait_for_kafka_message,
    collect_kafka_messages,
    wait_for_avro_message,
    collect_avro_messages,
)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_correlation_id_propagation_gateway_to_tickets(
    gateway_client,
    avro_consumer,
    test_kafka_topics,
    test_mongodb_collections,
):
    """
    Testa propagação de correlation_id: Gateway → STE → Consensus → Orchestrator → Tickets.
    """
    # 1. Enviar intent com correlation_id explícito
    correlation_id = str(uuid.uuid4())

    intent_request = {
        "text": "Criar API REST simples",
        "language": "pt-BR",
        "domain": "TECHNICAL",
        "priority": "NORMAL",
        "correlation_id": correlation_id,
    }

    response = await gateway_client.post("/intentions", json=intent_request)
    assert response.status_code == 200
    intent_data = response.json()
    intent_id = intent_data["intent_id"]

    # Validar que Gateway retornou o mesmo correlation_id
    assert intent_data.get("correlation_id") == correlation_id, (
        f"Gateway não retornou correlation_id. "
        f"Esperado: {correlation_id}, Recebido: {intent_data.get('correlation_id')}"
    )

    # 2. Aguardar cognitive_plan no tópico plans.ready
    plan = await wait_for_avro_message(
        avro_consumer,
        topic=test_kafka_topics.get("plans.ready", "plans.ready"),
        filter_fn=lambda msg: msg.get("intent_id") == intent_id,
        timeout=60,
    )
    assert plan is not None, "Timeout aguardando cognitive_plan em plans.ready"

    # Validar que STE preservou correlation_id
    assert plan.get("correlation_id") == correlation_id, (
        f"STE não preservou correlation_id. "
        f"Esperado: {correlation_id}, Recebido: {plan.get('correlation_id')}"
    )

    plan_id = plan["plan_id"]

    # 3. Aguardar decisão consolidada no tópico plans.consensus
    decision = await wait_for_avro_message(
        avro_consumer,
        topic=test_kafka_topics.get("plans.consensus", "plans.consensus"),
        filter_fn=lambda msg: msg.get("plan_id") == plan_id,
        timeout=120,
    )
    assert decision is not None, "Timeout aguardando decisão consolidada em plans.consensus"

    # Validar que Consensus Engine preservou correlation_id
    assert decision.get("correlation_id") == correlation_id, (
        f"Consensus Engine não preservou correlation_id. "
        f"Esperado: {correlation_id}, Recebido: {decision.get('correlation_id')}"
    )

    decision_id = decision.get("decision_id")

    # 4. Aguardar execution tickets no tópico execution.tickets
    tickets = await collect_avro_messages(
        avro_consumer,
        topic=test_kafka_topics.get("execution.tickets", "execution.tickets"),
        filter_fn=lambda msg: msg.get("decision_id") == decision_id or msg.get("plan_id") == plan_id,
        timeout=180,
        expected_count=1,
    )
    assert len(tickets) > 0, "Nenhum ticket encontrado em execution.tickets"

    # Validar que TODOS os tickets têm o mesmo correlation_id
    for ticket in tickets:
        assert ticket.get("correlation_id") == correlation_id, (
            f"Ticket {ticket.get('ticket_id')} não tem correlation_id correto. "
            f"Esperado: {correlation_id}, Recebido: {ticket.get('correlation_id')}"
        )

    # 5. Validar persistência no MongoDB (se coleções disponíveis)
    if test_mongodb_collections:
        # Verificar cognitive_ledger
        ledger_collection = test_mongodb_collections.get("cognitive_ledger")
        if ledger_collection:
            plan_doc = await ledger_collection.find_one({"plan_id": plan_id})
            if plan_doc:
                assert plan_doc.get("correlation_id") == correlation_id, (
                    f"MongoDB cognitive_ledger não tem correlation_id correto"
                )

        # Verificar consensus_decisions
        decisions_collection = test_mongodb_collections.get("consensus_decisions")
        if decisions_collection and decision_id:
            decision_doc = await decisions_collection.find_one({"decision_id": decision_id})
            if decision_doc:
                assert decision_doc.get("correlation_id") == correlation_id, (
                    f"MongoDB consensus_decisions não tem correlation_id correto"
                )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_correlation_id_auto_generation_when_missing(
    gateway_client,
    avro_consumer,
    test_kafka_topics,
):
    """
    Testa que correlation_id é gerado automaticamente quando ausente.
    """
    # 1. Enviar intent SEM correlation_id
    intent_request = {
        "text": "Criar API REST simples",
        "language": "pt-BR",
        "domain": "TECHNICAL",
        "priority": "NORMAL",
        # correlation_id ausente
    }

    response = await gateway_client.post("/intentions", json=intent_request)
    assert response.status_code == 200
    intent_data = response.json()
    intent_id = intent_data["intent_id"]

    # Gateway deve gerar correlation_id automaticamente
    assert "correlation_id" in intent_data, "Gateway não gerou correlation_id automaticamente"
    assert intent_data["correlation_id"] is not None, "correlation_id gerado é None"
    generated_correlation_id = intent_data["correlation_id"]

    # 2. Validar que correlation_id gerado é propagado
    plan = await wait_for_avro_message(
        avro_consumer,
        topic=test_kafka_topics.get("plans.ready", "plans.ready"),
        filter_fn=lambda msg: msg.get("intent_id") == intent_id,
        timeout=60,
    )
    assert plan is not None, "Timeout aguardando cognitive_plan"
    assert plan.get("correlation_id") == generated_correlation_id, (
        f"correlation_id gerado não foi propagado corretamente. "
        f"Esperado: {generated_correlation_id}, Recebido: {plan.get('correlation_id')}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_correlation_id_camelcase_to_snake_case_conversion(
    gateway_client,
    avro_consumer,
    test_kafka_topics,
):
    """
    Testa conversão de correlationId (camelCase) para correlation_id (snake_case).
    """
    correlation_id = str(uuid.uuid4())

    # Gateway publica com camelCase (correlationId)
    intent_request = {
        "text": "Criar API REST simples",
        "language": "pt-BR",
        "domain": "TECHNICAL",
        "priority": "NORMAL",
        "correlationId": correlation_id,  # camelCase
    }

    response = await gateway_client.post("/intentions", json=intent_request)
    assert response.status_code == 200
    intent_data = response.json()
    intent_id = intent_data["intent_id"]

    # STE deve aceitar ambos os formatos
    plan = await wait_for_avro_message(
        avro_consumer,
        topic=test_kafka_topics.get("plans.ready", "plans.ready"),
        filter_fn=lambda msg: msg.get("intent_id") == intent_id,
        timeout=60,
    )
    assert plan is not None, "Timeout aguardando cognitive_plan"

    # STE deve normalizar para snake_case
    assert plan.get("correlation_id") == correlation_id, (
        f"STE não converteu correlationId para correlation_id. "
        f"Esperado: {correlation_id}, Recebido: {plan.get('correlation_id')}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_correlation_id_persistence_in_mongodb(
    gateway_client,
    avro_consumer,
    test_kafka_topics,
    test_mongodb_collections,
):
    """
    Testa que correlation_id é persistido corretamente em todas as coleções MongoDB.
    """
    if not test_mongodb_collections:
        pytest.skip("Coleções MongoDB não disponíveis para teste")

    correlation_id = str(uuid.uuid4())

    intent_request = {
        "text": "Criar API REST simples para persistência",
        "language": "pt-BR",
        "domain": "TECHNICAL",
        "priority": "NORMAL",
        "correlation_id": correlation_id,
    }

    response = await gateway_client.post("/intentions", json=intent_request)
    assert response.status_code == 200
    intent_data = response.json()
    intent_id = intent_data["intent_id"]

    # Aguardar processamento completo
    plan = await wait_for_avro_message(
        avro_consumer,
        topic=test_kafka_topics.get("plans.ready", "plans.ready"),
        filter_fn=lambda msg: msg.get("intent_id") == intent_id,
        timeout=60,
    )
    assert plan is not None

    plan_id = plan["plan_id"]

    # Aguardar tempo para persistência
    await asyncio.sleep(5)

    # Verificar cognitive_ledger
    ledger_collection = test_mongodb_collections.get("cognitive_ledger")
    if ledger_collection:
        plan_doc = await ledger_collection.find_one({"plan_id": plan_id})
        assert plan_doc is not None, f"Plano {plan_id} não encontrado em cognitive_ledger"
        assert plan_doc.get("correlation_id") == correlation_id, (
            f"correlation_id incorreto em cognitive_ledger"
        )
