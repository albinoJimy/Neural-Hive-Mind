"""Testes Fase 3/4 — prova de que a ESCRITA real funciona (bug B da migração J4).

Bug B (``src/db/postgresql.py``): o ``target_client`` da migração é um
``PostgreSQLClient`` que NÃO tinha ``insert_batch``. Em ``BatchMigrator._migrate_table``
a escrita caía no ``raise BatchMigratorError("Target client não suporta...")`` →
0 linhas migradas (verde-falso: job "completed" sem dados no destino).

Este módulo prova, contra PostgreSQL REAL:
  1. ``insert_batch`` insere N linhas (SELECT COUNT(*) == N) e rejeita
     identificadores maliciosos (sem SQL injection).
  2. Round-trip ``fetch_batch`` (legacy) → ``insert_batch`` (modern) para as 4
     tabelas do seed, com contagens reais 5/5/5/9 (= 24).

Anti-verde-falso: SEM ``insert_batch`` (atributo ausente) o ``_migrate_table``
escrevia 0; COM a fix o destino fica com 24. O teste
``test_round_trip_*`` falharia se a escrita não persistisse.

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
# =============================================================================
EXPECTED_LEGACY_COUNTS: dict[str, int] = {
    "users": 5,
    "products": 5,
    "orders": 5,
    "order_items": 9,
}

# integration -> tests -> data-migration -> services -> raiz do repositório
_REPO_ROOT = Path(__file__).resolve().parents[4]
LEGACY_SEED_PATH = _REPO_ROOT / "scripts" / "init-legacy-db.sql"

# DDL do destino (schema ``modern``) — mesmas colunas do legado, SEM FKs
# (o objetivo é provar a ESCRITA/contagens; a integridade referencial não é o
# alvo deste teste). Ordem de inserção respeita as dependências do seed.
_MODERN_DDL = """
CREATE SCHEMA IF NOT EXISTS modern;
CREATE TABLE modern.users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    full_name VARCHAR(100),
    status VARCHAR(20),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE TABLE modern.products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    stock INTEGER,
    category VARCHAR(50),
    created_at TIMESTAMP
);
CREATE TABLE modern.orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE TABLE modern.order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL
);
"""

_POSTGRES_IMAGE = "postgres:17-alpine"
_PG_PASSWORD = "j4_insert_batch_probe"
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
    line = result.stdout.strip().splitlines()[0]
    return int(line.rsplit(":", 1)[1])


def _exec_sql(container: str, sql: str) -> None:
    """Executa SQL inline no container via psql (ON_ERROR_STOP=1)."""
    res = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", _PG_USER, "-v", "ON_ERROR_STOP=1"],
        input=sql,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 0, f"psql inline falhou:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"


@pytest.fixture()
def seeded_postgres():
    """Arranca um postgres:17-alpine efémero: aplica o seed legacy (schema
    ``public``) e cria o schema ``modern`` (tabelas vazias). Devolve o DSN.
    Remove o container em ``finally`` (cleanup garantido).
    """
    name = f"j4-insertbatch-pg-{uuid.uuid4().hex[:8]}"
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

        # Seed legacy (public) — ON_ERROR_STOP=1 aborta a qualquer erro.
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
            ["docker", "exec", name, "psql", "-U", _PG_USER, "-v", "ON_ERROR_STOP=1", "-f", dest],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert apply.returncode == 0, f"psql seed falhou:\n{apply.stdout}\n{apply.stderr}"

        # Destino moderno vazio.
        _exec_sql(name, _MODERN_DDL)

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
# Teste 1 — insert_batch real: N linhas escritas == N contadas
# =============================================================================


@pytest.mark.real_integration()
@pytest.mark.skipif(not _DOCKER, reason="docker indisponível (binário ou daemon)")
@pytest.mark.asyncio
async def test_insert_batch_real_writes_rows(seeded_postgres):
    """``insert_batch`` escreve N linhas numa tabela nova e ``COUNT(*) == N``."""
    client = PostgreSQLClient(dsn=seeded_postgres)
    await client.connect()
    try:
        await client.execute_query(
            "CREATE TABLE modern.widgets (id INTEGER PRIMARY KEY, name TEXT)",
            fetch="none",
        )
        rows = [{"id": i, "name": f"widget-{i}"} for i in range(1, 8)]  # 7 linhas

        inserted = await client.insert_batch(table="widgets", data=rows, schema="modern")
        assert inserted == 7

        count = await client.get_table_count(table_name="widgets", schema="modern")
        assert count == 7, f"esperado 7, obtido {count}"

        # Lista vazia → 0 (sem query).
        assert await client.insert_batch(table="widgets", data=[], schema="modern") == 0
    finally:
        await client.disconnect()


@pytest.mark.real_integration()
@pytest.mark.skipif(not _DOCKER, reason="docker indisponível (binário ou daemon)")
@pytest.mark.asyncio
async def test_insert_batch_rejects_injection_identifiers(seeded_postgres):
    """Tabela/coluna/schema maliciosos → ``ValueError`` ANTES de qualquer query
    (a interpolação dos identificadores não abriu SQL injection).
    """
    client = PostgreSQLClient(dsn=seeded_postgres)
    await client.connect()
    try:
        with pytest.raises(ValueError):
            await client.insert_batch(
                table="users; DROP TABLE modern.users", data=[{"id": 1}], schema="modern"
            )
        with pytest.raises(ValueError):
            await client.insert_batch(
                table="users", data=[{"id": 1}], schema="modern; DROP TABLE x"
            )
        with pytest.raises(ValueError):
            await client.insert_batch(
                table="users",
                data=[{"id": 1, "evil; DROP TABLE x": 2}],
                schema="modern",
            )
    finally:
        await client.disconnect()


# =============================================================================
# Teste 2 — round-trip real legacy→modern: 5/5/5/9 (= 24)
# =============================================================================


@pytest.mark.real_integration()
@pytest.mark.skipif(not _DOCKER, reason="docker indisponível (binário ou daemon)")
@pytest.mark.asyncio
async def test_round_trip_legacy_to_modern_real_counts(seeded_postgres):
    """``fetch_batch`` (public) → ``insert_batch`` (modern) move as 4 tabelas do
    seed com contagens reais 5/5/5/9. Prova a ESCRITA real (bug B).
    """
    client = PostgreSQLClient(dsn=seeded_postgres)
    await client.connect()
    try:
        # Ordem respeita dependências do seed (users/products antes de orders/items).
        migrated: dict[str, int] = {}
        for table in ("users", "products", "orders", "order_items"):
            batch = await client.fetch_batch(
                table_name=table, offset=0, batch_size=1000, schema="public"
            )
            written = await client.insert_batch(table=table, data=batch, schema="modern")
            migrated[table] = written

        # Confirmar pela CONTAGEM real no destino (não pelo valor devolvido).
        actual = {
            table: await client.get_table_count(table_name=table, schema="modern")
            for table in EXPECTED_LEGACY_COUNTS
        }
    finally:
        await client.disconnect()

    assert migrated == EXPECTED_LEGACY_COUNTS, f"escritas != oráculo: {migrated}"
    assert actual == EXPECTED_LEGACY_COUNTS, f"contagens destino != oráculo: {actual}"
    assert sum(actual.values()) == 24, f"total migrado != 24: {sum(actual.values())}"
