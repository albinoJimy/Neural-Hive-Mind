"""
Adapters para execução de ferramentas MCP.

Este módulo contém os adaptadores que permitem a execução real de ferramentas
através de diferentes métodos de integração (CLI, REST, gRPC, Container, Library).
"""

from .base_adapter import BaseToolAdapter, AdapterError, ExecutionResult
from .cli_adapter import CLIAdapter
from .rest_adapter import RESTAdapter
from .container_adapter import ContainerAdapter

__all__ = [
    "BaseToolAdapter",
    "AdapterError",
    "ExecutionResult",
    "CLIAdapter",
    "RESTAdapter",
    "ContainerAdapter",
]
