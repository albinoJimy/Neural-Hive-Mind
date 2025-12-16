"""
ML Pipelines Monitoring Module

Módulo de monitoramento de performance de modelos e auto-retreinamento.
"""

from .model_performance_monitor import ModelPerformanceMonitor
from .auto_retrain import AutoRetrainOrchestrator

__all__ = ['ModelPerformanceMonitor', 'AutoRetrainOrchestrator']

__version__ = '1.0.0'
