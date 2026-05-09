"""E2E test for Flow H (Migration) — TICKET-028.

Domínio INFRASTRUCTURE → ``FlowType.H`` → proxy para
``doc-ingestion:8018``.
"""

from __future__ import annotations

import pytest

from tests.e2e._unified_gateway_helpers import (  # noqa: F401
    capture_proxy_target,
    force_nlu_domain,
    gateway_client,
    unified_gateway_app,
)


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_flow_h_routes_to_doc_ingestion(
    gateway_client,
    force_nlu_domain,
    capture_proxy_target,
) -> None:
    force_nlu_domain("INFRASTRUCTURE", confidence=0.83)
    capture_proxy_target["set_response"](
        body=b'{"flow": "H", "migration": "ok"}',
        status_code=200,
    )

    response = await gateway_client.post(
        "/api/v1/nhm/request",
        json={"input": "migrar sistema legado para nova plataforma", "language": "pt"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["flow_type"] == "H"
    assert payload["status"] == "success"
    assert "doc-ingestion" in capture_proxy_target["last_target_url"]
    assert payload["gateway_used"] == "doc-ingestion"


async def test_flow_h_returns_error_envelope_on_downstream_failure(
    gateway_client,
    force_nlu_domain,
    capture_proxy_target,
) -> None:
    """Falha downstream (5xx) deve produzir resposta com status != success."""
    force_nlu_domain("INFRASTRUCTURE", confidence=0.9)
    capture_proxy_target["set_response"](
        body=b'{"error": "internal"}',
        status_code=500,
    )

    response = await gateway_client.post(
        "/api/v1/nhm/request",
        json={"input": "atualizar código legado para novo runtime"},
    )

    # O Unified Gateway responde 200 com envelope unificado mesmo quando o
    # downstream devolve 5xx — o status do envelope reflecte a falha.
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["flow_type"] == "H"
    assert payload["status"] != "success"
