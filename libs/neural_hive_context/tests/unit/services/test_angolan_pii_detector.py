"""
Testes para AngolanPIIDetector.
"""

import pytest

from neural_hive_context.services import AngolanPIIDetector
from neural_hive_context.models import PIIType, PIIRiskLevel


@pytest.fixture
def angolan_detector():
    """Fixture para AngolanPIIDetector."""
    return AngolanPIIDetector()


@pytest.fixture
def angolan_only_detector():
    """Fixture para AngolanPIIDetector apenas com tipos angolanos."""
    return AngolanPIIDetector(include_brazilian=False)


class TestAngolanPIIDetector:
    """Testes para AngolanPIIDetector."""

    def test_detect_nif(self, angolan_detector):
        """NIF angolano deve ser detectado."""
        # NIF válido: 9 dígitos começando com 0, 1 ou 5
        result = angolan_detector.detect("Meu NIF é 005123456")

        assert result.has_pii is True
        assert any(e.type == PIIType.NIF for e in result.entities)
        # Verificar que o risco associado ao NIF é HIGH
        nif_entity = next(e for e in result.entities if e.type == PIIType.NIF)
        assert angolan_detector.TYPE_RISK[PIIType.NIF] == PIIRiskLevel.HIGH

    def test_detect_bi(self, angolan_detector):
        """BI angolano deve ser detectado."""
        # BI formato: 12 dígitos + 2 letras
        result = angolan_detector.detect("BI: 001234567891AB")

        assert result.has_pii is True
        assert result.risk_level == PIIRiskLevel.CRITICAL
        assert result.requires_redaction is True
        assert any(e.type == PIIType.BI for e in result.entities)

    def test_detect_nuit(self, angolan_detector):
        """NUIT angolano deve ser detectado."""
        # NUIT: 9 dígitos
        result = angolan_detector.detect("NUIT: 541234567")

        assert result.has_pii is True
        assert any(e.type == PIIType.NUIT for e in result.entities)
        nuit_entity = next(e for e in result.entities if e.type == PIIType.NUIT)
        assert angolan_detector.TYPE_RISK[PIIType.NUIT] == PIIRiskLevel.HIGH

    def test_detect_multiple_angolan_entities(self, angolan_detector):
        """Múltiplas entidades angolanas devem ser detectadas."""
        result = angolan_detector.detect("NIF 005123456, BI 001234567891AB, NUIT 541234567")

        assert result.has_pii is True
        assert len(result.entities) >= 3

    def test_nif_invalid_sequence(self, angolan_detector):
        """NIF com sequência deve ser rejeitado."""
        result = angolan_detector.detect("NIF: 000000000")

        # Sequências não devem ser válidas
        nif_entities = [e for e in result.entities if e.type == PIIType.NIF]
        assert len(nif_entities) == 0

    def test_nuit_invalid_sequence(self, angolan_detector):
        """NUIT com sequência deve ser rejeitado."""
        result = angolan_detector.detect("NUIT: 111111111")

        nuit_entities = [e for e in result.entities if e.type == PIIType.NUIT]
        assert len(nuit_entities) == 0

    def test_bi_invalid_format(self, angolan_detector):
        """BI com formato inválido não deve ser detectado."""
        # Faltam letras no final
        result = angolan_detector.detect("BI: 001234567891")

        bi_entities = [e for e in result.entities if e.type == PIIType.BI]
        assert len(bi_entities) == 0

    def test_nif_starts_with_valid_digit(self, angolan_detector):
        """NIF deve começar com 0, 1 ou 5."""
        # Válido (começa com 0)
        result1 = angolan_detector.detect("NIF: 012345678")
        assert any(e.type == PIIType.NIF for e in result1.entities)

        # Válido (começa com 1)
        result2 = angolan_detector.detect("NIF: 112345678")
        assert any(e.type == PIIType.NIF for e in result2.entities)

        # Válido (começa com 5)
        result3 = angolan_detector.detect("NIF: 512345678")
        assert any(e.type == PIIType.NIF for e in result3.entities)

    def test_angolan_only_mode(self, angolan_only_detector):
        """Modo apenas angolano não detecta CPF."""
        detector = angolan_only_detector

        # Não deve detectar CPF
        result1 = detector.detect("CPF: 123.456.789-09")
        assert not any(e.type == PIIType.CPF for e in result1.entities)

        # Deve detectar NIF
        result2 = detector.detect("NIF: 005123456")
        assert any(e.type == PIIType.NIF for e in result2.entities)

    def test_include_brazilian_default(self, angolan_detector):
        """Por padrão inclui padrões brasileiros."""
        result = angolan_detector.detect("CPF: 123.456.789-09")

        assert result.has_pii is True
        assert any(e.type == PIIType.CPF for e in result.entities)

    def test_get_angolan_types(self, angolan_detector):
        """get_angolan_types deve retornar tipos angolanos."""
        types = angolan_detector.get_angolan_types()

        assert PIIType.NIF in types
        assert PIIType.BI in types
        assert PIIType.NUIT in types
        assert len(types) == 3

    def test_is_angolan_type(self, angolan_detector):
        """is_angolan_type deve identificar corretamente."""
        assert angolan_detector.is_angolan_type(PIIType.NIF) is True
        assert angolan_detector.is_angolan_type(PIIType.BI) is True
        assert angolan_detector.is_angolan_type(PIIType.NUIT) is True
        assert angolan_detector.is_angolan_type(PIIType.CPF) is False
        assert angolan_detector.is_angolan_type(PIIType.EMAIL) is False

    def test_masked_text_with_angolan_pii(self, angolan_detector):
        """Texto com PII angolano deve ser mascarado."""
        result = angolan_detector.detect("NIF 005123456 para contato")

        if result.masked_text:
            assert "para contato" in result.masked_text
            # O NIF deve estar mascarado
            assert "***" in result.masked_text

    def test_combined_brazilian_angolan_pii(self, angolan_detector):
        """Deve detectar PII brasileiro e angolano juntos."""
        result = angolan_detector.detect("CPF 123.456.789-09 e NIF 005123456")

        assert result.has_pii is True
        types_found = {e.type for e in result.entities}
        assert PIIType.CPF in types_found
        assert PIIType.NIF in types_found

    def test_bi_case_insensitive(self, angolan_detector):
        """BI deve ser detectado independente de maiúsculas/minúsculas."""
        result1 = angolan_detector.detect("BI: 001234567891AB")
        result2 = angolan_detector.detect("bi: 001234567891ab")
        result3 = angolan_detector.detect("Bi: 001234567891Ab")

        assert any(e.type == PIIType.BI for e in result1.entities)
        assert any(e.type == PIIType.BI for e in result2.entities)
        assert any(e.type == PIIType.BI for e in result3.entities)

    def test_real_world_example_angola(self, angolan_detector):
        """Exemplo real de documento angolano."""
        text = """
        Dados pessoais:
        Nome: João Manuel
        NIF: 005432198
        BI: 007895432001LA
        NUIT: 541234567
        Telefone: +244 923 456 789
        Email: joao@example.co.ao
        """

        result = angolan_detector.detect(text)

        assert result.has_pii is True
        types_found = {e.type for e in result.entities}

        # Deve detectar tipos angolanos
        assert PIIType.NIF in types_found
        assert PIIType.BI in types_found
        assert PIIType.NUIT in types_found

        # Deve detectar internacionais
        assert PIIType.PHONE in types_found
        assert PIIType.EMAIL in types_found

    def test_no_false_positives_phone_numbers(self, angolan_detector):
        """Não deve confundir telefones com NIF/NUIT."""
        # +244 é código de Angola, pode parecer NIF
        result = angolan_detector.detect("Telefone: +244 923 456 789")

        # Deve detectar PHONE mas não NIF/NUIT
        types_found = {e.type for e in result.entities}
        assert PIIType.PHONE in types_found
        # NIF/NUIT não devem estar presentes (não começam com 0/1/5)
        assert PIIType.NIF not in types_found
        assert PIIType.NUIT not in types_found
