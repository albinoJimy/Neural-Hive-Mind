"""
Adapter base para execução de ferramentas MCP.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionResult:
    """Resultado da execução de uma ferramenta."""

    success: bool
    output: str
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    exit_code: Optional[int] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class AdapterError(Exception):
    """Erro durante execução de adapter."""
    pass


class BaseToolAdapter(ABC):
    """Classe base para adaptadores de ferramentas."""

    def __init__(self):
        self.logger = logger.bind(adapter=self.__class__.__name__)

    @abstractmethod
    async def execute(
        self,
        tool_id: str,
        tool_name: str,
        command: str,
        parameters: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ExecutionResult:
        """
        Executa uma ferramenta.

        Args:
            tool_id: ID único da ferramenta
            tool_name: Nome da ferramenta
            command: Comando ou endpoint a executar
            parameters: Parâmetros da execução
            context: Contexto adicional (paths, env vars, etc)

        Returns:
            ExecutionResult com resultado da execução
        """
        pass

    @abstractmethod
    async def validate_tool_availability(self, tool_name: str) -> bool:
        """
        Valida se a ferramenta está disponível para execução.

        Args:
            tool_name: Nome da ferramenta

        Returns:
            True se disponível, False caso contrário
        """
        pass

    async def _log_execution(
        self,
        tool_name: str,
        command: str,
        result: ExecutionResult
    ):
        """Log estruturado da execução."""
        self.logger.info(
            "tool_execution_completed",
            tool_name=tool_name,
            command=command,
            success=result.success,
            execution_time_ms=result.execution_time_ms,
            exit_code=result.exit_code
        )
