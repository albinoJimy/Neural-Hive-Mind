"""
Observability module for Approval Service
"""

from src.observability.metrics import NeuralHiveMetrics, register_metrics

__all__ = ['NeuralHiveMetrics', 'register_metrics']
