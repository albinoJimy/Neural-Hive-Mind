"""Shared fixtures for the Unified Gateway E2E tests (TICKETs 026/027/028).

Os testes em ``tests/e2e/test_flow_*.py`` validam o pipeline completo
``cliente → Unified Gateway → flow router → resposta`` sem subir Docker
compose. Em vez disso:

- A app FastAPI real do unified-gateway é importada (via path setup) e
  exercitada com ``httpx.AsyncClient``/``ASGITransport``.
- O ``NLUServiceClient.parse`` é monkeypatched para devolver o domain
  desejado, forçando o ``IntentClassifier`` a escolher o ``FlowType``
  correcto.
- O método HTTP de proxy do ``FlowRouter`` (``_proxy_request``) é
  monkeypatched para devolver uma resposta simulada do gateway downstream,
  evitando rede.

O nome do ficheiro começa por ``_`` para impedir o pytest de o coleccionar
como teste; é um módulo de utilidades importado pelos test files.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---- Path setup ------------------------------------------------------------
# A app vive em services/unified-gateway/src/main.py com imports `src.*`,
# que só resolvem se ``services/unified-gateway`` estiver no sys.path.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIFIED_GATEWAY_ROOT = _REPO_ROOT / "services" / "unified-gateway"
if str(_UNIFIED_GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(_UNIFIED_GATEWAY_ROOT))


# ---- Stubs reusáveis -------------------------------------------------------


class StubNLUResult:
    """Imita ``src.models.classification.NLUResult`` o suficiente para o
    ``IntentClassifier`` decidir o ``FlowType`` sem chamar o NLU Service."""

    def __init__(
        self,
        domain: str,
        confidence: float = 0.85,
        keywords: list[str] | None = None,
    ) -> None:
        self.text = ""
        self.domain = domain
        self.confidence = confidence
        self.entities: dict[str, str] = {}
        self.keywords = keywords or []


def _make_proxy_response(
    body: bytes = b'{"ok": true}',
    status_code: int = 200,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Devolve o dict que ``FlowRouter._proxy_request`` espera."""
    headers = {"content-type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return {
        "status_code": status_code,
        "headers": headers,
        "body": body,
    }


# ---- Fixtures --------------------------------------------------------------


class _StubResilienceNLU:
    """Stub para ``ResilienceNLUService`` evitando o circuit breaker (que tem
    incompatibilidade pré-existente com ``pybreaker>=1.0``).

    Apenas o ``parse`` é realmente exercitado no caminho do
    ``nhm_request_detailed``; nos testes principais a chamada não acontece
    porque o caminho usa o ``IntentClassifier`` directamente.
    """

    async def parse(self, *args, **kwargs):  # noqa: ARG002 — interface parity
        return StubNLUResult(domain="DOMAIN_UNKNOWN", confidence=0.5)


@pytest_asyncio.fixture
async def unified_gateway_app(monkeypatch: pytest.MonkeyPatch):
    """Importa a app real e desliga validações que precisam de infra externa.

    Faz purge de ``sys.modules['src*']`` antes do import porque há outros
    serviços (ex: pii-service) que também usam ``src`` como nome de package
    — sem o purge, um teste anterior pode deixar a app errada em cache.
    """
    # JWT obrigatório por defeito desde o fix #10; nos E2E não temos IdP, então
    # configuramos antes do import para que o middleware seja construído com
    # require_auth=False.
    monkeypatch.setenv("JWT_AUTH_REQUIRED", "false")
    # Kafka producer não é mandatório e fica fail-soft, mas evitamos
    # tentativas de conexão com broker inexistente.
    monkeypatch.setenv("KAFKA_ENABLED", "false")

    # Limpa qualquer "src" cacheado (pode ser de outro serviço com mesmo
    # nome de package — ver pii-service/src/).
    for cached in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[cached]
    # Garante prioridade do unified-gateway no sys.path.
    if str(_UNIFIED_GATEWAY_ROOT) in sys.path:
        sys.path.remove(str(_UNIFIED_GATEWAY_ROOT))
    sys.path.insert(0, str(_UNIFIED_GATEWAY_ROOT))

    # Importação tardia para que os env vars já estejam aplicados quando o
    # ``Settings`` é instanciado.
    from src.config.settings import get_settings  # type: ignore  # noqa: WPS433
    from src.main import app  # type: ignore  # noqa: WPS433
    from src.services.resilience import get_resilience_nlu  # type: ignore  # noqa: WPS433

    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Override do ResilienceNLUService — o construtor real instancia um
    # circuit breaker do neural_hive_resilience que tem incompatibilidade
    # com pybreaker>=1.0 (bug pré-existente). Não está no caminho crítico
    # destes testes.
    app.dependency_overrides[get_resilience_nlu] = lambda: _StubResilienceNLU()
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_resilience_nlu, None)


@pytest_asyncio.fixture
async def gateway_client(unified_gateway_app) -> AsyncClient:
    """``AsyncClient`` ligado à app via ASGI (sem rede)."""
    transport = ASGITransport(app=unified_gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def force_nlu_domain(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, float], None]:
    """Devolve um helper para fixar o domain devolvido pelo NLU client.

    Usar como::

        def test_x(force_nlu_domain): force_nlu_domain("BUSINESS", 0.9)
    """

    def _set(domain: str, confidence: float = 0.85) -> None:
        from src.services import nlu_client as ug_nlu_client  # type: ignore

        async def _fake_parse(*args, **kwargs) -> StubNLUResult:  # noqa: ARG001
            return StubNLUResult(domain=domain, confidence=confidence)

        # Substituímos o método na classe — o IntentClassifier guarda uma ref
        # ao instance singleton mas chama-a por instance.parse(...).
        monkeypatch.setattr(
            ug_nlu_client.NLUServiceClient,
            "parse",
            _fake_parse,
            raising=True,
        )
        # Reset do singleton do classifier para apanhar o NLU client mockado.
        ug_nlu_client._intent_classifier = None  # type: ignore[attr-defined]
        ug_nlu_client._nlu_client = None  # type: ignore[attr-defined]

    return _set


@pytest.fixture
def capture_proxy_target(monkeypatch: pytest.MonkeyPatch):
    """Substitui ``FlowRouter._proxy_request`` por uma sonda que captura o URL.

    Devolve um dict ``state`` com ``last_target_url`` e permite definir a
    resposta simulada::

        capture_proxy_target.set_response(b'{"data": 1}', status_code=200)
    """
    state: dict[str, Any] = {
        "last_target_url": None,
        "last_method": None,
        "last_headers": None,
        "last_body": None,
        "response": _make_proxy_response(),
    }

    from src.services import flow_router as ug_flow_router  # type: ignore

    async def _fake_proxy_request(
        self,  # noqa: ARG001 — bound method
        *,
        target_url: str,
        method: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> dict[str, Any]:
        state["last_target_url"] = target_url
        state["last_method"] = method
        state["last_headers"] = headers
        state["last_body"] = body
        return state["response"]

    async def _fake_is_healthy(self, flow_type) -> bool:  # noqa: ARG001
        return True

    monkeypatch.setattr(
        ug_flow_router.FlowRouter,
        "_proxy_request",
        _fake_proxy_request,
        raising=True,
    )
    monkeypatch.setattr(
        ug_flow_router.FlowRouter,
        "_is_gateway_healthy",
        _fake_is_healthy,
        raising=True,
    )

    def set_response(
        body: bytes = b'{"ok": true}',
        status_code: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        state["response"] = _make_proxy_response(
            body=body, status_code=status_code, extra_headers=extra_headers
        )

    state["set_response"] = set_response
    return state
