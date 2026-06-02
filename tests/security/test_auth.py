"""Security tests for the Unified Gateway JWT authentication middleware.

Cobre o ``JWTAuthMiddleware`` em ``services/unified-gateway/src/middleware/jwt_auth.py``
quando ``JWT_AUTH_REQUIRED=true`` (default desde o fix recente). Estes testes
asseguram que pedidos não autenticados são bloqueados, tokens malformados são
rejeitados, e que tokens JWT válidos têm os claims (``sub`` / ``tenant_id``)
propagados downstream via headers (INV-7).

Relacionado com TICKET-030 (Security/Auth Coverage).

Notas de implementação:
    * O middleware faz ``import jwt`` (PyJWT, não python-jose). Por isso, os
      tokens são gerados com ``jwt.encode`` da PyJWT.
    * Em ambiente não-produção, ``verify_signature`` é ``False`` mas ``verify_exp``
      e ``require=["sub"]`` continuam activos — qualquer JWT bem-formado com
      claim ``sub`` válido e não expirado passa.
    * Os helpers em ``tests/e2e/_unified_gateway_helpers.py`` fixam
      ``JWT_AUTH_REQUIRED=false``; aqui criamos uma fixture própria que recarrega
      ``src.main`` com ``JWT_AUTH_REQUIRED=true`` para validar o caminho seguro.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Reaproveitamos os stubs / utilitários do módulo de helpers E2E (são funções
# puras, não fixtures partilhadas — por isso o import é seguro).
from tests.e2e._unified_gateway_helpers import (  # noqa: E402
    StubNLUResult,
    _UNIFIED_GATEWAY_ROOT,
    _StubResilienceNLU,
    _make_proxy_response,
)

# Garante que o pacote ``src`` do unified-gateway é importável.
if str(_UNIFIED_GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(_UNIFIED_GATEWAY_ROOT))


pytestmark = [pytest.mark.security, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers locais
# ---------------------------------------------------------------------------


_SECRET = "change-me"  # default do JWT_SECRET nas settings
_ALG = "HS256"


def _make_valid_jwt(
    sub: str = "u1",
    tenant_id: str | None = "t1",
    extra: dict[str, Any] | None = None,
    exp_delta: timedelta = timedelta(minutes=5),
) -> str:
    """Gera um JWT HS256 válido (com ``sub`` e ``exp`` no futuro)."""
    payload: dict[str, Any] = {
        "sub": sub,
        "exp": datetime.now(timezone.utc) + exp_delta,
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if extra:
        payload.update(extra)
    return pyjwt.encode(payload, _SECRET, algorithm=_ALG)


def _purge_unified_gateway_modules() -> None:
    """Remove módulos cacheados do unified-gateway para forçar reimport.

    Necessário porque ``src.main`` instancia ``settings = get_settings()`` no
    nível do módulo e regista o ``JWTAuthMiddleware`` com ``require_auth``
    fixo na app — uma reimportação limpa é a forma mais robusta de mudar o
    valor entre cenários de teste.
    """
    to_drop = [name for name in sys.modules if name == "src" or name.startswith("src.")]
    for name in to_drop:
        del sys.modules[name]


# ---------------------------------------------------------------------------
# Fixtures locais (não usamos as do helpers porque queremos JWT_AUTH_REQUIRED=true)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def secure_gateway_app(monkeypatch: pytest.MonkeyPatch):
    """Importa a app real com ``JWT_AUTH_REQUIRED=true``.

    Diferente do ``unified_gateway_app`` em ``_unified_gateway_helpers``, este
    fixture activa a autenticação obrigatória — necessário para validar o
    comportamento de bloqueio do middleware.
    """
    monkeypatch.setenv("JWT_AUTH_REQUIRED", "true")
    monkeypatch.setenv("KAFKA_ENABLED", "false")
    monkeypatch.setenv("ENVIRONMENT", "development")  # evita verify_signature=True
    monkeypatch.setenv("JWT_SECRET", _SECRET)

    # Limpamos módulos do unified-gateway para que o reimport apanhe os env vars.
    _purge_unified_gateway_modules()

    from src.config.settings import get_settings  # type: ignore  # noqa: WPS433
    from src.main import app  # type: ignore  # noqa: WPS433
    from src.services.resilience import get_resilience_nlu  # type: ignore  # noqa: WPS433

    get_settings.cache_clear()  # type: ignore[attr-defined]

    app.dependency_overrides[get_resilience_nlu] = lambda: _StubResilienceNLU()
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_resilience_nlu, None)
        # Limpa para não contaminar testes seguintes que reimportem com
        # JWT_AUTH_REQUIRED=false.
        _purge_unified_gateway_modules()


@pytest_asyncio.fixture
async def secure_client(secure_gateway_app) -> AsyncClient:
    transport = ASGITransport(app=secure_gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def force_nlu_domain_secure(monkeypatch: pytest.MonkeyPatch):
    """Versão local do ``force_nlu_domain`` que opera sobre o módulo recarregado."""

    def _set(domain: str, confidence: float = 0.85) -> None:
        from src.services import nlu_client as ug_nlu_client  # type: ignore

        async def _fake_parse(*args, **kwargs) -> StubNLUResult:  # noqa: ARG001
            return StubNLUResult(domain=domain, confidence=confidence)

        monkeypatch.setattr(
            ug_nlu_client.NLUServiceClient,
            "parse",
            _fake_parse,
            raising=True,
        )
        ug_nlu_client._intent_classifier = None  # type: ignore[attr-defined]
        ug_nlu_client._nlu_client = None  # type: ignore[attr-defined]

    return _set


@pytest.fixture
def patch_actor_user_id(monkeypatch: pytest.MonkeyPatch):
    """No-op fixture mantida para compatibilidade.

    A versão original instalava uma property ``user_id`` em ``ActorContext``
    como workaround do bug em ``request.py`` que lia ``actor.user_id`` num
    campo inexistente. O bug foi corrigido (commit subsequente lê
    ``actor.actor_id``); a fixture fica como no-op para não quebrar testes
    que ainda a referenciam.
    """
    return None


@pytest.fixture
def capture_proxy_target_secure(monkeypatch: pytest.MonkeyPatch):
    """Versão local do ``capture_proxy_target`` que opera sobre o módulo recarregado."""
    state: dict[str, Any] = {
        "last_target_url": None,
        "last_method": None,
        "last_headers": None,
        "last_body": None,
        "response": _make_proxy_response(),
    }

    from src.services import flow_router as ug_flow_router  # type: ignore

    async def _fake_proxy_request(
        self,  # noqa: ARG001
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


# ---------------------------------------------------------------------------
# 1. Pedido sem token → 401
# ---------------------------------------------------------------------------


async def test_request_without_token_returns_401(secure_client: AsyncClient) -> None:
    """POST em endpoint protegido sem ``Authorization`` deve devolver 401."""
    response = await secure_client.post(
        "/api/v1/nhm/request",
        json={"input": "consultar dashboard de vendas", "language": "pt"},
    )

    assert response.status_code == 401, response.text
    body = response.json()
    # Aceitamos qualquer payload de erro coerente — o middleware emite
    # ``{"error": "unauthorized"|"authentication_failed", ...}``.
    assert "error" in body
    assert body["error"] in {"unauthorized", "authentication_failed"}
    # Header WWW-Authenticate deve estar presente (RFC 6750).
    assert "WWW-Authenticate" in response.headers


# ---------------------------------------------------------------------------
# 2. Bearer malformado → 401
# ---------------------------------------------------------------------------


async def test_request_with_malformed_bearer_returns_401(
    secure_client: AsyncClient,
) -> None:
    """``Authorization: Bearer <lixo>`` deve falhar a validação JWT."""
    response = await secure_client.post(
        "/api/v1/nhm/request",
        json={"input": "qualquer", "language": "pt"},
        headers={"Authorization": "Bearer malformed.token.here"},
    )

    assert response.status_code == 401, response.text
    body = response.json()
    assert "error" in body
    assert body["error"] in {"unauthorized", "authentication_failed"}


# ---------------------------------------------------------------------------
# 3. JWT válido → 200, claims propagados downstream (INV-7)
# ---------------------------------------------------------------------------


async def test_request_with_valid_jwt_passes_through(
    secure_client: AsyncClient,
    force_nlu_domain_secure,
    capture_proxy_target_secure,
    patch_actor_user_id,
) -> None:
    """JWT válido deve ser aceite e os claims passados via headers downstream."""
    force_nlu_domain_secure("BUSINESS", confidence=0.92)
    capture_proxy_target_secure["set_response"](
        body=b'{"flow": "A-F", "result": "ok"}',
        status_code=200,
    )

    token = _make_valid_jwt(sub="u1", tenant_id="t1")

    response = await secure_client.post(
        "/api/v1/nhm/request",
        json={"input": "consultar dashboard de vendas", "language": "pt"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text

    # O FlowRouter foi atingido — sinal de que o middleware deixou passar.
    forwarded_headers = capture_proxy_target_secure["last_headers"]
    assert (
        forwarded_headers is not None
    ), "FlowRouter._proxy_request não foi invocado: middleware bloqueou ou app errou"

    # INV-7: user_id e tenant_id propagados downstream.
    # Comparação case-insensitive para tolerar normalização de headers.
    lower_headers = {k.lower(): v for k, v in forwarded_headers.items()}
    assert lower_headers.get("x-user-id") == "u1", forwarded_headers
    assert lower_headers.get("x-tenant-id") == "t1", forwarded_headers


# ---------------------------------------------------------------------------
# 4. Paths excluídos: /health, /metrics, / não exigem token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/health"),
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("GET", "/metrics"),
        ("GET", "/"),
    ],
)
async def test_excluded_paths_bypass_auth(
    secure_client: AsyncClient,
    method: str,
    path: str,
) -> None:
    """Endpoints excluídos devem responder sem exigir token (não 401)."""
    response = await secure_client.request(method, path)

    assert response.status_code != 401, (
        f"{method} {path} foi bloqueado pelo middleware (devia estar excluído): "
        f"{response.status_code} {response.text}"
    )
    # Sanity check: a resposta é minimamente bem-sucedida (2xx, ou 3xx para /).
    assert response.status_code < 500, response.text


# ---------------------------------------------------------------------------
# 5. Algoritmo "none" / token sem assinatura
# ---------------------------------------------------------------------------


async def test_jwt_with_alg_none_rejected(secure_client: AsyncClient) -> None:
    """Token com ``alg=none`` é sempre rejeitado, independentemente do ambiente.

    O middleware extrai o ``alg`` do header sem confiar no decode do PyJWT
    (PyJWT com ``verify_signature=False`` ignora a allowlist de algorithms
    e aceita tokens não assinados). A validação manual em
    ``_validate_jwt_token`` rejeita ``alg=none`` antes de chegar ao
    ``jwt.decode``.
    """
    # Construção manual de um token alg=none (PyJWT moderna recusa-se a
    # encodar com 'none' via API normal).
    import base64
    import json

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(
        json.dumps(
            {
                "sub": "attacker",
                "tenant_id": "evil",
                "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
            }
        ).encode()
    )
    token_none = f"{header}.{payload}."

    response = await secure_client.post(
        "/api/v1/nhm/request",
        json={"input": "x", "language": "pt"},
        headers={"Authorization": f"Bearer {token_none}"},
    )

    assert response.status_code == 401, (
        f"Token alg=none foi aceite — risco de segurança! "
        f"status={response.status_code} body={response.text}"
    )


# ---------------------------------------------------------------------------
# 6. Header ``authorization`` lowercase é aceite (HTTP é case-insensitive)
# ---------------------------------------------------------------------------


async def test_authorization_header_case_insensitive(
    secure_client: AsyncClient,
    force_nlu_domain_secure,
    capture_proxy_target_secure,
    patch_actor_user_id,
) -> None:
    """``authorization`` lowercase deve ser equivalente a ``Authorization``.

    Starlette/HTTPX normalizam headers case-insensitive; este teste confirma
    que o middleware (que usa ``request.headers.get("Authorization")``) lê
    correctamente o header independentemente do casing usado pelo cliente.
    """
    force_nlu_domain_secure("BUSINESS", confidence=0.9)
    capture_proxy_target_secure["set_response"](b'{"ok": true}', status_code=200)

    token = _make_valid_jwt(sub="u-case", tenant_id="t-case")

    # Enviado em lowercase explicitamente.
    response = await secure_client.post(
        "/api/v1/nhm/request",
        json={"input": "qualquer", "language": "pt"},
        headers={"authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text

    forwarded = capture_proxy_target_secure["last_headers"]
    assert forwarded is not None, "FlowRouter não foi chamado — header não reconhecido?"
    lower = {k.lower(): v for k, v in forwarded.items()}
    assert lower.get("x-user-id") == "u-case"
    assert lower.get("x-tenant-id") == "t-case"
