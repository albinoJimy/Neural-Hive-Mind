"""
Testes para o pacote test_helpers.

Estes testes validam que as factories, asserts e mocks funcionam corretamente.
"""

import pytest

# Import direto para evitar conflitos de nomes
from tests.test_helpers.factories import (
    TestCognitivePlanFactory,
    TestSpecialistOpinionFactory,
    TestConsolidatedDecisionFactory,
    TestExecutionTicketFactory,
    TestSpecialistFeedbackFactory,
    TestTaskFactory,
    create_test_plan,
    create_test_opinion,
    create_test_decision,
    create_test_ticket,
    create_test_feedback,
)

from tests.test_helpers.asserts import (
    assert_valid_plan_id,
    assert_valid_confidence,
    assert_valid_domain,
    assert_valid_risk_band,
    assert_valid_specialist_id,
    assert_valid_status,
    assert_tasks_dependent,
    assert_no_circular_dependencies,
    assert_cognitive_plan,
    assert_specialist_opinion,
    assert_consolidated_decision,
    assert_approve_reject_balance,
)

from tests.test_helpers.mocks import (
    MockKafkaProducer,
    MockKafkaConsumer,
    MockKafkaMessage,
    MockMongoDBClient,
    MockRedisClient,
    MockTemporalClient,
)


class TestCognitivePlanFactoryTests:
    """Testes para TestCognitivePlanFactory."""

    def test_create_basic_plan(self):
        """Testa criação de plano básico."""
        plan = TestCognitivePlanFactory.create()
        assert plan["plan_id"].startswith("plan-")
        assert plan["domain"] == "TECHNICAL"
        assert plan["status"] == "PENDING"

    def test_create_with_custom_params(self):
        """Testa criação de plano com parâmetros customizados."""
        plan = TestCognitivePlanFactory.create(
            intent="Custom intent",
            domain="BUSINESS",
            status="COMPLETED",
            risk_band="high",
        )
        assert plan["intent"] == "Custom intent"
        assert plan["domain"] == "BUSINESS"
        assert plan["status"] == "COMPLETED"
        assert plan["risk_band"] == "high"

    def test_create_batch(self):
        """Testa criação de múltiplos planos."""
        plans = TestCognitivePlanFactory.create_batch(count=3)
        assert len(plans) == 3
        assert all(p["status"] == "PENDING" for p in plans)


class TestSpecialistOpinionFactoryTests:
    """Testes para TestSpecialistOpinionFactory."""

    def test_create_opinion(self):
        """Testa criação de opinião."""
        opinion = TestSpecialistOpinionFactory.create(
            plan_id="plan-123",
            confidence=0.9,
            recommendation=True,
        )
        assert opinion["plan_id"] == "plan-123"
        assert opinion["confidence"] == 0.9
        assert opinion["recommendation"] is True

    def test_confidence_clamping(self):
        """Testa que confiança é limitada entre 0 e 1."""
        opinion_high = TestSpecialistOpinionFactory.create(confidence=1.5)
        assert opinion_high["confidence"] == 1.0

        opinion_low = TestSpecialistOpinionFactory.create(confidence=-0.5)
        assert opinion_low["confidence"] == 0.0


class TestConsolidatedDecisionFactoryTests:
    """Testes para TestConsolidatedDecisionFactory."""

    def test_create_decision(self):
        """Testa criação de decisão consolidada."""
        decision = TestConsolidatedDecisionFactory.create(
            plan_id="plan-123",
            final_decision=True,
            consensus_score=0.85,
        )
        assert decision["plan_id"] == "plan-123"
        assert decision["final_decision"] is True
        assert decision["consensus_score"] == 0.85


class TestExecutionTicketFactoryTests:
    """Testes para TestExecutionTicketFactory."""

    def test_create_ticket(self):
        """Testa criação de ticket."""
        ticket = TestExecutionTicketFactory.create(
            plan_id="plan-123",
            task_type="query",
        )
        assert ticket["plan_id"] == "plan-123"
        assert ticket["task"]["type"] == "query"
        assert ticket["status"] == "PENDING"

    def test_create_batch(self):
        """Testa criação de múltiplos tickets."""
        tickets = TestExecutionTicketFactory.create_batch(count=5)
        assert len(tickets) == 5
        task_types = {t["task"]["type"] for t in tickets}
        assert len(task_types) > 0  # Pelo menos um tipo


class TestSpecialistFeedbackFactoryTests:
    """Testes para TestSpecialistFeedbackFactory."""

    def test_create_feedback(self):
        """Testa criação de feedback."""
        feedback = TestSpecialistFeedbackFactory.create(
            human_decision=True,
            confidence=0.85,
        )
        assert feedback["human_decision"] == "approve"
        assert feedback["specialist_confidence"] == 0.85

    def test_create_batch_with_ratio(self):
        """Testa criação de batch com rácio de aprovação."""
        feedbacks = TestSpecialistFeedbackFactory.create_batch(
            count=10,
            approve_ratio=0.7,
        )
        assert len(feedbacks) == 10

        approve_count = sum(1 for f in feedbacks if f["human_decision"] == "approve")
        assert approve_count == 7  # 70% de 10


class TestTaskFactoryTests:
    """Testes para TestTaskFactory."""

    def test_create_task(self):
        """Testa criação de tarefa."""
        task = TestTaskFactory.create(
            task_type="ANALYZE",
            description="Test task",
        )
        assert task["task_type"] == "ANALYZE"
        assert task["description"] == "Test task"
        assert task["dependencies"] == []

    def test_create_with_dependencies(self):
        """Testa criação de tarefa com dependências."""
        main_task, dependencies = TestTaskFactory.create_with_dependencies(
            dependency_count=2
        )
        assert len(dependencies) == 2
        assert len(main_task["dependencies"]) == 2


class TestConvenienceFunctions:
    """Testes para funções de conveniência."""

    def test_create_test_plan(self):
        """Testa função create_test_plan."""
        plan = create_test_plan(intent="Test", domain="TECHNICAL")
        assert plan["intent"] == "Test"
        assert plan["domain"] == "TECHNICAL"

    def test_create_test_opinion(self):
        """Testa função create_test_opinion."""
        opinion = create_test_opinion(plan_id="plan-123", confidence=0.8)
        assert opinion["plan_id"] == "plan-123"
        assert opinion["confidence"] == 0.8


class TestAssertions:
    """Testes para assertions customizados."""

    def test_assert_valid_plan_id(self):
        """Testa validação de plan_id."""
        assert_valid_plan_id("plan-123")  # OK
        with pytest.raises(AssertionError):
            assert_valid_plan_id("invalid")

    def test_assert_valid_confidence(self):
        """Testa validação de confiança."""
        assert_valid_confidence(0.5)  # OK
        assert_valid_confidence(0.0)  # OK
        assert_valid_confidence(1.0)  # OK
        with pytest.raises(AssertionError):
            assert_valid_confidence(1.5)

    def test_assert_valid_domain(self):
        """Testa validação de domínio."""
        assert_valid_domain("TECHNICAL")  # OK
        with pytest.raises(AssertionError):
            assert_valid_domain("INVALID")

    def test_assert_valid_risk_band(self):
        """Testa validação de banda de risco."""
        assert_valid_risk_band("low")  # OK
        with pytest.raises(AssertionError):
            assert_valid_risk_band("invalid")

    def test_assert_tasks_dependent(self):
        """Testa verificação de dependência entre tarefas."""
        task_a = {"task_id": "task-a", "dependencies": []}
        task_b = {"task_id": "task-b", "dependencies": ["task-a"]}

        assert_tasks_dependent(task_a, task_b)  # OK

    def test_assert_no_circular_dependencies(self):
        """Testa detecção de dependências circulares."""
        task_a = {"task_id": "task-a", "dependencies": []}
        task_b = {"task_id": "task-b", "dependencies": ["task-a"]}
        task_c = {"task_id": "task-c", "dependencies": ["task-b"]}

        assert_no_circular_dependencies([task_a, task_b, task_c])  # OK

        # Circular
        task_circular = {
            "task_id": "task-circular",
            "dependencies": ["task-circular"]
        }
        with pytest.raises(AssertionError):
            assert_no_circular_dependencies([task_circular])

    def test_assert_cognitive_plan(self):
        """Testa validação completa de plano cognitivo."""
        plan = TestCognitivePlanFactory.create()
        assert_cognitive_plan(plan)  # OK

        # Invalid plan
        with pytest.raises(AssertionError):
            assert_cognitive_plan({"invalid": "plan"})

    def test_assert_specialist_opinion(self):
        """Testa validação completa de opinião."""
        opinion = TestSpecialistOpinionFactory.create()
        assert_specialist_opinion(opinion)  # OK

    def test_assert_consolidated_decision(self):
        """Testa validação completa de decisão consolidada."""
        decision = TestConsolidatedDecisionFactory.create()
        assert_consolidated_decision(decision)  # OK

    def test_assert_approve_reject_balance(self):
        """Testa validação de balanceamento."""
        assert_approve_reject_balance(4, 1, min_total=3)  # OK

        with pytest.raises(AssertionError):
            assert_approve_reject_balance(1, 1, min_total=3)


class TestKafkaMocks:
    """Testes para mocks de Kafka."""

    @pytest.mark.asyncio
    async def test_mock_producer(self):
        """Testa MockKafkaProducer."""
        producer = MockKafkaProducer()
        await producer.produce("test-topic", {"key": "value"})
        await producer.flush()

        messages = producer.get_messages()
        assert len(messages) == 1
        assert messages[0]["topic"] == "test-topic"

    def test_mock_kafka_message(self):
        """Testa MockKafkaMessage."""
        msg = MockKafkaMessage(
            value={"test": "data"},
            topic="test-topic",
        )
        assert msg.topic == "test-topic"
        assert b"test" in msg.value


class TestDatabaseMocks:
    """Testes para mocks de base de dados."""

    @pytest.mark.asyncio
    async def test_mock_mongodb(self):
        """Testa MockMongoDBClient."""
        client = MockMongoDBClient()
        collection = client.get_collection("test")

        await collection.insert_one({"_id": "123", "data": "test"})
        result = await collection.find_one({"_id": "123"})

        assert result is not None
        assert result["data"] == "test"

    @pytest.mark.asyncio
    async def test_mock_redis(self):
        """Testa MockRedisClient."""
        redis = MockRedisClient()
        await redis.set("key", "value")
        value = await redis.get("key")

        assert value is not None
        assert b"value" == value


class TestTemporalMock:
    """Testes para mocks de Temporal."""

    @pytest.mark.asyncio
    async def test_mock_temporal_client(self):
        """Testa MockTemporalClient."""
        client = MockTemporalClient()

        result = await client.start_workflow(
            workflow=None,
            args=[],
            id="workflow-123",
        )

        assert result.id == "workflow-123"
