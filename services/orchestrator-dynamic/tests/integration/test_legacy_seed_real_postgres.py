"""Testes Fase 0 / Task 1 — prova de que o seed legacy parseia num PostgreSQL REAL.

Anti-verde-falso para o bug #3 do seed (``scripts/init-legacy-db.sql``):

1. Comentários estilo shell ``#`` (inválidos em SQL).
2. ``CREATE EXTENSION IF NOT EXISTS "pgoutput";`` — ``pgoutput`` é um output plugin
   de logical decoding embutido no PostgreSQL, não uma extensão instalável.

Ambos rebentam num ``psql -v ON_ERROR_STOP=1`` real. O teste docker prova que o
seed corrigido aplica limpo e produz exatamente 4 tabelas e 24 linhas (o oráculo
de ``j4_migrate_fixture``). Com o seed original, FALHARIA.

O teste sem-docker confirma o oráculo inalterado e corre sempre (CI sem docker).
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid

import pytest

from tests.integration.j4_migrate_fixture import (
    EXPECTED_LEGACY_COUNTS,
    LEGACY_SEED_PATH,
    parse_legacy_seed_counts,
)

# =============================================================================
# Gate de disponibilidade do docker (skip limpo em CI sem daemon)
# =============================================================================

_POSTGRES_IMAGE = "postgres:17-alpine"
_PG_PASSWORD = "j4_seed_probe"


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


# =============================================================================
# Teste SEM docker — corre sempre (confirma o oráculo inalterado)
# =============================================================================


class TestLegacySeedOracleStable:
    """O oráculo do seed continua exatamente como esperado (anti-drift)."""

    def test_oracle_matches_seed_file(self):
        assert parse_legacy_seed_counts() == EXPECTED_LEGACY_COUNTS

    def test_oracle_total_is_24(self):
        assert sum(EXPECTED_LEGACY_COUNTS.values()) == 24


# =============================================================================
# Teste COM docker — PostgreSQL REAL aplica o seed corrigido
# =============================================================================


@pytest.fixture()
def postgres_container():
    """Arranca um postgres:17-alpine efémero (sem porta publicada) e limpa-o.

    Acesso só via ``docker exec`` para evitar colisões de porta. Garante remoção
    em ``finally`` mesmo se a espera por prontidão falhar.
    """
    name = f"j4-seed-pg-{uuid.uuid4().hex[:8]}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            f"POSTGRES_PASSWORD={_PG_PASSWORD}",
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
        yield name
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            timeout=60,
            check=False,
        )


def _wait_for_ready(container: str, timeout_s: int = 60) -> None:
    """Espera o Postgres aceitar ligações (loop pg_isready)."""
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        probe = subprocess.run(
            ["docker", "exec", container, "pg_isready", "-U", "postgres"],
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


@pytest.mark.real_integration()
@pytest.mark.skipif(not _DOCKER, reason="docker indisponível (binário ou daemon)")
def test_legacy_seed_applies_on_real_postgres(postgres_container):
    """O seed CORRIGIDO aplica com ON_ERROR_STOP e produz 4 tabelas / 24 linhas.

    Falharia com o seed original (``#`` + ``CREATE EXTENSION pgoutput``), pois
    ``ON_ERROR_STOP=1`` aborta no primeiro erro de sintaxe.
    """
    container = postgres_container

    # 1. Copiar o seed para dentro do container (não hardcodar caminho: reusa o módulo).
    dest = "/tmp/init-legacy-db.sql"
    cp = subprocess.run(
        ["docker", "cp", str(LEGACY_SEED_PATH), f"{container}:{dest}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert cp.returncode == 0, f"docker cp falhou: {cp.stderr}"

    # 2. Aplicar com ON_ERROR_STOP=1 (o '#'/pgoutput rebentam aqui se presentes).
    apply = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "postgres",
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
    assert apply.returncode == 0, (
        f"psql falhou ao aplicar o seed (ON_ERROR_STOP=1):\n"
        f"STDOUT:\n{apply.stdout}\nSTDERR:\n{apply.stderr}"
    )

    # 3. Exatamente 4 tabelas no schema public.
    tables = _psql_scalar(
        container,
        "SELECT string_agg(tablename, ',' ORDER BY tablename) "
        "FROM pg_tables WHERE schemaname = 'public';",
    )
    assert set(tables.split(",")) == set(EXPECTED_LEGACY_COUNTS), f"tabelas inesperadas: {tables}"

    # 4. Contagens por tabela == oráculo; soma == 24.
    actual: dict[str, int] = {}
    for table in EXPECTED_LEGACY_COUNTS:
        actual[table] = int(_psql_scalar(container, f"SELECT COUNT(*) FROM {table};"))

    assert actual == EXPECTED_LEGACY_COUNTS, f"contagens reais != oráculo: {actual}"
    assert sum(actual.values()) == 24


def _psql_scalar(container: str, sql: str) -> str:
    """Executa SQL via ``psql -tAc`` e devolve o escalar (linha única, sem fluff)."""
    result = subprocess.run(
        ["docker", "exec", container, "psql", "-U", "postgres", "-tAc", sql],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"psql query falhou: {result.stderr}"
    return result.stdout.strip()
