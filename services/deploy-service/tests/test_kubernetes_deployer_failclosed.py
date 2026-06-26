"""Testes fail-closed do KubernetesDeployer — Fase 5 j3-build-generate, Task 6.1.

Cobrem os 3 fixes da Fase 5 (anti-verde-falso no G8), provados por E2E em cluster
mas sem cobertura unitária:
  - _verify_health_checks usa o selector real `app={service_name}` (não `app={deployment_name}`);
  - guarda `total_pods > 0`: 0 pods NÃO é "saudável" (fim do falso 0/0 == HEALTHY);
  - _wait_for_rollout interpola `--timeout={timeout}s` (era literal → kubectl falhava).

Ficheiro novo (não altera o contrato existente test_kubernetes_deployer.py — regra 7).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.models.deployment import HealthCheckSpec, HealthCheckStatus
from src.services.kubernetes_deployer import KubernetesDeployer


def _capture_kubectl(get_pods_stdout: bytes, returncode: int = 0):
    """Patcha create_subprocess_exec e captura os argv de cada chamada kubectl."""
    captured = []

    async def mock_create_process(*args, **kwargs):
        captured.append([str(a) for a in args])
        process = MagicMock()

        async def mock_communicate(input_data=None, **_kw):
            return (get_pods_stdout, b"")

        process.communicate = mock_communicate
        process.returncode = returncode
        return process

    return patch("asyncio.create_subprocess_exec", side_effect=mock_create_process), captured


@pytest.fixture()
def deployer():
    return KubernetesDeployer()


class TestHealthCheckFailClosed:
    @pytest.mark.asyncio
    async def test_zero_pods_is_not_healthy(self, deployer):
        """Selector não encontra pods (0/0) → PENDING, nunca HEALTHY (anti-verde-falso)."""
        patcher, _ = _capture_kubectl(b'{"items":[]}')
        with patcher:
            result = await deployer._verify_health_checks("svc", "ns", HealthCheckSpec())
        assert result.liveness == HealthCheckStatus.PENDING
        assert result.readiness == HealthCheckStatus.PENDING
        assert result.custom["total_pods"] == 0

    @pytest.mark.asyncio
    async def test_all_ready_pods_healthy(self, deployer):
        """Todos os pods Ready → HEALTHY."""
        pods = b'{"items":[{"status":{"conditions":[{"type":"Ready","status":"True"}]}}]}'
        patcher, _ = _capture_kubectl(pods)
        with patcher:
            result = await deployer._verify_health_checks("svc", "ns", HealthCheckSpec())
        assert result.liveness == HealthCheckStatus.HEALTHY
        assert result.custom["total_pods"] == 1
        assert result.custom["ready_pods"] == 1

    @pytest.mark.asyncio
    async def test_selector_uses_app_service_name(self, deployer):
        """O get pods filtra por `app={service_name}` (a label real do pod template)."""
        patcher, captured = _capture_kubectl(b'{"items":[]}')
        with patcher:
            await deployer._verify_health_checks("my-service", "ns", HealthCheckSpec())
        argv = captured[0]
        assert "-l=app=my-service" in argv


class TestRolloutTimeout:
    @pytest.mark.asyncio
    async def test_timeout_arg_is_interpolated(self, deployer):
        """--timeout tem de ser interpolado (`--timeout=600s`), não o literal `{timeout}s`."""
        patcher, captured = _capture_kubectl(b"")
        with patcher:
            await deployer._wait_for_rollout("dep", "ns", timeout=600)
        argv = captured[0]
        assert "--timeout=600s" in argv
        assert "--timeout={timeout}s" not in argv
