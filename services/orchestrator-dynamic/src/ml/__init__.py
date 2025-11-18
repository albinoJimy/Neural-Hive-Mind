"""
ML Predictions Module for Orchestrator Dynamic.

This module provides predictive modeling capabilities for ticket duration estimation,
resource prediction, and anomaly detection using machine learning models.

Components:
- DurationPredictor: RandomForest regression for ticket duration prediction
- AnomalyDetector: Isolation Forest for runtime anomaly detection
- ModelRegistry: MLflow integration for model versioning and lifecycle management
- MLPredictor: Facade for coordinating predictions
- TrainingPipeline: Incremental learning and periodic retraining

Version: 1.0.0
"""

__version__ = '1.0.0'

from .duration_predictor import DurationPredictor
from .anomaly_detector import AnomalyDetector
from .model_registry import ModelRegistry
from .ml_predictor import MLPredictor
from .training_pipeline import TrainingPipeline
from .feature_engineering import (
    extract_ticket_features,
    encode_risk_band,
    encode_qos,
    compute_historical_stats,
    normalize_features
)

__all__ = [
    'DurationPredictor',
    'AnomalyDetector',
    'ModelRegistry',
    'MLPredictor',
    'TrainingPipeline',
    'extract_ticket_features',
    'encode_risk_band',
    'encode_qos',
    'compute_historical_stats',
    'normalize_features'
]
