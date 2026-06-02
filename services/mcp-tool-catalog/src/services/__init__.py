"""Business logic services."""

from .connectivity_tester import ConnectivityTester, check_tool_health
from .tool_catalog_bootstrap import ToolCatalogBootstrap
from .tool_registry import ToolRegistry

# Lazy import for GeneticToolSelector (requires deap)
try:
    from .genetic_tool_selector import GeneticToolSelector  # noqa: F401

    _genetic_available = True
except ImportError:
    _genetic_available = False

__all__ = ["ToolRegistry", "ToolCatalogBootstrap", "ConnectivityTester", "check_tool_health"]

if _genetic_available:
    __all__.append("GeneticToolSelector")
