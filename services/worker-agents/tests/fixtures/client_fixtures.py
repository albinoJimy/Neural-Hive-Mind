"""
Fixtures for HTTP mock servers simulating external services.

This module provides mock HTTP servers for integration testing:
- ArgoCD API
- OPA API
- GitHub Actions API
- SonarQube API

Uses httpx.MockTransport for simulating HTTP responses.
"""

import json
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


class MockHTTPServer:
    """Base class for mock HTTP servers."""

    def __init__(self):
        self.requests: List[httpx.Request] = []
        self.responses: Dict[str, Dict[str, Any]] = {}

    def add_response(
        self,
        method: str,
        path: str,
        status_code: int = 200,
        json_data: Optional[Dict] = None,
        text: str = '',
    ) -> None:
        """Add a mock response for a given method and path."""
        key = f'{method.upper()}:{path}'
        self.responses[key] = {
            'status_code': status_code,
            'json': json_data,
            'text': text,
        }

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle an incoming request and return a mock response."""
        self.requests.append(request)
        path = request.url.path
        method = request.method

        # Try exact match first
        key = f'{method}:{path}'
        if key in self.responses:
            resp = self.responses[key]
            content = json.dumps(resp['json']) if resp.get('json') else resp.get('text', '')
            return httpx.Response(
                status_code=resp['status_code'],
                content=content.encode(),
                headers={'content-type': 'application/json'} if resp.get('json') else {},
            )

        # Try pattern matching (simple prefix matching)
        for pattern, resp in self.responses.items():
            p_method, p_path = pattern.split(':', 1)
            if p_method == method and path.startswith(p_path.rstrip('/')):
                content = json.dumps(resp['json']) if resp.get('json') else resp.get('text', '')
                return httpx.Response(
                    status_code=resp['status_code'],
                    content=content.encode(),
                    headers={'content-type': 'application/json'} if resp.get('json') else {},
                )

        # Default 404 response
        return httpx.Response(status_code=404, content=b'{"error": "Not found"}')

    def get_transport(self) -> httpx.MockTransport:
        """Get an httpx.MockTransport for this server."""
        return httpx.MockTransport(self.handle_request)

    def get_client(self, **kwargs) -> httpx.AsyncClient:
        """Get an async client configured to use this mock server."""
        return httpx.AsyncClient(transport=self.get_transport(), **kwargs)

    def clear(self) -> None:
        """Clear recorded requests."""
        self.requests.clear()


class MockArgoCDServer(MockHTTPServer):
    """Mock ArgoCD API server."""

    def __init__(self, base_health_status: str = 'Healthy'):
        super().__init__()
        self.applications: Dict[str, Dict] = {}
        self.health_status = base_health_status
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup default ArgoCD API routes."""
        # Default responses will be dynamically generated based on applications dict
        pass

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle ArgoCD API requests."""
        self.requests.append(request)
        path = request.url.path
        method = request.method

        # POST /api/v1/applications - Create application
        if method == 'POST' and path == '/api/v1/applications':
            try:
                body = json.loads(request.content)
                name = body.get('metadata', {}).get('name', 'unknown')
                self.applications[name] = {
                    'metadata': body.get('metadata', {}),
                    'spec': body.get('spec', {}),
                    'status': {
                        'health': {'status': 'Progressing'},
                        'sync': {'status': 'OutOfSync'},
                    },
                }
                return httpx.Response(
                    status_code=201,
                    content=json.dumps(self.applications[name]).encode(),
                    headers={'content-type': 'application/json'},
                )
            except Exception as e:
                return httpx.Response(
                    status_code=400,
                    content=json.dumps({'error': str(e)}).encode(),
                )

        # GET /api/v1/applications/{name} - Get application
        if method == 'GET' and path.startswith('/api/v1/applications/'):
            name = path.split('/')[-1]
            if name in self.applications:
                app = self.applications[name]
                # Simulate health status progression
                app['status']['health']['status'] = self.health_status
                app['status']['sync']['status'] = 'Synced'
                return httpx.Response(
                    status_code=200,
                    content=json.dumps(app).encode(),
                    headers={'content-type': 'application/json'},
                )
            return httpx.Response(status_code=404, content=b'{"error": "Application not found"}')

        # DELETE /api/v1/applications/{name} - Delete application
        if method == 'DELETE' and path.startswith('/api/v1/applications/'):
            name = path.split('/')[-1]
            if name in self.applications:
                del self.applications[name]
                return httpx.Response(status_code=200, content=b'{}')
            return httpx.Response(status_code=404, content=b'{"error": "Application not found"}')

        return httpx.Response(status_code=404, content=b'{"error": "Not found"}')

    def set_health_status(self, status: str) -> None:
        """Set the health status for all applications."""
        self.health_status = status


class MockOPAServer(MockHTTPServer):
    """Mock OPA (Open Policy Agent) API server."""

    def __init__(self, default_allow: bool = True):
        super().__init__()
        self.policies: Dict[str, Callable[[Dict], Dict]] = {}
        self.default_allow = default_allow
        self._setup_default_policies()

    def _setup_default_policies(self) -> None:
        """Setup default OPA policies."""

        def default_policy(input_data: Dict) -> Dict:
            return {
                'allow': self.default_allow,
                'violations': [] if self.default_allow else [
                    {'message': 'Policy violation', 'rule': 'default'}
                ],
            }

        self.policies['policy/allow'] = default_policy
        self.policies['authz/allow'] = default_policy

    def add_policy(self, path: str, handler: Callable[[Dict], Dict]) -> None:
        """Add a custom policy handler."""
        self.policies[path] = handler

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle OPA API requests."""
        self.requests.append(request)
        path = request.url.path
        method = request.method

        # POST /v1/data/{policy_path} - Evaluate policy
        if method == 'POST' and path.startswith('/v1/data/'):
            policy_path = path.replace('/v1/data/', '')
            try:
                body = json.loads(request.content)
                input_data = body.get('input', {})

                if policy_path in self.policies:
                    result = self.policies[policy_path](input_data)
                else:
                    # Default policy response
                    result = {
                        'allow': self.default_allow,
                        'violations': [] if self.default_allow else [
                            {'message': 'Unknown policy', 'rule': policy_path}
                        ],
                    }

                return httpx.Response(
                    status_code=200,
                    content=json.dumps({'result': result}).encode(),
                    headers={'content-type': 'application/json'},
                )
            except Exception as e:
                return httpx.Response(
                    status_code=400,
                    content=json.dumps({'error': str(e)}).encode(),
                )

        return httpx.Response(status_code=404, content=b'{"error": "Not found"}')


class MockGitHubActionsServer(MockHTTPServer):
    """Mock GitHub Actions API server."""

    def __init__(self, default_conclusion: str = 'success'):
        super().__init__()
        self.workflows: Dict[str, Dict] = {}
        self.runs: Dict[str, Dict] = {}
        self.default_conclusion = default_conclusion
        self.run_counter = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle GitHub Actions API requests."""
        self.requests.append(request)
        path = request.url.path
        method = request.method

        # POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches
        if method == 'POST' and '/actions/workflows/' in path and path.endswith('/dispatches'):
            self.run_counter += 1
            run_id = f'run-{self.run_counter}'
            self.runs[run_id] = {
                'id': run_id,
                'status': 'completed',
                'conclusion': self.default_conclusion,
                'run_duration_ms': 120000,
            }
            return httpx.Response(status_code=204, content=b'')

        # GET /repos/{owner}/{repo}/actions/runs/{run_id}
        if method == 'GET' and '/actions/runs/' in path:
            run_id = path.split('/')[-1]
            if run_id in self.runs:
                return httpx.Response(
                    status_code=200,
                    content=json.dumps(self.runs[run_id]).encode(),
                    headers={'content-type': 'application/json'},
                )
            # Return simulated run for any unknown run_id
            return httpx.Response(
                status_code=200,
                content=json.dumps({
                    'id': run_id,
                    'status': 'completed',
                    'conclusion': self.default_conclusion,
                    'run_duration_ms': 120000,
                }).encode(),
                headers={'content-type': 'application/json'},
            )

        return httpx.Response(status_code=404, content=b'{"error": "Not found"}')


class MockSonarQubeServer(MockHTTPServer):
    """Mock SonarQube API server."""

    def __init__(self, quality_gate_status: str = 'OK'):
        super().__init__()
        self.quality_gate_status = quality_gate_status
        self.issues: List[Dict] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle SonarQube API requests."""
        self.requests.append(request)
        path = request.url.path
        method = request.method

        # POST /api/qualitygates/project_status
        if method == 'GET' and '/api/qualitygates/project_status' in path:
            return httpx.Response(
                status_code=200,
                content=json.dumps({
                    'projectStatus': {
                        'status': self.quality_gate_status,
                    }
                }).encode(),
                headers={'content-type': 'application/json'},
            )

        # GET /api/issues/search
        if method == 'GET' and '/api/issues/search' in path:
            return httpx.Response(
                status_code=200,
                content=json.dumps({
                    'issues': self.issues,
                    'total': len(self.issues),
                }).encode(),
                headers={'content-type': 'application/json'},
            )

        return httpx.Response(status_code=404, content=b'{"error": "Not found"}')


# Pytest Fixtures

@pytest.fixture
def mock_argocd_server():
    """Mock ArgoCD server with healthy status."""
    return MockArgoCDServer(base_health_status='Healthy')


@pytest.fixture
def mock_argocd_server_progressing():
    """Mock ArgoCD server with progressing status."""
    return MockArgoCDServer(base_health_status='Progressing')


@pytest.fixture
def mock_argocd_server_degraded():
    """Mock ArgoCD server with degraded status."""
    return MockArgoCDServer(base_health_status='Degraded')


@pytest.fixture
def mock_opa_server():
    """Mock OPA server that allows all requests."""
    return MockOPAServer(default_allow=True)


@pytest.fixture
def mock_opa_server_deny():
    """Mock OPA server that denies all requests."""
    return MockOPAServer(default_allow=False)


@pytest.fixture
def mock_github_actions_server():
    """Mock GitHub Actions server with success conclusion."""
    return MockGitHubActionsServer(default_conclusion='success')


@pytest.fixture
def mock_github_actions_server_failure():
    """Mock GitHub Actions server with failure conclusion."""
    return MockGitHubActionsServer(default_conclusion='failure')


@pytest.fixture
def mock_sonarqube_server():
    """Mock SonarQube server with OK quality gate."""
    return MockSonarQubeServer(quality_gate_status='OK')


@pytest.fixture
def mock_sonarqube_server_failed():
    """Mock SonarQube server with ERROR quality gate."""
    server = MockSonarQubeServer(quality_gate_status='ERROR')
    server.issues = [
        {'key': 'issue1', 'severity': 'CRITICAL', 'message': 'SQL Injection vulnerability'},
    ]
    return server
