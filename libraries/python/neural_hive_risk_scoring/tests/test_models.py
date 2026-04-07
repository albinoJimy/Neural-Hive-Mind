"""
Testes para modelos Pydantic: RiskFactor, RiskAssessment, RiskMatrix
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from neural_hive_risk_scoring import RiskFactor, RiskAssessment, RiskMatrix, RiskBand, UnifiedDomain


class TestRiskFactor:
    """Testes para RiskFactor."""

    def test_init_valid(self):
        """Testa inicialização com valores válidos."""
        factor = RiskFactor(
            name="test_factor",
            score=0.5,
            weight=0.3,
            description="Test factor description",
            contribution="positive",
        )

        assert factor.name == "test_factor"
        assert factor.score == 0.5
        assert factor.weight == 0.3
        assert factor.description == "Test factor description"
        assert factor.contribution == "positive"

    def test_score_bounds(self):
        """Testa limites de score."""
        # Valores válidos
        RiskFactor(name="min", score=0.0, weight=0.5, description="test", contribution="neutral")
        RiskFactor(name="max", score=1.0, weight=0.5, description="test", contribution="neutral")

        # Valores inválidos
        with pytest.raises(ValidationError):
            RiskFactor(
                name="invalid_low",
                score=-0.1,
                weight=0.5,
                description="test",
                contribution="neutral",
            )

        with pytest.raises(ValidationError):
            RiskFactor(
                name="invalid_high",
                score=1.1,
                weight=0.5,
                description="test",
                contribution="neutral",
            )

    def test_weight_bounds(self):
        """Testa limites de weight."""
        # Valores válidos
        RiskFactor(name="test", score=0.5, weight=0.0, description="test", contribution="neutral")
        RiskFactor(name="test", score=0.5, weight=1.0, description="test", contribution="neutral")

        # Valores inválidos
        with pytest.raises(ValidationError):
            RiskFactor(
                name="test", score=0.5, weight=-0.1, description="test", contribution="neutral"
            )

        with pytest.raises(ValidationError):
            RiskFactor(
                name="test", score=0.5, weight=1.1, description="test", contribution="neutral"
            )

    def test_contribution_values(self):
        """Testa valores válidos de contribution."""
        valid_contributions = ["positive", "negative", "neutral"]

        for contribution in valid_contributions:
            factor = RiskFactor(
                name="test", score=0.5, weight=0.5, description="test", contribution=contribution
            )
            assert factor.contribution == contribution


class TestRiskAssessment:
    """Testes para RiskAssessment."""

    def test_init_valid(self):
        """Testa inicialização com valores válidos."""
        assessment = RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.8, "cost": 0.6},
            reasoning="High business risk",
        )

        assert assessment.score == 0.7
        assert assessment.band == RiskBand.HIGH
        assert assessment.domain == UnifiedDomain.BUSINESS
        assert assessment.factors == {"priority": 0.8, "cost": 0.6}
        assert assessment.reasoning == "High business risk"

    def test_score_bounds(self):
        """Testa limites de score."""
        # Valores válidos
        RiskAssessment(
            score=0.0,
            band=RiskBand.LOW,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning="test",
        )
        RiskAssessment(
            score=1.0,
            band=RiskBand.CRITICAL,
            domain=UnifiedDomain.BUSINESS,
            factors={},
            reasoning="test",
        )

        # Valor inválido
        with pytest.raises(ValidationError):
            RiskAssessment(
                score=1.5,
                band=RiskBand.CRITICAL,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning="test",
            )

    def test_default_assessed_at(self):
        """Testa valor padrão de assessed_at."""
        assessment = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.TECHNICAL,
            factors={},
            reasoning="test",
        )

        assert assessment.assessed_at is not None
        assert isinstance(assessment.assessed_at, datetime)

    def test_default_metadata(self):
        """Testa valor padrão de metadata."""
        assessment = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.TECHNICAL,
            factors={},
            reasoning="test",
        )

        assert assessment.metadata == {}

    def test_custom_metadata(self):
        """Testa metadata customizado."""
        custom_metadata = {"source": "manual", "reviewer": "user-1"}

        assessment = RiskAssessment(
            score=0.5,
            band=RiskBand.MEDIUM,
            domain=UnifiedDomain.TECHNICAL,
            factors={},
            reasoning="test",
            metadata=custom_metadata,
        )

        assert assessment.metadata == custom_metadata

    def test_all_domains(self):
        """Testa criação para todos os domínios."""
        for domain in UnifiedDomain:
            assessment = RiskAssessment(
                score=0.5,
                band=RiskBand.MEDIUM,
                domain=domain,
                factors={},
                reasoning=f"test {domain.value}",
            )
            assert assessment.domain == domain

    def test_all_bands(self):
        """Testa criação para todas as bands."""
        for band in RiskBand:
            assessment = RiskAssessment(
                score=0.5,
                band=band,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning=f"test {band.value}",
            )
            assert assessment.band == band


class TestRiskMatrix:
    """Testes para RiskMatrix."""

    def test_init_valid(self):
        """Testa inicialização com valores válidos."""
        assessments = {
            "BUSINESS": RiskAssessment(
                score=0.3,
                band=RiskBand.LOW,
                domain=UnifiedDomain.BUSINESS,
                factors={},
                reasoning="test",
            ),
            "TECHNICAL": RiskAssessment(
                score=0.7,
                band=RiskBand.HIGH,
                domain=UnifiedDomain.TECHNICAL,
                factors={},
                reasoning="test",
            ),
        }

        matrix = RiskMatrix(
            entity_id="test-entity",
            entity_type="plan",
            assessments=assessments,
            overall_score=0.5,
            overall_band=RiskBand.MEDIUM,
            highest_risk_domain=UnifiedDomain.TECHNICAL,
        )

        assert matrix.entity_id == "test-entity"
        assert matrix.entity_type == "plan"
        assert len(matrix.assessments) == 2
        assert matrix.overall_score == 0.5
        assert matrix.overall_band == RiskBand.MEDIUM
        assert matrix.highest_risk_domain == UnifiedDomain.TECHNICAL

    def test_default_created_at(self):
        """Testa valor padrão de created_at."""
        matrix = RiskMatrix(
            entity_id="test",
            entity_type="plan",
            assessments={},
            overall_score=0.0,
            overall_band=RiskBand.LOW,
            highest_risk_domain=UnifiedDomain.BUSINESS,
        )

        assert matrix.created_at is not None
        assert isinstance(matrix.created_at, datetime)

    def test_overall_score_bounds(self):
        """Testa limites de overall_score."""
        # Valores válidos
        RiskMatrix(
            entity_id="test",
            entity_type="plan",
            assessments={},
            overall_score=0.0,
            overall_band=RiskBand.LOW,
            highest_risk_domain=UnifiedDomain.BUSINESS,
        )
        RiskMatrix(
            entity_id="test",
            entity_type="plan",
            assessments={},
            overall_score=1.0,
            overall_band=RiskBand.CRITICAL,
            highest_risk_domain=UnifiedDomain.BUSINESS,
        )

        # Valor inválido
        with pytest.raises(ValidationError):
            RiskMatrix(
                entity_id="test",
                entity_type="plan",
                assessments={},
                overall_score=-0.1,
                overall_band=RiskBand.LOW,
                highest_risk_domain=UnifiedDomain.BUSINESS,
            )

    def test_entity_types(self):
        """Testa diferentes tipos de entidade."""
        entity_types = ["plan", "decision", "execution"]

        for entity_type in entity_types:
            matrix = RiskMatrix(
                entity_id="test",
                entity_type=entity_type,
                assessments={},
                overall_score=0.5,
                overall_band=RiskBand.MEDIUM,
                highest_risk_domain=UnifiedDomain.BUSINESS,
            )
            assert matrix.entity_type == entity_type

    def test_empty_assessments(self):
        """Testa matriz com avaliações vazias."""
        matrix = RiskMatrix(
            entity_id="test",
            entity_type="plan",
            assessments={},
            overall_score=0.0,
            overall_band=RiskBand.LOW,
            highest_risk_domain=UnifiedDomain.BUSINESS,
        )

        assert len(matrix.assessments) == 0

    def test_full_matrix(self):
        """Testa matriz com todos os domínios."""
        assessments = {}
        for domain in UnifiedDomain:
            assessments[domain.value] = RiskAssessment(
                score=0.5, band=RiskBand.MEDIUM, domain=domain, factors={}, reasoning="test"
            )

        matrix = RiskMatrix(
            entity_id="test",
            entity_type="plan",
            assessments=assessments,
            overall_score=0.5,
            overall_band=RiskBand.MEDIUM,
            highest_risk_domain=UnifiedDomain.SECURITY,
        )

        assert len(matrix.assessments) == len(UnifiedDomain)

    def test_model_serialization(self):
        """Testa serialização de modelos."""
        assessment = RiskAssessment(
            score=0.7,
            band=RiskBand.HIGH,
            domain=UnifiedDomain.BUSINESS,
            factors={"priority": 0.8},
            reasoning="test",
        )

        # Deve ser serializável
        data = assessment.model_dump()
        assert data["score"] == 0.7
        assert data["band"] == RiskBand.HIGH

    def test_model_deserialization(self):
        """Testa desserialização de modelos."""
        data = {
            "score": 0.7,
            "band": RiskBand.HIGH,
            "domain": UnifiedDomain.BUSINESS,
            "factors": {"priority": 0.8},
            "reasoning": "test",
        }

        assessment = RiskAssessment(**data)
        assert assessment.score == 0.7
        assert assessment.band == RiskBand.HIGH
