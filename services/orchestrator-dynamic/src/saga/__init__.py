"""
Modulo de coordenacao de Saga para transaccoes distribuidas.

Implementa o padrao Saga com estado persistido no MongoDB para
coordenacao de transaccoes distribuidas com compensacao automatica.
"""
from .retry_config import NON_RETRYABLE_ERRORS, SagaRetryConfig
from .retry_policy import NoRetryPolicy, RetryError, RetryPolicy, create_retry_policy
from .saga_event_store import SagaEventStore
from .saga_metrics import SagaMetrics, get_saga_metrics, timer
from .saga_orchestrator import SagaOrchestrator
from .saga_producer import SagaProducer, get_saga_producer
from .saga_repository import SagaRepository
from .saga_state import (
    SagaConcurrentModificationError,
    SagaEvent,
    SagaEventType,
    SagaState,
    SagaStatus,
    SagaStep,
)

__all__ = [
    "NON_RETRYABLE_ERRORS",
    "NoRetryPolicy",
    "RetryError",
    "RetryPolicy",
    "SagaConcurrentModificationError",
    "SagaEvent",
    "SagaEventStore",
    "SagaEventType",
    "SagaMetrics",
    "SagaOrchestrator",
    "SagaProducer",
    "SagaRepository",
    "SagaRetryConfig",
    "SagaState",
    "SagaStatus",
    "SagaStep",
    "create_retry_policy",
    "get_saga_metrics",
    "get_saga_producer",
    "timer",
]
