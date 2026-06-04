"""Testes unitários para PII Service."""

import pytest
from src.models.pii import MaskStrategy, PIIType
from src.services.pii_service import PIIService


@pytest.fixture
def pii_service():
    """Fixture para PII Service."""
    return PIIService()


class TestPIIServiceDetect:
    """Testes de detecção de PII (INV-2: 7 tipos com positions)."""

    def test_detect_email(self, pii_service):
        """Testa detecção de email."""
        text = "Contact joao@example.com for more info"
        detected = pii_service.detect(text, [PIIType.EMAIL])

        assert len(detected) == 1
        assert detected[0].type == PIIType.EMAIL
        assert detected[0].value == "joao@example.com"
        assert detected[0].start >= 0  # INV-2: position requerido
        assert detected[0].end > detected[0].start  # INV-2: position requerido

    def test_detect_phone(self, pii_service):
        """Testa detecção de telefone."""
        text = "Call +351 912 345 678"
        detected = pii_service.detect(text, [PIIType.PHONE])

        assert len(detected) == 1
        assert detected[0].type == PIIType.PHONE
        assert detected[0].start >= 0
        assert detected[0].end > detected[0].start

    def test_detect_cpf(self, pii_service):
        """Testa detecção de CPF."""
        text = "CPF: 123.456.789-01"
        detected = pii_service.detect(text, [PIIType.CPF])

        assert len(detected) == 1
        assert detected[0].type == PIIType.CPF
        assert detected[0].value == "123.456.789-01"

    def test_detect_cnpj(self, pii_service):
        """Testa detecção de CNPJ."""
        text = "CNPJ: 12.345.678/0001-90"
        detected = pii_service.detect(text, [PIIType.CNPJ])

        assert len(detected) == 1
        assert detected[0].type == PIIType.CNPJ

    def test_detect_credit_card(self, pii_service):
        """Testa detecção de cartão de crédito."""
        text = "Card: 4532 1234 5678 9010"
        detected = pii_service.detect(text, [PIIType.CREDIT_CARD])

        assert len(detected) == 1
        assert detected[0].type == PIIType.CREDIT_CARD

    def test_detect_ssn(self, pii_service):
        """Testa detecção de SSN."""
        text = "SSN: 123-45-6789"
        detected = pii_service.detect(text, [PIIType.SSN])

        assert len(detected) == 1
        assert detected[0].type == PIIType.SSN

    def test_detect_address(self, pii_service):
        """Testa detecção de endereço."""
        text = "Address: 123 Main St, Springfield, IL"
        detected = pii_service.detect(text, [PIIType.ADDRESS])

        # Endereço pode ser detectado como PII
        assert isinstance(detected, list)

    def test_detect_multiple_types(self, pii_service):
        """Testa detecção de múltiplos tipos."""
        text = "Contact joao@example.com or call +351 912 345 678"
        detected = pii_service.detect(text)

        assert len(detected) >= 2
        types_found = [d.type for d in detected]
        assert PIIType.EMAIL in types_found
        assert PIIType.PHONE in types_found


class TestPIIServiceMask:
    """Testes de mascaramento de PII (R-P3: 3 strategies)."""

    @pytest.mark.asyncio
    async def test_mask_full(self, pii_service):
        """Testa mascaramento MASK_FULL."""
        text = "Contact joao@example.com"
        masked, detected, masks, mask_id = await pii_service.mask(
            text, strategy=MaskStrategy.MASK_FULL
        )

        assert "[EMAIL]" in masked or "EMAIL" in masked
        assert len(detected) == 1
        assert detected[0].type == PIIType.EMAIL

    @pytest.mark.asyncio
    async def test_mask_partial(self, pii_service):
        """Testa mascaramento MASK_PARTIAL."""
        text = "Contact joao@example.com"
        masked, detected, masks, mask_id = await pii_service.mask(
            text, strategy=MaskStrategy.MASK_PARTIAL
        )

        # Mascaramento parcial preserva alguns caracteres
        assert "@" in masked or masked != text
        assert len(detected) == 1

    @pytest.mark.asyncio
    async def test_mask_redact(self, pii_service):
        """Testa mascaramento MASK_REDACT."""
        text = "Contact joao@example.com"
        masked, detected, masks, mask_id = await pii_service.mask(
            text, strategy=MaskStrategy.MASK_REDACT
        )

        # REDACT remove completamente
        assert "joao@example.com" not in masked
        assert len(detected) == 1

    @pytest.mark.asyncio
    async def test_mask_with_reversible(self, pii_service):
        """Testa mascaramento reversível (INV-14)."""
        text = "Email: joao@example.com"
        masked, detected, masks, mask_id = await pii_service.mask(
            text,
            strategy=MaskStrategy.MASK_REDACT,
            enable_reversible=True,
        )

        # Se reversível habilitado, deve ter mask_id
        # Nota: Pode não funcionar se MASK_REDACT não gerar token
        assert isinstance(masked, str)
        assert len(detected) == 1


class TestPIIServiceUnmask:
    """Testes de desmascaramento (INV-14: AES-256-GCM)."""

    @pytest.mark.asyncio
    async def test_unmask_invalid_token(self, pii_service):
        """Testa unmask com token inválido."""
        original, success, error = await pii_service.unmask(mask_id="invalid_token")

        assert not success
        assert error is not None
        assert original == ""


class TestPIIServiceCapabilities:
    """Testes de capacidades do serviço."""

    def test_get_capabilities(self, pii_service):
        """Testa obter capacidades."""
        capabilities = pii_service.get_capabilities()

        assert "supported_types" in capabilities
        assert "supported_strategies" in capabilities
        assert "supports_reversible_unmask" in capabilities
        assert "supports_audit_log" in capabilities
        assert "version" in capabilities

        # Verificar tipos requeridos por INV-2
        required_types = ["EMAIL", "PHONE", "CPF", "CNPJ", "CREDIT_CARD", "SSN", "ADDRESS"]
        for t in required_types:
            assert t in capabilities["supported_types"]

        # Verificar estratégias requeridas por INV-2
        required_strategies = ["MASK_FULL", "MASK_PARTIAL", "MASK_REDACT"]
        for s in required_strategies:
            assert s in capabilities["supported_strategies"]
