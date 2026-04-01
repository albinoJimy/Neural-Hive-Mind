"""
Multi-Language Support for Semantic Translation Engine

Provides language detection and translation for user intents.
Supports Portuguese, English, Spanish, French, German, Italian.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class LanguageCode(Enum):
    """Códigos de idioma suportados"""

    PT_BR = "pt-BR"  # Português Brasil
    EN_US = "en-US"  # English (US)
    ES = "es-ES"  # Spanish
    FR = "fr-FR"  # French
    DE = "de-DE"  # German
    IT = "it-IT"  # Italian
    UNKNOWN = "unknown"


@dataclass
class DetectedLanguage:
    """Resultado da detecção de idioma"""

    language: LanguageCode
    confidence: float
    original_text: str


class LanguageDetector:
    """
    Detector de idioma para intenções do usuário.

    Usa heurísticas simples baseadas em palavras-chave
    e padrões de cada idioma.
    """

    # Palavras-chave por idioma para detecção rápida
    KEYWORDS = {
        LanguageCode.PT_BR: [
            "criar",
            "fazer",
            "construir",
            "deploy",
            "executar",
            "análise",
            "relatório",
            "consultar",
            "buscar",
            "listar",
            "para",
            "por favor",
            "obrigado",
            "ajuda",
            "ajudar",
            "como",
            "qual",
            "onde",
            "quando",
            "quanto",
            "tabela",
        ],
        LanguageCode.EN_US: [
            "create",
            "make",
            "build",
            "deploy",
            "execute",
            "analyze",
            "report",
            "query",
            "search",
            "list",
            "please",
            "thanks",
            "help",
            "how",
            "what",
            "where",
            "when",
            "how much",
            "table",
            "database",
        ],
        LanguageCode.ES: [
            "crear",
            "hacer",
            "construir",
            "desplegar",
            "ejecutar",
            "análisis",
            "informe",
            "consulta",
            "buscar",
            "listar",
            "por favor",
            "gracias",
            "ayuda",
            "cómo",
            "qué",
            "dónde",
            "cuándo",
            "cuánto",
            "tabla",
        ],
        LanguageCode.FR: [
            "créer",
            "faire",
            "construire",
            "déployer",
            "exécuter",
            "analyser",
            "rapport",
            "requête",
            "chercher",
            "lister",
            "s'il vous plaît",
            "merci",
            "aide",
            "comment",
            "quoi",
            "où",
            "quand",
            "combien",
            "table",
        ],
        LanguageCode.DE: [
            "erstellen",
            "machen",
            "bauen",
            "deployen",
            "ausführen",
            "analyse",
            "bericht",
            "abfrage",
            "suchen",
            "auflisten",
            "bitte",
            "danke",
            "hilfe",
            "wie",
            "was",
            "wo",
            "wann",
            "wie viel",
            "tabelle",
        ],
        LanguageCode.IT: [
            "creare",
            "fare",
            "costruire",
            "deploy",
            "eseguire",
            "analisi",
            "rapporto",
            "query",
            "cercare",
            "elencare",
            "per favore",
            "grazie",
            "aiuto",
            "come",
            "cosa",
            "dove",
            "quando",
            "quanto",
            "tabella",
        ],
    }

    def __init__(self, config=None):
        """
        Inicializa o detector de idioma.

        Args:
            config: Configurações opcionais
        """
        self.config = config
        self.logger = logger.bind(component="language_detector")

        # Idioma padrão
        self.default_language = LanguageCode.PT_BR

    def detect(self, text: str) -> DetectedLanguage:
        """
        Detecta o idioma do texto da intenção.

        Args:
            text: Texto da intenção do usuário

        Returns:
            DetectedLanguage com idioma detectado e confiança
        """
        if not text or not text.strip():
            return DetectedLanguage(
                language=LanguageCode.UNKNOWN, confidence=0.0, original_text=text
            )

        text_lower = text.lower()
        scores = {}

        # Calcular pontuação para cada idioma
        for lang, keywords in self.KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            scores[lang] = matches

        # Encontrar idioma com maior pontuação
        if not scores or max(scores.values()) == 0:
            # Nenhum match detectado - usar padrão
            return DetectedLanguage(
                language=self.default_language, confidence=0.0, original_text=text
            )

        best_lang = max(scores, key=scores.get)
        best_score = scores[best_lang]

        # Calcular confiança baseado no número de matches
        confidence = min(best_score / 3.0, 1.0)  # Max 3 palavras = 100% confiança

        self.logger.debug(
            "language_detected",
            language=best_lang.value,
            confidence=confidence,
            text_length=len(text),
        )

        return DetectedLanguage(language=best_lang, confidence=confidence, original_text=text)


class TranslationService:
    """
    Serviço de tradução para intenções multi-idioma.

    Traduz comandos de outros idiomas para inglês (padrão interno).
    """

    # Dicionário de tradução de comandos comuns
    COMMAND_TRANSLATIONS = {
        LanguageCode.PT_BR: {
            "criar": "create",
            "fazer": "make",
            "construir": "build",
            "deploy": "deploy",
            "executar": "execute",
            "análise": "analyze",
            "analise": "analyze",
            "relatório": "report",
            "relatorio": "report",
            "consultar": "query",
            "buscar": "search",
            "listar": "list",
            "mostrar": "show",
            "tabela": "table",
            "banco de dados": "database",
            "usuário": "user",
            "ajuda": "help",
        },
        LanguageCode.ES: {
            "crear": "create",
            "hacer": "make",
            "construir": "build",
            "desplegar": "deploy",
            "ejecutar": "execute",
            "análisis": "analyze",
            "informe": "report",
            "consulta": "query",
            "buscar": "search",
            "listar": "list",
            "tabla": "table",
            "base de datos": "database",
            "usuario": "user",
            "ayuda": "help",
        },
        LanguageCode.FR: {
            "créer": "create",
            "faire": "make",
            "construire": "build",
            "déployer": "deploy",
            "exécuter": "execute",
            "analyser": "analyze",
            "rapport": "report",
            "requête": "query",
            "chercher": "search",
            "lister": "list",
            "table": "table",
            "base de données": "database",
            "utilisateur": "user",
            "aide": "help",
        },
        LanguageCode.DE: {
            "erstellen": "create",
            "machen": "make",
            "bauen": "build",
            "deployen": "deploy",
            "ausführen": "execute",
            "analyse": "analyze",
            "bericht": "report",
            "abfrage": "query",
            "suchen": "search",
            "auflisten": "list",
            "tabelle": "table",
            "datenbank": "database",
            "benutzer": "user",
            "hilfe": "help",
        },
        LanguageCode.IT: {
            "creare": "create",
            "fare": "make",
            "costruire": "build",
            "deploy": "deploy",
            "eseguire": "execute",
            "analisi": "analyze",
            "rapporto": "report",
            "query": "query",
            "cercare": "search",
            "elencare": "list",
            "tabella": "table",
            "database": "database",
            "utente": "user",
            "aiuto": "help",
        },
    }

    def __init__(self, config=None):
        """
        Inicializa o serviço de tradução.

        Args:
            config: Configurações opcionais
        """
        self.config = config
        self.logger = logger.bind(component="translation_service")

    def translate_to_english(self, text: str, source_language: LanguageCode) -> str:
        """
        Traduz texto para inglês.

        Args:
            text: Texto original
            source_language: Idioma de origem

        Returns:
            Texto traduzido para inglês
        """
        # Se já está em inglês, retornar original
        if source_language == LanguageCode.EN_US:
            return text

        # Se não temos tradução, retornar original
        if source_language not in self.COMMAND_TRANSLATIONS:
            self.logger.warning("no_translation_available", language=source_language.value)
            return text

        translations = self.COMMAND_TRANSLATIONS[source_language]
        result = text.lower()

        # Aplicar traduções palavra por palavra
        for original, translated in translations.items():
            result = result.replace(original, translated)

        self.logger.debug(
            "text_translated",
            source_language=source_language.value,
            original_length=len(text),
            translated_length=len(result),
        )

        return result

    def normalize_intent(self, text: str, detected_language: DetectedLanguage) -> dict[str, Any]:
        """
        Normaliza a intenção para o formato interno do STE.

        Args:
            text: Texto da intenção
            detected_language: Idioma detectado

        Returns:
            Dict com texto normalizado e metadados
        """
        # Traduzir para inglês se necessário
        normalized_text = self.translate_to_english(text, detected_language.language)

        return {
            "original_text": text,
            "normalized_text": normalized_text,
            "detected_language": detected_language.language.value,
            "language_confidence": detected_language.confidence,
            "translation_applied": detected_language.language != LanguageCode.EN_US,
        }


class MultiLanguageProcessor:
    """
    Processador multi-idioma para o STE.

    Coordena detecção de idioma e tradução.
    """

    def __init__(self, config=None):
        """
        Inicializa o processador multi-idioma.

        Args:
            config: Configurações opcionais
        """
        self.config = config
        self.logger = logger.bind(component="multilanguage_processor")

        self.detector = LanguageDetector(config)
        self.translator = TranslationService(config)

    def process(self, intent_data: dict[str, Any]) -> dict[str, Any]:
        """
        Processa intenção com suporte multi-idioma.

        Args:
            intent_data: Dados da intenção do usuário (deve conter 'text')

        Returns:
            Dict com intenção normalizada e metadados de idioma
        """
        text = intent_data.get("text", "")
        intent_id = intent_data.get("intent_id", "unknown")

        self.logger.info(
            "processing_multilanguage_intent", intent_id=intent_id, text_length=len(text)
        )

        # Detectar idioma
        detected = self.detector.detect(text)

        # Normalizar
        normalized = self.translator.normalize_intent(text, detected)

        # Adicionar metadados ao resultado
        result = {
            **intent_data,
            "original_text": text,
            "normalized_text": normalized["normalized_text"],
            "detected_language": normalized["detected_language"],
            "language_confidence": normalized["language_confidence"],
            "translation_applied": normalized["translation_applied"],
        }

        self.logger.info(
            "multilanguage_intent_processed",
            intent_id=intent_id,
            detected_language=normalized["detected_language"],
            translation_applied=normalized["translation_applied"],
        )

        return result
