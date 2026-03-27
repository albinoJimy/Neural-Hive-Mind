"""Testes de PII Masker."""
import pytest
from neural_hive_specialists.compliance.pii_masker import (
    PIIMasker,
    MaskStrategy,
    MaskResult,
    PIIType,
    create_masker,
)


class TestPIIMasker:
    """Testa mascaramento de PII."""

    def test_mask_email_partial(self):
        masker = create_masker(strategy=MaskStrategy.PARTIAL)
        result = masker.mask("Contact: john@example.com")
        assert "john@example.com" not in result.text
        assert "j***" in result.text or "jo***" in result.text

    def test_mask_cpf_partial(self):
        masker = create_masker()
        result = masker.mask("CPF: 123.456.789-00")
        # Verificar que CPF foi mascarado e formato preservado
        assert "123.456." in result.text  # Primeiros 6 caracteres preservados
        assert "-**" in result.text  # Últimos 2 com máscara
        assert result.metadata["total"] == 1

    def test_mask_phone_preserves_format(self):
        masker = create_masker()
        # Formato que casa com o pattern atual (sem espaço extra no meio)
        result = masker.mask("+351 912345678")
        assert "+351" in result.text  # Código do país preservado
        assert "***" in result.text or "* *" in result.text

    def test_full_masking_strategy(self):
        masker = create_masker(strategy=MaskStrategy.FULL)
        result = masker.mask("Email: test@example.com")
        assert "[EMAIL]" in result.text

    def test_multiple_entities(self):
        masker = create_masker()
        result = masker.mask("João Silva - CPF: 123.456.789-00")
        # Deve detectar pelo menos o CPF
        assert result.metadata["total"] >= 1
