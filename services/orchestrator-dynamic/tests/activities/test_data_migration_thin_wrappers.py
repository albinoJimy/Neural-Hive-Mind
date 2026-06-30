"""Tests dos thin-wrappers de migração (Fase 2 / Task 3).

Spec: docs/specs/2026-06-29-migracao-j4-real — torna as activities de migração
THIN-WRAPPERS reais sobre o serviço data-migration:8019 (fonte de verdade), com
job_id real propagado e db_urls no contrato. SEM simulação local.

Estes testes congelam o contrato fail-closed (espelha test_validate_data.py):
- ``create_migration_job``: 201 → job_id; sem client/db_urls/non-2xx → fail-closed.
- ``run_batch_migration``: start + poll até terminal com contagens REAIS;
  ``failed`` → success=False; sem client/erro/non-2xx → fail-closed.
- ``analyze_legacy_schema``: thin-wrapper de leitura (GET) com SHAPE preservada.
- ``_extract_migration_config``: db_urls aditivas (presentes → valor; ausentes →
  None, SEM raise).
"""

import httpx
import pytest
from src.activities.data_migration import (
    analyze_legacy_schema,
    create_migration_job,
    run_batch_migration,
    set_data_migration_dependencies,
)

# =============================================================================
# Stub de httpx.AsyncClient com post/get programáveis (incl. sequência de poll)
# =============================================================================


class _StubClient:
    """Stub mínimo de httpx.AsyncClient.

    - ``post_response``/``post_exc``: resposta/erro para POST.
    - ``get_responses``: lista de respostas para GET (consumida em sequência; a
      última repete-se), permitindo simular o poll a evoluir running→completed.
    - ``get_exc``: erro para GET.
    """

    def __init__(
        self,
        *,
        post_response=None,
        post_exc=None,
        get_responses=None,
        get_exc=None,
    ):
        self._post_response = post_response
        self._post_exc = post_exc
        self._get_responses = list(get_responses) if get_responses else []
        self._get_exc = get_exc
        self.post_calls = []
        self.get_calls = []

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if self._post_exc is not None:
            raise self._post_exc
        return self._post_response

    async def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if self._get_exc is not None:
            raise self._get_exc
        idx = min(len(self.get_calls) - 1, len(self._get_responses) - 1)
        return self._get_responses[idx]


def _json_response(status_code, payload, method="POST"):
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request(method, "http://data-migration:8019/x"),
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Anula o asyncio.sleep do poll (testes rápidos e determinísticos)."""

    async def _instant(_seconds):
        return None

    monkeypatch.setattr("src.activities.data_migration.asyncio.sleep", _instant)


_VALID_CONFIG = {
    "legacy_db_url": "postgresql://u:p@legacy:5432/db",
    "modern_db_url": "postgresql://u:p@modern:5432/db",
    "tables": ["users", "orders"],
    "batch_size": 500,
}


# =============================================================================
# create_migration_job
# =============================================================================


@pytest.mark.asyncio()
class TestCreateMigrationJob:
    async def test_201_returns_job_id(self):
        """201 do /migrations → success=True + job_id real propagado."""
        client = _StubClient(
            post_response=_json_response(201, {"job_id": "job-xyz", "status": "pending"})
        )
        set_data_migration_dependencies(http_client=client, base_url="http://data-migration:8019")

        result = await create_migration_job(_VALID_CONFIG)

        assert result["success"] is True
        assert result["job_id"] == "job-xyz"
        # POST no endpoint REAL com o body de MigrationCreateRequest.
        url, kwargs = client.post_calls[0]
        assert url.endswith("/api/v1/migrations")
        body = kwargs["json"]
        assert body["legacy_db_url"] == _VALID_CONFIG["legacy_db_url"]
        assert body["modern_db_url"] == _VALID_CONFIG["modern_db_url"]
        assert body["tables"] == ["users", "orders"]
        assert body["batch_size"] == 500
        assert body["auto_approve"] is True

    async def test_no_http_client_fail_closed(self):
        """http client NÃO configurado → success=False (não assume sucesso)."""
        set_data_migration_dependencies(http_client=None)

        result = await create_migration_job(_VALID_CONFIG)

        assert result["success"] is False
        assert "error" in result

    async def test_missing_legacy_db_url_fail_closed(self):
        """legacy_db_url em falta → fail-closed (ponto de fail-closed das db_urls)."""
        client = _StubClient(post_response=_json_response(201, {"job_id": "j"}))
        set_data_migration_dependencies(http_client=client)

        config = dict(_VALID_CONFIG)
        config.pop("legacy_db_url")
        result = await create_migration_job(config)

        assert result["success"] is False
        # Não deve sequer chamar o serviço sem db_urls.
        assert client.post_calls == []

    async def test_empty_modern_db_url_fail_closed(self):
        """modern_db_url vazia → fail-closed."""
        client = _StubClient(post_response=_json_response(201, {"job_id": "j"}))
        set_data_migration_dependencies(http_client=client)

        config = dict(_VALID_CONFIG, modern_db_url="   ")
        result = await create_migration_job(config)

        assert result["success"] is False
        assert client.post_calls == []

    async def test_non_2xx_fail_closed(self):
        """Resposta não-2xx → fail-closed."""
        client = _StubClient(
            post_response=httpx.Response(
                500,
                text="boom",
                request=httpx.Request("POST", "http://data-migration:8019/x"),
            )
        )
        set_data_migration_dependencies(http_client=client)

        result = await create_migration_job(_VALID_CONFIG)

        assert result["success"] is False

    async def test_http_error_fail_closed(self):
        """Erro de rede httpx → fail-closed."""
        client = _StubClient(
            post_exc=httpx.RequestError(
                "refused",
                request=httpx.Request("POST", "http://data-migration:8019/x"),
            )
        )
        set_data_migration_dependencies(http_client=client)

        result = await create_migration_job(_VALID_CONFIG)

        assert result["success"] is False

    async def test_2xx_without_job_id_fail_closed(self):
        """2xx sem job_id → fail-closed (sem id real não há propagação)."""
        client = _StubClient(post_response=_json_response(201, {"status": "pending"}))
        set_data_migration_dependencies(http_client=client)

        result = await create_migration_job(_VALID_CONFIG)

        assert result["success"] is False


# =============================================================================
# run_batch_migration (start + poll)
# =============================================================================


def _status_response(status_value, rows_migrated=0, total_rows=0, progress=0.0):
    return _json_response(
        200,
        {
            "job_id": "job-1",
            "status": status_value,
            "progress": progress,
            "current_phase": status_value,
            "tables_completed": 2,
            "total_tables": 2,
            "rows_migrated": rows_migrated,
            "total_rows": total_rows,
        },
        method="GET",
    )


@pytest.mark.asyncio()
class TestRunBatchMigration:
    async def test_start_then_poll_until_completed(self):
        """start + poll: running→completed com rows_migrated REAIS do serviço."""
        client = _StubClient(
            post_response=_json_response(
                200, {"job_id": "job-1", "action": "start", "success": True}
            ),
            get_responses=[
                _status_response("batch_migrating", rows_migrated=5, total_rows=10),
                _status_response("completed", rows_migrated=10, total_rows=10, progress=100.0),
            ],
        )
        set_data_migration_dependencies(http_client=client, base_url="http://data-migration:8019")

        result = await run_batch_migration("job-1", {"tables": []})

        assert result["success"] is True
        # Contagens REAIS do serviço (não rows_migrated = total_rows local).
        assert result["rows_migrated"] == 10
        assert result["total_rows"] == 10
        assert result["progress_percentage"] == 100.0
        # Endpoints REAIS chamados.
        assert client.post_calls[0][0].endswith("/api/v1/migrations/job-1/start")
        assert client.get_calls[0][0].endswith("/api/v1/migrations/job-1")
        # Houve poll (>1 GET até terminal).
        assert len(client.get_calls) == 2

    async def test_terminal_failed_yields_success_false(self):
        """status terminal ``failed`` → success=False (fail-closed)."""
        client = _StubClient(
            post_response=_json_response(200, {"success": True}),
            get_responses=[_status_response("failed", rows_migrated=3, total_rows=10)],
        )
        set_data_migration_dependencies(http_client=client)

        result = await run_batch_migration("job-1", {"tables": []})

        assert result["success"] is False
        # Mesmo a falhar, devolve as contagens reais observadas.
        assert result["rows_migrated"] == 3

    async def test_no_http_client_fail_closed(self):
        """http client NÃO configurado → success=False (não assume sucesso)."""
        set_data_migration_dependencies(http_client=None)

        result = await run_batch_migration("job-1", {"tables": []})

        assert result["success"] is False

    async def test_start_non_2xx_fail_closed(self):
        """/start não-2xx → fail-closed (sem poll)."""
        client = _StubClient(
            post_response=httpx.Response(
                409,
                text="conflict",
                request=httpx.Request("POST", "http://data-migration:8019/x"),
            )
        )
        set_data_migration_dependencies(http_client=client)

        result = await run_batch_migration("job-1", {"tables": []})

        assert result["success"] is False
        assert client.get_calls == []

    async def test_poll_http_error_fail_closed(self):
        """Erro de rede no poll → fail-closed."""
        client = _StubClient(
            post_response=_json_response(200, {"success": True}),
            get_exc=httpx.RequestError(
                "refused",
                request=httpx.Request("GET", "http://data-migration:8019/x"),
            ),
        )
        set_data_migration_dependencies(http_client=client)

        result = await run_batch_migration("job-1", {"tables": []})

        assert result["success"] is False

    async def test_poll_invalid_json_fail_closed(self):
        """Poll: GET 2xx com JSON inválido → fail-closed (não assume sucesso)."""
        client = _StubClient(
            post_response=_json_response(200, {"success": True}),
            get_responses=[
                httpx.Response(
                    200,
                    content=b"<<nao json>>",
                    request=httpx.Request("GET", "http://data-migration:8019/x"),
                )
            ],
        )
        set_data_migration_dependencies(http_client=client)

        result = await run_batch_migration("job-1", {"tables": []})

        assert result["success"] is False

    async def test_poll_timeout_fail_closed(self, monkeypatch):
        """Esgotar a janela de poll sem estado terminal → fail-closed."""
        monkeypatch.setattr("src.activities.data_migration._BATCH_POLL_MAX_ATTEMPTS", 3)
        client = _StubClient(
            post_response=_json_response(200, {"success": True}),
            # Nunca atinge estado terminal (fica sempre em batch_migrating).
            get_responses=[_status_response("batch_migrating", rows_migrated=1, total_rows=10)],
        )
        set_data_migration_dependencies(http_client=client)

        result = await run_batch_migration("job-1", {"tables": []})

        assert result["success"] is False
        assert "Timeout" in result["error"]
        # Esgotou exatamente a janela de poll (3 tentativas), sem verde-falso.
        assert len(client.get_calls) == 3


# =============================================================================
# analyze_legacy_schema (thin-wrapper de leitura)
# =============================================================================


@pytest.mark.asyncio()
class TestAnalyzeLegacySchema:
    async def test_get_builds_schema_analysis_shape(self):
        """GET 2xx → schema_analysis com SHAPE consumida por generate_schema_mapping."""
        client = _StubClient(get_responses=[_status_response("pending", total_rows=14)])
        set_data_migration_dependencies(http_client=client, base_url="http://data-migration:8019")

        result = await analyze_legacy_schema("job-1", ["users", "orders"], "public")

        assert result["success"] is True
        sa = result["schema_analysis"]
        # SHAPE: tables com {schema, table, columns, row_estimate}.
        assert [t["table"] for t in sa["tables"]] == ["users", "orders"]
        assert all("columns" in t for t in sa["tables"])
        # total_rows REAL do serviço (não hardcoded).
        assert sa["total_rows"] == 14
        assert client.get_calls[0][0].endswith("/api/v1/migrations/job-1")

    async def test_no_http_client_fail_closed(self):
        set_data_migration_dependencies(http_client=None)

        result = await analyze_legacy_schema("job-1", ["users"])

        assert result["success"] is False

    async def test_get_invalid_json_fail_closed(self):
        """GET 2xx com JSON inválido → fail-closed."""
        client = _StubClient(
            get_responses=[
                httpx.Response(
                    200,
                    content=b"<<nao json>>",
                    request=httpx.Request("GET", "http://data-migration:8019/x"),
                )
            ]
        )
        set_data_migration_dependencies(http_client=client)

        result = await analyze_legacy_schema("job-1", ["users"])

        assert result["success"] is False

    async def test_get_non_2xx_fail_closed(self):
        client = _StubClient(
            get_responses=[
                httpx.Response(
                    404,
                    text="not found",
                    request=httpx.Request("GET", "http://data-migration:8019/x"),
                )
            ]
        )
        set_data_migration_dependencies(http_client=client)

        result = await analyze_legacy_schema("job-1", ["users"])

        assert result["success"] is False


# =============================================================================
# _extract_migration_config — db_urls aditivas (sem raise)
# =============================================================================


class TestExtractMigrationConfigDbUrls:
    def test_db_urls_present_are_loaded(self):
        from src.consumers.decision_consumer import _extract_migration_config

        config = _extract_migration_config(
            {
                "migration_config": {
                    "legacy_connection_id": "pg",
                    "tables": ["users"],
                    "legacy_db_url": "postgresql://u:p@legacy:5432/db",
                    "modern_db_url": "postgresql://u:p@modern:5432/db",
                }
            }
        )
        assert config["legacy_db_url"] == "postgresql://u:p@legacy:5432/db"
        assert config["modern_db_url"] == "postgresql://u:p@modern:5432/db"

    def test_db_urls_absent_become_none_without_raise(self):
        from src.consumers.decision_consumer import _extract_migration_config

        # Sem db_urls → None (NÃO levanta erro: fail-closed vive na activity).
        config = _extract_migration_config(
            {"migration_config": {"legacy_connection_id": "pg", "tables": ["users"]}}
        )
        assert config["legacy_db_url"] is None
        assert config["modern_db_url"] is None
