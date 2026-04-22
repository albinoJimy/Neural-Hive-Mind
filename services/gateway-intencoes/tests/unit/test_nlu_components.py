"""Testes unitários para componentes NLU refatorados.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)
"""

import pytest
from models.intent_envelope import NLUResult
from pipelines.nlu import (
    CacheManager,
    ClassifierEngine,
    LanguageDetector,
    TextProcessor,
    ThresholdCalculator,
)

from neural_hive_domain import UnifiedDomain


@pytest.mark.asyncio()
class TestThresholdCalculator:
    """Testes para ThresholdCalculator."""

    async def test_initialization(self):
        """Testa inicialização com valores padrão."""
        calc = ThresholdCalculator()
        assert calc.base_threshold == 0.6
        assert calc.min_threshold == 0.4
        assert calc.max_threshold == 0.8
        assert calc.current_threshold == 0.6

    async def test_calculate_threshold_empty_history(self):
        """Testa cálculo com histórico vazio."""
        calc = ThresholdCalculator()
        threshold = await calc.calculate_threshold()
        assert threshold == 0.6

    async def test_calculate_threshold_high_confidence(self):
        """Testa aumento de threshold com alta confiança."""
        calc = ThresholdCalculator()

        # Registrar confianças altas
        for _ in range(10):
            await calc.record_confidence(0.9)

        threshold = await calc.calculate_threshold()
        assert threshold > 0.6
        assert threshold <= calc.max_threshold

    async def test_calculate_threshold_low_confidence(self):
        """Testa redução de threshold com baixa confiança."""
        calc = ThresholdCalculator()

        # Registrar confianças baixas
        for _ in range(10):
            await calc.record_confidence(0.4)

        threshold = await calc.calculate_threshold()
        assert threshold < 0.6
        assert threshold >= calc.min_threshold

    async def test_should_accept(self):
        """Testa decisão de aceitação."""
        calc = ThresholdCalculator(base_threshold=0.7)

        result = NLUResult(
            processed_text="test",
            domain=UnifiedDomain.BUSINESS,
            classification="test",
            confidence=0.8,
            entities=[],
            keywords=[],
        )

        assert calc.should_accept(result) is True

        result_low = NLUResult(
            processed_text="test",
            domain=UnifiedDomain.BUSINESS,
            classification="test",
            confidence=0.5,
            entities=[],
            keywords=[],
        )

        assert calc.should_accept(result_low) is False

    async def test_reset(self):
        """Testa reset do threshold."""
        calc = ThresholdCalculator()
        calc.current_threshold = 0.75
        calc.confidence_history = [0.8, 0.9]

        calc.reset()

        assert calc.current_threshold == 0.6
        assert len(calc.confidence_history) == 0


@pytest.mark.asyncio()
class TestLanguageDetector:
    """Testes para LanguageDetector."""

    async def test_detect_portuguese(self):
        """Testa detecção de português."""
        detector = LanguageDetector()
        lang, conf = detector.detect("Preciso de um relatório de vendas")

        assert lang == "pt"
        # Confiança pode variar, mas deve detectar português
        assert conf >= 0.0

    async def test_detect_english(self):
        """Testa detecção de inglês."""
        detector = LanguageDetector()
        # Usar texto com mais palavras exclusivas do inglês
        lang, conf = detector.detect("The quick brown fox jumps over the lazy dog")

        assert lang == "en"
        # Confiança pode variar, mas deve detectar inglês
        assert conf >= 0.0

    async def test_detect_short_text(self):
        """Testa texto curto retorna default."""
        detector = LanguageDetector(default_language="pt")
        lang, conf = detector.detect("oi")

        assert lang == "pt"
        assert conf == 0.0

    async def test_detect_empty_text(self):
        """Testa texto vazio retorna default."""
        detector = LanguageDetector(default_language="pt")
        lang, conf = detector.detect("")

        assert lang == "pt"
        assert conf == 0.0

    async def test_is_supported(self):
        """Testa verificação de idioma suportado."""
        detector = LanguageDetector(supported_languages=["pt", "en"])

        assert detector.is_supported("pt") is True
        assert detector.is_supported("en") is True
        assert detector.is_supported("fr") is False

    async def test_set_enabled(self):
        """Testa habilitar/desabilitar detecção."""
        detector = LanguageDetector()

        assert detector.enabled is True

        detector.set_enabled(False)
        assert detector.enabled is False

        lang, conf = detector.detect("qualquer texto")
        assert lang == "pt"  # Default quando desabilitado


@pytest.mark.asyncio()
class TestTextProcessor:
    """Testes para TextProcessor."""

    async def test_normalize(self):
        """Testa normalização de texto."""
        processor = TextProcessor()

        normalized = processor.normalize("  Testo   com  espaços  ")
        assert normalized == "Testo com espaços"

    async def test_normalize_preserves_accents(self):
        """Testa que normalização preserva acentos."""
        processor = TextProcessor()

        normalized = processor.normalize("São Paulo, café, Pé")
        assert "ã" in normalized
        assert "é" in normalized

    async def test_extract_keywords(self):
        """Testa extração de palavras-chave."""
        processor = TextProcessor()

        keywords = processor.extract_keywords("relatório de vendas com métricas de analytics")

        # Verifica que palavras-chave foram extraídas
        assert len(keywords) > 0
        # "vendas" ou "analytics" devem estar presentes
        assert any(kw in keywords for kw in ["vendas", "analytics", "métricas"])

    async def test_calculate_similarity(self):
        """Testa cálculo de similaridade."""
        processor = TextProcessor()

        sim = processor.calculate_similarity("relatório de vendas", "relatório vendas mensal")

        assert sim >= 0.5

    async def test_calculate_similarity_different(self):
        """Testa similaridade de textos diferentes."""
        processor = TextProcessor()

        sim = processor.calculate_similarity("relatório de vendas", "configuração de servidor")

        assert sim < 0.5

    async def test_truncate(self):
        """Testa truncamento de texto."""
        processor = TextProcessor()

        long_text = "a" * 1000
        truncated = processor.truncate(long_text, max_length=100)

        assert len(truncated) <= 103  # 100 + "..."

    async def test_mask_pii_unavailable(self):
        """Testa masking quando módulo não disponível."""
        processor = TextProcessor(enable_pii_masking=False)

        masked, entities = processor.mask_pii("Meu email é test@example.com")

        assert masked == "Meu email é test@example.com"
        assert entities == []


@pytest.mark.asyncio()
class TestClassifierEngine:
    """Testes para ClassifierEngine."""

    async def test_initialization(self):
        """Testa inicialização do engine."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        assert "BUSINESS" in engine.get_supported_domains()
        assert "TECHNICAL" in engine.get_supported_domains()
        assert "INFRASTRUCTURE" in engine.get_supported_domains()
        assert "SECURITY" in engine.get_supported_domains()

    async def test_classify_business(self):
        """Testa classificação de domínio BUSINESS."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        domain, conf, subcat = engine.classify("Preciso de um relatório de vendas")

        assert domain == UnifiedDomain.BUSINESS
        assert conf > 0.0

    async def test_classify_technical(self):
        """Testa classificação de domínio TECHNICAL."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        domain, conf, subcat = engine.classify("Tem um bug na API de login")

        assert domain == UnifiedDomain.TECHNICAL
        assert conf > 0.0

    async def test_classify_infrastructure(self):
        """Testa classificação de domínio INFRASTRUCTURE."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        domain, conf, subcat = engine.classify("Fazer deploy do Kubernetes")

        assert domain == UnifiedDomain.INFRASTRUCTURE
        assert conf > 0.0

    async def test_classify_security(self):
        """Testa classificação de domínio SECURITY."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        domain, conf, subcat = engine.classify("Configurar autenticação OAuth")

        assert domain == UnifiedDomain.SECURITY
        assert conf > 0.0

    async def test_validate_text_quality_valid(self):
        """Testa validação de texto válido."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        valid, reason = engine.validate_text_quality("Texto válido para teste")

        assert valid is True
        assert reason is None

    async def test_validate_text_quality_too_short(self):
        """Testa validação de texto muito curto."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        valid, reason = engine.validate_text_quality("oi")

        assert valid is False
        assert "curto" in reason.lower()

    async def test_validate_text_quality_spam(self):
        """Testa validação de padrão de spam."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        valid, reason = engine.validate_text_quality("aaaaaaaaaa")

        assert valid is False

    async def test_get_domain_config(self):
        """Testa obter configuração de domínio."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        config = engine.get_domain_config("BUSINESS")

        assert config is not None
        assert "keywords" in config
        assert "patterns" in config

    async def test_update_domain_rules(self):
        """Testa atualização de regras de domínio."""
        engine = ClassifierEngine(enable_custom_rules=False)
        await engine.initialize()

        success = engine.update_domain_rules("BUSINESS", keywords=["custom_keyword"])

        assert success is True


@pytest.mark.asyncio()
class TestCacheManager:
    """Testes para CacheManager."""

    async def test_initialization_with_no_client(self):
        """Testa inicialização sem cliente Redis."""
        manager = CacheManager(redis_client=None, enabled=True)

        assert manager.is_enabled() is False

    async def test_generate_key(self):
        """Testa geração de chave de cache."""
        manager = CacheManager()

        key1 = manager._generate_key("test text", "pt")
        key2 = manager._generate_key("test text", "pt")
        key3 = manager._generate_key("test text", "en")

        assert key1 == key2  # Mesmo texto e idioma
        assert key1 != key3  # Idiomas diferentes

    async def test_get_returns_none_when_disabled(self):
        """Testa get retorna None quando desabilitado."""
        manager = CacheManager(redis_client=None, enabled=False)

        result = await manager.get("test text", "pt")

        assert result is None

    async def test_set_returns_false_when_disabled(self):
        """Testa set retorna False quando desabilitado."""
        manager = CacheManager(redis_client=None, enabled=False)

        result = NLUResult(
            processed_text="test",
            domain=UnifiedDomain.BUSINESS,
            classification="test",
            confidence=0.8,
            entities=[],
            keywords=[],
        )

        success = await manager.set("test text", result, "pt")

        assert success is False

    async def test_delete_returns_false_when_disabled(self):
        """Testa delete retorna False quando desabilitado."""
        manager = CacheManager(redis_client=None, enabled=False)

        success = await manager.delete("test text", "pt")

        assert success is False

    async def test_clear_returns_false_when_disabled(self):
        """Testa clear retorna False quando desabilitado."""
        manager = CacheManager(redis_client=None, enabled=False)

        success = await manager.clear()

        assert success is False

    async def test_get_stats(self):
        """Testa obter estatísticas."""
        manager = CacheManager(redis_client=None, enabled=False)

        stats = await manager.get_stats()

        assert stats["enabled"] is False
        assert stats["backend"] == "memory"

    async def test_set_enabled(self):
        """Testa habilitar/desabilitar cache."""
        manager = CacheManager(redis_client=None, enabled=True)

        manager.set_enabled(False)
        assert manager.is_enabled() is False
