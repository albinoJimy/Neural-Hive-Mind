"""
Neural Hive ML - Biblioteca Centralizada de Modelos Preditivos

Esta biblioteca fornece modelos de machine learning reutilizáveis para:
- Previsão de duração e recursos de tickets (SchedulingPredictor)
- Previsão de carga do sistema (LoadPredictor)
- Detecção de anomalias (AnomalyDetector)
"""

from neural_hive_ml.predictive_models import (
    SchedulingPredictor,
    LoadPredictor,
    AnomalyDetector
)

__version__ = "1.0.0"
__all__ = ["SchedulingPredictor", "LoadPredictor", "AnomalyDetector"]
