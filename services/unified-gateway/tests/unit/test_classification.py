"""Testes unitários para Intent Classifier."""

import pytest

from src.models.classification import (
    ClassificationDecision,
    FlowType,
    IntentClassifier,
)


@pytest.fixture
def classifier() -> IntentClassifier:
    """Retorna instância do classificador sem NLU client (usa keywords)."""
    return IntentClassifier(nlu_client=None)


@pytest.mark.asyncio
async def test_classify_simple_intent_af_dashboard(classifier):
    """Classifica 'consultar dashboard' como Fluxo A-F."""
    decision = await classifier.classify("Consultar dashboard de vendas")

    assert decision.flow_type == FlowType.AF
    assert decision.confidence >= 0.5


@pytest.mark.asyncio
async def test_classify_simple_intent_g_software(classifier):
    """Classifica 'gerar sistema' como Fluxo G."""
    decision = await classifier.classify("Gerar sistema de gestão de tarefas")

    assert decision.flow_type == FlowType.G
    assert decision.confidence >= 0.5
    assert "keywords" in decision.reasoning.lower()


@pytest.mark.asyncio
async def test_classify_simple_intent_h_migration(classifier):
    """Classifica 'migrar legado' como Fluxo H."""
    decision = await classifier.classify("Migrar sistema legado para nova arquitetura")

    assert decision.flow_type == FlowType.H
    assert decision.confidence >= 0.5
    assert "keywords" in decision.reasoning.lower()


@pytest.mark.asyncio
async def test_classify_keywords_af_priority(classifier):
    """Palavras-chave de A-F têm prioridade."""
    decision = await classifier.classify("Consultar dados do dashboard de vendas")

    assert decision.flow_type == FlowType.AF


@pytest.mark.asyncio
async def test_classify_keywords_g_priority(classifier):
    """Palavras-chave de G têm prioridade."""
    decision = await classifier.classify("Desenvolver aplicação web completa")

    assert decision.flow_type == FlowType.G


@pytest.mark.asyncio
async def test_classify_keywords_h_priority(classifier):
    """Palavras-chave de H têm prioridade."""
    decision = await classifier.classify("Migrar sistema legado para arquitetura moderna")

    assert decision.flow_type == FlowType.H


@pytest.mark.asyncio
async def test_classify_default_to_af(classifier):
    """Sem indicadores claros, deve defaultar para A-F."""
    decision = await classifier.classify("Processar solicitação genérica")

    assert decision.flow_type == FlowType.AF
    assert decision.confidence < 0.7  # Baixa confiança para default


def test_classification_decision_model():
    """ClassificationDecision model deve ser válido."""
    decision = ClassificationDecision(
        flow_type=FlowType.AF,
        confidence=0.85,
        reasoning="Palavras-chave indicam consulta de dados",
        alternative=FlowType.G,
    )

    assert decision.flow_type == FlowType.AF
    assert decision.confidence == 0.85
    assert "consulta" in decision.reasoning.lower()
    assert decision.alternative == FlowType.G


def test_flow_type_enum():
    """FlowType enum deve ter valores corretos."""
    assert FlowType.AF.value == "A-F"
    assert FlowType.G.value == "G"
    assert FlowType.H.value == "H"


@pytest.mark.asyncio
async def test_confidence_threshold(classifier):
    """Confiança deve estar entre 0 e 1."""
    decision = await classifier.classify("Teste genérico")

    assert 0 <= decision.confidence <= 1


@pytest.mark.asyncio
async def test_multiple_indicators_same_flow(classifier):
    """Múltiplos indicadores do mesmo fluxo aumentam confiança."""
    decision = await classifier.classify("Gerar sistema completo com código fonte e documentação")

    assert decision.flow_type == FlowType.G
    assert decision.confidence > 0.7  # Alta confiança
