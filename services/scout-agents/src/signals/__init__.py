"""
Signals Module - Detecção de sinais e curiosidade para exploração inteligente.

Módulos:
- curiosity_calculator: Calcula scores de curiosidade
- signal_detector: Detecta sinais de mudança/interesse
"""
from .curiosity_calculator import CuriosityCalculator
from .signal_detector import SignalDetector, FileSignal

__all__ = ['CuriosityCalculator', 'SignalDetector', 'FileSignal']
