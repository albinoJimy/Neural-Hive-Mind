"""
Registry Module - Sistema inteligente de seleção de LLM.

Exporta componentes de registry, tracker e selector.
"""

# Import base que não depende de outros módulos
from neural_hive_llm.registry.model_registry import (
    ModelCapabilities,
    ModelMetadata,
    ModelPricing,
    ModelRegistry,
    Priority,
    TaskType,
    get_registry,
    reset_registry,
)
from neural_hive_llm.registry.performance_tracker import (
    PerformanceTracker,
    RequestMetric,
    get_tracker,
    reset_tracker,
)
from neural_hive_llm.registry.intelligent_selector import (
    IntelligentSelector,
    SelectionCriteria,
    SelectionContext,
    SelectionResult,
    SelectionWeights,
    get_selector,
    reset_selector,
)
from neural_hive_llm.registry.enhanced_selection import (
    ComplianceRequirement,
    DataResidencyRequirement,
    Domain,
    EnhancedSelectionContext,
    ExtendedSelectionCriteria,
    ExtendedSelectionWeights,
    PriorityLevel,
)
from neural_hive_llm.registry.enhanced_selector import (
    EnhancedIntelligentSelector,
    get_enhanced_selector,
)

__all__ = [
    # Model Registry
    "ModelRegistry",
    "ModelMetadata",
    "ModelCapabilities",
    "ModelPricing",
    "TaskType",
    "Priority",
    "get_registry",
    "reset_registry",
    # Performance Tracker
    "PerformanceTracker",
    "RequestMetric",
    "get_tracker",
    "reset_tracker",
    # Intelligent Selector
    "IntelligentSelector",
    "SelectionContext",
    "SelectionResult",
    "SelectionCriteria",
    "SelectionWeights",
    "get_selector",
    "reset_selector",
    # Enhanced Selection
    "ComplianceRequirement",
    "DataResidencyRequirement",
    "Domain",
    "EnhancedSelectionContext",
    "ExtendedSelectionCriteria",
    "ExtendedSelectionWeights",
    "PriorityLevel",
    "EnhancedIntelligentSelector",
    "get_enhanced_selector",
]
