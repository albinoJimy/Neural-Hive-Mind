"""Workflows para geração de arquitetura."""

from src.workflows.compensation_workflow import CompensationWorkflow
from src.workflows.conditional_workflow import ConditionalWorkflow
from src.workflows.parallel_workflow import ParallelWorkflow

__all__ = [
    "CompensationWorkflow",
    "ConditionalWorkflow",
    "ParallelWorkflow",
]
