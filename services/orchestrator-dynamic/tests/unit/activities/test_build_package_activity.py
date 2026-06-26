"""Testes G7 (build_package) — Fase 4 j3-build-generate, Task 5.1.

DoD Task 5: G7 constrói imagem real via Kaniko e publica no GHCR; "build falhado /
imagem não-puxável → FAILED". Estes testes provam (anti-verde-falso):
  - build sucesso devolve a imagem/digest publicados (push_to_registry True por omissão);
  - status=failed do code-forge → RuntimeError (não COMPLETED simulado);
  - timeout → TimeoutError;
  - POST não-201 → RuntimeError (nenhum ramo de simulação devolve "completed");
  - o cliente HTTP efémero (caminho degradado) é fechado (sem fuga de sockets);
  - validate_build_quality reprova quality score baixo / vulnerabilidade crítica.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import src.activities.build_package_activity as g7
import src.activities.code_generation_activity as cg

_PLAN = {"plan_id": "plan-g7", "version": "1.0.0", "parameters": {}}


def _make_client(get_payload: dict, post_status: int = 201):
    """Cliente httpx mock: POST /pipelines -> 201 {pipeline_id}; GET -> 200 get_payload."""
    client = AsyncMock()
    post_resp = MagicMock(status_code=post_status)
    post_resp.json = MagicMock(return_value={"pipeline_id": "pipe-1"})
    post_resp.text = ""
    client.post = AsyncMock(return_value=post_resp)
    get_resp = MagicMock(status_code=200)
    get_resp.json = MagicMock(return_value=get_payload)
    client.get = AsyncMock(return_value=get_resp)
    client.aclose = AsyncMock()
    return client


_COMPLETED = {
    "status": "completed",
    "stage": "container_build",
    "quality_score": 0.8,
    "artifacts": [
        {
            "artifact_type": "container_image",
            "content_uri": "ghcr.io/org/svc@sha256:abc",
            "metadata": {"tag": "service-plan-g7:1.0.0"},
        }
    ],
}


@pytest.fixture(autouse=True)
def _reset_deps():
    """Isola o cliente HTTP global entre testes."""
    cg.set_code_generation_dependencies(None, None)
    yield
    cg.set_code_generation_dependencies(None, None)


class TestG7Success:
    @pytest.mark.asyncio
    async def test_completed_returns_published_image(self):
        cg.set_code_generation_dependencies(_make_client(_COMPLETED), None)
        result = await g7.build_package("art-1", _PLAN)
        assert result["status"] == "completed"
        assert result["container_image"] == "ghcr.io/org/svc@sha256:abc"
        assert result["image_tag"] == "service-plan-g7:1.0.0"

    @pytest.mark.asyncio
    async def test_push_to_registry_default_true(self):
        """J3_BUILD: a imagem TEM de ser publicada → push_to_registry default True."""
        client = _make_client(_COMPLETED)
        cg.set_code_generation_dependencies(client, None)
        await g7.build_package("art-1", _PLAN)
        payload = client.post.call_args.kwargs["json"]
        assert payload["parameters"]["push_to_registry"] is True


class TestG7FailClosed:
    @pytest.mark.asyncio
    async def test_status_failed_raises(self):
        """code-forge reporta failed → RuntimeError (anti-verde-falso)."""
        payload = {"status": "failed", "error": "kaniko push DENIED"}
        cg.set_code_generation_dependencies(_make_client(payload), None)
        with pytest.raises(RuntimeError, match="Build falhou"):
            await g7.build_package("art-1", _PLAN)

    @pytest.mark.asyncio
    async def test_post_non_201_raises(self):
        """Falha a iniciar o pipeline → RuntimeError (sem ramo de simulação)."""
        cg.set_code_generation_dependencies(_make_client(_COMPLETED, post_status=500), None)
        with pytest.raises(RuntimeError, match="Falha ao iniciar build"):
            await g7.build_package("art-1", _PLAN)

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        """Pipeline nunca termina dentro do limite → TimeoutError."""
        client = _make_client({"status": "running", "stage": "container_build"})
        with pytest.raises(TimeoutError):
            await g7._wait_for_build_completion(client, "pipe-1", "plan-g7", "art-1", max_wait=-1)


class TestG7EphemeralClientClosed:
    @pytest.mark.asyncio
    async def test_ephemeral_client_closed_on_degraded(self):
        """Sem cliente injetado, o efémero criado é fechado (sem fuga de sockets)."""
        cg.set_code_generation_dependencies(None, None)  # força caminho degradado
        ephemeral = _make_client(_COMPLETED)
        with patch.object(httpx, "AsyncClient", return_value=ephemeral):
            await g7.build_package("art-1", _PLAN)
        ephemeral.aclose.assert_awaited()


class TestValidateBuildQuality:
    @pytest.mark.asyncio
    async def test_low_quality_score_not_approved(self):
        result = await g7.validate_build_quality({"quality_score": 0.1})
        assert result["approved"] is False

    @pytest.mark.asyncio
    async def test_critical_vulnerability_not_approved(self):
        build = {
            "quality_score": 0.9,
            "test_results": {"passed": 10, "total": 10},
            "security_scan": {"vulnerabilities": {"critical": 1}},
        }
        result = await g7.validate_build_quality(build)
        assert result["approved"] is False

    @pytest.mark.asyncio
    async def test_good_build_approved(self):
        build = {
            "quality_score": 0.9,
            "test_results": {"passed": 10, "total": 10},
            "security_scan": {"vulnerabilities": {}},
        }
        result = await g7.validate_build_quality(build)
        assert result["approved"] is True
