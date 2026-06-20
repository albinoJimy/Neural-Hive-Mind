"""
Testes da Task 3 — "Reativar NER/embeddings reais no STE".

Cobre os 3 caminhos obrigatórios da DoD:
1. Caminho real (sucesso/evidência): spaCy presente, entidades limpas, subject correto.
2. Fail-safe MARCADO: degradação legítima incrementa `degradation_total` e loga `degraded=true`.
3. Sem simulação silenciosa: qualquer fallback marca a métrica; helper de cleaning testado.

NÃO modifica testes existentes (contrato). Ficheiro NOVO.
"""

import pytest


def _counter_value(component: str, reason: str) -> float:
    """Lê o valor atual do counter degradation_total para (component, reason)."""
    from src.observability.metrics import degradation_total

    return degradation_total.labels(component=component, reason=reason)._value.get()


# ---------------------------------------------------------------------------
# Helper de cleaning (unitário)
# ---------------------------------------------------------------------------
class TestCleanEntityValue:
    """Testa o helper de limpeza de entidades."""

    def test_remove_artigo_pt_e_pontuacao(self):
        from src.services.nlp_processor import clean_entity_value

        assert clean_entity_value("a infraestrutura,") == "infraestrutura"

    def test_remove_artigo_o(self):
        from src.services.nlp_processor import clean_entity_value

        assert clean_entity_value("o sistema") == "sistema"

    def test_remove_artigo_the(self):
        from src.services.nlp_processor import clean_entity_value

        assert clean_entity_value("the database") == "database"

    def test_colapsa_espacos_e_trim(self):
        from src.services.nlp_processor import clean_entity_value

        assert clean_entity_value("  SAP  ") == "SAP"

    def test_entidade_so_stopword_fica_vazia(self):
        from src.services.nlp_processor import clean_entity_value

        # "a" sozinho (só artigo) deve resultar em string vazia
        assert clean_entity_value("a") == ""

    def test_pontuacao_nas_pontas(self):
        from src.services.nlp_processor import clean_entity_value

        assert clean_entity_value(",infraestrutura SAP.") == "infraestrutura SAP"

    def test_preserva_siglas_allcaps_que_coincidem_com_artigos(self):
        from src.services.nlp_processor import clean_entity_value

        # Siglas técnicas que coincidem com artigos em lowercase NÃO devem ser apagadas.
        assert clean_entity_value("OS") == "OS"
        assert clean_entity_value("AS") == "AS"
        assert clean_entity_value("A") == "A"
        # Mas o artigo real (lowercase) continua a ser removido.
        assert clean_entity_value("a") == ""
        assert clean_entity_value("os servidores") == "servidores"


class TestEntityTextCoercion:
    """`_entity_text` aceita str e dict sem TypeError."""

    def test_coerca_dict_com_value(self):
        from src.services.decomposition_templates import _entity_text

        assert _entity_text({"value": "a infraestrutura"}) == "infraestrutura"

    def test_coerca_str(self):
        from src.services.decomposition_templates import _entity_text

        assert _entity_text("o sistema") == "sistema"


# ---------------------------------------------------------------------------
# Caminho real (sucesso / evidência)
# ---------------------------------------------------------------------------
class TestRealPathSuccess:
    """spaCy presente → is_ready True, entidades limpas, subject correto."""

    @pytest.fixture()
    async def processor(self):
        from src.services.nlp_processor import NLPProcessor

        p = NLPProcessor(redis_client=None)
        await p.initialize()
        return p

    @pytest.mark.asyncio()
    async def test_is_ready_true_com_spacy(self, processor):
        assert processor.is_ready() is True

    @pytest.mark.asyncio()
    async def test_entidades_limpas_sem_artigo_nem_pontuacao(self, processor):
        text = "Migrar a infraestrutura SAP para a cloud AWS"
        entities = processor.extract_entities_advanced(text)

        values = [e["value"] for e in entities]
        # Existe uma entidade que contém "infraestrutura" ou "SAP"
        relevant = [v for v in values if "infraestrutura" in v.lower() or "sap" in v.lower()]
        assert relevant, f"esperava entidade relevante, obtive {values}"

        for v in relevant:
            # Sem artigo inicial
            first = v.lower().split()[0] if v.split() else ""
            assert first not in {
                "o",
                "a",
                "os",
                "as",
                "um",
                "uma",
                "the",
                "an",
            }, f"entidade '{v}' começa por artigo"
            # Sem pontuação nas pontas
            assert v == v.strip(" ,.;:"), f"entidade '{v}' tem pontuação nas pontas"

    @pytest.mark.asyncio()
    async def test_subject_limpo_nao_eh_entities0_cru(self, processor):
        from src.services.decomposition_templates import DecompositionTemplates

        dt = DecompositionTemplates()
        entities = ["a infraestrutura SAP", "AWS"]
        subject, target = dt._extract_subject_target("Atualizar a infraestrutura SAP", entities)

        # subject NÃO deve começar por artigo "a "
        assert not subject.lower().startswith("a "), subject
        # subject não é literalmente entities[0] cru
        assert subject != entities[0]


# ---------------------------------------------------------------------------
# Fail-safe MARCADO (degradação legítima, não silenciosa)
# ---------------------------------------------------------------------------
class TestFailSafeMarked:
    """Processador não inicializado → fallback + métrica degradation_total."""

    @pytest.fixture()
    def uninitialized(self):
        from src.services.nlp_processor import NLPProcessor

        p = NLPProcessor(redis_client=None)
        assert p._initialized is False
        return p

    def test_is_ready_false_quando_nao_init(self, uninitialized):
        assert uninitialized.is_ready() is False

    def test_keywords_fallback_incrementa_metrica(self, uninitialized):
        before = _counter_value("nlp_processor", "not_initialized")
        result = uninitialized.extract_keywords("criar sistema de pagamentos")
        after = _counter_value("nlp_processor", "not_initialized")

        assert isinstance(result, list)
        assert after == before + 1

    def test_objectives_fallback_incrementa_metrica(self, uninitialized):
        before = _counter_value("nlp_processor", "not_initialized")
        result = uninitialized.extract_objectives("criar sistema de pagamentos")
        after = _counter_value("nlp_processor", "not_initialized")

        assert isinstance(result, list)
        assert after == before + 1

    def test_entities_fallback_incrementa_metrica(self, uninitialized):
        before = _counter_value("nlp_processor", "not_initialized")
        result = uninitialized.extract_entities_advanced("criar sistema de pagamentos")
        after = _counter_value("nlp_processor", "not_initialized")

        assert result == []
        assert after == before + 1


class TestIntentClassifierDegradationMetric:
    """Reforço semântico indisponível → degradation_total marcado."""

    def test_embeddings_unavailable_incrementa_metrica(self):
        from src.services.intent_classifier import IntentClassifier

        clf = IntentClassifier()
        # Força o ramo de ImportError em _score_by_semantics: sem
        # sentence_transformers no runtime, self.model levanta ImportError.
        before = _counter_value("intent_classifier", "embeddings_unavailable")
        # Texto curto/genérico força a passagem por _score_by_semantics
        # (best_pattern_score < 0.5) na primeira classificação.
        clf._score_by_semantics("xyz")
        after = _counter_value("intent_classifier", "embeddings_unavailable")

        # _semantic_available deve ter ficado False e a métrica incrementada uma vez.
        assert clf._semantic_available is False
        assert after == before + 1


class TestPositionalSubjectFallbackMarked:
    """Sem entidades nem padrão de migração → fallback posicional MARCADO."""

    def test_fallback_posicional_incrementa_metrica(self):
        from src.services.decomposition_templates import DecompositionTemplates

        dt = DecompositionTemplates()
        before = _counter_value("decomposition_templates", "positional_subject_fallback")
        # Sem entidades e sem marcadores "de...para"/"from...to".
        subject, target = dt._extract_subject_target("gerar relatorio mensal vendas", [])
        after = _counter_value("decomposition_templates", "positional_subject_fallback")

        assert subject  # não vazio
        assert after == before + 1
