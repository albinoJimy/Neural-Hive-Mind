"""
Evolution Hooks - Meta-learning para Evolution Specialist.

Este módulo implementa um sistema de meta-learning que permite ao Evolution
Specialist aprender quais heurísticas funcionam melhor para quais tipos
de planos e adaptar seus pesos dinamicamente baseado em histórico de avaliações.

Components:
- FingerprintExtractor: Extrai assinatura do plano
- PatternMatcher: Busca planos similares no histórico
- WeightAdapter: Ajusta pesos baseado em histórico de sucesso
- PatternRegistry: Repository MongoDB para padrões de avaliação
- EvolutionFeedbackConsumer: Consome feedback do Kafka
"""

# Version do módulo
__version__ = "1.0.0"

# Models serão importados aqui após implementação
from .feedback_consumer import EvolutionFeedbackConsumer, create_feedback_consumer

# Core components
from .fingerprint_extractor import FingerprintExtractor
from .models import (
    DEFAULT_WEIGHTS,
    DurationRange,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackMessage,
    FeedbackOutcome,
    FeedbackSource,
    Fingerprint,
    PatternMetrics,
    PatternRecord,
    TaskCountRange,
)
from .pattern_matcher import PatternMatcher
from .pattern_registry import PatternRegistry, SyncPatternRegistry
from .weight_adapter import WeightAdapter

__all__ = [
    # Models
    "Fingerprint",
    "PatternRecord",
    "EvolutionEvaluation",
    "FeedbackData",
    "FeedbackMessage",
    "FeedbackOutcome",
    "FeedbackSource",
    "PatternMetrics",
    "TaskCountRange",
    "DurationRange",
    "DEFAULT_WEIGHTS",
    # Core components (uncomment as implemented)
    "FingerprintExtractor",
    "PatternMatcher",
    "WeightAdapter",
    "PatternRegistry",
    "SyncPatternRegistry",
    "EvolutionFeedbackConsumer",
    "create_feedback_consumer",
]
