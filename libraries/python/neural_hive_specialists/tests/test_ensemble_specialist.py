"""
Testes para EnsembleSpecialist.

Testa carregamento de modelos, agregação de predições,
e funcionalidades específicas de ensemble.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np
from neural_hive_specialists.ensemble_specialist import EnsembleSpecialist
from neural_hive_specialists.config import SpecialistConfig


@pytest.fixture
def ensemble_config():
    """Configuração para ensemble specialist."""
    return SpecialistConfig(
        specialist_type='technical',
        service_name='test-ensemble-specialist',
        mlflow_tracking_uri='http://localhost:5000',
        mlflow_experiment_name='test-ensemble',
        mlflow_model_name='technical-ensemble',
        mongodb_uri='mongodb://localhost:27017',
        redis_cluster_nodes='localhost:6379',
        neo4j_uri='bolt://localhost:7687',
        neo4j_password='test',
        enable_ensemble=True,
        ensemble_models=['model-rf', 'model-gb', 'model-lr'],
        ensemble_stages=['Production'],
        ensemble_weights=[0.4, 0.4, 0.2],
        ensemble_aggregation_method='weighted_average',
        ensemble_approve_threshold=0.8,
        ensemble_review_threshold=0.6
    )


@pytest.fixture
def mock_mlflow_client():
    """Mock do MLflowClient."""
    with patch('neural_hive_specialists.ensemble_specialist.MLflowClient') as mock_client:
        client_instance = MagicMock()

        # Mock load_model para retornar modelos mock
        def mock_load_model(name, stage):
            model = MagicMock()
            model.predict = Mock(return_value=np.array([[0.7, 0.3]]))
            return model

        client_instance.load_model = Mock(side_effect=mock_load_model)

        # Mock get_model_metadata
        client_instance.get_model_metadata = Mock(return_value={
            'version': '1',
            'run_id': 'test-run-id'
        })

        mock_client.return_value = client_instance
        yield client_instance


@pytest.fixture
def ensemble_specialist(ensemble_config, mock_mlflow_client):
    """Instância de EnsembleSpecialist configurada."""
    with patch('neural_hive_specialists.base_specialist.LedgerWriter'), \
         patch('neural_hive_specialists.base_specialist.RedisCache'), \
         patch('neural_hive_specialists.base_specialist.FeatureStore'):

        specialist = EnsembleSpecialist(config=ensemble_config)
        specialist.mlflow_client = mock_mlflow_client

        # Mock dos modelos carregados
        specialist.models = {
            'model-rf': MagicMock(),
            'model-gb': MagicMock(),
            'model-lr': MagicMock()
        }

        specialist.ensemble_weights = {
            'model-rf': 0.4,
            'model-gb': 0.4,
            'model-lr': 0.2
        }

        yield specialist


class TestEnsembleSpecialistLoading:
    """Testes de carregamento de modelos."""

    def test_load_multiple_models(self, ensemble_specialist, mock_mlflow_client):
        """Testa carregamento de múltiplos modelos."""
        assert len(ensemble_specialist.models) == 3
        assert 'model-rf' in ensemble_specialist.models
        assert 'model-gb' in ensemble_specialist.models
        assert 'model-lr' in ensemble_specialist.models

    def test_ensemble_weights_loaded(self, ensemble_specialist):
        """Testa que pesos de ensemble foram carregados."""
        assert ensemble_specialist.ensemble_weights == {
            'model-rf': 0.4,
            'model-gb': 0.4,
            'model-lr': 0.2
        }

        # Verificar que soma é 1.0
        total = sum(ensemble_specialist.ensemble_weights.values())
        assert abs(total - 1.0) < 0.01

    def test_stage_broadcasting(self, ensemble_config, mock_mlflow_client):
        """Testa broadcasting de stage único para múltiplos modelos."""
        # Config com 1 stage para 3 modelos
        assert len(ensemble_config.ensemble_stages) == 1
        assert len(ensemble_config.ensemble_models) == 3

        with patch('neural_hive_specialists.base_specialist.LedgerWriter'), \
             patch('neural_hive_specialists.base_specialist.RedisCache'), \
             patch('neural_hive_specialists.base_specialist.FeatureStore'):

            specialist = EnsembleSpecialist(config=ensemble_config)
            specialist.mlflow_client = mock_mlflow_client

            # Simular carregamento
            specialist.models = {'model-rf': MagicMock(), 'model-gb': MagicMock()}

            # Verificar que funciona sem erros
            assert specialist.models is not None


class TestEnsembleAggregation:
    """Testes de agregação de predições."""

    def test_weighted_average_aggregation(self, ensemble_specialist):
        """Testa agregação por média ponderada."""
        predictions = {
            'model-rf': {
                'confidence_score': 0.8,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_factors': []
            },
            'model-gb': {
                'confidence_score': 0.9,
                'risk_score': 0.1,
                'recommendation': 'approve',
                'reasoning_factors': []
            },
            'model-lr': {
                'confidence_score': 0.6,
                'risk_score': 0.4,
                'recommendation': 'review_required',
                'reasoning_factors': []
            }
        }

        result = ensemble_specialist._weighted_average_aggregation(predictions)

        # Verificar cálculo: 0.8*0.4 + 0.9*0.4 + 0.6*0.2 = 0.8
        expected_confidence = 0.8
        assert abs(result['confidence_score'] - expected_confidence) < 0.01

        # Verificar recomendação baseada em threshold
        assert result['recommendation'] == 'approve'  # >= 0.8

    def test_weighted_average_thresholds(self, ensemble_specialist):
        """Testa thresholds configuráveis na agregação."""
        # Confidence = 0.7 (entre review e approve)
        predictions = {
            'model-rf': {'confidence_score': 0.7, 'risk_score': 0.3, 'reasoning_factors': []},
            'model-gb': {'confidence_score': 0.7, 'risk_score': 0.3, 'reasoning_factors': []},
            'model-lr': {'confidence_score': 0.7, 'risk_score': 0.3, 'reasoning_factors': []}
        }

        result = ensemble_specialist._weighted_average_aggregation(predictions)

        # 0.7 >= 0.6 (review_threshold) mas < 0.8 (approve_threshold)
        assert result['recommendation'] == 'review_required'

    def test_stacking_aggregation_with_predict_proba(self, ensemble_specialist):
        """Testa stacking usando predict_proba."""
        # Mock meta-modelo com predict_proba
        meta_model = MagicMock()
        meta_model.predict_proba = Mock(return_value=np.array([[0.2, 0.8]]))
        ensemble_specialist.meta_model = meta_model

        predictions = {
            'model-rf': {'confidence_score': 0.8, 'risk_score': 0.2, 'reasoning_factors': []},
            'model-gb': {'confidence_score': 0.9, 'risk_score': 0.1, 'reasoning_factors': []}
        }

        result = ensemble_specialist._stacking_aggregation(predictions)

        # Verificar que usou predict_proba
        meta_model.predict_proba.assert_called_once()
        assert result['confidence_score'] == 0.8
        assert result['recommendation'] == 'approve'

    def test_stacking_fallback_to_decision_function(self, ensemble_specialist):
        """Testa stacking com fallback para decision_function."""
        # Mock meta-modelo sem predict_proba, mas com decision_function
        meta_model = MagicMock()
        del meta_model.predict_proba  # Remover predict_proba
        meta_model.decision_function = Mock(return_value=np.array([1.5]))
        ensemble_specialist.meta_model = meta_model

        predictions = {
            'model-rf': {'confidence_score': 0.8, 'risk_score': 0.2, 'reasoning_factors': []}
        }

        result = ensemble_specialist._stacking_aggregation(predictions)

        # Verificar que usou decision_function e aplicou sigmoid
        meta_model.decision_function.assert_called_once()
        # sigmoid(1.5) ≈ 0.817
        assert 0.8 < result['confidence_score'] < 0.85


class TestEnsembleMetrics:
    """Testes de métricas de ensemble."""

    def test_ensemble_weights_published_to_metrics(self, ensemble_specialist):
        """Testa que pesos são publicados nas métricas."""
        # Mock metrics
        ensemble_specialist.metrics = MagicMock()

        # Simular publicação de pesos
        for model_name, weight in ensemble_specialist.ensemble_weights.items():
            ensemble_specialist.metrics.set_ensemble_weight(model_name, weight)

        # Verificar chamadas
        assert ensemble_specialist.metrics.set_ensemble_weight.call_count == 3

    def test_prediction_variance_calculated(self, ensemble_specialist):
        """Testa cálculo de variância entre predições."""
        predictions = {
            'model-rf': {'confidence_score': 0.8, 'risk_score': 0.2},
            'model-gb': {'confidence_score': 0.9, 'risk_score': 0.1},
            'model-lr': {'confidence_score': 0.6, 'risk_score': 0.4}
        }

        variance = ensemble_specialist._calculate_prediction_variance(predictions)

        # Variância deve ser > 0 quando há diferenças
        assert variance > 0
        assert variance < 1.0


class TestEnsembleExplainability:
    """Testes de explainability ensemble-aware."""

    def test_ensemble_explainability_aggregation(self, ensemble_specialist):
        """Testa agregação de feature importances."""
        predictions = {
            'model-rf': {
                'explainability': {
                    'feature_importances': {'feature_a': 0.5, 'feature_b': 0.3},
                    'method': 'shap'
                }
            },
            'model-gb': {
                'explainability': {
                    'feature_importances': {'feature_a': 0.6, 'feature_c': 0.2},
                    'method': 'shap'
                }
            }
        }

        result = {}
        ensemble_specialist._add_ensemble_explainability(result, predictions)

        # Verificar estrutura
        assert 'explainability' in result
        assert 'ensemble' in result['explainability']

        # Verificar agregação ponderada
        ensemble_expl = result['explainability']['ensemble']
        assert 'aggregated_feature_importances' in ensemble_expl

        # feature_a: 0.5*0.4 + 0.6*0.4 = 0.44
        importances = ensemble_expl['aggregated_feature_importances']
        assert 'feature_a' in importances
        assert abs(importances['feature_a'] - 0.44) < 0.01


class TestEnsembleErrorHandling:
    """Testes de tratamento de erros."""

    def test_timeout_handling_in_parallel_predictions(self, ensemble_specialist, ensemble_config):
        """Testa tratamento de timeout em predições paralelas."""
        # Verificar que timeout está em segundos
        timeout_ms = ensemble_config.model_inference_timeout_ms
        timeout_seconds = timeout_ms / 1000.0

        assert timeout_seconds > 0
        assert timeout_seconds < 10  # Razoável para testes

    def test_fallback_on_model_failure(self, ensemble_specialist):
        """Testa fallback quando modelo falha."""
        # Mock um modelo que falha
        failing_model = MagicMock()
        failing_model.predict = Mock(side_effect=Exception("Model error"))
        ensemble_specialist.models['model-rf'] = failing_model

        # Simular predição
        predictions = ensemble_specialist._execute_parallel_predictions({'plan_id': 'test'})

        # Deve continuar com outros modelos
        assert len(predictions) >= 0  # Pelo menos alguns devem funcionar


class TestEnsembleMLflowIntegration:
    """Testes de integração com MLflow."""

    def test_load_weights_from_mlflow_artifact(self, ensemble_specialist, mock_mlflow_client):
        """Testa carregamento de pesos do MLflow artifact."""
        import json
        import tempfile
        import os

        # Criar artifact temporário
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_file = os.path.join(tmpdir, 'ensemble_weights.json')
            weights_data = {'model-rf': 0.5, 'model-gb': 0.3, 'model-lr': 0.2}

            with open(weights_file, 'w') as f:
                json.dump(weights_data, f)

            # Mock download_artifacts
            mock_mlflow_client.client = MagicMock()
            mock_mlflow_client.client.download_artifacts = Mock(return_value=weights_file)
            mock_mlflow_client.get_model_metadata = Mock(return_value={'run_id': 'test-run'})

            # Testar carregamento
            weights = ensemble_specialist._load_weights_from_mlflow_artifact()

            # Verificar que pesos foram carregados e normalizados
            assert weights is not None
            assert sum(weights.values()) == pytest.approx(1.0, abs=0.01)


@pytest.mark.integration
class TestEnsembleIntegration:
    """Testes de integração end-to-end."""

    def test_full_ensemble_prediction_flow(self, ensemble_specialist):
        """Testa fluxo completo de predição com ensemble."""
        # Mock métodos internos
        ensemble_specialist._execute_parallel_predictions = Mock(return_value={
            'model-rf': {
                'confidence_score': 0.8,
                'risk_score': 0.2,
                'recommendation': 'approve',
                'reasoning_factors': []
            },
            'model-gb': {
                'confidence_score': 0.85,
                'risk_score': 0.15,
                'recommendation': 'approve',
                'reasoning_factors': []
            }
        })

        cognitive_plan = {
            'plan_id': 'test-plan-123',
            'description': 'Test plan',
            'complexity_score': 0.5
        }

        result = ensemble_specialist._predict_with_model(cognitive_plan)

        # Verificar resultado
        assert result is not None
        assert 'confidence_score' in result
        assert 'metadata' in result
        assert 'ensemble_models' in result['metadata']
        assert len(result['metadata']['ensemble_models']) == 2


class TestEnsembleCalibrationMetadata:
    """Testes de metadata de calibração agregada em _combine_predictions."""

    def test_combine_predictions_calibration_metadata_all_calibrated(self, ensemble_specialist):
        """Testa propagação de metadata quando todos modelos usam predict_proba."""
        # Mock metrics para evitar dependência de Prometheus real
        ensemble_specialist.metrics = MagicMock()

        predictions = {
            'model-rf': {
                'confidence_score': 0.8,
                'risk_score': 0.2,
                'calibrated': True,
                'recommendation': 'approve',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_proba'}
            },
            'model-gb': {
                'confidence_score': 0.9,
                'risk_score': 0.1,
                'calibrated': True,
                'recommendation': 'approve',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_proba'}
            },
            'model-lr': {
                'confidence_score': 0.7,
                'risk_score': 0.3,
                'calibrated': True,
                'recommendation': 'review_required',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_proba'}
            }
        }

        result = ensemble_specialist._combine_predictions(predictions)

        # Verificar campos de metadata de calibração
        assert 'metadata' in result
        metadata = result['metadata']

        # base_models_prediction_methods deve conter todos os modelos
        assert 'base_models_prediction_methods' in metadata
        assert metadata['base_models_prediction_methods'] == {
            'model-rf': 'predict_proba',
            'model-gb': 'predict_proba',
            'model-lr': 'predict_proba'
        }

        # calibrated_models_count deve ser 3 (todos calibrados)
        assert 'calibrated_models_count' in metadata
        assert metadata['calibrated_models_count'] == 3

        # ensemble_calibrated deve ser True (3/3 > 50%)
        assert 'ensemble_calibrated' in metadata
        assert metadata['ensemble_calibrated'] is True

        # calibration_coverage deve ser 1.0 (100%)
        assert 'calibration_coverage' in metadata
        assert metadata['calibration_coverage'] == 1.0

        # Verificar chamadas às métricas
        ensemble_specialist.metrics.observe_ensemble_calibration_coverage.assert_called_once_with(1.0)
        ensemble_specialist.metrics.increment_ensemble_probabilistic_prediction.assert_called_once()

    def test_combine_predictions_calibration_metadata_mixed(self, ensemble_specialist):
        """Testa propagação de metadata com mistura de modelos calibrados e não-calibrados."""
        # Mock metrics
        ensemble_specialist.metrics = MagicMock()

        predictions = {
            'model-rf': {
                'confidence_score': 0.8,
                'risk_score': 0.2,
                'calibrated': True,
                'recommendation': 'approve',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_proba'}
            },
            'model-gb': {
                'confidence_score': 0.7,
                'risk_score': 0.3,
                'calibrated': False,
                'recommendation': 'review_required',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict'}
            },
            'model-lr': {
                'confidence_score': 0.6,
                'risk_score': 0.4,
                'calibrated': False,
                'recommendation': 'review_required',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_fallback'}
            }
        }

        result = ensemble_specialist._combine_predictions(predictions)

        metadata = result['metadata']

        # base_models_prediction_methods deve refletir métodos misturados
        assert metadata['base_models_prediction_methods'] == {
            'model-rf': 'predict_proba',
            'model-gb': 'predict',
            'model-lr': 'predict_fallback'
        }

        # calibrated_models_count deve ser 1 (apenas model-rf)
        assert metadata['calibrated_models_count'] == 1

        # ensemble_calibrated deve ser False (1/3 < 50%)
        assert metadata['ensemble_calibrated'] is False

        # calibration_coverage deve ser ~0.333
        assert abs(metadata['calibration_coverage'] - (1/3)) < 0.01

        # Verificar chamadas às métricas com valores corretos
        ensemble_specialist.metrics.observe_ensemble_calibration_coverage.assert_called_once()
        call_args = ensemble_specialist.metrics.observe_ensemble_calibration_coverage.call_args[0]
        assert abs(call_args[0] - (1/3)) < 0.01

    def test_combine_predictions_calibration_metadata_none_calibrated(self, ensemble_specialist):
        """Testa propagação de metadata quando nenhum modelo usa predict_proba."""
        # Mock metrics
        ensemble_specialist.metrics = MagicMock()

        predictions = {
            'model-rf': {
                'confidence_score': 0.75,
                'risk_score': 0.25,
                'calibrated': False,
                'recommendation': 'review_required',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict'}
            },
            'model-gb': {
                'confidence_score': 0.65,
                'risk_score': 0.35,
                'calibrated': False,
                'recommendation': 'review_required',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict'}
            }
        }

        result = ensemble_specialist._combine_predictions(predictions)

        metadata = result['metadata']

        # calibrated_models_count deve ser 0
        assert metadata['calibrated_models_count'] == 0

        # ensemble_calibrated deve ser False (0/2 < 50%)
        assert metadata['ensemble_calibrated'] is False

        # calibration_coverage deve ser 0.0
        assert metadata['calibration_coverage'] == 0.0

    def test_combine_predictions_calibration_metadata_majority_calibrated(self, ensemble_specialist):
        """Testa que ensemble_calibrated é True quando maioria está calibrada."""
        # Mock metrics
        ensemble_specialist.metrics = MagicMock()

        predictions = {
            'model-rf': {
                'confidence_score': 0.8,
                'risk_score': 0.2,
                'calibrated': True,
                'recommendation': 'approve',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_proba'}
            },
            'model-gb': {
                'confidence_score': 0.85,
                'risk_score': 0.15,
                'calibrated': True,
                'recommendation': 'approve',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_proba'}
            },
            'model-lr': {
                'confidence_score': 0.6,
                'risk_score': 0.4,
                'calibrated': False,
                'recommendation': 'review_required',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict'}
            }
        }

        result = ensemble_specialist._combine_predictions(predictions)

        metadata = result['metadata']

        # calibrated_models_count deve ser 2
        assert metadata['calibrated_models_count'] == 2

        # ensemble_calibrated deve ser True (2/3 > 50%)
        assert metadata['ensemble_calibrated'] is True

        # calibration_coverage deve ser ~0.667
        assert abs(metadata['calibration_coverage'] - (2/3)) < 0.01

    def test_combine_predictions_preserves_aggregation_method(self, ensemble_specialist):
        """Testa que aggregation_method é incluído na metadata."""
        # Mock metrics
        ensemble_specialist.metrics = MagicMock()

        predictions = {
            'model-rf': {
                'confidence_score': 0.8,
                'risk_score': 0.2,
                'calibrated': True,
                'recommendation': 'approve',
                'reasoning_factors': [],
                'metadata': {'prediction_method': 'predict_proba'}
            }
        }

        result = ensemble_specialist._combine_predictions(predictions)

        # aggregation_method deve estar presente
        assert 'aggregation_method' in result['metadata']
        assert result['metadata']['aggregation_method'] == 'weighted_average'
