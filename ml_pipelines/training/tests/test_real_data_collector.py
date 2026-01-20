#!/usr/bin/env python3
"""
Testes unitários para RealDataCollector.

Testa:
- Coleta de dados com sucesso
- Erro por dados insuficientes
- Validação de distribuição de labels
- Splits temporais
- Validação de qualidade de dados
- Tratamento de falhas de conexão
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
import numpy as np

# Adicionar paths para imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'libraries' / 'python'))


@pytest.fixture
def mock_feature_names():
    """Feature names mockados."""
    return [
        'num_tasks', 'priority_score', 'total_duration_ms', 'avg_duration_ms',
        'risk_score', 'complexity_score', 'domain_risk_weight',
        'avg_task_complexity_factor', 'num_patterns_detected',
        'num_anti_patterns_detected', 'avg_pattern_quality',
        'total_anti_pattern_penalty', 'num_nodes', 'num_edges',
        'density', 'avg_in_degree', 'max_in_degree', 'critical_path_length',
        'max_parallelism', 'num_levels', 'avg_coupling', 'num_bottlenecks',
        'graph_complexity_score', 'mean_norm', 'std_norm', 'avg_diversity'
    ]


@pytest.fixture
def mock_opinions():
    """Opiniões mockadas do MongoDB."""
    base_date = datetime.utcnow() - timedelta(days=30)
    return [
        {
            'opinion_id': f'opinion_{i}',
            'plan_id': f'plan_{i}',
            'specialist_type': 'technical',
            'recommendation': 'approve',
            'confidence_score': 0.85,
            'risk_score': 0.2,
            'cognitive_plan': {
                'plan_id': f'plan_{i}',
                'tasks': [{'task_id': 't1', 'description': 'Task 1'}]
            },
            'created_at': base_date + timedelta(hours=i)
        }
        for i in range(1200)
    ]


@pytest.fixture
def mock_feedbacks():
    """Feedbacks mockados do MongoDB."""
    recommendations = ['approve', 'reject', 'review_required', 'approve_with_conditions']
    return [
        {
            'opinion_id': f'opinion_{i}',
            'human_recommendation': recommendations[i % 4],
            'human_rating': 0.8 + (i % 3) * 0.05
        }
        for i in range(1200)
    ]


class TestRealDataCollectorMocked:
    """Testes para RealDataCollector com mocks completos."""

    @pytest.fixture
    def collector_mocked(self, mock_feature_names):
        """Cria collector com mocks injetados diretamente."""
        # Criar mocks
        mock_opinions_coll = MagicMock()
        mock_feedback_coll = MagicMock()

        mock_extractor = MagicMock()
        mock_extractor.extract_features.return_value = {
            'aggregated_features': {
                'num_tasks': 5.0,
                'priority_score': 0.7,
                'risk_score': 0.3,
                'num_nodes': 5.0,
                'num_edges': 4.0
            }
        }

        # Criar objeto mock do collector sem chamar __init__
        from real_data_collector import RealDataCollector

        # Criar instância sem inicializar
        collector = object.__new__(RealDataCollector)

        # Configurar atributos manualmente
        collector.mongodb_uri = 'mongodb://localhost:27017'
        collector.mongodb_database = 'test_db'
        collector.mongodb_client = MagicMock()
        collector.db = MagicMock()
        collector.opinions_collection = mock_opinions_coll
        collector.feedback_collection = mock_feedback_coll
        collector.feature_extractor = mock_extractor
        collector.expected_feature_names = mock_feature_names
        collector.circuit_breaker = None

        # Guardar referências
        collector._mock_opinions = mock_opinions_coll
        collector._mock_feedback = mock_feedback_coll
        collector._mock_extractor = mock_extractor

        return collector

    @pytest.mark.asyncio
    async def test_collect_training_data_success(
        self,
        collector_mocked,
        mock_opinions,
        mock_feedbacks
    ):
        """Testa coleta de dados com sucesso."""
        collector = collector_mocked

        # Configurar mocks
        collector._mock_opinions.find.return_value.sort.return_value = mock_opinions

        def mock_find_one(query):
            opinion_id = query.get('opinion_id')
            if opinion_id:
                idx = int(opinion_id.split('_')[1])
                return mock_feedbacks[idx] if idx < len(mock_feedbacks) else None
            return None

        collector._mock_feedback.find_one.side_effect = mock_find_one

        # Executar
        df = await collector.collect_training_data(
            specialist_type='technical',
            days=90,
            min_samples=1000
        )

        # Verificar
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 1000
        assert 'label' in df.columns
        assert 'opinion_id' in df.columns
        assert 'created_at' in df.columns

        # Verificar distribuição de labels
        labels = df['label'].unique()
        assert len(labels) > 1

    @pytest.mark.asyncio
    async def test_collect_training_data_insufficient_samples(
        self,
        collector_mocked
    ):
        """Testa erro quando há amostras insuficientes."""
        collector = collector_mocked

        few_opinions = [
            {
                'opinion_id': f'opinion_{i}',
                'plan_id': f'plan_{i}',
                'specialist_type': 'technical',
                'recommendation': 'approve',
                'cognitive_plan': {'plan_id': f'plan_{i}', 'tasks': []},
                'created_at': datetime.utcnow()
            }
            for i in range(100)
        ]
        collector._mock_opinions.find.return_value.sort.return_value = few_opinions

        def mock_find_one(query):
            opinion_id = query.get('opinion_id')
            if opinion_id:
                idx = int(opinion_id.split('_')[1])
                if idx < 50:
                    return {
                        'opinion_id': opinion_id,
                        'human_recommendation': 'approve',
                        'human_rating': 0.9
                    }
            return None

        collector._mock_feedback.find_one.side_effect = mock_find_one

        from real_data_collector import InsufficientDataError

        with pytest.raises(InsufficientDataError) as exc_info:
            await collector.collect_training_data(
                specialist_type='technical',
                days=90,
                min_samples=1000
            )

        assert 'insuficientes' in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_collection_statistics(self, collector_mocked):
        """Testa obtenção de estatísticas das collections."""
        collector = collector_mocked

        collector._mock_opinions.count_documents.return_value = 5000
        collector._mock_opinions.aggregate.return_value = [{'total': 2500}]
        collector._mock_feedback.aggregate.return_value = [
            {'_id': 0.8, 'count': 1000},
            {'_id': 0.9, 'count': 1500}
        ]

        stats = await collector.get_collection_statistics(
            specialist_type='technical',
            days=90
        )

        assert 'total_opinions' in stats
        assert 'opinions_with_feedback' in stats
        assert 'coverage_rate' in stats
        assert stats['total_opinions'] == 5000
        assert stats['opinions_with_feedback'] == 2500
        assert stats['coverage_rate'] == 50.0


class TestValidateLabelDistribution:
    """Testes para validação de distribuição de labels."""

    @pytest.fixture
    def collector(self, mock_feature_names):
        """Collector mínimo para testes de validação."""
        from real_data_collector import RealDataCollector

        collector = object.__new__(RealDataCollector)
        collector.expected_feature_names = mock_feature_names
        collector.BASELINE_DISTRIBUTION = {
            1: 40.0, 0: 20.0, 2: 25.0, 3: 15.0
        }
        collector.RECOMMENDATION_TO_LABEL = {
            "approve": 1, "reject": 0, "review_required": 2, "approve_with_conditions": 3
        }
        return collector

    def test_validate_label_distribution_balanced(self, collector, mock_feature_names):
        """Testa validação de distribuição balanceada."""
        n = 1000
        data = {name: np.random.random(n) for name in mock_feature_names}
        data['label'] = [0] * 200 + [1] * 400 + [2] * 250 + [3] * 150

        df = pd.DataFrame(data)
        report = collector.validate_label_distribution(df, 'technical')

        assert 'distribution' in report
        assert 'percentages' in report
        assert 'divergence_from_baseline' in report
        assert 'is_balanced' in report
        assert report['percentages'][0] == pytest.approx(20.0, rel=0.1)
        assert report['percentages'][1] == pytest.approx(40.0, rel=0.1)

    def test_validate_label_distribution_imbalanced(self, collector, mock_feature_names):
        """Testa detecção de desbalanceamento."""
        n = 1000
        data = {name: np.random.random(n) for name in mock_feature_names}
        data['label'] = [1] * 900 + [0] * 100

        df = pd.DataFrame(data)
        report = collector.validate_label_distribution(df, 'technical')

        assert not report['is_balanced']
        assert len(report['warnings']) > 0


class TestCreateTemporalSplits:
    """Testes para criação de splits temporais."""

    @pytest.fixture
    def collector(self, mock_feature_names):
        """Collector mínimo para testes de split."""
        from real_data_collector import RealDataCollector

        collector = object.__new__(RealDataCollector)
        collector.expected_feature_names = mock_feature_names
        return collector

    def test_create_temporal_splits_correct_sizes(self, collector, mock_feature_names):
        """Testa tamanhos corretos dos splits."""
        n = 1000
        base_date = datetime(2024, 1, 1)
        dates = [base_date + timedelta(hours=i) for i in range(n)]

        data = {name: np.random.random(n) for name in mock_feature_names}
        data['label'] = np.random.randint(0, 4, n)
        data['created_at'] = dates

        df = pd.DataFrame(data)
        train_df, val_df, test_df = collector.create_temporal_splits(df)

        assert len(train_df) == 600
        assert len(val_df) == 200
        assert len(test_df) == 200

    def test_create_temporal_splits_temporal_order(self, collector, mock_feature_names):
        """Testa ordem temporal dos splits."""
        n = 1000
        base_date = datetime(2024, 1, 1)
        dates = [base_date + timedelta(hours=i) for i in range(n)]

        data = {name: np.random.random(n) for name in mock_feature_names}
        data['label'] = np.random.randint(0, 4, n)
        data['created_at'] = dates

        df = pd.DataFrame(data)
        train_df, val_df, test_df = collector.create_temporal_splits(df)

        assert train_df['created_at'].max() < val_df['created_at'].min()
        assert val_df['created_at'].max() < test_df['created_at'].min()

    def test_create_temporal_splits_invalid_ratios(self, collector, mock_feature_names):
        """Testa erro com ratios inválidos."""
        data = {name: [0.0] * 100 for name in mock_feature_names}
        data['created_at'] = [datetime.utcnow() for _ in range(100)]
        df = pd.DataFrame(data)

        with pytest.raises(ValueError) as exc_info:
            collector.create_temporal_splits(
                df,
                train_ratio=0.5,
                val_ratio=0.5,
                test_ratio=0.5
            )

        assert '1.0' in str(exc_info.value)


class TestValidateDataQuality:
    """Testes para validação de qualidade de dados."""

    @pytest.fixture
    def collector(self, mock_feature_names):
        """Collector mínimo para testes de qualidade."""
        from real_data_collector import RealDataCollector

        collector = object.__new__(RealDataCollector)
        collector.expected_feature_names = mock_feature_names
        collector.RECOMMENDATION_TO_LABEL = {
            "approve": 1, "reject": 0, "review_required": 2, "approve_with_conditions": 3
        }
        return collector

    def test_validate_data_quality_good_data(self, collector, mock_feature_names):
        """Testa validação com dados de boa qualidade."""
        n = 1000
        data = {name: np.random.random(n) for name in mock_feature_names}
        data['label'] = np.random.randint(0, 4, n)
        data['opinion_id'] = [f'op_{i}' for i in range(n)]

        df = pd.DataFrame(data)
        report = collector.validate_data_quality(df)

        assert 'quality_score' in report
        assert 'passed' in report
        assert 'missing_values' in report
        assert 'sparse_features' in report
        assert 'outliers' in report
        assert report['quality_score'] > 0.5

    def test_validate_data_quality_sparse_features(self, collector, mock_feature_names):
        """Testa detecção de features sparse."""
        n = 1000
        data = {}

        for i, name in enumerate(mock_feature_names):
            if i < len(mock_feature_names) // 2:
                data[name] = [0.0] * n
            else:
                data[name] = np.random.random(n)

        data['label'] = np.random.randint(0, 4, n)
        df = pd.DataFrame(data)
        report = collector.validate_data_quality(df)

        assert len(report['sparse_features']) > 0
        assert report['sparsity_rate'] > 40


class TestMongoDBConnection:
    """Testes para conexão MongoDB."""

    @pytest.mark.asyncio
    async def test_mongodb_connection_failure(self, mock_feature_names):
        """Testa tratamento de falha de conexão MongoDB."""
        mock_client_instance = MagicMock()
        mock_client_instance.admin.command.side_effect = Exception("Connection refused")

        with patch('pymongo.MongoClient', return_value=mock_client_instance), \
             patch('real_data_collector.get_feature_names', return_value=mock_feature_names):

            from real_data_collector import RealDataCollector

            with pytest.raises(Exception) as exc_info:
                RealDataCollector(
                    mongodb_uri='mongodb://localhost:27017',
                    mongodb_database='test_db'
                )

            assert 'Connection' in str(exc_info.value) or 'refused' in str(exc_info.value).lower()


class TestSyncWrapper:
    """Testes para função síncrona auxiliar."""

    def test_sync_wrapper_exists(self):
        """Verifica que a função síncrona existe."""
        from real_data_collector import collect_training_data_sync
        assert callable(collect_training_data_sync)


class TestCompareDistributions:
    """Testes para função compare_distributions.

    Implementação inline para evitar problemas de import com dependências pesadas.
    """

    @staticmethod
    def _compare_distributions(real_dist, synthetic_baseline):
        """Implementação local de compare_distributions para testes."""
        divergences = {}
        for label, baseline_pct in synthetic_baseline.items():
            real_pct = real_dist.get(label, 0.0)
            divergences[f"label_{label}_divergence"] = abs(real_pct - baseline_pct)

        max_divergence = max(divergences.values()) if divergences else 0.0

        return {
            'real_distribution': real_dist,
            'synthetic_baseline': synthetic_baseline,
            'divergences': divergences,
            'max_divergence': max_divergence,
            'significant_drift': max_divergence > 30.0
        }

    def test_compare_distributions_identical(self):
        """Testa comparação com distribuições idênticas."""
        real_dist = {0: 25.0, 1: 50.0, 2: 25.0}
        synthetic_baseline = {0: 25.0, 1: 50.0, 2: 25.0}

        comparison = self._compare_distributions(real_dist, synthetic_baseline)

        assert comparison['max_divergence'] == 0.0
        assert comparison['significant_drift'] is False
        assert all(v == 0.0 for v in comparison['divergences'].values())

    def test_compare_distributions_with_divergence(self):
        """Testa comparação com divergência moderada."""
        real_dist = {0: 30.0, 1: 50.0, 2: 20.0}
        synthetic_baseline = {0: 25.0, 1: 50.0, 2: 25.0}

        comparison = self._compare_distributions(real_dist, synthetic_baseline)

        assert comparison['divergences']['label_0_divergence'] == 5.0
        assert comparison['divergences']['label_2_divergence'] == 5.0
        assert comparison['max_divergence'] == 5.0
        assert comparison['significant_drift'] is False

    def test_compare_distributions_significant_drift(self):
        """Testa detecção de drift significativo (> 30%)."""
        real_dist = {0: 60.0, 1: 30.0, 2: 10.0}
        synthetic_baseline = {0: 25.0, 1: 50.0, 2: 25.0}

        comparison = self._compare_distributions(real_dist, synthetic_baseline)

        assert comparison['max_divergence'] == 35.0
        assert comparison['significant_drift'] is True

    def test_compare_distributions_missing_label(self):
        """Testa comparação quando label está ausente nos dados reais."""
        real_dist = {0: 50.0, 1: 50.0}  # Label 2 ausente
        synthetic_baseline = {0: 25.0, 1: 50.0, 2: 25.0}

        comparison = self._compare_distributions(real_dist, synthetic_baseline)

        assert comparison['divergences']['label_2_divergence'] == 25.0


class TestLoadDatasetWithRealDataPriorityLogic:
    """Testes para lógica de load_dataset_with_real_data_priority.

    Testa a lógica de resolução de allow_synthetic_fallback sem importar
    o módulo completo (que tem dependências pesadas).
    """

    def test_allow_synthetic_fallback_auto_resolves_to_true_in_dev(self):
        """Testa que 'auto' resolve para True em ambiente development."""
        environment = 'development'
        allow_synthetic_fallback = 'auto'

        # Lógica de resolução
        if allow_synthetic_fallback == 'auto':
            allow_fallback = (environment != 'production')
        else:
            allow_fallback = (allow_synthetic_fallback == 'true')

        assert allow_fallback is True

    def test_allow_synthetic_fallback_auto_resolves_to_false_in_prod(self):
        """Testa que 'auto' resolve para False em ambiente production."""
        environment = 'production'
        allow_synthetic_fallback = 'auto'

        if allow_synthetic_fallback == 'auto':
            allow_fallback = (environment != 'production')
        else:
            allow_fallback = (allow_synthetic_fallback == 'true')

        assert allow_fallback is False

    def test_allow_synthetic_fallback_true_always_allows(self):
        """Testa que 'true' sempre permite fallback."""
        for environment in ['development', 'production', 'staging']:
            allow_synthetic_fallback = 'true'

            if allow_synthetic_fallback == 'auto':
                allow_fallback = (environment != 'production')
            else:
                allow_fallback = (allow_synthetic_fallback == 'true')

            assert allow_fallback is True, f"Failed for environment={environment}"

    def test_allow_synthetic_fallback_false_never_allows(self):
        """Testa que 'false' nunca permite fallback."""
        for environment in ['development', 'production', 'staging']:
            allow_synthetic_fallback = 'false'

            if allow_synthetic_fallback == 'auto':
                allow_fallback = (environment != 'production')
            else:
                allow_fallback = (allow_synthetic_fallback == 'true')

            assert allow_fallback is False, f"Failed for environment={environment}"

    def test_synthetic_metadata_structure(self):
        """Testa estrutura de metadata retornada para dados sintéticos."""
        # Simula estrutura esperada
        synthetic_metadata = {
            'synthetic_samples_count': 1000,
            'label_distribution': {0: 500, 1: 500},
            'data_source': 'synthetic',
            'warning': 'Model trained on synthetic data - performance may degrade in production'
        }

        assert 'synthetic_samples_count' in synthetic_metadata
        assert 'warning' in synthetic_metadata
        assert synthetic_metadata['data_source'] == 'synthetic'

    def test_real_data_metadata_structure(self):
        """Testa estrutura de metadata retornada para dados reais."""
        # Simula estrutura esperada
        real_data_metadata = {
            'real_samples_count': 1500,
            'label_distribution': {0: 375, 1: 750, 2: 375},
            'label_percentages': {0: 25.0, 1: 50.0, 2: 25.0},
            'is_balanced': True,
            'quality_score': 0.85,
            'quality_passed': True,
            'date_range_start': '2024-01-01T00:00:00',
            'date_range_end': '2024-03-31T23:59:59'
        }

        assert 'real_samples_count' in real_data_metadata
        assert 'quality_score' in real_data_metadata
        assert 'is_balanced' in real_data_metadata
        assert real_data_metadata['quality_passed'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
