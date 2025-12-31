"""Hierarquia de exceções customizadas para erros MCP.

Códigos de erro JSON-RPC 2.0 padrão:
    -32700: Parse error - JSON inválido
    -32600: Invalid request - Requisição JSON-RPC inválida
    -32601: Method not found - Método não encontrado
    -32602: Invalid params - Parâmetros inválidos
    -32603: Internal error - Erro interno do servidor
"""
from typing import Any, Optional


class MCPError(Exception):
    """Exceção base para erros MCP."""

    def __init__(
        self,
        message: str,
        code: int = -32603,
        data: Optional[Any] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data

    def __str__(self) -> str:
        return f"MCPError(code={self.code}, message={self.message})"


class MCPServerError(MCPError):
    """Erro retornado pelo servidor MCP (códigos -32xxx)."""

    def __str__(self) -> str:
        return f"MCPServerError(code={self.code}, message={self.message})"


class MCPTransportError(MCPError):
    """Erro de transporte (timeout, conexão recusada, circuit breaker aberto)."""

    def __init__(
        self,
        message: str,
        data: Optional[Any] = None
    ) -> None:
        super().__init__(message, code=-32000, data=data)

    def __str__(self) -> str:
        return f"MCPTransportError(message={self.message})"


class MCPProtocolError(MCPError):
    """Erro de protocolo (resposta inválida, JSON malformado)."""

    def __init__(
        self,
        message: str,
        data: Optional[Any] = None
    ) -> None:
        super().__init__(message, code=-32700, data=data)

    def __str__(self) -> str:
        return f"MCPProtocolError(message={self.message})"


class MCPToolNotFoundError(MCPServerError):
    """Ferramenta não encontrada no servidor MCP."""

    def __init__(
        self,
        tool_name: str,
        data: Optional[Any] = None
    ) -> None:
        super().__init__(
            message=f"Tool not found: {tool_name}",
            code=-32601,
            data=data
        )
        self.tool_name = tool_name

    def __str__(self) -> str:
        return f"MCPToolNotFoundError(tool={self.tool_name})"


class MCPInvalidParamsError(MCPServerError):
    """Parâmetros inválidos na chamada de ferramenta."""

    def __init__(
        self,
        message: str = "Invalid parameters",
        data: Optional[Any] = None
    ) -> None:
        super().__init__(message=message, code=-32602, data=data)

    def __str__(self) -> str:
        return f"MCPInvalidParamsError(message={self.message})"


# Mapeamento de códigos de erro JSON-RPC para exceções
JSONRPC_ERROR_MAP = {
    -32700: MCPProtocolError,
    -32600: MCPProtocolError,
    -32601: MCPToolNotFoundError,
    -32602: MCPInvalidParamsError,
    -32603: MCPServerError,
}


def create_exception_from_error(code: int, message: str, data: Optional[Any] = None) -> MCPError:
    """Cria exceção apropriada baseada no código de erro JSON-RPC."""
    exception_class = JSONRPC_ERROR_MAP.get(code, MCPServerError)

    if exception_class == MCPToolNotFoundError:
        # Extrai nome da ferramenta da mensagem se possível
        tool_name = data if isinstance(data, str) else "unknown"
        return MCPToolNotFoundError(tool_name=tool_name, data=data)

    return exception_class(message=message, data=data)
