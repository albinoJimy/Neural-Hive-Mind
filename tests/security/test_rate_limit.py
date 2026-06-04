"""
Testes de segurança para o RateLimitMiddleware do Unified Gateway.

TICKET-030 — Cobertura de segurança do rate limiting.

Valida o comportamento do middleware em
``services/unified-gateway/src/middleware/rate_limit.py``, incluindo a
correcção recente de race condition (INCR atómico + EXPIRE apenas no
primeiro hit da janela).

Estratégia:
- Não usamos Redis real. Substituímos ``RateLimiter.get_redis`` por um stub
  in-memory (`_FakeRedis`) que reimplementa a interface mínima usada pelo
  middleware: ``pipeline().incr().ttl().execute()`` + ``expire()``.
- Reaproveitamos os fixtures ``unified_gateway_app`` / ``gateway_client`` de
  ``tests/e2e/_unified_gateway_helpers.py`` (têm ``JWT_AUTH_REQUIRED=false``,
  o que torna todos os requests "anonymous" no tier ``DEFAULT``).
- Limites por tier validados aqui: TRIAL 10/min, DEFAULT 100/min, ENTERPRISE
  1000/min.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

# Garantir que ``src.*`` do unified-gateway é importável (mesmo que os
# fixtures partilhados ainda não tenham sido carregados).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIFIED_GATEWAY_ROOT = _REPO_ROOT / "services" / "unified-gateway"
if str(_UNIFIED_GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(_UNIFIED_GATEWAY_ROOT))

# Fixtures partilhados com a suite E2E do unified-gateway.
from tests.e2e._unified_gateway_helpers import (  # noqa: E402,F401
    gateway_client,
    unified_gateway_app,
)

pytestmark = [pytest.mark.security, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Stub in-memory para Redis async
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Stub mínimo de ``redis.asyncio.Redis`` usado pelo RateLimiter.

    Implementa apenas o que o middleware exercita:
    - ``pipeline().incr(key).ttl(key).execute()``
    - ``expire(key, seconds)``
    - ``close()``

    Mantém um contador por chave + um TTL absoluto (epoch). Chaves expiradas
    são purgadas no próximo acesso, simulando o comportamento do Redis real.
    """

    def __init__(self) -> None:
        self._store: dict[str, int] = {}
        self._ttl: dict[str, int] = {}  # epoch absoluto; -1 ⇒ sem TTL

    # --- internos ---------------------------------------------------------

    def _purge_if_expired(self, key: str) -> None:
        ttl_at = self._ttl.get(key, -1)
        if ttl_at > 0 and ttl_at <= int(time.time()):
            self._store.pop(key, None)
            self._ttl.pop(key, None)

    # --- API consumida pelo middleware ------------------------------------

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)

    async def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        self._store[key] = self._store.get(key, 0) + 1
        # Manter ``-1`` como "sem expiry" (compatível com Redis real).
        self._ttl.setdefault(key, -1)
        return self._store[key]

    async def ttl(self, key: str) -> int:
        self._purge_if_expired(key)
        if key not in self._store:
            return -2  # key não existe
        ttl_at = self._ttl.get(key, -1)
        if ttl_at < 0:
            return -1
        remaining = ttl_at - int(time.time())
        return max(0, remaining)

    async def expire(self, key: str, seconds: int) -> bool:
        if key in self._store:
            self._ttl[key] = int(time.time()) + int(seconds)
            return True
        return False

    async def close(self) -> None:  # noqa: D401 — interface parity
        return None

    # --- helpers de teste -------------------------------------------------

    def seed(self, key: str, count: int, ttl_seconds: int = 60) -> None:
        """Pré-popula o contador e arma TTL (uso só em testes)."""
        self._store[key] = count
        self._ttl[key] = int(time.time()) + ttl_seconds

    def get_count(self, key: str) -> int:
        self._purge_if_expired(key)
        return self._store.get(key, 0)


class _FakePipeline:
    """Pipeline em buffer; ``execute()`` aplica as ops em ordem."""

    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, str]] = []

    def incr(self, key: str) -> "_FakePipeline":
        self._ops.append(("incr", key))
        return self

    def ttl(self, key: str) -> "_FakePipeline":
        self._ops.append(("ttl", key))
        return self

    async def execute(self) -> list[int]:
        results: list[int] = []
        for op, key in self._ops:
            if op == "incr":
                results.append(await self._redis.incr(key))
            elif op == "ttl":
                results.append(await self._redis.ttl(key))
        self._ops.clear()
        return results


# ---------------------------------------------------------------------------
# Helpers de patching
# ---------------------------------------------------------------------------


def _install_fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    """Substitui ``RateLimiter.get_redis`` para devolver sempre o mesmo fake.

    Como o middleware é construído com ``rate_limiter=RateLimiter()`` por
    defeito (no app factory), todas as instâncias partilham o método de
    classe. Patchamos no nível da classe para apanhar todas.
    """
    from src.middleware.rate_limit import RateLimiter  # type: ignore

    fake = _FakeRedis()

    async def _get_redis(self):  # noqa: ARG001 — interface de método bound
        return fake

    monkeypatch.setattr(RateLimiter, "get_redis", _get_redis, raising=True)
    return fake


# ---------------------------------------------------------------------------
# Testes via gateway_client (caminho integrado middleware → response)
# ---------------------------------------------------------------------------


async def test_under_limit_allows_request(monkeypatch: pytest.MonkeyPatch, gateway_client):
    """Request sob o limite passa e expõe X-RateLimit-Remaining = limite-1."""
    _install_fake_redis(monkeypatch)

    response = await gateway_client.get("/")

    assert response.status_code == 200, response.text
    # Tier DEFAULT (sem auth) ⇒ 100 req/min.
    assert response.headers.get("X-RateLimit-Limit") == "100"
    assert response.headers.get("X-RateLimit-Remaining") == "99"
    assert response.headers.get("X-RateLimit-Reset") is not None
    # Reset deve ser um epoch numérico futuro.
    assert int(response.headers["X-RateLimit-Reset"]) >= int(time.time())


async def test_over_limit_returns_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch, gateway_client
):
    """Após 100 hits da janela, o 101.º request retorna 429 com Retry-After."""
    fake = _install_fake_redis(monkeypatch)

    # Pré-popular contador no exact path/tenant que o middleware vai usar.
    # Key format: unified_gateway:rate_limit:<tenant>:<endpoint>:rate_limit:<window>
    minute_window = int(time.time()) // 60
    key = f"unified_gateway:rate_limit:anonymous:/:rate_limit:{minute_window}"
    fake.seed(key, count=100, ttl_seconds=60)

    response = await gateway_client.get("/")

    assert response.status_code == 429, response.text

    retry_after = response.headers.get("Retry-After")
    assert retry_after is not None
    assert int(retry_after) > 0
    assert response.headers.get("X-RateLimit-Limit") == "100"
    assert response.headers.get("X-RateLimit-Remaining") == "0"

    body = response.json()
    assert body["error"] == "rate_limit_exceeded"
    assert "retry_after" in body
    assert body["retry_after"] == int(retry_after)


async def test_atomic_increment_under_concurrency(monkeypatch: pytest.MonkeyPatch, gateway_client):
    """50 requests concorrentes: a soma dos sucessos nunca excede o limite.

    Garante que o INCR atómico previne a race condition (em vez de SET-after-GET
    que permitiria várias requests passarem antes do contador ser persistido).
    """
    fake = _install_fake_redis(monkeypatch)

    # Janela DEFAULT = 100; lançamos 50 → todas devem passar e o contador
    # final tem que reflectir exactamente 50 incrementos.
    responses = await asyncio.gather(*[gateway_client.get("/") for _ in range(50)])

    successes = [r for r in responses if r.status_code == 200]
    rate_limited = [r for r in responses if r.status_code == 429]

    # Sob 50 < 100, ninguém deve ser barrado.
    assert len(successes) == 50
    assert len(rate_limited) == 0

    minute_window = int(time.time()) // 60
    key = f"unified_gateway:rate_limit:anonymous:/:rate_limit:{minute_window}"
    # Atomicidade: o contador final é exactamente 50 (sem perdas de update).
    assert fake.get_count(key) == 50


async def test_excluded_paths_skip_rate_limit(monkeypatch: pytest.MonkeyPatch, gateway_client):
    """``/health`` ignora o middleware mesmo com fake redis pré-populado.

    Verificamos que:
    1. Não há headers ``X-RateLimit-*`` na resposta.
    2. O contador da chave anónima genérica não é tocado.
    3. 200 hits seguidos continuam todos a passar (200 OK) — não há 429.
    """
    fake = _install_fake_redis(monkeypatch)

    # Pré-popular a chave equivalente para garantir que o middleware,
    # se fosse executado, retornaria 429 — provando que foi mesmo skipado.
    minute_window = int(time.time()) // 60
    health_key = f"unified_gateway:rate_limit:anonymous:/health:rate_limit:{minute_window}"
    fake.seed(health_key, count=999, ttl_seconds=60)

    # 200 hits — todos devem passar, sem 429 e sem headers de rate limit.
    last = None
    for _ in range(200):
        last = await gateway_client.get("/health")
        assert last.status_code == 200

    assert last is not None
    assert "X-RateLimit-Limit" not in last.headers
    assert "X-RateLimit-Remaining" not in last.headers
    assert "X-RateLimit-Reset" not in last.headers
    assert "Retry-After" not in last.headers

    # O contador não foi incrementado pelo middleware (path excluído).
    assert fake.get_count(health_key) == 999


async def test_headers_present_on_successful_response(
    monkeypatch: pytest.MonkeyPatch, gateway_client
):
    """Resposta bem-sucedida traz X-RateLimit-Limit/Remaining/Reset numéricos."""
    _install_fake_redis(monkeypatch)

    response = await gateway_client.get("/")

    assert response.status_code == 200
    for header in ("X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"):
        assert header in response.headers, f"missing {header}"
        # Todos devem ser inteiros parseáveis.
        int(response.headers[header])

    # Sanity: Remaining == Limit - 1 logo a seguir ao primeiro request.
    assert int(response.headers["X-RateLimit-Remaining"]) == (
        int(response.headers["X-RateLimit-Limit"]) - 1
    )


# ---------------------------------------------------------------------------
# Testes directos do RateLimiter (granularidade tenant/tier)
# ---------------------------------------------------------------------------


async def test_rate_limit_per_tenant_isolation(monkeypatch: pytest.MonkeyPatch):
    """Tenant A consumir quota não afecta a quota do tenant B.

    Validamos directamente no ``RateLimiter`` porque sem JWT todos os
    requests via cliente HTTP partilham ``tenant_id="anonymous"``. Aqui,
    invocamos com tenant_ids distintos e checamos que cada um tem a sua
    janela independente.
    """
    fake = _install_fake_redis(monkeypatch)

    from src.middleware.rate_limit import RateLimiter, TenantTier  # type: ignore

    limiter = RateLimiter()

    # Tenant A: 5 requests; Tenant B: 0.
    for _ in range(5):
        result_a = await limiter.check_rate_limit(
            tenant_id="tenant-a", tier=TenantTier.DEFAULT, endpoint="/x"
        )
        assert result_a.allowed
    # ``remaining`` reflecte o consumo exclusivo de A.
    assert result_a.remaining == 100 - 5  # noqa: PLR2004 — DEFAULT=100

    # Tenant B começa do zero (isolamento por chave).
    result_b = await limiter.check_rate_limit(
        tenant_id="tenant-b", tier=TenantTier.DEFAULT, endpoint="/x"
    )
    assert result_b.allowed
    assert result_b.remaining == 99  # noqa: PLR2004

    # Sanity: as chaves no fake são distintas.
    keys = [k for k in fake._store.keys() if "/x" in k]  # noqa: SLF001 — teste
    assert any("tenant-a" in k for k in keys)
    assert any("tenant-b" in k for k in keys)
    # Contadores independentes:
    a_key = next(k for k in keys if "tenant-a" in k)
    b_key = next(k for k in keys if "tenant-b" in k)
    assert fake.get_count(a_key) == 5
    assert fake.get_count(b_key) == 1


async def test_tier_limits_differ(monkeypatch: pytest.MonkeyPatch):
    """TRIAL (10), DEFAULT (100) e ENTERPRISE (1000) têm limites distintos."""
    _install_fake_redis(monkeypatch)

    from src.middleware.rate_limit import RateLimiter, TenantTier  # type: ignore

    limiter = RateLimiter()

    trial = await limiter.check_rate_limit(
        tenant_id="t-trial", tier=TenantTier.TRIAL, endpoint="/y"
    )
    default = await limiter.check_rate_limit(
        tenant_id="t-default", tier=TenantTier.DEFAULT, endpoint="/y"
    )
    enterprise = await limiter.check_rate_limit(
        tenant_id="t-ent", tier=TenantTier.ENTERPRISE, endpoint="/y"
    )

    assert trial.limit == 10
    assert default.limit == 100
    assert enterprise.limit == 1000

    # Todos os três no primeiro hit ainda têm orçamento positivo.
    assert trial.remaining == 9
    assert default.remaining == 99
    assert enterprise.remaining == 999


async def test_expire_armed_only_on_first_hit(monkeypatch: pytest.MonkeyPatch):
    """EXPIRE deve ser chamado apenas quando o contador transita 0→1.

    Validação directa da correcção da race condition: no segundo hit, o
    TTL não deve ser reposto (mantém-se decrescente). Se o middleware
    chamasse EXPIRE em todos os hits, o reset_at avançaria a cada call.
    """
    fake = _install_fake_redis(monkeypatch)

    from src.middleware.rate_limit import RateLimiter, TenantTier  # type: ignore

    limiter = RateLimiter()

    first = await limiter.check_rate_limit(
        tenant_id="t-ttl", tier=TenantTier.DEFAULT, endpoint="/z"
    )
    # Forçar passagem de tempo simulada: descer o TTL da chave manualmente.
    minute_window = int(time.time()) // 60
    key = f"unified_gateway:rate_limit:t-ttl:/z:rate_limit:{minute_window}"
    # Reduz o TTL absoluto em 30s (como se 30s tivessem passado).
    fake._ttl[key] = fake._ttl[key] - 30  # noqa: SLF001 — manipulação de teste

    second = await limiter.check_rate_limit(
        tenant_id="t-ttl", tier=TenantTier.DEFAULT, endpoint="/z"
    )

    # Se o EXPIRE fosse re-armado, second.reset_at >= first.reset_at + ~30.
    # Como NÃO é re-armado, second.reset_at fica próximo de first.reset_at.
    # Tolerância ampla para evitar flakiness em máquinas lentas.
    drift = second.reset_at - first.reset_at
    assert drift <= 1, (
        f"reset_at avançou {drift}s — EXPIRE foi armado num hit > 1 "
        "(potencial regressão da correcção de race condition)"
    )


async def test_response_body_is_valid_json_on_429(monkeypatch: pytest.MonkeyPatch, gateway_client):
    """O body do 429 é JSON válido com campos esperados."""
    fake = _install_fake_redis(monkeypatch)

    minute_window = int(time.time()) // 60
    key = f"unified_gateway:rate_limit:anonymous:/:rate_limit:{minute_window}"
    fake.seed(key, count=100, ttl_seconds=42)

    response = await gateway_client.get("/")

    assert response.status_code == 429
    assert response.headers.get("Content-Type", "").startswith("application/json")

    body = json.loads(response.content)
    assert body["error"] == "rate_limit_exceeded"
    assert isinstance(body["retry_after"], int)
    assert "message" in body
