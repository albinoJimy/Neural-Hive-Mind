"""Business logic services."""
from .tool_registry import ToolRegistry
from .tool_catalog_bootstrap import ToolCatalogBootstrap

# Lazy import for GeneticToolSelector (requires deap)
try:
    from .genetic_tool_selector import GeneticToolSelector
    _genetic_available = True
except ImportError:
    _genetic_available = False

__all__ = ["ToolRegistry", "ToolCatalogBootstrap"]

if _genetic_available:
    __all__.append("GeneticToolSelector")
