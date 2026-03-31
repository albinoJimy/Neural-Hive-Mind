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
    SagaEventType
)
from .saga_orchestrator import SagaOrchestrator
from .saga_repository import SagaRepository
from .saga_event_store import SagaEventStore

__all__ = [
    'SagaStatus',
    'SagaStep',
    'SagaState',
    'SagaEvent',
    'SagaEventType',
    'SagaOrchestrator',
    'SagaRepository',
    'SagaEventStore'
]
