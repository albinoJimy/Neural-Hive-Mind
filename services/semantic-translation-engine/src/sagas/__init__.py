"""
Sagas module for distributed transaction patterns.

Implementa Saga Pattern para garantir consistência eventual
entre MongoDB e Kafka em operações distribuídas.
"""

from src.sagas.approval_saga import ApprovalSaga

__all__ = ['ApprovalSaga']
