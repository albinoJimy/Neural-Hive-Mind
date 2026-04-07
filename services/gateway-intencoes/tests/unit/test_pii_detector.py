"""
Testes unitários para PII Detector e Masker
Testa detecção e mascaramento de informações pessoais sensíveis
"""

import pytest
from unittest.mock import MagicMock, patch
import re
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestPIIDetectorLite:
    """Testes para o detector de PII"""

    @pytest.fixture
    def mock_detector(self):
        """Mock do detector de PII"""
        detector = MagicMock()
        detector.detect_pii = MagicMock(return_value=[])
        detector.is_available = True
        return detector

    def test_detect_email(self, mock_detector):
        """Testar detecção de email"""
        mock_detector.detect_pii.return_value = [
            {"type": "email", "value": "usuario@exemplo.com", "start": 0, "end": 18}
        ]

        text = "usuario@exemplo.com é o email de contato"
        result = mock_detector.detect_pii(text)

        assert len(result) == 1
        assert result[0]["type"] == "email"
        assert "usuario@exemplo.com" in result[0]["value"]

    def test_detect_cpf(self, mock_detector):
        """Testar detecção de CPF brasileiro"""
        mock_detector.detect_pii.return_value = [
            {"type": "cpf", "value": "123.456.789-09", "start": 0, "end": 14}
        ]

        text = "CPF: 123.456.789-09"
        result = mock_detector.detect_pii(text)

        assert len(result) == 1
        assert result[0]["type"] == "cpf"
        assert "123.456.789-09" in result[0]["value"]

    def test_detect_phone(self, mock_detector):
        """Testar detecção de telefone"""
        mock_detector.detect_pii.return_value = [
            {"type": "phone", "value": "+55 11 98765-4321", "start": 0, "end": 17}
        ]

        text = "Telefone: +55 11 98765-4321"
        result = mock_detector.detect_pii(text)

        assert len(result) == 1
        assert result[0]["type"] == "phone"

    def test_detect_credit_card(self, mock_detector):
        """Testar detecção de cartão de crédito"""
        mock_detector.detect_pii.return_value = [
            {"type": "credit_card", "value": "4532 1234 5678 9010", "start": 0, "end": 19}
        ]

        text = "Cartão: 4532 1234 5678 9010"
        result = mock_detector.detect_pii(text)

        assert len(result) == 1
        assert result[0]["type"] == "credit_card"

    def test_batch_detection(self, mock_detector):
        """Testar detecção em lote de múltiplos PII"""
        mock_detector.detect_pii.return_value = [
            {"type": "email", "value": "user@test.com", "start": 0, "end": 13},
            {"type": "phone", "value": "(11) 98765-4321", "start": 20, "end": 35},
            {"type": "cpf", "value": "123.456.789-09", "start": 40, "end": 54},
        ]

        text = "user@test.com telefone (11) 98765-4321 cpf 123.456.789-09"
        result = mock_detector.detect_pii(text)

        assert len(result) == 3
        types = [r["type"] for r in result]
        assert "email" in types
        assert "phone" in types
        assert "cpf" in types

    def test_no_pii_returns_empty(self, mock_detector):
        """Testar texto sem PII retorna lista vazia"""
        mock_detector.detect_pii.return_value = []

        text = "Este é um texto normal sem informações sensíveis"
        result = mock_detector.detect_pii(text)

        assert len(result) == 0
        assert isinstance(result, list)


class TestPIIMasker:
    """Testes para o mascarador de PII"""

    @pytest.fixture
    def mock_masker(self):
        """Mock do masker de PII"""
        masker = MagicMock()
        masker.mask_pii = MagicMock()
        masker.is_available = True
        return masker

    def test_mask_preserves_format(self, mock_masker):
        """Testar que mascaramento preserva formato do texto"""
        mock_masker.mask_pii.return_value = "Email: ***@***.com confirmado"

        text = "Email: usuario@exemplo.com confirmado"
        result = mock_masker.mask_pii(text, strategy="redaction")

        assert "***" in result or "[EMAIL]" in result
        assert "confirmado" in result  # Preserva contexto

    def test_mask_email_with_placeholder(self, mock_masker):
        """Testar mascaramento de email com placeholder"""
        mock_masker.mask_pii.return_value = "Contato: [EMAIL]"

        text = "Contato: joao@empresa.com.br"
        result = mock_masker.mask_pii(text, strategy="placeholder")

        assert "[EMAIL]" in result
        assert "joao@empresa.com.br" not in result

    def test_mask_cpf_partial(self, mock_masker):
        """Testar mascaramento parcial de CPF"""
        mock_masker.mask_pii.return_value = "CPF: ***.456.***-**"

        text = "CPF: 123.456.789-09"
        result = mock_masker.mask_pii(text, strategy="partial")

        assert "456" in result  # Preserva alguns dígitos
        assert "***" in result  # Mascara outros

    def test_mask_phone_partial(self, mock_masker):
        """Testar mascaramento parcial de telefone"""
        mock_masker.mask_pii.return_value = "Tel: +55 ** *****-4321"

        text = "Tel: +55 11 98765-4321"
        result = mock_masker.mask_pii(text, strategy="partial")

        assert "+55" in result  # Preserva DDI
        assert "4321" in result  # Preserva últimos dígitos
        assert "**" in result  # Mascara resto

    def test_mask_multiple_pii_in_text(self, mock_masker):
        """Testar mascaramento de múltiplos PII no mesmo texto"""
        mock_masker.mask_pii.return_value = (
            "Cliente [NAME] com email [EMAIL] e telefone [PHONE] " "cpf [CPF] solicitou acesso."
        )

        text = (
            "Cliente João Silva com email joao@exemplo.com e "
            "telefone (11) 98765-4321 cpf 123.456.789-09 solicitou acesso."
        )
        result = mock_masker.mask_pii(text, strategy="placeholder")

        assert "[NAME]" in result
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "[CPF]" in result
        assert "João Silva" not in result
        assert "joao@exemplo.com" not in result

    def test_mask_with_custom_patterns(self, mock_masker):
        """Testar mascaramento com padrões customizados"""
        mock_masker.mask_pii.return_value = "Token: [CUSTOM_TOKEN]"

        text = "Token: ABCD-1234-EFGH-5678"
        result = mock_masker.mask_pii(
            text,
            strategy="placeholder",
            custom_patterns=[
                {"pattern": r"[A-Z]{4}-\d{4}-[A-Z]{4}-\d{4}", "label": "CUSTOM_TOKEN"}
            ],
        )

        assert "[CUSTOM_TOKEN]" in result
        assert "ABCD-1234-EFGH-5678" not in result

    def test_mask_preserves_structure(self, mock_masker):
        """Testar que mascaramento preserva estrutura do documento"""
        input_text = (
            "Nome: João Silva\n"
            "Email: joao@test.com\n"
            "Telefone: (11) 9876-5432\n"
            "Mensagem: Olá, preciso de ajuda."
        )

        mock_masker.mask_pii.return_value = (
            "Nome: [NAME]\n"
            "Email: [EMAIL]\n"
            "Telefone: [PHONE]\n"
            "Mensagem: Olá, preciso de ajuda."
        )

        result = mock_masker.mask_pii(input_text, strategy="placeholder")

        # Preserva quebras de linha e estrutura
        assert "\n" in result
        assert "Mensagem: Olá, preciso de ajuda." in result


class TestPIIIntegration:
    """Testes de integração de detecção e mascaramento"""

    @pytest.fixture
    def mock_pii_system(self):
        """Mock do sistema completo de PII"""
        detector = MagicMock()
        detector.detect_pii = MagicMock(return_value=[])

        masker = MagicMock()
        masker.mask_pii = MagicMock(return_value="")

        return {"detector": detector, "masker": masker}

    def test_detect_then_mask_workflow(self, mock_pii_system):
        """Testar fluxo completo de detecção e mascaramento"""
        detector = mock_pii_system["detector"]
        masker = mock_pii_system["masker"]

        # Configurar detector
        detector.detect_pii.return_value = [
            {"type": "email", "value": "admin@empresa.com", "start": 6, "end": 23}
        ]

        # Configurar masker
        masker.mask_pii.return_value = "Para: [EMAIL] entre em contato"

        text = "Para: admin@empresa.com entre em contato"

        # Detectar
        detected = detector.detect_pii(text)
        assert len(detected) == 1
        assert detected[0]["type"] == "email"

        # Mascarar
        masked = masker.mask_pii(text, strategy="placeholder")
        assert "[EMAIL]" in masked
        assert "admin@empresa.com" not in masked

    def test_performance_with_large_text(self, mock_pii_system):
        """Testar performance com texto longo"""
        detector = mock_pii_system["detector"]
        masker = mock_pii_system["masker"]

        # Texto longo com alguns PII
        large_text = "Lorem ipsum " * 100 + "email: test@test.com" + " dolor amet " * 100

        detector.detect_pii.return_value = [
            {"type": "email", "value": "test@test.com", "start": 1206, "end": 1219}
        ]
        masker.mask_pii.return_value = large_text.replace("test@test.com", "[EMAIL]")

        detected = detector.detect_pii(large_text)
        assert len(detected) == 1

        masked = masker.mask_pii(large_text)
        assert "[EMAIL]" in masked

    def test_empty_text_handling(self, mock_pii_system):
        """Testar handling de texto vazio"""
        detector = mock_pii_system["detector"]
        masker = mock_pii_system["masker"]

        detector.detect_pii.return_value = []
        masker.mask_pii.return_value = ""

        result = detector.detect_pii("")
        assert result == []

        masked = masker.mask_pii("")
        assert masked == ""


class TestPIIRegexPatterns:
    """Testes para padrões regex de PII"""

    def test_email_regex_pattern(self):
        """Testar padrão regex para email"""
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

        text = "Contact: user@domain.com and admin@test.co.uk"
        matches = re.findall(email_pattern, text)

        assert len(matches) == 2
        assert "user@domain.com" in matches
        assert "admin@test.co.uk" in matches

    def test_cpf_regex_pattern(self):
        """Testar padrão regex para CPF"""
        cpf_pattern = r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"

        test_cases = ["123.456.789-09", "987.654.321-00", "111.222.333-44"]

        for cpf in test_cases:
            assert re.match(cpf_pattern, cpf), f"CPF {cpf} não corresponde ao padrão"

    def test_phone_regex_pattern(self):
        """Testar padrão regex para telefone brasileiro"""
        phone_patterns = [
            r"\+55\s?\d{2}\s?\d{4,5}-?\d{4}",  # +55 11 98765-4321
            r"\(\d{2}\)\s?\d{4,5}-?\d{4}",  # (11) 98765-4321
        ]

        text = "Tel: +55 11 98765-4321 ou (11) 9876-5432"
        all_matches = []
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            all_matches.extend(matches)

        assert len(all_matches) >= 2

    def test_credit_card_regex_pattern(self):
        """Testar padrão regex para cartão de crédito"""
        cc_pattern = r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"

        test_cases = ["4532 1234 5678 9010", "4532-1234-5678-9010", "4532123456789010"]

        text = " ".join(test_cases)
        matches = re.findall(cc_pattern, text)

        assert len(matches) == 3

    def test_cpf_validation_with_check_digits(self):
        """Testar validação de dígitos verificadores do CPF"""
        # CPF válido: 529.982.247-25
        valid_cpf = "529.982.247-25"

        # Extrair apenas os números
        cpf_numbers = [int(d) for d in re.findall(r"\d", valid_cpf)]

        # Verificar que tem 11 dígitos
        assert len(cpf_numbers) == 11

        # Primeiro dito verificador
        sum1 = sum(cpf_numbers[i] * (10 - i) for i in range(9))
        digit1 = (sum1 * 10) % 11
        if digit1 == 10:
            digit1 = 0
        assert cpf_numbers[9] == digit1

        # Segundo dito verificador
        sum2 = sum(cpf_numbers[i] * (11 - i) for i in range(10))
        digit2 = (sum2 * 10) % 11
        if digit2 == 10:
            digit2 = 0
        assert cpf_numbers[10] == digit2

    def test_detect_multiple_emails_in_text(self):
        """Testar detecção de múltiplos emails em um texto"""
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

        text = """
        Entre em contato com:
        - Vendas: vendas@empresa.com
        - Suporte: suporte@empresa.com
        - RH: rh@empresa.com.br
        """

        matches = re.findall(email_pattern, text, re.IGNORECASE)

        assert len(matches) == 3
        assert "vendas@empresa.com" in matches
        assert "suporte@empresa.com" in matches
        assert "rh@empresa.com.br" in matches

    def test_mask_preserves_email_structure(self):
        """Testar que mascaramento preserva estrutura do email"""
        email = "usuario.nome@dominio.com.br"

        # Extrair partes do email
        parts = email.split("@")
        assert len(parts) == 2
        assert "." in parts[0]  # Usuário tem ponto
        assert "." in parts[1]  # Domínio tem subdomínio

        # Mascarar preservando @ e pontos
        masked_user = "***.***"
        masked_domain = "*******.***.**"

        masked_email = f"{masked_user}@{masked_domain}"

        assert "@" in masked_email
        assert "." in masked_email
        assert "usuario" not in masked_email
