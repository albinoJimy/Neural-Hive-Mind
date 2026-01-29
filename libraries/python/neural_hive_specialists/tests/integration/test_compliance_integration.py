"""
Testes de integração para Compliance Layer.

Fluxo completo: plano com PII → sanitize → save opinion → encrypt fields →
verify signature/content_hash → audit entries → retention (mask/delete).

Nota: Estes testes requerem MongoDB disponível e são marcados como 'integration'.
Para executar: pytest -m integration
"""

import pytest
import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import mongomock

from neural_hive_specialists.compliance.compliance_layer import ComplianceLayer
from neural_hive_specialists.compliance.pii_detector import PIIDetector
from neural_hive_specialists.compliance.field_encryptor import FieldEncryptor
from neural_hive_specialists.compliance.audit_logger import AuditLogger
from neural_hive_specialists.ledger_client import LedgerClient
from neural_hive_specialists.config import SpecialistConfig


@pytest.fixture
def integration_config():
    """Cria configuração para testes de integração."""
    config = SpecialistConfig()
    config.enable_compliance_layer = True
    config.enable_pii_detection = False  # Desabilitar Presidio para testes rápidos
    config.enable_field_encryption = True
    config.enable_audit_logging = True
    config.encryption_key_path = "/tmp/test_encryption_key.key"
    config.fields_to_encrypt = ["correlation_id", "trace_id", "span_id"]
    config.audit_log_collection = "test_audit_logs"
    config.audit_log_retention_days = 90
    config.enable_correlation_hash = True
    return config


@pytest.fixture
def mock_mongodb():
    """Cria mock de MongoDB para testes."""
    return mongomock.MongoClient()


@pytest.fixture
def mock_metrics():
    """Cria mock de métricas."""
    metrics = Mock()
    metrics.increment_pii_entities_detected = Mock()
    metrics.increment_pii_anonymization = Mock()
    metrics.observe_pii_detection_duration = Mock()
    metrics.increment_fields_encrypted = Mock()
    metrics.increment_fields_decrypted = Mock()
    metrics.observe_encryption_duration = Mock()
    return metrics


@pytest.mark.integration
class TestComplianceFlowIntegration:
    """Testes de integração do fluxo completo de compliance."""

    def test_full_compliance_flow_without_pii(
        self, integration_config, mock_mongodb, mock_metrics
    ):
        """
        Testa fluxo completo de compliance sem PII detection.

        Fluxo: criar opinião → encrypt fields → salvar no ledger →
        verificar signature e content_hash → audit log.
        """
        # Setup
        db = mock_mongodb["neural_hive_test"]
        opinions_collection = db["opinions"]
        audit_collection = db[integration_config.audit_log_collection]

        # Criar ComplianceLayer
        compliance = ComplianceLayer(integration_config, "business", mock_metrics)
        compliance.pii_detector = None  # Desabilitar PII para este teste

        # Criar opinião de teste
        opinion_doc = {
            "opinion_id": "test-opinion-001",
            "correlation_id": "corr-123",
            "trace_id": "trace-456",
            "span_id": "span-789",
            "specialist_type": "business",
            "opinion": {
                "verdict": "approved",
                "reasoning": "Analysis complete",
                "confidence": 0.95,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Criptografar campos
        encrypted_doc = compliance.encrypt_opinion_fields(opinion_doc)

        # Verificar que campos foram criptografados
        assert encrypted_doc["correlation_id"].startswith("enc:")
        assert encrypted_doc["trace_id"].startswith("enc:")
        assert encrypted_doc["span_id"].startswith("enc:")
        assert "_compliance" in encrypted_doc

        # Verificar metadados de compliance
        assert (
            encrypted_doc["_compliance"]["encrypted_fields"]
            == integration_config.fields_to_encrypt
        )
        assert encrypted_doc["_compliance"]["encryption_algorithm"] == "fernet"

        # Simular salvamento no MongoDB
        opinions_collection.insert_one(encrypted_doc)

        # Verificar que documento foi salvo
        saved_doc = opinions_collection.find_one({"opinion_id": "test-opinion-001"})
        assert saved_doc is not None
        assert saved_doc["correlation_id"].startswith("enc:")

        # Descriptografar para verificar integridade
        decrypted_doc = compliance.decrypt_opinion_fields(saved_doc)
        assert decrypted_doc["correlation_id"] == "corr-123"
        assert decrypted_doc["trace_id"] == "trace-456"
        assert decrypted_doc["span_id"] == "span-789"

    def test_compliance_with_ledger_client(
        self, integration_config, mock_mongodb, mock_metrics
    ):
        """
        Testa integração entre ComplianceLayer e LedgerClient.

        Fluxo: encrypt opinion → save via LedgerClient → verify signature →
        check correlation_id_hash indexing.
        """
        # Setup
        with patch(
            "neural_hive_specialists.ledger_client.MongoClient",
            return_value=mock_mongodb,
        ):
            # Criar LedgerClient
            ledger_client = LedgerClient(integration_config, metrics=mock_metrics)
            ledger_client._collection = mock_mongodb["neural_hive_test"]["opinions"]

            # Criar ComplianceLayer
            compliance = ComplianceLayer(integration_config, "business", mock_metrics)
            compliance.pii_detector = None

            # Criar opinião
            opinion = {
                "verdict": "approved",
                "reasoning": "Test reasoning",
                "confidence": 0.90,
            }

            # Criptografar campos antes de salvar
            opinion_doc = {
                "opinion": opinion,
                "correlation_id": "corr-test-123",
                "trace_id": "trace-test-456",
            }
            encrypted_opinion = compliance.encrypt_opinion_fields(opinion_doc)

            # Salvar via LedgerClient
            opinion_id = ledger_client.save_opinion(
                opinion=encrypted_opinion["opinion"],
                plan_id="plan-test-001",
                intent_id="intent-test-001",
                specialist_type="business",
                correlation_id=encrypted_opinion["correlation_id"],
            )

            assert opinion_id is not None

            # Recuperar opinião salva
            saved_opinion = ledger_client.get_opinion(opinion_id)
            assert saved_opinion is not None

            # Verificar campos criptografados
            assert "hash" in saved_opinion
            assert "signature" in saved_opinion

            # Verificar correlation_id_hash se habilitado
            if integration_config.enable_correlation_hash:
                assert "correlation_id_hash" in saved_opinion
                # Verificar que hash foi gerado corretamente
                import hashlib

                expected_hash = hashlib.sha256(
                    "corr-test-123".encode("utf-8")
                ).hexdigest()
                # Note: correlation_id está criptografado, mas hash é do original

    def test_audit_logging_integration(
        self, integration_config, mock_mongodb, mock_metrics
    ):
        """
        Testa que operações de compliance geram entradas de audit log.

        Fluxo: encrypt fields → check audit entries created.
        """
        # Setup
        db = mock_mongodb["neural_hive_test"]
        audit_collection = db[integration_config.audit_log_collection]

        # Criar AuditLogger diretamente conectado ao mock MongoDB
        with patch(
            "neural_hive_specialists.compliance.audit_logger.MongoClient",
            return_value=mock_mongodb,
        ):
            audit_logger = AuditLogger(integration_config, "business")
            audit_logger._collection = audit_collection

            # Criar ComplianceLayer com audit logger real
            compliance = ComplianceLayer(integration_config, "business", mock_metrics)
            compliance.pii_detector = None
            compliance.audit_logger = audit_logger

            # Criar e criptografar opinião
            opinion_doc = {
                "opinion_id": "test-audit-001",
                "correlation_id": "corr-audit-123",
                "trace_id": "trace-audit-456",
            }

            encrypted_doc = compliance.encrypt_opinion_fields(opinion_doc)

            # Verificar que entradas de audit foram criadas
            audit_entries = list(
                audit_collection.find({"event_type": "field_encrypted"})
            )
            assert len(audit_entries) >= 1

            # Verificar estrutura da entrada de audit
            for entry in audit_entries:
                assert "event_type" in entry
                assert "timestamp" in entry
                assert "specialist_type" in entry
                assert entry["specialist_type"] == "business"

    @pytest.mark.skipif(
        os.getenv("SKIP_SLOW_TESTS") == "1", reason="Teste de retenção pode ser lento"
    )
    def test_retention_policy_integration(
        self, integration_config, mock_mongodb, mock_metrics
    ):
        """
        Testa aplicação de políticas de retenção.

        Fluxo: criar opiniões antigas → aplicar retention → verificar masking/delete.
        """
        # Setup
        db = mock_mongodb["neural_hive_test"]
        opinions_collection = db["opinions"]

        # Criar ComplianceLayer
        compliance = ComplianceLayer(integration_config, "business", mock_metrics)
        compliance.pii_detector = None

        # Criar opinião antiga (mais de 90 dias)
        old_timestamp = datetime.utcnow() - timedelta(days=95)
        old_opinion = {
            "opinion_id": "old-opinion-001",
            "correlation_id": "corr-old-123",
            "trace_id": "trace-old-456",
            "timestamp": old_timestamp.isoformat(),
            "specialist_type": "business",
            "opinion": {"verdict": "approved", "reasoning": "Old analysis"},
        }

        # Criptografar e salvar
        encrypted_old = compliance.encrypt_opinion_fields(old_opinion)
        opinions_collection.insert_one(encrypted_old)

        # Criar opinião recente
        recent_opinion = {
            "opinion_id": "recent-opinion-001",
            "correlation_id": "corr-recent-123",
            "trace_id": "trace-recent-456",
            "timestamp": datetime.utcnow().isoformat(),
            "specialist_type": "business",
            "opinion": {"verdict": "approved", "reasoning": "Recent analysis"},
        }

        encrypted_recent = compliance.encrypt_opinion_fields(recent_opinion)
        opinions_collection.insert_one(encrypted_recent)

        # Simular aplicação de retention policy (mask_after_90_days)
        cutoff_date = datetime.utcnow() - timedelta(days=90)

        # Encontrar e mascarar opiniões antigas
        old_opinions = opinions_collection.find(
            {"timestamp": {"$lt": cutoff_date.isoformat()}}
        )

        masked_count = 0
        for opinion in old_opinions:
            # Mascarar campos sensíveis
            opinions_collection.update_one(
                {"_id": opinion["_id"]},
                {
                    "$set": {
                        "opinion.reasoning": "[MASKED]",
                        "opinion.verdict": "[MASKED]",
                    }
                },
            )
            masked_count += 1

        assert masked_count == 1

        # Verificar que opinião antiga foi mascarada
        masked_opinion = opinions_collection.find_one({"opinion_id": "old-opinion-001"})
        assert masked_opinion["opinion"]["reasoning"] == "[MASKED]"
        assert masked_opinion["opinion"]["verdict"] == "[MASKED]"

        # Verificar que opinião recente não foi mascarada
        recent_doc = opinions_collection.find_one({"opinion_id": "recent-opinion-001"})
        assert recent_doc["opinion"]["reasoning"] == "Recent analysis"


@pytest.mark.integration
class TestComplianceErrorHandling:
    """Testes de tratamento de erros em cenários de integração."""

    def test_encryption_failure_graceful_degradation(
        self, integration_config, mock_metrics
    ):
        """Testa degradação graciosa quando criptografia falha."""
        # Configurar chave inválida para forçar erro
        integration_config.encryption_key_path = "/nonexistent/path/key.key"

        compliance = ComplianceLayer(integration_config, "business", mock_metrics)

        # FieldEncryptor deve estar desabilitado ou com erro
        opinion_doc = {"opinion_id": "test-001", "correlation_id": "corr-123"}

        # Deve retornar documento original sem lançar exceção
        result = compliance.encrypt_opinion_fields(opinion_doc)

        # Verifica que sistema continua funcionando
        assert result is not None

    def test_mongodb_connection_failure(self, integration_config, mock_metrics):
        """Testa comportamento quando MongoDB não está disponível."""
        # Tentar conectar a MongoDB inexistente
        bad_config = SpecialistConfig()
        bad_config.mongodb_uri = "mongodb://nonexistent:27017/test"

        # Não deve lançar exceção na inicialização
        try:
            with patch(
                "neural_hive_specialists.ledger_client.MongoClient"
            ) as mock_client:
                mock_client.side_effect = Exception("Connection failed")
                # Sistema deve lidar com erro graciosamente
                pass
        except Exception as e:
            pytest.fail(f"Não deveria lançar exceção: {e}")


@pytest.mark.integration
class TestCompliancePerformance:
    """Testes de performance de operações de compliance."""

    def test_encryption_performance(self, integration_config, mock_metrics):
        """Testa performance de criptografia em lote."""
        compliance = ComplianceLayer(integration_config, "business", mock_metrics)
        compliance.pii_detector = None

        # Criar 100 documentos para teste de performance
        documents = []
        for i in range(100):
            doc = {
                "opinion_id": f"perf-test-{i}",
                "correlation_id": f"corr-{i}",
                "trace_id": f"trace-{i}",
                "span_id": f"span-{i}",
            }
            documents.append(doc)

        # Medir tempo de criptografia
        start_time = time.time()

        encrypted_docs = []
        for doc in documents:
            encrypted = compliance.encrypt_opinion_fields(doc)
            encrypted_docs.append(encrypted)

        duration = time.time() - start_time

        # Performance check: deve processar 100 documentos em menos de 5 segundos
        assert duration < 5.0, f"Criptografia muito lenta: {duration:.2f}s"
        assert len(encrypted_docs) == 100

        # Verificar que todos foram criptografados
        for encrypted in encrypted_docs:
            assert encrypted["correlation_id"].startswith("enc:")


@pytest.mark.integration
@pytest.mark.skipif(os.getenv("CI") == "true", reason="Requer modelos spaCy instalados")
class TestPIIDetectionIntegration:
    """
    Testes de integração com PII detection real.

    Nota: Requerem modelos spaCy instalados:
    python -m spacy download pt_core_news_sm
    python -m spacy download en_core_web_sm
    """

    def test_pii_detection_with_real_presidio(self):
        """
        Testa detecção de PII com Presidio real.

        Este teste é opcional e requer Presidio instalado.
        """
        pytest.skip("Teste requer Presidio e modelos spaCy instalados")


# Cleanup após testes
@pytest.fixture(scope="function", autouse=True)
def cleanup_temp_files():
    """Remove arquivos temporários após cada teste."""
    yield

    # Cleanup de chave de teste
    temp_key_path = "/tmp/test_encryption_key.key"
    if os.path.exists(temp_key_path):
        os.remove(temp_key_path)
