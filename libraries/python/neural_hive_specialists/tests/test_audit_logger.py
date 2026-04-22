"""
Testes unitários para AuditLogger.

Cobertura para compliance/audit_logger.py
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestAuditLogger:
    """Testes para AuditLogger."""

    @pytest.fixture()
    def config(self):
        """Configuração de teste."""
        mock_config = Mock()
        mock_config.enable_audit_logging = True
        mock_config.mongodb_uri = "mongodb://localhost:27017"
        mock_config.mongodb_database = "test_db"
        mock_config.audit_log_collection = "audit_log"
        mock_config.audit_log_retention_days = 30
        return mock_config

    @pytest.fixture()
    def sample_event_data(self):
        """Dados de evento de exemplo."""
        return {
            "action": "update_config",
            "changes": {"key": "value"},
            "reason": "Test reason",
        }

    def test_init_with_audit_enabled(self, config):
        """Testa inicialização com audit logging habilitado."""
        with patch("neural_hive_specialists.compliance.audit_logger.MongoClient"):
            from neural_hive_specialists.compliance.audit_logger import AuditLogger

            logger = AuditLogger(config, specialist_type="test_specialist")

            assert logger.enabled is True
            assert logger.specialist_type == "test_specialist"

    def test_init_with_audit_disabled(self, config):
        """Testa inicialização com audit logging desabilitado."""
        config.enable_audit_logging = False

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        assert logger.enabled is False

    def test_init_with_mongo_error_disables_audit(self, config):
        """Testa que erro no Mongo desabilita audit logging."""
        with patch(
            "neural_hive_specialists.compliance.audit_logger.MongoClient",
            side_effect=Exception("Connection error"),
        ):
            from neural_hive_specialists.compliance.audit_logger import AuditLogger

            logger = AuditLogger(config, specialist_type="test_specialist")

            assert logger.enabled is False

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_initialize_mongo_creates_indexes(self, mock_mongo_class, config):
        """Testa que índices são criados corretamente."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        # Verificar que create_index foi chamado várias vezes (5 índices)
        assert mock_collection.create_index.call_count == 5

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_config_change_success(self, mock_mongo_class, config, sample_event_data):
        """Testa log de mudança de configuração."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_config_change(
            changed_by="user123",
            old_config={"key": "old_value"},
            new_config={"key": "new_value"},
            reason="Test reason",
        )

        # Verificar que insert_one foi chamado
        assert mock_collection.insert_one.called

        # Verificar estrutura do documento inserido
        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["event_type"] == "config_change"
        assert doc["actor"] == "user123"
        assert "old_config" in doc["event_data"]
        assert "new_config" in doc["event_data"]

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_data_access_success(self, mock_mongo_class, config):
        """Testa log de acesso a dados."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_data_access(
            accessed_by="user123",
            resource_type="opinion",
            resource_id="opinion_123",
            action="read",
            metadata={"reason": "Review"},
        )

        assert mock_collection.insert_one.called

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["event_type"] == "data_access"
        assert doc["actor"] == "user123"
        assert doc["event_data"]["resource_type"] == "opinion"

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_pii_detection_success(self, mock_mongo_class, config):
        """Testa log de detecção de PII."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_pii_detection(
            plan_id="plan_123",
            entities_detected=[
                {"entity_type": "email", "score": 0.9, "field": "contact"},
                {"entity_type": "phone", "score": 0.8, "field": "phone"},
            ],
            anonymization_applied=True,
        )

        assert mock_collection.insert_one.called

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["event_type"] == "pii_detection"
        assert doc["event_data"]["plan_id"] == "plan_123"
        assert doc["event_data"]["entities_count"] == 2
        assert doc["event_data"]["anonymization_applied"] is True
        assert doc["severity"] == "warning"  # Has entities

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_encryption_operation_success(self, mock_mongo_class, config):
        """Testa log de operação de criptografia."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_encryption_operation(
            operation="encrypt",
            field_name="ssn",
            success=True,
        )

        assert mock_collection.insert_one.called

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["event_type"] == "encryption_operation"
        assert doc["event_data"]["operation"] == "encrypt"
        assert doc["event_data"]["field_name"] == "ssn"
        assert doc["event_data"]["success"] is True

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_retention_action_success(self, mock_mongo_class, config):
        """Testa log de ação de retenção."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_retention_action(
            action_type="mask",
            affected_documents=10,
            policy_name="gdpr",
            metadata={"reason": "GDPR right_to_be_forgotten"},
        )

        assert mock_collection.insert_one.called

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["event_type"] == "retention_action"
        assert doc["event_data"]["action_type"] == "mask"
        assert doc["event_data"]["affected_documents"] == 10

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_when_disabled_does_nothing(self, mock_mongo_class, config):
        """Testa que logs não são registrados quando desabilitado."""
        config.enable_audit_logging = False

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        # Não deve chamar Mongo pois está desabilitado
        assert not mock_mongo_class.called

        # Chamar métodos - não deve causar erro
        logger.log_config_change("user", {}, {}, "test")
        logger.log_data_access("user", "opinion", "123", "read")
        logger.log_pii_detection("plan_123", [], False)
        logger.log_encryption_operation("encrypt", "field", True)
        logger.log_retention_action("mask", 1, "policy")

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_with_correlation_id(self, mock_mongo_class, config):
        """Testa log com correlation_id via metadata."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_data_access(
            accessed_by="user123",
            resource_type="opinion",
            resource_id="opinion_123",
            action="read",
            metadata={"correlation_id": "corr-123"},
        )

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["correlation_id"] == "corr-123"

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_with_severity(self, mock_mongo_class, config):
        """Testa que severidade é 'warning' para config_change."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_config_change(
            changed_by="user123",
            old_config={},
            new_config={},
            reason="test",
        )

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["severity"] == "warning"

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_log_with_metadata(self, mock_mongo_class, config):
        """Testa log com metadados customizados."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        custom_metadata = {"ip_address": "192.168.1.1", "user_agent": "test"}

        logger.log_data_access(
            accessed_by="user123",
            resource_type="opinion",
            resource_id="opinion_123",
            action="read",
            metadata=custom_metadata,
        )

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        # Metadata é merged no event_data
        assert doc["event_data"]["ip_address"] == "192.168.1.1"

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_query_audit_logs(self, mock_mongo_class, config):
        """Testa consulta de logs de auditoria."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_cursor = MagicMock()

        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = [{"audit_id": "123", "event_type": "config_change"}]
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        results = logger.query_audit_logs(
            filters={"event_type": "config_change"},
            limit=10,
        )

        assert len(results) == 1
        assert results[0]["event_type"] == "config_change"

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_query_audit_logs_with_date_filter(self, mock_mongo_class, config):
        """Testa consulta de logs com filtro de data."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_cursor = MagicMock()

        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.find.return_value = mock_cursor
        mock_cursor.sort.return_value = mock_cursor
        mock_cursor.limit.return_value = []
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        from datetime import timedelta

        start_date = datetime.now(UTC) - timedelta(days=7)
        results = logger.query_audit_logs(
            filters={"start_date": start_date},
            limit=10,
        )

        # Verificar que find foi chamado com filtro de data
        assert mock_collection.find.called

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_query_audit_logs_when_disabled(self, mock_mongo_class, config):
        """Testa consulta quando audit logging está desabilitado."""
        config.enable_audit_logging = False

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        results = logger.query_audit_logs()

        assert results == []

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_get_audit_summary(self, mock_mongo_class, config):
        """Testa obtenção de resumo de auditoria."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_collection.aggregate.return_value = [
            {"_id": "config_change", "count": 10},
            {"_id": "data_access", "count": 25},
        ]
        mock_mongo_class.return_value = mock_client

        from datetime import timedelta

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=7)
        summary = logger.get_audit_summary(start_date, end_date)

        assert "events_by_type" in summary
        assert summary["events_by_type"]["config_change"] == 10
        assert summary["events_by_type"]["data_access"] == 25

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_get_audit_summary_when_disabled(self, mock_mongo_class, config):
        """Testa resumo quando audit logging está desabilitado."""
        config.enable_audit_logging = False

        from datetime import timedelta

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=7)
        summary = logger.get_audit_summary(start_date, end_date)

        assert summary == {}

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_document_structure_has_required_fields(self, mock_mongo_class, config):
        """Testa que documentos de auditoria têm campos obrigatórios."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_config_change(
            changed_by="user123",
            old_config={},
            new_config={},
            reason="test",
        )

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        # Campos obrigatórios
        required_fields = [
            "audit_id",
            "timestamp",
            "specialist_type",
            "event_type",
            "event_data",
            "actor",
            "severity",
        ]

        for field in required_fields:
            assert field in doc, f"Campo obrigatório {field} não encontrado"

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_audit_id_is_uuid(self, mock_mongo_class, config):
        """Testa que audit_id é um UUID válido."""
        import uuid

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_config_change(
            changed_by="user123",
            old_config={},
            new_config={},
            reason="test",
        )

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        # Verificar que audit_id é um UUID válido
        try:
            uuid.UUID(doc["audit_id"])
        except ValueError:
            pytest.fail("audit_id não é um UUID válido")

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_timestamp_is_datetime(self, mock_mongo_class, config):
        """Testa que timestamp é um datetime."""

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_config_change(
            changed_by="user123",
            old_config={},
            new_config={},
            reason="test",
        )

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert isinstance(doc["timestamp"], datetime)

    @patch("neural_hive_specialists.compliance.audit_logger.MongoClient")
    def test_default_severity_for_config_change_is_warning(self, mock_mongo_class, config):
        """Testa que severidade padrão para config_change é 'warning'."""
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_mongo_class.return_value = mock_client

        from neural_hive_specialists.compliance.audit_logger import AuditLogger

        logger = AuditLogger(config, specialist_type="test_specialist")

        logger.log_config_change(
            changed_by="user123",
            old_config={},
            new_config={},
            reason="test",
        )

        call_args = mock_collection.insert_one.call_args
        doc = call_args[0][0]

        assert doc["severity"] == "warning"
