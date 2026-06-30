"""Testes Fase 1 / Task 2 — prova de que ``get_table_count`` funciona contra um
PostgreSQL REAL (bug #2 da migração J4).

Bug #2 (``src/db/postgresql.py::get_table_count``): a query usava
``SELECT COUNT(*) FROM $1.$2`` com ``$1``/``$2`` em posição de IDENTIFICADOR
(schema/tabela). Em PostgreSQL os placeholders ligam apenas VALORES, logo a query
rebenta com ``syntax error at or near "$1"``. Este método é chamado por
``schema_mapper.analyze_legacy_schema`` durante ``POST /api/v1/migrations``.

Anti-verde-falso: o teste real abaixo FALHA com o código ``$1.$2`` antigo
(``asyncpg.exceptions.PostgresSyntaxError``) e PASSA com a interpolação validada.
O teste de identificador inválido prova que a interpolação NÃO abriu SQL injection
(a validação ``validate_sql_identifier`` continua a barrar).

Docker-gated: ``skipif`` limpo quando o daemon não está disponível (CI sem docker).
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from src.db.postgresql import PostgreSQLClient

# =============================================================================
# Oráculo de contagens — derivado de scripts/init-legacy-db.sql (blocos INSERT):
#   users -> 5, products -> 5, orders -> 5, order_items -> 9  (total 24)
# Espelha EXPECTED_LEGACY_COUNTS do gate Fase 0 (orchestrator j4_migrate_fixture).
# =============================================================================
EXPECTED_LEGACY_COUNTS: dict[str, int] = {
    "users": 5,
    "orders": 5,
    "products": 5,
    "order_items": 9,
}

# integration -> tests -> data-migration -> services -> raiz do repositório
_REPO_ROOT = Path(__file__).resolve().parents[4]
LEGACY_SEED_PATH = _REPO_ROOT / "scripts" / "init-legacy-db.sql"

_POSTGRES_IMAGE = "postgres:17-alpine"
_PG_PASSWORD = "j4_table_count_probe"
_PG_DB = "postgres"
_PG_USER = "postgres"


def _docker_available() -> bool:
    """True se o binário docker existe E o daemon responde rapidamente."""
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    else:
        return result.returncode == 0


_DOCKER = _docker_available()


def _wait_for_ready(container: str, timeout_s: int = 60) -> None:
    """Espera o Postgres aceitar ligações (loop pg_isready)."""
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        probe = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", _PG_USER],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if probe.returncode == 0:
            return
        last = (probe.stdout + probe.stderr).strip()
        time.sleep(1)
    raise TimeoutError(f"postgres não ficou pronto em {timeout_s}s: {last}")


def _published_port(container: str) -> int:
    """Descobre a porta de host publicada para o 5432 do container."""
    result = subprocess.run(
        ["docker", "port", container, "5432/tcp"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, f"docker port falhou: {result.stderr}"
    # Formato: "0.0.0.0:49153" (ou "[::]:49153"); usa o último campo após ':'.
    line = result.stdout.strip().splitlines()[0]
    return int(line.rsplit(":", 1)[1])


@pytest.fixture()
def seeded_postgres():
    """Arranca um postgres:17-alpine efémero com porta publicada, aplica o seed
    legacy e devolve o DSN. Remove o container em ``finally`` (cleanup garantido).
    """
    name = f"j4-tablecount-pg-{uuid.uuid4().hex[:8]}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            f"POSTGRES_PASSWORD={_PG_PASSWORD}",
            "-p",
            "127.0.0.1::5432",
            _POSTGRES_IMAGE,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if run.returncode != 0:
        pytest.skip(f"docker run falhou: {run.stderr.strip()}")

    try:
        _wait_for_ready(name, timeout_s=60)

        # Copiar e aplicar o seed (ON_ERROR_STOP=1 — aborta a qualquer erro).
        dest = "/tmp/init-legacy-db.sql"
        cp = subprocess.run(
            ["docker", "cp", str(LEGACY_SEED_PATH), f"{name}:{dest}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert cp.returncode == 0, f"docker cp falhou: {cp.stderr}"

        apply = subprocess.run(
            [
                "docker",
                "exec",
                name,
                "psql",
                "-U",
                _PG_USER,
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                dest,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert (
            apply.returncode == 0
        ), f"psql falhou ao aplicar o seed:\nSTDOUT:\n{apply.stdout}\nSTDERR:\n{apply.stderr}"

        port = _published_port(name)
        dsn = f"postgresql://{_PG_USER}:{_PG_PASSWORD}@127.0.0.1:{port}/{_PG_DB}"
        yield dsn
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            timeout=60,
            check=False,
        )


# =============================================================================
# Teste COM docker — caminho real (asyncpg) através de PostgreSQLClient
# =============================================================================


@pytest.mark.real_integration()
@pytest.mark.skipif(not _DOCKER, reason="docker indisponível (binário ou daemon)")
@pytest.mark.asyncio
async def test_get_table_count_real_returns_seed_counts(seeded_postgres):
    """``get_table_count`` devolve as contagens reais do seed SEM syntax error.

    Falharia com o código ``$1.$2`` antigo (PostgresSyntaxError em ``$1``).
    """
    client = PostgreSQLClient(dsn=seeded_postgres)
    await client.connect()
    try:
        actual = {
            table: await client.get_table_count(table_name=table, schema="public")
            for table in EXPECTED_LEGACY_COUNTS
        }
    finally:
        await client.disconnect()

    assert actual == EXPECTED_LEGACY_COUNTS, f"contagens reais != oráculo: {actual}"
    assert actual["users"] == 5
    assert actual["orders"] == 5
    assert actual["products"] == 5
    assert actual["order_items"] == 9
    assert sum(actual.values()) == 24


@pytest.mark.real_integration()
@pytest.mark.skipif(not _DOCKER, reason="docker indisponível (binário ou daemon)")
@pytest.mark.asyncio
async def test_analyze_legacy_schema_end_to_end_real(seeded_postgres):
    """``analyze_legacy_schema`` (que chama ``get_table_count``) corre end-to-end
    contra o PostgreSQL real e produz row_counts corretos por tabela.

    Reproduz o caminho de ``POST /api/v1/migrations`` onde o bug #2 explodia.
    """
    from src.services.schema_mapper import SchemaMapper

    client = PostgreSQLClient(dsn=seeded_postgres)
    await client.connect()
    try:
        mapper = SchemaMapper()
        analyzed = await mapper.analyze_legacy_schema(
            postgres_client=client,
            schema="public",
            tables=list(EXPECTED_LEGACY_COUNTS),
        )
    finally:
        await client.disconnect()

    row_counts = {t["name"]: t["row_count"] for t in analyzed["tables"]}
    assert row_counts == EXPECTED_LEGACY_COUNTS, f"row_counts != oráculo: {row_counts}"


# =============================================================================
# Teste SEM docker — a interpolação NÃO abriu SQL injection (corre sempre)
# =============================================================================


@pytest.mark.asyncio
async def test_get_table_count_rejects_injection_identifier():
    """Identificador malicioso é rejeitado por ``validate_sql_identifier``.

    Prova que interpolar ``{schema}.{table_name}`` na query (em vez de ``$1.$2``)
    NÃO criou um vetor de SQL injection: a validação precede qualquer query e o
    cliente nem chega a precisar de conexão.
    """
    client = PostgreSQLClient(dsn="postgresql://user:pass@localhost:5432/db")

    with pytest.raises(ValueError):
        await client.get_table_count(table_name="users; DROP TABLE x", schema="public")

    with pytest.raises(ValueError):
        await client.get_table_count(table_name="users", schema="public; DROP TABLE x")
