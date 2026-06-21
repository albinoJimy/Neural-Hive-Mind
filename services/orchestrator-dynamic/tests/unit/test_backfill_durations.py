"""
Unit tests para o backfill de durações reais Postgres → Mongo.

Cobre a função pura `build_duration_fields` (Task 9 da spec
caminho-real-first-class): mapeia uma linha do PostgreSQL `sla_management`
para os campos de duração a persistir no Mongo, com `completed_at`/`started_at`
como datetime (BSON Date) — consistentes com os filtros de treino do
DurationPredictor.
"""

from datetime import datetime, timezone

from scripts.backfill_durations_from_sla import build_duration_fields

UTC = timezone.utc


class TestBuildDurationFields:
    def test_normal_row_returns_datetime_fields(self):
        completed = datetime(2026, 6, 18, 15, 3, 54, tzinfo=UTC)
        created = datetime(2026, 6, 18, 15, 3, 43, tzinfo=UTC)
        fields = build_duration_fields(
            {
                "actual_duration_ms": 11000,
                "started_at": None,
                "completed_at": None,
                "created_at": created,
                "updated_at": completed,
            }
        )
        assert fields is not None
        assert fields["actual_duration_ms"] == 11000
        # completed_at cai para updated_at quando completed_at ausente
        assert fields["completed_at"] == completed
        assert isinstance(fields["completed_at"], datetime)
        # started_at derivado de completed_at - duração
        assert fields["started_at"] == datetime(2026, 6, 18, 15, 3, 43, tzinfo=UTC)

    def test_uses_explicit_started_and_completed_when_present(self):
        started = datetime(2026, 6, 18, 10, 0, 0, tzinfo=UTC)
        completed = datetime(2026, 6, 18, 10, 0, 5, tzinfo=UTC)
        fields = build_duration_fields(
            {
                "actual_duration_ms": 5000,
                "started_at": started,
                "completed_at": completed,
                "created_at": None,
                "updated_at": None,
            }
        )
        assert fields["started_at"] == started
        assert fields["completed_at"] == completed

    def test_invalid_duration_returns_none(self):
        base = {"updated_at": datetime.now(UTC), "created_at": None, "started_at": None}
        assert build_duration_fields({**base, "actual_duration_ms": None}) is None
        assert build_duration_fields({**base, "actual_duration_ms": 0}) is None
        assert build_duration_fields({**base, "actual_duration_ms": -5}) is None
        # bool não conta como duração válida
        assert build_duration_fields({**base, "actual_duration_ms": True}) is None

    def test_naive_datetime_becomes_utc_aware(self):
        naive = datetime(2026, 6, 18, 12, 0, 0)  # noqa: DTZ001 — naïve é o caso em teste
        fields = build_duration_fields(
            {
                "actual_duration_ms": 1000,
                "started_at": None,
                "completed_at": naive,
                "created_at": None,
                "updated_at": None,
            }
        )
        assert fields["completed_at"].tzinfo is not None
        assert fields["completed_at"] == naive.replace(tzinfo=UTC)

    def test_epoch_ms_and_iso_string_are_parsed(self):
        epoch_ms = 1_750_000_000_000
        fields = build_duration_fields(
            {
                "actual_duration_ms": 2000,
                "started_at": None,
                "completed_at": epoch_ms,
                "created_at": "2026-06-18T15:03:43Z",
                "updated_at": None,
            }
        )
        assert fields["completed_at"] == datetime.fromtimestamp(epoch_ms / 1000.0, tz=UTC)

    def test_idempotent(self):
        row = {
            "actual_duration_ms": 3000,
            "started_at": None,
            "completed_at": None,
            "created_at": datetime(2026, 6, 18, 9, 0, 0, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 18, 9, 0, 3, tzinfo=UTC),
        }
        assert build_duration_fields(dict(row)) == build_duration_fields(dict(row))
