"""Fixtures reprodutíveis do gate "J4/MIGRATE fiável" (Fase 0 / Task 1).

Dois artefactos determinísticos e testáveis, sem dependências de runtime:

1. **Oráculo de contagens** — as contagens conhecidas por tabela do seed legacy
   (``scripts/init-legacy-db.sql``). Serve de oráculo da validação pós-migração
   (Fases 2/4): destino migrado deve ter ``rows == N`` por tabela.

2. **Harness de injeção J4** — função PURA que constrói a mensagem de "plano
   direto" ``J4_MIGRATE`` pronta a produzir no topic ``plans.consensus`` (espelha
   o método do gate 3.3). A produção real para Kafka é uma função separada e
   opcional (``produce_j4_migrate_plan``), não exercitada em unit.

NOTA (escopo Fase 0): este módulo apenas DEFINE e testa em bloco. A EXECUÇÃO real
do fixture (correr docker-compose / migração) é da Fase 4.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

# =============================================================================
# Localização do seed legacy (fonte da verdade das contagens)
# =============================================================================

# Subir 4 níveis a partir deste ficheiro chega à raiz do repositório:
# integration -> tests -> orchestrator-dynamic -> services -> raiz.
_REPO_ROOT = Path(__file__).resolve().parents[4]
LEGACY_SEED_PATH = _REPO_ROOT / "scripts" / "init-legacy-db.sql"
MODERN_SEED_PATH = _REPO_ROOT / "scripts" / "init-modern-db.sql"

# Tabelas-alvo da migração (espelham o DDL do seed).
MIGRATION_TABLES = ["users", "orders", "products", "order_items"]

# Contagens conhecidas do seed legacy — referência explícita a
# scripts/init-legacy-db.sql (blocos INSERT ... VALUES):
#   users       -> 5 linhas
#   products    -> 5 linhas
#   orders      -> 5 linhas
#   order_items -> 9 linhas
# Estas constantes são o oráculo; ``parse_legacy_seed_counts`` confirma que
# continuam a bater com o ficheiro real (anti-drift).
EXPECTED_LEGACY_COUNTS: dict[str, int] = {
    "users": 5,
    "orders": 5,
    "products": 5,
    "order_items": 9,
}


# =============================================================================
# Oráculo de contagens (determinístico, derivado do seed)
# =============================================================================

# Captura "INSERT INTO <tabela> (<colunas>) VALUES <tuplos>;"
_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(\w+)\s*\([^)]*\)\s*VALUES\s*(.*?);",
    re.IGNORECASE | re.DOTALL,
)


def _count_value_tuples(values_segment: str) -> int:
    """Conta os tuplos de topo ``(...)`` num segmento VALUES (depth-aware)."""
    depth = 0
    tuples = 0
    for ch in values_segment:
        if ch == "(":
            if depth == 0:
                tuples += 1
            depth += 1
        elif ch == ")":
            depth -= 1
    return tuples


def parse_legacy_seed_counts(sql_path: Path | str = LEGACY_SEED_PATH) -> dict[str, int]:
    """Parse das contagens por tabela a partir dos INSERTs do seed legacy.

    Determinístico: conta os tuplos ``(...)`` de cada ``INSERT INTO ... VALUES``.
    Usado para validar que ``EXPECTED_LEGACY_COUNTS`` não derivou do ficheiro real.
    """
    text = Path(sql_path).read_text(encoding="utf-8")
    counts: dict[str, int] = {}
    for match in _INSERT_RE.finditer(text):
        table = match.group(1).lower()
        counts[table] = counts.get(table, 0) + _count_value_tuples(match.group(2))
    return counts


def expected_legacy_counts() -> dict[str, int]:
    """Devolve as contagens-oráculo conhecidas (cópia defensiva)."""
    return dict(EXPECTED_LEGACY_COUNTS)


def legacy_row_count(table: str) -> int:
    """Contagem-oráculo de uma tabela do seed legacy."""
    return EXPECTED_LEGACY_COUNTS[table]


# =============================================================================
# Harness de injeção J4 (função PURA — só constrói a mensagem)
# =============================================================================


# DSNs default dos fixtures J4 (DNS dos PostgreSQL legacy/modern no cluster).
DEFAULT_LEGACY_DB_URL = (
    "postgresql://legacy_user:legacy_pass@"
    "j4-postgres-legacy.neural-hive.svc.cluster.local:5432/legacy_db"
)
DEFAULT_MODERN_DB_URL = (
    "postgresql://modern_user:modern_pass@"
    "j4-postgres-modern.neural-hive.svc.cluster.local:5432/modern_db"
)


def build_j4_migrate_plan_message(
    *,
    plan_id: str | None = None,
    tables: list[str] | None = None,
    legacy_connection_id: str = "postgres-legacy",
    modern_connection_id: str = "postgres-modern",
    schema: str = "public",
    risk_band: str = "medium",
    source: str = "doc-ingestion",
    legacy_db_url: str | None = None,
    modern_db_url: str | None = None,
) -> dict:
    """Constrói a mensagem de PLANO DIRETO ``J4_MIGRATE`` para ``plans.consensus``.

    Espelha o método do gate 3.3: plano direto JSON (com ``tasks``, sem
    ``decision_id`` — o consumer trata-o como ``is_direct_plan``). A journey
    ``J4_MIGRATE`` e o sinal ``context.source == "doc-ingestion"`` reproduzem a
    classificação do STE; ``migration_config`` carrega o spec de migração
    (legacy/modern + tabelas) consumido pelo ``DataMigrationWorkflow``.

    Função PURA: não toca em Kafka nem em I/O (a produção real é
    ``produce_j4_migrate_plan``).
    """
    plan_id = plan_id or f"j4-migrate-{uuid.uuid4().hex[:12]}"
    table_list = list(tables) if tables is not None else list(MIGRATION_TABLES)
    legacy_db_url = legacy_db_url if legacy_db_url is not None else DEFAULT_LEGACY_DB_URL
    modern_db_url = modern_db_url if modern_db_url is not None else DEFAULT_MODERN_DB_URL

    tasks = [
        {
            "task_id": f"{plan_id}-migrate",
            "task_type": "migrate",
            "description": "Migrar schema+dados do PostgreSQL legacy para o moderno",
        }
    ]

    return {
        "plan_id": plan_id,
        "journey": "J4_MIGRATE",
        "context": {"source": source},
        "tasks": tasks,
        "execution_order": [task["task_id"] for task in tasks],
        "risk_band": risk_band,
        "migration_config": {
            "legacy_connection_id": legacy_connection_id,
            "modern_connection_id": modern_connection_id,
            "schema": schema,
            "tables": table_list,
            "legacy_db_url": legacy_db_url,
            "modern_db_url": modern_db_url,
        },
        # PLANO DIRETO: NÃO incluir "decision_id" (aciona is_direct_plan no consumer).
    }


def serialize_plan_message(message: dict) -> bytes:
    """Serializa o plano para bytes JSON (formato aceite por plans.consensus)."""
    return json.dumps(message, ensure_ascii=False).encode("utf-8")


def produce_j4_migrate_plan(
    bootstrap_servers: str,
    message: dict | None = None,
    topic: str = "plans.consensus",
):  # pragma: no cover - produção real, não exercitada em unit
    """Produz (REAL) o plano J4 no topic ``plans.consensus``.

    Função SEPARADA e OPCIONAL: só usada na prova E2E (Fase 4), de dentro do pod
    orchestrator (Kafka interno plaintext :9092). Importa ``kafka`` localmente
    para não acoplar os testes unitários a um broker.
    """
    from kafka import KafkaProducer

    if message is None:
        message = build_j4_migrate_plan_message()

    producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
    try:
        future = producer.send(topic, serialize_plan_message(message))
        producer.flush()
        return future.get(timeout=10)
    finally:
        producer.close()
