"""Detection modules for signal analysis"""
from .signal_detector import SignalDetector
from .bayesian_filter import BayesianFilter
from .curiosity_scorer import CuriosityScorer

__all__ = ['SignalDetector', 'BayesianFilter', 'CuriosityScorer']
