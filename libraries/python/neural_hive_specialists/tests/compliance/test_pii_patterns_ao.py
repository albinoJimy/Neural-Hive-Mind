"""Testes de PII patterns angolanos (TICKET-013).

Cobertura:
- BI_AO: Bilhete de Identidade angolano (9 dígitos + 2 letras + 3 dígitos)
- PHONE_AO: Telefone com prefixo internacional +244

Estes patterns são variantes específicas exigidas pela spec
2026-05-01-unified-gateway-architecture, complementares aos detectores
globais (PHONE genérico, NIF Portugal) — não substituem.
"""

from neural_hive_specialists.compliance.pii_patterns import (
    PIICategory,
    PIIType,
    get_pattern_registry,
)


# ---- BI angolano -----------------------------------------------------------


class TestBIAngolano:
    """Bilhete de Identidade angolano: 9 dígitos + 2 letras + 3 dígitos."""

    def test_bi_ao_valid_luanda(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.BI_AO)
        assert pattern is not None
        assert pattern.search("003456789LA017") is not None

    def test_bi_ao_valid_huambo(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.BI_AO)
        # HU = sigla provincial Huambo
        assert pattern.search("987654321HU042") is not None

    def test_bi_ao_in_sentence(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.BI_AO)
        text = "O cidadão com BI 003456789LA017 fez o pedido."
        match = pattern.search(text)
        assert match is not None
        assert match.group() == "003456789LA017"

    def test_bi_ao_rejects_lowercase_province(self):
        """Letras provinciais são sempre maiúsculas — `flags=0` aplicado."""
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.BI_AO)
        assert pattern.search("003456789la017") is None

    def test_bi_ao_rejects_short_digits(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.BI_AO)
        # 8 dígitos só → não é BI
        assert pattern.search("00345678LA017") is None

    def test_bi_ao_rejects_extra_digits(self):
        """`\\b` garante que sequências maiores não passam."""
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.BI_AO)
        # 10 dígitos antes das letras → não é BI standard
        assert pattern.search("0034567890LA017") is None


# ---- Telefone +244 ---------------------------------------------------------


class TestPhoneAngolano:
    """Telefone angolano com prefixo internacional +244 e 9 dígitos."""

    def test_phone_ao_with_spaces(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.PHONE_AO)
        assert pattern is not None
        assert pattern.search("+244 923 456 789") is not None

    def test_phone_ao_with_hyphens(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.PHONE_AO)
        assert pattern.search("+244-923-456-789") is not None

    def test_phone_ao_compact(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.PHONE_AO)
        assert pattern.search("+244923456789") is not None

    def test_phone_ao_in_sentence(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.PHONE_AO)
        text = "Liga-me para +244 923 456 789 amanhã."
        match = pattern.search(text)
        assert match is not None
        assert match.group().strip() == "+244 923 456 789"

    def test_phone_ao_rejects_other_country_codes(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.PHONE_AO)
        # +351 (Portugal), +55 (Brasil) — não devem matchar PHONE_AO
        assert pattern.search("+351 912 345 678") is None
        assert pattern.search("+55 11 9 1234-5678") is None

    def test_phone_ao_rejects_missing_country_code(self):
        registry = get_pattern_registry()
        pattern = registry.get_pattern(PIIType.PHONE_AO)
        # Sem o +244 — cai no PHONE genérico, não no PHONE_AO
        assert pattern.search("923 456 789") is None


# ---- Categoria ANGOLAN -----------------------------------------------------


class TestAngolanCategory:
    """Garante que os patterns angolanos pertencem à categoria correcta."""

    def test_angolan_category_exists(self):
        assert PIICategory.ANGOLAN.value == "angolan"

    def test_registry_returns_angolan_patterns(self):
        registry = get_pattern_registry()
        patterns = registry.get_patterns_by_category(PIICategory.ANGOLAN)
        types = {pii_type for pii_type, _ in patterns}
        assert PIIType.BI_AO in types
        assert PIIType.PHONE_AO in types

    def test_supported_types_include_angolan(self):
        registry = get_pattern_registry()
        types = registry.get_all_types()
        assert PIIType.BI_AO in types
        assert PIIType.PHONE_AO in types
