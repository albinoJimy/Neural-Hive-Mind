#!/usr/bin/env python3
"""
Testes unitários para PreRetrainingValidator.

Testa validações de pré-requisitos antes do retraining:
- Contagem de amostras
- Distribuição de labels
- Qualidade de features
- Integridade temporal
- Comparação com baseline
"""

import os
import sys
import datetime
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Any, List

import pytest

# Adicionar paths para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ml_pipelines', 'training'))


class MockCollection:
    """Mock de collection MongoDB para testes."""

    def __init__(self, data: List[Dict[str, Any]] = None):
        self._data = data or []

    def aggregate(self, pipeline):
        """Mock de aggregation pipeline."""
        return self._data

    def count_documents(self, filter_query):
        """Mock de count_documents."""
        return len(self._data)

    def find(self, query=None, projection=None):
        """Mock de find."""
        return MockCursor(self._data)

    def find_one(self, query=None, **kwargs):
        """Mock de find_one."""
        return self._data[0] if self._data else None


class MockCursor:
    """Mock de cursor MongoDB."""

    def __init__(self, data):
        self._data = data

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n):
        self._data = self._data[:n]
        return self

    def __iter__(self):
        return iter(self._data)


class MockMongoClient:
    """Mock de MongoClient para testes."""

    def __init__(self, collections: Dict[str, MockCollection] = None):
        self._collections = collections or {}
        self.admin = MagicMock()
        self.admin.command = MagicMock(return_value={'ok': 1})

    def __getitem__(self, name):
        return MockDatabase(self._collections)

    def close(self):
        pass


class MockDatabase:
    """Mock de database MongoDB."""

    def __init__(self, collections: Dict[str, MockCollection]):
        self._collections = collections

    def __getitem__(self, name):
        return self._collections.get(name, MockCollection())


class TestPreRetrainingValidatorSampleCount:
    """Testes para verificação de contagem de amostras."""

    @patch('pre_retraining_validator.MongoClient')
    def test_check_sample_count_success(self, mock_mongo_class):
        """Testa sucesso quando há amostras suficientes."""
        from pre_retraining_validator import PreRetrainingValidator

        # Configurar mock para retornar contagem suficiente
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Aggregation retorna contagem
        mock_collection.aggregate.return_value = [{'total': 1500}]
        mock_collection.count_documents.return_value = 2000

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._check_sample_count(
            specialist_type='technical',
            days=90,
            min_samples=1000,
            min_feedback_rating=0.0
        )

        assert result['passed'] is True
        assert result['current'] == 1500
        assert result['required'] == 1000
        assert result['coverage_rate'] == 75.0

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    def test_check_sample_count_insufficient(self, mock_mongo_class):
        """Testa falha quando há amostras insuficientes."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Contagem insuficiente
        mock_collection.aggregate.return_value = [{'total': 500}]
        mock_collection.count_documents.return_value = 1000

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._check_sample_count(
            specialist_type='technical',
            days=90,
            min_samples=1000,
            min_feedback_rating=0.0
        )

        assert result['passed'] is False
        assert result['current'] == 500
        assert result['required'] == 1000

        validator.close()


class TestPreRetrainingValidatorLabelDistribution:
    """Testes para verificação de distribuição de labels."""

    @patch('pre_retraining_validator.MongoClient')
    def test_check_label_distribution_balanced(self, mock_mongo_class):
        """Testa distribuição balanceada de labels."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Distribuição balanceada
        mock_collection.aggregate.return_value = [
            {'_id': 'approve', 'count': 500},
            {'_id': 'reject', 'count': 250},
            {'_id': 'review_required', 'count': 250}
        ]

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._check_label_distribution(
            specialist_type='technical',
            days=90,
            min_feedback_rating=0.0
        )

        assert result['passed'] is True
        assert result['is_balanced'] is True
        assert len(result['underrepresented_classes']) == 0
        assert len(result['dominant_classes']) == 0
        assert result['percentages']['approve'] == 50.0
        assert result['percentages']['reject'] == 25.0

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    def test_check_label_distribution_underrepresented(self, mock_mongo_class):
        """Testa detecção de classes subrepresentadas."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Classe subrepresentada (< 5%)
        mock_collection.aggregate.return_value = [
            {'_id': 'approve', 'count': 900},
            {'_id': 'reject', 'count': 80},
            {'_id': 'review_required', 'count': 20}  # 2% - subrepresentada
        ]

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._check_label_distribution(
            specialist_type='technical',
            days=90,
            min_feedback_rating=0.0
        )

        assert result['passed'] is False
        assert result['is_balanced'] is False
        assert 'review_required' in result['underrepresented_classes']

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    def test_check_label_distribution_dominant(self, mock_mongo_class):
        """Testa detecção de classe dominante."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # Classe dominante (> 80%)
        mock_collection.aggregate.return_value = [
            {'_id': 'approve', 'count': 850},  # 85% - dominante
            {'_id': 'reject', 'count': 100},
            {'_id': 'review_required', 'count': 50}
        ]

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._check_label_distribution(
            specialist_type='technical',
            days=90,
            min_feedback_rating=0.0
        )

        assert result['passed'] is False
        assert 'approve' in result['dominant_classes']

        validator.close()


class TestPreRetrainingValidatorFeatureQuality:
    """Testes para verificação de qualidade de features."""

    @patch('pre_retraining_validator.MongoClient')
    def test_check_feature_quality_success(self, mock_mongo_class):
        """Testa sucesso quando qualidade de features é boa."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # 100 amostras com cognitive_plan válido
        samples = [
            {
                'opinion_id': f'op_{i}',
                'cognitive_plan': {'steps': [{'action': 'test'}]}
            }
            for i in range(100)
        ]
        mock_collection.aggregate.return_value = samples

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._check_feature_quality(
            specialist_type='technical',
            days=90,
            min_feedback_rating=0.0,
            sample_size=100
        )

        assert result['passed'] is True
        assert result['sample_size'] == 100
        assert result['missing_value_rate'] == 0.0

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    def test_check_feature_quality_high_missing(self, mock_mongo_class):
        """Testa falha quando taxa de valores ausentes é alta."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        # 10% sem cognitive_plan (acima do limite de 5%)
        samples = []
        for i in range(90):
            samples.append({
                'opinion_id': f'op_{i}',
                'cognitive_plan': {'steps': []}
            })
        for i in range(10):
            samples.append({
                'opinion_id': f'op_missing_{i}',
                'cognitive_plan': None  # Missing
            })

        mock_collection.aggregate.return_value = samples

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._check_feature_quality(
            specialist_type='technical',
            days=90,
            min_feedback_rating=0.0,
            sample_size=100
        )

        assert result['passed'] is False
        assert result['missing_value_rate'] == 0.1  # 10%

        validator.close()


class TestPreRetrainingValidatorTemporalIntegrity:
    """Testes para verificação de integridade temporal."""

    @patch('pre_retraining_validator.MongoClient')
    def test_validate_temporal_integrity_success(self, mock_mongo_class):
        """Testa sucesso quando dados temporais são válidos."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        now = datetime.datetime.utcnow()
        min_date = now - datetime.timedelta(days=30)
        max_date = now - datetime.timedelta(hours=1)

        mock_collection.aggregate.return_value = [{
            '_id': None,
            'min_date': min_date,
            'max_date': max_date
        }]

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._validate_temporal_integrity(
            specialist_type='technical',
            days=90
        )

        assert result['passed'] is True
        assert result['has_future_timestamps'] is False
        assert result['span_days'] >= 7

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    def test_validate_temporal_integrity_future_timestamps(self, mock_mongo_class):
        """Testa falha quando há timestamps no futuro."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        now = datetime.datetime.utcnow()
        min_date = now - datetime.timedelta(days=30)
        max_date = now + datetime.timedelta(days=1)  # Futuro

        mock_collection.aggregate.return_value = [{
            '_id': None,
            'min_date': min_date,
            'max_date': max_date
        }]

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._validate_temporal_integrity(
            specialist_type='technical',
            days=90
        )

        assert result['passed'] is False
        assert result['has_future_timestamps'] is True

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    def test_validate_temporal_integrity_short_span(self, mock_mongo_class):
        """Testa falha quando range de dados é muito curto."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        now = datetime.datetime.utcnow()
        min_date = now - datetime.timedelta(days=2)
        max_date = now - datetime.timedelta(hours=1)

        mock_collection.aggregate.return_value = [{
            '_id': None,
            'min_date': min_date,
            'max_date': max_date
        }]

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._validate_temporal_integrity(
            specialist_type='technical',
            days=90
        )

        assert result['passed'] is False
        assert result['span_days'] < 7

        validator.close()


class TestPreRetrainingValidatorBaselineComparison:
    """Testes para comparação com baseline MLflow."""

    @patch('pre_retraining_validator.MongoClient')
    def test_compare_with_baseline_no_mlflow(self, mock_mongo_class):
        """Testa quando MLflow não está disponível."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        with patch.dict('sys.modules', {'mlflow': None}):
            result = validator._compare_with_baseline(
                specialist_type='technical',
                current_distribution={'approve': 50.0, 'reject': 25.0}
            )

        # Deve retornar graciosamente quando MLflow não disponível
        assert result.get('comparison_available') is False or 'error' in result

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    @patch('mlflow.tracking.MlflowClient')
    def test_compare_with_baseline_no_production_model(self, mock_mlflow_client, mock_mongo_class):
        """Testa quando não há modelo Production no registry."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_db.__getitem__.return_value = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        # MLflow retorna lista vazia de versões
        mock_mlflow_client.return_value.search_model_versions.return_value = []

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        result = validator._compare_with_baseline(
            specialist_type='technical',
            current_distribution={'approve': 50.0, 'reject': 25.0}
        )

        assert result['comparison_available'] is False
        assert 'Production' in result.get('reason', '')

        validator.close()


class TestPreRetrainingValidatorFullValidation:
    """Testes de validação completa."""

    @patch('pre_retraining_validator.MongoClient')
    def test_validate_prerequisites_success(self, mock_mongo_class):
        """Testa validação completa com sucesso."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        now = datetime.datetime.utcnow()

        # Mock para diferentes chamadas de aggregate
        def aggregate_side_effect(pipeline):
            # Detectar qual pipeline está sendo chamado
            pipeline_str = str(pipeline)

            if '$count' in pipeline_str:
                return [{'total': 1500}]
            elif '$group' in pipeline_str and '_id' in pipeline_str:
                return [
                    {'_id': 'approve', 'count': 750},
                    {'_id': 'reject', 'count': 375},
                    {'_id': 'review_required', 'count': 375}
                ]
            elif '$sample' in pipeline_str:
                return [
                    {'opinion_id': f'op_{i}', 'cognitive_plan': {'steps': []}}
                    for i in range(100)
                ]
            elif 'min_date' in pipeline_str or '$min' in pipeline_str:
                return [{
                    '_id': None,
                    'min_date': now - datetime.timedelta(days=30),
                    'max_date': now - datetime.timedelta(hours=1)
                }]
            return []

        mock_collection.aggregate.side_effect = aggregate_side_effect
        mock_collection.count_documents.return_value = 2000

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        # Mock do _compare_with_baseline para não precisar de MLflow
        with patch.object(validator, '_compare_with_baseline') as mock_baseline:
            mock_baseline.return_value = {
                'comparison_available': False,
                'reason': 'Test mock'
            }

            result = validator.validate_prerequisites(
                specialist_type='technical',
                days=90,
                min_samples=1000,
                min_feedback_rating=0.0
            )

        assert result['passed'] is True
        assert result['recommendation'] == 'proceed'
        assert len(result['blocking_issues']) == 0

        validator.close()

    @patch('pre_retraining_validator.MongoClient')
    def test_validate_prerequisites_insufficient_samples(self, mock_mongo_class):
        """Testa validação com amostras insuficientes."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        now = datetime.datetime.utcnow()

        def aggregate_side_effect(pipeline):
            pipeline_str = str(pipeline)
            if '$count' in pipeline_str:
                return [{'total': 500}]  # Insuficiente
            elif '$group' in pipeline_str:
                return [{'_id': 'approve', 'count': 500}]
            elif '$sample' in pipeline_str:
                return [{'opinion_id': 'op_1', 'cognitive_plan': {}}]
            elif 'min_date' in pipeline_str:
                return [{
                    '_id': None,
                    'min_date': now - datetime.timedelta(days=30),
                    'max_date': now - datetime.timedelta(hours=1)
                }]
            return []

        mock_collection.aggregate.side_effect = aggregate_side_effect
        mock_collection.count_documents.return_value = 1000

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        with patch.object(validator, '_compare_with_baseline') as mock_baseline:
            mock_baseline.return_value = {'comparison_available': False}

            result = validator.validate_prerequisites(
                specialist_type='technical',
                days=90,
                min_samples=1000,
                min_feedback_rating=0.0
            )

        assert result['passed'] is False
        assert result['recommendation'] == 'wait_for_more_data'
        assert len(result['blocking_issues']) > 0

        validator.close()


class TestValidationFailedError:
    """Testes para a exceção ValidationFailedError."""

    def test_validation_failed_error_import(self):
        """Testa que ValidationFailedError pode ser importada."""
        from pre_retraining_validator import ValidationFailedError

        error = ValidationFailedError("Dados insuficientes")
        assert str(error) == "Dados insuficientes"

    def test_validation_failed_error_raised(self):
        """Testa que ValidationFailedError pode ser lançada."""
        from pre_retraining_validator import ValidationFailedError

        with pytest.raises(ValidationFailedError) as exc_info:
            raise ValidationFailedError("Teste de falha")

        assert "Teste de falha" in str(exc_info.value)


class TestValidationReportFormat:
    """Testes para formato do relatório de validação."""

    @patch('pre_retraining_validator.MongoClient')
    def test_validation_report_structure(self, mock_mongo_class):
        """Testa que relatório tem estrutura correta para MLflow."""
        from pre_retraining_validator import PreRetrainingValidator

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {'ok': 1}
        mock_db = MagicMock()
        mock_collection = MagicMock()

        now = datetime.datetime.utcnow()

        def aggregate_side_effect(pipeline):
            pipeline_str = str(pipeline)
            if '$count' in pipeline_str:
                return [{'total': 1500}]
            elif '$group' in pipeline_str:
                return [
                    {'_id': 'approve', 'count': 750},
                    {'_id': 'reject', 'count': 375},
                    {'_id': 'review_required', 'count': 375}
                ]
            elif '$sample' in pipeline_str:
                return [{'opinion_id': f'op_{i}', 'cognitive_plan': {}} for i in range(100)]
            elif 'min_date' in pipeline_str:
                return [{
                    '_id': None,
                    'min_date': now - datetime.timedelta(days=30),
                    'max_date': now - datetime.timedelta(hours=1)
                }]
            return []

        mock_collection.aggregate.side_effect = aggregate_side_effect
        mock_collection.count_documents.return_value = 2000

        mock_db.__getitem__.return_value = mock_collection
        mock_client.__getitem__.return_value = mock_db
        mock_mongo_class.return_value = mock_client

        validator = PreRetrainingValidator(
            mongodb_uri='mongodb://test:27017',
            mongodb_database='test_db'
        )

        with patch.object(validator, '_compare_with_baseline') as mock_baseline:
            mock_baseline.return_value = {'comparison_available': False}

            result = validator.validate_prerequisites(
                specialist_type='technical',
                days=90,
                min_samples=1000,
                min_feedback_rating=0.0
            )

        # Verificar campos obrigatórios
        assert 'validation_timestamp' in result
        assert 'specialist_type' in result
        assert 'passed' in result
        assert 'recommendation' in result
        assert 'checks' in result
        assert 'warnings' in result
        assert 'blocking_issues' in result
        assert 'recommendations' in result

        # Verificar sub-estrutura de checks
        checks = result['checks']
        assert 'sample_count' in checks
        assert 'label_distribution' in checks
        assert 'feature_quality' in checks
        assert 'temporal_integrity' in checks
        assert 'baseline_comparison' in checks

        # Verificar que recommendation é válida
        assert result['recommendation'] in ['proceed', 'wait_for_more_data', 'investigate_distribution']

        validator.close()
