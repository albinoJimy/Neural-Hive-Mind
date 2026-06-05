"""Testes de regressão para timezone-awareness do PheromoneSignal.

Cobre o bug que bloqueava o processamento de consenso: `created_at` usava
`datetime.utcnow()` (naive). Como `calculate_current_strength()` subtrai
`created_at` de `datetime.now(timezone.utc)` (aware), o consenso rebentava com
`TypeError: can't subtract offset-naive and offset-aware datetimes` no passo de
feromônios — e o offset Kafka não era commitado, prendendo o consumer em loop.
"""

from datetime import datetime, timedelta, timezone

from src.models.pheromone_signal import PheromoneSignal


def _signal(**overrides):
    base = dict(
        specialist_type="technical",
        domain="technical",
        pheromone_type="success",
        strength=0.8,
        plan_id="plan-1",
        intent_id="intent-1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    base.update(overrides)
    return PheromoneSignal(**base)


class TestPheromoneSignalTimezone:
    def test_created_at_default_e_aware(self):
        """O default de created_at tem de ser tz-aware (UTC)."""
        signal = _signal()
        assert signal.created_at.tzinfo is not None

    def test_created_at_naive_e_coagido_para_aware(self):
        """created_at naive (feromônio antigo no Redis) é coagido para UTC-aware."""
        signal = _signal(created_at=datetime.utcnow())  # naive de proposito
        assert signal.created_at.tzinfo is not None

    def test_expires_at_naive_e_coagido_para_aware(self):
        signal = _signal(expires_at=datetime.utcnow() + timedelta(hours=1))
        assert signal.expires_at.tzinfo is not None

    def test_calculate_current_strength_nao_rebenta_com_created_at_naive(self):
        """Regressão direta: a subtração aware - (naive coagido) não levanta TypeError."""
        signal = _signal(strength=0.8, created_at=datetime.utcnow())
        strength = signal.calculate_current_strength()
        assert 0.0 <= strength <= 0.8

    def test_decay_temporal_aplicado(self):
        """Feromônio criado há 10h decai abaixo da força inicial."""
        signal = _signal(
            strength=1.0,
            decay_rate=0.1,
            created_at=datetime.now(timezone.utc) - timedelta(hours=10),
        )
        assert signal.calculate_current_strength() < 1.0
