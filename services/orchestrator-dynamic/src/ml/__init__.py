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

__version__ = "1.0.0"

from .anomaly_detector import AnomalyDetector
from .duration_predictor import DurationPredictor
from .feature_engineering import (
    compute_historical_stats,
    encode_qos,
    encode_risk_band,
    extract_ticket_features,
    normalize_features,
)
from .ml_predictor import MLPredictor
from .model_audit_logger import AuditEventContext, ModelAuditLogger, ModelLifecycleEvent
from .model_comparator import ComparisonResult, ModelComparator
from .model_promotion import ModelPromotionManager
from .model_registry import ModelRegistry
from .training_pipeline import TrainingPipeline

__all__ = [
    "AnomalyDetector",
    "AuditEventContext",
    "ComparisonResult",
    "DurationPredictor",
    "MLPredictor",
    "ModelAuditLogger",
    "ModelComparator",
    "ModelLifecycleEvent",
    "ModelPromotionManager",
    "ModelRegistry",
    "TrainingPipeline",
    "compute_historical_stats",
    "encode_qos",
    "encode_risk_band",
    "extract_ticket_features",
    "normalize_features",
]
