"""Módulo do Intelligent Scheduler."""

from .adaptive_priority import AdaptivePriorityCalculator
from .preemption import PreemptionManager, PreemptionStatus
from .preemption_rules import PreemptionDecision, PreemptionRules
from .priority_calculator import PriorityCalculator
from .priority_queues import PriorityLevel, PriorityQueues
from .queue_manager import QueueManager
from .reprioritizer import RePrioritizer
from .sla_reprioritizer import SLARePrioritizer

# Imports condicionais para módulos com dependências externas
try:
    from .intelligent_scheduler import IntelligentScheduler

    _intelligent_available = True
except ImportError:
    IntelligentScheduler = None  # type: ignore
    _intelligent_available = False

try:
    from .resource_allocator import ResourceAllocator

    _allocator_available = True
except ImportError:
    ResourceAllocator = None  # type: ignore
    _allocator_available = False

try:
    from .affinity_tracker import AffinityTracker

    _affinity_available = True
except ImportError:
    AffinityTracker = None  # type: ignore
    _affinity_available = False

__all__ = [
    "AdaptivePriorityCalculator",
    "PreemptionDecision",
    "PreemptionManager",
    "PreemptionRules",
    "PreemptionStatus",
    "PriorityCalculator",
    "PriorityLevel",
    "PriorityQueues",
    "QueueManager",
    "RePrioritizer",
    "SLARePrioritizer",
]

# Adicionar módulos condicionais ao __all__ se disponíveis
if _intelligent_available:
    __all__.append("IntelligentScheduler")
if _allocator_available:
    __all__.append("ResourceAllocator")
if _affinity_available:
    __all__.append("AffinityTracker")
