"""
Testes para os serviços de explicabilidade do Explainability API.

Cobre ShapCalculator, QualityScorer e HierarchicalExplainer.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import numpy as np


@pytest.mark.asyncio
async def test_shap_calculator_init():
    """ShapCalculator deve inicializar com parametros corretos."""
    from src.services.shap_calculator import ShapCalculator

    calculator = ShapCalculator(n_background_samples=100)

    assert calculator.n_background_samples == 100


@pytest.mark.asyncio
async def test_shap_calculate_explanation():
    """Calculadora SHAP deve retornar valores de feature importance."""
    from src.services.shap_calculator import ShapCalculator

    calculator = ShapCalculator(n_background_samples=50)

    # Mock decision data com specialist_votes
    decision_data = {
        "specialist_votes": [
            {
                "specialist_id": "s1",
                "confidence": 0.9,
                "features": {"f1": 0.5, "f2": 0.3, "f3": 0.2},
            },
            {
                "specialist_id": "s2",
                "confidence": 0.8,
                "features": {"f1": 0.4, "f2": 0.4, "f3": 0.2},
            },
            {
                "specialist_id": "s3",
                "confidence": 0.7,
                "features": {"f1": 0.6, "f2": 0.3, "f3": 0.1},
            },
        ],
        "final_decision": "approve",
        "confidence": 0.85,
    }

    result = calculator.calculate_shap(decision_data=decision_data, features=["f1", "f2", "f3"])

    assert "feature_attribution" in result
    assert "method" in result
    assert result["method"] == "kernel_shap"
    assert result["num_votes"] == 3


@pytest.mark.asyncio
async def test_shap_calculate_with_background():
    """Calculadora SHAP deve usar background samples."""
    from src.services.shap_calculator import ShapCalculator

    calculator = ShapCalculator(n_background_samples=10)

    # Mock decision data para batch
    decision_data = {
        "decision_id": "test-123",
        "specialist_votes": [
            {
                "specialist_id": "s1",
                "confidence": 0.5,
                "features": {"f1": 0.3, "f2": 0.4, "f3": 0.3},
            },
        ],
        "final_decision": "approve",
        "confidence": 0.5,
    }

    result = calculator.batch_calculate_shap(
        decisions=[decision_data] * 5, features=["f1", "f2", "f3"]
    )

    assert isinstance(result, list)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_quality_scorer_init():
    """QualityScorer deve inicializar com cliente MongoDB."""
    from src.services.quality_scorer import ExplanationQualityScorer

    mock_mongo = AsyncMock()

    scorer = ExplanationQualityScorer(mongodb_client=mock_mongo)

    assert scorer.mongodb == mock_mongo


@pytest.mark.asyncio
async def test_quality_score_completeness():
    """Score de qualidade deve medir completude."""
    from src.services.quality_scorer import ExplanationQualityScorer

    mock_mongo = AsyncMock()

    scorer = ExplanationQualityScorer(mongodb_client=mock_mongo)

    explanation = {
        "decision_id": "decision-123",
        "method": "shap",
        "shap_values": [0.1, 0.2, 0.3],
        "feature_names": ["f1", "f2", "f3"],
    }

    scores = scorer.score_explanation(explanation)

    assert "completeness" in scores
    assert 0 <= scores["completeness"] <= 1


@pytest.mark.asyncio
async def test_quality_score_clarity():
    """Score de qualidade deve medir clareza."""
    from src.services.quality_scorer import ExplanationQualityScorer

    mock_mongo = AsyncMock()

    scorer = ExplanationQualityScorer(mongodb_client=mock_mongo)

    explanation = {
        "decision_id": "decision-123",
        "explanation_text": "A decisão foi baseada nos fatores X e Y",
        "reasoning": "Fator X contribuiu com 60%",
    }

    scores = scorer.score_explanation(explanation)

    assert "clarity" in scores
    assert 0 <= scores["clarity"] <= 1


@pytest.mark.asyncio
async def test_quality_score_specificity():
    """Score de qualidade deve medir especificidade."""
    from src.services.quality_scorer import ExplanationQualityScorer

    mock_mongo = AsyncMock()

    scorer = ExplanationQualityScorer(mongodb_client=mock_mongo)

    explanation = {
        "decision_id": "decision-123",
        "feature_contributions": {"feature_x": 0.6, "feature_y": 0.4},
    }

    scores = scorer.score_explanation(explanation)

    assert "specificity" in scores


@pytest.mark.asyncio
async def test_quality_overall_score():
    """Score geral deve combinar metricas parciais."""
    from src.services.quality_scorer import ExplanationQualityScorer

    mock_mongo = AsyncMock()

    scorer = ExplanationQualityScorer(mongodb_client=mock_mongo)

    explanation = {
        "decision_id": "decision-123",
        "method": "hierarchical",
        "hierarchical_weights": [0.3, 0.5, 0.2],
        "reasoning": "Detailed reasoning text",
    }

    overall_score = await scorer.get_overall_score(explanation)

    assert 0 <= overall_score <= 1


@pytest.mark.asyncio
async def test_hierarchical_explainer_init():
    """HierarchicalExplainer deve inicializar corretamente."""
    from src.services.hierarchical_explainer import HierarchicalExplainer

    explainer = HierarchicalExplainer()

    assert explainer is not None


@pytest.mark.asyncio
async def test_hierarchical_explain_decision():
    """Explicador hierarquico deve gerar explicação com pesos."""
    from src.services.hierarchical_explainer import HierarchicalExplainer

    explainer = HierarchicalExplainer()

    decision = {
        "decision_id": "decision-123",
        "specialist_votes": [
            {"specialist": "business", "vote": "approve", "seniority": "senior"},
            {"specialist": "technical", "vote": "approve", "seniority": "expert"},
            {"specialist": "architecture", "vote": "reject", "seniority": "mid_level"},
        ],
        "final_decision": "approve",
    }

    explanation = await explainer.explain_decision(decision)

    assert "decision_id" in explanation
    assert "hierarchical_weights" in explanation
    assert "seniority_impact" in explanation


@pytest.mark.asyncio
async def test_hierarchical_seniority_weights():
    """Explicação deve calcular impacto de senioridade."""
    from src.services.hierarchical_explainer import HierarchicalExplainer

    explainer = HierarchicalExplainer()

    weights = explainer.calculate_seniority_weights(
        [
            {"seniority": "expert"},
            {"seniority": "senior"},
            {"seniority": "mid_level"},
            {"seniority": "trainee"},
        ]
    )

    assert weights["expert"] > weights["senior"]
    assert weights["senior"] > weights["mid_level"]
    assert weights["mid_level"] > weights["trainee"]


@pytest.mark.asyncio
async def test_reasoning_extractor_init():
    """ReasoningExtractor deve inicializar corretamente."""
    from src.services.reasoning_extractor import ReasoningExtractor

    extractor = ReasoningExtractor()

    assert extractor is not None


@pytest.mark.asyncio
async def test_reasoning_extract_from_decision():
    """Extrair reasoning deve identificar fatores de decisão."""
    from src.services.reasoning_extractor import ReasoningExtractor

    extractor = ReasoningExtractor()

    decision = {
        "decision_id": "decision-123",
        "reasoning_factors": [
            {"factor": "low_risk", "impact": 0.3},
            {"factor": "high_confidence", "impact": 0.5},
            {"factor": "business_alignment", "impact": 0.2},
        ],
    }

    reasoning = extractor.extract(decision)

    assert "factors" in reasoning
    assert len(reasoning["factors"]) == 3


@pytest.mark.asyncio
async def test_reasoning_format_as_text():
    """Formatar reasoning como texto deve ser legivel."""
    from src.services.reasoning_extractor import ReasoningExtractor

    extractor = ReasoningExtractor()

    reasoning_data = {
        "factors": [
            {"factor": "low_risk", "impact": 0.3},
            {"factor": "high_confidence", "impact": 0.5},
        ]
    }

    text = extractor.format_as_text(reasoning_data)

    assert isinstance(text, str)
    assert "low_risk" in text or "high_confidence" in text


@pytest.mark.asyncio
async def test_counterfactual_analyzer():
    """Analisador contrafactual deve gerar cenarios alternativos."""
    from src.services.counterfactual_analyzer import CounterfactualAnalyzer

    analyzer = CounterfactualAnalyzer()

    explanation = {"feature_values": {"f1": 1.0, "f2": 2.0}, "prediction": "approve"}

    counterfactual = analyzer.generate_counterfactual(
        explanation=explanation, target_outcome="reject"
    )

    assert "original_outcome" in counterfactual
    assert "counterfactual_changes" in counterfactual


@pytest.mark.asyncio
async def test_api_extensions_init():
    """API Extensions deve inicializar com servicos."""
    from src.services.api_extensions import ExplainabilityAPIExtensions

    mock_db = AsyncMock()
    mock_shap = MagicMock()
    mock_quality = MagicMock()
    mock_reasoning = MagicMock()

    extensions = ExplainabilityAPIExtensions(
        mongodb_client=mock_db,
        shap_calculator=mock_shap,
        quality_scorer=mock_quality,
        reasoning_extractor=mock_reasoning,
    )

    assert extensions.mongodb_client == mock_db
    assert extensions.db == mock_db
    assert extensions.shap_calculator == mock_shap


@pytest.mark.asyncio
async def test_api_extensions_get_explainability():
    """API Extensions deve buscar explicação por decision_id."""
    from src.services.api_extensions import ExplainabilityAPIExtensions

    # Mock do banco de dados com estrutura correta
    mock_db = AsyncMock()
    mock_ledger = AsyncMock()
    mock_ledger.find_one = AsyncMock(
        return_value={"decision_id": "decision-123", "method": "hierarchical"}
    )
    mock_db.explainability_ledger = mock_ledger

    mock_shap = MagicMock()
    mock_quality = MagicMock()
    mock_reasoning = MagicMock()

    extensions = ExplainabilityAPIExtensions(
        mongodb_client=mock_db,
        shap_calculator=mock_shap,
        quality_scorer=mock_quality,
        reasoning_extractor=mock_reasoning,
    )

    result = await extensions.get_explainability_by_decision_id("decision-123")

    assert result["decision_id"] == "decision-123"


@pytest.mark.asyncio
async def test_api_extensions_generate_explanation():
    """API Extensions deve gerar nova explicação."""
    from src.services.api_extensions import ExplainabilityAPIExtensions

    mock_db = AsyncMock()
    mock_shap = MagicMock()
    mock_shap.calculate_shap = MagicMock(
        return_value={"feature_attribution": {"confidence": 0.5, "risk": 0.3}}
    )
    mock_quality = MagicMock()
    mock_quality.score_explanation = MagicMock(return_value={"overall": 0.85})
    mock_reasoning = MagicMock()

    extensions = ExplainabilityAPIExtensions(
        mongodb_client=mock_db,
        shap_calculator=mock_shap,
        quality_scorer=mock_quality,
        reasoning_extractor=mock_reasoning,
    )

    request = {
        "decision_id": "decision-123",
        "format": "json",
        "include_shap": True,
        "specialist_votes": [{"specialist_id": "s1", "confidence": 0.8}],
    }

    result = await extensions.generate_explanation(request)

    assert "decision_id" in result
    assert "explainability_token" in result
