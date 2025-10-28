"""
Testes unitários para ComplianceLayer.

Cobertura: orquestração de componentes, sanitize_cognitive_plan usa deepcopy,
encrypt_opinion_fields adiciona metadados, audit logging, métricas.
"""

import pytest
import copy
from unittest.mock import Mock, MagicMock, patch, call

from neural_hive_specialists.compliance.compliance_layer import ComplianceLayer


@pytest.fixture
def mock_config():
    """Cria configuração mockada para testes."""
    config = Mock()
    config.enable_compliance_layer = True
    config.enable_pii_detection = True
    config.enable_field_encryption = True
    config.enable_audit_logging = True
    config.pii_detection_languages = ['pt', 'en']
    config.pii_entities_to_detect = ['PERSON', 'EMAIL_ADDRESS']
    config.pii_anonymization_strategy = 'replace'
    config.fields_to_encrypt = ['correlation_id', 'trace_id']
    config.encryption_algorithm = 'fernet'
    config.audit_log_collection = 'audit_logs'
    config.audit_log_retention_days = 90
    return config


@pytest.fixture
def mock_metrics():
    """Cria mock de SpecialistMetrics."""
    metrics = Mock()
    metrics.increment_pii_entities_detected = Mock()
    metrics.increment_pii_anonymization = Mock()
    metrics.observe_pii_detection_duration = Mock()
    metrics.increment_fields_encrypted = Mock()
    metrics.observe_encryption_duration = Mock()
    metrics.increment_pii_detection_error = Mock()
    metrics.increment_encryption_error = Mock()
    return metrics


@pytest.fixture
def sample_cognitive_plan():
    """Cria plano cognitivo de exemplo para testes."""
    return {
        'plan_id': 'plan-123',
        'tasks': [
            {
                'description': 'João Silva mora em São Paulo',
                'parameters': {
                    'email': 'joao@example.com',
                    'phone': '11-99999-9999'
                }
            },
            {
                'description': 'Processar dados do cliente',
                'parameters': {}
            }
        ],
        'metadata': {
            'owner': 'Maria Santos',
            'department': 'Vendas'
        }
    }


@pytest.fixture
def sample_opinion_doc():
    """Cria documento de opinião de exemplo."""
    return {
        'opinion_id': 'opinion-123',
        'correlation_id': 'corr-456',
        'trace_id': 'trace-789',
        'opinion': {
            'verdict': 'approved',
            'reasoning': 'Analysis complete'
        }
    }


@pytest.mark.unit
class TestComplianceLayerInitialization:
    """Testes de inicialização da ComplianceLayer."""

    def test_initialization_disabled(self):
        """Testa inicialização quando compliance layer está desabilitado."""
        config = Mock()
        config.enable_compliance_layer = False
        metrics = Mock()

        compliance = ComplianceLayer(config, 'business', metrics)

        assert compliance.enabled is False

    @patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector')
    @patch('neural_hive_specialists.compliance.compliance_layer.FieldEncryptor')
    @patch('neural_hive_specialists.compliance.compliance_layer.AuditLogger')
    def test_initialization_all_components_enabled(self, mock_audit, mock_encryptor, mock_pii, mock_config, mock_metrics):
        """Testa inicialização bem-sucedida com todos os componentes."""
        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        assert compliance.enabled is True
        mock_pii.assert_called_once_with(mock_config)
        mock_encryptor.assert_called_once_with(mock_config)
        mock_audit.assert_called_once_with(mock_config, 'business')

    @patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector')
    @patch('neural_hive_specialists.compliance.compliance_layer.FieldEncryptor')
    def test_initialization_partial_components(self, mock_encryptor, mock_pii, mock_config, mock_metrics):
        """Testa inicialização com alguns componentes desabilitados."""
        mock_config.enable_pii_detection = True
        mock_config.enable_field_encryption = False
        mock_config.enable_audit_logging = False

        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        assert compliance.enabled is True
        mock_pii.assert_called_once()
        assert compliance.field_encryptor is None
        assert compliance.audit_logger is None

    @patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector', side_effect=Exception("Init error"))
    def test_initialization_handles_error(self, mock_pii, mock_config, mock_metrics):
        """Testa que erro na inicialização desabilita compliance."""
        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        assert compliance.enabled is False


@pytest.mark.unit
class TestSanitizeCognitivePlan:
    """Testes do método sanitize_cognitive_plan."""

    @pytest.fixture
    def compliance(self, mock_config, mock_metrics):
        """Cria ComplianceLayer com componentes mockados."""
        with patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector') as mock_pii, \
             patch('neural_hive_specialists.compliance.compliance_layer.FieldEncryptor'), \
             patch('neural_hive_specialists.compliance.compliance_layer.AuditLogger'):

            compliance = ComplianceLayer(mock_config, 'business', mock_metrics)
            compliance.pii_detector = Mock()
            compliance.audit_logger = Mock()

            return compliance

    def test_sanitize_uses_deepcopy(self, compliance, sample_cognitive_plan):
        """Testa que sanitize_cognitive_plan usa deepcopy (plano original inalterado)."""
        compliance.pii_detector.anonymize_text = Mock(return_value=("<PERSON>", []))

        original_plan = copy.deepcopy(sample_cognitive_plan)
        sanitized_plan, _ = compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        # Plano original não deve ter mudado
        assert sample_cognitive_plan == original_plan
        # Plano sanitizado pode ter mudado
        assert sanitized_plan is not sample_cognitive_plan

    def test_sanitize_task_descriptions(self, compliance, sample_cognitive_plan):
        """Testa sanitização de task descriptions."""
        mock_entity = {'entity_type': 'PERSON', 'start': 0, 'end': 11, 'score': 0.85, 'anonymized': True}
        compliance.pii_detector.anonymize_text = Mock(return_value=("<PERSON> mora em São Paulo", [mock_entity]))

        sanitized_plan, metadata = compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        # Verificar que anonymize_text foi chamado para task descriptions
        assert compliance.pii_detector.anonymize_text.call_count >= 1

    def test_sanitize_task_parameters(self, compliance, sample_cognitive_plan):
        """Testa sanitização de task parameters."""
        mock_entity = {'entity_type': 'EMAIL_ADDRESS', 'start': 0, 'end': 17, 'score': 0.90, 'anonymized': True}
        compliance.pii_detector.anonymize_text = Mock(return_value=("<EMAIL_ADDRESS>", [mock_entity]))

        sanitized_plan, metadata = compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        # Verificar que anonymize_text foi chamado para parameters string
        assert compliance.pii_detector.anonymize_text.called

    def test_sanitize_metadata_fields(self, compliance, sample_cognitive_plan):
        """Testa sanitização de metadata fields."""
        mock_entity = {'entity_type': 'PERSON', 'start': 0, 'end': 12, 'score': 0.85, 'anonymized': True}
        compliance.pii_detector.anonymize_text = Mock(return_value=("<PERSON>", [mock_entity]))

        sanitized_plan, metadata = compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        # Verificar que anonymize_text foi chamado para metadata
        assert compliance.pii_detector.anonymize_text.called

    def test_sanitize_returns_metadata(self, compliance, sample_cognitive_plan):
        """Testa que metadados corretos são retornados."""
        mock_entity = {'entity_type': 'PERSON', 'start': 0, 'end': 11, 'score': 0.85, 'anonymized': True}
        compliance.pii_detector.anonymize_text = Mock(return_value=("<PERSON>", [mock_entity]))

        _, metadata = compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        assert 'entities_detected' in metadata
        assert 'anonymization_applied' in metadata
        assert 'duration_seconds' in metadata
        assert isinstance(metadata['entities_detected'], list)
        assert isinstance(metadata['anonymization_applied'], bool)

    def test_sanitize_increments_metrics(self, compliance, sample_cognitive_plan, mock_metrics):
        """Testa que métricas são incrementadas quando PII detectado."""
        compliance.metrics = mock_metrics
        mock_entity = {'entity_type': 'PERSON', 'start': 0, 'end': 11, 'score': 0.85, 'anonymized': True}
        compliance.pii_detector.anonymize_text = Mock(return_value=("<PERSON>", [mock_entity]))

        compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        # Verificar que métricas foram chamadas
        assert mock_metrics.increment_pii_entities_detected.called
        assert mock_metrics.increment_pii_anonymization.called
        assert mock_metrics.observe_pii_detection_duration.called

    def test_sanitize_audit_logs_when_pii_detected(self, compliance, sample_cognitive_plan):
        """Testa que audit log é criado quando PII detectado."""
        mock_entity = {'entity_type': 'PERSON', 'start': 0, 'end': 11, 'score': 0.85, 'anonymized': True}
        compliance.pii_detector.anonymize_text = Mock(return_value=("<PERSON>", [mock_entity]))

        compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        compliance.audit_logger.log_pii_detection.assert_called_once()

    def test_sanitize_no_pii_detected(self, compliance, sample_cognitive_plan):
        """Testa comportamento quando nenhum PII detectado."""
        compliance.pii_detector.anonymize_text = Mock(return_value=("texto normal", []))

        sanitized_plan, metadata = compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        assert metadata['anonymization_applied'] is False
        assert len(metadata['entities_detected']) == 0

    def test_sanitize_disabled(self, mock_config, mock_metrics):
        """Testa que compliance desabilitado retorna plano original."""
        mock_config.enable_compliance_layer = False
        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        plan = {'plan_id': 'test'}
        sanitized_plan, metadata = compliance.sanitize_cognitive_plan(plan)

        assert sanitized_plan == plan
        assert metadata == {}

    def test_sanitize_handles_error(self, compliance, sample_cognitive_plan, mock_metrics):
        """Testa que erro na sanitização retorna plano original."""
        compliance.metrics = mock_metrics
        compliance.pii_detector.anonymize_text = Mock(side_effect=Exception("Sanitization error"))

        sanitized_plan, metadata = compliance.sanitize_cognitive_plan(sample_cognitive_plan)

        # Deve retornar plano original
        assert sanitized_plan == sample_cognitive_plan
        assert metadata == {}
        mock_metrics.increment_pii_detection_error.assert_called_once_with('sanitization_error')


@pytest.mark.unit
class TestEncryptOpinionFields:
    """Testes do método encrypt_opinion_fields."""

    @pytest.fixture
    def compliance(self, mock_config, mock_metrics):
        """Cria ComplianceLayer com componentes mockados."""
        with patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector'), \
             patch('neural_hive_specialists.compliance.compliance_layer.FieldEncryptor') as mock_encryptor, \
             patch('neural_hive_specialists.compliance.compliance_layer.AuditLogger'):

            compliance = ComplianceLayer(mock_config, 'business', mock_metrics)
            compliance.field_encryptor = Mock()
            compliance.audit_logger = Mock()

            return compliance

    def test_encrypt_opinion_fields_success(self, compliance, sample_opinion_doc):
        """Testa criptografia bem-sucedida de campos de opinião."""
        encrypted_doc = {
            'opinion_id': 'opinion-123',
            'correlation_id': 'enc:encrypted_corr',
            'trace_id': 'enc:encrypted_trace',
            'opinion': sample_opinion_doc['opinion']
        }
        compliance.field_encryptor.encrypt_dict = Mock(return_value=encrypted_doc)

        result = compliance.encrypt_opinion_fields(sample_opinion_doc)

        compliance.field_encryptor.encrypt_dict.assert_called_once_with(
            sample_opinion_doc,
            compliance.config.fields_to_encrypt
        )

    def test_encrypt_adds_compliance_metadata(self, compliance, sample_opinion_doc):
        """Testa que metadados _compliance são adicionados."""
        encrypted_doc = sample_opinion_doc.copy()
        compliance.field_encryptor.encrypt_dict = Mock(return_value=encrypted_doc)

        result = compliance.encrypt_opinion_fields(sample_opinion_doc)

        assert '_compliance' in result
        assert 'encrypted_fields' in result['_compliance']
        assert 'encryption_algorithm' in result['_compliance']
        assert 'encryption_version' in result['_compliance']
        assert 'encrypted_at' in result['_compliance']

    def test_encrypt_increments_metrics(self, compliance, sample_opinion_doc, mock_metrics):
        """Testa que métricas são incrementadas para cada campo."""
        compliance.metrics = mock_metrics
        encrypted_doc = sample_opinion_doc.copy()
        compliance.field_encryptor.encrypt_dict = Mock(return_value=encrypted_doc)

        compliance.encrypt_opinion_fields(sample_opinion_doc)

        # Verificar que métricas foram incrementadas para campos presentes
        assert mock_metrics.increment_fields_encrypted.call_count >= 1
        assert mock_metrics.observe_encryption_duration.called

    def test_encrypt_audit_logs_operations(self, compliance, sample_opinion_doc):
        """Testa que operações são auditadas."""
        encrypted_doc = sample_opinion_doc.copy()
        compliance.field_encryptor.encrypt_dict = Mock(return_value=encrypted_doc)

        compliance.encrypt_opinion_fields(sample_opinion_doc)

        # Verificar que audit logger foi chamado
        assert compliance.audit_logger.log_encryption_operation.called

    def test_encrypt_disabled(self, mock_config, mock_metrics):
        """Testa que compliance desabilitado retorna documento original."""
        mock_config.enable_compliance_layer = False
        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        doc = {'opinion_id': 'test'}
        result = compliance.encrypt_opinion_fields(doc)

        assert result == doc

    def test_encrypt_handles_error(self, compliance, sample_opinion_doc, mock_metrics):
        """Testa que erro na criptografia retorna documento original."""
        compliance.metrics = mock_metrics
        compliance.field_encryptor.encrypt_dict = Mock(side_effect=Exception("Encryption error"))

        result = compliance.encrypt_opinion_fields(sample_opinion_doc)

        # Deve retornar documento original
        assert result == sample_opinion_doc
        mock_metrics.increment_encryption_error.assert_called_once_with('encryption_error')


@pytest.mark.unit
class TestDecryptOpinionFields:
    """Testes do método decrypt_opinion_fields."""

    @pytest.fixture
    def compliance(self, mock_config, mock_metrics):
        """Cria ComplianceLayer com componentes mockados."""
        with patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector'), \
             patch('neural_hive_specialists.compliance.compliance_layer.FieldEncryptor') as mock_encryptor, \
             patch('neural_hive_specialists.compliance.compliance_layer.AuditLogger'):

            compliance = ComplianceLayer(mock_config, 'business', mock_metrics)
            compliance.field_encryptor = Mock()

            return compliance

    def test_decrypt_opinion_fields_success(self, compliance):
        """Testa descriptografia bem-sucedida de campos."""
        encrypted_doc = {
            'opinion_id': 'opinion-123',
            'correlation_id': 'enc:encrypted',
            '_compliance': {'encrypted_fields': ['correlation_id']}
        }
        decrypted_doc = {
            'opinion_id': 'opinion-123',
            'correlation_id': 'corr-456',
            '_compliance': {'encrypted_fields': ['correlation_id']}
        }
        compliance.field_encryptor.decrypt_dict = Mock(return_value=decrypted_doc)

        result = compliance.decrypt_opinion_fields(encrypted_doc)

        compliance.field_encryptor.decrypt_dict.assert_called_once()

    def test_decrypt_uses_compliance_metadata_fields(self, compliance):
        """Testa que campos de _compliance.encrypted_fields são usados."""
        encrypted_doc = {
            'opinion_id': 'opinion-123',
            'correlation_id': 'enc:encrypted',
            '_compliance': {'encrypted_fields': ['correlation_id', 'trace_id']}
        }
        compliance.field_encryptor.decrypt_dict = Mock(return_value=encrypted_doc)

        compliance.decrypt_opinion_fields(encrypted_doc)

        call_args = compliance.field_encryptor.decrypt_dict.call_args
        assert call_args[0][1] == ['correlation_id', 'trace_id']

    def test_decrypt_fallback_to_config_fields(self, compliance):
        """Testa fallback para config.fields_to_encrypt quando _compliance ausente."""
        encrypted_doc = {
            'opinion_id': 'opinion-123',
            'correlation_id': 'enc:encrypted'
        }
        compliance.field_encryptor.decrypt_dict = Mock(return_value=encrypted_doc)

        compliance.decrypt_opinion_fields(encrypted_doc)

        call_args = compliance.field_encryptor.decrypt_dict.call_args
        assert call_args[0][1] == compliance.config.fields_to_encrypt

    def test_decrypt_increments_metrics(self, compliance, mock_metrics):
        """Testa que métricas são incrementadas."""
        compliance.metrics = mock_metrics
        encrypted_doc = {
            'opinion_id': 'opinion-123',
            'correlation_id': 'enc:encrypted',
            '_compliance': {'encrypted_fields': ['correlation_id']}
        }
        compliance.field_encryptor.decrypt_dict = Mock(return_value=encrypted_doc)

        compliance.decrypt_opinion_fields(encrypted_doc)

        assert mock_metrics.increment_fields_decrypted.called
        assert mock_metrics.observe_encryption_duration.called

    def test_decrypt_disabled(self, mock_config, mock_metrics):
        """Testa que compliance desabilitado retorna documento original."""
        mock_config.enable_compliance_layer = False
        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        doc = {'opinion_id': 'test', 'correlation_id': 'enc:data'}
        result = compliance.decrypt_opinion_fields(doc)

        assert result == doc

    def test_decrypt_handles_error(self, compliance, mock_metrics):
        """Testa que erro na descriptografia retorna documento original."""
        compliance.metrics = mock_metrics
        encrypted_doc = {'opinion_id': 'test'}
        compliance.field_encryptor.decrypt_dict = Mock(side_effect=Exception("Decryption error"))

        result = compliance.decrypt_opinion_fields(encrypted_doc)

        assert result == encrypted_doc
        mock_metrics.increment_encryption_error.assert_called_once_with('decryption_error')


@pytest.mark.unit
class TestGetComplianceMetadata:
    """Testes do método get_compliance_metadata."""

    @patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector')
    @patch('neural_hive_specialists.compliance.compliance_layer.FieldEncryptor')
    @patch('neural_hive_specialists.compliance.compliance_layer.AuditLogger')
    def test_get_metadata_enabled(self, mock_audit, mock_encryptor, mock_pii, mock_config, mock_metrics):
        """Testa metadados quando compliance habilitado."""
        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        metadata = compliance.get_compliance_metadata()

        assert metadata['enabled'] is True
        assert 'pii_detection' in metadata
        assert 'field_encryption' in metadata
        assert 'audit_logging' in metadata

    def test_get_metadata_disabled(self):
        """Testa metadados quando compliance desabilitado."""
        config = Mock()
        config.enable_compliance_layer = False
        compliance = ComplianceLayer(config, 'business', Mock())

        metadata = compliance.get_compliance_metadata()

        assert metadata == {'enabled': False}

    @patch('neural_hive_specialists.compliance.compliance_layer.PIIDetector')
    @patch('neural_hive_specialists.compliance.compliance_layer.FieldEncryptor')
    @patch('neural_hive_specialists.compliance.compliance_layer.AuditLogger')
    def test_get_metadata_structure(self, mock_audit, mock_encryptor, mock_pii, mock_config, mock_metrics):
        """Testa estrutura completa dos metadados."""
        compliance = ComplianceLayer(mock_config, 'business', mock_metrics)

        metadata = compliance.get_compliance_metadata()

        # Verificar estrutura de pii_detection
        assert 'enabled' in metadata['pii_detection']
        assert 'languages' in metadata['pii_detection']
        assert 'entities' in metadata['pii_detection']
        assert 'strategy' in metadata['pii_detection']

        # Verificar estrutura de field_encryption
        assert 'enabled' in metadata['field_encryption']
        assert 'algorithm' in metadata['field_encryption']
        assert 'fields' in metadata['field_encryption']

        # Verificar estrutura de audit_logging
        assert 'enabled' in metadata['audit_logging']
        assert 'collection' in metadata['audit_logging']
        assert 'retention_days' in metadata['audit_logging']
