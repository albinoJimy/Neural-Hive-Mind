"""
Backfill one-time de durações reais Postgres (sla_management) → MongoDB
(neural_hive_orchestration.execution_tickets).

Contexto (spec caminho-real-first-class, Tasks 9 e 12):
    O worker computa `actual_duration_ms` e reporta-o por dois caminhos — Kafka
    `execution.results` (consumido pelo orchestrator) e gRPC para o
    execution-ticket-service (PostgreSQL `sla_management`). Historicamente a
    duração só chegava ao PostgreSQL; o `DurationPredictor` lê do MongoDB e via
    `actual_duration_ms=None`. O fix #1 (Task 12) corrige o caminho FUTURO
    (consumer persiste no Mongo). Este script corrige o PASSADO: traz as
    durações reais já registadas no PostgreSQL para o Mongo, desbloqueando o
    treino do `DurationPredictor` pelo seu caminho normal (sem dados sintéticos).

Idempotente: re-correr produz o mesmo estado (escreve sempre os mesmos campos
derivados; não duplica documentos — só faz $set por ticket_id).

`completed_at`/`started_at` são gravados como datetime (BSON Date), consistente
com os filtros `completed_at >= cutoff_date:datetime` do treino/stats.

Execução (in-cluster, pod com acesso a Postgres sla_management + Mongo):
    POSTGRES_HOST=... POSTGRES_USER=... POSTGRES_PASSWORD=... \
    POSTGRES_DATABASE=sla_management MONGODB_URI=... \
    MONGODB_DATABASE=neural_hive_orchestration \
    python3 backfill_durations_from_sla.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

UTC = timezone.utc


def build_duration_fields(row: dict[str, Any]) -> dict[str, Any] | None:
    """
    Constrói os campos de duração a persistir no Mongo a partir de uma linha
    do PostgreSQL `execution_tickets`.

    Regras:
    - `actual_duration_ms` tem de ser numérico > 0; caso contrário devolve None
      (não se escreve duração inválida por cima).
    - `completed_at`: usa o `completed_at` da linha se existir; senão `updated_at`
      (instante em que o ticket foi finalizado). Garante datetime tz-aware (UTC).
    - `started_at`: usa `started_at` se existir; senão deriva de
      `completed_at - actual_duration_ms`; em último caso usa `created_at`.

    Returns:
        Dict com {actual_duration_ms:int, completed_at:datetime, started_at:datetime}
        ou None se a duração for inválida.
    """
    duration = row.get("actual_duration_ms")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        return None
    duration = int(duration)

    completed_at = _as_utc_datetime(row.get("completed_at")) or _as_utc_datetime(
        row.get("updated_at")
    )

    started_at = _as_utc_datetime(row.get("started_at"))
    if started_at is None and completed_at is not None:
        started_at = completed_at - timedelta(milliseconds=duration)
    if started_at is None:
        started_at = _as_utc_datetime(row.get("created_at"))

    fields: dict[str, Any] = {"actual_duration_ms": duration}
    if completed_at is not None:
        fields["completed_at"] = completed_at
    if started_at is not None:
        fields["started_at"] = started_at
    return fields


def _as_utc_datetime(value: Any) -> datetime | None:
    """Normaliza um valor temporal para datetime tz-aware (UTC) ou None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # epoch ms
        return datetime.fromtimestamp(value / 1000.0, tz=UTC)
    return None


async def _run() -> dict[str, int]:
    import asyncpg
    from pymongo import MongoClient

    pg = await asyncpg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        user=os.environ["POSTGRES_USER"],
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        database=os.environ.get("POSTGRES_DATABASE", "sla_management"),
    )
    rows = await pg.fetch(
        "SELECT ticket_id, actual_duration_ms, started_at, completed_at, "
        "created_at, updated_at FROM execution_tickets "
        "WHERE actual_duration_ms IS NOT NULL AND actual_duration_ms > 0"
    )
    await pg.close()

    mongo = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=30000)
    col = mongo[os.environ.get("MONGODB_DATABASE", "neural_hive_orchestration")][
        "execution_tickets"
    ]

    stats = {"pg_rows": len(rows), "updated": 0, "not_in_mongo": 0, "skipped": 0}
    for row in rows:
        fields = build_duration_fields(dict(row))
        if fields is None:
            stats["skipped"] += 1
            continue
        res = col.update_one({"ticket_id": str(row["ticket_id"])}, {"$set": fields})
        if res.matched_count:
            stats["updated"] += 1
        else:
            stats["not_in_mongo"] += 1
    return stats


if __name__ == "__main__":
    result = asyncio.run(_run())
    print(f"[backfill_durations_from_sla] {result}")
