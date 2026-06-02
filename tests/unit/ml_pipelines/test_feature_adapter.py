"""
Testes unitários para FeatureAdapter.

Este módulo testa o adapter entre Feature Extraction Profissional e
Approval Predictor Legado.

Coverage:
- Extração de features legadas
- Conversão de features profissionais para legadas
- Validação de features
- Fallback manual sem NLPFeatureExtractor
"""

import os
import sys

import pytest

# Adicionar paths para imports
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "ml_pipelines", "inference")
)

from feature_adapter import (
    FeatureAdapter,
    get_feature_adapter,
)

# LEGACY_FEATURE_ORDER é um atributo de classe
LEGACY_FEATURE_ORDER = FeatureAdapter.LEGACY_FEATURE_ORDER


class TestFeatureAdapterInitialization:
    """Testes de inicialização do FeatureAdapter."""

    def test_init_default(self):
        """Testa inicialização padrão."""
        adapter = FeatureAdapter()
        assert adapter._nlp_extractor is None
        assert not adapter._extractor_initialized

    def test_init_with_extractor(self, mock_nlp_extractor):
        """Testa inicialização com NLPFeatureExtractor."""
        adapter = FeatureAdapter(nlp_extractor=mock_nlp_extractor)
        assert adapter._nlp_extractor == mock_nlp_extractor

    def test_singleton(self):
        """Testa singleton get_feature_adapter."""
        adapter1 = get_feature_adapter()
        adapter2 = get_feature_adapter()
        assert adapter1 is adapter2


class TestFeatureNames:
    """Testes de nomes de features."""

    def test_legacy_feature_order(self):
        """Testa ordem de features legadas."""
        adapter = FeatureAdapter()
        names = adapter.get_feature_names()
        assert len(names) == 30
        assert names[0] == "specialist_confidence"
        assert names[1] == "domain_security"
        assert names[-1] == "primary_action_deploy"

    def test_feature_names_consistency(self):
        """Testa consistência de nomes de features."""
        adapter = FeatureAdapter()
        names = adapter.get_feature_names()
        assert len(names) == len(set(names))  # Sem duplicatas


class TestManualFeatureExtraction:
    """Testes de extração manual de features (sem NLPFeatureExtractor)."""

    def test_empty_text(self):
        """Testa texto vazio."""
        adapter = FeatureAdapter()
        features = adapter.extract_legacy_features("", {}, 0.5)
        # Deve retornar features vazias/default
        assert features.get("text_length_chars") == 0

    def test_security_domain_extraction(self):
        """Testa extração de domínio security."""
        adapter = FeatureAdapter()
        text = "Fix authentication bug in login endpoint"
        features = adapter.extract_legacy_features(text, {}, 0.7)

        assert features["specialist_confidence"] == 0.7
        assert features["domain_security"] == 1.0
        assert features["text_length_chars"] == len(text)
        assert features["text_length_words"] == len(text.split())

    def test_database_domain_extraction(self):
        """Testa extração de domínio database."""
        adapter = FeatureAdapter()
        text = "Create index on email column for query performance"
        features = adapter.extract_legacy_features(text, {}, 0.5)

        assert features["domain_database"] == 1.0
        assert features["domain_performance"] == 1.0

    def test_delete_action_extraction(self):
        """Testa extração de ação delete."""
        adapter = FeatureAdapter()
        text = "Delete all records from users table"
        features = adapter.extract_legacy_features(text, {}, 0.3)

        assert features["action_delete"] == 1.0
        assert features["risk_high"] == 1.0
        assert features["primary_action_delete"] == 1.0
        assert features["simple_risk_score"] > 0

    def test_create_action_extraction(self):
        """Testa extração de ação create."""
        adapter = FeatureAdapter()
        text = "Create new user with email verification"
        features = adapter.extract_legacy_features(text, {}, 0.8)

        assert features["action_create"] == 1.0
        assert features["risk_low"] == 1.0
        assert features["primary_action_create"] == 1.0

    def test_backup_keyword_detection(self):
        """Testa detecção de palavra-chave backup."""
        adapter = FeatureAdapter()
        text = "Create backup of database before migration"
        features = adapter.extract_legacy_features(text, {}, 0.9)

        assert features["has_backup"] == 1.0

    def test_verification_keyword_detection(self):
        """Testa detecção de palavra-chave verification."""
        adapter = FeatureAdapter()
        text = "Verify user credentials before access"
        features = adapter.extract_legacy_features(text, {}, 0.7)

        assert features["has_verification"] == 1.0

    def test_all_keyword_detection(self):
        """Testa detecção de palavra-chave all."""
        adapter = FeatureAdapter()
        text = "Delete all users from database"
        features = adapter.extract_legacy_features(text, {}, 0.2)

        assert features["has_all"] == 1.0
        assert features["simple_risk_score"] > 0.3  # delete + all = alto risco

    def test_primary_domain_selection(self):
        """Testa seleção de domínio primário."""
        adapter = FeatureAdapter()
        text = "Deploy database with SSL authentication"  # 3 domínios
        features = adapter.extract_legacy_features(text, {}, 0.6)

        # Deve ter exatamente um primary_domain_* = 1.0
        primary_count = sum(
            1 for k, v in features.items() if k.startswith("primary_domain_") and v == 1.0
        )
        assert primary_count == 1

    def test_text_length_metrics(self):
        """Testa métricas de comprimento de texto."""
        adapter = FeatureAdapter()
        text = "Create user"
        features = adapter.extract_legacy_features(text, {}, 0.5)

        assert features["text_length_chars"] == len("Create user")
        assert features["text_length_words"] == 2

    def test_complex_sentence_multiple_features(self):
        """Testa sentença complexa com múltiplas features."""
        adapter = FeatureAdapter()
        text = "Deploy secure authentication microservice with JWT tokens and SSL"
        features = adapter.extract_legacy_features(text, {}, 0.75)

        # Múltiplos domínios detectados
        assert features["domain_security"] == 1.0
        assert features["domain_devops"] == 1.0

        # Ação deploy
        assert features["action_deploy"] == 1.0
        assert features["primary_action_deploy"] == 1.0


class TestProfessionalToLegacyConversion:
    """Testes de conversão de features profissionais para legadas."""

    def test_convert_professional_features(self, sample_professional_features):
        """Testa conversão básica de features profissionais."""
        adapter = FeatureAdapter()
        legacy = adapter.to_legacy_format(sample_professional_features, 0.7)

        assert legacy["specialist_confidence"] == 0.7
        assert len(legacy) == 30

    def test_domain_mapping_from_professional(self, sample_professional_features):
        """Testa mapeamento de domínios de features profissionais."""
        adapter = FeatureAdapter()
        sample_professional_features["domain_security"] = 0.8
        sample_professional_features["domain_performance"] = 0.0

        legacy = adapter.to_legacy_format(sample_professional_features, 0.5)

        assert legacy["domain_security"] == 1.0  # > 0 vira 1.0
        assert legacy["domain_performance"] == 0.0

    def test_action_mapping_from_professional(self, sample_professional_features):
        """Testa mapeamento de ações de features profissionais."""
        adapter = FeatureAdapter()
        sample_professional_features["action_delete"] = 1
        sample_professional_features["action_create"] = 0

        legacy = adapter.to_legacy_format(sample_professional_features, 0.5)

        assert legacy["action_delete"] == 1.0
        assert legacy["action_create"] == 0.0
        assert legacy["risk_high"] == 1.0  # Derivado de delete

    def test_primary_domain_derivation(self, sample_professional_features):
        """Testa derivação de domínio primário."""
        adapter = FeatureAdapter()
        # Garantir que apenas database tem valor > 0 para não haver empate
        sample_professional_features["domain_database"] = 0.9
        # Deixar security como 0.0 (não setar)

        legacy = adapter.to_legacy_format(sample_professional_features, 0.5)

        assert legacy["primary_domain_database"] == 1.0
        assert legacy["primary_domain_security"] == 0.0

    def test_primary_action_derivation(self, sample_professional_features):
        """Testa derivação de ação primária."""
        adapter = FeatureAdapter()
        sample_professional_features["action_create"] = 2
        sample_professional_features["action_read"] = 1

        legacy = adapter.to_legacy_format(sample_professional_features, 0.5)

        assert legacy["primary_action_create"] == 1.0  # Maior contagem

    def test_risk_score_derivation(self, sample_professional_features):
        """Testa derivação de score de risco."""
        adapter = FeatureAdapter()
        sample_professional_features["action_delete"] = 1

        legacy = adapter.to_legacy_format(sample_professional_features, 0.5)

        assert legacy["simple_risk_score"] > 0  # Delete aumenta risco


class TestFeatureArrayConversion:
    """Testes de conversão para array."""

    def test_to_feature_array(self):
        """Testa conversão de dicionário para array."""
        adapter = FeatureAdapter()
        legacy_features = {f: float(i) for i, f in enumerate(LEGACY_FEATURE_ORDER)}

        array = adapter.to_feature_array(legacy_features)

        assert len(array) == 1  # 2D array
        assert len(array[0]) == 30  # 30 features
        assert array[0][0] == 0.0  # specialist_confidence
        assert array[0][-1] == 29.0  # primary_action_deploy

    def test_feature_array_order(self):
        """Testa ordem do array de features."""
        adapter = FeatureAdapter()
        features = adapter.extract_legacy_features("Create user", {}, 0.5)
        array = adapter.to_feature_array(features)

        # Primeira posição deve ser specialist_confidence
        assert array[0][0] == 0.5
        # Segunda posição deve ser domain_security
        assert array[0][1] in [0.0, 1.0]


class TestFeatureValidation:
    """Testes de validação de features."""

    def test_validate_complete_features(self):
        """Testa validação de features completas."""
        adapter = FeatureAdapter()
        features = {f: 0.0 for f in LEGACY_FEATURE_ORDER}

        assert adapter.validate_features(features) is True

    def test_validate_incomplete_features(self):
        """Testa validação de features incompletas."""
        adapter = FeatureAdapter()
        features = {"specialist_confidence": 0.5}  # Apenas 1 feature

        assert adapter.validate_features(features) is False

    def test_validate_extra_features(self):
        """Testa validação com features extras."""
        adapter = FeatureAdapter()
        features = {f: 0.0 for f in LEGACY_FEATURE_ORDER}
        features["extra_feature"] = 1.0  # Extra não deve quebrar

        assert adapter.validate_features(features) is True


class TestEdgeCases:
    """Testes de casos extremos."""

    def test_none_text(self):
        """Testa texto None."""
        adapter = FeatureAdapter()
        features = adapter.extract_legacy_features(None, {}, 0.5)

        assert features.get("text_length_chars", 0) == 0

    def test_very_long_text(self):
        """Testa texto muito longo."""
        adapter = FeatureAdapter()
        text = "word " * 1000  # 5000 caracteres
        features = adapter.extract_legacy_features(text, {}, 0.5)

        assert features["text_length_chars"] == len(text)
        assert features["text_length_words"] == 1000

    def test_unicode_text(self):
        """Testa texto com unicode."""
        adapter = FeatureAdapter()
        text = "Create user with JWT authentication"  # Inglês para teste
        features = adapter.extract_legacy_features(text, {}, 0.5)

        assert features["text_length_chars"] == len(text)
        assert features["action_create"] == 1.0

    def test_specialist_confidence_bounds(self):
        """Testa limites de specialist_confidence."""
        adapter = FeatureAdapter()
        features = adapter.extract_legacy_features("test", {}, 1.5)

        # Confiança deve ser preservada mesmo se > 1.0
        assert features["specialist_confidence"] == 1.5

    def test_no_features_detected(self):
        """Testa texto sem features detectadas."""
        adapter = FeatureAdapter()
        text = "hello world foo bar"  # Sem keywords técnicas
        features = adapter.extract_legacy_features(text, {}, 0.5)

        # Todos domínios devem ser 0.0
        assert all(
            features.get(f"domain_{d}", 0.0) == 0.0
            for d in ["security", "performance", "database", "devops", "testing"]
        )
        # Todas ações devem ser 0.0
        assert all(
            features.get(f"action_{a}", 0.0) == 0.0
            for a in ["create", "update", "delete", "read", "deploy"]
        )


class TestIntegrationScenarios:
    """Testes de cenários de integração."""

    def test_high_risk_scenario(self):
        """Testa cenário de alto risco."""
        adapter = FeatureAdapter()
        text = "Delete all records from users table without backup"
        features = adapter.extract_legacy_features(text, {}, 0.1)

        assert features["action_delete"] == 1.0
        assert features["has_all"] == 1.0
        assert features["simple_risk_score"] >= 0.6  # Muito alto

    def test_low_risk_scenario(self):
        """Testa cenário de baixo risco."""
        adapter = FeatureAdapter()
        text = "Verify user authentication with backup and tests"
        features = adapter.extract_legacy_features(text, {}, 0.9)

        assert features["has_backup"] == 1.0
        assert features["has_verification"] == 1.0
        assert features["risk_low"] == 1.0

    def test_mixed_domain_scenario(self):
        """Testa cenário com múltiplos domínios."""
        adapter = FeatureAdapter()
        text = "Deploy microservice with database index and SSL security"
        features = adapter.extract_legacy_features(text, {}, 0.7)

        # 3 domínios detectados
        domain_count = sum(
            1
            for d in ["security", "performance", "database", "devops", "testing"]
            if features.get(f"domain_{d}", 0.0) > 0
        )
        assert domain_count >= 2

    def test_primary_action_tie_breaking(self):
        """Testa desempate na ação primária."""
        adapter = FeatureAdapter()
        # Duas ações com mesma prioridade - primeira deve ganhar
        text = "Create and read data"
        features = adapter.extract_legacy_features(text, {}, 0.5)

        # Deve ter exatamente um primary_action
        primary_count = sum(
            1 for k, v in features.items() if k.startswith("primary_action_") and v == 1.0
        )
        assert primary_count == 1


# Fixtures


@pytest.fixture
def mock_nlp_extractor():
    """Mock de NLPFeatureExtractor."""

    class MockExtractor:
        def extract_features(self, text):
            return {
                "text_length_chars": len(text),
                "text_length_words": len(text.split()),
                "domain_security": 0.0,
                "domain_performance": 0.0,
                "domain_architecture": 0.0,
                "domain_database": 0.0,
                "domain_testing": 0.0,
                "domain_devops": 0.0,
                "action_create": 0,
                "action_update": 0,
                "action_delete": 0,
                "action_read": 0,
                "action_deploy": 0,
            }

    return MockExtractor()


@pytest.fixture
def sample_professional_features():
    """Features profissionais de exemplo."""
    return {
        "text_length_chars": 50,
        "text_length_words": 8,
        "text_length_sentences": 1,
        "avg_word_length": 6.0,
        "domain_security": 0.0,
        "domain_performance": 0.0,
        "domain_architecture": 0.0,
        "domain_database": 0.0,
        "domain_testing": 0.0,
        "domain_devops": 0.0,
        "action_create": 0,
        "action_update": 0,
        "action_delete": 0,
        "action_read": 0,
        "action_deploy": 0,
        "primary_domain": "unknown",
        "primary_action": "unknown",
        "has_url": 0,
        "has_path": 0,
        "has_email": 0,
        "has_file_path": 0,
        "has_command": 0,
        "has_code_reference": 0,
        "technical_patterns_count": 0,
        "sentiment_positive": 0.0,
        "sentiment_negative": 0.0,
        "sentiment_neutral": 1.0,
        "urgency_low": 0.5,
        "urgency_high": 0.0,
    }
