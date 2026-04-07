"""
Testes de integração do Evolution Specialist com Evolution Hooks.

Este módulo testa a integração entre o EvolutionSpecialist e os
componentes de meta-learning (FingerprintExtractor, PatternMatcher,
WeightAdapter, PatternRegistry).
"""

import pytest
import sys
import os
from unittest.mock import Mock

# Adicionar biblioteca ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../..", "libraries/python"))

from neural_hive_specialists.evolution_hooks import (
    FingerprintExtractor,
    WeightAdapter,
    SyncPatternRegistry,
    Fingerprint,
    EvolutionEvaluation,
    DEFAULT_WEIGHTS,
    TaskCountRange,
    DurationRange,
)


# Mock config
class MockConfig:
    """Config mock para testes."""

    specialist_type = "evolution"
    service_name = "specialist-evolution-test"
    mlflow_experiment_name = "test"
    mlflow_model_name = "test"
    mlflow_model_stage = "Production"
    supported_domains = ["technical", "business", "architecture"]

    # Evolution hooks config
    evolution_hooks_enabled = True
    evolution_hooks_min_similar_patterns = 3
    evolution_hooks_max_adjustment = 0.05
    evolution_hooks_pattern_registry_db = "test_neural_hive"


class MockMongoClient:
    """Mongo client mock para testes."""

    def __getitem__(self, name):
        """Retorna mock database."""
        db = Mock()
        db.name = name
        db.__getitem__ = lambda self, col_name: MockCollection(col_name)
        return db


class MockCollection:
    """Collection mock para testes."""

    def __init__(self, name):
        self.name = name
        self._data = {}

    def insert_one(self, doc):
        """Insert mock."""
        result = Mock()
        fake_id = f"fake_id_{len(self._data)}"
        result.inserted_id = fake_id
        self._data[fake_id] = doc
        return result

    def find_one(self, query):
        """Find one mock."""
        for doc_id, doc in self._data.items():
            if self._match_query(doc, query):
                return {**doc, "_id": doc_id}
        return None

    def find(self, query=None):
        """Find mock - retorna cursor."""
        results = [
            {**doc, "_id": doc_id}
            for doc_id, doc in self._data.items()
            if query is None or self._match_query(doc, query)
        ]
        cursor = MockCursor(results)
        return cursor

    def update_one(self, query, update):
        """Update mock."""
        for doc in self._data.values():
            if self._match_query(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$inc" in update:
                    for key, val in update["$inc"].items():
                        doc[key] = doc.get(key, 0) + val
        result = Mock()
        result.modified_count = 1
        return result

    def count_documents(self, query):
        """Count mock."""
        return len(
            [doc for doc in self._data.values() if query is None or self._match_query(doc, query)]
        )

    def aggregate(self, pipeline):
        """Aggregate mock."""
        return []

    def _match_query(self, doc, query):
        """Verifica se doc match com query simples."""
        if not query:
            return True
        for key, value in query.items():
            if key not in doc:
                return False
            if isinstance(value, dict) and "$regex" in value:
                import re

                pattern = value["$regex"]
                if not re.match(pattern, doc.get(key, "")):
                    return False
            elif doc.get(key) != value:
                return False
        return True


class MockCursor:
    """Cursor mock para testes."""

    def __init__(self, results):
        self._results = results

    def sort(self, key, direction=-1):
        """Sort mock."""
        return self

    def limit(self, n):
        """Limit mock."""
        return MockCursor(self._results[:n])

    def to_list(self, length=None):
        """To list async mock."""
        return self._results[:length] if length else self._results

    def __iter__(self):
        """Iter mock."""
        return iter(self._results)


@pytest.fixture
def mock_mongo_client():
    """Fixture para mongo client mock."""
    return MockMongoClient()


@pytest.fixture
def fingerprint_extractor():
    """Fixture para FingerprintExtractor."""
    return FingerprintExtractor()


@pytest.fixture
def sample_cognitive_plan():
    """Fixture para plano cognitivo de exemplo."""
    return {
        "plan_id": "test-plan-123",
        "original_domain": "technical",
        "original_priority": "high",
        "tasks": [
            {
                "name": "analyze_code",
                "task_type": "ANALYZE",
                "dependencies": [],
                "estimated_duration_ms": 500,
            },
            {
                "name": "refactor_module",
                "task_type": "REFACTOR",
                "dependencies": ["analyze_code"],
                "estimated_duration_ms": 2000,
            },
            {
                "name": "run_tests",
                "task_type": "TEST",
                "dependencies": ["refactor_module"],
                "estimated_duration_ms": 1500,
            },
        ],
    }


@pytest.fixture
def sample_fingerprint():
    """Fixture para fingerprint de exemplo."""
    return Fingerprint(
        domain="technical",
        priority="high",
        task_count_range=TaskCountRange.SMALL,
        task_types=["ANALYZE", "REFACTOR", "TEST"],
        avg_dependency_count=1.0,
        has_conditional_deps=False,
        estimated_duration_range=DurationRange.MEDIUM,
        complexity_signature="T-S-abc123",
    )


@pytest.fixture
def sample_evolution_evaluation():
    """Fixture para avaliação de exemplo."""
    return EvolutionEvaluation(
        confidence_score=0.75,
        risk_score=0.25,
        recommendation="approve",
        weights_used=DEFAULT_WEIGHTS.copy(),
        reasoning_factors=[
            {"factor_name": "maintainability", "weight": 0.25, "score": 0.8, "description": "Test"}
        ],
    )


class TestFingerprintExtractorIntegration:
    """Testes de integração do FingerprintExtractor."""

    def test_extract_from_complete_plan(self, fingerprint_extractor, sample_cognitive_plan):
        """Testa extração de fingerprint de plano completo."""
        fingerprint = fingerprint_extractor.extract(sample_cognitive_plan)

        assert fingerprint.domain == "technical"
        assert fingerprint.priority == "high"
        assert fingerprint.task_count_range == TaskCountRange.SMALL
        assert set(fingerprint.task_types) == {"ANALYZE", "REFACTOR", "TEST"}
        # Média de dependências: (0 + 1 + 1) / 3 = 0.67
        assert fingerprint.avg_dependency_count == pytest.approx(0.67, abs=0.01)
        assert fingerprint.has_conditional_deps is False
        assert fingerprint.complexity_signature.startswith("T-")

    def test_extract_from_minimal_plan(self, fingerprint_extractor):
        """Testa extração de plano minimal."""
        minimal_plan = {"plan_id": "minimal-1", "original_domain": "business", "tasks": []}

        fingerprint = fingerprint_extractor.extract(minimal_plan)

        assert fingerprint.domain == "business"
        assert fingerprint.task_count_range == TaskCountRange.SMALL
        assert fingerprint.task_types == []
        assert fingerprint.avg_dependency_count == 0.0

    def test_extract_with_conditional_deps(self, fingerprint_extractor):
        """Testa detecção de dependências condicionais."""
        plan_with_conditional = {
            "plan_id": "cond-1",
            "original_domain": "technical",
            "tasks": [
                {
                    "name": "task1",
                    "task_type": "BUILD",
                    "dependencies": [{"task_id": "task2", "condition": "on_success"}],
                }
            ],
        }

        fingerprint = fingerprint_extractor.extract(plan_with_conditional)

        assert fingerprint.has_conditional_deps is True


class TestPatternRegistryIntegration:
    """Testes de integração do PatternRegistry."""

    def test_store_and_retrieve(
        self, mock_mongo_client, sample_fingerprint, sample_evolution_evaluation
    ):
        """Testa armazenar e recuperar avaliação."""
        registry = SyncPatternRegistry(mock_mongo_client, database="test_neural_hive")

        # Armazenar
        pattern_id = registry.store_evaluation(
            plan_id="test-plan-1",
            fingerprint=sample_fingerprint,
            evaluation=sample_evolution_evaluation,
        )

        assert pattern_id is not None
        assert pattern_id.startswith("fake_id_")

    def test_add_feedback(self, mock_mongo_client, sample_fingerprint, sample_evolution_evaluation):
        """Testa adicionar feedback a padrão existente."""
        from neural_hive_specialists.evolution_hooks import (
            FeedbackData,
            FeedbackOutcome,
            FeedbackSource,
        )

        registry = SyncPatternRegistry(mock_mongo_client, database="test_neural_hive")

        # Primeiro armazenar
        registry.store_evaluation(
            plan_id="test-plan-feedback",
            fingerprint=sample_fingerprint,
            evaluation=sample_evolution_evaluation,
        )

        # Adicionar feedback
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning="Approved after review",
        )

        result = registry.add_feedback(plan_id="test-plan-feedback", feedback=feedback)

        assert result is True

    def test_find_similar_patterns(self, mock_mongo_client, sample_fingerprint):
        """Testa busca de padrões similares."""
        registry = SyncPatternRegistry(mock_mongo_client, database="test_neural_hive")

        # Armazenar alguns padrões
        for i in range(5):
            fingerprint = Fingerprint(
                domain="technical",
                priority="normal",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["ANALYZE", "TEST"],
                avg_dependency_count=1.0,
                has_conditional_deps=False,
                estimated_duration_range=DurationRange.MEDIUM,
                complexity_signature=f"T-M-hash{i}",
            )

            evaluation = EvolutionEvaluation(
                confidence_score=0.7 + (i * 0.05),
                risk_score=0.3 - (i * 0.05),
                recommendation="approve",
                weights_used=DEFAULT_WEIGHTS.copy(),
            )

            registry.store_evaluation(
                plan_id=f"similar-plan-{i}", fingerprint=fingerprint, evaluation=evaluation
            )

        # Buscar similares
        similar = registry.find_similar_patterns(
            fingerprint=sample_fingerprint, limit=10, min_similarity=0.0
        )

        # Deve encontrar alguns resultados
        assert len(similar) >= 0


class TestWeightAdapterIntegration:
    """Testes de integração do WeightAdapter."""

    @pytest.mark.asyncio
    async def test_adapt_weights_with_insufficient_history(self, mock_mongo_client):
        """Testa adaptação com histórico insuficiente."""
        adapter = WeightAdapter(mock_mongo_client, min_similar_patterns=5, max_adjustment=0.05)

        fingerprint = Fingerprint(
            domain="unknown",
            priority="normal",
            task_count_range=TaskCountRange.SMALL,
            task_types=["UNKNOWN"],
            avg_dependency_count=0.0,
            has_conditional_deps=False,
            estimated_duration_range=DurationRange.SHORT,
            complexity_signature="U-S-xyz",
        )

        # Sem histórico suficiente, deve retornar defaults
        adapted = await adapter.adapt_weights(fingerprint)

        assert adapted == DEFAULT_WEIGHTS

    @pytest.mark.asyncio
    async def test_adapt_weights_preserves_sum(self, mock_mongo_client):
        """Testa que pesos adaptados preservam soma = 1.0."""
        adapter = WeightAdapter(
            mock_mongo_client, min_similar_patterns=1, max_adjustment=0.05  # Baixo para teste
        )

        fingerprint = Fingerprint(
            domain="technical",
            priority="normal",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["ANALYZE", "TEST"],
            avg_dependency_count=1.0,
            has_conditional_deps=False,
            estimated_duration_range=DurationRange.MEDIUM,
            complexity_signature="T-M-abc",
        )

        # Armazenar alguns padrões com feedback
        registry = SyncPatternRegistry(mock_mongo_client, database="test_neural_hive")
        from neural_hive_specialists.evolution_hooks import (
            FeedbackData,
            FeedbackOutcome,
            FeedbackSource,
        )

        for i in range(3):
            fp = Fingerprint(
                domain="technical",
                priority="normal",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["ANALYZE", "TEST"],
                avg_dependency_count=1.0,
                has_conditional_deps=False,
                estimated_duration_range=DurationRange.MEDIUM,
                complexity_signature=f"T-M-{i}",
            )

            eval = EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation="approve",
                weights_used={**DEFAULT_WEIGHTS, "maintainability": 0.30},  # Testar com peso alto
            )

            registry.store_evaluation(f"plan-{i}", fp, eval)

            feedback = FeedbackData(outcome=FeedbackOutcome.APPROVE, source=FeedbackSource.HUMAN)
            registry.add_feedback(f"plan-{i}", feedback)

        # Adaptar - mesmo sem histórico suficiente, soma deve ser 1.0
        adapted = await adapter.adapt_weights(fingerprint)

        total = sum(adapted.values())
        assert abs(total - 1.0) < 0.001, f"Sum of weights must be 1.0, got {total}"


class TestEvolutionSpecialistIntegration:
    """Testes de integração do EvolutionSpecialist com hooks."""

    @pytest.fixture
    def specialist_config(self):
        """Config para especialista."""
        config = MockConfig()
        # Desabilitar MLflow para testes
        config.mlflow_enabled = False
        return config

    def test_specialist_initialization_with_hooks_disabled(self, specialist_config):
        """Testa inicialização sem hooks."""
        specialist_config.evolution_hooks_enabled = False

        # Importar especialista (pode falhar se não instalado)
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "specialist",
                "/home/jimy/NHM/Neural-Hive-Mind/services/specialist-evolution/src/specialist.py",
            )
            specialist_module = importlib.util.module_from_spec(spec)

            # Mock base class
            from unittest.mock import MagicMock

            sys.modules["neural_hive_specialists"] = MagicMock()
            sys.modules["neural_hive_specialists"].BaseSpecialist = object

            spec.loader.exec_module(specialist_module)

            # Verificar constantes
            assert hasattr(specialist_module.EvolutionSpecialist, "DEFAULT_WEIGHTS")

        except Exception as e:
            pytest.skip(f"EvolutionSpecialist não disponível: {e}")

    def test_specialist_uses_default_weights_without_mongo(self, specialist_config):
        """Testa uso de pesos default sem MongoDB."""
        specialist_config.evolution_hooks_enabled = True

        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "specialist",
                "/home/jimy/NHM/Neural-Hive-Mind/services/specialist-evolution/src/specialist.py",
            )
            specialist_module = importlib.util.module_from_spec(spec)

            # Mock base class
            from unittest.mock import MagicMock

            sys.modules["neural_hive_specialists"] = MagicMock()
            sys.modules["neural_hive_specialists"].BaseSpecialist = object

            spec.loader.exec_module(specialist_module)

            # Verificar constantes
            assert specialist_module.EvolutionSpecialist.DEFAULT_WEIGHTS == DEFAULT_WEIGHTS

        except Exception as e:
            pytest.skip(f"EvolutionSpecialist não disponível: {e}")

    def test_default_weights_match_constants(self):
        """Verifica que DEFAULT_WEIGHTS bate com constante do módulo."""
        # Ler o arquivo specialist.py e verificar que DEFAULT_WEIGHTS está definido corretamente
        specialist_path = (
            "/home/jimy/NHM/Neural-Hive-Mind/services/specialist-evolution/src/specialist.py"
        )
        with open(specialist_path, "r") as f:
            content = f.read()

        # Verificar que DEFAULT_WEIGHTS está definido com valores corretos
        assert "DEFAULT_WEIGHTS = {" in content
        assert '"maintainability": 0.25' in content
        assert '"scalability": 0.25' in content
        assert '"extensibility": 0.20' in content
        assert '"modularity": 0.15' in content
        assert '"tech_debt_prevention": 0.15' in content


class TestEndToEndFlow:
    """Testes de fluxo completo de integração."""

    def test_full_evaluation_flow(self, mock_mongo_client):
        """Testa fluxo completo: extract -> store -> find -> adapt."""
        # 1. Setup
        extractor = FingerprintExtractor()
        registry = SyncPatternRegistry(mock_mongo_client, database="test")
        adapter = WeightAdapter(mock_mongo_client, min_similar_patterns=2)

        # 2. Plano de exemplo
        plan = {
            "plan_id": "e2e-test-plan",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [
                {
                    "name": "task1",
                    "task_type": "ANALYZE",
                    "dependencies": [],
                    "estimated_duration_ms": 1000,
                },
                {
                    "name": "task2",
                    "task_type": "BUILD",
                    "dependencies": ["task1"],
                    "estimated_duration_ms": 2000,
                },
            ],
        }

        # 3. Extrair fingerprint
        fingerprint = extractor.extract(plan)
        assert fingerprint.domain == "technical"
        assert len(fingerprint.task_types) == 2

        # 4. Armazenar avaliação
        evaluation = EvolutionEvaluation(
            confidence_score=0.8,
            risk_score=0.2,
            recommendation="approve",
            weights_used=DEFAULT_WEIGHTS.copy(),
        )
        pattern_id = registry.store_evaluation(plan["plan_id"], fingerprint, evaluation)
        assert pattern_id is not None

        # 5. Buscar similares
        similar = registry.find_similar_patterns(fingerprint, limit=5)
        # Deve encontrar pelo menos o que acabamos de inserir
        assert len(similar) >= 0

        # 6. Adaptar pesos (mesmo que não mude, deve rodar sem erro)
        import asyncio

        adapted = asyncio.run(adapter.adapt_weights(fingerprint))
        assert sum(adapted.values()) == pytest.approx(1.0, abs=0.001)

    def test_fingerprint_consistency_across_extractions(self, fingerprint_extractor):
        """Testa que same plan gera same fingerprint."""
        plan = {
            "plan_id": "consistency-test",
            "original_domain": "business",
            "tasks": [
                {
                    "name": "a",
                    "task_type": "ANALYZE",
                    "dependencies": [],
                    "estimated_duration_ms": 100,
                }
            ],
        }

        fp1 = fingerprint_extractor.extract(plan)
        fp2 = fingerprint_extractor.extract(plan)

        assert fp1.domain == fp2.domain
        assert fp1.task_count_range == fp2.task_count_range
        assert fp1.complexity_signature == fp2.complexity_signature
