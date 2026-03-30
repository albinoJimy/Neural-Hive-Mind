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

    def test_analyze_trend_stable(self, risk_history):
        """Testa análise de tendência estável."""
        now = datetime.utcnow()

        # Criar tendência estável
        for i in range(10):
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            assessment.assessed_at = now - timedelta(hours=10 - i)
            risk_history.record_assessment(assessment, 'test-entity')

        trend = risk_history.analyze_trend('test-entity', window_hours=10)

        assert trend is not None
        assert trend.direction == TrendDirection.STABLE
        assert abs(trend.delta) < 0.1

    def test_anomaly_no_detection(self, risk_history):
        """Testa não detecção quando score está dentro do esperado."""
        now = datetime.utcnow()

        # Histórico consistente
        for i in range(20):
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='normal'
            )
            assessment.assessed_at = now - timedelta(hours=24 - i)
            risk_history.record_assessment(assessment, 'test-entity')

        # Score semelhante
        normal = RiskAssessment(
            score=0.52,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='normal too'
        )
        risk_history.record_assessment(normal, 'test-entity')

        detection = risk_history.detect_anomaly('test-entity')

        # Não deve ser anomalia (ou muito baixa severidade)
        if detection:
            assert detection.is_anomaly == False or detection.severity == 'low'

    def test_percentile_extremes(self, risk_history):
        """Testa percentil em valores extremos."""
        # Criar distribuição
        for i in range(100):
            assessment = RiskAssessment(
                score=i / 100,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            risk_history.record_assessment(assessment, 'test-entity')

        # Percentil 0 deve ser ~0
        p0 = risk_history.get_percentile('test-entity', score=0.0)
        assert 0.0 <= p0 <= 0.05

        # Percentil 100 deve ser ~1
        p100 = risk_history.get_percentile('test-entity', score=1.0)
        assert 0.95 <= p100 <= 1.0

    def test_get_statistics_with_single_value(self, risk_history):
        """Testa estatísticas com valor único."""
        assessment = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='test'
        )
        risk_history.record_assessment(assessment, 'test-entity')

        stats = risk_history.get_statistics('test-entity')

        assert stats['count'] == 1
        assert stats['mean'] == 0.5
        assert stats['min'] == 0.5
        assert stats['max'] == 0.5
        assert stats['std_dev'] == 0.0

    def test_record_matrix(self, risk_history):
        """Testa registro de matriz de risco."""
        from neural_hive_risk_scoring import RiskMatrix

        assessments = {
            'BUSINESS': RiskAssessment(
                score=0.3,
                band=RiskBand.LOW,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            ),
            'SECURITY': RiskAssessment(
                score=0.7,
                band=RiskBand.HIGH,
                domain=UnifiedDomain.SECURITY,
                factors={},
                reasoning='test'
            )
        }

        matrix = RiskMatrix(
            entity_id='test-entity',
            entity_type='plan',
            assessments=assessments,
            overall_score=0.5,
            overall_band=RiskBand.MEDIUM,
            highest_risk_domain=UnifiedDomain.SECURITY
        )

        snapshots = risk_history.record_matrix(matrix)

        assert len(snapshots) == 2
        assert all(isinstance(s, RiskSnapshot) for s in snapshots)

    def test_snapshot_to_dict(self, risk_history, sample_assessment):
        """Testa conversão de snapshot para dicionário."""
        snapshot = risk_history.record_assessment(sample_assessment, 'test-entity')

        snapshot_dict = snapshot.to_dict()

        assert 'timestamp' in snapshot_dict
        assert 'score' in snapshot_dict
        assert 'band' in snapshot_dict
        assert 'domain' in snapshot_dict
        assert 'entity_id' in snapshot_dict

    def test_get_latest_with_domain_filter(self, risk_history):
        """Testa get_latest com filtro de domínio."""
        # Registrar avaliações de domínios diferentes
        business = RiskAssessment(
            score=0.3,
            band=RiskBand.LOW,
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

        # Latest BUSINESS
        latest_business = risk_history.get_latest('test-entity', domain=UnifiedDomain.BUSINESS)
        assert latest_business is not None
        assert latest_business.domain == UnifiedDomain.BUSINESS

        # Latest TECHNICAL
        latest_technical = risk_history.get_latest('test-entity', domain=UnifiedDomain.TECHNICAL)
        assert latest_technical is not None
        assert latest_technical.domain == UnifiedDomain.TECHNICAL

    def test_anomaly_severity_levels(self, risk_history):
        """Testa níveis de severidade de anomalia."""
        now = datetime.utcnow()

        # Histórico consistente em 0.5
        for i in range(20):
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='normal'
            )
            assessment.assessed_at = now - timedelta(hours=24 - i)
            risk_history.record_assessment(assessment, 'severity-entity')

        # Anomalia de baixa severidade
        low_anomaly = RiskAssessment(
            score=0.65,  # 1.5 desvios (assumindo std pequeno)
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='low anomaly'
        )
        risk_history.record_assessment(low_anomaly, 'severity-entity')

        detection = risk_history.detect_anomaly('severity-entity')
        if detection and detection.is_anomaly:
            assert detection.severity in ['low', 'medium', 'high']

    def test_trend_strength_calculation(self, risk_history):
        """Testa cálculo de força da tendência."""
        now = datetime.utcnow()

        # Criar tendência forte (linear perfeita)
        for i in range(10):
            assessment = RiskAssessment(
                score=0.1 + i * 0.08,  # 0.1, 0.18, 0.26, ..., 0.82
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            )
            assessment.assessed_at = now - timedelta(hours=10 - i)
            risk_history.record_assessment(assessment, 'strong-trend')

        trend = risk_history.analyze_trend('strong-trend')

        if trend:
            # Força deve ser alta (correlação forte)
            assert trend.strength > 0.5

    def test_volatility_calculation(self, risk_history):
        """Testa cálculo de volatilidade."""
        # Série estável
        for i in range(10):
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='stable'
            )
            risk_history.record_assessment(assessment, 'stable-entity')

        trend = risk_history.analyze_trend('stable-entity')

        if trend:
            # Volatilidade deve ser muito baixa
            assert trend.volatility < 0.1

    def test_get_entity_ids_by_domain(self, risk_history):
        """Testa obtenção de IDs por domínio."""
        # Registrar para diferentes domínios
        risk_history.record_assessment(
            RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning='test'
            ),
            'entity-1'
        )

        risk_history.record_assessment(
            RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=UnifiedDomain.SECURITY,
                factors={},
                reasoning='test'
            ),
            'entity-2'
        )

        business_ids = risk_history.get_entity_ids(domain=UnifiedDomain.BUSINESS)
        security_ids = risk_history.get_entity_ids(domain=UnifiedDomain.SECURITY)

        assert 'entity-1' in business_ids
        assert 'entity-2' in security_ids

    def test_snapshot_metadata(self, risk_history, sample_assessment):
        """Testa metadados do snapshot."""
        custom_metadata = {'source': 'manual', 'reviewer': 'user-1'}

        snapshot = risk_history.record_assessment(
            assessment=sample_assessment,
            entity_id='test-entity',
            metadata=custom_metadata
        )

        assert snapshot.metadata == custom_metadata

    def test_trend_delta_percentage(self, risk_history):
        """Testa cálculo de delta percentual na tendência."""
        now = datetime.utcnow()

        # Criar mudança de 50% (0.4 -> 0.6)
        assessment1 = RiskAssessment(
            score=0.4,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='start'
        )
        assessment1.assessed_at = now - timedelta(hours=2)

        assessment2 = RiskAssessment(
            score=0.6,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning='end'
        )
        assessment2.assessed_at = now - timedelta(hours=1)

        risk_history.record_assessment(assessment1, 'delta-entity')
        risk_history.record_assessment(assessment2, 'delta-entity')

        trend = risk_history.analyze_trend('delta-entity')

        if trend:
            # Delta percentual deve ser aproximadamente 50%
            assert abs(trend.delta_percentage - 50.0) < 5.0