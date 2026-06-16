"""
Testes unitários para degradação graciosa do IntentClassifier quando o
reforço semântico (sentence_transformers/sklearn) está indisponível.

Cenário do bug [ste-sentence-transformers]: o pacote `sentence_transformers`
não está instalado no runtime do STE. Antes da correção, o import lazy levantava
ModuleNotFoundError não-tratado, propagava até ao DAGGenerator e degradava todos
os planos para o fallback legado (num_tasks=1). Estes testes garantem que a
classificação por padrões linguísticos continua a funcionar sem embeddings.
"""

import builtins

import pytest
from src.services.dag_generator import DAGGenerator
from src.services.intent_classifier import IntentClassifier, IntentType


@pytest.fixture(autouse=True)
def _no_sentence_transformers(monkeypatch):
    """Simula ausência do pacote sentence_transformers no runtime."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


class TestSemanticFallback:
    """Garante degradação graciosa sem sentence_transformers."""

    def test_classify_migration_without_embeddings(self):
        """Migração com keywords claras classifica corretamente sem embeddings."""
        classifier = IntentClassifier(config={"intent_classification_min_confidence": 0.3})
        intent = "Migrar banco de dados de PostgreSQL para MongoDB"

        classification = classifier.classify(intent)

        # Não pode cair em GENERIC: keywords/verbos de migração são suficientes
        assert classification.intent_type == IntentType.MIGRATION
        assert classification.confidence >= 0.3
        # Templates ricos: migração recomenda múltiplas tasks
        assert classification.recommended_task_count > 1

    def test_security_audit_without_embeddings(self):
        """Auditoria de segurança classifica via padrões, sem embeddings."""
        classifier = IntentClassifier(config={"intent_classification_min_confidence": 0.3})
        intent = "Realizar auditoria de segurança no sistema de autenticação"

        classification = classifier.classify(intent)

        assert classification.intent_type == IntentType.SECURITY_AUDIT
        assert classification.confidence >= 0.3
        assert classification.recommended_task_count > 1

    def test_semantic_available_flag_set_false_once(self):
        """O flag _semantic_available é definido como False após primeira falha."""
        classifier = IntentClassifier(config={"intent_classification_min_confidence": 0.3})

        # Intent fraco em padrões força o caminho semântico (_score_by_semantics)
        classifier.classify("fazer algo indefinido qualquer")

        assert classifier._semantic_available is False

    def test_score_by_semantics_returns_zeros_when_unavailable(self):
        """_score_by_semantics devolve scores zerados sem levantar exceção."""
        classifier = IntentClassifier(config={"intent_classification_min_confidence": 0.3})

        scores = classifier._score_by_semantics("texto qualquer")

        assert scores  # não vazio
        assert all(value == 0.0 for value in scores.values())
        # GENERIC não deve estar nos scores semânticos
        assert IntentType.GENERIC not in scores

    def test_weak_pattern_does_not_crash(self):
        """Intent sem padrões claros degrada para GENERIC sem crash."""
        classifier = IntentClassifier(config={"intent_classification_min_confidence": 0.3})

        classification = classifier.classify("xyz abc def")

        # Sem padrões e sem embeddings -> GENERIC (comportamento controlado)
        assert classification.intent_type == IntentType.GENERIC

    def test_combined_scores_does_not_mutate_pattern_scores(self):
        """classify() não deve corromper o dict retornado por _score_by_patterns.

        Guarda a cópia defensiva: combined_scores não partilha referência com
        os pattern_scores, evitando corrupção do dict partilhado no futuro.
        """
        classifier = IntentClassifier(config={"intent_classification_min_confidence": 0.3})

        original = classifier._score_by_patterns("migrar banco de dados")
        snapshot = dict(original)

        # classify() recalcula internamente; confirmamos que múltiplas chamadas
        # não acumulam efeitos colaterais entre si.
        classifier.classify("migrar banco de dados")
        again = classifier._score_by_patterns("migrar banco de dados")

        assert again == snapshot


class TestDAGGeneratorRichDecompositionWithoutEmbeddings:
    """E2E: a cadeia dag_generator -> classify -> templates gera num_tasks>1.

    Reproduz o sintoma original do bug [ste-sentence-transformers] ao nível da
    integração: sem sentence_transformers, o except largo de dag_generator.py:492
    degradava todos os planos para o fallback legado (num_tasks=1). Estes testes
    travam regressões futuras nesse except, provando que a decomposição rica por
    template continua a funcionar via padrões linguísticos.
    """

    @pytest.fixture()
    def dag_generator(self):
        """DAGGenerator com decomposição por intent habilitada."""
        return DAGGenerator(intent_decomposition_enabled=True)

    def test_migration_generates_rich_decomposition(self, dag_generator):
        """Migração gera múltiplas tasks por template, sem embeddings."""
        intermediate_repr = {
            "original_text": "Migrar banco de dados de PostgreSQL para MongoDB com zero downtime",
            "objectives": ["migrate"],
            "entities": [
                {"type": "database", "name": "PostgreSQL"},
                {"type": "database", "name": "MongoDB"},
            ],
            "constraints": {"domain": "architecture"},
        }

        tasks, execution_order = dag_generator.generate(intermediate_repr)

        # Sintoma do bug: fallback legado gerava num_tasks=1. A correção garante
        # decomposição rica (>1) mesmo sem sentence_transformers instalado.
        assert len(tasks) > 1
        assert len(execution_order) == len(tasks)

        # Confirma que veio do template (não do fallback legado).
        template_tasks = [
            t for t in tasks if t.metadata.get("decomposition_method") == "template_based"
        ]
        assert len(template_tasks) > 1

    def test_security_audit_generates_rich_decomposition(self, dag_generator):
        """Auditoria de segurança gera decomposição rica, sem embeddings."""
        intermediate_repr = {
            "original_text": "Realizar auditoria de segurança no sistema de autenticação",
            "objectives": ["audit"],
            "entities": [{"type": "system", "name": "autenticação"}],
            "constraints": {"domain": "security"},
        }

        tasks, _ = dag_generator.generate(intermediate_repr)

        assert len(tasks) > 1
        template_tasks = [
            t for t in tasks if t.metadata.get("decomposition_method") == "template_based"
        ]
        assert len(template_tasks) > 1
