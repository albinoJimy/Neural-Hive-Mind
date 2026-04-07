"""
Testes unitários para API Extensions da Explainability API.

TDD: Testes escritos antes da implementação (GAPS-04 Task 5).
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.api_extensions import ExplainabilityAPIExtensions


class TestGetExplanationByDecisionIdExtended:
    """Testes do endpoint GET /api/v1/explainability/{decision_id} estendido."""

    @pytest.fixture
    def mock_db(self):
        """Mock do MongoDB."""
        db = MagicMock()
        collection = MagicMock()
        collection.find_one = AsyncMock()
        db.explainability_ledger = collection
        return db

    @pytest.fixture
    def sample_extended_explanation(self):
        """Explicação extendida com campos hierárquicos."""
        return {
            "explainability_token": "token-123",
            "decision_id": "decision-456",
            "consensus_process": {
                "method": "hierarchical_bayesian",
                "num_specialists": 5,
                "aggregation": {"confidence": 0.85, "risk": 0.15, "divergence": 0.12},
                "seniority_distribution": {"senior": 2, "expert": 1, "mid_level": 2},
                "hierarchical_weights_enabled": True,
            },
            "specialist_opinions": [
                {
                    "specialist_type": "business",
                    "seniority_level": "senior",
                    "seniority_multiplier": 1.5,
                    "final_weight": 0.65,
                    "confidence": 0.85,
                    "risk": 0.15,
                }
            ],
            "explanation_quality": {
                "completeness": 0.92,
                "clarity": 0.88,
                "specificity": 0.75,
                "overall": 0.85,
            },
        }

    @pytest.mark.asyncio
    async def test_get_by_decision_id_includes_hierarchical_fields(
        self, mock_db, sample_extended_explanation
    ):
        """Testa que resposta inclui campos hierárquicos."""
        api = ExplainabilityAPIExtensions(mongodb_client=mock_db)

        mock_db.explainability_ledger.find_one.return_value = sample_extended_explanation

        response = await api.get_explainability_by_decision_id("decision-456")

        assert "consensus_process" in response
        assert "seniority_distribution" in response["consensus_process"]
        assert response["consensus_process"]["hierarchical_weights_enabled"] is True

    @pytest.mark.asyncio
    async def test_get_by_decision_id_includes_quality_scores(
        self, mock_db, sample_extended_explanation
    ):
        """Testa que resposta inclui scores de qualidade."""
        api = ExplainabilityAPIExtensions(mongodb_client=mock_db)

        mock_db.explainability_ledger.find_one.return_value = sample_extended_explanation

        response = await api.get_explainability_by_decision_id("decision-456")

        assert "explanation_quality" in response
        assert "overall" in response["explanation_quality"]
        assert 0 <= response["explanation_quality"]["overall"] <= 1

    @pytest.mark.asyncio
    async def test_get_by_decision_id_shap_values_present(
        self, mock_db, sample_extended_explanation
    ):
        """Testa que resposta inclui valores SHAP quando disponíveis."""
        explanation_with_shap = sample_extended_explanation.copy()
        explanation_with_shap["shap_values"] = {
            "confidence": 0.45,
            "risk": -0.15,
            "seniority_multiplier": 0.08,
        }

        api = ExplainabilityAPIExtensions(mongodb_client=mock_db)

        mock_db.explainability_ledger.find_one.return_value = explanation_with_shap

        response = await api.get_explainability_by_decision_id("decision-456")

        assert "shap_values" in response
        assert "confidence" in response["shap_values"]


class TestPostGenerateExplanation:
    """Testes do endpoint POST /api/v1/explainability/generate."""

    @pytest.fixture
    def mock_services(self):
        """Mock dos serviços."""
        services = {"shap_calculator": Mock(), "quality_scorer": Mock()}
        return services

    @pytest.fixture
    def sample_generation_request(self):
        """Request de geração de explicação."""
        return {
            "decision_id": "decision-123",
            "format": "json",
            "include_shap": True,
            "include_reasoning_extraction": False,
            "include_quality_score": True,
            "specialist_votes": [{"specialist_type": "business", "confidence": 0.85, "risk": 0.15}],
        }

    @pytest.mark.asyncio
    async def test_generate_creates_new_explanation(self, mock_services, sample_generation_request):
        """Testa que generate cria nova explicação."""
        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(),
            shap_calculator=mock_services["shap_calculator"],
            quality_scorer=mock_services["quality_scorer"],
        )

        mock_services["shap_calculator"].calculate_shap.return_value = {
            "feature_attribution": {"confidence": 0.5}
        }
        mock_services["quality_scorer"].score_explanation.return_value = {"overall": 0.8}

        response = await api.generate_explanation(sample_generation_request)

        assert "explainability_token" in response
        assert "decision_id" in response
        assert response["decision_id"] == "decision-123"

    @pytest.mark.asyncio
    async def test_generate_respects_format_parameter(
        self, mock_services, sample_generation_request
    ):
        """Testa que generate respeita parâmetro de formato."""
        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(),
            shap_calculator=mock_services["shap_calculator"],
            quality_scorer=mock_services["quality_scorer"],
        )

        # Setup mock return values
        mock_services["shap_calculator"].calculate_shap.return_value = {
            "feature_attribution": {"confidence": 0.5}
        }
        mock_services["quality_scorer"].score_explanation.return_value = {"overall": 0.8}

        sample_generation_request["format"] = "json"
        response = await api.generate_explanation(sample_generation_request)

        assert "format" in response
        assert response["format"] == "json"

    @pytest.mark.asyncio
    async def test_generate_with_text_format(self, mock_services, sample_generation_request):
        """Testa geração em formato texto."""
        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(),
            shap_calculator=mock_services["shap_calculator"],
            quality_scorer=mock_services["quality_scorer"],
        )

        # Setup mock return values
        mock_services["shap_calculator"].calculate_shap.return_value = {
            "feature_attribution": {"confidence": 0.5}
        }
        mock_services["quality_scorer"].score_explanation.return_value = {"overall": 0.8}

        sample_generation_request["format"] = "text"

        response = await api.generate_explanation(sample_generation_request)

        assert "format" in response
        assert response["format"] == "text"
        assert "narrative" in response

    @pytest.mark.asyncio
    async def test_generate_with_html_format(self, mock_services, sample_generation_request):
        """Testa geração em formato HTML."""
        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(),
            shap_calculator=mock_services["shap_calculator"],
            quality_scorer=mock_services["quality_scorer"],
        )

        # Setup mock return values
        mock_services["shap_calculator"].calculate_shap.return_value = {
            "feature_attribution": {"confidence": 0.5}
        }
        mock_services["quality_scorer"].score_explanation.return_value = {"overall": 0.8}

        sample_generation_request["format"] = "html"

        response = await api.generate_explanation(sample_generation_request)

        assert "format" in response
        assert response["format"] == "html"
        assert "html" in response


class TestMultiFormatSupport:
    """Testes de suporte a múltiplos formatos."""

    @pytest.fixture
    def sample_explanation_data(self):
        """Dados de explicação para formatação."""
        return {
            "decision_id": "dec-123",
            "final_decision": {"decision": "approve"},
            "aggregated_confidence": 0.85,
            "specialist_opinions": [
                {
                    "specialist_type": "business",
                    "seniority_level": "senior",
                    "confidence": 0.85,
                    "reasoning": "Bom alinhamento com objetivos",
                }
            ],
            "shap_values": {"confidence": 0.45, "risk": -0.15},
            "explanation_quality": {"overall": 0.85},
        }

    def test_format_as_json_returns_dict(self, sample_explanation_data):
        """Testa formatação como JSON retorna dicionário."""
        api = ExplainabilityAPIExtensions(mongodb_client=MagicMock())

        result = api.format_explanation(sample_explanation_data, "json")

        assert isinstance(result, dict)
        assert "decision_id" in result

    def test_format_as_text_returns_string(self, sample_explanation_data):
        """Testa formatação como texto retorna string."""
        api = ExplainabilityAPIExtensions(mongodb_client=MagicMock())

        result = api.format_explanation(sample_explanation_data, "text")

        assert isinstance(result, dict)
        assert result["format"] == "text"
        assert "narrative" in result
        narrative = result["narrative"]
        assert any(term in narrative.lower() for term in ["decisão", "aprovado", "confiança"])

    def test_format_as_html_returns_html_string(self, sample_explanation_data):
        """Testa formatação como HTML retorna string HTML."""
        api = ExplainabilityAPIExtensions(mongodb_client=MagicMock())

        result = api.format_explanation(sample_explanation_data, "html")

        assert isinstance(result, dict)
        assert result["format"] == "html"
        assert "html" in result
        html_content = result["html"]
        assert "<html" in html_content or "<div" in html_content or "<p>" in html_content

    def test_format_with_invalid_format_defaults_to_json(self, sample_explanation_data):
        """Testa que formato inválido usa JSON como padrão."""
        api = ExplainabilityAPIExtensions(mongodb_client=MagicMock())

        result = api.format_explanation(sample_explanation_data, "invalid")

        assert isinstance(result, dict)


class TestShapIntegration:
    """Testes de integração SHAP na API."""

    @pytest.fixture
    def mock_shap_calculator(self):
        """Mock do ShapCalculator."""
        shap = Mock()
        shap.calculate_shap.return_value = {
            "feature_attribution": {"confidence": 0.50, "risk": -0.20},
            "base_value": 0.0,
            "method": "kernel_shap",
        }
        return shap

    @pytest.mark.asyncio
    async def test_shap_calculator_called_on_generate(self, mock_shap_calculator):
        """Testa que ShapCalculator é chamado na geração."""
        request = {
            "decision_id": "dec-123",
            "include_shap": True,
            "specialist_votes": [{"specialist_type": "business", "confidence": 0.85, "risk": 0.15}],
        }

        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(), shap_calculator=mock_shap_calculator
        )

        response = await api.generate_explanation(request)

        mock_shap_calculator.calculate_shap.assert_called_once()
        assert "shap_values" in response

    @pytest.mark.asyncio
    async def test_shap_skipped_when_flag_false(self, mock_shap_calculator):
        """Testa que SHAP não é calculado quando flag é False."""
        request = {"decision_id": "dec-123", "include_shap": False, "specialist_votes": []}

        api = ExplainabilityAPIExtensions(
            mongodb_client=MagicMock(), shap_calculator=mock_shap_calculator
        )

        await api.generate_explanation(request)

        mock_shap_calculator.calculate_shap.assert_not_called()
