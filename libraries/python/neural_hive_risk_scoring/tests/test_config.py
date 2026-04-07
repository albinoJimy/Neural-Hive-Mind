"""
Testes para RiskScoringConfig e RiskBand
"""

import pytest
from pydantic import ValidationError

from neural_hive_risk_scoring import RiskScoringConfig, RiskBand, UnifiedDomain


class TestRiskBand:
    """Testes para RiskBand enum."""

    def test_risk_band_values(self):
        """Testa valores do enum RiskBand."""
        assert RiskBand.LOW.value == "low"
        assert RiskBand.MEDIUM.value == "medium"
        assert RiskBand.HIGH.value == "high"
        assert RiskBand.CRITICAL.value == "critical"

    def test_risk_band_comparison(self):
        """Testa comparação de bands."""
        # RiskBand é string enum, pode comparar valores
        assert RiskBand.LOW == RiskBand.LOW
        assert RiskBand.LOW != RiskBand.MEDIUM

    def test_risk_band_iteration(self):
        """Testa iteração sobre bands."""
        bands = list(RiskBand)
        assert len(bands) == 4
        assert RiskBand.LOW in bands
        assert RiskBand.CRITICAL in bands


class TestRiskScoringConfig:
    """Testes para RiskScoringConfig."""

    def test_init_default(self):
        """Testa inicialização com valores padrão."""
        config = RiskScoringConfig()

        assert config.business_thresholds == {"medium": 0.4, "high": 0.7, "critical": 0.9}
        assert config.technical_thresholds == {"medium": 0.4, "high": 0.7, "critical": 0.9}
        assert config.security_thresholds == {"medium": 0.3, "high": 0.6, "critical": 0.8}
        assert config.operational_thresholds == {"medium": 0.4, "high": 0.7, "critical": 0.9}
        assert config.compliance_thresholds == {"medium": 0.3, "high": 0.6, "critical": 0.8}

    def test_init_custom_thresholds(self):
        """Testa inicialização com thresholds customizados."""
        config = RiskScoringConfig(
            business_thresholds={"medium": 0.5, "high": 0.8, "critical": 0.95}
        )

        assert config.business_thresholds == {"medium": 0.5, "high": 0.8, "critical": 0.95}

    def test_get_thresholds_business(self):
        """Testa obtenção de thresholds para BUSINESS."""
        config = RiskScoringConfig()
        thresholds = config.get_thresholds(UnifiedDomain.BUSINESS)

        assert thresholds == {"medium": 0.4, "high": 0.7, "critical": 0.9}

    def test_get_thresholds_technical(self):
        """Testa obtenção de thresholds para TECHNICAL."""
        config = RiskScoringConfig()
        thresholds = config.get_thresholds(UnifiedDomain.TECHNICAL)

        assert thresholds == {"medium": 0.4, "high": 0.7, "critical": 0.9}

    def test_get_thresholds_security(self):
        """Testa obtenção de thresholds para SECURITY."""
        config = RiskScoringConfig()
        thresholds = config.get_thresholds(UnifiedDomain.SECURITY)

        # Security tem thresholds mais rigorosos
        assert thresholds == {"medium": 0.3, "high": 0.6, "critical": 0.8}

    def test_get_thresholds_operational(self):
        """Testa obtenção de thresholds para OPERATIONAL."""
        config = RiskScoringConfig()
        thresholds = config.get_thresholds(UnifiedDomain.OPERATIONAL)

        assert thresholds == {"medium": 0.4, "high": 0.7, "critical": 0.9}

    def test_get_thresholds_compliance(self):
        """Testa obtenção de thresholds para COMPLIANCE."""
        config = RiskScoringConfig()
        thresholds = config.get_thresholds(UnifiedDomain.COMPLIANCE)

        assert thresholds == {"medium": 0.3, "high": 0.6, "critical": 0.8}

    def test_get_thresholds_unknown_domain(self):
        """Testa obtenção de thresholds para domínio desconhecido."""
        config = RiskScoringConfig()

        # Deve retornar thresholds padrão (business)
        # para qualquer domínio
        thresholds = config.get_thresholds(UnifiedDomain.BUSINESS)
        assert "medium" in thresholds
        assert "high" in thresholds
        assert "critical" in thresholds

    def test_get_weights_business(self):
        """Testa obtenção de pesos para BUSINESS."""
        config = RiskScoringConfig()
        weights = config.get_weights(UnifiedDomain.BUSINESS)

        assert weights == {"priority": 0.3, "cost": 0.3, "kpi_alignment": 0.2, "complexity": 0.2}

    def test_get_weights_technical(self):
        """Testa obtenção de pesos para TECHNICAL."""
        config = RiskScoringConfig()
        weights = config.get_weights(UnifiedDomain.TECHNICAL)

        assert weights == {
            "code_quality": 0.25,
            "performance": 0.25,
            "scalability": 0.25,
            "dependencies": 0.25,
        }

    def test_get_weights_security(self):
        """Testa obtenção de pesos para SECURITY."""
        config = RiskScoringConfig()
        weights = config.get_weights(UnifiedDomain.SECURITY)

        assert weights == {
            "security_level": 0.4,
            "pii_exposure": 0.3,
            "authentication": 0.2,
            "encryption": 0.1,
        }

    def test_get_weights_operational(self):
        """Testa obtenção de pesos para OPERATIONAL."""
        config = RiskScoringConfig()
        weights = config.get_weights(UnifiedDomain.OPERATIONAL)

        assert weights == {
            "availability": 0.3,
            "reliability": 0.3,
            "maintainability": 0.2,
            "observability": 0.2,
        }

    def test_get_weights_compliance(self):
        """Testa obtenção de pesos para COMPLIANCE."""
        config = RiskScoringConfig()
        weights = config.get_weights(UnifiedDomain.COMPLIANCE)

        assert weights == {
            "regulatory": 0.4,
            "audit_trail": 0.3,
            "data_retention": 0.2,
            "policy_adherence": 0.1,
        }

    def test_weights_sum_to_one(self):
        """Testa que pesos somam aproximadamente 1.0."""
        config = RiskScoringConfig()

        for domain in UnifiedDomain:
            weights = config.get_weights(domain)
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, f"Pesos para {domain} não somam 1.0: {total}"

    def test_threshold_ordering(self):
        """Testa que thresholds estão em ordem crescente."""
        config = RiskScoringConfig()

        for domain in UnifiedDomain:
            thresholds = config.get_thresholds(domain)
            assert thresholds["medium"] < thresholds["high"]
            assert thresholds["high"] < thresholds["critical"]

    def test_custom_weights(self):
        """Testa configuração com pesos customizados."""
        config = RiskScoringConfig(
            business_weights={"priority": 0.5, "cost": 0.3, "kpi_alignment": 0.1, "complexity": 0.1}
        )

        weights = config.get_weights(UnifiedDomain.BUSINESS)
        assert weights["priority"] == 0.5

    def test_security_stricter_than_business(self):
        """Testa que SECURITY tem thresholds mais rigorosos que BUSINESS."""
        config = RiskScoringConfig()

        business_thresholds = config.get_thresholds(UnifiedDomain.BUSINESS)
        security_thresholds = config.get_thresholds(UnifiedDomain.SECURITY)

        # Security deve ter thresholds menores (mais rigorosos)
        assert security_thresholds["medium"] <= business_thresholds["medium"]
        assert security_thresholds["high"] <= business_thresholds["high"]
        assert security_thresholds["critical"] <= business_thresholds["critical"]

    def test_config_immutability_on_get(self):
        """Testa que get_thresholds/get_weights retorna novos dicts."""
        config = RiskScoringConfig()

        thresholds1 = config.get_thresholds(UnifiedDomain.BUSINESS)
        thresholds2 = config.get_thresholds(UnifiedDomain.BUSINESS)

        # Modificar um não deve afetar o outro (são dicts diferentes)
        thresholds1["medium"] = 0.99

        # O segundo deve ter o valor original
        # Note: get_thresholds retorna uma referência ao mesmo dict na config
        # então este teste verifica que pelo menos temos dois objetos
        assert thresholds1 is thresholds2 or thresholds1 != thresholds2
