"""
Fixtures compartilhadas para testes de integracao.
"""

import asyncio
import json
from typing import Any, Dict

import pytest
from aiohttp import web


# ============================================================================
# Fixtures de Mock HTTP Server
# ============================================================================

@pytest.fixture
def mock_http_server_app():
    """
    Aplicacao aiohttp.web para simular APIs REST.

    Endpoints disponiveis:
    - GET /health -> {"status": "healthy"}
    - POST /analyze -> {"result": "success", "issues": 0}
    - GET /projects/:id -> {"id": id, "name": "project"}
    - POST /scan -> {"vulnerabilities": 0}
    """
    app = web.Application()

    async def health_handler(request):
        return web.json_response({"status": "healthy"})

    async def analyze_handler(request):
        body = await request.json()
        return web.json_response({
            "result": "success",
            "issues": 0,
            "project": body.get("project", "unknown")
        })

    async def project_handler(request):
        project_id = request.match_info.get("id", "0")
        return web.json_response({
            "id": project_id,
            "name": f"project-{project_id}"
        })

    async def scan_handler(request):
        body = await request.json()
        return web.json_response({
            "vulnerabilities": 0,
            "image": body.get("image", "unknown"),
            "severity": "none"
        })

    async def error_500_handler(request):
        return web.json_response(
            {"error": "Internal Server Error"},
            status=500
        )

    async def slow_handler(request):
        await asyncio.sleep(5)  # Simula endpoint lento
        return web.json_response({"slow": True})

    app.router.add_get("/health", health_handler)
    app.router.add_post("/analyze", analyze_handler)
    app.router.add_get("/projects/{id}", project_handler)
    app.router.add_post("/scan", scan_handler)
    app.router.add_post("/error", error_500_handler)
    app.router.add_get("/slow", slow_handler)

    return app


@pytest.fixture
async def mock_http_server(mock_http_server_app, aiohttp_server):
    """Mock HTTP server rodando em porta aleatoria."""
    server = await aiohttp_server(mock_http_server_app)
    return server


# ============================================================================
# Fixtures de Mock MCP Server
# ============================================================================

@pytest.fixture
def mock_mcp_server_app():
    """
    Aplicacao aiohttp.web simulando MCP Server (JSON-RPC 2.0).

    Metodos disponiveis:
    - tools/list -> lista de ferramentas
    - tools/call -> executa ferramenta
    - resources/read -> le recurso
    """
    app = web.Application()

    async def jsonrpc_handler(request):
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            })

        method = data.get("method")
        params = data.get("params", {})
        request_id = data.get("id", 1)

        if method == "tools/list":
            return web.json_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "trivy-scan",
                            "description": "Security vulnerability scanner",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "image": {"type": "string"}
                                }
                            }
                        },
                        {
                            "name": "sonarqube-analyze",
                            "description": "Code quality analyzer",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "project": {"type": "string"}
                                }
                            }
                        }
                    ]
                }
            })

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "trivy-scan":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Scan completed for {arguments.get('image', 'unknown')}: 0 vulnerabilities found"
                            }
                        ],
                        "structuredContent": {
                            "vulnerabilities": [],
                            "severity": "none"
                        },
                        "isError": False
                    }
                })

            elif tool_name == "sonarqube-analyze":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Analysis completed for {arguments.get('project', 'unknown')}: 0 issues found"
                            }
                        ],
                        "structuredContent": {
                            "issues": 0,
                            "coverage": 85.5
                        },
                        "isError": False
                    }
                })

            elif tool_name == "failing-tool":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "Tool execution failed"
                            }
                        ],
                        "isError": True
                    }
                })

            else:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }
                })

        elif method == "resources/read":
            uri = params.get("uri", "")
            return web.json_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps({"resource": "content"})
                        }
                    ]
                }
            })

        else:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            })

    app.router.add_post("/", jsonrpc_handler)

    return app


@pytest.fixture
async def mock_mcp_server(mock_mcp_server_app, aiohttp_server):
    """Mock MCP Server rodando em porta aleatoria."""
    server = await aiohttp_server(mock_mcp_server_app)
    return server


# ============================================================================
# Fixtures de Configuracao
# ============================================================================

@pytest.fixture
def mock_settings_factory():
    """Factory para criar settings com configuracoes customizadas."""
    from unittest.mock import MagicMock

    def create_settings(**overrides):
        settings = MagicMock()
        settings.TOOL_EXECUTION_TIMEOUT_SECONDS = 300
        settings.TOOL_RETRY_MAX_ATTEMPTS = 3
        settings.MAX_CONCURRENT_TOOL_EXECUTIONS = 10
        settings.MCP_SERVER_TIMEOUT_SECONDS = 30
        settings.MCP_SERVER_MAX_RETRIES = 3
        settings.MCP_SERVER_CIRCUIT_BREAKER_THRESHOLD = 5
        settings.MCP_SERVER_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 60
        settings.MCP_SERVERS = {}

        for key, value in overrides.items():
            setattr(settings, key, value)

        return settings

    return create_settings


@pytest.fixture
def mock_metrics():
    """Mock de MCPToolCatalogMetrics para testes de integracao."""
    from unittest.mock import MagicMock

    metrics = MagicMock()
    metrics.record_tool_execution = MagicMock()
    metrics.record_mcp_fallback = MagicMock()
    metrics.record_feedback = MagicMock()
    metrics.record_selection = MagicMock()

    return metrics


@pytest.fixture
def mock_tool_registry():
    """Mock de ToolRegistry para testes de integracao."""
    from unittest.mock import AsyncMock, MagicMock

    registry = MagicMock()
    registry.update_tool_metrics = AsyncMock()
    registry.get_tool_by_id = AsyncMock(return_value=None)

    return registry
