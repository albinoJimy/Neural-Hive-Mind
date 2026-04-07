"""
Testes para Multi-Language Processor

Testa detecção de idioma e tradução de intenções.
"""
import pytest

from src.services.multilanguage_processor import (
    LanguageDetector,
    TranslationService,
    MultiLanguageProcessor,
    LanguageCode,
    DetectedLanguage,
)


class TestLanguageDetector:
    """Testes para LanguageDetector"""

    @pytest.fixture
    def detector(self):
        """Detector de idioma"""
        return LanguageDetector()

    def test_detect_portuguese(self, detector):
        """Testa detecção de português"""
        text = "Criar um relatório de usuários"
        result = detector.detect(text)

        assert result.language == LanguageCode.PT_BR
        assert result.confidence > 0.5
        assert result.original_text == text

    def test_detect_english(self, detector):
        """Testa detecção de inglês"""
        text = "Create a user report"
        result = detector.detect(text)

        assert result.language == LanguageCode.EN_US
        assert result.confidence > 0.5

    def test_detect_spanish(self, detector):
        """Testa detecção de espanhol"""
        text = "Crear un informe de usuarios"
        result = detector.detect(text)

        assert result.language == LanguageCode.ES
        assert result.confidence > 0.3

    def test_detect_french(self, detector):
        """Testa detecção de francês"""
        text = "Créer un rapport d'utilisateurs"
        result = detector.detect(text)

        assert result.language == LanguageCode.FR
        assert result.confidence > 0.3

    def test_detect_german(self, detector):
        """Testa detecção de alemão"""
        text = "Erstellen einen Benutzerbericht"
        result = detector.detect(text)

        assert result.language == LanguageCode.DE
        assert result.confidence > 0.3

    def test_detect_italian(self, detector):
        """Testa detecção de italiano"""
        text = "Creare un rapporto utenti"
        result = detector.detect(text)

        assert result.language == LanguageCode.IT
        assert result.confidence > 0.3

    def test_detect_empty_text(self, detector):
        """Testa detecção de texto vazio"""
        result = detector.detect("")

        assert result.language == LanguageCode.UNKNOWN
        assert result.confidence == 0.0

    def test_detect_unknown_language(self, detector):
        """Testa detecção de idioma desconhecido"""
        result = detector.detect("xyz abc 123")

        # Deve retornar idioma padrão com baixa confiança
        assert result.confidence == 0.0
        assert result.language in [LanguageCode.PT_BR, LanguageCode.UNKNOWN]

    def test_confidence_increases_with_keywords(self, detector):
        """Testa que confiança aumenta com mais palavras-chave"""
        text1 = "criar"  # 1 palavra
        text2 = "criar relatório"  # 2 palavras
        text3 = "criar relatório de usuários"  # 3 palavras

        result1 = detector.detect(text1)
        result2 = detector.detect(text2)
        result3 = detector.detect(text3)

        assert result3.confidence >= result2.confidence >= result1.confidence


class TestTranslationService:
    """Testes para TranslationService"""

    @pytest.fixture
    def translator(self):
        """Serviço de tradução"""
        return TranslationService()

    def test_translate_portuguese_to_english(self, translator):
        """Testa tradução de português para inglês"""
        text = "criar relatório"
        result = translator.translate_to_english(text, LanguageCode.PT_BR)

        assert "create" in result.lower()
        assert "report" in result.lower()

    def test_translate_spanish_to_english(self, translator):
        """Testa tradução de espanhol para inglês"""
        text = "crear informe"
        result = translator.translate_to_english(text, LanguageCode.ES)

        assert "create" in result.lower() or "report" in result.lower()

    def test_translate_english_returns_original(self, translator):
        """Testa que inglês retorna original"""
        text = "create report"
        result = translator.translate_to_english(text, LanguageCode.EN_US)

        assert result == text

    def test_normalize_intent(self, translator):
        """Testa normalização de intenção"""
        detected = DetectedLanguage(
            language=LanguageCode.PT_BR, confidence=0.8, original_text="criar relatório"
        )

        result = translator.normalize_intent("criar relatório", detected)

        assert result["original_text"] == "criar relatório"
        assert "normalized_text" in result
        assert result["detected_language"] == "pt-BR"
        assert result["translation_applied"] is True

    def test_normalize_english_no_translation(self, translator):
        """Testa que inglês não aplica tradução"""
        detected = DetectedLanguage(
            language=LanguageCode.EN_US, confidence=1.0, original_text="create report"
        )

        result = translator.normalize_intent("create report", detected)

        assert result["translation_applied"] is False


class TestMultiLanguageProcessor:
    """Testes para MultiLanguageProcessor"""

    @pytest.fixture
    def processor(self):
        """Processador multi-idioma"""
        return MultiLanguageProcessor()

    def test_process_portuguese_intent(self, processor):
        """Testa processamento de intenção em português"""
        intent_data = {"intent_id": "test-001", "text": "Criar um relatório de vendas"}

        result = processor.process(intent_data)

        assert result["intent_id"] == "test-001"
        assert result["original_text"] == "Criar um relatório de vendas"
        assert result["detected_language"] == "pt-BR"
        assert result["translation_applied"] is True
        assert "create" in result["normalized_text"].lower()
        assert "report" in result["normalized_text"].lower()

    def test_process_english_intent(self, processor):
        """Testa processamento de intenção em inglês"""
        intent_data = {"intent_id": "test-002", "text": "Create a sales report"}

        result = processor.process(intent_data)

        assert result["detected_language"] == "en-US"
        assert result["translation_applied"] is False
        # Texto normalizado deve ser similar ao original
        assert "create" in result["normalized_text"].lower()

    def test_process_spanish_intent(self, processor):
        """Testa processamento de intenção em espanhol"""
        # Usar palavra única do espanhol "gracias"
        intent_data = {"intent_id": "test-003", "text": "Crear informe de ventas por favor"}

        result = processor.process(intent_data)

        assert result["detected_language"] == "es-ES"
        assert result["translation_applied"] is True
        assert (
            "create" in result["normalized_text"].lower()
            or "report" in result["normalized_text"].lower()
        )

    def test_process_preserves_original_fields(self, processor):
        """Testa que campos originais são preservados"""
        intent_data = {
            "intent_id": "test-004",
            "text": "Criar relatório",
            "user_id": "user-123",
            "timestamp": 1234567890,
        }

        result = processor.process(intent_data)

        assert result["intent_id"] == "test-004"
        assert result["user_id"] == "user-123"
        assert result["timestamp"] == 1234567890

    def test_process_empty_text(self, processor):
        """Testa processamento de texto vazio"""
        intent_data = {"intent_id": "test-005", "text": ""}

        result = processor.process(intent_data)

        assert result["detected_language"] == "unknown"
        assert result["language_confidence"] == 0.0

    def test_all_supported_languages(self, processor):
        """Testa todos os idiomas suportados"""
        test_cases = [
            ("pt-BR", "criar tabela"),
            ("en-US", "create table"),
            ("es-ES", "crear tabla"),
            ("fr-FR", "créer table"),
            ("de-DE", "tabelle erstellen"),
            ("it-IT", "creare tabella"),
        ]

        for expected_lang, text in test_cases:
            intent_data = {"intent_id": f"test-{expected_lang}", "text": text}
            result = processor.process(intent_data)

            assert result["detected_language"] == expected_lang
