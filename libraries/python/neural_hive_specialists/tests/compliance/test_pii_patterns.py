"""Testes de PII patterns."""

import pytest
from neural_hive_specialists.compliance.pii_patterns import (
    PIIType,
    PIICategory,
    get_pattern_registry,
)


class TestPIIPatterns:
    """Testa registry de patterns."""

    def test_registry_initialization(self):
        registry = get_pattern_registry()
        assert registry is not None

    def test_email_pattern(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.EMAIL)
        assert pattern is not None
        assert pattern.search("user@example.com")

    def test_cpf_pattern(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.CPF)
        assert pattern.search("123.456.789-00")

    def test_ip_address_pattern(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.IP_ADDRESS)
        assert pattern.search("192.168.1.1")

    def test_get_all_types(self):
        registry = get_pattern_registry()
        types = registry.get_all_types()
        assert PIIType.EMAIL in types
        assert PIIType.CPF in types
