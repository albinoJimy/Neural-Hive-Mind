"""Componentes NLU refatorados.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)

Este módulo contém os componentes extraídos do NLUPipeline monolítico:
- ClassifierEngine: Regras de classificação de intenções
- CacheManager: Gerenciamento de cache Redis
- TextProcessor: Normalização, extração de entidades, PII masking
- LanguageDetector: Detecção automática de idioma
- ThresholdCalculator: Threshold adaptativo baseado em confiança
"""

from .cache_manager import CacheManager
from .classifier_engine import ClassifierEngine
from .language_detector import LanguageDetector
from .text_processor import TextProcessor
from .threshold_calculator import ThresholdCalculator

__all__ = [
    "CacheManager",
    "ClassifierEngine",
    "LanguageDetector",
    "TextProcessor",
    "ThresholdCalculator",
]
