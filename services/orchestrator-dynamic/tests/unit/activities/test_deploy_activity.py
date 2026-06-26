"""Testes G8 (deploy_software / verify_deployment) — Fase 5 j3-build-generate, Task 6.1.

DoD Task 6: G8 faz deploy real; "deploy não-ready / healthcheck != 200 → FAILED".
Estes testes provam (anti-verde-falso):
  - deploy sucesso devolve status 'deployed' com service_url;
  - status=failed do deploy-service → RuntimeError (não COMPLETED simulado);
  - POST não-202 → RuntimeError;
  - verify_deployment reprova quando o status não é 'deployed' ou os health checks falham;
  - o cliente HTTP efémero (caminho degradado) é fechado (sem fuga de sockets).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.activities.code_generation_activity as cg
import src.activities.deploy_activity as g8

_PLAN = {"plan_id": "plan-g8", "version": "1.0.0", "parameters": {"namespace": "ns-g8"}}


def _make_client(get_payload: dict, post_status: int = 202):
    """Cliente httpx mock: POST /deployments -> 202 {deployment_id}; GET -> 200 get_payload."""
    client = AsyncMock()
    post_resp = MagicMock(status_code=post_status)
    post_resp.json = MagicMock(return_value={"deployment_id": "dep-1"})
    post_resp.text = ""
    client.post = AsyncMock(return_value=post_resp)
    get_resp = MagicMock(status_code=200)
    get_resp.json = MagicMock(return_value=get_payload)
    client.get = AsyncMock(return_value=get_resp)
    client.aclose = AsyncMock()
    return client


_DEPLOYED = {
    "status": "deployed",
    "kubernetes": {"deployment_name": "service-plan-g8", "namespace": "ns-g8", "replicas": 1,
                   "available_replicas": 1},
    "service": {"url": "http://service-plan-g8.ns-g8.svc.cluster.local:80", "port": 80},
    "health_checks": {"liveness": "healthy", "readiness": "healthy"},
}


@pytest.fixture(autouse=True)
def _reset_deps():
    """Isola o cliente HTTP global entre testes."""
    cg.set_code_generation_dependencies(None, None)
    yield
    cg.set_code_generation_dependencies(None, None)


class TestG8Success:
    @pytest.mark.asyncio
    async def test_deployed_returns_service_url(self):
        cg.set_code_generation_dependencies(_make_client(_DEPLOYED), None)
        result = await g8.deploy_software("ghcr.io/org/svc@sha256:abc", {}, _PLAN)
        assert result["status"] == "deployed"
        assert "svc.cluster.local" in result["service_url"]


class TestG8FailClosed:
    @pytest.mark.asyncio
    async def test_status_failed_raises(self):
        """deploy-service reporta failed → RuntimeError (anti-verde-falso)."""
        payload = {"status": "failed", "error": "rollout não ficou ready"}
        cg.set_code_generation_dependencies(_make_client(payload), None)
        with pytest.raises(RuntimeError, match="Deploy falhou"):
            await g8.deploy_software("img", {}, _PLAN)

    @pytest.mark.asyncio
    async def test_post_non_202_raises(self):
        cg.set_code_generation_dependencies(_make_client(_DEPLOYED, post_status=500), None)
        with pytest.raises(RuntimeError, match="Falha ao iniciar deploy"):
            await g8.deploy_software("img", {}, _PLAN)

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        client = _make_client({"status": "deploying"})
        with pytest.raises(TimeoutError):
            await g8._wait_for_deploy_completion(client, "dep-1", "plan-g8", "svc", max_wait=-1)


class TestVerifyDeployment:
    @pytest.mark.asyncio
    async def test_healthy_deployed_verified(self):
        result = await g8.verify_deployment(
            {
                "status": "deployed",
                "available_replicas": 1,
                "health_checks": {"liveness": "healthy", "readiness": "healthy"},
            }
        )
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_not_deployed_not_verified(self):
        result = await g8.verify_deployment({"status": "failed", "available_replicas": 0})
        assert result["verified"] is False

    @pytest.mark.asyncio
    async def test_unhealthy_not_verified(self):
        """healthcheck != healthy → não verificado (deploy não-saudável → FAILED)."""
        result = await g8.verify_deployment(
            {
                "status": "deployed",
                "available_replicas": 1,
                "health_checks": {"liveness": "pending", "readiness": "pending"},
            },
            require_healthy=True,
        )
        assert result["verified"] is False


class TestG8EphemeralClientClosed:
    @pytest.mark.asyncio
    async def test_ephemeral_client_closed_on_degraded(self):
        cg.set_code_generation_dependencies(None, None)  # força caminho degradado
        ephemeral = _make_client(_DEPLOYED)
        with patch.object(httpx, "AsyncClient", return_value=ephemeral):
            await g8.deploy_software("img", {}, _PLAN)
        ephemeral.aclose.assert_awaited()
