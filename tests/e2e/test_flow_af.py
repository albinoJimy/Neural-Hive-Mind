"""E2E test for Flow A-F (Cognitive Pipeline) — TICKET-026.

Valida o pipeline completo:
    cliente -> Unified Gateway -> NLU classification (BUSINESS) ->
    FlowRouter -> gateway-intencoes:8000 -> resposta.

NLU e o proxy HTTP downstream são monkeypatched (ver
``_unified_gateway_helpers.py``); o resto da app FastAPI corre real.
"""

from __future__ import annotations

import pytest

# Reexporta as fixtures partilhadas para este módulo (pytest precisa que
# estejam no namespace deste ficheiro ou num conftest).
from tests.e2e._unified_gateway_helpers import (  # noqa: F401
    capture_proxy_target,
    force_nlu_domain,
    gateway_client,
    unified_gateway_app,
)


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_flow_af_routes_to_gateway_intencoes(
    gateway_client,
    force_nlu_domain,
    capture_proxy_target,
) -> None:
    force_nlu_domain("BUSINESS", confidence=0.92)
    capture_proxy_target["set_response"](
        body=b'{"flow": "A-F", "result": "dashboard"}',
        status_code=200,
    )

    response = await gateway_client.post(
        "/api/v1/nhm/request",
        json={"input": "consultar dashboard de vendas mensal", "language": "pt"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    # Classificação correcta
    assert payload["flow_type"] == "A-F"
    assert payload["status"] == "success"

    # Proxy foi para o gateway A-F
    assert capture_proxy_target["last_target_url"], "FlowRouter não foi chamado"
    assert "gateway-intencoes" in capture_proxy_target["last_target_url"]
    assert payload["gateway_used"] == "gateway-intencoes"

    # Body original do cliente foi propagado downstream
    assert capture_proxy_target["last_body"] == b"consultar dashboard de vendas mensal"

    # Status tracking não dependeu de Redis (fail-soft)
    assert "request_id" in payload


async def test_flow_af_falls_back_when_explicit_flow_overrides_classifier(
    gateway_client,
    force_nlu_domain,
    capture_proxy_target,
) -> None:
    """Quando o cliente fornece flow_type=A-F, o classifier é bypassado."""
    # NLU diria TECHNICAL → G; o explicit override deve vencer.
    force_nlu_domain("TECHNICAL", confidence=0.95)
    capture_proxy_target["set_response"](b'{"override": true}')

    response = await gateway_client.post(
        "/api/v1/nhm/request",
        json={
            "input": "qualquer texto",
            "flow_type": "A-F",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["flow_type"] == "A-F"
    assert "gateway-intencoes" in capture_proxy_target["last_target_url"]
