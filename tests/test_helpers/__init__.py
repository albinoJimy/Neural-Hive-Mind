"""
Test Helpers Package para Neural Hive Mind.

Este pacote fornece factories, assertions e mocks helpers
para testes em todo o projecto.
"""

from .factories import (
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

from .asserts import (
    assert_valid_plan_id,
    assert_valid_ticket_id,
    assert_valid_opinion_id,
    assert_valid_specialist_id,
    assert_valid_workflow_id,
    assert_valid_confidence,
    assert_valid_percentage,
    assert_valid_duration_ms,
    assert_valid_domain,
    assert_valid_risk_band,
    assert_valid_priority,
    assert_valid_status,
    assert_tasks_dependent,
    assert_no_circular_dependencies,
    assert_consolidated_decision,
    assert_specialist_opinion,
    assert_approve_reject_balance,
    assert_cognitive_plan,
    assert_http_response,
    assert_kafka_message,
    assert_feedback_structure,
    assert_feedback_semantic_features,
)

from .mocks import (
    MockKafkaMessage,
    MockKafkaProducer,
    MockKafkaConsumer,
    MockMongoDBCollection,
    MockMongoDBClient,
    MockRedisClient,
    MockTemporalClient,
    MockTemporalWorkflowHandle,
    MockGRPCChannel,
    MockGRPCServer,
    MockHTTPResponse,
    MockHTTPClient,
)

__all__ = [
    # Factories
    "TestCognitivePlanFactory",
    "TestSpecialistOpinionFactory",
    "TestConsolidatedDecisionFactory",
    "TestExecutionTicketFactory",
    "TestSpecialistFeedbackFactory",
    "TestTaskFactory",
    "create_test_plan",
    "create_test_opinion",
    "create_test_decision",
    "create_test_ticket",
    "create_test_feedback",
    # Assertions - ID validations
    "assert_valid_plan_id",
    "assert_valid_ticket_id",
    "assert_valid_opinion_id",
    "assert_valid_specialist_id",
    "assert_valid_workflow_id",
    # Assertions - Value validations
    "assert_valid_confidence",
    "assert_valid_percentage",
    "assert_valid_duration_ms",
    # Assertions - Domain validations
    "assert_valid_domain",
    "assert_valid_risk_band",
    "assert_valid_priority",
    "assert_valid_status",
    # Assertions - Task/Dependency
    "assert_tasks_dependent",
    "assert_no_circular_dependencies",
    # Assertions - Decision/Opinion
    "assert_consolidated_decision",
    "assert_specialist_opinion",
    "assert_approve_reject_balance",
    # Assertions - Structure
    "assert_cognitive_plan",
    "assert_http_response",
    "assert_kafka_message",
    "assert_feedback_structure",
    "assert_feedback_semantic_features",
    # Mocks - Kafka
    "MockKafkaMessage",
    "MockKafkaProducer",
    "MockKafkaConsumer",
    # Mocks - Database
    "MockMongoDBCollection",
    "MockMongoDBClient",
    "MockRedisClient",
    # Mocks - Temporal
    "MockTemporalClient",
    "MockTemporalWorkflowHandle",
    # Mocks - gRPC
    "MockGRPCChannel",
    "MockGRPCServer",
    # Mocks - HTTP
    "MockHTTPResponse",
    "MockHTTPClient",
]
