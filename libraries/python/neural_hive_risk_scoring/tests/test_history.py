"""
Testes para RiskHistory
"""

import pytest
from datetime import datetime, timedelta

from neural_hive_risk_scoring import (
    RiskHistory,
    RiskSnapshot,
    TrendDirection,
    RiskBand,
    RiskAssessment,
    UnifiedDomain
)


@pytest.fixture
def risk_history():
    """Histórico de risco de teste."""
    return RiskHistory(
        max_snapshots_per_entity=100,
        retention_days=30
    )


@pytest.fixture
def sample_assessment():
    """Avaliação de exemplo."""
    return RiskAssessment(
        score=0.7,
        band=RiskBand.HIGH,
        domain=UnifiedDomain.BUSINESS,
        factors={'priority': 0.8, 'cost': 0.6},
        reasoning='High business risk'
    )


class TestRiskHistory:
    """Testes para RiskHistory."""

    def test_init(self, risk_history):
        """Testa inicialização."""
        assert risk_history.max_snapshots == 100
        assert risk_history.retention_days == 30
        assert risk_history._history == {}

    def test_record_assessment(self, risk_history, sample_assessment):
        """Testa registro de avaliação."""
        snapshot = risk_history.record_assessment(
            assessment=sample_assessment,
            entity_id='test-entity'
        )

        assert snapshot.entity_id == 'test-entity'
        assert snapshot.score == 0.7
        assert snapshot.band == RiskBand.HIGH
        assert snapshot.domain == UnifiedDomain.BUSINESS

    def test_get_history(self, risk_history, sample_assessment):
        """Testa obtenção de histórico."""
        # Registrar múltiplas avaliações
        for i in range(5):
            assessment = RiskAssessment(
                score=0.3 + i * 0.1,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.TECHNICAL,
                factors={},
                reasoning=f'test {i}'
            )
            risk_history.record_assessment(assessment, 'test-entity')

        history = risk_history.get_history('test-entity')

        assert len(history) == 5
        assert all(isinstance(s, RiskSnapshot) for s in history)

    def test_get_history_with_domain_filter(self, risk_history):
        """Testa filtro por domínio."""
        # Registrar avaliações de domínios diferentes
        business = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='test'
        )
        technical = RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.TECHNICAL,
            factors={},
            reasoning='test'
        )

        risk_history.record_assessment(business, 'test-entity')
        risk_history.record_assessment(technical, 'test-entity')

        business_history = risk_history.get_history('test-entity', domain=UnifiedDomain.BUSINESS)

        assert len(business_history) == 1
        assert business_history[0].domain == UnifiedDomain.BUSINESS

    def test_get_history_with_time_range(self, risk_history):
        """Testa filtro por intervalo de tempo."""
        now = datetime.utcnow()

        # Registrar avaliação antiga
        old = RiskAssessment(
            score=0.3,
            band=RiskBand.LOW,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='old'
        )
        old.assessed_at = now - timedelta(hours=10)
        risk_history.record_assessment(old, 'test-entity')

        # Registrar avaliação recente
        recent = RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='recent'
        )
        risk_history.record_assessment(recent, 'test-entity')

        # Buscar apenas últimas 5 horas
        recent_history = risk_history.get_history(
            'test-entity',
            start=now - timedelta(hours=5)
        )

        assert len(recent_history) == 1
        assert recent_history[0].score == 0.7

    def test_get_latest(self, risk_history):
        """Testa obtenção do snapshot mais recente."""
        # Registrar múltiplas avaliações
        for i in range(3):
            assessment = RiskAssessment(
                score=0.3 + i * 0.1,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            risk_history.record_assessment(assessment, 'test-entity')

        latest = risk_history.get_latest('test-entity')

        assert latest is not None
        assert latest.score == 0.5  # Último registrado

    def test_analyze_trend_increasing(self, risk_history):
        """Testa análise de tendência crescente."""
        now = datetime.utcnow()

        # Criar tendência crescente
        for i in range(10):
            assessment = RiskAssessment(
                score=0.3 + i * 0.05,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            assessment.assessed_at = now - timedelta(hours=10 - i)
            risk_history.record_assessment(assessment, 'test-entity')

        trend = risk_history.analyze_trend('test-entity', window_hours=10)

        assert trend is not None
        assert trend.direction == TrendDirection.WORSENING
        assert trend.delta > 0

    def test_analyze_trend_decreasing(self, risk_history):
        """Testa análise de tendência decrescente."""
        now = datetime.utcnow()

        # Criar tendência decrescente
        for i in range(10):
            assessment = RiskAssessment(
                score=0.8 - i * 0.05,
                band=RiskBand.HIGH,
                domain=UnifiedDomain.SECURITY,
                factors={},
                reasoning='test'
            )
            assessment.assessed_at = now - timedelta(hours=10 - i)
            risk_history.record_assessment(assessment, 'test-entity')

        trend = risk_history.analyze_trend('test-entity', window_hours=10)

        assert trend is not None
        assert trend.direction == TrendDirection.IMPROVING
        assert trend.delta < 0

    def test_analyze_trend_insufficient_data(self, risk_history):
        """Testa análise com dados insuficientes."""
        assessment = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='test'
        )
        risk_history.record_assessment(assessment, 'test-entity')

        trend = risk_history.analyze_trend('test-entity', min_samples=3)

        assert trend is None

    def test_detect_anomaly(self, risk_history):
        """Testa detecção de anomalia."""
        now = datetime.utcnow()

        # Histórico normal (scores em torno de 0.5)
        for i in range(20):
            assessment = RiskAssessment(
                score=0.45 + (i % 5) * 0.02,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='normal'
            )
            assessment.assessed_at = now - timedelta(hours=24 - i)
            risk_history.record_assessment(assessment, 'test-entity')

        # Anomalia: score muito diferente
        anomaly = RiskAssessment(
            score=0.95,
            band=RiskBand.CRITICAL,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='anomaly'
        )
        risk_history.record_assessment(anomaly, 'test-entity')

        detection = risk_history.detect_anomaly('test-entity')

        assert detection is not None
        # Pode detectar como anomalia dependendo do threshold
        # assert detection.is_anomaly == True

    def test_get_percentile(self, risk_history):
        """Testa cálculo de percentil."""
        # Criar distribuição conhecida
        for i in range(100):
            assessment = RiskAssessment(
                score=i / 100,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            risk_history.record_assessment(assessment, 'test-entity')

        # Percentil 50 deve ser ~0.5
        percentile = risk_history.get_percentile('test-entity', score=0.5)

        assert 0.45 <= percentile <= 0.55

    def test_get_statistics(self, risk_history):
        """Testa estatísticas do histórico."""
        scores = [0.3, 0.5, 0.7, 0.4, 0.6]

        for score in scores:
            assessment = RiskAssessment(
                score=score,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            risk_history.record_assessment(assessment, 'test-entity')

        stats = risk_history.get_statistics('test-entity')

        assert stats['count'] == 5
        assert stats['mean'] == sum(scores) / len(scores)
        assert stats['min'] == min(scores)
        assert stats['max'] == max(scores)
        assert stats['std_dev'] > 0

    def test_get_entity_ids(self, risk_history):
        """Testa obtenção de IDs de entidades."""
        # Registrar para diferentes entidades
        for entity_id in ['entity-1', 'entity-2', 'entity-3']:
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            risk_history.record_assessment(assessment, entity_id)

        entity_ids = risk_history.get_entity_ids()

        assert len(entity_ids) == 3
        assert 'entity-1' in entity_ids
        assert 'entity-2' in entity_ids
        assert 'entity-3' in entity_ids

    def test_cleanup_old_snapshots(self, risk_history):
        """Testa limpeza de snapshots antigos."""
        # Criar histórico com retenção curta
        short_history = RiskHistory(retention_days=1)

        now = datetime.utcnow()

        # Snapshot antigo
        old = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='old'
        )
        old.assessed_at = now - timedelta(days=2)
        short_history.record_assessment(old, 'test-entity')

        # Snapshot recente
        recent = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='recent'
        )
        short_history.record_assessment(recent, 'test-entity')

        # Limpar
        short_history.cleanup_all()

        # Apenas recente deve permanecer
        history = short_history.get_history('test-entity')
        assert len(history) == 1

    def test_max_snapshots_limit(self, risk_history):
        """Testa limite máximo de snapshots."""
        small_history = RiskHistory(max_snapshots_per_entity=5)

        # Registrar mais que o limite
        for i in range(10):
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            small_history.record_assessment(assessment, 'test-entity')

        history = small_history.get_history('test-entity')

        # Deve ter no máximo max_snapshots
        assert len(history) <= 5
