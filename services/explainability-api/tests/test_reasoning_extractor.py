"""
Tests para ReasoningExtractor.

Stub - expandir em iteração futura.
"""

from src.services.reasoning_extractor import ReasoningExtractor


def test_reasoning_extractor_init():
    """Testa inicialização do ReasoningExtractor."""
    extractor = ReasoningExtractor()
    assert extractor is not None


def test_extract_reasoning_factors_stub():
    """Testa extract_reasoning_factors (stub retorna vazio)."""
    extractor = ReasoningExtractor()
    factors = extractor.extract_reasoning_factors({"opinion": "test"})
    assert factors == []  # Stub retorna vazio


def test_extract_from_text_stub():
    """Testa extract_from_text (stub retorna vazio)."""
    extractor = ReasoningExtractor()
    factors = extractor.extract_from_text("some text")
    assert factors == []
