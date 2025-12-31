"""
Configuracao de fixtures pytest para testes E2E do MCP Tool Catalog.

Fixtures especificas para testes E2E com mock MCP server real.
"""

import asyncio
import json
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web


# ============================================================================
# MCP Server Mock Fixtures
# ============================================================================

@pytest.fixture
def mcp_server_state():
    """Estado compartilhado do MCP Server mock."""
    return {
        "healthy": True,
        "slow_mode": False,
        "fail_mode": False,
        "request_count": 0,
        "last_request": None,
        "tools": [
            {
                "name": "trivy-scan",
                "description": "Container vulnerability scanner",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Image to scan"}
                    },
                    "required": ["target"]
                }
            },
            {
                "name": "sonarqube-analyze",
                "description": "Code quality analysis",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "projectKey": {"type": "string"},
                        "branch": {"type": "string"}
                    },
                    "required": ["projectKey"]
                }
            },
            {
                "name": "snyk-test",
                "description": "Dependency vulnerability testing",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "targetFile": {"type": "string"}
                    },
                    "required": ["targetFile"]
                }
            }
        ],
        "tool_results": {
            "trivy-scan": {
                "vulnerabilities": [],
                "summary": {"critical": 0, "high": 0, "medium": 2, "low": 5}
            },
            "sonarqube-analyze": {
                "qualityGate": "OK",
                "issues": {"bugs": 0, "vulnerabilities": 1, "codeSmells": 10}
            },
            "snyk-test": {
                "ok": True,
                "vulnerabilities": [],
                "dependencyCount": 42
            }
        }
    }


@pytest.fixture
def mcp_server_app(mcp_server_state):
    """Aplicacao aiohttp simulando MCP Server."""
    app = web.Application()

    async def handle_jsonrpc(request):
        """Handler principal JSON-RPC."""
        state = mcp_server_state
        state["request_count"] += 1

        try:
            body = await request.json()
            state["last_request"] = body
        except Exception:
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            }, status=400)

        # Modo de falha
        if state["fail_mode"]:
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": "Server error (fail mode)"},
                "id": body.get("id")
            }, status=500)

        # Modo lento
        if state["slow_mode"]:
            await asyncio.sleep(10)

        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id")

        # Handlers por metodo
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "mock-mcp-server", "version": "1.0.0"},
                "capabilities": {"tools": {"listChanged": True}}
            }
        elif method == "tools/list":
            result = {"tools": state["tools"]}
        elif method == "tools/call":
            tool_name = params.get("name", "unknown")
            arguments = params.get("arguments", {})

            if tool_name in state["tool_results"]:
                tool_result = state["tool_results"][tool_name].copy()
                tool_result["_arguments"] = arguments
                result = {
                    "content": [{"type": "text", "text": json.dumps(tool_result)}],
                    "isError": False
                }
            else:
                result = {
                    "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                    "isError": True
                }
        elif method == "notifications/initialized":
            return web.json_response({
                "jsonrpc": "2.0",
                "result": {},
                "id": request_id
            })
        else:
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id
            })

        return web.json_response({
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        })

    async def handle_health(request):
        """Health check endpoint."""
        if mcp_server_state["healthy"]:
            return web.json_response({
                "status": "healthy",
                "requests": mcp_server_state["request_count"]
            })
        return web.json_response({"status": "unhealthy"}, status=503)

    async def handle_control(request):
        """Endpoint de controle para manipular estado nos testes."""
        body = await request.json()
        action = body.get("action", "")

        if action == "set_healthy":
            mcp_server_state["healthy"] = body.get("value", True)
        elif action == "set_slow_mode":
            mcp_server_state["slow_mode"] = body.get("value", False)
        elif action == "set_fail_mode":
            mcp_server_state["fail_mode"] = body.get("value", False)
        elif action == "add_tool":
            mcp_server_state["tools"].append(body.get("tool", {}))
        elif action == "set_tool_result":
            tool_name = body.get("tool_name")
            result = body.get("result")
            if tool_name and result:
                mcp_server_state["tool_results"][tool_name] = result
        elif action == "reset":
            mcp_server_state["healthy"] = True
            mcp_server_state["slow_mode"] = False
            mcp_server_state["fail_mode"] = False
            mcp_server_state["request_count"] = 0
        elif action == "get_stats":
            return web.json_response(mcp_server_state)

        return web.json_response({"status": "ok", "state": {
            "healthy": mcp_server_state["healthy"],
            "slow_mode": mcp_server_state["slow_mode"],
            "fail_mode": mcp_server_state["fail_mode"],
            "request_count": mcp_server_state["request_count"]
        }})

    app.router.add_post("/", handle_jsonrpc)
    app.router.add_post("/jsonrpc", handle_jsonrpc)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/control", handle_control)

    return app


@pytest.fixture
async def mcp_server(mcp_server_app, aiohttp_server):
    """Mock MCP Server rodando."""
    return await aiohttp_server(mcp_server_app)


# ============================================================================
# Failing MCP Server Fixtures
# ============================================================================

@pytest.fixture
def failing_mcp_server_app():
    """MCP Server que sempre falha."""
    app = web.Application()

    async def always_fail(request):
        return web.json_response({
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": "Server unavailable"},
            "id": None
        }, status=503)

    app.router.add_post("/", always_fail)
    app.router.add_get("/health", lambda r: web.json_response(
        {"status": "unhealthy"}, status=503
    ))

    return app


@pytest.fixture
async def failing_mcp_server(failing_mcp_server_app, aiohttp_server):
    """Mock MCP Server que sempre falha."""
    return await aiohttp_server(failing_mcp_server_app)


# ============================================================================
# Flaky MCP Server Fixtures
# ============================================================================

@pytest.fixture
def flaky_mcp_server_app():
    """MCP Server que falha intermitentemente."""
    app = web.Application()
    app["request_count"] = 0

    async def flaky_handler(request):
        app["request_count"] += 1
        if app["request_count"] <= 2:
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": "Temporary failure"},
                "id": None
            }, status=500)

        body = await request.json()
        return web.json_response({
            "jsonrpc": "2.0",
            "result": {"success": True, "attempt": app["request_count"]},
            "id": body.get("id")
        })

    async def reset(request):
        app["request_count"] = 0
        return web.json_response({"status": "reset"})

    app.router.add_post("/", flaky_handler)
    app.router.add_post("/reset", reset)

    return app


@pytest.fixture
async def flaky_mcp_server(flaky_mcp_server_app, aiohttp_server):
    """Mock MCP Server flaky."""
    return await aiohttp_server(flaky_mcp_server_app)


# ============================================================================
# E2E Test Helpers
# ============================================================================

@pytest.fixture
def mcp_jsonrpc_request():
    """Helper para criar requisicoes JSON-RPC."""
    request_id = [0]

    def make_request(method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        request_id[0] += 1
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": request_id[0]
        }

    return make_request


@pytest.fixture
def assert_mcp_response():
    """Helper para validar respostas JSON-RPC."""
    def validate(response: Dict[str, Any], expected_id: int = None):
        assert response.get("jsonrpc") == "2.0"
        assert "result" in response or "error" in response
        if expected_id is not None:
            assert response.get("id") == expected_id
        return response.get("result")

    return validate
