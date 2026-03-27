"""
Módulo de Extração de Features NLP para Texto de Intenções.

Este módulo extrai features linguísticas do texto bruto de intenções
para uso em treinamento de modelos ML.

Features extraídas:
- Comprimento do texto (caracteres, palavras, sentenças)
- Contagem de palavras-chave técnicas
- Análise de sentimento básica
- Detecção de domínio (security, performance, architecture, etc.)
- Complexidade textual
- Presença de padrões específicos (URLs, paths, comandos)
"""

import re
from typing import Dict, List, Any, Optional, Set
from collections import Counter
import structlog

logger = structlog.get_logger()


class NLPFeatureExtractor:
    """
    Extrai features NLP do texto de intenções para enriquecimento de feedback.

    Não depende de bibliotecas pesadas de NLP (spacy, transformers)
    para manter latência baixa. Usa regex e regras simples.
    """

    # Palavras-chave por domínio
    DOMAIN_KEYWORDS = {
        "security": [
            "security",
            "auth",
            "authentication",
            "authorization",
            "password",
            "login",
            "token",
            "jwt",
            "oauth",
            "ssl",
            "tls",
            "encryption",
            "vulnerability",
            "xss",
            "csrf",
            "injection",
            "firewall",
            "access",
            "permission",
            "role",
            "user",
            "identity",
            "credential",
            "hash",
        ],
        "performance": [
            "performance",
            "optimization",
            "slow",
            "fast",
            "cache",
            "redis",
            "latency",
            "throughput",
            "scale",
            "load",
            "database",
            "query",
            "index",
            "memcached",
            "response",
            "time",
            "speed",
            "benchmark",
            "profiling",
            "async",
            "concurrent",
            "parallel",
        ],
        "architecture": [
            "architecture",
            "design",
            "pattern",
            "microservice",
            "monolith",
            "structure",
            "component",
            "module",
            "layer",
            "service",
            "api",
            "endpoint",
            "interface",
            "coupling",
            "cohesion",
            "dependency",
            "diagram",
            "schema",
            "model",
            "entity",
            "repository",
        ],
        "database": [
            "database",
            "db",
            "sql",
            "nosql",
            "mongodb",
            "postgres",
            "mysql",
            "query",
            "table",
            "collection",
            "index",
            "migration",
            "seed",
            "orm",
            "relation",
            "column",
            "field",
            "record",
            "document",
        ],
        "testing": [
            "test",
            "testing",
            "unit",
            "integration",
            "e2e",
            "mock",
            "stub",
            "spec",
            "coverage",
            "tdd",
            "bdd",
            "assertion",
            "fixture",
            "pytest",
            "jest",
            "cypress",
            "selenium",
        ],
        "devops": [
            "deploy",
            "deployment",
            "ci",
            "cd",
            "pipeline",
            "docker",
            "kubernetes",
            "k8s",
            "container",
            "helm",
            "terraform",
            "ansible",
            "jenkins",
            "github",
            "gitlab",
            "actions",
            "workflow",
            "release",
            "build",
        ],
    }

    # Indicadores de ação/categoria
    ACTION_PATTERNS = {
        "create": ["create", "add", "insert", "new", "make", "build", "generate"],
        "update": ["update", "modify", "change", "edit", "alter", "fix", "patch"],
        "delete": ["delete", "remove", "drop", "destroy", "clean", "clear"],
        "read": ["get", "fetch", "find", "list", "show", "display", "view", "read"],
        "deploy": ["deploy", "release", "ship", "publish", "push"],
    }

    # Padrões técnicos
    TECHNICAL_PATTERNS = {
        "url": r"https?://[^\s]+",
        "path": r"/[\w\-./]+",
        "email": r"[\w.]+@[\w.]+\.\w+",
        "file_path": r"[\w~/\-./]+\.(py|js|ts|java|go|rs|sql|yaml|yml|json|md|txt)",
        "command": r"(npm|pip|pytest|docker|kubectl|git|maven|gradle|cargo)\s+\w+",
        "code_reference": r"[\w]+\.(py|js|ts|java|go|rs|sql):[\d:]+",
    }

    def __init__(self, enable_sentiment: bool = True):
        """
        Inicializa extrator de features NLP.

        Args:
            enable_sentiment: Habilita análise de sentimento básica
        """
        self.enable_sentiment = enable_sentiment

        # Compilar regex patterns
        self.compiled_patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.TECHNICAL_PATTERNS.items()
        }

        logger.info(
            "NLPFeatureExtractor initialized",
            enable_sentiment=enable_sentiment,
            domains_count=len(self.DOMAIN_KEYWORDS),
        )

    def extract_features(self, text: str) -> Dict[str, Any]:
        """
        Extrai todas as features do texto.

        Args:
            text: Texto bruto da intenção

        Returns:
            Dict com features extraídas
        """
        if not text or not isinstance(text, str):
            return self._empty_features()

        # Normalizar texto
        text_normalized = self._normalize_text(text)

        # Extrair grupos de features
        features = {
            # Features básicas de texto
            **self._extract_basic_features(text, text_normalized),
            # Features de domínio
            **self._extract_domain_features(text_normalized),
            # Features de padrões técnicos
            **self._extract_technical_patterns(text),
            # Features de ação
            **self._extract_action_features(text_normalized),
            # Features de sentimento (se habilitado)
            **(
                self._extract_sentiment_features(text_normalized)
                if self.enable_sentiment
                else {}
            ),
        }

        return features

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para análise."""
        return text.lower().strip()

    def _empty_features(self) -> Dict[str, Any]:
        """Retorna features vazias com defaults."""
        return {
            # Texto básico
            "text_length_chars": 0,
            "text_length_words": 0,
            "text_length_sentences": 0,
            "avg_word_length": 0.0,
            # Domínios
            "domain_security": 0.0,
            "domain_performance": 0.0,
            "domain_architecture": 0.0,
            "domain_database": 0.0,
            "domain_testing": 0.0,
            "domain_devops": 0.0,
            "primary_domain": "unknown",
            # Padrões técnicos
            "has_url": 0,
            "has_path": 0,
            "has_email": 0,
            "has_file_path": 0,
            "has_command": 0,
            "has_code_reference": 0,
            "technical_patterns_count": 0,
            # Ações
            "action_create": 0,
            "action_update": 0,
            "action_delete": 0,
            "action_read": 0,
            "action_deploy": 0,
            "primary_action": "unknown",
            # Sentimento
            "sentiment_positive": 0.0,
            "sentiment_negative": 0.0,
            "sentiment_neutral": 0.0,
            "urgency_low": 0.0,
            "urgency_high": 0.0,
        }

    def _extract_basic_features(
        self, text: str, text_normalized: str
    ) -> Dict[str, Any]:
        """Extrai features básicas do texto."""
        chars = len(text)
        words = len(text_normalized.split()) if text_normalized else 0
        sentences = max(1, len(re.split(r"[.!?]+", text))) if text else 0

        # Comprimento médio das palavras
        word_lengths = [len(w) for w in text_normalized.split() if w]
        avg_word_len = sum(word_lengths) / len(word_lengths) if word_lengths else 0.0

        return {
            "text_length_chars": chars,
            "text_length_words": words,
            "text_length_sentences": sentences,
            "avg_word_length": round(avg_word_len, 2),
        }

    def _extract_domain_features(self, text: str) -> Dict[str, Any]:
        """Extrai features de domínio do texto."""
        domain_scores = {}
        word_counts = Counter(text.split())
        total_words = sum(word_counts.values()) or 1

        # Contar palavras por domínio
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            count = sum(word_counts.get(kw, 0) for kw in keywords)
            domain_scores[f"domain_{domain}"] = round(count / total_words, 4)

        # Identificar domínio primário
        if domain_scores:
            primary_domain = max(domain_scores.items(), key=lambda x: x[1])
            domain_scores["primary_domain"] = (
                primary_domain[0] if primary_domain[1] > 0 else "unknown"
            )
        else:
            domain_scores["primary_domain"] = "unknown"

        return domain_scores

    def _extract_technical_patterns(self, text: str) -> Dict[str, Any]:
        """Extrai contagem de padrões técnicos."""
        features = {}
        total_count = 0

        for name, pattern in self.compiled_patterns.items():
            matches = pattern.findall(text)
            count = len(matches)
            features[f"has_{name}"] = 1 if count > 0 else 0
            total_count += count

        features["technical_patterns_count"] = total_count
        return features

    def _extract_action_features(self, text: str) -> Dict[str, Any]:
        """Extrai features de ação/comando."""
        words = set(text.split())
        features = {}

        for action, patterns in self.ACTION_PATTERNS.items():
            count = sum(1 for word in words if any(p in word for p in patterns))
            features[f"action_{action}"] = count

        # Identificar ação primária
        action_counts = {k: v for k, v in features.items() if v > 0}
        if action_counts:
            primary = max(action_counts.items(), key=lambda x: x[1])
            features["primary_action"] = primary[7:]  # Remove 'action_' prefix
        else:
            features["primary_action"] = "unknown"

        return features

    def _extract_sentiment_features(self, text: str) -> Dict[str, Any]:
        """Extrai features de sentimento básicas."""
        # Palavras positivas e negativas simples
        positive_words = [
            "good",
            "great",
            "excellent",
            "better",
            "best",
            "love",
            "perfect",
            "works",
            "working",
            "success",
            "successful",
            "fix",
            "solved",
            "resolved",
            "improve",
            "improvement",
            "optimization",
            "fast",
            "quick",
            "easy",
            "simple",
        ]

        negative_words = [
            "bad",
            "worst",
            "hate",
            "broken",
            "fails",
            "failing",
            "error",
            "issue",
            "problem",
            "bug",
            "crash",
            "slow",
            "difficult",
            "complex",
            "complicated",
            "confusing",
            "urgent",
            "critical",
            "blocking",
            "blocked",
        ]

        urgency_words = [
            "urgent",
            "asap",
            "immediately",
            "critical",
            "blocking",
            "priority",
        ]

        words = text.split()
        total_words = len(words) or 1

        positive_count = sum(1 for w in words if any(pw in w for pw in positive_words))
        negative_count = sum(1 for w in words if any(nw in w for nw in negative_words))
        urgency_count = sum(1 for w in words if any(uw in w for uw in urgency_words))

        return {
            "sentiment_positive": round(positive_count / total_words, 4),
            "sentiment_negative": round(negative_count / total_words, 4),
            "sentiment_neutral": round(
                1 - (positive_count + negative_count) / total_words, 4
            ),
            "urgency_low": 0.0 if urgency_count == 0 else 0.5,
            "urgency_high": 1.0 if urgency_count > 0 else 0.0,
        }

    def get_feature_names(self) -> List[str]:
        """Retorna lista de nomes de features extraídas."""
        return list(self._empty_features().keys())


# Singleton para uso fácil
_default_extractor: Optional[NLPFeatureExtractor] = None


def get_nlp_extractor() -> NLPFeatureExtractor:
    """Retorna instância singleton do extrator."""
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = NLPFeatureExtractor()
    return _default_extractor
