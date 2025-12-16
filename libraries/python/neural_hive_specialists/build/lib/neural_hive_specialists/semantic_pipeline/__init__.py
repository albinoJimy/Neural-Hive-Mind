"""Pipeline semântico para substituir heurísticas de string-match."""

from .semantic_analyzer import SemanticAnalyzer
from .ontology_evaluator import OntologyBasedEvaluator
from .semantic_pipeline import SemanticPipeline

__all__ = [
    'SemanticAnalyzer',
    'OntologyBasedEvaluator',
    'SemanticPipeline'
]
