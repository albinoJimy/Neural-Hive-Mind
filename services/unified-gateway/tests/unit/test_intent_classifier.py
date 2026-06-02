"""Testes para o Intent Classifier."""

import pytest
from src.models.classification import (
    FlowType,
    IntentClassifier,
    NLUResult,
)


class MockNLUClient:
    """Mock do NLU Client para testes."""

    async def parse(
        self,
        text: str,
        language: str = "pt",
        context: dict | None = None,
        enable_cache: bool = True,
    ):
        """Retorna resultado NLU mockado baseado no texto."""

        # Texto vazio retorna baixa confiança
        if not text or text.strip() == "":
            return NLUResult(
                text=text,
                domain="DOMAIN_UNKNOWN",
                confidence=0.3,
                entities={},
                keywords=[],
            )

        # Simular classificação de domínio
        # Ordem importa: INFRASTRUCTURE tem precedência sobre TECHNICAL
        text_lower = text.lower()

        # Primeiro verificar INFRASTRUCTURE (migration tem prioridade)
        if any(
            kw in text_lower for kw in ["migrar", "legado", "migration", "atualizar", "modernizar"]
        ):
            domain = "INFRASTRUCTURE"
            confidence = 0.9
            keywords = ["migrar", "legado"]
        # Depois verificar TECHNICAL (mas não se já for INFRA)
        elif any(
            kw in text_lower
            for kw in ["gerar", "criar", "código", "app", "build", "desenvolver", "implementar"]
        ):
            domain = "TECHNICAL"
            confidence = 0.85
            keywords = ["gerar", "código"]
        # Por fim, default para BUSINESS
        else:
            domain = "BUSINESS"
            confidence = 0.75
            keywords = ["consultar", "dados"]

        return NLUResult(
            text=text,
            domain=domain,
            confidence=confidence,
            entities={},
            keywords=keywords,
        )


@pytest.fixture
def mock_nlu_client():
    """Fixture para mock NLU client."""
    return MockNLUClient()


@pytest.fixture
def classifier(mock_nlu_client):
    """Fixture para IntentClassifier com mock."""
    return IntentClassifier(nlu_client=mock_nlu_client)


@pytest.mark.asyncio
class TestIntentClassifier:
    """Testes do classificador de intenção."""

    async def test_classify_business_domain(self, classifier):
        """Testar classificação de domínio BUSINESS → Flow A-F."""
        decision = await classifier.classify("Quero consultar os dados de vendas")

        assert decision.flow_type == FlowType.AF
        assert decision.confidence > 0.7
        assert "BUSINESS" in decision.reasoning

    async def test_classify_technical_domain(self, classifier):
        """Testar classificação de domínio TECHNICAL → Flow G."""
        decision = await classifier.classify("Gerar código para um sistema de vendas")

        assert decision.flow_type == FlowType.G
        assert decision.confidence > 0.8
        assert "TECHNICAL" in decision.reasoning

    async def test_classify_infrastructure_domain(self, classifier):
        """Testar classificação de domínio INFRASTRUCTURE → Flow H."""
        # "Migrar" está nas keywords H, mas não nas keywords T ("atualizar" também está em H)
        decision = await classifier.classify("Migrar sistema antigo legado")

        assert decision.flow_type == FlowType.H
        assert decision.confidence > 0.85
        assert "INFRASTRUCTURE" in decision.reasoning

    async def test_classify_low_confidence_fallback_to_keywords(self, classifier):
        """Testar fallback para keywords quando confiança é baixa."""

        # Override mock para retornar baixa confiança
        async def low_confidence_parse(*args, **kwargs):
            text = args[0] if args else ""
            # Retorna DOMAIN_UNKNOWN com baixa confiança, sem keywords do NLU
            return NLUResult(
                text=text,
                domain="DOMAIN_UNKNOWN",
                confidence=0.4,
                entities={},
                keywords=[],  # NLU não retorna keywords
            )

        classifier._nlu_client.parse = low_confidence_parse

        decision = await classifier.classify("Criar aplicativo mobile")

        # Deve classificar por keywords (criar → Flow G)
        # O código detecta keywords e combina com NLU
        assert decision.flow_type == FlowType.G
        # A confiança é baseada no _combine_confidence (0.4 NLU + 0.1 boost = 0.5)
        assert decision.confidence >= 0.4
        # O reasoning contém o domínio NLU DOMAIN_UNKNOWN mas flow foi ajustado
        assert "DOMAIN_UNKNOWN" in decision.reasoning

    async def test_classify_without_nlu_client(self):
        """Testar classificação sem NLU client (keyword-only)."""
        classifier = IntentClassifier(nlu_client=None)

        decision = await classifier.classify("Criar novo sistema de vendas")

        assert decision.flow_type == FlowType.G  # "Criar", "sistema" → Flow G
        assert decision.confidence > 0.0


@pytest.mark.asyncio
class TestIntentClassifierEdgeCases:
    """Testes de edge cases do classificador."""

    async def test_empty_text(self, classifier):
        """Testar texto vazio."""
        decision = await classifier.classify("")

        # Deve default para A-F com baixa confiança do NLU
        assert decision.flow_type == FlowType.AF
        # NLU retorna 0.3, mas pode ter keyword boost, então verificamos apenas que está em um range razoável
        assert 0.3 <= decision.confidence <= 0.5

    async def test_multiple_keywords_same_flow(self, classifier):
        """Testar múltiplas keywords do mesmo flow."""
        decision = await classifier.classify("Gerar código, criar app, desenvolver sistema")

        assert decision.flow_type == FlowType.G
        # Confiança deve ser maior devido a múltiplas keywords
        assert decision.confidence > 0.8

    async def test_alternative_flow_provided(self, classifier):
        """Testar que flow alternativo é fornecido."""
        decision = await classifier.classify("Consultar dados")

        assert decision.alternative is not None
        assert decision.alternative in (FlowType.G, FlowType.AF)


class TestDomainToFlowMapping:
    """Testes do mapeamento domínio → flow."""

    def test_business_to_af(self):
        """Testar mapeamento BUSINESS → A-F."""
        classifier = IntentClassifier()
        flow = classifier._domain_to_flow("BUSINESS", "qualquer texto")
        assert flow == FlowType.AF

    def test_technical_to_g(self):
        """Testar mapeamento TECHNICAL → G."""
        classifier = IntentClassifier()
        flow = classifier._domain_to_flow("TECHNICAL", "qualquer texto")
        assert flow == FlowType.G

    def test_infrastructure_to_h(self):
        """Testar mapeamento INFRASTRUCTURE → H."""
        classifier = IntentClassifier()
        flow = classifier._domain_to_flow("INFRASTRUCTURE", "qualquer texto")
        assert flow == FlowType.H

    def test_security_to_af(self):
        """Testar mapeamento SECURITY → A-F."""
        classifier = IntentClassifier()
        flow = classifier._domain_to_flow("SECURITY", "qualquer texto")
        assert flow == FlowType.AF

    def test_unknown_to_af(self):
        """Testar mapeamento DOMAIN_UNKNOWN → A-F."""
        classifier = IntentClassifier()
        flow = classifier._domain_to_flow("DOMAIN_UNKNOWN", "qualquer texto")
        assert flow == FlowType.AF

    def test_unknown_with_keywords_refinement(self):
        """Testar refinamento de DOMAIN_UNKNOWN com keywords."""
        classifier = IntentClassifier()

        # DOMAIN_UNKNOWN com keywords G → Flow G
        flow = classifier._domain_to_flow("DOMAIN_UNKNOWN", "gerar código")
        assert flow == FlowType.G

        # DOMAIN_UNKNOWN com keywords H → Flow H
        flow = classifier._domain_to_flow("DOMAIN_UNKNOWN", "migrar legado")
        assert flow == FlowType.H


class TestKeywordOnlyClassification:
    """Testes de classificação apenas por keywords (fallback)."""

    def test_af_keywords(self):
        """Testar keywords de Flow A-F."""
        classifier = IntentClassifier()
        decision = classifier._classify_by_keywords("consultar dashboard de vendas")

        assert decision.flow_type == FlowType.AF
        assert decision.confidence > 0.0

    def test_g_keywords(self):
        """Testar keywords de Flow G."""
        classifier = IntentClassifier()
        decision = classifier._classify_by_keywords("gerar código para app")

        assert decision.flow_type == FlowType.G
        assert decision.confidence > 0.5

    def test_h_keywords(self):
        """Testar keywords de Flow H."""
        classifier = IntentClassifier()
        decision = classifier._classify_by_keywords("migrar sistema legado")

        assert decision.flow_type == FlowType.H
        assert decision.confidence > 0.5

    def test_no_keywords_defaults_to_af(self):
        """Testar default para A-F quando não há keywords."""
        classifier = IntentClassifier()
        decision = classifier._classify_by_keywords("texto aleatório sem keywords")

        assert decision.flow_type == FlowType.AF
        assert decision.confidence < 0.5  # Baixa confiança sem keywords


class TestConfidenceCombination:
    """Testes de combinação de confiança."""

    def test_combine_high_nlu_confidence(self):
        """Testar combinação com alta confiança NLU."""
        classifier = IntentClassifier()
        combined = classifier._combine_confidence(0.85, "gerar código")

        # Deve manter alta confiança
        assert combined >= 0.85

    def test_combine_low_nlu_confidence_with_keywords(self):
        """Testar boost de confiança com keywords."""
        classifier = IntentClassifier()
        combined = classifier._combine_confidence(0.5, "gerar código")

        # Deve ter boost devido a keywords
        assert combined > 0.5

    def test_combine_low_nlu_confidence_without_keywords(self):
        """Testar sem boost quando não há keywords."""
        classifier = IntentClassifier()
        combined = classifier._combine_confidence(0.5, "texto aleatório")

        # Sem boost
        assert combined == 0.5


class TestAlternativeFlow:
    """Testes de fluxo alternativo."""

    def test_alternative_for_af(self):
        """Testar alternativa para A-F."""
        classifier = IntentClassifier()
        alt = classifier._get_alternative(FlowType.AF)
        assert alt == FlowType.G

    def test_alternative_for_g(self):
        """Testar alternativa para G."""
        classifier = IntentClassifier()
        alt = classifier._get_alternative(FlowType.G)
        assert alt == FlowType.AF

    def test_alternative_for_h(self):
        """Testar alternativa para H."""
        classifier = IntentClassifier()
        alt = classifier._get_alternative(FlowType.H)
        assert alt == FlowType.AF
