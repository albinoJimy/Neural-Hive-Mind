"""
Servidor MCP para Guard Agents usando FastMCP.

Implementa o protocolo Anthropic MCP para expor ferramentas
de validação de segurança, detecção de ameaças e remediação.
"""

import structlog
from fastmcp import FastMCP

from guard_mcp_server.config import get_settings
from guard_mcp_server.tools.guard_tools import register_guard_tools

logger = structlog.get_logger(__name__)

# Criar instância do servidor MCP
settings = get_settings()
mcp = FastMCP(
    name="Guard MCP Server",
    version=settings.service_version,
    instructions="Ferramentas de validação de segurança, detecção de ameaças e remediação",
)


@mcp.resource("guard://info")
def get_guard_info() -> str:
    """Retorna informações sobre o servidor Guard MCP."""
    return """
    Guard MCP Server
    ================

    Servidor MCP que fornece ferramentas de segurança para o Neural Hive Mind.

    Ferramentas disponíveis:
    - validate_security: Validar políticas de segurança (OPA, RBAC, secrets)
    - scan_vulnerabilities: Scan de vulnerabilidades (Trivy)
    - detect_threats: Detectar ameaças em tempo real
    - check_compliance: Verificar compliance regulatório (GDPR, SOC2, ISO27001)
    - remediate_issue: Executar ações de remediação automática

    Uso:
    - Validar ExecutionTickets antes da execução
    - Escanear imagens Docker antes do deploy
    - Detectar anomalias de segurança em tempo real
    - Verificar compliance regulatório
    - Executar ações de remediação automática ou manual
    """


# Registrar ferramentas
register_guard_tools(mcp)

logger.info("guard_mcp_server_initialized", name=mcp.name, version=settings.service_version)
