"""
Testes de integração para ExplainabilityLedgerV2.

Testa persistência, recuperação e queries semânticas.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from pydantic import ValidationError

from neural_hive_specialists.explainability.explainability_ledger_v2 import (
    ExplainabilityLedgerV2,
    ExplainabilityRecordSchema
)


@pytest.fixture
def mock_config():
    """Configuração mockada."""
    config = Mock()
    config.mongodb_uri = "mongodb://localhost:27017"
    config.mongodb_database = "test_neural_hive"
    return config


@pytest.fixture
def sample_explainability_data():
    """Dados de explicabilidade de exemplo."""
    return {
        'plan_id': 'plan-123',
        'explanation_method': 'shap',
        'input_features': {
            'num_tasks': 8.0,
            'complexity_score': 0.75,
            'avg_duration_ms': 2500.0
        },
        'feature_names': ['num_tasks', 'complexity_score', 'avg_duration_ms'],
        'model_version': '1.2.3',
        'model_type': 'RandomForestClassifier',
        'feature_importances': [
            {
                'feature_name': 'num_tasks',
                'shap_value': 0.35,
                'feature_value': 8.0,
                'contribution': 'positive',
                'importance': 0.35
            },
            {
                'feature_name': 'complexity_score',
                'shap_value': -0.25,
                'feature_value': 0.75,
                'contribution': 'negative',
                'importance': 0.25
            }
        ],
        'human_readable_summary': 'Decisão influenciada principalmente porque o plano contém 8 tarefas.',
        'detailed_narrative': 'A decisão foi baseada principalmente nos seguintes fatores...',
        'prediction': {
            'confidence_score': 0.85,
            'risk_score': 0.25
        },
        'computation_time_ms': 1250,
        'background_dataset_hash': 'abc123def456',
        'random_seed': None,
        'num_samples': None
    }


@pytest.mark.unit
class TestExplainabilityRecordSchema:
    """Testes do schema Pydantic."""

    def test_schema_validation_success(self, sample_explainability_data):
        """Testa validação bem-sucedida do schema."""
        record = ExplainabilityRecordSchema(
            explainability_token='token-123',
            plan_id=sample_explainability_data['plan_id'],
            specialist_type='technical',
            explanation_method=sample_explainability_data['explanation_method'],
            input_features=sample_explainability_data['input_features'],
            feature_names=sample_explainability_data['feature_names'],
            model_version=sample_explainability_data['model_version'],
            model_type=sample_explainability_data['model_type'],
            feature_importances=sample_explainability_data['feature_importances'],
            human_readable_summary=sample_explainability_data['human_readable_summary'],
            detailed_narrative=sample_explainability_data['detailed_narrative'],
            prediction=sample_explainability_data['prediction'],
            computation_time_ms=sample_explainability_data['computation_time_ms']
        )

        assert record.explainability_token == 'token-123'
        assert record.schema_version == '2.0.0'
        assert record.plan_id == 'plan-123'
        assert record.specialist_type == 'technical'

    def test_schema_validation_missing_required_field(self):
        """Testa que campos obrigatórios são validados."""
        with pytest.raises(ValidationError) as exc_info:
            ExplainabilityRecordSchema(
                explainability_token='token-123',
                # plan_id faltando
                specialist_type='technical',
                explanation_method='shap'
            )

        errors = exc_info.value.errors()
        assert any(error['loc'][0] == 'plan_id' for error in errors)

    def test_schema_default_values(self, sample_explainability_data):
        """Testa valores padrão do schema."""
        record = ExplainabilityRecordSchema(
            explainability_token='token-123',
            plan_id='plan-123',
            specialist_type='technical',
            explanation_method='shap',
            input_features={},
            feature_names=[],
            model_version='1.0.0',
            model_type='heuristic',
            feature_importances=[],
            human_readable_summary='',
            detailed_narrative='',
            prediction={},
            computation_time_ms=0
        )

        # Schema version tem default
        assert record.schema_version == '2.0.0'
        # created_at é gerado automaticamente
        assert isinstance(record.created_at, datetime)


@pytest.mark.integration
class TestExplainabilityLedgerV2Persistence:
    """Testes de persistência no MongoDB."""

    @pytest.fixture
    def ledger(self, mock_config):
        """Cria ledger com MongoDB mockado."""
        with patch('neural_hive_specialists.explainability.explainability_ledger_v2.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            ledger = ExplainabilityLedgerV2(mock_config)
            ledger._mongo_client = mock_mongo.return_value

            # Mock collection methods
            mock_db = MagicMock()
            mock_db.__getitem__.return_value = mock_collection
            ledger.mongo_client.__getitem__.return_value = mock_db

            return ledger

    def test_persist_success(self, ledger, sample_explainability_data):
        """Testa persistência bem-sucedida."""
        token = ledger.persist(
            sample_explainability_data,
            specialist_type='technical',
            correlation_id='corr-123'
        )

        assert token is not None
        assert len(token) == 64  # SHA-256 hex

    def test_persist_generates_unique_tokens(self, ledger, sample_explainability_data):
        """Testa que tokens únicos são gerados."""
        token1 = ledger.persist(
            sample_explainability_data,
            specialist_type='technical'
        )

        # Modificar dados
        modified_data = sample_explainability_data.copy()
        modified_data['plan_id'] = 'plan-456'

        token2 = ledger.persist(
            modified_data,
            specialist_type='technical'
        )

        assert token1 != token2

    def test_retrieve_success(self, ledger):
        """Testa recuperação bem-sucedida."""
        mock_doc = {
            'explainability_token': 'token-123',
            'plan_id': 'plan-123',
            'specialist_type': 'technical'
        }

        # Mock find_one
        mock_collection = ledger.mongo_client[ledger.config.mongodb_database]['explainability_ledger_v2']
        mock_collection.find_one = MagicMock(return_value=mock_doc)

        result = ledger.retrieve('token-123')

        assert result is not None
        assert result['explainability_token'] == 'token-123'
        assert '_id' not in result  # Deve remover _id

    def test_retrieve_not_found(self, ledger):
        """Testa recuperação quando token não existe."""
        mock_collection = ledger.mongo_client[ledger.config.mongodb_database]['explainability_ledger_v2']
        mock_collection.find_one = MagicMock(return_value=None)

        result = ledger.retrieve('nonexistent')

        assert result is None


@pytest.mark.integration
class TestExplainabilityLedgerV2Queries:
    """Testes de queries semânticas."""

    @pytest.fixture
    def ledger(self, mock_config):
        """Cria ledger com MongoDB mockado."""
        with patch('neural_hive_specialists.explainability.explainability_ledger_v2.MongoClient') as mock_mongo:
            mock_collection = MagicMock()
            mock_mongo.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            ledger = ExplainabilityLedgerV2(mock_config)
            ledger._mongo_client = mock_mongo.return_value

            mock_db = MagicMock()
            mock_db.__getitem__.return_value = mock_collection
            ledger.mongo_client.__getitem__.return_value = mock_db

            return ledger

    def test_query_by_plan(self, ledger):
        """Testa query por plan_id."""
        mock_docs = [
            {'explainability_token': 'token-1', 'plan_id': 'plan-123', '_id': 'id1'},
            {'explainability_token': 'token-2', 'plan_id': 'plan-123', '_id': 'id2'}
        ]

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.__iter__ = MagicMock(return_value=iter(mock_docs))

        mock_collection = ledger.mongo_client[ledger.config.mongodb_database]['explainability_ledger_v2']
        mock_collection.find = MagicMock(return_value=mock_cursor)

        results = ledger.query_by_plan('plan-123')

        assert len(results) == 2
        assert all('_id' not in doc for doc in results)
        mock_collection.find.assert_called_once_with({'plan_id': 'plan-123'})

    def test_query_by_specialist(self, ledger):
        """Testa query por specialist_type."""
        mock_docs = [
            {'explainability_token': 'token-1', 'specialist_type': 'technical', '_id': 'id1'},
            {'explainability_token': 'token-2', 'specialist_type': 'technical', '_id': 'id2'}
        ]

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.__iter__ = MagicMock(return_value=iter(mock_docs))

        mock_collection = ledger.mongo_client[ledger.config.mongodb_database]['explainability_ledger_v2']
        mock_collection.find = MagicMock(return_value=mock_cursor)

        results = ledger.query_by_specialist('technical', limit=100)

        assert len(results) == 2
        mock_collection.find.assert_called_once_with({'specialist_type': 'technical'})

    def test_validate_schema_success(self, ledger, sample_explainability_data):
        """Testa validação de schema bem-sucedida."""
        document = {
            'explainability_token': 'token-123',
            'plan_id': 'plan-123',
            'specialist_type': 'technical',
            'explanation_method': 'shap',
            'input_features': sample_explainability_data['input_features'],
            'feature_names': sample_explainability_data['feature_names'],
            'model_version': '1.0.0',
            'model_type': 'RandomForest',
            'feature_importances': sample_explainability_data['feature_importances'],
            'human_readable_summary': 'Summary',
            'detailed_narrative': 'Narrative',
            'prediction': {'confidence_score': 0.8},
            'computation_time_ms': 1000
        }

        is_valid = ledger.validate_schema(document)

        assert is_valid is True

    def test_validate_schema_failure(self, ledger):
        """Testa validação de schema com documento inválido."""
        invalid_document = {
            'explainability_token': 'token-123'
            # Campos obrigatórios faltando
        }

        is_valid = ledger.validate_schema(invalid_document)

        assert is_valid is False

    def test_schema_accepts_importance_vectors_alias(self, sample_explainability_data):
        """Testa que schema aceita 'importance_vectors' como alias de 'feature_importances'."""
        # Usar importance_vectors ao invés de feature_importances
        data_with_alias = {
            'explainability_token': 'token-alias-test',
            'plan_id': sample_explainability_data['plan_id'],
            'specialist_type': 'technical',
            'explanation_method': sample_explainability_data['explanation_method'],
            'input_features': sample_explainability_data['input_features'],
            'feature_names': sample_explainability_data['feature_names'],
            'model_version': sample_explainability_data['model_version'],
            'model_type': sample_explainability_data['model_type'],
            'importance_vectors': sample_explainability_data['feature_importances'],  # Usar alias
            'human_readable_summary': sample_explainability_data['human_readable_summary'],
            'detailed_narrative': sample_explainability_data['detailed_narrative'],
            'prediction': sample_explainability_data['prediction'],
            'computation_time_ms': sample_explainability_data['computation_time_ms']
        }

        # Schema deve aceitar importance_vectors
        record = ExplainabilityRecordSchema(**data_with_alias)

        # Internamente, deve ter sido mapeado para feature_importances
        assert record.feature_importances == sample_explainability_data['feature_importances']
        assert len(record.feature_importances) > 0
