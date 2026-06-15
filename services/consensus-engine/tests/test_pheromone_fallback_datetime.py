"""Testes para a normalização de datetime no fallback MongoDB das feromonas.

Regressão (FIX-CP-001 / BUG-3): comparações de expires_at falhavam com
"can't compare offset-naive and offset-aware datetimes" e
"'<' not supported between instances of 'str' and 'datetime.datetime'"
quando o documento vinha do MongoDB como string ISO ou datetime naive.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.clients.pheromone_client import _to_aware_datetime


def test_iso_string_naive_to_aware():
    """String ISO sem timezone deve tornar-se datetime aware (UTC)."""
    result = _to_aware_datetime("2026-06-15T12:00:00")
    assert result is not None
    assert result.tzinfo is not None
    # comparação com aware não deve levantar TypeError
    assert isinstance(result < datetime.now(timezone.utc), bool)


def test_iso_string_with_offset_preserved_as_utc():
    """String ISO com offset deve ser convertida para UTC aware."""
    result = _to_aware_datetime("2026-06-15T12:00:00+00:00")
    assert result is not None
    assert result.tzinfo is not None


def test_naive_datetime_becomes_aware():
    """datetime naive (como Motor sem tz_aware) deve tornar-se aware."""
    naive = datetime(2026, 6, 15, 12, 0, 0)
    result = _to_aware_datetime(naive)
    assert result.tzinfo is not None
    assert isinstance(result < datetime.now(timezone.utc), bool)


def test_aware_datetime_unchanged_semantics():
    """datetime já aware mantém-se aware e comparável."""
    aware = datetime.now(timezone.utc) + timedelta(hours=1)
    result = _to_aware_datetime(aware)
    assert result.tzinfo is not None
    assert result > datetime.now(timezone.utc)


@pytest.mark.parametrize("value", [None, "", "not-a-date"])
def test_invalid_values_return_none(value):
    """Valores vazios/invalidos devolvem None (sem levantar excecao)."""
    assert _to_aware_datetime(value) is None


def test_expired_comparison_does_not_raise_for_string():
    """O cenario original do bug: string ISO comparada com now() nao deve falhar."""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    normalized = _to_aware_datetime(past)
    assert normalized is not None
    assert normalized < datetime.now(timezone.utc)  # expirado, sem TypeError
