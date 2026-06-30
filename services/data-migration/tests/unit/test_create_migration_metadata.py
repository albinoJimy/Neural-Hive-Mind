"""Teste Fase 3/4 — ``create_migration`` persiste as db_urls em ``metadata``
(bug A da migração J4 real).

Bug A (``src/api/routers/migrations.py::create_migration``): o handler criava o
``MigrationJob`` SEM guardar ``legacy_db_url``/``modern_db_url`` em ``metadata``.
``/start``, ``/validate`` e ``/rollback`` lêem
``job_dict["metadata"]["legacy_db_url"]``/``["modern_db_url"]`` → obtêm None →
falham (``/validate`` devolve 400 "Database connection URLs not found").

Anti-verde-falso: este teste captura o ``job_dict`` realmente passado a
``insert_migration_job`` e exige as duas URLs em ``metadata``. SEM a fix o dict
não as contém e o teste FALHA.

Sem docker: mocka ``PostgreSQLClient`` (ligações), ``get_schema_mapper`` (análise)
e o ``mongodb_client``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.routers.migrations import MigrationCreateRequest, create_migration

_LEGACY_URL = "postgresql://legacy_user:legacy_pw@legacy-host:5432/legacy_db"
_MODERN_URL = "postgresql://modern_user:modern_pw@modern-host:5432/modern_db"


@pytest.mark.asyncio
async def test_create_migration_persists_db_urls_in_metadata():
    """O ``job_dict`` inserido no Mongo contém ``metadata.legacy_db_url`` e
    ``metadata.modern_db_url`` com as URLs do request.
    """
    request = MigrationCreateRequest(
        legacy_db_url=_LEGACY_URL,
        modern_db_url=_MODERN_URL,
        tables=["users", "orders"],
        batch_size=500,
    )

    # mongodb_client: captura o que foi inserido.
    mongodb_client = AsyncMock()
    mongodb_client.insert_schema_mapping = AsyncMock()
    mongodb_client.insert_migration_job = AsyncMock()

    # schema_mapper: análise e geração de mapeamento (ambos awaited).
    schema_mapper = MagicMock()
    schema_mapper.analyze_legacy_schema = AsyncMock(
        return_value={"tables": [{"name": "users", "row_count": 5}]}
    )
    fake_mapping = MagicMock()
    fake_mapping.model_dump = MagicMock(return_value={"tables": [{"name": "users"}]})
    schema_mapper.generate_schema_mapping = AsyncMock(return_value=fake_mapping)

    # PostgreSQLClient: ligações reais substituídas por no-ops async.
    fake_pg = MagicMock()
    fake_pg.connect = AsyncMock()
    fake_pg.disconnect = AsyncMock()

    background_tasks = MagicMock()

    with patch("src.api.routers.migrations.PostgreSQLClient", return_value=fake_pg), patch(
        "src.services.schema_mapper.get_schema_mapper", return_value=schema_mapper
    ):
        response = await create_migration(
            request=request,
            background_tasks=background_tasks,
            mongodb_client=mongodb_client,
        )

    # O job foi inserido exatamente uma vez.
    mongodb_client.insert_migration_job.assert_awaited_once()
    job_dict = mongodb_client.insert_migration_job.await_args.args[0]

    assert "metadata" in job_dict, "job_dict não tem campo metadata"
    assert job_dict["metadata"]["legacy_db_url"] == _LEGACY_URL
    assert job_dict["metadata"]["modern_db_url"] == _MODERN_URL
    assert job_dict["job_id"] == response.job_id
