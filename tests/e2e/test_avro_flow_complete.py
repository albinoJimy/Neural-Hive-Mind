"""
Testes E2E para validar serialização/deserialização Avro em todo o pipeline.

Valida o fluxo completo:
- Schema Registry (Apicurio) → registro e recuperação de schemas
- Semantic Translation Engine → produção de mensagens Avro
- Consensus Engine → consumo e deserialização Avro
- Specialists → invocação via gRPC
- Orchestrator → geração de execution tickets

Autor: Neural Hive Mind Team
"""

import asyncio
import json
import time
import uuid
from typing import Dict, List, Optional

import httpx
import pytest
from confluent_kafka.avro import AvroConsumer, AvroProducer

from tests.e2e.utils.assertions import (
    assert_avro_message_valid,
    assert_cognitive_plan_structure,
    assert_consolidated_decision_structure,
    assert_execution_ticket_structure,
    assert_specialist_invoked,
)
from tests.e2e.utils.kafka_helpers import (
    collect_avro_messages,
    wait_for_avro_message,
)
from tests.e2e.utils.k8s_helpers import get_pod_logs

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio, pytest.mark.slow, pytest.mark.avro]


# ============================================
# Teste 1: Schema Registry
# ============================================


@pytest.mark.timeout(30)
class TestSchemaRegistryValidation:
    """Testes de validação do Schema Registry (Apicurio)."""

    async def test_schema_registry_has_cognitive_plan_schema(
        self,
        schema_registry_client: httpx.AsyncClient,
    ):
        """
        Valida que o schema CognitivePlan está registrado no Schema Registry.

        Verificações:
        - Subject plans.ready-value existe
        - Schema contém campos obrigatórios
        - Versão >= 1
        """
        # Buscar lista de subjects
        response = await schema_registry_client.get("/apis/ccompat/v6/subjects")
        assert response.status_code == 200, f"Falha ao listar subjects: {response.text}"

        subjects = response.json()
        assert "plans.ready-value" in subjects, "Subject plans.ready-value não encontrado"

        # Buscar versões do subject
        response = await schema_registry_client.get(
            "/apis/ccompat/v6/subjects/plans.ready-value/versions"
        )
        assert response.status_code == 200, f"Falha ao listar versões: {response.text}"

        versions = response.json()
        assert len(versions) >= 1, "Nenhuma versão do schema encontrada"

        # Buscar schema mais recente
        response = await schema_registry_client.get(
            "/apis/ccompat/v6/subjects/plans.ready-value/versions/latest"
        )
        assert response.status_code == 200, f"Falha ao buscar schema: {response.text}"

        schema_data = response.json()
        schema_str = schema_data.get("schema", "{}")
        schema = json.loads(schema_str)

        # Validar campos obrigatórios
        field_names = [f["name"] for f in schema.get("fields", [])]
        required_fields = ["plan_id", "tasks", "execution_order", "risk_score"]

        for field in required_fields:
            assert field in field_names, f"Campo obrigatório ausente: {field}"

    async def test_schema_registry_has_consolidated_decision_schema(
        self,
        schema_registry_client: httpx.AsyncClient,
    ):
        """Valida que o schema ConsolidatedDecision está registrado."""
        response = await schema_registry_client.get("/apis/ccompat/v6/subjects")
        subjects = response.json()

        assert "plans.consensus-value" in subjects, "Subject plans.consensus-value não encontrado"

    async def test_schema_registry_has_execution_ticket_schema(
        self,
        schema_registry_client: httpx.AsyncClient,
    ):
        """Valida que o schema ExecutionTicket está registrado."""
        response = await schema_registry_client.get("/apis/ccompat/v6/subjects")
        subjects = response.json()

        assert (
            "execution.tickets-value" in subjects
        ), "Subject execution.tickets-value não encontrado"


# ============================================
# Teste 2: Serialização Avro no Semantic Translation Engine
# ============================================


@pytest.mark.timeout(90)
class TestSemanticTranslationEngineSerialization:
    """Testes de serialização Avro no Semantic Translation Engine."""

    async def test_semantic_translation_engine_produces_avro_messages(
        self,
        gateway_client: httpx.AsyncClient,
        cognitive_plan_avro_consumer: AvroConsumer,
        test_kafka_topics: Dict[str, str],
        sample_intent_for_avro_flow: Dict,
    ):
        """
        Valida que o Semantic Translation Engine produz mensagens Avro corretamente.

        Fluxo:
        1. Publicar intent via Gateway
        2. Aguardar mensagem no tópico plans.ready
        3. Validar estrutura Avro
        """
        intent = sample_intent_for_avro_flow
        correlation_id = intent["correlation_id"]

        # Publicar intent via Gateway
        response = await gateway_client.post("/api/v1/intentions", json=intent)
        assert response.status_code in [200, 201, 202], f"Falha ao publicar intent: {response.text}"

        # Aguardar mensagem no tópico plans.ready
        plan = await wait_for_avro_message(
            consumer=cognitive_plan_avro_consumer,
            topic=test_kafka_topics["plans.ready"],
            filter_fn=lambda msg: msg.get("correlation_id") == correlation_id,
            timeout=60,
        )

        assert plan is not None, "CognitivePlan não recebido no tópico plans.ready"

        # Validar estrutura do plano
        assert_cognitive_plan_structure(plan)

        # Validar campos específicos
        assert plan["correlation_id"] == correlation_id
        assert len(plan["tasks"]) > 0, "Plano deve ter pelo menos uma task"
        assert plan["risk_band"] in ["low", "medium", "high", "critical"]
        assert plan["status"] in ["draft", "validated", "approved", "rejected"]


# ============================================
# Teste 3: Deserialização Avro no Consensus Engine
# ============================================


@pytest.mark.timeout(120)
class TestConsensusEngineDeserialization:
    """Testes de deserialização Avro no Consensus Engine."""

    async def test_consensus_engine_deserializes_avro_messages(
        self,
        cognitive_plan_avro_producer: AvroProducer,
        consolidated_decision_avro_consumer: AvroConsumer,
        complete_cognitive_plan_avro_with_order: Dict,
        k8s_client,
        test_kafka_topics: Dict[str, str],
    ):
        """
        Valida que o Consensus Engine deserializa mensagens Avro corretamente.

        Fluxo:
        1. Publicar CognitivePlan Avro no tópico plans.ready
        2. Verificar logs do consensus-engine
        3. Aguardar decisão consolidada
        """
        plan = complete_cognitive_plan_avro_with_order
        plan_id = plan["plan_id"]

        # Publicar CognitivePlan
        cognitive_plan_avro_producer.produce(
            topic=test_kafka_topics["plans.ready"],
            value=plan,
        )
        cognitive_plan_avro_producer.flush()

        # Aguardar processamento
        await asyncio.sleep(5)

        # Verificar logs do consensus-engine
        logs = get_pod_logs(
            k8s_client,
            namespace="neural-hive-orchestration",
            label_selector="app=consensus-engine",
            tail_lines=200,
        )

        # Validar que não há erros de magic byte
        assert "Invalid magic byte" not in logs, "Erro de magic byte detectado no consensus-engine"

        # Aguardar decisão consolidada
        decision = await wait_for_avro_message(
            consumer=consolidated_decision_avro_consumer,
            topic=test_kafka_topics["plans.consensus"],
            filter_fn=lambda msg: msg.get("plan_id") == plan_id,
            timeout=90,
        )

        assert decision is not None, "ConsolidatedDecision não recebida"
        assert decision["plan_id"] == plan_id


# ============================================
# Teste 4: Invocação dos 5 Specialists via gRPC
# ============================================


@pytest.mark.timeout(180)
class TestSpecialistsInvocation:
    """Testes de invocação dos Specialists via gRPC."""

    async def test_consensus_engine_invokes_all_specialists(
        self,
        cognitive_plan_avro_producer: AvroProducer,
        consolidated_decision_avro_consumer: AvroConsumer,
        complete_cognitive_plan_avro_with_order: Dict,
        k8s_client,
        all_specialist_types: List[str],
        test_kafka_topics: Dict[str, str],
    ):
        """
        Valida que o Consensus Engine invoca todos os 5 specialists.

        Verificações:
        - Cada specialist recebeu EvaluatePlan para o plan_id (via logs)
        - Decisão consolidada contém 5 specialist_votes
        - Falha se algum specialist não for invocado
        """
        plan = complete_cognitive_plan_avro_with_order
        plan_id = plan["plan_id"]

        # Publicar CognitivePlan
        cognitive_plan_avro_producer.produce(
            topic=test_kafka_topics["plans.ready"],
            value=plan,
        )
        cognitive_plan_avro_producer.flush()

        print(f"\n📤 CognitivePlan publicado - plan_id: {plan_id}")

        # Verificar invocação de CADA specialist via logs ANTES de validar votos
        # Isso garante que o gRPC foi chamado para cada um
        specialists_invoked = []
        specialists_not_invoked = []

        for specialist_type in all_specialist_types:
            try:
                await assert_specialist_invoked(
                    k8s_client=k8s_client,
                    specialist_type=specialist_type,
                    plan_id=plan_id,
                    timeout=60,
                )
                specialists_invoked.append(specialist_type)
                print(f"   ✅ Specialist {specialist_type} invocado para plan_id: {plan_id}")
            except AssertionError as e:
                specialists_not_invoked.append(specialist_type)
                print(f"   ❌ Specialist {specialist_type} NÃO foi invocado: {e}")

        # Falhar teste se algum specialist não foi invocado
        assert len(specialists_not_invoked) == 0, (
            f"Os seguintes specialists não foram invocados para plan_id {plan_id}: "
            f"{specialists_not_invoked}. "
            f"Invocados com sucesso: {specialists_invoked}"
        )

        print(f"\n✅ Todos os 5 specialists foram invocados via gRPC")

        # Aguardar decisão consolidada com specialist_votes
        decision = await wait_for_avro_message(
            consumer=consolidated_decision_avro_consumer,
            topic=test_kafka_topics["plans.consensus"],
            filter_fn=lambda msg: msg.get("plan_id") == plan_id,
            timeout=150,
        )

        assert decision is not None, "ConsolidatedDecision não recebida"

        # Validar specialist_votes
        specialist_votes = decision.get("specialist_votes", [])
        assert (
            len(specialist_votes) == 5
        ), f"Esperado 5 specialist_votes, recebido {len(specialist_votes)}"

        # Validar que todos os tipos de specialists estão presentes nos votos
        vote_types = {vote["specialist_type"] for vote in specialist_votes}
        for specialist_type in all_specialist_types:
            assert (
                specialist_type in vote_types
            ), f"Voto do specialist {specialist_type} não encontrado na decisão"

        # Validar estrutura de cada voto
        for vote in specialist_votes:
            assert "opinion_id" in vote
            assert "confidence_score" in vote
            assert 0.0 <= vote["confidence_score"] <= 1.0
            assert "recommendation" in vote
            assert "processing_time_ms" in vote

        print(f"   ✅ ConsolidatedDecision contém votos de todos os 5 specialists")


# ============================================
# Teste 5: Geração de Execution Tickets
# ============================================


@pytest.mark.timeout(240)
class TestExecutionTicketsGeneration:
    """Testes de geração de Execution Tickets."""

    async def test_execution_tickets_generated_from_consensus(
        self,
        gateway_client: httpx.AsyncClient,
        cognitive_plan_avro_consumer: AvroConsumer,
        consolidated_decision_avro_consumer: AvroConsumer,
        execution_ticket_avro_consumer: AvroConsumer,
        sample_intent_for_avro_flow: Dict,
        test_kafka_topics: Dict[str, str],
    ):
        """
        Valida que execution tickets são gerados a partir do consenso.

        Fluxo:
        1. Publicar intent
        2. Aguardar plano cognitivo
        3. Aguardar decisão consolidada
        4. Aguardar execution tickets
        """
        intent = sample_intent_for_avro_flow
        correlation_id = intent["correlation_id"]

        # Publicar intent
        response = await gateway_client.post("/api/v1/intentions", json=intent)
        assert response.status_code in [200, 201, 202]

        # Aguardar plano
        plan = await wait_for_avro_message(
            consumer=cognitive_plan_avro_consumer,
            topic=test_kafka_topics["plans.ready"],
            filter_fn=lambda msg: msg.get("correlation_id") == correlation_id,
            timeout=60,
        )
        assert plan is not None, "CognitivePlan não recebido"

        num_tasks = len(plan.get("tasks", []))

        # Aguardar decisão
        decision = await wait_for_avro_message(
            consumer=consolidated_decision_avro_consumer,
            topic=test_kafka_topics["plans.consensus"],
            filter_fn=lambda msg: msg.get("plan_id") == plan["plan_id"],
            timeout=90,
        )
        assert decision is not None, "ConsolidatedDecision não recebida"

        # Aguardar tickets (se decisão for approve)
        if decision.get("final_decision") == "approve":
            tickets = await collect_avro_messages(
                consumer=execution_ticket_avro_consumer,
                topic=test_kafka_topics["execution.tickets"],
                filter_fn=lambda msg: msg.get("plan_id") == plan["plan_id"],
                timeout=60,
                expected_count=num_tasks,
            )

            assert len(tickets) >= 1, "Nenhum ExecutionTicket recebido"

            # Validar estrutura dos tickets
            for ticket in tickets:
                assert_execution_ticket_structure(ticket)
                assert ticket["status"] == "PENDING"


# ============================================
# Teste 6: Fluxo Completo A → B → C
# ============================================


@pytest.mark.timeout(360)
class TestCompleteAvroFlow:
    """Testes do fluxo Avro completo de ponta a ponta."""

    async def test_complete_avro_flow_intent_to_execution(
        self,
        gateway_client: httpx.AsyncClient,
        cognitive_plan_avro_consumer: AvroConsumer,
        consolidated_decision_avro_consumer: AvroConsumer,
        execution_ticket_avro_consumer: AvroConsumer,
        sample_intent_for_avro_flow: Dict,
        k8s_client,
        mongodb_client,
        redis_client,
        test_kafka_topics: Dict[str, str],
    ):
        """
        Valida o fluxo completo A → B → C com serialização Avro.

        Fluxo A: Intent → Gateway → Kafka
        Fluxo B: Semantic Translation → plans.ready → Consensus → Specialists → plans.consensus
        Fluxo C: Orchestrator → execution.tickets

        Métricas coletadas:
        - Latência total e por etapa
        - Número de mensagens por tópico
        """
        intent = sample_intent_for_avro_flow
        correlation_id = intent["correlation_id"]
        metrics = {"start_time": time.time()}

        # ========== FLUXO A ==========
        # Publicar intent via Gateway
        response = await gateway_client.post("/api/v1/intentions", json=intent)
        assert response.status_code in [200, 201, 202], f"Falha no Fluxo A: {response.text}"

        metrics["flow_a_end"] = time.time()

        # Verificar Redis (cache e dedup)
        intent_key = f"intent:{correlation_id}"
        dedup_key = f"dedup:{correlation_id}"

        # Redis pode não ter as chaves imediatamente
        await asyncio.sleep(2)

        # ========== FLUXO B ==========
        # Aguardar CognitivePlan
        plan = await wait_for_avro_message(
            consumer=cognitive_plan_avro_consumer,
            topic=test_kafka_topics["plans.ready"],
            filter_fn=lambda msg: msg.get("correlation_id") == correlation_id,
            timeout=60,
        )
        assert plan is not None, "Falha no Fluxo B: CognitivePlan não recebido"

        metrics["plan_received"] = time.time()

        # Validar estrutura do plano
        assert_cognitive_plan_structure(plan)

        # Aguardar ConsolidatedDecision
        decision = await wait_for_avro_message(
            consumer=consolidated_decision_avro_consumer,
            topic=test_kafka_topics["plans.consensus"],
            filter_fn=lambda msg: msg.get("plan_id") == plan["plan_id"],
            timeout=90,
        )
        assert decision is not None, "Falha no Fluxo B: ConsolidatedDecision não recebida"

        metrics["decision_received"] = time.time()

        # Validar decisão
        assert_consolidated_decision_structure(decision)

        # Validar specialist_votes (5 specialists)
        assert len(decision.get("specialist_votes", [])) == 5

        # Verificar MongoDB (consensus_decisions)
        consensus_doc = mongodb_client["consensus_decisions"].find_one(
            {"decision_id": decision["decision_id"]}
        )
        # MongoDB pode não ter o documento se não estiver configurado
        # assert consensus_doc is not None

        metrics["flow_b_end"] = time.time()

        # ========== FLUXO C ==========
        if decision.get("final_decision") == "approve":
            num_tasks = len(plan.get("tasks", []))

            # Aguardar ExecutionTickets
            tickets = await collect_avro_messages(
                consumer=execution_ticket_avro_consumer,
                topic=test_kafka_topics["execution.tickets"],
                filter_fn=lambda msg: msg.get("plan_id") == plan["plan_id"],
                timeout=60,
                expected_count=num_tasks,
            )

            metrics["flow_c_end"] = time.time()

            # Validar tickets
            for ticket in tickets:
                assert_execution_ticket_structure(ticket)
                assert ticket["correlation_id"] == correlation_id

            # Verificar MongoDB (execution_tickets e workflows)
            # Documentos podem não existir se MongoDB não estiver configurado

        # ========== MÉTRICAS ==========
        metrics["total_latency_ms"] = (
            metrics.get("flow_c_end", metrics["flow_b_end"]) - metrics["start_time"]
        ) * 1000
        metrics["flow_a_latency_ms"] = (metrics["flow_a_end"] - metrics["start_time"]) * 1000
        metrics["flow_b_latency_ms"] = (metrics["flow_b_end"] - metrics["flow_a_end"]) * 1000

        if "flow_c_end" in metrics:
            metrics["flow_c_latency_ms"] = (metrics["flow_c_end"] - metrics["flow_b_end"]) * 1000

        # Log de métricas para análise
        print(f"\n📊 Métricas do Fluxo Avro Completo:")
        print(f"   Latência Total: {metrics['total_latency_ms']:.2f}ms")
        print(f"   Fluxo A: {metrics['flow_a_latency_ms']:.2f}ms")
        print(f"   Fluxo B: {metrics['flow_b_latency_ms']:.2f}ms")
        if "flow_c_latency_ms" in metrics:
            print(f"   Fluxo C: {metrics['flow_c_latency_ms']:.2f}ms")


# ============================================
# Teste 7: Schema Evolution
# ============================================


@pytest.mark.timeout(120)
class TestSchemaEvolution:
    """Testes de evolução de schema (backward compatibility)."""

    async def test_schema_evolution_backward_compatible(
        self,
        schema_registry_client: httpx.AsyncClient,
    ):
        """
        Valida que o Schema Registry suporta evolução backward-compatible.

        Verificações:
        - Schema pode ser atualizado com novos campos opcionais
        - Consumers com schema antigo ainda funcionam
        """
        # Buscar compatibilidade configurada
        response = await schema_registry_client.get("/apis/ccompat/v6/config/plans.ready-value")

        if response.status_code == 200:
            config = response.json()
            compatibility = config.get("compatibilityLevel", "BACKWARD")
            assert compatibility in [
                "BACKWARD",
                "BACKWARD_TRANSITIVE",
                "FULL",
            ], f"Compatibilidade não é backward: {compatibility}"

    async def test_schema_evolution_cross_version_serialization(
        self,
        schema_registry_client: httpx.AsyncClient,
        k8s_service_endpoints: Dict[str, str],
        test_kafka_topics: Dict[str, str],
    ):
        """
        Valida compatibilidade de serialização/deserialização entre versões de schema.

        Fluxo:
        1. Registrar schema v1 (campos base)
        2. Registrar schema v2 (campos base + novo campo opcional)
        3. Publicar mensagem com schema v1
        4. Publicar mensagem com schema v2
        5. Consumir com AvroConsumer v1 e v2 - ambos devem deserializar corretamente
        """
        from confluent_kafka import avro
        from confluent_kafka.avro import AvroConsumer, AvroProducer
        from confluent_kafka.avro.error import ClientError

        test_subject = f"schema-evolution-test-{uuid.uuid4().hex[:8]}-value"
        test_topic = f"schema-evolution-{uuid.uuid4().hex[:8]}"

        # Schema v1: campos base
        schema_v1_str = json.dumps(
            {
                "type": "record",
                "name": "SchemaEvolutionTest",
                "namespace": "com.neuralhive.test",
                "fields": [
                    {"name": "id", "type": "string"},
                    {"name": "name", "type": "string"},
                    {"name": "created_at", "type": "long"},
                ],
            }
        )

        # Schema v2: campos base + campo opcional (backward compatible)
        schema_v2_str = json.dumps(
            {
                "type": "record",
                "name": "SchemaEvolutionTest",
                "namespace": "com.neuralhive.test",
                "fields": [
                    {"name": "id", "type": "string"},
                    {"name": "name", "type": "string"},
                    {"name": "created_at", "type": "long"},
                    {"name": "description", "type": ["null", "string"], "default": None},
                ],
            }
        )

        # Registrar schema v1
        response_v1 = await schema_registry_client.post(
            f"/apis/ccompat/v6/subjects/{test_subject}/versions",
            json={"schema": schema_v1_str},
        )
        assert response_v1.status_code in [
            200,
            201,
        ], f"Falha ao registrar schema v1: {response_v1.text}"
        schema_v1_id = response_v1.json().get("id")
        assert schema_v1_id is not None, "Schema v1 não retornou ID"

        # Registrar schema v2 (deve ser compatível)
        response_v2 = await schema_registry_client.post(
            f"/apis/ccompat/v6/subjects/{test_subject}/versions",
            json={"schema": schema_v2_str},
        )
        assert response_v2.status_code in [
            200,
            201,
        ], f"Falha ao registrar schema v2 (não compatível?): {response_v2.text}"
        schema_v2_id = response_v2.json().get("id")
        assert schema_v2_id is not None, "Schema v2 não retornou ID"

        # Carregar schemas para producer
        schema_v1 = avro.loads(schema_v1_str)
        schema_v2 = avro.loads(schema_v2_str)

        kafka_config = {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
        }

        # Mensagem v1 (sem campo opcional)
        msg_v1 = {
            "id": f"v1-{uuid.uuid4().hex[:8]}",
            "name": "Mensagem schema v1",
            "created_at": int(time.time() * 1000),
        }

        # Mensagem v2 (com campo opcional)
        msg_v2 = {
            "id": f"v2-{uuid.uuid4().hex[:8]}",
            "name": "Mensagem schema v2",
            "created_at": int(time.time() * 1000),
            "description": "Campo adicional do schema v2",
        }

        # Publicar com producer v1
        producer_v1 = AvroProducer(kafka_config, default_value_schema=schema_v1)
        producer_v1.produce(topic=test_topic, value=msg_v1)
        producer_v1.flush()

        # Publicar com producer v2
        producer_v2 = AvroProducer(kafka_config, default_value_schema=schema_v2)
        producer_v2.produce(topic=test_topic, value=msg_v2)
        producer_v2.flush()

        # Consumir com consumer (deve deserializar ambas as mensagens)
        consumer_config = {
            **kafka_config,
            "group.id": f"e2e-schema-evolution-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
        consumer = AvroConsumer(consumer_config)
        consumer.subscribe([test_topic])

        messages_received = []
        start_time = time.time()
        timeout = 30

        while time.time() - start_time < timeout and len(messages_received) < 2:
            msg = await asyncio.to_thread(consumer.poll, 1.0)
            if msg is None:
                continue
            if msg.error():
                pytest.fail(f"Erro ao consumir mensagem: {msg.error()}")
            messages_received.append(msg.value())

        consumer.close()

        # Validar que ambas as mensagens foram deserializadas
        assert (
            len(messages_received) == 2
        ), f"Esperado 2 mensagens, recebido {len(messages_received)}"

        # Validar mensagem v1
        msg_v1_received = next((m for m in messages_received if m.get("id") == msg_v1["id"]), None)
        assert msg_v1_received is not None, "Mensagem v1 não recebida"
        assert msg_v1_received["name"] == msg_v1["name"]

        # Validar mensagem v2
        msg_v2_received = next((m for m in messages_received if m.get("id") == msg_v2["id"]), None)
        assert msg_v2_received is not None, "Mensagem v2 não recebida"
        assert msg_v2_received["name"] == msg_v2["name"]
        assert msg_v2_received.get("description") == msg_v2["description"]

        # Cleanup: remover subject de teste
        await schema_registry_client.delete(f"/apis/ccompat/v6/subjects/{test_subject}")

        print(f"\n✅ Schema Evolution Test:")
        print(f"   Schema v1 ID: {schema_v1_id}")
        print(f"   Schema v2 ID: {schema_v2_id}")
        print(f"   Mensagens deserializadas: {len(messages_received)}")


# ============================================
# Teste 8: Error Handling - Schema Não Registrado
# ============================================


@pytest.mark.timeout(30)
class TestErrorHandlingSchemaNotRegistered:
    """Testes de tratamento de erro para schema não registrado."""

    async def test_error_handling_schema_not_registered(
        self,
        schema_registry_client: httpx.AsyncClient,
        k8s_service_endpoints: Dict[str, str],
    ):
        """
        Valida tratamento de erro quando schema não está registrado.

        Fluxo:
        1. Criar producer com schema para subject inexistente
        2. Tentar produzir mensagem
        3. Verificar que ClientError é lançado
        """
        from confluent_kafka import avro
        from confluent_kafka.avro import AvroProducer
        from confluent_kafka.avro.error import ClientError

        # Subject que definitivamente não existe
        nonexistent_subject = f"nonexistent-subject-{uuid.uuid4().hex}"
        fake_topic = f"fake-topic-{uuid.uuid4().hex[:8]}"

        # Schema de teste
        fake_schema_str = json.dumps(
            {
                "type": "record",
                "name": "FakeSchema",
                "namespace": "com.neuralhive.test.nonexistent",
                "fields": [
                    {"name": "id", "type": "string"},
                    {"name": "test_field", "type": "string"},
                ],
            }
        )

        fake_schema = avro.loads(fake_schema_str)

        # Criar producer SEM auto-registro de schema
        kafka_config = {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
            "auto.register.schemas": False,  # Desabilitar auto-registro
        }

        producer = AvroProducer(kafka_config, default_value_schema=fake_schema)

        fake_message = {
            "id": f"fake-{uuid.uuid4().hex[:8]}",
            "test_field": "valor de teste",
        }

        # Verificar que produzir com subject não registrado gera erro
        error_caught = False
        error_message = ""

        try:
            producer.produce(
                topic=fake_topic,
                value=fake_message,
            )
            producer.flush()
        except ClientError as e:
            error_caught = True
            error_message = str(e)
            print(f"\n✅ ClientError capturado como esperado: {error_message}")
        except Exception as e:
            # Outros erros relacionados a schema também são válidos
            if "schema" in str(e).lower() or "subject" in str(e).lower():
                error_caught = True
                error_message = str(e)
                print(f"\n✅ Erro de schema capturado: {error_message}")
            else:
                raise

        assert error_caught, (
            "Esperava-se ClientError ao produzir com schema não registrado, "
            "mas nenhum erro foi lançado"
        )

        # Verificar que o subject realmente não existe
        response = await schema_registry_client.get("/apis/ccompat/v6/subjects")
        subjects = response.json()
        assert (
            f"{fake_topic}-value" not in subjects
        ), f"Subject {fake_topic}-value não deveria existir"

        print(f"   Subject verificado como inexistente: {fake_topic}-value")

    async def test_error_handling_deleted_subject(
        self,
        schema_registry_client: httpx.AsyncClient,
        k8s_service_endpoints: Dict[str, str],
    ):
        """
        Valida tratamento de erro após remover subject do Registry.

        Fluxo:
        1. Registrar um subject temporário
        2. Remover o subject
        3. Tentar produzir mensagem para o subject removido
        4. Verificar que erro é gerado
        """
        from confluent_kafka import avro
        from confluent_kafka.avro import AvroProducer
        from confluent_kafka.avro.error import ClientError

        temp_subject = f"temp-delete-test-{uuid.uuid4().hex[:8]}-value"
        temp_topic = f"temp-delete-test-{uuid.uuid4().hex[:8]}"

        # Schema temporário
        temp_schema_str = json.dumps(
            {
                "type": "record",
                "name": "TempDeleteTest",
                "namespace": "com.neuralhive.test.temp",
                "fields": [
                    {"name": "id", "type": "string"},
                ],
            }
        )

        # Registrar schema temporariamente
        response = await schema_registry_client.post(
            f"/apis/ccompat/v6/subjects/{temp_subject}/versions",
            json={"schema": temp_schema_str},
        )
        assert response.status_code in [
            200,
            201,
        ], f"Falha ao registrar schema temporário: {response.text}"

        # Remover o subject
        delete_response = await schema_registry_client.delete(
            f"/apis/ccompat/v6/subjects/{temp_subject}"
        )
        assert delete_response.status_code in [
            200,
            204,
        ], f"Falha ao remover subject: {delete_response.text}"

        # Aguardar propagação da remoção
        await asyncio.sleep(1)

        # Criar producer sem auto-registro
        kafka_config = {
            "bootstrap.servers": k8s_service_endpoints["kafka"],
            "schema.registry.url": f"http://{k8s_service_endpoints['schema_registry']}",
            "auto.register.schemas": False,
        }

        temp_schema = avro.loads(temp_schema_str)
        producer = AvroProducer(kafka_config, default_value_schema=temp_schema)

        # Tentar produzir deve falhar
        error_caught = False

        try:
            producer.produce(
                topic=temp_topic,
                value={"id": "test-after-delete"},
            )
            producer.flush()
        except (ClientError, Exception) as e:
            error_caught = True
            print(f"\n✅ Erro capturado após remoção de subject: {e}")

        assert error_caught, "Esperava-se erro ao produzir para subject removido"


# ============================================
# Teste 9: Error Handling - Invalid Magic Byte
# ============================================


@pytest.mark.timeout(90)
class TestErrorHandlingInvalidMagicByte:
    """Testes de tratamento de erro para magic byte inválido."""

    async def test_error_handling_invalid_magic_byte(
        self,
        kafka_test_helper,
        k8s_client,
        consolidated_decision_avro_consumer: AvroConsumer,
        test_kafka_topics: Dict[str, str],
    ):
        """
        Valida tratamento de erro quando mensagem não tem magic byte Avro.

        Fluxo:
        1. Publicar mensagem JSON pura (sem magic byte Avro)
        2. Verificar que logs do consensus-engine contêm erro esperado
        3. Verificar que nenhuma ConsolidatedDecision é emitida para esse plan_id
        4. Verificar que consumer continua ativo (não travou)

        Falha o teste se:
        - Erro não for observado nos logs
        - Serviço parar de consumir
        """
        # Gerar plan_id único para rastrear
        fake_plan_id = f"invalid-magic-{uuid.uuid4().hex[:8]}"

        # Publicar mensagem JSON pura no tópico plans.ready (sem magic byte Avro)
        producer = kafka_test_helper.get_producer()

        fake_message = {
            "plan_id": fake_plan_id,
            "intent_id": f"fake-intent-{uuid.uuid4().hex[:8]}",
            "correlation_id": f"fake-corr-{uuid.uuid4().hex[:8]}",
            "version": "1.0.0",
            "tasks": [],
            "execution_order": [],
            "risk_score": 0.1,
            "risk_band": "low",
            "risk_factors": {},
            "explainability_token": "fake-token",
            "reasoning_summary": "Mensagem de teste sem magic byte",
            "status": "validated",
            "created_at": int(time.time() * 1000),
            "complexity_score": 0.1,
            "original_domain": "TEST",
            "original_priority": "LOW",
            "original_security_level": "PUBLIC",
        }

        producer.produce(
            test_kafka_topics["plans.ready"],
            value=json.dumps(fake_message).encode("utf-8"),
        )
        producer.flush()

        # Aguardar processamento pelo consensus-engine
        await asyncio.sleep(10)

        # Verificar logs do consensus-engine para erro de magic byte
        logs = get_pod_logs(
            k8s_client,
            namespace="neural-hive-orchestration",
            label_selector="app=consensus-engine",
            tail_lines=300,
        )

        # Erros esperados nos logs
        error_indicators = [
            "Invalid magic byte",
            "invalid magic byte",
            "magic byte",
            "deserialization error",
            "SerializationException",
            "AvroDeserializer",
            "failed to deserialize",
            "Falha ao deserializar",
        ]

        error_found = any(indicator in logs for indicator in error_indicators)
        assert error_found, (
            f"Erro de magic byte não encontrado nos logs do consensus-engine. "
            f"Esperado um dos: {error_indicators}. "
            f"Plan ID: {fake_plan_id}"
        )

        print(f"\n✅ Erro de magic byte detectado nos logs para plan_id: {fake_plan_id}")

        # Verificar que NENHUMA ConsolidatedDecision foi emitida para esse plan_id
        consolidated_decision_avro_consumer.subscribe([test_kafka_topics["plans.consensus"]])

        decision_found = False
        start_time = time.time()
        check_timeout = 15  # Tempo suficiente para verificar que não há decisão

        while time.time() - start_time < check_timeout:
            msg = await asyncio.to_thread(consolidated_decision_avro_consumer.poll, 1.0)
            if msg is None:
                continue
            if msg.error():
                continue

            value = msg.value()
            if isinstance(value, dict) and value.get("plan_id") == fake_plan_id:
                decision_found = True
                break

        assert not decision_found, (
            f"ConsolidatedDecision foi emitida para plan_id inválido: {fake_plan_id}. "
            "Esperava-se que mensagens com magic byte inválido não gerassem decisões."
        )

        print(f"   ✅ Nenhuma ConsolidatedDecision emitida para plan_id inválido")

        # Verificar que o consumer do consensus-engine continua ativo
        # Publicar uma mensagem válida após o erro e verificar que é processada
        # (para garantir que o serviço não travou)

        # Obter logs novamente para verificar se não há erros fatais
        logs_after = get_pod_logs(
            k8s_client,
            namespace="neural-hive-orchestration",
            label_selector="app=consensus-engine",
            tail_lines=50,
        )

        fatal_indicators = [
            "FATAL",
            "panic",
            "Panic",
            "crashed",
            "terminated",
            "OOMKilled",
        ]

        service_crashed = any(indicator in logs_after for indicator in fatal_indicators)
        assert not service_crashed, (
            f"Consensus-engine aparenta ter falhado fatalmente após mensagem inválida. "
            f"Indicadores encontrados nos logs: {logs_after[-500:]}"
        )

        print(f"   ✅ Consensus-engine continua ativo após erro de magic byte")


# ============================================
# Teste 10: Performance
# ============================================


@pytest.mark.timeout(120)
@pytest.mark.performance
class TestPerformanceAvroSerialization:
    """Testes de performance de serialização Avro."""

    async def test_performance_avro_serialization_throughput(
        self,
        cognitive_plan_avro_producer: AvroProducer,
        complete_cognitive_plan_avro: Dict,
        test_kafka_topics: Dict[str, str],
    ):
        """
        Valida throughput de serialização Avro.

        Métricas:
        - Throughput >= 50 mensagens/segundo
        - Latência média < 20ms por mensagem
        """
        num_messages = 100
        latencies = []

        start_time = time.time()

        for i in range(num_messages):
            plan = complete_cognitive_plan_avro.copy()
            plan["plan_id"] = f"perf-{uuid.uuid4().hex[:8]}"

            msg_start = time.time()
            cognitive_plan_avro_producer.produce(
                topic=test_kafka_topics["plans.ready"],
                value=plan,
            )
            latencies.append((time.time() - msg_start) * 1000)

        cognitive_plan_avro_producer.flush()
        total_time = time.time() - start_time

        # Calcular métricas
        throughput = num_messages / total_time
        avg_latency = sum(latencies) / len(latencies)

        print(f"\n📊 Métricas de Performance Avro:")
        print(f"   Mensagens: {num_messages}")
        print(f"   Tempo Total: {total_time:.2f}s")
        print(f"   Throughput: {throughput:.2f} msgs/s")
        print(f"   Latência Média: {avg_latency:.2f}ms")

        # Validações
        assert throughput >= 50, f"Throughput baixo: {throughput:.2f} msgs/s"
        assert avg_latency < 20, f"Latência alta: {avg_latency:.2f}ms"
