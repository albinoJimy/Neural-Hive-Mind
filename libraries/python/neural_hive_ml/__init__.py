"""
Neural Hive ML - Biblioteca Centralizada de Modelos Preditivos

Esta biblioteca fornece modelos de machine learning reutilizáveis para:
- Previsão de duração e recursos de tickets (SchedulingPredictor)
- Previsão de carga do sistema (LoadPredictor)
- Detecção de anomalias (AnomalyDetector)
- MLflow integration para Online Learning (MLflowClient)
- Detecção de Model Drift (DriftDetector)
- Canary Deployment de modelos (CanaryDeployer)
"""

from neural_hive_ml.predictive_models import (
    SchedulingPredictor,
    LoadPredictor,
    AnomalyDetector,
)
from neural_hive_ml.mlflow_client import MLflowClient
from neural_hive_ml.config import (
    get_mlflow_settings,
    get_online_learning_settings,
    MLflowSettings,
    OnlineLearningSettings,
)
from neural_hive_ml.model_version_repository import ModelVersionRepository
from neural_hive_ml.retraining_job import RetrainingJob
from neural_hive_ml.drift_detector import DriftDetector, CanaryDeployer

__version__ = "1.2.0"
__all__ = [
    "SchedulingPredictor",
    "LoadPredictor",
    "AnomalyDetector",
    "MLflowClient",
    "ModelVersionRepository",
    "RetrainingJob",
    "DriftDetector",
    "CanaryDeployer",
    "get_mlflow_settings",
    "get_online_learning_settings",
    "MLflowSettings",
    "OnlineLearningSettings",
]
