"""E2E test for Flow G (Code Generation) — TICKET-027.

Domínio TECHNICAL → ``FlowType.G`` → proxy para
``requirements-engineering:8010``.
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


async def test_flow_g_routes_to_requirements_engineering(
    gateway_client,
    force_nlu_domain,
    capture_proxy_target,
) -> None:
    force_nlu_domain("TECHNICAL", confidence=0.88)
    capture_proxy_target["set_response"](
        body=b'{"flow": "G", "code": "generated"}',
        status_code=200,
    )

    response = await gateway_client.post(
        "/api/v1/nhm/request",
        json={"input": "gerar código para criar um novo serviço REST", "language": "pt"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["flow_type"] == "G"
    assert payload["status"] == "success"
    assert "requirements-engineering" in capture_proxy_target["last_target_url"]
    assert payload["gateway_used"] == "requirements-engineering"
    assert capture_proxy_target["last_method"] == "POST"


async def test_flow_g_propagates_tenant_headers_downstream(
    gateway_client,
    force_nlu_domain,
    capture_proxy_target,
) -> None:
    """Headers ``X-Tenant-ID``/``X-User-ID`` devem ir downstream (INV-7)."""
    force_nlu_domain("TECHNICAL", confidence=0.9)
    capture_proxy_target["set_response"](b'{"ok": true}')

    response = await gateway_client.post(
        "/api/v1/nhm/request",
        json={"input": "criar novo app de inventário"},
        headers={
            "X-Tenant-ID": "tenant-acme",
            "X-User-ID": "user-42",
        },
    )

    assert response.status_code == 200, response.text
    forwarded = capture_proxy_target["last_headers"] or {}
    # Os headers podem ser case-folded conforme o middleware HTTP.
    lower_keys = {k.lower(): v for k, v in forwarded.items()}
    assert lower_keys.get("x-tenant-id") == "tenant-acme"
    assert lower_keys.get("x-user-id") == "user-42"
