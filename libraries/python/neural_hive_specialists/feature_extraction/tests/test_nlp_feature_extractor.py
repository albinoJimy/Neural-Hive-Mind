"""
Testes para NLPFeatureExtractor.

Valida extração de features NLP de texto de intenções.
"""

import pytest

from neural_hive_specialists.feature_extraction.nlp_feature_extractor import (
    NLPFeatureExtractor,
    get_nlp_extractor,
)


class TestNLPFeatureExtractor:
    """Testes para NLPFeatureExtractor."""

    def test_initialization(self):
        """Testa inicialização do extrator."""
        extractor = NLPFeatureExtractor(enable_sentiment=True)
        assert extractor is not None
        assert extractor.enable_sentiment is True

    def test_extract_features_empty_text(self):
        """Testa extração de features de texto vazio."""
        extractor = NLPFeatureExtractor()

        features = extractor.extract_features("")
        assert features is not None
        assert features["text_length_chars"] == 0
        assert features["text_length_words"] == 0

    def test_extract_features_none_text(self):
        """Testa extração de features de texto None."""
        extractor = NLPFeatureExtractor()

        features = extractor.extract_features(None)
        assert features is not None
        assert features["text_length_chars"] == 0

    def test_extract_features_security_domain(self):
        """Testa detecção de domínio security."""
        extractor = NLPFeatureExtractor()

        text = "Fix authentication bug in login endpoint with JWT token validation"
        features = extractor.extract_features(text)

        assert features["domain_security"] > 0
        assert features["primary_domain"] == "security"

    def test_extract_features_performance_domain(self):
        """Testa detecção de domínio performance."""
        extractor = NLPFeatureExtractor()

        text = "Optimize slow database query with redis cache and indexing"
        features = extractor.extract_features(text)

        assert features["domain_performance"] > 0
        assert features["primary_domain"] == "performance"

    def test_extract_features_technical_patterns(self):
        """Testa detecção de padrões técnicos."""
        extractor = NLPFeatureExtractor()

        text = "Deploy https://api.example.com/users and fix auth/user.py:123"
        features = extractor.extract_features(text)

        assert features["has_url"] == 1
        assert features["has_file_path"] == 1
        assert features["technical_patterns_count"] >= 2

    def test_extract_features_action_create(self):
        """Testa detecção de ação create."""
        extractor = NLPFeatureExtractor()

        text = "Create new user endpoint with authentication"
        features = extractor.extract_features(text)

        assert features["action_create"] >= 1
        assert features["primary_action"] == "create"

    def test_extract_features_action_delete(self):
        """Testa detecção de ação delete."""
        extractor = NLPFeatureExtractor()

        text = "Remove old user and delete database records"
        features = extractor.extract_features(text)

        assert features["action_delete"] >= 1
        assert features["primary_action"] == "delete"

    def test_extract_features_sentiment_positive(self):
        """Testa detecção de sentimento positivo."""
        extractor = NLPFeatureExtractor(enable_sentiment=True)

        text = "Great fix! Works perfectly and very fast"
        features = extractor.extract_features(text)

        assert features["sentiment_positive"] > 0

    def test_extract_features_sentiment_negative(self):
        """Testa detecção de sentimento negativo."""
        extractor = NLPFeatureExtractor(enable_sentiment=True)

        text = "Bug blocking deployment, critical issue with authentication"
        features = extractor.extract_features(text)

        assert features["sentiment_negative"] > 0
        assert features["urgency_high"] > 0

    def test_extract_features_composite_text(self):
        """Testa extração de features de texto composto."""
        extractor = NLPFeatureExtractor()

        text = """
        Create secure authentication microservice with JWT tokens.
        Add user login, password reset, and role-based access control.
        Fix SQL injection vulnerability in user management.
        Deploy to kubernetes with docker and CI/CD pipeline.
        """
        features = extractor.extract_features(text)

        # Validar múltiplos domínios detectados
        assert features["domain_security"] > 0  # authentication, JWT, SQL injection
        assert features["domain_devops"] > 0  # kubernetes, docker, CI/CD
        assert features["domain_database"] > 0  # SQL

        # Validar ações
        assert features["action_create"] >= 1  # Create, Add
        assert features["action_deploy"] >= 1  # Deploy

        # Validar padrões técnicos
        assert features["technical_patterns_count"] >= 1

    def test_get_feature_names(self):
        """Testa obtenção de nomes de features."""
        extractor = NLPFeatureExtractor()
        names = extractor.get_feature_names()

        assert isinstance(names, list)
        assert len(names) > 20  # Deve ter pelo menos 20 features
        assert "text_length_chars" in names
        assert "domain_security" in names
        assert "has_url" in names

    def test_singleton_get_nlp_extractor(self):
        """Testa função singleton get_nlp_extractor."""
        extractor1 = get_nlp_extractor()
        extractor2 = get_nlp_extractor()

        # Deve retornar a mesma instância
        assert extractor1 is extractor2


if __name__ == "__main__":
    # Executar testes
    pytest.main([__file__, "-v"])
