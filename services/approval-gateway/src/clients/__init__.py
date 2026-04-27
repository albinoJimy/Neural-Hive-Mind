"""Clients do Approval Gateway."""

from .llm_client_wrapper import LLMClient

try:
    from .engineering_service_registry_client import (
        EngineeringServiceRegistryClient,
        register_engineering_service,
    )
except ImportError:
    # Proto stubs podem não estar disponíveis em todos os ambientes
    pass

__all__ = [
    "LLMClient",
]
