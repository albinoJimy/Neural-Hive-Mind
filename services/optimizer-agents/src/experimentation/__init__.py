"""
Modulo de Experimentacao A/B Testing para o Optimizer Agents.

Este modulo fornece um framework completo para testes A/B, incluindo:
- ABTestingEngine: Engine principal para gerenciamento de testes A/B
- Estrategias de randomizacao (simples, estratificada, blocos)
- Analise estatistica (t-test, chi-square, Mann-Whitney, Bayesiano)
- Guardrails automaticos para seguranca de experimentos
- Calculadora de tamanho de amostra
"""

from src.experimentation.ab_testing_engine import ABTestingEngine
from src.experimentation.guardrails import GuardrailMonitor
from src.experimentation.randomization import (
    BlockedRandomizer,
    RandomizationStrategyType,
    RandomRandomizer,
    StratifiedRandomizer,
)
from src.experimentation.sample_size_calculator import SampleSizeCalculator
from src.experimentation.statistical_analysis import StatisticalAnalyzer

__all__ = [
    "ABTestingEngine",
    "RandomRandomizer",
    "StratifiedRandomizer",
    "BlockedRandomizer",
    "RandomizationStrategyType",
    "StatisticalAnalyzer",
    "GuardrailMonitor",
    "SampleSizeCalculator",
]
