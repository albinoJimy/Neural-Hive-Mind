"""
Testes de integracao para RESTAdapter com mock HTTP server real.

Estes testes usam um servidor HTTP real (aiohttp.web) para validar
o comportamento do RESTAdapter em cenarios proximos a producao.
"""

import asyncio
import json
from typing import Any, Dict

import pytest
from aiohttp import web

from src.adapters.rest_adapter import RESTAdapter


# ============================================================================
# Fixtures de Mock HTTP Server
# ============================================================================

@pytest.fixture
def sonarqube_mock_app():
    """Mock da API SonarQube."""
    app = web.Application()

    async def analyze_handler(request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return web.json_response(
                {"error": "Unauthorized"},
                status=401
            )

        body = await request.json()
        return web.json_response({
            "taskId": "AXd9_xyz123",
            "status": "SUCCESS",
            "project": body.get("projectKey"),
            "qualityGate": "OK",
            "issues": {
                "bugs": 0,
                "vulnerabilities": 2,
                "codeSmells": 15
            }
        })

    async def issues_handler(request):
        project = request.query.get("componentKeys", "unknown")
        return web.json_response({
            "total": 17,
            "issues": [
                {
                    "key": "issue-1",
                    "severity": "MAJOR",
                    "type": "CODE_SMELL",
                    "component": project
                }
            ],
            "paging": {"pageIndex": 1, "pageSize": 100, "total": 17}
        })

    async def health_handler(request):
        return web.json_response({"status": "UP"})

    app.router.add_post("/api/analysis", analyze_handler)
    app.router.add_get("/api/issues/search", issues_handler)
    app.router.add_get("/api/system/health", health_handler)

    return app


@pytest.fixture
def snyk_mock_app():
    """Mock da API Snyk."""
    app = web.Application()

    async def test_handler(request):
        body = await request.json()
        return web.json_response({
            "ok": True,
            "issues": {
                "vulnerabilities": [],
                "licenses": []
            },
            "dependencyCount": 42,
            "packageManager": "pip",
            "summary": body.get("targetFile", "requirements.txt")
        })

    async def projects_handler(request):
        return web.json_response({
            "projects": [
                {"id": "proj-1", "name": "my-project"},
                {"id": "proj-2", "name": "another-project"}
            ]
        })

    app.router.add_post("/v1/test", test_handler)
    app.router.add_get("/v1/org/{orgId}/projects", projects_handler)

    return app


@pytest.fixture
def checkmarx_mock_app():
    """Mock da API Checkmarx."""
    app = web.Application()

    async def scan_handler(request):
        body = await request.json()
        return web.json_response({
            "id": "scan-123",
            "status": "Completed",
            "projectName": body.get("projectName"),
            "highVulnerabilities": 0,
            "mediumVulnerabilities": 3,
            "lowVulnerabilities": 12
        })

    async def results_handler(request):
        scan_id = request.match_info.get("scanId")
        return web.json_response({
            "scanId": scan_id,
            "results": [
                {"severity": "Medium", "name": "SQL Injection Risk"},
                {"severity": "Low", "name": "Unused Variable"}
            ]
        })

    app.router.add_post("/api/scans", scan_handler)
    app.router.add_get("/api/scans/{scanId}/results", results_handler)

    return app


@pytest.fixture
async def sonarqube_server(sonarqube_mock_app, aiohttp_server):
    """Mock SonarQube server."""
    return await aiohttp_server(sonarqube_mock_app)


@pytest.fixture
async def snyk_server(snyk_mock_app, aiohttp_server):
    """Mock Snyk server."""
    return await aiohttp_server(snyk_mock_app)


@pytest.fixture
async def checkmarx_server(checkmarx_mock_app, aiohttp_server):
    """Mock Checkmarx server."""
    return await aiohttp_server(checkmarx_mock_app)


# ============================================================================
# Testes de Integracao com SonarQube Mock
# ============================================================================

class TestSonarQubeIntegration:
    """Testes de integracao com API SonarQube."""

    @pytest.mark.asyncio
    async def test_sonarqube_analyze_success(self, sonarqube_server):
        """Testa chamada de analise SonarQube."""
        adapter = RESTAdapter(timeout_seconds=30, max_retries=1)

        result = await adapter.execute(
            tool_id="sonarqube-001",
            tool_name="sonarqube",
            command=f"http://{sonarqube_server.host}:{sonarqube_server.port}/api/analysis",
            parameters={
                "body": {"projectKey": "my-project:main"}
            },
            context={
                "http_method": "POST",
                "auth_token": "sonar-token-123"
            }
        )

        assert result.success is True
        response_data = json.loads(result.output)
        assert response_data["status"] == "SUCCESS"
        assert response_data["qualityGate"] == "OK"
        assert "issues" in response_data

    @pytest.mark.asyncio
    async def test_sonarqube_unauthorized(self, sonarqube_server):
        """Testa erro de autenticacao SonarQube."""
        adapter = RESTAdapter(timeout_seconds=30, max_retries=1)

        result = await adapter.execute(
            tool_id="sonarqube-001",
            tool_name="sonarqube",
            command=f"http://{sonarqube_server.host}:{sonarqube_server.port}/api/analysis",
            parameters={"body": {"projectKey": "test"}},
            context={"http_method": "POST"}  # Sem auth_token
        )

        assert result.success is False
        assert result.exit_code == 401

    @pytest.mark.asyncio
    async def test_sonarqube_issues_search(self, sonarqube_server):
        """Testa busca de issues SonarQube."""
        adapter = RESTAdapter(timeout_seconds=30, max_retries=1)

        result = await adapter.execute(
            tool_id="sonarqube-issues",
            tool_name="sonarqube",
            command=f"http://{sonarqube_server.host}:{sonarqube_server.port}/api/issues/search",
            parameters={
                "query": {"componentKeys": "my-project"}
            },
            context={"http_method": "GET"}
        )

        assert result.success is True
        response_data = json.loads(result.output)
        assert response_data["total"] == 17
        assert len(response_data["issues"]) == 1

    @pytest.mark.asyncio
    async def test_sonarqube_health_check(self, sonarqube_server):
        """Testa health check SonarQube."""
        adapter = RESTAdapter(timeout_seconds=10, max_retries=1)

        result = await adapter.execute(
            tool_id="sonarqube-health",
            tool_name="sonarqube",
            command=f"http://{sonarqube_server.host}:{sonarqube_server.port}/api/system/health",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is True
        response_data = json.loads(result.output)
        assert response_data["status"] == "UP"


# ============================================================================
# Testes de Integracao com Snyk Mock
# ============================================================================

class TestSnykIntegration:
    """Testes de integracao com API Snyk."""

    @pytest.mark.asyncio
    async def test_snyk_test_success(self, snyk_server):
        """Testa scan de vulnerabilidades Snyk."""
        adapter = RESTAdapter(timeout_seconds=30, max_retries=1)

        result = await adapter.execute(
            tool_id="snyk-001",
            tool_name="snyk",
            command=f"http://{snyk_server.host}:{snyk_server.port}/v1/test",
            parameters={
                "body": {"targetFile": "requirements.txt"}
            },
            context={"http_method": "POST"}
        )

        assert result.success is True
        response_data = json.loads(result.output)
        assert response_data["ok"] is True
        assert response_data["dependencyCount"] == 42

    @pytest.mark.asyncio
    async def test_snyk_list_projects(self, snyk_server):
        """Testa listagem de projetos Snyk."""
        adapter = RESTAdapter(timeout_seconds=30, max_retries=1)

        result = await adapter.execute(
            tool_id="snyk-projects",
            tool_name="snyk",
            command=f"http://{snyk_server.host}:{snyk_server.port}/v1/org/my-org/projects",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is True
        response_data = json.loads(result.output)
        assert len(response_data["projects"]) == 2


# ============================================================================
# Testes de Integracao com Checkmarx Mock
# ============================================================================

class TestCheckmarxIntegration:
    """Testes de integracao com API Checkmarx."""

    @pytest.mark.asyncio
    async def test_checkmarx_scan_success(self, checkmarx_server):
        """Testa scan Checkmarx."""
        adapter = RESTAdapter(timeout_seconds=30, max_retries=1)

        result = await adapter.execute(
            tool_id="checkmarx-001",
            tool_name="checkmarx",
            command=f"http://{checkmarx_server.host}:{checkmarx_server.port}/api/scans",
            parameters={
                "body": {"projectName": "my-project"}
            },
            context={"http_method": "POST"}
        )

        assert result.success is True
        response_data = json.loads(result.output)
        assert response_data["status"] == "Completed"
        assert response_data["highVulnerabilities"] == 0

    @pytest.mark.asyncio
    async def test_checkmarx_get_results(self, checkmarx_server):
        """Testa obtencao de resultados Checkmarx."""
        adapter = RESTAdapter(timeout_seconds=30, max_retries=1)

        result = await adapter.execute(
            tool_id="checkmarx-results",
            tool_name="checkmarx",
            command=f"http://{checkmarx_server.host}:{checkmarx_server.port}/api/scans/scan-123/results",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is True
        response_data = json.loads(result.output)
        assert response_data["scanId"] == "scan-123"
        assert len(response_data["results"]) == 2


# ============================================================================
# Testes de Retry com Mock Server
# ============================================================================

class TestRetryWithRealServer:
    """Testes de retry com servidor real."""

    @pytest.fixture
    def flaky_app(self):
        """App que falha nas primeiras requisicoes."""
        app = web.Application()
        app["request_count"] = 0

        async def flaky_handler(request):
            app["request_count"] += 1
            if app["request_count"] < 3:
                return web.json_response(
                    {"error": "Temporary failure"},
                    status=500
                )
            return web.json_response({"success": True})

        app.router.add_get("/flaky", flaky_handler)
        return app

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_third_attempt(self, flaky_app, aiohttp_server):
        """Testa que retry funciona com servidor flaky."""
        server = await aiohttp_server(flaky_app)
        adapter = RESTAdapter(timeout_seconds=10, max_retries=3)

        result = await adapter.execute(
            tool_id="flaky-001",
            tool_name="flaky",
            command=f"http://{server.host}:{server.port}/flaky",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is True
        assert result.metadata.get("attempt") == 3


# ============================================================================
# Testes de Timeout com Mock Server
# ============================================================================

class TestTimeoutWithRealServer:
    """Testes de timeout com servidor real."""

    @pytest.fixture
    def slow_app(self):
        """App com endpoint lento."""
        app = web.Application()

        async def slow_handler(request):
            await asyncio.sleep(10)  # Muito lento
            return web.json_response({"slow": True})

        app.router.add_get("/slow", slow_handler)
        return app

    @pytest.mark.asyncio
    async def test_timeout_triggers(self, slow_app, aiohttp_server):
        """Testa que timeout e acionado corretamente."""
        server = await aiohttp_server(slow_app)
        adapter = RESTAdapter(timeout_seconds=1, max_retries=1)

        result = await adapter.execute(
            tool_id="slow-001",
            tool_name="slow",
            command=f"http://{server.host}:{server.port}/slow",
            parameters={"query": {}},
            context={"http_method": "GET"}
        )

        assert result.success is False
        assert "Timeout" in result.error
