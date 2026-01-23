"""E2E test utilities for Neural Hive Mind Phase 2."""

from tests.e2e.utils.temporal_helpers import (
    TemporalTestHelper,
    WorkflowStatus,
    ActivityExecution,
    validate_temporal_workflow,
    validate_temporal_activities,
)
from tests.e2e.utils.database_helpers import (
    MongoDBTestHelper,
    PostgreSQLTestHelper,
    PostgreSQLTicketsHelper,
    PostgreSQLTemporalHelper,
    MongoDBCollectionStats,
    TicketPersistenceStats,
    validate_mongodb_persistence,
    validate_postgresql_persistence,
)
from tests.e2e.utils.kafka_helpers import (
    KafkaTestHelper,
    KafkaMessageValidation,
    validate_kafka_messages,
    wait_for_kafka_message,
    collect_kafka_messages,
)
from tests.e2e.utils.status_tracker import (
    TicketStatusTracker,
    FlowCStatusTracker,
    TicketStatus,
    TicketStatusHistory,
    StatusTransition,
    VALID_TRANSITIONS,
)
from tests.e2e.utils.flow_c_validators import (
    validate_ticket_status_transition,
    validate_status_sequence,
    validate_telemetry_completeness,
    validate_telemetry_step_metrics,
    validate_sla_compliance,
    validate_result_structure,
    validate_dependency_chain,
    validate_trace_correlation,
    ValidationResult,
)

__all__ = [
    # Temporal
    "TemporalTestHelper",
    "WorkflowStatus",
    "ActivityExecution",
    "validate_temporal_workflow",
    "validate_temporal_activities",
    # Database
    "MongoDBTestHelper",
    "PostgreSQLTestHelper",
    "PostgreSQLTicketsHelper",
    "PostgreSQLTemporalHelper",
    "MongoDBCollectionStats",
    "TicketPersistenceStats",
    "validate_mongodb_persistence",
    "validate_postgresql_persistence",
    # Kafka
    "KafkaTestHelper",
    "KafkaMessageValidation",
    "validate_kafka_messages",
    "wait_for_kafka_message",
    "collect_kafka_messages",
    # Status Tracking
    "TicketStatusTracker",
    "FlowCStatusTracker",
    "TicketStatus",
    "TicketStatusHistory",
    "StatusTransition",
    "VALID_TRANSITIONS",
    # Flow C Validators
    "validate_ticket_status_transition",
    "validate_status_sequence",
    "validate_telemetry_completeness",
    "validate_telemetry_step_metrics",
    "validate_sla_compliance",
    "validate_result_structure",
    "validate_dependency_chain",
    "validate_trace_correlation",
    "ValidationResult",
]
