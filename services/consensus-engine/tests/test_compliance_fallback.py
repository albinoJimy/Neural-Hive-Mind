import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.append(str(ROOT))

from services.compliance_fallback import ComplianceFallback  # noqa: E402


def _build_config(
    min_confidence=0.65,
    max_divergence=0.25,
    high_risk=0.7,
    critical_risk=0.9,
    require_unanimous=True
):
    return SimpleNamespace(
        min_confidence_score=min_confidence,
        max_divergence_threshold=max_divergence,
        high_risk_threshold=high_risk,
        critical_risk_threshold=critical_risk,
        require_unanimous_for_critical=require_unanimous
    )


def _opinion(
    specialist_type,
    confidence,
    model_source="ml_model",
    explain_method="shap",
    recommendation="approve"
):
    return {
        "specialist_type": specialist_type,
        "opinion": {
            "confidence_score": confidence,
            "recommendation": recommendation,
            "metadata": {"model_source": model_source},
            "explainability": {"method": explain_method},
        },
    }


def test_check_compliance_healthy_strict_thresholds():
    config = _build_config()
    compliance = ComplianceFallback(config)

    opinions = [
        _opinion("business", 0.72),
        _opinion("technical", 0.71),
        _opinion("architecture", 0.70),
    ]

    is_compliant, violations, adaptive = compliance.check_compliance(
        cognitive_plan={"original_security_level": "internal"},
        opinions=opinions,
        aggregated_confidence=0.69,  # abaixo do estrito 0.70
        aggregated_risk=0.2,
        divergence=0.14,  # abaixo do estrito 0.15
        is_unanimous=True,
    )

    assert is_compliant is False
    assert any("mínimo adaptativo" in v for v in violations)
    assert adaptive["health_status"] == "healthy"
    assert pytest.approx(adaptive["min_confidence"], 0.01) == 0.70
    assert pytest.approx(adaptive["max_divergence"], 0.01) == 0.15


def test_check_compliance_partially_degraded_uses_base_thresholds():
    config = _build_config()
    compliance = ComplianceFallback(config)

    opinions = [
        _opinion("business", 0.72),
        _opinion("technical", 0.002, model_source="heuristics"),
        _opinion("behavior", 0.68),
        _opinion("evolution", 0.002, model_source="heuristics"),
        _opinion("architecture", 0.70),
    ]

    is_compliant, violations, adaptive = compliance.check_compliance(
        cognitive_plan={"original_security_level": "internal"},
        opinions=opinions,
        aggregated_confidence=0.64,  # abaixo do base 0.65
        aggregated_risk=0.3,
        divergence=0.20,  # abaixo do base 0.25
        is_unanimous=True,
    )

    assert is_compliant is False
    assert any("ajustado" in v for v in violations)
    assert adaptive["health_status"] == "partially_degraded"
    assert adaptive["degraded_count"] == 2
    assert pytest.approx(adaptive["min_confidence"], 0.01) == 0.65
    assert pytest.approx(adaptive["max_divergence"], 0.01) == 0.25


def test_check_compliance_severely_degraded_relaxes_thresholds():
    config = _build_config()
    compliance = ComplianceFallback(config)

    opinions = [
        _opinion("business", 0.002, model_source="heuristics"),
        _opinion("technical", 0.002, model_source="heuristics"),
        _opinion("behavior", 0.60),
        _opinion("evolution", 0.002, model_source="heuristics"),
    ]

    is_compliant, violations, adaptive = compliance.check_compliance(
        cognitive_plan={"original_security_level": "internal"},
        opinions=opinions,
        aggregated_confidence=0.52,  # acima do relaxado 0.50
        aggregated_risk=0.4,
        divergence=0.30,  # abaixo do relaxado 0.35
        is_unanimous=True,
    )

    assert is_compliant is True
    assert violations == []
    assert adaptive["health_status"] == "severely_degraded"
    assert adaptive["degraded_count"] == 3
    assert pytest.approx(adaptive["min_confidence"], 0.01) == 0.50
    assert pytest.approx(adaptive["max_divergence"], 0.01) == 0.35
