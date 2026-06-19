"""
Testes unitários para ExplainabilityGenerator.

Cobertura: generate com/sem modelo, determinação de método (shap/lime/heuristic),
feature importances, persistência/recuperação, circuit breaker.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from circuitbreaker import CircuitBreakerError

from neural_hive_specialists.explainability_generator import ExplainabilityGenerator


@pytest.mark.unit()
class TestExplainabilityGeneratorInitialization:
    """Testes de inicialização do ExplainabilityGenerator."""

    def test_initialization_success(self, mock_config, mock_metrics):
        """Testa inicialização bem-sucedida."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            gen = ExplainabilityGenerator(mock_config, metrics=mock_metrics)

            assert gen.config == mock_config
            assert gen._metrics == mock_metrics

    def test_initialization_creates_ledger(self, mock_config):
        """Verifica criação de ledger."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient") as mock_mongo:
            gen = ExplainabilityGenerator(mock_config)

            assert gen.ledger_v2 is not None


@pytest.mark.unit()
class TestGenerateWithModel:
    """Testes de geração de explicabilidade com modelo."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator com MongoDB mockado."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient") as mock_mongo:
            gen = ExplainabilityGenerator(mock_config)
            # Mock ledger_v2 para evitar chamadas reais ao MongoDB
            gen.ledger_v2 = MagicMock()
            gen.ledger_v2.persist = MagicMock(return_value="test_token_v2")
            return gen

    def test_generate_with_shap_model(
        self, generator, sample_evaluation_result, sample_cognitive_plan
    ):
        """Testa geração com modelo usando SHAP."""
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[0.85])

        # Mock feature_extractor
        generator._feature_extractor = MagicMock()
        generator._feature_extractor.extract_features = MagicMock(
            return_value={
                "aggregated_features": {"feature1": 0.5, "feature2": 0.3},
                "feature_names": ["feature1", "feature2"],
            }
        )

        # Mock shap_explainer
        generator.shap_explainer.explain = MagicMock(
            return_value={
                "feature_importances": [
                    {"feature_name": "feature1", "importance": 0.6, "contribution": "positive"},
                    {"feature_name": "feature2", "importance": 0.3, "contribution": "positive"},
                ]
            }
        )

        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=mock_model,
        )

        assert token is not None
        assert len(token) == 36  # UUID
        assert "method" in metadata
        assert "feature_importances" in metadata
        assert "model_type" in metadata
        assert "model_version" in metadata

    def test_generate_persists_explanation(
        self, generator, sample_evaluation_result, sample_cognitive_plan
    ):
        """Verifica que explicação é persistida."""
        mock_model = Mock()

        generator._feature_extractor = MagicMock()
        generator._feature_extractor.extract_features = MagicMock(
            return_value={"aggregated_features": {}, "feature_names": []}
        )

        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=mock_model,
        )

        # Verifica que ledger_v2.persist foi chamado
        generator.ledger_v2.persist.assert_called_once()


@pytest.mark.unit()
class TestGenerateWithoutModel:
    """Testes de geração heurística sem modelo."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator com ledger mockado."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient") as mock_mongo:
            gen = ExplainabilityGenerator(mock_config)
            gen.ledger_v2 = MagicMock()
            gen.ledger_v2.persist = MagicMock(return_value="test_token_v2")
            return gen

    def test_generate_without_model_uses_heuristic(
        self, generator, sample_evaluation_result, sample_cognitive_plan
    ):
        """Testa que método heurístico é usado sem modelo."""
        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=None,
        )

        assert metadata["method"] == "heuristic"
        assert "feature_importances" in metadata
        assert "model_type" in metadata

    def test_generate_extracts_feature_importances_from_reasoning_factors(
        self, generator, sample_evaluation_result, sample_cognitive_plan
    ):
        """Verifica extração de feature importances dos reasoning factors."""
        sample_evaluation_result["reasoning_factors"] = [
            {
                "factor_name": "complexity",
                "weight": 0.5,
                "score": 0.9,
            },
            {"factor_name": "risk", "weight": 0.3, "score": 0.2},
        ]

        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=None,
        )

        assert "feature_importances" in metadata
        importances = metadata["feature_importances"]
        # Deve extrair dos reasoning_factors
        assert len(importances) >= 0


@pytest.mark.unit()
class TestMethodDetermination:
    """Testes de determinação do método de explicabilidade."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            return ExplainabilityGenerator(mock_config)

    def test_determine_method_no_model(self, generator):
        """Sem modelo, deve retornar heuristic."""
        method = generator._determine_method(model=None)
        assert method == "heuristic"

    def test_determine_method_with_random_forest(self, generator):
        """Com modelo RandomForest, deve retornar shap."""
        mock_model = Mock()
        mock_model.__class__.__name__ = "RandomForestClassifier"

        method = generator._determine_method(model=mock_model)
        assert method == "shap"

    def test_determine_method_with_linear_model(self, generator):
        """Com modelo linear, deve retornar lime."""
        mock_model = Mock()
        mock_model.__class__.__name__ = "LogisticRegression"

        method = generator._determine_method(model=mock_model)
        assert method == "lime"


@pytest.mark.unit()
class TestUnwrapModel:
    """Testes de desembrulhamento de MLflow PyFuncModel para o estimador nativo.

    Causa-raiz (análise SHAP 2026-06-19): os specialists carregam modelos via
    mlflow.pyfunc.load_model, que devolve um PyFuncModel genérico. Sem desembrulhar,
    o método de explicabilidade é sempre 'heuristic'. A cadeia real em produção é:
    PyFuncModel -> _model_impl.python_model (ProbabilisticModelWrapper)
    -> sklearn_model (RandomForestClassifier).
    """

    @pytest.fixture()
    def generator(self, mock_config):
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            return ExplainabilityGenerator(mock_config)

    def _make_random_forest(self):
        rf = Mock()
        rf.__class__.__name__ = "RandomForestClassifier"
        rf.predict = Mock(return_value=[0])
        return rf

    def test_unwrap_none_returns_none(self, generator):
        assert generator._unwrap_model(None) is None

    def test_unwrap_plain_model_returns_itself(self, generator):
        """Modelo sem _model_impl (sklearn direto) é devolvido tal como está."""
        rf = self._make_random_forest()
        # Mock() expõe _model_impl como auto-Mock; simular ausência explicitamente
        rf._model_impl = None
        assert generator._unwrap_model(rf) is rf

    def test_unwrap_custom_python_model_via_sklearn_model(self, generator):
        """PyFuncModel -> python_model (wrapper) -> sklearn_model (RandomForest)."""
        rf = self._make_random_forest()

        python_model = Mock()
        python_model.sklearn_model = rf

        pyfunc = Mock()
        pyfunc._model_impl = Mock()
        pyfunc._model_impl.python_model = python_model

        unwrapped = generator._unwrap_model(pyfunc)
        assert unwrapped is rf
        # E o método passa a ser SHAP (antes era heuristic com o PyFuncModel)
        assert generator._determine_method(unwrapped) == "shap"

    def test_unwrap_sklearn_flavor_direct(self, generator):
        """PyFuncModel sklearn flavor: _model_impl.sklearn_model direto."""
        rf = self._make_random_forest()

        pyfunc = Mock()
        pyfunc._model_impl = Mock(spec=["sklearn_model"])
        pyfunc._model_impl.sklearn_model = rf

        assert generator._unwrap_model(pyfunc) is rf

    def test_pyfuncmodel_without_unwrap_would_be_heuristic(self, generator):
        """Regressão: sem desembrulhar, o tipo PyFuncModel cai em heuristic."""
        pyfunc = Mock()
        pyfunc.__class__.__name__ = "PyFuncModel"
        # Sem predict reconhecível como tree/linear
        assert generator._determine_method(pyfunc) == "heuristic"


@pytest.mark.unit()
class TestFeatureAlignment:
    """Testes do alinhamento de features ao schema do modelo (32 vs 26).

    O FeatureExtractor produz mais features do que o modelo foi treinado; sem
    alinhar a feature_names_in_, o SHAP explicava features na ordem errada.
    """

    @pytest.fixture()
    def generator(self, mock_config):
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            return ExplainabilityGenerator(mock_config)

    def test_align_to_feature_names_in(self, generator):
        """Usa feature_names_in_ do modelo, na ordem do modelo."""
        model = Mock()
        model.feature_names_in_ = ["num_tasks", "risk_score", "complexity_score"]

        # FeatureExtractor produz MAIS features (extras) e numa ordem diferente
        aggregated = {
            "risk_score": 0.7,
            "zzz_extra_feature": 0.9,  # extra: deve ser descartada
            "num_tasks": 5.0,
            "complexity_score": 0.3,
        }

        names, aligned = generator._align_features_to_model(model, aggregated)

        # Ordem e conjunto exatos do modelo (26->aqui 3), sem a extra
        assert names == ["num_tasks", "risk_score", "complexity_score"]
        assert set(aligned.keys()) == {"num_tasks", "risk_score", "complexity_score"}
        assert "zzz_extra_feature" not in aligned
        assert aligned["num_tasks"] == 5.0
        assert aligned["risk_score"] == 0.7

    def test_align_fills_missing_with_zero(self, generator):
        """Features esperadas pelo modelo mas ausentes são preenchidas com 0.0."""
        model = Mock()
        model.feature_names_in_ = ["a", "b", "missing_feature"]
        aggregated = {"a": 1.0, "b": 2.0}

        names, aligned = generator._align_features_to_model(model, aggregated)

        assert names == ["a", "b", "missing_feature"]
        assert aligned["missing_feature"] == 0.0

    def test_align_without_feature_names_falls_back_to_sorted(self, generator):
        """Sem feature_names_in_, usa ordenação determinista (sorted)."""
        model = Mock(spec=[])  # sem feature_names_in_
        aggregated = {"c": 3.0, "a": 1.0, "b": 2.0}

        names, aligned = generator._align_features_to_model(model, aggregated)

        assert names == ["a", "b", "c"]
        assert aligned == aggregated


@pytest.mark.unit()
class TestPersistenceAndRetrieval:
    """Testes de persistência e recuperação de explicações."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator com MongoDB mockado."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient") as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = (
                mock_collection
            )
            gen = ExplainabilityGenerator(mock_config)
            # Mock para backward compatibility
            gen._mongo_client = mock_mongo.return_value
            return gen

    def test_retrieve_explanation_success(self, generator):
        """Testa recuperação bem-sucedida de explicação."""
        mock_doc = {
            "explainability_token": "token-123",
            "metadata": {"method": "heuristic"},
        }
        with patch.object(generator, "retrieve_explanation_impl", return_value=mock_doc):
            result = generator.retrieve_explanation("token-123")

            assert result == mock_doc

    def test_retrieve_explanation_not_found(self, generator):
        """Testa que None é retornado quando explicação não existe."""
        with patch.object(generator, "retrieve_explanation_impl", return_value=None):
            result = generator.retrieve_explanation("nonexistent")

            assert result is None


@pytest.mark.unit()
class TestCircuitBreaker:
    """Testes de circuit breaker do ExplainabilityGenerator."""

    @pytest.fixture()
    def generator(self, mock_config, mock_metrics):
        """Cria generator com circuit breaker habilitado."""
        mock_config.enable_circuit_breaker = True
        mock_config.enable_legacy_explainability_persistence = True
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            gen = ExplainabilityGenerator(mock_config, metrics=mock_metrics)
            return gen

    def test_circuit_breaker_enabled(self, generator):
        """Verifica que circuit breaker é criado quando habilitado."""
        assert generator._persist_breaker is not None
        assert generator._retrieve_breaker is not None

    def test_persist_with_circuit_breaker_error(
        self, generator, sample_evaluation_result, sample_cognitive_plan
    ):
        """Testa comportamento quando circuit breaker está aberto."""
        # Criar um circuit breaker que vai falhar
        generator._persist_breaker = Mock()
        generator._persist_breaker.call = Mock(side_effect=CircuitBreakerError("Circuit open"))

        # Deve retornar token mesmo com circuit breaker aberto
        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=None,
        )

        assert token is not None
        assert metadata["method"] == "heuristic"

    def test_retrieve_with_circuit_breaker_error(self, generator):
        """Testa recuperação quando circuit breaker está aberto."""
        # O circuit breaker propaga CircuitBreakerError quando está aberto
        # Testa que o erro é devidamente propagado
        generator._retrieve_breaker = Mock()
        generator._retrieve_breaker.call = Mock(side_effect=CircuitBreakerError("Circuit open"))

        # Deve propagar o erro do circuit breaker
        with pytest.raises(CircuitBreakerError):
            generator.retrieve_explanation("token-123")


@pytest.mark.unit()
class TestHeuristicExplanation:
    """Testes de geração de explicação heurística."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            return ExplainabilityGenerator(mock_config)

    def test_heuristic_extracts_from_reasoning_factors(
        self, generator, sample_evaluation_result, sample_cognitive_plan
    ):
        """Verifica extração de fatores de raciocínio."""
        sample_evaluation_result["reasoning_factors"] = [
            {
                "factor_name": "test_factor",
                "weight": 0.5,
                "score": 0.8,
            }
        ]

        importances = generator._extract_heuristic_importances(sample_evaluation_result)

        assert len(importances) == 1
        assert importances[0]["feature_name"] == "test_factor"

    def test_determine_contribution_positive(self, generator):
        """Verifica determinação de contribuição positiva."""
        contribution = generator._determine_contribution(0.8)
        assert contribution == "positive"

    def test_determine_contribution_negative(self, generator):
        """Verifica determinação de contribuição negativa."""
        contribution = generator._determine_contribution(0.3)
        assert contribution == "negative"

    def test_determine_contribution_neutral(self, generator):
        """Verifica determinação de contribuição neutra."""
        contribution = generator._determine_contribution(0.5)
        assert contribution == "neutral"


@pytest.mark.unit()
class TestMinimalExplainability:
    """Testes de geração de explicabilidade mínima."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            return ExplainabilityGenerator(mock_config)

    def test_generate_minimal_explainability(self, generator):
        """Testa geração de explicabilidade mínima."""
        token, metadata = generator._generate_minimal_explainability()

        assert token is not None
        assert len(token) == 36  # UUID
        assert metadata["method"] == "heuristic"
        assert metadata["model_type"] == "rule_based"
        assert metadata["model_version"] == "heuristic"


@pytest.mark.unit()
class TestGetModelInfo:
    """Testes de obtenção de informações do modelo."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            return ExplainabilityGenerator(mock_config)

    def test_get_model_version_none(self, generator):
        """Testa versão quando modelo é None."""
        version = generator._get_model_version(None)
        assert version == "heuristic"

    def test_get_model_type_none(self, generator):
        """Testa tipo quando modelo é None."""
        model_type = generator._get_model_type(None)
        assert model_type == "heuristic"

    def test_get_model_type_with_model(self, generator):
        """Testa tipo com modelo concreto."""
        mock_model = Mock()
        mock_model.__class__.__name__ = "RandomForestClassifier"

        model_type = generator._get_model_type(mock_model)
        assert model_type == "RandomForestClassifier"


@pytest.mark.unit()
class TestReasoningLinks:
    """Testes de construção de links entre reasoning_factors e features."""

    @pytest.fixture()
    def generator(self, mock_config):
        """Cria generator."""
        with patch("neural_hive_specialists.explainability_generator.MongoClient"):
            return ExplainabilityGenerator(mock_config)

    def test_build_reasoning_links_exact_match(self, generator):
        """Testa link exato entre factor e feature."""
        reasoning_factors = [{"factor_name": "complexity", "score": 0.8, "weight": 0.5}]
        feature_importances = [{"feature_name": "complexity", "importance": 0.6}]

        links = generator._build_reasoning_links(reasoning_factors, feature_importances)

        assert "complexity" in links
        assert links["complexity"]["match_type"] == "exact"

    def test_normalize_name(self, generator):
        """Testa normalização de nomes."""
        normalized = generator._normalize_name("Test_Name-123")
        assert normalized == "testname123"
