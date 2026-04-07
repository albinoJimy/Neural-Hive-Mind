"""
Testes unitários para PIIDetectorLite.

Cobertura: versão leve sem Presidio, detecção via regex, compatibilidade de interface,
anonymize_text, detect_pii.
"""

import pytest
from unittest.mock import Mock, patch
from neural_hive_specialists.compliance.pii_detector import PIIDetectorLite
from neural_hive_specialists.compliance.pii_patterns import PIIType


@pytest.mark.unit
class TestPIIDetectorLiteInitialization:
    """Testes de inicialização do PIIDetectorLite."""

    def test_initialization_success(self):
        """Testa inicialização bem-sucedida."""
        detector = PIIDetectorLite()

        assert detector.enabled is True
        assert detector.masker is not None
        assert detector.pattern_registry is not None

    def test_initialization_without_config(self):
        """Testa inicialização sem config (usa defaults)."""
        detector = PIIDetectorLite(config=None)

        assert detector.enabled is True

    def test_initialization_handles_import_error(self):
        """Testa tratamento de erro ao importar dependências."""
        with patch(
            "neural_hive_specialists.compliance.pii_masker.PIIMasker",
            side_effect=ImportError("No module named 'missing_module'"),
        ):
            detector = PIIDetectorLite()

            assert detector.enabled is False
            assert detector.masker is None


@pytest.mark.unit
class TestPIIDetectorLiteDetectPII:
    """Testes do método detect_pii do PIIDetectorLite."""

    @pytest.fixture
    def detector(self):
        return PIIDetectorLite()

    def test_detect_pii_empty_string(self, detector):
        """Testa detecção em string vazia."""
        result = detector.detect_pii("")

        assert result == []

    def test_detect_pii_no_pii(self, detector):
        """Testa texto sem PII retorna lista vazia."""
        result = detector.detect_pii("Este texto não tem informações sensíveis.")

        assert result == []

    def test_detect_pii_returns_list_of_dicts(self, detector):
        """Testa que resultado é lista de dicionários."""
        result = detector.detect_pii("Email: test@example.com")

        assert isinstance(result, list)
        if len(result) > 0:
            assert isinstance(result[0], dict)

    def test_detect_pii_dict_structure(self, detector):
        """Testa estrutura dos dicionários retornados."""
        result = detector.detect_pii("Email: test@example.com")

        if len(result) > 0:
            entity = result[0]
            required_keys = ["entity_type", "start", "end", "score", "value"]
            for key in required_keys:
                assert key in entity, f"Key {key} not found in entity"

    def test_detect_pii_email(self, detector):
        """Testa detecção de email."""
        result = detector.detect_pii("Contact: user@example.com")

        assert len(result) >= 1
        assert any(e["entity_type"] == "EMAIL" for e in result)

    def test_detect_pii_cpf(self, detector):
        """Testa detecção de CPF."""
        result = detector.detect_pii("CPF: 123.456.789-00")

        assert len(result) >= 1
        assert any(e["entity_type"] == "CPF" for e in result)

    def test_detect_pii_multiple_entities(self, detector):
        """Testa detecção de múltiplas entidades."""
        text = "Email: user@example.com, CPF: 123.456.789-00"
        result = detector.detect_pii(text)

        assert len(result) >= 2

    def test_detect_pii_disabled(self):
        """Testa detector desabilitado retorna lista vazia."""
        with patch(
            "neural_hive_specialists.compliance.pii_masker.PIIMasker",
            side_effect=ImportError("Import error"),
        ):
            detector = PIIDetectorLite()
            result = detector.detect_pii("Email: test@example.com")

            assert result == []

    def test_detect_pii_language_parameter_ignored(self, detector):
        """Testa que parâmetro language é aceito mas pode ser ignorado."""
        # Lite version não usa language da mesma forma
        result_pt = detector.detect_pii("Email: test@example.com", language="pt")
        result_en = detector.detect_pii("Email: test@example.com", language="en")

        # Ambos devem detectar o email
        assert len(result_pt) >= 1
        assert len(result_en) >= 1


@pytest.mark.unit
class TestPIIDetectorLiteAnonymizeText:
    """Testes do método anonymize_text do PIIDetectorLite."""

    @pytest.fixture
    def detector(self):
        return PIIDetectorLite()

    def test_anonymize_text_returns_tuple(self, detector):
        """Testa que retorna tupla (texto, metadata)."""
        result = detector.anonymize_text("Email: test@example.com")

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_anonymize_text_first_element_is_string(self, detector):
        """Testa que primeiro elemento é string (texto mascarado)."""
        text, metadata = detector.anonymize_text("Email: test@example.com")

        assert isinstance(text, str)

    def test_anonymize_text_second_element_is_list(self, detector):
        """Testa que segundo elemento é lista (metadata)."""
        text, metadata = detector.anonymize_text("Email: test@example.com")

        assert isinstance(metadata, list)

    def test_anonymize_text_masks_email(self, detector):
        """Testa que email é mascarado."""
        text, metadata = detector.anonymize_text("Contact: user@example.com")

        assert "user@example.com" not in text
        assert len(metadata) >= 1

    def test_anonymize_text_masks_cpf(self, detector):
        """Testa que CPF é mascarado."""
        text, metadata = detector.anonymize_text("CPF: 123.456.789-00")

        assert "123.456.789-00" not in text or text.count("*") > 0
        assert len(metadata) >= 1

    def test_anonymize_text_metadata_structure(self, detector):
        """Testa estrutura dos metadados."""
        text, metadata = detector.anonymize_text("Email: test@example.com")

        if len(metadata) > 0:
            entity = metadata[0]
            required_keys = ["entity_type", "start", "end", "score", "value"]
            for key in required_keys:
                assert key in entity

    def test_anonymize_text_empty_string(self, detector):
        """Testa anonimização de string vazia."""
        text, metadata = detector.anonymize_text("")

        assert text == ""
        assert metadata == []

    def test_anonymize_text_no_pii(self, detector):
        """Testa texto sem PII retorna original."""
        original = "Texto sem informações sensíveis."
        text, metadata = detector.anonymize_text(original)

        assert text == original
        assert metadata == []

    def test_anonymize_text_multiple_pii(self, detector):
        """Testa anonimização de múltiplos PII."""
        text, metadata = detector.anonymize_text("Email: user@example.com, CPF: 123.456.789-00")

        assert len(metadata) >= 2
        assert "user@example.com" not in text
        assert "123.456.789-00" not in text or text.count("*") > 0

    def test_anonymize_text_disabled(self):
        """Testa detector desabilitado retorna original."""
        with patch(
            "neural_hive_specialists.compliance.pii_masker.PIIMasker",
            side_effect=ImportError("Import error"),
        ):
            detector = PIIDetectorLite()
            text, metadata = detector.anonymize_text("Email: test@example.com")

            # Com erro, retorna texto original
            assert isinstance(text, str)

    def test_anonymize_text_language_parameter(self, detector):
        """Testa que parâmetro language é aceito."""
        # Lite version aceita language mas pode não usá-lo
        text, metadata = detector.anonymize_text("Email: test@example.com", language="pt")

        assert isinstance(text, str)
        assert isinstance(metadata, list)


@pytest.mark.unit
class TestPIIDetectorLiteIsEnabled:
    """Testes do método is_enabled."""

    def test_is_enabled_when_initialized(self):
        """Testa is_enabled retorna True quando inicializado corretamente."""
        detector = PIIDetectorLite()

        assert detector.is_enabled() is True

    def test_is_enabled_when_import_failed(self):
        """Testa is_enabled retorna False quando import falhou."""
        with patch(
            "neural_hive_specialists.compliance.pii_masker.PIIMasker",
            side_effect=ImportError("Import error"),
        ):
            detector = PIIDetectorLite()

            assert detector.is_enabled() is False


@pytest.mark.unit
class TestPIIDetectorLiteCompatibility:
    """Testes de compatibilidade com interface do PIIDetector."""

    @pytest.fixture
    def detector(self):
        return PIIDetectorLite()

    def test_detect_pii_signature_compatible(self, detector):
        """Testa que assinatura é compatível com PIIDetector."""
        # Ambos aceitam text e language
        result = detector.detect_pii("test", language="pt")

        assert isinstance(result, list)

    def test_anonymize_text_signature_compatible(self, detector):
        """Testa que assinatura de anonymize_text é compatível."""
        # Ambos retornam (str, list)
        result = detector.anonymize_text("test", language="pt")

        assert isinstance(result, tuple)
        assert isinstance(result[0], str)
        assert isinstance(result[1], list)

    def test_metadata_format_compatible(self, detector):
        """Testa que formato de metadados é compatível."""
        text, metadata = detector.anonymize_text("Email: test@example.com")

        if len(metadata) > 0:
            # Formato deve ser compatível com Presidio
            entity = metadata[0]
            assert "entity_type" in entity or "type" in entity
            assert "start" in entity
            assert "end" in entity
            assert "score" in entity or "confidence" in entity


@pytest.mark.unit
class TestPIIDetectorLiteRealScenarios:
    """Testes de cenários reais com PIIDetectorLite."""

    @pytest.fixture
    def detector(self):
        return PIIDetectorLite()

    def test_user_profile_text(self, detector):
        """Testa perfil de usuário com múltiplos PII."""
        text = """
        Nome: João Silva
        Email: joao.silva@example.com
        Telefone: (11) 99999-9999
        CPF: 123.456.789-00
        """

        anonymized, metadata = detector.anonymize_text(text)

        # Deve detectar pelo menos email e CPF
        assert len(metadata) >= 2
        assert "joao.silva@example.com" not in anonymized
        assert "123.456.789-00" not in anonymized or anonymized.count("*") > 0

    def test_log_entry_with_ip(self, detector):
        """Testa entrada de log com IP address."""
        text = "User access from 192.168.1.100 at 2024-01-01"

        anonymized, metadata = detector.anonymize_text(text)

        # IP deve ser mascarado
        assert "192.168.1.100" not in anonymized or "*" in anonymized

    def test_credit_card_in_text(self, detector):
        """Testa cartão de crédito em texto."""
        text = "Payment with card 4532 1234 5678 9010 was approved"

        anonymized, metadata = detector.anonymize_text(text)

        assert len(metadata) >= 1
        assert "4532 1234 5678 9010" not in anonymized

    def test_mixed_brazilian_pii(self, detector):
        """Testa múltiplos PII brasileiros."""
        text = "RG: 12.345.678-9, CNPJ: 12.345.678/0001-99"

        anonymized, metadata = detector.anonymize_text(text)

        # Deve detectar CNPJ (RG pattern é genérico)
        assert len(metadata) >= 1
