"""Detector de Idioma para NLU.

Autor: Neural Hive Mind
Criado: 2026-04-20 (REFACTOR-A-001)
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Padrões de detecção por idioma
LANGUAGE_PATTERNS = {
    "pt": {
        "common_words": [
            "o",
            "a",
            "os",
            "as",
            "um",
            "uma",
            "de",
            "para",
            "com",
            "por",
            "em",
            "é",
            "que",
            "se",
            "não",
            "mais",
            "como",
        ],
        "exclusive_words": [
            "para",
            "pelo",
            "essa",
            "esse",
            "aquela",
            "àquele",
            "neste",
            "nesta",
            "pela",
        ],
        "accented_chars": "ãõáéíóúàâêôûç",
        "patterns": [r"\b(para|como|onde|pela|pelo)\b"],
    },
    "en": {
        "common_words": [
            "the",
            "a",
            "an",
            "of",
            "to",
            "in",
            "is",
            "it",
            "you",
            "that",
            "he",
            "was",
            "for",
            "on",
            "are",
            "with",
            "as",
        ],
        "exclusive_words": [
            "the",
            "with",
            "from",
            "they",
            "their",
            "what",
            "which",
            "about",
            "after",
        ],
        "accented_chars": "",
        "patterns": [r"\b(the|is|you|that|with|from|they|their)\b"],
    },
    "es": {
        "common_words": [
            "el",
            "la",
            "los",
            "las",
            "un",
            "una",
            "de",
            "para",
            "con",
            "por",
            "en",
            "es",
            "que",
            "se",
            "no",
            "más",
            "como",
        ],
        "exclusive_words": ["sus", "sus", "estos", "estas", "aquel", "aquella", "donde"],
        "accented_chars": "áéíóúñü",
        "patterns": [r"\b(el|los|las|para|como|sus|estos)\b"],
    },
}


class LanguageDetector:
    """Detector de idioma baseado em padrões e heurísticas."""

    def __init__(
        self,
        default_language: str = "pt",
        supported_languages: list[str] | None = None,
        confidence_threshold: float = 0.6,
        enabled: bool = True,
    ):
        """Inicializa detector de idioma.

        Args:
            default_language: Idioma padrão quando detecção falha
            supported_languages: Lista de idiomas suportados
            confidence_threshold: Confiança mínima para detecção
            enabled: Se detecção automática está habilitada
        """
        self.default_language = default_language
        self.supported_languages = supported_languages or ["pt", "en", "es"]
        self.confidence_threshold = confidence_threshold
        self.enabled = enabled

    def detect(self, text: str) -> tuple[str, float]:
        """Detecta idioma do texto.

        Args:
            text: Texto para detectar idioma

        Returns:
            Tupla (idioma, confiança)
        """
        if not self.enabled or not text or len(text.strip()) < 3:
            return self.default_language, 0.0

        text_lower = text.lower()
        scores = {}

        for lang in self.supported_languages:
            if lang not in LANGUAGE_PATTERNS:
                continue

            patterns = LANGUAGE_PATTERNS[lang]
            score = self._calculate_score(text_lower, patterns, lang)
            scores[lang] = score

        if not scores:
            return self.default_language, 0.0

        best_lang = max(scores, key=scores.get)
        best_score = scores[best_lang]

        if best_score < self.confidence_threshold:
            return self.default_language, 0.0

        return best_lang, best_score

    def _calculate_score(self, text: str, patterns: dict, lang: str) -> float:
        """Calcula score de confiança para um idioma.

        Args:
            text: Texto em minúsculas
            patterns: Padrões do idioma
            lang: Código do idioma

        Returns:
            Score entre 0 e 1
        """
        score = 0.0

        # 1. Checar palavras comuns (palavras exclusivas têm mais peso)
        common_words = patterns.get("common_words", [])
        exclusive_words = patterns.get("exclusive_words", [])

        if common_words or exclusive_words:
            text_words = set(text.split())

            # Dar peso extra para palavras exclusivas deste idioma
            for word in text_words:
                if word in exclusive_words:
                    score += 0.5  # Peso alto para exclusivas
                elif word in common_words:
                    score += 0.1  # Peso menor para comuns

            # Limitar score desta seção
            score = min(score, 0.7)

        # 2. Checar caracteres acentuados
        accented = patterns.get("accented_chars", "")
        if accented:
            accented_count = sum(1 for c in text if c in accented)
            if accented_count > 0:
                score += min(accented_count / len(text) * 2, 0.3)

        # 3. Checar padrões regex
        regex_patterns = patterns.get("patterns", [])
        import re

        for pattern in regex_patterns:
            if re.search(pattern, text):
                score += 0.2
                break

        return min(score, 1.0)

    def get_supported_languages(self) -> list[str]:
        """Retorna lista de idiomas suportados.

        Returns:
            Lista de códigos de idioma
        """
        return self.supported_languages.copy()

    def is_supported(self, language: str) -> bool:
        """Verifica se idioma é suportado.

        Args:
            language: Código do idioma

        Returns:
            True se suportado
        """
        return language in self.supported_languages

    def set_enabled(self, enabled: bool) -> None:
        """Habilita/desabilita detecção automática.

        Args:
            enabled: Novo estado
        """
        self.enabled = enabled

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do detector.

        Returns:
            Dicionário com estatísticas
        """

        return {
            "enabled": self.enabled,
            "default_language": self.default_language,
            "supported_languages": self.supported_languages,
            "confidence_threshold": self.confidence_threshold,
        }
