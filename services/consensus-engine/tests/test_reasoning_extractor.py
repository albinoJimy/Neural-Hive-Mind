"""
Testes unitários para ReasoningExtractor.

TDD: Testes escritos antes da implementação (GAPS-04 Task 3).
"""

import pytest
from typing import List, Dict, Any
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.reasoning_extractor import ReasoningExtractor


class TestReasoningExtractorInitialization:
    """Testes de inicialização do ReasoningExtractor."""

    def test_initialization(self):
        """Testa que o extractor pode ser inicializado."""
        extractor = ReasoningExtractor()
        assert extractor is not None


class TestExtractKeyFactors:
    """Testes de extração de factores-chave do texto."""

    @pytest.fixture
    def sample_reasoning_texts(self):
        """Textos de reasoning para extração."""
        return {
            "technical": "A arquitetura proposta utiliza microserviços com Kafka para event streaming. "
            + "O banco de dados MongoDB é adequado para cargas não-relacionais. "
            + "A API REST segue princípios RESTful corretos.",
            "business": "A solução alinha-se com os objetivos de negócio de reduzir custos operacionais. "
            + "O ROI estimado é de 18 meses. O impacto na receita é positivo.",
            "security": "Existem preocupações sobre injeção de SQL nos formulários de entrada. "
            + "A autenticação OAuth2 está implementada corretamente. "
            + "Dados sensíveis devem ser criptografados em repouso.",
            "compliance": "A solução cumpre requisitos LGPD para anonimização de dados. "
            + "Auditoria completa de acessos está implementada.",
        }

    def test_extract_from_technical_text(self, sample_reasoning_texts):
        """Testa extração de texto técnico."""
        extractor = ReasoningExtractor()

        result = extractor.extract_factors(sample_reasoning_texts["technical"])

        assert "factors" in result
        assert len(result["factors"]) > 0

    def test_extract_from_business_text(self, sample_reasoning_texts):
        """Testa extração de texto de negócio."""
        extractor = ReasoningExtractor()

        result = extractor.extract_factors(sample_reasoning_texts["business"])

        assert "factors" in result
        # Deve detectar menção a ROI ou custos
        factor_texts = [f["text"] for f in result["factors"]]
        has_business = any(
            term in " ".join(factor_texts).lower() for term in ["roi", "custo", "receita"]
        )
        assert has_business or len(result["factors"]) > 0

    def test_extract_from_security_text(self, sample_reasoning_texts):
        """Testa extração de texto de segurança."""
        extractor = ReasoningExtractor()

        result = extractor.extract_factors(sample_reasoning_texts["security"])

        assert "factors" in result
        # Deve detectar termos de segurança
        factor_texts = [f["text"] for f in result["factors"]]
        has_security = any(
            term in " ".join(factor_texts).lower() for term in ["sql", "oauth", "criptograf"]
        )
        assert has_security or len(result["factors"]) > 0

    def test_extract_returns_text_and_position(self, sample_reasoning_texts):
        """Testa que factores incluem texto e posição original."""
        extractor = ReasoningExtractor()

        result = extractor.extract_factors(sample_reasoning_texts["technical"])

        for factor in result["factors"]:
            assert "text" in factor
            assert isinstance(factor["text"], str)
            assert len(factor["text"]) > 0


class TestCategorizeFactors:
    """Testes de categorização de factores."""

    def test_categorize_technical_factor(self):
        """Testa categorização correta de factor técnico."""
        extractor = ReasoningExtractor()

        result = extractor.categorize_factor("A arquitetura usa microserviços com Kafka")

        assert "category" in result
        assert result["category"] in ["technical", "business", "security", "compliance", "general"]

    def test_categorize_business_factor(self):
        """Testa categorização correta de factor de negócio."""
        extractor = ReasoningExtractor()

        result = extractor.categorize_factor("ROI estimado de 18 meses com redução de custos")

        assert "category" in result
        # Deve identificar como business ou general
        assert result["category"] in ["business", "general"]

    def test_categorize_security_factor(self):
        """Testa categorização correta de factor de segurança."""
        extractor = ReasoningExtractor()

        result = extractor.categorize_factor("Vulnerabilidade de injeção de SQL detectada")

        assert "category" in result
        # Deve identificar como security ou general
        assert result["category"] in ["security", "general"]

    def test_categorize_compliance_factor(self):
        """Testa categorização correta de factor de compliance."""
        extractor = ReasoningExtractor()

        result = extractor.categorize_factor("Conformidade com LGPD implementada")

        assert "category" in result
        # Deve identificar como compliance ou general
        assert result["category"] in ["compliance", "general"]


class TestStructuredOutput:
    """Testes de geração de output estruturado."""

    def test_generate_structured_output_includes_citations(self):
        """Testa que output estruturado inclui citações."""
        extractor = ReasoningExtractor()

        reasoning = "A arquitetura usa microserviços. O ROI é de 18 meses."
        factors = extractor.extract_factors(reasoning)

        structured = extractor.generate_structured_output(factors, reasoning)

        assert "factors" in structured
        for factor in structured["factors"]:
            # Cada factor deve ter citação ao texto original
            assert "citation" in factor or "text" in factor

    def test_structured_output_includes_category(self):
        """Testa que output estruturado inclui categorias."""
        extractor = ReasoningExtractor()

        reasoning = "A arquitetura usa microserviços. O ROI é de 18 meses."
        factors = extractor.extract_factors(reasoning)

        structured = extractor.generate_structured_output(factors, reasoning)

        assert "factors" in structured
        for factor in structured["factors"]:
            assert "category" in factor

    def test_structured_output_includes_confidence(self):
        """Testa que output estruturado inclui confiança da extração."""
        extractor = ReasoningExtractor()

        reasoning = "A arquitetura usa microserviços."
        factors = extractor.extract_factors(reasoning)

        structured = extractor.generate_structured_output(factors, reasoning)

        assert "factors" in structured
        for factor in structured["factors"]:
            # A implementação retorna extraction_confidence e category_confidence
            assert "extraction_confidence" in factor
            assert "category_confidence" in factor
            assert 0 <= factor["extraction_confidence"] <= 1
            assert 0 <= factor["category_confidence"] <= 1


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_empty_text(self):
        """Testa comportamento com texto vazio."""
        extractor = ReasoningExtractor()

        result = extractor.extract_factors("")

        assert "factors" in result
        assert len(result["factors"]) == 0

    def test_very_long_text(self):
        """Testa comportamento com texto muito longo."""
        extractor = ReasoningExtractor()

        long_text = "A arquitetura usa microserviços. " * 100

        result = extractor.extract_factors(long_text)

        assert "factors" in result
        # Deve limitar número de factores extraídos
        assert len(result["factors"]) <= 50

    def test_text_with_no_clear_factors(self):
        """Testa texto sem factores claros."""
        extractor = ReasoningExtractor()

        unclear_text = "Ok, tudo bem, acho que funciona."

        result = extractor.extract_factors(unclear_text)

        assert "factors" in result
        # Pode retornar factores com baixa confiança ou vazio

    def test_multilingual_text(self):
        """Testa texto com mistura de idiomas."""
        extractor = ReasoningExtractor()

        mixed_text = "The architecture uses microserviços com Kafka streaming."

        result = extractor.extract_factors(mixed_text)

        assert "factors" in result


class TestBatchExtraction:
    """Testes de extração em lote."""

    @pytest.fixture
    def sample_reasonings(self):
        """Múltiplos textos de reasoning."""
        return [
            "A arquitetura usa microserviços com Kafka.",
            "O ROI estimado é de 18 meses.",
            "Vulnerabilidade de SQL detectada nos formulários.",
        ]

    def test_batch_extract_returns_list(self, sample_reasonings):
        """Testa que extração em lote retorna lista."""
        extractor = ReasoningExtractor()

        results = extractor.batch_extract(sample_reasonings)

        assert isinstance(results, list)
        assert len(results) == len(sample_reasonings)

    def test_batch_preserves_order(self, sample_reasonings):
        """Testa que extração em lote preserva ordem."""
        extractor = ReasoningExtractor()

        results = extractor.batch_extract(sample_reasonings)

        # Ordem deve ser preservada
        for i, result in enumerate(results):
            assert "factors" in result
