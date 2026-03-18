# MCP Client SDK Exceptions


class MCPError(Exception):
    """Base exception para erros do MCP Client."""

    pass


class MCPConnectionError(MCPError):
    """Erro de conexão com servidor MCP."""

    pass


class MCPTimeoutError(MCPError):
    """Erro de timeout na requisição."""

    pass


class MCPResponseError(MCPError):
    """Erro na resposta do servidor."""

    pass


class MCPToolNotFoundError(MCPError):
    """Ferramenta não encontrada."""

    pass
