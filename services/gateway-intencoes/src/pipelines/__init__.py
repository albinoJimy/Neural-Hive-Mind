"""Pipelines do Gateway de Intenções."""

# T11: NLU Service via gRPC (refator de 1.303 LOC)
from .nlu_pipeline_service import NLUPipeline

__all__ = ["NLUPipeline"]
