"""Testes unitários para Intent Classifier."""

import pytest

from src.models.classification import (
    ClassificationDecision,
    FlowType,
    IntentClassifier,
    NLUResult,
)


@pytest.fixture
def classifier() -> IntentClassifier:
    """Retorna instância do classificador."""
    return IntentClassifier()


@pytest.fixture
def nlu_result_base() -> NLUResult:
    """Resultado NLU base."""
    return NLUResult(
        text="",
        domain="BUSINESS",
        confidence=0.8,
        entities={},
        keywords=[],
    )


def test_classify_simple_intent_af_dashboard(classifier, nlu_result_base):
    """Classifica 'criar dashboard' como Fluxo A-F."""
    nlu_result_base.text = "Criar dashboard de vendas"
    nlu_result_base.keywords = ["criar", "dashboard", "vendas"]

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.AF
    assert decision.confidence >= 0.5
    assert "dashboard" in decision.reasoning.lower()


def test_classify_simple_intent_g_software(classifier, nlu_result_base):
    """Classifica 'gerar sistema' como Fluxo G."""
    nlu_result_base.text = "Gerar sistema de gestão de tarefas"
    nlu_result_base.keywords = ["gerar", "sistema", "gestão"]

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.G
    assert decision.confidence >= 0.5
    assert "sistema" in decision.reasoning.lower() or "software" in decision.reasoning.lower()


def test_classify_simple_intent_h_migration(classifier, nlu_result_base):
    """Classifica 'migrar legado' como Fluxo H."""
    nlu_result_base.text = "Migrar sistema legado para nova arquitetura"
    nlu_result_base.keywords = ["migrar", "legado", "arquitetura"]

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.H
    assert decision.confidence >= 0.5
    assert "migration" in decision.reasoning.lower()


def test_classify_keywords_af_priority(classifier, nlu_result_base):
    """Palavras-chave de A-F têm prioridade."""
    nlu_result_base.text = "Consultar dados do dashboard de vendas"
    nlu_result_base.keywords = ["consultar", "dados", "dashboard"]

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.AF


def test_classify_keywords_g_priority(classifier, nlu_result_base):
    """Palavras-chave de G têm prioridade."""
    nlu_result_base.text = "Desenvolver aplicação web completa"
    nlu_result_base.keywords = ["desenvolver", "aplicação", "web"]

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.G


def test_classify_keywords_h_priority(classifier, nlu_result_base):
    """Palavras-chave de H têm prioridade."""
    nlu_result_base.text = "Migrar base de dados legada"
    nlu_result_base.keywords = ["migrar", "base", "dados", "legada"]

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.H


def test_classify_entity_software_type(classifier, nlu_result_base):
    """Entidade software_type classifica como G."""
    nlu_result_base.text = "Criar novo app"
    nlu_result_base.entities = {"software_type": "web_app"}

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.G


def test_classify_entity_legacy_system(classifier, nlu_result_base):
    """Entidade legacy_system classifica como H."""
    nlu_result_base.text = "Atualizar sistema antigo"
    nlu_result_base.entities = {"legacy_system": "mainframe"}

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.H


def test_classify_default_to_af(classifier, nlu_result_base):
    """Sem indicadores claros, deve defaultar para A-F."""
    nlu_result_base.text = "Processar solicitação"
    nlu_result_base.keywords = ["processar", "solicitação"]

    decision = classifier.classify(nlu_result_base)

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


def test_confidence_threshold(classifier, nlu_result_base):
    """Confiança deve estar entre 0 e 1."""
    nlu_result_base.text = "Teste genérico"
    nlu_result_base.keywords = ["teste"]

    decision = classifier.classify(nlu_result_base)

    assert 0 <= decision.confidence <= 1


def test_multiple_indicators_same_flow(classifier, nlu_result_base):
    """Múltiplos indicadores do mesmo fluxo aumentam confiança."""
    nlu_result_base.text = "Gerar sistema completo com código fonte e documentação"
    nlu_result_base.keywords = ["gerar", "sistema", "código", "documentação"]
    nlu_result_base.entities = {"software_type": "full_stack"}

    decision = classifier.classify(nlu_result_base)

    assert decision.flow_type == FlowType.G
    assert decision.confidence > 0.8  # Alta confiança
