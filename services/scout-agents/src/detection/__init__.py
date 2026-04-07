"""Detection modules for signal analysis"""

from .bayesian_filter import BayesianFilter
from .curiosity_scorer import CuriosityScorer
from .signal_detector import SignalDetector

__all__ = ["SignalDetector", "BayesianFilter", "CuriosityScorer"]
