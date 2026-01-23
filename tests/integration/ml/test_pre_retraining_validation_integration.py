# -*- coding: utf-8 -*-
"""
Testes de integração para validação de pré-retraining.

Testa o fluxo completo de validação antes do pipeline de treinamento,
incluindo integração com MongoDB e MLflow.
"""

import os
import sys
import datetime
import uuid
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

# Adicionar paths para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ml_pipelines', 'training'))


@pytest.fixture
def mongodb_test_data(mongodb_ml_client, event_loop) -> Dict[str, Any]:
    """
    Popula MongoDB com dados de teste para validação de pré-retraining.

    Cria opiniões com feedback para simular cenário realista.
    """
    import datetime

    np.random.seed(42)
    base_time = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    opinions = []
    feedbacks = []

    # Criar 1500 opiniões com distribuição balanceada
    recommendations = ['approve'] * 750 + ['reject'] * 375 + ['review_required'] * 375
    np.random.shuffle(recommendations)

    for i, rec in enumerate(recommendations):
        opinion_id = f"op_{uuid.uuid4().hex[:8]}"
        created_at = base_time + datetime.timedelta(hours=i)

        opinions.append({
            'opinion_id': opinion_id,
            'plan_id': f"plan_{i}",
            'specialist_type': 'technical',
            'recommendation': rec,
            'confidence_score': np.random.uniform(0.6, 0.95),
            'risk_score': np.random.uniform(0.1, 0.8),
            'cognitive_plan': {
                'steps': [
                    {'action': 'analyze', 'target': 'code'},
                    {'action': 'evaluate', 'target': 'risk'}
                ],
                'complexity_score': np.random.uniform(0.3, 0.9)
            },
            'created_at': created_at
        })

        feedbacks.append({
            'opinion_id': opinion_id,
            'specialist_type': 'technical',
            'human_recommendation': rec,
            'human_rating': np.random.uniform(0.6, 1.0),
            'submitted_at': created_at + datetime.timedelta(minutes=30)
        })

    async def insert():
        await mongodb_ml_client.db['specialist_opinions'].insert_many(opinions)
        await mongodb_ml_client.db['feedback'].insert_many(feedbacks)

    event_loop.run_until_complete(insert())

    return {
        'total_opinions': len(opinions),
        'total_feedbacks': len(feedbacks),
        'specialist_type': 'technical'
    }


@pytest.fixture
def mongodb_insufficient_data(mongodb_ml_client, event_loop) -> Dict[str, Any]:
    """
    Popula MongoDB com dados insuficientes para validação.
    """
    import datetime

    np.random.seed(42)
    base_time = datetime.datetime.utcnow() - datetime.timedelta(days=30)

    opinions = []
    feedbacks = []

    # Apenas 500 opiniões (abaixo do mínimo de 1000)
    for i in range(500):
        opinion_id = f"op_insuf_{uuid.uuid4().hex[:8]}"
        created_at = base_time + datetime.timedelta(hours=i)

        opinions.append({
            'opinion_id': opinion_id,
            'plan_id': f"plan_{i}",
            'specialist_type': 'evolution',
            'recommendation': 'approve',
            'cognitive_plan': {'steps': []},
            'created_at': created_at
        })

        feedbacks.append({
            'opinion_id': opinion_id,
            'specialist_type': 'evolution',
            'human_recommendation': 'approve',
            'human_rating': 0.8,
            'submitted_at': created_at + datetime.timedelta(minutes=30)
        })

    async def insert():
        await mongodb_ml_client.db['specialist_opinions'].insert_many(opinions)
        await mongodb_ml_client.db['feedback'].insert_many(feedbacks)

    event_loop.run_until_complete(insert())

    return {
        'total_opinions': len(opinions),
        'specialist_type': 'evolution'
    }


@pytest.mark.ml_integration
class TestPreRetrainingValidationIntegration:
    """Testes de integração para validação de pré-retraining."""

    @pytest.mark.skipif(
        not os.getenv('MONGODB_URI'),
        reason="MONGODB_URI não configurada"
    )
    def test_validation_with_real_mongodb(self, mongodb_ml_client, mongodb_test_data, event_loop):
        """
        Testa validação completa com MongoDB real.
        """
        try:
            from pre_retraining_validator import PreRetrainingValidator
        except ImportError:
            pytest.skip("PreRetrainingValidator não disponível")

        # Usar conexão do fixture
        validator = PreRetrainingValidator(
            mongodb_uri=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'),
            mongodb_database=mongodb_ml_client.db.name
        )

        try:
            with patch.object(validator, '_compare_with_baseline') as mock_baseline:
                mock_baseline.return_value = {
                    'comparison_available': False,
                    'reason': 'Test environment'
                }

                result = validator.validate_prerequisites(
                    specialist_type=mongodb_test_data['specialist_type'],
                    days=90,
                    min_samples=1000,
                    min_feedback_rating=0.0
                )

            assert result is not None
            assert 'passed' in result
            assert 'recommendation' in result
            assert 'checks' in result

            # Com 1500 amostras, deve passar
            if mongodb_test_data['total_opinions'] >= 1000:
                assert result['passed'] is True
                assert result['recommendation'] == 'proceed'

        finally:
            validator.close()

    @pytest.mark.skipif(
        not os.getenv('MONGODB_URI'),
        reason="MONGODB_URI não configurada"
    )
    def test_validation_insufficient_data(self, mongodb_ml_client, mongodb_insufficient_data, event_loop):
        """
        Testa validação quando dados são insuficientes.
        """
        try:
            from pre_retraining_validator import PreRetrainingValidator
        except ImportError:
            pytest.skip("PreRetrainingValidator não disponível")

        validator = PreRetrainingValidator(
            mongodb_uri=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'),
            mongodb_database=mongodb_ml_client.db.name
        )

        try:
            with patch.object(validator, '_compare_with_baseline') as mock_baseline:
                mock_baseline.return_value = {'comparison_available': False}

                result = validator.validate_prerequisites(
                    specialist_type=mongodb_insufficient_data['specialist_type'],
                    days=90,
                    min_samples=1000,  # Exige 1000, mas só tem 500
                    min_feedback_rating=0.0
                )

            assert result['passed'] is False
            assert result['recommendation'] == 'wait_for_more_data'
            assert len(result['blocking_issues']) > 0

        finally:
            validator.close()


@pytest.mark.ml_integration
class TestTrainingPipelineValidationIntegration:
    """Testes de integração do validador no pipeline de treinamento."""

    def test_skip_validation_flag(self):
        """
        Testa que flag --skip-validation funciona corretamente.
        """
        try:
            from train_specialist_model import parse_args
        except ImportError:
            pytest.skip("train_specialist_model não disponível")

        # Simular argumentos com skip-validation=true
        import sys
        original_argv = sys.argv

        try:
            sys.argv = [
                'train_specialist_model.py',
                '--specialist-type', 'technical',
                '--skip-validation', 'true'
            ]

            args = parse_args()

            assert args.skip_validation == 'true'

        finally:
            sys.argv = original_argv

    def test_validation_failure_error_raised(self):
        """
        Testa que ValidationFailedError é lançada corretamente.
        """
        try:
            from pre_retraining_validator import ValidationFailedError
        except ImportError:
            pytest.skip("ValidationFailedError não disponível")

        # Verificar que exceção pode ser lançada e capturada
        with pytest.raises(ValidationFailedError) as exc_info:
            raise ValidationFailedError(
                "Dados insuficientes para retraining. "
                "Atual: 500 amostras, Necessário: 1000."
            )

        assert "500" in str(exc_info.value)
        assert "1000" in str(exc_info.value)


@pytest.mark.ml_integration
class TestValidationReportMLflowIntegration:
    """Testes de integração do relatório de validação com MLflow."""

    def test_validation_report_mlflow_compatible(self, mlflow_test_tracking_uri):
        """
        Testa que relatório de validação pode ser logado no MLflow.
        """
        try:
            import mlflow
            from pre_retraining_validator import PreRetrainingValidator
        except ImportError:
            pytest.skip("MLflow ou PreRetrainingValidator não disponível")

        # Criar relatório mock
        validation_report = {
            'validation_timestamp': datetime.datetime.utcnow().isoformat() + 'Z',
            'specialist_type': 'technical',
            'passed': True,
            'recommendation': 'proceed',
            'checks': {
                'sample_count': {
                    'passed': True,
                    'current': 1500,
                    'required': 1000,
                    'coverage_rate': 75.0
                },
                'label_distribution': {
                    'passed': True,
                    'percentages': {'approve': 50.0, 'reject': 25.0, 'review_required': 25.0},
                    'is_balanced': True
                },
                'feature_quality': {
                    'passed': True,
                    'missing_value_rate': 0.02
                },
                'temporal_integrity': {
                    'passed': True,
                    'span_days': 30
                },
                'baseline_comparison': {
                    'comparison_available': False
                }
            },
            'warnings': [],
            'blocking_issues': [],
            'recommendations': ['Prosseguir com retraining']
        }

        mlflow.set_tracking_uri(mlflow_test_tracking_uri)

        with mlflow.start_run():
            # Deve ser possível logar o relatório
            mlflow.log_dict(validation_report, "pre_retraining_validation.json")
            mlflow.log_param('pre_validation_passed', validation_report['passed'])
            mlflow.log_param('pre_validation_recommendation', validation_report['recommendation'])

            run_id = mlflow.active_run().info.run_id

        # Verificar que artifact foi criado
        client = mlflow.tracking.MlflowClient()
        artifacts = client.list_artifacts(run_id)
        artifact_paths = [a.path for a in artifacts]

        assert 'pre_retraining_validation.json' in artifact_paths


@pytest.mark.ml_integration
class TestValidationEndToEnd:
    """Testes end-to-end da validação de pré-retraining."""

    def test_validation_flow_complete(self):
        """
        Testa fluxo completo de validação (mock).

        Simula cenário onde validação passa e pipeline continua.
        """
        try:
            from pre_retraining_validator import PreRetrainingValidator, ValidationFailedError
        except ImportError:
            pytest.skip("PreRetrainingValidator não disponível")

        # Mock completo do validador
        with patch('pre_retraining_validator.MongoClient') as mock_mongo:
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
            mock_mongo.return_value = mock_client

            validator = PreRetrainingValidator(
                mongodb_uri='mongodb://test:27017',
                mongodb_database='test_db'
            )

            with patch.object(validator, '_compare_with_baseline') as mock_baseline:
                mock_baseline.return_value = {
                    'comparison_available': True,
                    'baseline_run_id': 'test_run_123',
                    'significant_shift': False,
                    'max_divergence': 5.0
                }

                result = validator.validate_prerequisites(
                    specialist_type='technical',
                    days=90,
                    min_samples=1000,
                    min_feedback_rating=0.0
                )

            # Validação completa deve passar
            assert result['passed'] is True
            assert result['recommendation'] == 'proceed'

            # Verificar todos os checks
            assert result['checks']['sample_count']['passed'] is True
            assert result['checks']['label_distribution']['passed'] is True
            assert result['checks']['feature_quality']['passed'] is True
            assert result['checks']['temporal_integrity']['passed'] is True

            validator.close()

    def test_validation_flow_failure_raises_error(self):
        """
        Testa que falha de validação levanta erro apropriado.
        """
        try:
            from pre_retraining_validator import PreRetrainingValidator, ValidationFailedError
        except ImportError:
            pytest.skip("PreRetrainingValidator não disponível")

        with patch('pre_retraining_validator.MongoClient') as mock_mongo:
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
            mock_mongo.return_value = mock_client

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

            # Validação deve falhar
            assert result['passed'] is False
            assert result['recommendation'] == 'wait_for_more_data'

            # Verificar que blocking_issues contém mensagem apropriada
            assert len(result['blocking_issues']) > 0
            assert any('insuficientes' in issue.lower() or 'insufficient' in issue.lower()
                      for issue in result['blocking_issues'])

            validator.close()
