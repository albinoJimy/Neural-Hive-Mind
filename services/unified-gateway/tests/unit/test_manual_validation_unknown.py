"""
Testes para validação humana em domínio não-mapeado (Task 10.4 da spec
caminho-real-first-class).

Quando o NLU devolve domínio UNKNOWN/DOMAIN_UNKNOWN (ou sinaliza incerteza), o
gateway tem de marcar `requires_manual_validation` na decisão — não encaminhar
um plano com domínio adivinhado.
"""

from unittest.mock import AsyncMock

import pytest
from src.models.classification import ClassificationDecision, IntentClassifier, NLUResult


def _classifier_with_nlu(nlu_result: NLUResult) -> IntentClassifier:
    nlu_client = AsyncMock()
    nlu_client.parse = AsyncMock(return_value=nlu_result)
    return IntentClassifier(nlu_client=nlu_client)


def test_decision_has_manual_validation_field_default_false():
    decision = ClassificationDecision(flow_type="A-F", confidence=0.8, reasoning="x")
    assert decision.requires_manual_validation is False


@pytest.mark.asyncio()
async def test_unknown_domain_requires_manual_validation():
    nlu_result = NLUResult(
        text="algo ambíguo",
        domain="DOMAIN_UNKNOWN",
        confidence=0.0,
        entities={},
        keywords=[],
    )
    classifier = _classifier_with_nlu(nlu_result)
    decision = await classifier.classify("algo ambíguo")
    assert decision.requires_manual_validation is True


@pytest.mark.asyncio()
async def test_nlu_manual_validation_flag_propagates():
    nlu_result = NLUResult(
        text="negócio incerto",
        domain="BUSINESS",
        confidence=0.55,
        entities={},
        keywords=[],
        requires_manual_validation=True,
    )
    classifier = _classifier_with_nlu(nlu_result)
    decision = await classifier.classify("negócio incerto")
    assert decision.requires_manual_validation is True


@pytest.mark.asyncio()
async def test_known_domain_does_not_require_manual_validation():
    nlu_result = NLUResult(
        text="gerar relatório de vendas e dashboard",
        domain="BUSINESS",
        confidence=0.9,
        entities={},
        keywords=["relatório", "dashboard"],
    )
    classifier = _classifier_with_nlu(nlu_result)
    decision = await classifier.classify("gerar relatório de vendas e dashboard")
    assert decision.requires_manual_validation is False
