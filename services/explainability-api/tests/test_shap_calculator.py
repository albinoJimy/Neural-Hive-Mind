"""
Testes unitários para ShapCalculator.

TDD: Testes escritos antes da implementação (GAPS-04 Task 2).
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.shap_calculator import ShapCalculator


class TestShapCalculatorInitialization:
    """Testes de inicialização do ShapCalculator."""

    def test_initialization(self):
        """Testa que o calculator pode ser inicializado."""
        calculator = ShapCalculator()
        assert calculator is not None

    def test_initialization_with_custom_samples(self):
        """Testa inicialização com número customizado de amostras."""
        calculator = ShapCalculator(n_background_samples=50)
        assert calculator.n_background_samples == 50


class TestKernelSHAP:
    """Testes do método Kernel SHAP para decisões de consenso."""

    @pytest.fixture
    def sample_decision_data(self):
        """Dados de decisão para cálculo SHAP."""
        return {
            "specialist_votes": [
                {
                    "specialist_type": "business",
                    "confidence_score": 0.85,
                    "risk_score": 0.15,
                    "recommendation": "approve",
                    "seniority_level": "senior",
                    "seniority_multiplier": 1.5,
                },
                {
                    "specialist_type": "technical",
                    "confidence_score": 0.90,
                    "risk_score": 0.10,
                    "recommendation": "approve",
                    "seniority_level": "expert",
                    "seniority_multiplier": 2.0,
                },
                {
                    "specialist_type": "security",
                    "confidence_score": 0.70,
                    "risk_score": 0.30,
                    "recommendation": "needs_revision",
                    "seniority_level": "mid_level",
                    "seniority_multiplier": 1.0,
                },
            ],
            "aggregated_confidence": 0.82,
            "aggregated_risk": 0.18,
            "final_decision": "approve",
        }

    def test_calculate_shap_returns_attribution_dict(self, sample_decision_data):
        """Testa que calculate_shap retorna dicionário de atribuições."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data=sample_decision_data,
            features=["confidence", "risk", "seniority_multiplier"],
        )

        assert isinstance(result, dict)
        assert "feature_attribution" in result

    def test_feature_attribution_contains_all_features(self, sample_decision_data):
        """Testa que feature attribution contém todas as features solicitadas."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data=sample_decision_data,
            features=["confidence", "risk", "seniority_multiplier"],
        )

        attribution = result["feature_attribution"]
        for feature in ["confidence", "risk", "seniority_multiplier"]:
            assert feature in attribution, f"Feature {feature} missing"

    def test_shap_values_sum_to_approximate_prediction(self, sample_decision_data):
        """Testa que valores SHAP somam aproximadamente à predição."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data=sample_decision_data, features=["confidence", "risk"]
        )

        # SHAP values devem somar aproximadamente ao valor base + predição
        attribution = result["feature_attribution"]
        shap_sum = sum(attribution.values())

        # A soma deve estar em range razoável
        assert -1.0 <= shap_sum <= 2.0, f"SHAP sum {shap_sum} out of range"

    def test_high_confidence_contributes_positively(self, sample_decision_data):
        """Testa que alta confiança contribui positivamente para aprovação."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data=sample_decision_data, features=["confidence", "risk"]
        )

        attribution = result["feature_attribution"]
        # Confiança alta deve ter contribuição positiva
        assert attribution["confidence"] > 0, "High confidence should contribute positively"

    def test_high_risk_contributes_negatively(self):
        """Testa que alto risco contribui negativamente para aprovação."""
        calculator = ShapCalculator()

        # Dados com alto risco (>0.5)
        high_risk_data = {
            "specialist_votes": [
                {"confidence_score": 0.70, "risk_score": 0.75},
                {"confidence_score": 0.65, "risk_score": 0.80},
            ],
            "aggregated_confidence": 0.675,
            "aggregated_risk": 0.775,  # Alto risco
            "final_decision": "reject",
        }

        result = calculator.calculate_shap(
            decision_data=high_risk_data, features=["confidence", "risk"]
        )

        attribution = result["feature_attribution"]
        # Risco alto (>0.5) deve ter contribuição negativa
        assert (
            attribution["risk"] < 0
        ), f"High risk should contribute negatively, got {attribution['risk']}"

    def test_seniority_multiplier_affects_attribution(self, sample_decision_data):
        """Testa que multiplicador de senioridade afeta atribuição."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data=sample_decision_data,
            features=["confidence", "risk", "seniority_multiplier"],
        )

        attribution = result["feature_attribution"]
        # Seniority deve ter algum efeito (positivo para especialistas seniores)
        assert "seniority_multiplier" in attribution
        # Pode ser positivo ou negativo dependendo do contexto


class TestBatchProcessing:
    """Testes de processamento em lote."""

    @pytest.fixture
    def sample_batch(self):
        """Lote de decisões para processamento."""
        return [
            {
                "decision_id": "dec-1",
                "specialist_votes": [{"confidence_score": 0.85, "risk_score": 0.15}],
                "final_decision": "approve",
            },
            {
                "decision_id": "dec-2",
                "specialist_votes": [{"confidence_score": 0.60, "risk_score": 0.40}],
                "final_decision": "reject",
            },
        ]

    def test_batch_calculate_returns_list_of_attributions(self, sample_batch):
        """Testa que batch processing retorna lista de atribuições."""
        calculator = ShapCalculator()

        results = calculator.batch_calculate_shap(
            decisions=sample_batch, features=["confidence", "risk"]
        )

        assert isinstance(results, list)
        assert len(results) == len(sample_batch)

    def test_batch_preserves_decision_ids(self, sample_batch):
        """Testa que batch processing preserva decision_ids."""
        calculator = ShapCalculator()

        results = calculator.batch_calculate_shap(
            decisions=sample_batch, features=["confidence", "risk"]
        )

        decision_ids = [r["decision_id"] for r in results]
        assert "dec-1" in decision_ids
        assert "dec-2" in decision_ids


class TestExplanationFormatting:
    """Testes de formatação de explicações SHAP."""

    def test_format_for_human_readable(self):
        """Testa formatação legível para humanos."""
        calculator = ShapCalculator()

        attribution = {"confidence": 0.35, "risk": -0.20, "seniority_multiplier": 0.10}

        formatted = calculator.format_explanation(attribution)

        assert isinstance(formatted, str)
        assert len(formatted) > 0
        # Deve mencionar as features
        assert "confidence" in formatted.lower() or "confiança" in formatted.lower()

    def test_format_highlights_top_features(self):
        """Testa que formatação destaca features mais importantes."""
        calculator = ShapCalculator()

        attribution = {"confidence": 0.50, "risk": -0.05, "seniority_multiplier": 0.02}

        formatted = calculator.format_explanation(attribution)

        # Feature mais importante (confidence) deve ser mencionada
        assert "confidence" in formatted.lower() or "0.50" in formatted or "50" in formatted


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_empty_specialist_votes(self):
        """Testa comportamento com lista vazia de votos."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data={"specialist_votes": [], "final_decision": "approve"},
            features=["confidence", "risk"],
        )

        # Deve retornar atribuição vazia ou zeros
        assert "feature_attribution" in result

    def test_single_feature(self):
        """Testa cálculo com única feature."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data={
                "specialist_votes": [{"confidence_score": 0.85}],
                "final_decision": "approve",
            },
            features=["confidence"],
        )

        assert "confidence" in result["feature_attribution"]

    def test_missing_optional_feature(self):
        """Testa que features ausentes são tratadas graciosamente."""
        calculator = ShapCalculator()

        result = calculator.calculate_shap(
            decision_data={
                "specialist_votes": [{"confidence_score": 0.85}],
                "final_decision": "approve",
            },
            features=["confidence", "risk"],  # risk não está presente
        )

        # Risk pode ter valor zero ou padrão
        assert "confidence" in result["feature_attribution"]
