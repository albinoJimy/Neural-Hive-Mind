"""
Modulo de coordenacao de Saga para transaccoes distribuidas.

Implementa o padrao Saga com estado persistido no MongoDB para
coordenacao de transaccoes distribuidas com compensacao automatica.
"""
from .saga_state import (
    SagaStatus,
    SagaStep,
    SagaState,
    SagaEvent,
    SagaEventType,
    SagaConcurrentModificationError
)
from .saga_orchestrator import SagaOrchestrator
from .saga_repository import SagaRepository
from .saga_event_store import SagaEventStore
from .retry_config import SagaRetryConfig, NON_RETRYABLE_ERRORS
from .retry_policy import RetryPolicy, RetryError, NoRetryPolicy, create_retry_policy

__all__ = [
    'SagaStatus',
    'SagaStep',
    'SagaState',
    'SagaEvent',
    'SagaEventType',
    'SagaConcurrentModificationError',
    'SagaOrchestrator',
    'SagaRepository',
    'SagaEventStore',
    'SagaRetryConfig',
    'NON_RETRYABLE_ERRORS',
    'RetryPolicy',
    'RetryError',
    'NoRetryPolicy',
    'create_retry_policy'
]
