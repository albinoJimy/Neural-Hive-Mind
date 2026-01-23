"""
Testes unitários para ModelComparator.

Testa comparação de modelos ML com análises estatísticas,
fairness e geração de relatórios.
"""

import pytest
import numpy as np
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from ml.model_comparator import ModelComparator, ComparisonResult


@pytest.fixture
def mock_config():
    """Config mock."""
    config = MagicMock()
    config.ml_validation_mae_threshold = 0.15
    config.ml_comparison_confidence_threshold = 0.7
    return config


@pytest.fixture
def mock_model_registry():
    """ModelRegistry mock."""
    registry = MagicMock()
    registry.load_model = AsyncMock()
    registry.client = MagicMock()
    return registry


@pytest.fixture
def mock_mongodb_client():
    """MongoDB client mock."""
    client = MagicMock()
    client.db = MagicMock()
    return client


@pytest.fixture
def mock_metrics():
    """Metrics mock."""
    metrics = MagicMock()
    metrics.ml_model_comparison_total = MagicMock()
    metrics.ml_model_comparison_duration_seconds = MagicMock()
    metrics.ml_model_comparison_confidence = MagicMock()
    return metrics


@pytest.fixture
def comparator(mock_config, mock_model_registry, mock_mongodb_client, mock_metrics):
    """ModelComparator instance."""
    return ModelComparator(
        config=mock_config,
        model_registry=mock_model_registry,
        mongodb_client=mock_mongodb_client,
        metrics=mock_metrics,
        logger=MagicMock()
    )


class TestComparisonResult:
    """Testes para dataclass ComparisonResult."""

    def test_default_values(self):
        """Verifica valores default."""
        result = ComparisonResult(
            model_name='test_model',
            current_version='1',
            candidate_version='2'
        )

        assert result.model_name == 'test_model'
        assert result.current_version == '1'
        assert result.candidate_version == '2'
        assert result.recommendation == 'manual_review'
        assert result.confidence_score == 0.5
        assert result.metrics_comparison == {}
        assert result.statistical_tests == {}
        assert result.fairness_analysis == {}
        assert result.visualizations == {}

    def test_to_dict(self):
        """Verifica conversão para dict."""
        result = ComparisonResult(
            model_name='test_model',
            current_version='1',
            candidate_version='2',
            recommendation='promote',
            confidence_score=0.85
        )

        data = result.to_dict()

        assert data['model_name'] == 'test_model'
        assert data['recommendation'] == 'promote'
        assert data['confidence_score'] == 0.85
        assert 'compared_at' in data
        assert isinstance(data['compared_at'], str)  # ISO format


class TestModelComparator:
    """Testes para ModelComparator."""

    @pytest.mark.asyncio
    async def test_compare_classification_models(self, comparator, mock_model_registry):
        """Testa comparação de modelos de classificação."""
        # Setup
        y_true = np.array([0, 1, 0, 1, 0, 1] * 100)
        current_preds = np.array([0, 1, 0, 0, 0, 1] * 100)  # ~83% accuracy
        candidate_preds = np.array([0, 1, 0, 1, 0, 1] * 100)  # 100% accuracy

        # Mock models
        current_model = MagicMock()
        candidate_model = MagicMock()
        current_model.predict = MagicMock(return_value=current_preds)
        candidate_model.predict = MagicMock(return_value=candidate_preds)

        mock_model_registry.load_model.side_effect = [current_model, candidate_model]

        # Test data
        test_data = {
            'X_test': np.random.rand(600, 10).tolist(),
            'y_test': y_true.tolist(),
            'metadata': {'task_type': ['api_call'] * 600}
        }

        # Execute
        result = await comparator.compare_models(
            model_name='test_classifier',
            current_version='1',
            candidate_version='2',
            test_data=test_data
        )

        # Assertions
        assert isinstance(result, ComparisonResult)
        assert result.model_name == 'test_classifier'
        assert result.recommendation in ['promote', 'reject', 'manual_review']
        assert 'accuracy' in result.metrics_comparison
        assert 'mcnemar_test' in result.statistical_tests

    @pytest.mark.asyncio
    async def test_compare_regression_models(self, comparator, mock_model_registry):
        """Testa comparação de modelos de regressão."""
        # Setup
        np.random.seed(42)
        y_true = np.random.rand(1000) * 1000
        current_preds = y_true + np.random.randn(1000) * 100  # MAE ~80
        candidate_preds = y_true + np.random.randn(1000) * 50  # MAE ~40

        # Mock models
        current_model = MagicMock()
        candidate_model = MagicMock()
        current_model.predict = MagicMock(return_value=current_preds)
        candidate_model.predict = MagicMock(return_value=candidate_preds)

        mock_model_registry.load_model.side_effect = [current_model, candidate_model]

        # Test data
        test_data = {
            'X_test': np.random.rand(1000, 10).tolist(),
            'y_test': y_true.tolist(),
            'metadata': {'task_type': ['computation'] * 1000}
        }

        # Execute
        result = await comparator.compare_models(
            model_name='duration_predictor',
            current_version='1',
            candidate_version='2',
            test_data=test_data
        )

        # Assertions
        assert result.recommendation in ['promote', 'manual_review']
        assert 'mae' in result.metrics_comparison
        assert result.metrics_comparison['mae']['candidate'] < result.metrics_comparison['mae']['current']
        assert 'paired_ttest' in result.statistical_tests

    @pytest.mark.asyncio
    async def test_model_load_failure(self, comparator, mock_model_registry):
        """Testa comportamento quando modelo não carrega."""
        mock_model_registry.load_model.return_value = None

        test_data = {
            'X_test': np.random.rand(100, 10).tolist(),
            'y_test': np.random.rand(100).tolist(),
            'metadata': {}
        }

        result = await comparator.compare_models(
            model_name='test_model',
            current_version='1',
            candidate_version='2',
            test_data=test_data
        )

        assert result.recommendation == 'reject'
        assert 'Falha ao carregar modelos' in result.recommendation_reason
        assert result.confidence_score == 0.0


class TestStatisticalTests:
    """Testes para testes estatísticos."""

    def test_mcnemar_test_significant_improvement(self, comparator):
        """Testa McNemar quando candidato é significativamente melhor."""
        y_true = np.array([1] * 100 + [0] * 100)
        current_preds = np.array([1] * 80 + [0] * 20 + [0] * 80 + [1] * 20)  # 80% acc
        candidate_preds = np.array([1] * 95 + [0] * 5 + [0] * 95 + [1] * 5)  # 95% acc

        result = comparator._mcnemar_test(y_true, current_preds, candidate_preds)

        assert result['significant'] is True
        assert result['p_value'] < 0.05
        assert 'candidato' in result['interpretation'].lower()

    def test_mcnemar_test_no_difference(self, comparator):
        """Testa McNemar quando não há diferença significativa."""
        y_true = np.array([1] * 100 + [0] * 100)
        current_preds = np.array([1] * 85 + [0] * 15 + [0] * 85 + [1] * 15)
        candidate_preds = np.array([1] * 84 + [0] * 16 + [0] * 84 + [1] * 16)

        result = comparator._mcnemar_test(y_true, current_preds, candidate_preds)

        assert result['significant'] is False
        assert 'não há diferença' in result['interpretation'].lower()

    def test_mcnemar_test_identical_predictions(self, comparator):
        """Testa McNemar quando predições são idênticas."""
        y_true = np.array([1, 0, 1, 0, 1])
        preds = np.array([1, 0, 1, 0, 0])

        result = comparator._mcnemar_test(y_true, preds, preds)

        assert result['significant'] is False
        assert result['p_value'] == 1.0
        assert 'idêntica' in result['interpretation'].lower()

    def test_paired_ttest_significant_improvement(self, comparator):
        """Testa paired t-test quando candidato tem erros menores."""
        np.random.seed(42)
        y_true = np.random.rand(1000) * 100
        current_preds = y_true + np.random.randn(1000) * 20  # High error
        candidate_preds = y_true + np.random.randn(1000) * 5  # Low error

        result = comparator._paired_ttest(y_true, current_preds, candidate_preds)

        assert result['significant'] is True
        assert result['mean_candidate_error'] < result['mean_current_error']
        assert 'candidato' in result['interpretation'].lower()

    def test_paired_ttest_no_difference(self, comparator):
        """Testa paired t-test quando não há diferença."""
        np.random.seed(42)
        y_true = np.random.rand(100)
        noise = np.random.randn(100) * 0.1
        current_preds = y_true + noise
        candidate_preds = y_true + noise + np.random.randn(100) * 0.001

        result = comparator._paired_ttest(y_true, current_preds, candidate_preds)

        assert result['significant'] is False


class TestFairnessAnalysis:
    """Testes para análise de fairness."""

    def test_fairness_analysis_with_groups(self, comparator):
        """Testa análise de fairness com grupos diferentes."""
        y_true = np.concatenate([
            np.ones(500) * 100,   # task_type: api_call
            np.ones(500) * 200    # task_type: computation
        ])

        # Current model: viés contra api_call (erro maior)
        current_preds = np.concatenate([
            np.ones(500) * 70,    # Erro: 30
            np.ones(500) * 190    # Erro: 10
        ])

        # Candidate model: mais justo
        candidate_preds = np.concatenate([
            np.ones(500) * 95,    # Erro: 5
            np.ones(500) * 195    # Erro: 5
        ])

        metadata = {
            'task_type': ['api_call'] * 500 + ['computation'] * 500
        }

        result = comparator._fairness_analysis(
            y_true, current_preds, candidate_preds, metadata
        )

        assert 'task_type' in result
        assert 'api_call' in result['task_type']['groups']
        assert 'computation' in result['task_type']['groups']
        assert result['task_type']['groups']['api_call']['improvement_pct'] > 0

    def test_fairness_analysis_empty_metadata(self, comparator):
        """Testa análise de fairness sem metadados."""
        y_true = np.random.rand(100)
        preds = y_true + np.random.randn(100) * 0.1

        result = comparator._fairness_analysis(y_true, preds, preds, {})

        assert result == {}

    def test_fairness_disparity_calculation(self, comparator):
        """Testa cálculo de ratio de disparidade."""
        y_true = np.concatenate([
            np.ones(100) * 100,
            np.ones(100) * 100
        ])

        # Predições com disparidade
        candidate_preds = np.concatenate([
            np.ones(100) * 80,    # MAE: 20
            np.ones(100) * 95     # MAE: 5
        ])

        metadata = {'domain': ['internal'] * 100 + ['external'] * 100}

        result = comparator._fairness_analysis(
            y_true, candidate_preds, candidate_preds, metadata
        )

        # Disparity ratio = 20/5 = 4.0
        assert result['domain']['disparity_ratio'] >= 4.0
        assert result['domain']['is_fair'] is False


class TestMetricsComparison:
    """Testes para comparação de métricas."""

    def test_regression_metrics(self, comparator):
        """Testa métricas de regressão."""
        y_true = np.array([100, 200, 300, 400, 500])
        current_preds = np.array([110, 190, 310, 390, 510])  # MAE: 10
        candidate_preds = np.array([105, 195, 305, 395, 505])  # MAE: 5

        result = comparator._compare_metrics(
            y_true, current_preds, candidate_preds, 'regression'
        )

        assert 'mae' in result
        assert result['mae']['improved'] is True
        assert result['mae']['candidate'] < result['mae']['current']
        assert 'rmse' in result
        assert 'r2' in result

    def test_classification_metrics(self, comparator):
        """Testa métricas de classificação."""
        y_true = np.array([0, 1, 0, 1, 0, 1, 0, 1])
        current_preds = np.array([0, 1, 1, 1, 0, 0, 0, 1])  # 75% acc
        candidate_preds = np.array([0, 1, 0, 1, 0, 1, 0, 1])  # 100% acc

        result = comparator._compare_metrics(
            y_true, current_preds, candidate_preds, 'classification'
        )

        assert 'accuracy' in result
        assert result['accuracy']['improved'] is True
        assert 'f1_score' in result


class TestRecommendation:
    """Testes para determinação de recomendação."""

    def test_promote_recommendation(self, comparator):
        """Testa recomendação de promoção."""
        result = ComparisonResult(
            model_name='test',
            current_version='1',
            candidate_version='2',
            metrics_comparison={
                'mae': {'current': 100, 'candidate': 80, 'diff_pct': -20, 'improved': True},
                'r2': {'current': 0.8, 'candidate': 0.9, 'diff_pct': 12.5, 'improved': True}
            },
            statistical_tests={
                'paired_ttest': {
                    'significant': True,
                    'interpretation': 'Candidato tem erros significativamente menores'
                }
            }
        )

        comparator._determine_recommendation(result)

        assert result.recommendation == 'promote'
        assert result.confidence_score >= 0.7

    def test_reject_recommendation(self, comparator):
        """Testa recomendação de rejeição."""
        result = ComparisonResult(
            model_name='test',
            current_version='1',
            candidate_version='2',
            metrics_comparison={
                'mae': {'current': 80, 'candidate': 120, 'diff_pct': 50, 'improved': False},
                'r2': {'current': 0.9, 'candidate': 0.7, 'diff_pct': -22, 'improved': False}
            },
            statistical_tests={
                'paired_ttest': {
                    'significant': True,
                    'interpretation': 'Modelo atual tem erros significativamente menores'
                }
            }
        )

        comparator._determine_recommendation(result)

        assert result.recommendation == 'reject'
        assert result.confidence_score < 0.5

    def test_manual_review_recommendation(self, comparator):
        """Testa recomendação de revisão manual."""
        result = ComparisonResult(
            model_name='test',
            current_version='1',
            candidate_version='2',
            metrics_comparison={
                'mae': {'current': 100, 'candidate': 98, 'diff_pct': -2, 'improved': True},
                'r2': {'current': 0.85, 'candidate': 0.84, 'diff_pct': -1, 'improved': False}
            },
            statistical_tests={
                'paired_ttest': {
                    'significant': False,
                    'interpretation': 'Não há diferença significativa nos erros'
                }
            }
        )

        comparator._determine_recommendation(result)

        assert result.recommendation == 'manual_review'


class TestHTMLReportGeneration:
    """Testes para geração de relatório HTML."""

    def test_generate_html_report(self, comparator):
        """Testa geração de relatório HTML."""
        result = ComparisonResult(
            model_name='test_model',
            current_version='1',
            candidate_version='2',
            metrics_comparison={
                'f1_score': {
                    'current': 0.80,
                    'candidate': 0.85,
                    'diff_pct': 6.25,
                    'improved': True
                }
            },
            statistical_tests={
                'mcnemar_test': {
                    'statistic': 10.5,
                    'p_value': 0.001,
                    'significant': True,
                    'interpretation': 'Candidato é significativamente melhor'
                }
            },
            fairness_analysis={},
            visualizations={},
            recommendation='promote',
            recommendation_reason='Candidato tem F1 significativamente melhor',
            confidence_score=0.85,
            test_samples_count=1000
        )

        html = comparator._generate_html_report(result)

        assert '<html>' in html
        assert 'test_model' in html
        assert 'promote' in html.lower()
        assert 'f1_score' in html.lower() or 'F1_SCORE' in html

    def test_inline_template_fallback(self, comparator):
        """Testa template inline quando arquivo não existe."""
        template = comparator._get_inline_template()

        assert '<!DOCTYPE html>' in template
        assert '{{ model_name }}' in template
        assert '{{ recommendation }}' in template


class TestModelTypeDetection:
    """Testes para detecção de tipo de modelo."""

    def test_detect_classification_by_name(self, comparator):
        """Testa detecção de classificação pelo nome."""
        y = np.array([0, 1, 0, 1])

        assert comparator._determine_model_type('anomaly_detector', y) == 'classification'
        assert comparator._determine_model_type('my_classifier', y) == 'classification'

    def test_detect_regression_by_name(self, comparator):
        """Testa detecção de regressão pelo nome."""
        y = np.array([100, 200, 300])

        assert comparator._determine_model_type('duration_predictor', y) == 'regression'
        assert comparator._determine_model_type('time_predictor', y) == 'regression'

    def test_detect_by_target_values(self, comparator):
        """Testa detecção pelo tipo de valores target."""
        # Classificação binária
        y_binary = np.array([0, 1, 0, 1, 0])
        assert comparator._determine_model_type('unknown_model', y_binary) == 'classification'

        # Regressão contínua
        y_continuous = np.array([1.5, 2.7, 3.1, 4.8, 5.2])
        assert comparator._determine_model_type('unknown_model', y_continuous) == 'regression'


class TestVisualizationGeneration:
    """Testes para geração de visualizações."""

    def test_generate_confusion_matrix(self, comparator):
        """Testa geração de confusion matrix."""
        y_true = np.array([0, 1, 0, 1, 0, 1])
        current_preds = np.array([0, 1, 1, 1, 0, 0])
        candidate_preds = np.array([0, 1, 0, 1, 0, 1])

        result = comparator._generate_confusion_matrix(y_true, current_preds, candidate_preds)

        # Deve retornar string base64
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 100  # Base64 de imagem deve ser longo

    def test_generate_error_distribution(self, comparator):
        """Testa geração de histograma de erros."""
        y_true = np.random.rand(100) * 100
        current_preds = y_true + np.random.randn(100) * 10
        candidate_preds = y_true + np.random.randn(100) * 5

        result = comparator._generate_error_distribution(y_true, current_preds, candidate_preds)

        assert result is not None
        assert isinstance(result, str)

    def test_generate_prediction_scatter(self, comparator):
        """Testa geração de scatter plot."""
        y_true = np.random.rand(100) * 100
        current_preds = y_true * 0.9
        candidate_preds = y_true * 0.95

        result = comparator._generate_prediction_scatter(y_true, current_preds, candidate_preds)

        assert result is not None
        assert isinstance(result, str)

    def test_generate_feature_importance_diff(self, comparator):
        """Testa geração de diff de feature importance."""
        # Mock models com feature_importances_
        current_model = MagicMock()
        candidate_model = MagicMock()
        current_model.feature_importances_ = np.array([0.3, 0.2, 0.5])
        candidate_model.feature_importances_ = np.array([0.25, 0.35, 0.4])

        result = comparator._generate_feature_importance_diff(
            current_model, candidate_model, ['feat_a', 'feat_b', 'feat_c']
        )

        assert result is not None
        assert isinstance(result, str)

    def test_feature_importance_diff_no_importances(self, comparator):
        """Testa quando modelos não têm feature_importances_."""
        current_model = MagicMock(spec=[])  # Sem feature_importances_
        candidate_model = MagicMock(spec=[])

        result = comparator._generate_feature_importance_diff(
            current_model, candidate_model, ['feat_a']
        )

        assert result is None
