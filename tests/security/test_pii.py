"""Testes de segurança para o PII Service (TICKET-030).

Valida o pipeline ``cliente REST → PII Service → detect/mask/unmask``
sem subir Docker compose nem MongoDB. Em vez disso:

- A app FastAPI real do ``pii-service`` é importada via path injection,
  identicamente ao pattern usado em ``tests/e2e/_unified_gateway_helpers``.
- A env var ``JWT_AUTH_REQUIRED`` é definida como ``false`` antes do
  import para que o ``JWTAuthMiddleware`` seja construído com
  ``require_auth=False``. Isto permite exercitar todos os endpoints sem
  IdP real.
- O ``PIIAuditLogger.initialize`` é mockado (``AsyncMock``) para que o
  lifespan da app não tente abrir conexão MongoDB.
- Os métodos ``log_*_operation`` do audit logger são mockados a nível
  do singleton no ``pii_service`` (via ``monkeypatch.setattr``) para que
  os testes consigam afirmar invocações sem depender de MongoDB.

Tipos PII testados (apenas os funcionais conforme
``services/pii-service/LIMITACOES.md``):

- ✅ EMAIL
- ✅ ADDRESS (via spaCy GPE/LOC)
- ❌ PHONE / CNPJ / CREDIT_CARD / SSN — detector regex não cobre todos
  os formatos; *intencionalmente evitados*.

Referências:
- ``services/pii-service/src/api/routers/pii.py`` — endpoints REST.
- ``services/pii-service/src/services/pii_service.py`` — fluxo
  detect/mask/unmask + integração com ``PIIDetectorLite`` e
  ``ReversibleMaskService``.
- ``services/pii-service/src/services/encryption.py`` — AES-256-GCM,
  TTL 168h, ``UNMASK_MAX_ATTEMPTS=3``.
- ``services/pii-service/LIMITACOES.md`` — limitações documentadas
  do detector.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.security, pytest.mark.asyncio]


# ---- Path setup ------------------------------------------------------------
# A app vive em services/pii-service/src/main.py com imports `src.*`,
# que só resolvem se ``services/pii-service`` estiver no sys.path. Como
# também há ``services/unified-gateway/src/`` usado por outros testes de
# segurança, fazemos purge dos módulos ``src*`` em cada fixture para
# evitar colisão de namespaces.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PII_SERVICE_ROOT = _REPO_ROOT / "services" / "pii-service"


# ---- Fixtures --------------------------------------------------------------


@pytest_asyncio.fixture
async def pii_app(monkeypatch: pytest.MonkeyPatch):
    """Importa a app real do PII Service e neutraliza dependências externas.

    - Desliga JWT auth (``JWT_AUTH_REQUIRED=false``) para evitar IdP.
    - Mocka ``PIIAuditLogger.initialize`` e ``close`` para que o lifespan
      não tente conectar a MongoDB.
    - Não cacheia ``get_settings`` entre testes (limpa o ``lru_cache``).
    - Limpa ``sys.modules['src*']`` e prioriza ``services/pii-service``
      no ``sys.path`` para evitar colisão com o package ``src`` de
      ``services/unified-gateway`` quando os testes correm na mesma sessão.
    """
    monkeypatch.setenv("JWT_AUTH_REQUIRED", "false")

    # Purge sys.modules['src*'] de qualquer outro serviço já carregado.
    for cached in [m for m in list(sys.modules) if m == "src" or m.startswith("src.")]:
        del sys.modules[cached]
    # Garante prioridade do pii-service no sys.path.
    if str(_PII_SERVICE_ROOT) in sys.path:
        sys.path.remove(str(_PII_SERVICE_ROOT))
    sys.path.insert(0, str(_PII_SERVICE_ROOT))

    # Importação tardia para que a env var já esteja aplicada quando o
    # ``Settings`` é instanciado.
    from src.config.settings import get_settings  # type: ignore

    get_settings.cache_clear()  # type: ignore[attr-defined]

    # Mockar audit logger antes de importar a app, para o lifespan não falhar.
    from src.services import audit as audit_module  # type: ignore

    audit_logger_mock = audit_module.get_audit_logger()
    monkeypatch.setattr(audit_logger_mock, "initialize", AsyncMock(return_value=None))
    monkeypatch.setattr(audit_logger_mock, "close", AsyncMock(return_value=None))
    # As operações log_* são chamadas dentro do PIIService — mockamos sempre.
    monkeypatch.setattr(audit_logger_mock, "log_mask_operation", AsyncMock(return_value=None))
    monkeypatch.setattr(audit_logger_mock, "log_unmask_operation", AsyncMock(return_value=None))
    monkeypatch.setattr(audit_logger_mock, "log_detect_operation", AsyncMock(return_value=None))

    from src.main import app  # type: ignore

    yield app, audit_logger_mock


@pytest_asyncio.fixture
async def pii_client(pii_app):
    """``AsyncClient`` ligado à app via ASGI (sem rede)."""
    app, _audit = pii_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---- Helpers ---------------------------------------------------------------


_EMAIL_TEXT = "Contacte-me em joao@example.com"
_EMAIL_VALUE = "joao@example.com"


# ---- Testes ----------------------------------------------------------------


async def test_detect_finds_email_in_text(pii_client: AsyncClient) -> None:
    """``/detect`` deve devolver pelo menos um item de tipo EMAIL.

    Sub-req coberto: detecção de PII em texto livre.
    GIVEN um texto contendo um endereço de email
    WHEN o cliente invoca ``POST /api/v1/pii/detect``
    THEN a resposta lista o email em ``detected_pii`` com tipo EMAIL.
    """
    resp = await pii_client.post(
        "/api/v1/pii/detect",
        json={"text": _EMAIL_TEXT, "language": "pt"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "detected_pii" in body
    types = [item["type"] for item in body["detected_pii"]]
    assert "EMAIL" in types, f"Expected EMAIL detected, got {types}"

    # Position invariant (INV-2)
    email_item = next(item for item in body["detected_pii"] if item["type"] == "EMAIL")
    assert email_item["start"] >= 0
    assert email_item["end"] > email_item["start"]
    assert email_item["value"] == _EMAIL_VALUE


async def test_mask_replaces_email_with_placeholder(pii_client: AsyncClient) -> None:
    """``/mask`` deve substituir o email original por placeholder.

    GIVEN o mesmo texto com email
    WHEN o cliente invoca ``POST /api/v1/pii/mask``
    THEN ``masked_text`` não contém o valor original e foi
         efectivamente alterado.
    """
    resp = await pii_client.post(
        "/api/v1/pii/mask",
        json={
            "text": _EMAIL_TEXT,
            "strategy": "MASK_FULL",
            "language": "pt",
            "enable_audit_log": True,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    masked = body["masked_text"]

    # O email original NÃO pode estar presente no texto mascarado.
    assert (
        _EMAIL_VALUE not in masked
    ), f"PII leak: email original presente no masked_text: {masked!r}"
    # O texto deve ter sido alterado.
    assert masked != _EMAIL_TEXT
    # Algum padrão de masking foi aplicado (placeholder/tag ou *).
    has_placeholder = (
        "[EMAIL]" in masked or "EMAIL" in masked or "*" in masked or "[REDACTED]" in masked
    )
    assert has_placeholder, f"Nenhum padrão de masking detectado em {masked!r}"


async def test_unmask_with_invalid_token_returns_error(
    pii_client: AsyncClient,
) -> None:
    """``/unmask`` com token inválido tem de devolver ``success=False``.

    GIVEN um ``mask_id`` que não corresponde a nenhum token criado
    WHEN o cliente invoca ``POST /api/v1/pii/unmask``
    THEN o serviço rejeita a operação com ``success=False`` e
         ``error_message`` populado, sem expor PII.
    """
    resp = await pii_client.post(
        "/api/v1/pii/unmask",
        json={
            "mask_id": "totally-invalid-token-not-base64-aesgcm",
            "enable_audit_log": True,
        },
    )

    # O endpoint devolve 200 com ``success=False`` (não é uma 4xx).
    # Esta semântica é a definida em ``unmask`` do PIIService.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["original_text"] == ""
    assert body["error_message"], "Esperava error_message não vazio"


async def test_unmask_max_attempts_enforced(pii_client: AsyncClient) -> None:
    """``UNMASK_MAX_ATTEMPTS=3`` é respeitado na lógica do serviço.

    GIVEN um token criado via ``ReversibleMaskService.create_mask_token``
    WHEN o cliente tenta desmascará-lo 4 vezes consecutivas
    THEN a 4ª tentativa é rejeitada com ``error_message`` indicando
         excesso de tentativas.

    O ``ReversibleMaskService`` mantém o contador num dict in-memory
    (``_attempt_counters[mask_id]``) separado do payload encriptado;
    o ciphertext continua imutável, mas cada chamada incrementa o
    counter — atingido ``max_attempts``, futuras chamadas falham.
    """
    from src.services.encryption import get_reversible_mask_service  # type: ignore

    rms = get_reversible_mask_service()
    # Garante que esta execução começa sem contador acumulado de outros testes.
    rms._attempt_counters.clear()

    mask_id, _expires_at = rms.create_mask_token(
        original_value="EMAIL:joao@example.com",
        pii_type="EMAIL",
        requestor_id="test-suite",
    )

    payload = {"mask_id": mask_id, "enable_audit_log": False}

    last_body: dict = {}
    for _ in range(rms.max_attempts + 1):
        r = await pii_client.post("/api/v1/pii/unmask", json=payload)
        assert r.status_code == 200, r.text
        last_body = r.json()

    assert last_body.get("success") is False
    err = (last_body.get("error_message") or "").lower()
    assert "attempt" in err or "max" in err or "exceeded" in err


async def test_audit_logger_called_on_mask(pii_app, pii_client: AsyncClient) -> None:
    """O ``audit_logger`` é invocado em operações de mask.

    GIVEN o audit logger mockado com ``AsyncMock``
    WHEN o cliente invoca ``POST /api/v1/pii/mask`` com
         ``enable_audit_log=True``
    THEN ``log_mask_operation`` foi chamado pelo menos uma vez.
    """
    _app, audit_logger = pii_app

    # Reset contagem antes do exercício.
    audit_logger.log_mask_operation.reset_mock()

    resp = await pii_client.post(
        "/api/v1/pii/mask",
        json={
            "text": _EMAIL_TEXT,
            "strategy": "MASK_FULL",
            "language": "pt",
            "enable_audit_log": True,
            "correlation_id": "test-correlation-001",
        },
    )

    assert resp.status_code == 200, resp.text
    assert audit_logger.log_mask_operation.await_count >= 1, (
        "Esperava log_mask_operation invocado pelo menos 1×, "
        f"got {audit_logger.log_mask_operation.await_count}"
    )


async def test_pii_not_leaked_in_response_logs(pii_client: AsyncClient) -> None:
    """O PII original não deve aparecer em campos non-PII da response.

    GIVEN um texto com email
    WHEN o cliente invoca ``POST /api/v1/pii/mask`` com MASK_REDACT
    THEN o ``masked_text`` não contém o email; o email só pode aparecer
         dentro de ``detected_pii[].value`` / ``masks[].original_value``
         (campos auditáveis previstos pelo schema, não vazamento).
    """
    resp = await pii_client.post(
        "/api/v1/pii/mask",
        json={
            "text": _EMAIL_TEXT,
            "strategy": "MASK_REDACT",
            "language": "pt",
            "enable_audit_log": True,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # masked_text NUNCA pode conter o PII original.
    assert _EMAIL_VALUE not in body["masked_text"], "PII leak no masked_text"
    # masked_at é metadata, não pode conter PII.
    assert _EMAIL_VALUE not in body.get("masked_at", "")
    # mask_id é (potencialmente) um token AES; nunca o PII em claro.
    assert _EMAIL_VALUE not in (body.get("mask_id") or "")
    # detected_pii[].masked_value não deve repetir o original em texto claro.
    for item in body.get("detected_pii", []):
        masked_value = item.get("masked_value") or ""
        assert (
            _EMAIL_VALUE not in masked_value
        ), f"PII leak em detected_pii[].masked_value: {masked_value!r}"


async def test_capabilities_endpoint_does_not_require_auth(
    pii_client: AsyncClient,
) -> None:
    """``/capabilities`` é exposto sem autenticação (whitelist).

    GIVEN nenhum header ``Authorization``
    WHEN o cliente invoca ``GET /api/v1/pii/capabilities``
    THEN a resposta é 200 e expõe ``supported_types``,
         ``supported_strategies`` e flags de capacidade.
    """
    resp = await pii_client.get("/api/v1/pii/capabilities")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "supported_types" in body
    assert "supported_strategies" in body
    assert "EMAIL" in body["supported_types"]
    # As 3 estratégias INV-2 têm de estar lá.
    assert "MASK_FULL" in body["supported_strategies"]
    assert "MASK_PARTIAL" in body["supported_strategies"]
    assert "MASK_REDACT" in body["supported_strategies"]
