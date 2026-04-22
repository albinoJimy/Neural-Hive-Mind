"""Unit tests for UnifiedDomain enum."""

import pytest

from neural_hive_domain.domain import UnifiedDomain


class TestUnifiedDomain:
    """Testes para UnifiedDomain enum."""

    def test_all_domains_defined(self):
        """Todos os domínios devem estar definidos."""
        expected_domains = {
            "BUSINESS",
            "TECHNICAL",
            "SECURITY",
            "INFRASTRUCTURE",
            "BEHAVIOR",
            "OPERATIONAL",
            "COMPLIANCE",
        }
        actual_domains = {domain.value for domain in UnifiedDomain}
        assert actual_domains == expected_domains

    def test_domain_values_are_strings(self):
        """UnifiedDomain herda de str, valores devem ser strings."""
        assert isinstance(UnifiedDomain.BUSINESS, str)
        assert str(UnifiedDomain.TECHNICAL) == "TECHNICAL"

    def test_domain_value_accessor(self):
        """Método __str__ retorna o valor do domínio."""
        domain = UnifiedDomain.SECURITY
        assert domain.__str__() == "SECURITY"
        assert str(domain) == "SECURITY"

    def test_domain_equality(self):
        """Domínios com mesmo valor são iguais."""
        assert UnifiedDomain.BUSINESS == UnifiedDomain.BUSINESS
        assert UnifiedDomain.BUSINESS != UnifiedDomain.TECHNICAL

    def test_domain_hashable(self):
        """UnifiedDomain deve ser hashable para uso em sets/dicts."""
        domain_set = {UnifiedDomain.BUSINESS, UnifiedDomain.TECHNICAL}
        assert len(domain_set) == 2
        assert UnifiedDomain.SECURITY not in domain_set

    def test_domain_iteration(self):
        """Deve ser possível iterar sobre todos os domínios."""
        domains = list(UnifiedDomain)
        assert len(domains) == 7
        assert UnifiedDomain.BUSINESS in domains
        assert UnifiedDomain.COMPLIANCE in domains

    def test_domain_in_dict(self):
        """UnifiedDomain pode ser usado como chave de dict."""
        mapping = {
            UnifiedDomain.BUSINESS: "business_value",
            UnifiedDomain.TECHNICAL: "technical_value",
        }
        assert mapping[UnifiedDomain.BUSINESS] == "business_value"

    def test_domain_serialization(self):
        """UnifiedDomain pode ser serializado para JSON."""
        import json

        domain_dict = {"domain": UnifiedDomain.SECURITY}
        serialized = json.dumps(domain_dict)
        assert '"SECURITY"' in serialized

    def test_domain_from_string(self):
        """Criar UnifiedDomain a partir de string."""
        domain = UnifiedDomain("TECHNICAL")
        assert domain == UnifiedDomain.TECHNICAL

    def test_invalid_domain_string_raises(self):
        """String inválido levanta ValueError."""
        with pytest.raises(ValueError):
            UnifiedDomain("INVALID_DOMAIN")

    def test_domain_comparable(self):
        """UnifiedDomain pode ser comparado."""
        assert UnifiedDomain.BUSINESS < UnifiedDomain.COMPLIANCE

    def test_getattr_access(self):
        """Pode acessar domínios via getattr."""
        domain = UnifiedDomain.SECURITY
        assert domain == UnifiedDomain.SECURITY
