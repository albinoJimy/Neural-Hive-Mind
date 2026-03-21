"""Services package for explainability-api."""

# Lazy import to avoid numpy dependency at module level
# ShapCalculator requires numpy and is imported dynamically when needed

from .quality_scorer import ExplanationQualityScorer
from .hierarchical_explainer import HierarchicalExplainer
from .counterfactual_analyzer import CounterfactualAnalyzer
from .temporal_tracker import TemporalTracker

__all__ = [
    'ExplanationQualityScorer',
    'HierarchicalExplainer',
    'CounterfactualAnalyzer',
    'TemporalTracker',
]

def get_shap_calculator():
    """Lazy import of ShapCalculator to avoid numpy dependency."""
    from .shap_calculator import ShapCalculator
    return ShapCalculator
