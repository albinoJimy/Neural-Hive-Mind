"""
ML Predictive Scheduling Optimization Module

Este módulo implementa previsão de carga e otimização de agendamento usando:
- Prophet/ARIMA para forecasting de séries temporais de volumes de tickets
- Reinforcement Learning (Q-learning) para políticas de agendamento otimizadas
- Integração com ClickHouse para dados históricos de 18 meses
- Engenharia de features e registro de modelos via MLflow
"""

from .load_predictor import LoadPredictor
from .scheduling_optimizer import SchedulingOptimizer
from .feature_engineering import FeatureEngineering
from .model_registry import ModelRegistry
from .training_pipeline import TrainingPipeline

__all__ = [
    'LoadPredictor',
    'SchedulingOptimizer',
    'FeatureEngineering',
    'ModelRegistry',
    'TrainingPipeline',
]
