"""
Testes unitários para ExplainabilityGenerator.

Cobertura: generate com/sem modelo, determinação de método (shap/lime/heuristic),
feature importances, persistência/recuperação, circuit breaker.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pymongo.errors import PyMongoError
from circuitbreaker import CircuitBreakerError

from neural_hive_specialists.explainability_generator import ExplainabilityGenerator


@pytest.mark.unit
class TestExplainabilityGeneratorInitialization:
    """Testes de inicialização do ExplainabilityGenerator."""

    def test_initialization_success(self, mock_config, mock_metrics):
        """Testa inicialização bem-sucedida."""
        with patch('neural_hive_specialists.explainability_generator.MongoClient'):
            gen = ExplainabilityGenerator(mock_config, metrics=mock_metrics)

            assert gen.config == mock_config
            assert gen._metrics == mock_metrics

    def test_initialization_creates_collection(self, mock_config):
        """Verifica criação de collection."""
        with patch('neural_hive_specialists.explainability_generator.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            gen = ExplainabilityGenerator(mock_config)

            assert gen._collection is not None


@pytest.mark.unit
class TestGenerateWithModel:
    """Testes de geração de explicabilidade com modelo."""

    @pytest.fixture
    def generator(self, mock_config):
        """Cria generator com MongoDB mockado."""
        with patch('neural_hive_specialists.explainability_generator.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            gen = ExplainabilityGenerator(mock_config)
            gen._collection = mock_collection
            return gen

    def test_generate_with_shap_model(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Testa geração com modelo usando SHAP."""
        mock_model = Mock()
        mock_model.predict = Mock(return_value=[0.85])

        generator._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        with patch('neural_hive_specialists.explainability_generator.shap') as mock_shap:
            mock_explainer = MagicMock()
            mock_shap_values = MagicMock()
            mock_shap_values.values = [[0.1, 0.2, 0.3]]
            mock_explainer.return_value = mock_shap_values
            mock_shap.Explainer = Mock(return_value=mock_explainer)

            token, metadata = generator.generate(
                evaluation_result=sample_evaluation_result,
                cognitive_plan=sample_cognitive_plan,
                model=mock_model
            )

            assert token is not None
            assert len(token) == 36  # UUID
            assert 'method' in metadata
            assert metadata['method'] == 'shap'
            assert 'feature_importances' in metadata

    def test_generate_with_lime_model(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Testa geração com modelo usando LIME."""
        mock_model = Mock()
        mock_model.predict_proba = Mock(return_value=[[0.15, 0.85]])

        generator._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        # SHAP falha, deve usar LIME
        with patch('neural_hive_specialists.explainability_generator.shap', side_effect=Exception("SHAP failed")):
            with patch('neural_hive_specialists.explainability_generator.lime') as mock_lime:
                mock_explainer = MagicMock()
                mock_exp = MagicMock()
                mock_exp.as_list = Mock(return_value=[('feature1', 0.5), ('feature2', 0.3)])
                mock_explainer.explain_instance = Mock(return_value=mock_exp)
                mock_lime.LimeTabularExplainer = Mock(return_value=mock_explainer)

                token, metadata = generator.generate(
                    evaluation_result=sample_evaluation_result,
                    cognitive_plan=sample_cognitive_plan,
                    model=mock_model
                )

                assert metadata['method'] == 'lime'

    def test_generate_persists_explanation(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Verifica que explicação é persistida."""
        mock_model = Mock()
        generator._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        with patch('neural_hive_specialists.explainability_generator.shap') as mock_shap:
            mock_shap.Explainer = Mock(side_effect=Exception("Use heuristic"))

            token, metadata = generator.generate(
                evaluation_result=sample_evaluation_result,
                cognitive_plan=sample_cognitive_plan,
                model=mock_model
            )

            generator._collection.insert_one.assert_called_once()
            call_args = generator._collection.insert_one.call_args[0][0]
            assert call_args['explainability_token'] == token


@pytest.mark.unit
class TestGenerateWithoutModel:
    """Testes de geração heurística sem modelo."""

    @pytest.fixture
    def generator(self, mock_config):
        """Cria generator com MongoDB mockado."""
        with patch('neural_hive_specialists.explainability_generator.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            gen = ExplainabilityGenerator(mock_config)
            gen._collection = mock_collection
            return gen

    def test_generate_without_model_uses_heuristic(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Testa que método heurístico é usado sem modelo."""
        generator._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=None
        )

        assert metadata['method'] == 'heuristic'
        assert 'reasoning_factors' in metadata
        assert 'task_complexity' in metadata

    def test_generate_extracts_feature_importances(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Verifica extração de feature importances dos reasoning factors."""
        sample_evaluation_result['reasoning_factors'] = [
            {'factor': 'complexity', 'weight': 0.5, 'score': 0.9, 'contribution': 'positive'},
            {'factor': 'risk', 'weight': 0.3, 'score': 0.2, 'contribution': 'negative'}
        ]

        generator._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=None
        )

        assert 'feature_importances' in metadata
        importances = metadata['feature_importances']
        assert 'complexity' in importances
        assert 'risk' in importances


@pytest.mark.unit
class TestMethodDetermination:
    """Testes de determinação do método de explicabilidade."""

    @pytest.fixture
    def generator(self, mock_config):
        """Cria generator."""
        with patch('neural_hive_specialists.explainability_generator.MongoClient'):
            return ExplainabilityGenerator(mock_config)

    def test_determine_method_no_model(self, generator):
        """Sem modelo, deve retornar heuristic."""
        method = generator._determine_explainability_method(model=None)
        assert method == 'heuristic'

    def test_determine_method_with_model_shap_available(self, generator):
        """Com modelo e SHAP disponível, deve retornar shap."""
        mock_model = Mock()

        with patch('neural_hive_specialists.explainability_generator.shap'):
            method = generator._determine_explainability_method(model=mock_model)
            assert method == 'shap'

    def test_determine_method_fallback_to_lime(self, generator):
        """Se SHAP falhar, deve tentar LIME."""
        mock_model = Mock()

        with patch('neural_hive_specialists.explainability_generator.shap', side_effect=ImportError):
            with patch('neural_hive_specialists.explainability_generator.lime'):
                method = generator._determine_explainability_method(model=mock_model)
                assert method == 'lime'

    def test_determine_method_fallback_to_heuristic(self, generator):
        """Se ambos falharem, deve usar heuristic."""
        mock_model = Mock()

        with patch('neural_hive_specialists.explainability_generator.shap', side_effect=ImportError):
            with patch('neural_hive_specialists.explainability_generator.lime', side_effect=ImportError):
                method = generator._determine_explainability_method(model=mock_model)
                assert method == 'heuristic'


@pytest.mark.unit
class TestPersistenceAndRetrieval:
    """Testes de persistência e recuperação de explicações."""

    @pytest.fixture
    def generator(self, mock_config):
        """Cria generator com MongoDB mockado."""
        with patch('neural_hive_specialists.explainability_generator.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            gen = ExplainabilityGenerator(mock_config)
            gen._collection = mock_collection
            return gen

    def test_get_explanation_success(self, generator):
        """Testa recuperação bem-sucedida de explicação."""
        mock_doc = {
            'explainability_token': 'token-123',
            'method': 'shap',
            'feature_importances': {'complexity': 0.5}
        }
        generator._collection.find_one = MagicMock(return_value=mock_doc)

        result = generator.get_explanation('token-123')

        assert result == mock_doc
        generator._collection.find_one.assert_called_once_with({'explainability_token': 'token-123'})

    def test_get_explanation_not_found(self, generator):
        """Testa que None é retornado quando explicação não existe."""
        generator._collection.find_one = MagicMock(return_value=None)

        result = generator.get_explanation('nonexistent')

        assert result is None

    def test_persist_explanation_success(self, generator):
        """Testa persistência bem-sucedida."""
        generator._collection.insert_one = MagicMock(return_value=MagicMock(acknowledged=True))

        explanation_data = {
            'explainability_token': 'token-123',
            'method': 'shap',
            'feature_importances': {}
        }

        generator._persist_explanation(explanation_data)

        generator._collection.insert_one.assert_called_once_with(explanation_data)


@pytest.mark.unit
class TestCircuitBreaker:
    """Testes de circuit breaker do ExplainabilityGenerator."""

    @pytest.fixture
    def generator(self, mock_config, mock_metrics):
        """Cria generator com circuit breaker habilitado."""
        mock_config.enable_circuit_breaker = True
        with patch('neural_hive_specialists.explainability_generator.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection
            gen = ExplainabilityGenerator(mock_config, metrics=mock_metrics)
            gen._collection = mock_collection
            return gen

    def test_circuit_breaker_enabled(self, generator):
        """Verifica que circuit breaker é criado quando habilitado."""
        assert generator._persist_explanation_breaker is not None
        assert generator._get_explanation_breaker is not None

    def test_persist_with_circuit_breaker_error(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Testa comportamento quando circuit breaker está aberto."""
        generator._persist_explanation_breaker = Mock()
        generator._persist_explanation_breaker.call = Mock(side_effect=CircuitBreakerError("Circuit open"))

        # Deve retornar token mesmo com circuit breaker aberto
        token, metadata = generator.generate(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan,
            model=None
        )

        assert token is not None
        assert metadata['method'] == 'heuristic'

    def test_get_explanation_with_circuit_breaker_error(self, generator):
        """Testa recuperação quando circuit breaker está aberto."""
        generator._get_explanation_breaker = Mock()
        generator._get_explanation_breaker.call = Mock(side_effect=CircuitBreakerError("Circuit open"))

        result = generator.get_explanation('token-123')

        # Deve retornar None quando não consegue recuperar
        assert result is None


@pytest.mark.unit
class TestHeuristicExplanation:
    """Testes de geração de explicação heurística."""

    @pytest.fixture
    def generator(self, mock_config):
        """Cria generator."""
        with patch('neural_hive_specialists.explainability_generator.MongoClient'):
            return ExplainabilityGenerator(mock_config)

    def test_heuristic_explanation_structure(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Verifica estrutura da explicação heurística."""
        explanation = generator._generate_heuristic_explanation(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan
        )

        assert 'method' in explanation
        assert explanation['method'] == 'heuristic'
        assert 'feature_importances' in explanation
        assert 'task_complexity' in explanation
        assert 'reasoning_factors' in explanation

    def test_heuristic_calculates_task_complexity(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Verifica cálculo de complexidade de tarefas."""
        explanation = generator._generate_heuristic_explanation(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan
        )

        assert 'task_complexity' in explanation
        task_complexity = explanation['task_complexity']
        assert 'total_tasks' in task_complexity
        assert task_complexity['total_tasks'] == len(sample_cognitive_plan['tasks'])

    def test_heuristic_extracts_reasoning_factors(self, generator, sample_evaluation_result, sample_cognitive_plan):
        """Verifica extração de fatores de raciocínio."""
        sample_evaluation_result['reasoning_factors'] = [
            {'factor': 'test_factor', 'weight': 0.5, 'score': 0.8, 'contribution': 'positive'}
        ]

        explanation = generator._generate_heuristic_explanation(
            evaluation_result=sample_evaluation_result,
            cognitive_plan=sample_cognitive_plan
        )

        assert 'reasoning_factors' in explanation
        assert len(explanation['reasoning_factors']) == 1
        assert explanation['reasoning_factors'][0]['factor'] == 'test_factor'
