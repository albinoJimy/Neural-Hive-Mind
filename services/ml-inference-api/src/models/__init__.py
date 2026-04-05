"""Modelos de dados do ML Inference API."""
from .schemas import (
    PredictRequest,
    PredictResponse,
    PredictOptions,
    BatchPredictRequest,
    BatchPredictResponse,
    BatchOptions,
    ModelInfo,
    ErrorResponse,
    HealthResponse,
    ReadyResponse,
)

__all__ = [
    "PredictRequest",
    "PredictResponse",
    "PredictOptions",
    "BatchPredictRequest",
    "BatchPredictResponse",
    "BatchOptions",
    "ModelInfo",
    "ErrorResponse",
    "HealthResponse",
    "ReadyResponse",
]
