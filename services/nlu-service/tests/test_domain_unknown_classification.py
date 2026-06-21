"""
Testes para a classificação honesta de domínio (Task 10 da spec
caminho-real-first-class).

Princípio: marcar+falhar em vez de adivinhar. Quando nenhuma regra bate, o
domínio é UNKNOWN (não um default cego TECHNICAL) e o resultado reporta o
`classification_method` e força validação humana.
"""

import pytest

from src.models.nlu import NLUResult, UnifiedDomain
from src.services.nlu_pipeline import NLUPipelineService


@pytest.fixture
async def nlu_service():
    service = NLUPipelineService()
    service.nlp = type("MockSpacy", (), {"ents": []})()
    service.nlp_models = {"default": service.nlp, "pt": service.nlp}
    service._ready = True
    service._load_classification_rules = lambda: None
    service.classification_rules = service._get_default_rules()
    service._prepare_optimized_structures()
    return service


class TestUnknownDomain:
    def test_enum_has_unknown(self):
        assert UnifiedDomain.UNKNOWN.value == "UNKNOWN"

    def test_coerce_invalid_domain_is_unknown_not_technical(self):
        # Domínio inválido NÃO é coagido a TECHNICAL (default cego); vira UNKNOWN
        result = NLUResult(processed_text="x", domain="NAO_EXISTE", confidence=0.5)
        assert result.domain == UnifiedDomain.UNKNOWN

    @pytest.mark.asyncio
    async def test_no_keyword_match_returns_unknown(self, nlu_service):
        # Texto sem qualquer keyword/pattern de domínio → UNKNOWN, confiança 0
        text = "xyzzy plugh frobnicate quux blorp"
        domain, _classification, confidence = nlu_service._classify_domain(text, [], "pt", None)
        assert domain == UnifiedDomain.UNKNOWN
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_keyword_match_is_not_unknown(self, nlu_service):
        # Texto com keywords claras → domínio concreto (não UNKNOWN)
        domain, _classification, _confidence = nlu_service._classify_domain(
            "Relatório de vendas do cliente", [], "pt", None
        )
        assert domain != UnifiedDomain.UNKNOWN

    def test_classification_method_reports_provenance(self):
        # Honestidade: método explícito por proveniência
        assert NLUPipelineService._classification_method(UnifiedDomain.UNKNOWN) == "no_match"
        assert NLUPipelineService._classification_method(UnifiedDomain.BUSINESS) == "keyword_rules"
