"""Tests para a activity validate_data (gate J4/MIGRATE fail-closed).

Fase 2 / Task 3 da spec docs/specs/2026-06-29-gate-j4-migrate-fiavel.

Estes testes congelam o contrato fail-closed da `validate_data`: o sucesso só é
afirmado quando o serviço data-migration (`POST /migrations/{id}/validate`)
devolve `overall_passed=True` explicitamente. Qualquer ambiguidade (erro de
rede, timeout, status não-2xx, JSON sem o campo de validação, http client não
configurado) → `success=False` (FAILED). Nunca assumir sucesso por defeito.
"""

import httpx
import pytest
from src.activities.data_migration import (
    set_data_migration_dependencies,
    validate_data,
)


@pytest.fixture()
def schema_mapping():
    """Schema mapping de exemplo (2 tabelas)."""
    return {
        "tables": [
            {"target_table": "users", "estimated_rows": 5},
            {"target_table": "orders", "estimated_rows": 5},
        ]
    }


def _ok_response():
    """Resposta 2xx do /validate com contagens que batem (overall_passed=True)."""
    return httpx.Response(
        status_code=200,
        json={
            "job_id": "job-1",
            "overall_passed": True,
            "total_validations": 2,
            "passed_validations": 2,
            "failed_validations": 0,
            "results": [
                {
                    "table": "users",
                    "type": "row_count",
                    "passed": True,
                    "legacy_count": 5,
                    "modern_count": 5,
                    "discrepancy": 0,
                    "details": {},
                },
                {
                    "table": "orders",
                    "type": "row_count",
                    "passed": True,
                    "legacy_count": 5,
                    "modern_count": 5,
                    "discrepancy": 0,
                    "details": {},
                },
            ],
        },
        request=httpx.Request("POST", "http://data-migration:8019/x"),
    )


def _diverge_response():
    """Resposta 2xx do /validate com contagens divergentes (overall_passed=False)."""
    return httpx.Response(
        status_code=200,
        json={
            "job_id": "job-1",
            "overall_passed": False,
            "total_validations": 2,
            "passed_validations": 1,
            "failed_validations": 1,
            "results": [
                {
                    "table": "users",
                    "type": "row_count",
                    "passed": False,
                    "legacy_count": 5,
                    "modern_count": 0,
                    "discrepancy": 5,
                    "details": {"message": "5 registros faltando"},
                },
            ],
        },
        request=httpx.Request("POST", "http://data-migration:8019/x"),
    )


class _StubClient:
    """Stub mínimo de httpx.AsyncClient com `post` programável."""

    def __init__(self, *, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.mark.asyncio()
class TestValidateDataFailClosed:
    """Contrato fail-closed da validate_data."""

    async def test_validate_ok_counts_match(self, schema_mapping):
        """/validate 2xx com overall_passed=True → success=True + counts reais."""
        client = _StubClient(response=_ok_response())
        set_data_migration_dependencies(
            http_client=client, base_url="http://data-migration:8019"
        )

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is True
        report = result["validation_report"]
        assert report["overall_passed"] is True
        # counts REAIS vindos do serviço (não estimados)
        users = next(r for r in report["table_results"] if r["table"] == "users")
        assert users["legacy_rows"] == 5
        assert users["target_rows"] == 5
        assert users["row_count_match"] is True
        # URL do endpoint REAL chamado
        assert client.calls[0][0].endswith("/api/v1/migrations/job-1/validate")

    async def test_validate_counts_diverge_fails(self, schema_mapping):
        """/validate 2xx com overall_passed=False → success=False (FAILED)."""
        client = _StubClient(response=_diverge_response())
        set_data_migration_dependencies(
            http_client=client, base_url="http://data-migration:8019"
        )

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is False
        assert result["validation_report"]["overall_passed"] is False

    async def test_validate_http_error_fail_closed(self, schema_mapping):
        """Erro de rede httpx → success=False (fail-closed)."""
        client = _StubClient(
            exc=httpx.RequestError(
                "connection refused",
                request=httpx.Request("POST", "http://data-migration:8019/x"),
            )
        )
        set_data_migration_dependencies(http_client=client)

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is False
        assert result["validation_report"]["overall_passed"] is False
        assert "error" in result

    async def test_validate_timeout_fail_closed(self, schema_mapping):
        """Timeout httpx → success=False (fail-closed)."""
        client = _StubClient(
            exc=httpx.TimeoutException(
                "timed out",
                request=httpx.Request("POST", "http://data-migration:8019/x"),
            )
        )
        set_data_migration_dependencies(http_client=client)

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is False
        assert result["validation_report"]["overall_passed"] is False

    async def test_validate_http_5xx_fail_closed(self, schema_mapping):
        """HTTP 5xx → success=False (fail-closed)."""
        resp = httpx.Response(
            status_code=500,
            text="Internal Server Error",
            request=httpx.Request("POST", "http://data-migration:8019/x"),
        )
        client = _StubClient(response=resp)
        set_data_migration_dependencies(http_client=client)

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is False
        assert result["validation_report"]["overall_passed"] is False

    async def test_validate_http_4xx_fail_closed(self, schema_mapping):
        """HTTP 4xx → success=False (fail-closed)."""
        resp = httpx.Response(
            status_code=404,
            text="Not Found",
            request=httpx.Request("POST", "http://data-migration:8019/x"),
        )
        client = _StubClient(response=resp)
        set_data_migration_dependencies(http_client=client)

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is False
        assert result["validation_report"]["overall_passed"] is False

    async def test_validate_json_missing_field_fail_closed(self, schema_mapping):
        """JSON 2xx sem o campo overall_passed → success=False (fail-closed)."""
        resp = httpx.Response(
            status_code=200,
            json={"job_id": "job-1", "results": []},
            request=httpx.Request("POST", "http://data-migration:8019/x"),
        )
        client = _StubClient(response=resp)
        set_data_migration_dependencies(http_client=client)

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is False
        assert result["validation_report"]["overall_passed"] is False

    async def test_validate_no_http_client_fail_closed(self, schema_mapping):
        """http client NÃO configurado → success=False (não assume sucesso)."""
        set_data_migration_dependencies(http_client=None)

        result = await validate_data("job-1", schema_mapping)

        assert result["success"] is False
        assert result["validation_report"]["overall_passed"] is False
