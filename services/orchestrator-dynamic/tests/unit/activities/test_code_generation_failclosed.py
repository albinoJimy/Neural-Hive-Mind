"""Testes anti-verde-falso do G6 (generate_code) — Fase 3 j3-build-generate.

DoD Task 4: G6 gera código real via code-forge; "geração vazia/stub → FAILED".
O caminho de sucesso só é legítimo se houver um artefacto de código real
(artifact_id presente + código não-vazio). Geração que "completa" mas devolve
zero artefactos (ou artefacto sem id / sem código) é VERDE FALSO e deve FALHAR.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import src.activities.code_generation_activity as g6


def _make_client(get_payload: dict):
    """Cliente httpx mock: POST /generate -> 202 {request_id}; GET -> 200 get_payload."""
    client = AsyncMock()
    post_resp = MagicMock(status_code=202)
    post_resp.json = MagicMock(return_value={"request_id": "req-1"})
    client.post = AsyncMock(return_value=post_resp)
    get_resp = MagicMock(status_code=200)
    get_resp.json = MagicMock(return_value=get_payload)
    client.get = AsyncMock(return_value=get_resp)
    return client


_PLAN = {"plan_id": "plan-g6", "intent_id": "intent-g6", "parameters": {}}
_REQS = {"requirements_set_id": "REQ-1"}
_DOCS = {"documentation_id": "DOC-1"}


@pytest.fixture(autouse=True)
def _reset_deps():
    """Garante isolamento das dependências globais entre testes."""
    g6.set_code_generation_dependencies(None, None)
    yield
    g6.set_code_generation_dependencies(None, None)


class TestG6Success:
    @pytest.mark.asyncio
    async def test_real_artifact_completes(self):
        payload = {
            "status": "completed",
            "artifacts": [
                {
                    "artifact_type": "code",
                    "artifact_id": "art-123",
                    "language": "python",
                    "framework": "fastapi",
                    "lines_of_code": 42,
                }
            ],
            "code_preview": "from fastapi import FastAPI\napp = FastAPI()",
        }
        g6.set_code_generation_dependencies(_make_client(payload), None)
        result = await g6.generate_code(_REQS, _DOCS, _PLAN)
        assert result["status"] == "completed"
        assert result["code_artifact_id"] == "art-123"


class TestG6FailClosedOnEmpty:
    @pytest.mark.asyncio
    async def test_completed_with_no_artifacts_fails(self):
        """code-forge completa mas devolve zero artefactos -> FAILED (não verde falso)."""
        payload = {"status": "completed", "artifacts": [], "code_preview": ""}
        g6.set_code_generation_dependencies(_make_client(payload), None)
        with pytest.raises(Exception):
            await g6.generate_code(_REQS, _DOCS, _PLAN)

    @pytest.mark.asyncio
    async def test_completed_artifact_without_id_fails(self):
        """Artefacto sem artifact_id -> não há código real -> FAILED."""
        payload = {
            "status": "completed",
            "artifacts": [{"artifact_type": "code", "lines_of_code": 10}],
            "code_preview": "x",
        }
        g6.set_code_generation_dependencies(_make_client(payload), None)
        with pytest.raises(Exception):
            await g6.generate_code(_REQS, _DOCS, _PLAN)

    @pytest.mark.asyncio
    async def test_completed_empty_code_fails(self):
        """Artefacto com id mas sem código (0 linhas e sem preview) -> FAILED."""
        payload = {
            "status": "completed",
            "artifacts": [{"artifact_type": "code", "artifact_id": "art-9", "lines_of_code": 0}],
            "code_preview": "",
        }
        g6.set_code_generation_dependencies(_make_client(payload), None)
        with pytest.raises(Exception):
            await g6.generate_code(_REQS, _DOCS, _PLAN)


class TestG6FailClosedOnStatus:
    @pytest.mark.asyncio
    async def test_status_failed_raises(self):
        payload = {"status": "failed", "error": "boom", "artifacts": []}
        g6.set_code_generation_dependencies(_make_client(payload), None)
        with pytest.raises(Exception):
            await g6.generate_code(_REQS, _DOCS, _PLAN)
