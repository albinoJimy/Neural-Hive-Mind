"""
Testes para a normalização de acentos na classificação de domínio.

Contexto: o matching de keywords era exato e não normalizava acentos, pelo que
intents escritas sem acentos (ex.: 'seguranca') caíam no fallback TECHNICAL/0.2
em vez de classificarem corretamente (SECURITY). Esta correção normaliza ambos
os lados do match (texto e léxico).
"""

import pytest

from src.models.nlu import UnifiedDomain
from src.services.nlu_pipeline import NLUPipelineService


@pytest.fixture
def nlu_service():
    """Serviço NLU com regras default e estruturas otimizadas preparadas."""
    service = NLUPipelineService()
    service.nlp = type("MockSpacy", (), {"ents": []})()
    service.nlp_models = {"default": service.nlp, "pt": service.nlp}
    service._ready = True
    service.classification_rules = service._get_default_rules()
    service._prepare_optimized_structures()
    return service


class TestStripAccents:
    """Testes da função utilitária de remoção de acentos."""

    def test_remove_acentos_comuns(self):
        assert NLUPipelineService._strip_accents("segurança") == "seguranca"
        assert NLUPipelineService._strip_accents("autenticação") == "autenticacao"
        assert NLUPipelineService._strip_accents("relatório") == "relatorio"

    def test_lowercase_aplicado(self):
        assert NLUPipelineService._strip_accents("SEGURANÇA") == "seguranca"

    def test_texto_sem_acentos_inalterado(self):
        assert NLUPipelineService._strip_accents("oauth2 jwt mfa") == "oauth2 jwt mfa"


class TestClassificacaoRobustaAcentos:
    """A classificação deve ser equivalente com e sem acentos."""

    def test_security_sem_acentos_classifica_igual(self, nlu_service):
        # Sem acentos (caso que antes caía no fallback TECHNICAL/0.2)
        domain_sem, _, conf_sem = nlu_service._classify_domain(
            "Consultar incidentes de seguranca e autenticacao", [], "pt", None
        )
        # Com acentos (já funcionava)
        domain_com, _, conf_com = nlu_service._classify_domain(
            "Consultar incidentes de segurança e autenticação", [], "pt", None
        )
        assert domain_sem == UnifiedDomain.SECURITY
        assert domain_com == UnifiedDomain.SECURITY
        assert conf_sem == conf_com
        assert conf_sem > 0.2  # já não cai no fallback

    def test_business_sem_acentos(self, nlu_service):
        domain, _, conf = nlu_service._classify_domain(
            "Gerar relatorio de vendas e metricas de negocio", [], "pt", None
        )
        assert domain == UnifiedDomain.BUSINESS
        assert conf > 0.2

    def test_keyword_sets_normalizados(self, nlu_service):
        # Os sets de keywords não devem conter acentos após a preparação.
        for domain_name, kw_set in nlu_service.keyword_sets.items():
            for kw in kw_set:
                assert kw == NLUPipelineService._strip_accents(
                    kw
                ), f"keyword '{kw}' em {domain_name} não está normalizada"
