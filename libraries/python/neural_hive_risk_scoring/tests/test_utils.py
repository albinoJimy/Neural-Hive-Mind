"""
Testes para utilitários: get_domain_value, get_domain_enum
"""

import pytest

from neural_hive_domain import UnifiedDomain
from neural_hive_risk_scoring.utils import get_domain_enum, get_domain_value


class TestGetDomainValue:
    """Testes para get_domain_value."""

    def test_with_enum(self):
        """Testa com entrada UnifiedDomain enum."""
        result = get_domain_value(UnifiedDomain.BUSINESS)
        assert result == "BUSINESS"

    def test_with_string(self):
        """Testa com entrada string."""
        result = get_domain_value("BUSINESS")
        assert result == "BUSINESS"

    def test_all_domains_enum(self):
        """Testa todos os domínios como enum."""
        for domain in UnifiedDomain:
            result = get_domain_value(domain)
            assert result == domain.value

    def test_all_domains_string(self):
        """Testa todos os domínios como string."""
        for domain in UnifiedDomain:
            result = get_domain_value(domain.value)
            assert result == domain.value

    def test_case_sensitive(self):
        """Testa sensibilidade a maiúsculas/minúsculas."""
        # String deve ser retornada como está
        result = get_domain_value("business")
        assert result == "business"

        result = get_domain_value("Business")
        assert result == "Business"


class TestGetDomainEnum:
    """Testes para get_domain_enum."""

    def test_with_enum(self):
        """Testa com entrada UnifiedDomain enum."""
        result = get_domain_enum(UnifiedDomain.BUSINESS)
        assert result == UnifiedDomain.BUSINESS
        assert isinstance(result, UnifiedDomain)

    def test_with_string_valid(self):
        """Testa com string válida (maiúscula)."""
        result = get_domain_enum("BUSINESS")
        assert result == UnifiedDomain.BUSINESS
        assert isinstance(result, UnifiedDomain)

    def test_all_domains_string(self):
        """Testa todos os domínios como string."""
        test_cases = [
            ("BUSINESS", UnifiedDomain.BUSINESS),
            ("TECHNICAL", UnifiedDomain.TECHNICAL),
            ("SECURITY", UnifiedDomain.SECURITY),
            ("INFRASTRUCTURE", UnifiedDomain.INFRASTRUCTURE),
            ("BEHAVIOR", UnifiedDomain.BEHAVIOR),
            ("OPERATIONAL", UnifiedDomain.OPERATIONAL),
            ("COMPLIANCE", UnifiedDomain.COMPLIANCE),
        ]

        for string_value, expected_enum in test_cases:
            result = get_domain_enum(string_value)
            assert result == expected_enum

    def test_case_sensitive_string(self):
        """Testa sensibilidade a maiúsculas/minúsculas em string."""
        # Deve falhar com minúsculas
        with pytest.raises(ValueError):
            get_domain_enum("business")

        with pytest.raises(ValueError):
            get_domain_enum("Business")

    def test_invalid_string(self):
        """Testa string inválida."""
        with pytest.raises(ValueError):
            get_domain_enum("invalid_domain")

    def test_empty_string(self):
        """Testa string vazia."""
        with pytest.raises(ValueError):
            get_domain_enum("")


class TestUtilityFunctionsIntegration:
    """Testes de integração das funções utilitárias."""

    def test_roundtrip_enum_to_value_to_enum(self):
        """Testa conversão ida e volta: enum -> value -> enum."""
        for domain in UnifiedDomain:
            # Enum para valor
            value = get_domain_value(domain)

            # Valor para enum
            back_to_enum = get_domain_enum(value)

            assert back_to_enum == domain

    def test_roundtrip_string_to_enum_to_value(self):
        """Testa conversão ida e volta: string -> enum -> value."""
        test_cases = ["BUSINESS", "TECHNICAL", "SECURITY", "OPERATIONAL", "COMPLIANCE"]

        for string_value in test_cases:
            # String para enum
            domain = get_domain_enum(string_value)

            # Enum para valor
            back_to_value = get_domain_value(domain)

            assert back_to_value == string_value

    def test_consistency(self):
        """Testa consistência entre as funções."""
        # Para cada domínio, as duas funções devem ser consistentes
        for domain in UnifiedDomain:
            value = get_domain_value(domain)
            enum = get_domain_enum(value)

            assert enum == domain
            assert get_domain_value(enum) == value
