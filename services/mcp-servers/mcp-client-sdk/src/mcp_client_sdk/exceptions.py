# MCP Client SDK Exceptions


class MCPError(Exception):
    """Base exception para erros do MCP Client."""


class MCPConnectionError(MCPError):
    """Erro de conexão com servidor MCP."""


class MCPTimeoutError(MCPError):
    """Erro de timeout na requisição."""


class MCPResponseError(MCPError):
    """Erro na resposta do servidor."""


class MCPToolNotFoundError(MCPError):
    """Ferramenta não encontrada."""
