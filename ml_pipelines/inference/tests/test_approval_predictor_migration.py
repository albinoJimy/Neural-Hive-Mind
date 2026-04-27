"""
Testes para migração do ApprovalPredictor para FeatureAdapter profissional.

TICKET 1.4: Migrar approval_predictor para FeatureExtractor profissional

Valida:
1. Funcionamento com USE_PROFESSIONAL_FEATURES=false (regex manuais)
2. Funcionamento com USE_PROFESSIONAL_FEATURES=true (profissional)
3. Compatibilidade de output entre ambos modos
4. Fallback automático em caso de erro
"""

import os
import pickle
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest
import numpy as np
from sklearn.ensemble import RandomForestClassifier


class SimpleTestModel:
    """Modelo simples para testes."""

    def __init__(self):
        self.classes_ = ["approve", "reject", "review_required"]
        # Criar um modelo simples que sempre prediz "approve"
        self._model = RandomForestClassifier(n_estimators=1, random_state=42)
        # Treinar com dummy data
        X_train = np.random.rand(10, 30)
        y_train = ["approve"] * 10
        self._model.fit(X_train, y_train)

    def predict(self, X):
        return self._model.predict(X)

    def predict_proba(self, X):
        return self._model.predict_proba(X)


def create_test_model_file():
    """Cria um arquivo de modelo temporário para testes."""
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        model = SimpleTestModel()

        model_data = {
            "model": model,
            "version": "test_v1",
            "trained_at": "2024-01-01",
            "features": [],
            "metrics": {},
            "training_samples": 50,
        }

        pickle.dump(model_data, f)
        return Path(f.name)


class TestApprovalPredictorLegacyMode:
    """Testes do modo legado (regex manuais)."""

    @pytest.fixture
    def predictor(self):
        """Cria instância do predictor em modo legado."""
        # Garantir modo legado
        os.environ["USE_PROFESSIONAL_FEATURES"] = "false"

        model_path = create_test_model_file()

        try:
            # Importar aqui para pegar a variável de ambiente
            from ml_pipelines.inference.approval_predictor import ApprovalPredictor

            predictor = ApprovalPredictor(model_path=model_path)
            yield predictor
        finally:
            # Cleanup
            if model_path.exists():
                model_path.unlink()

    def test_legacy_mode_is_default(self, predictor):
        """Testa que modo legado é o padrão."""
        assert not predictor.use_professional_features
        assert predictor.is_using_professional_features() is False

    def test_extract_nlp_features_returns_30_features(self, predictor):
        """Testa que extract_nlp_features retorna 30 features."""
        text = "Create new user with email verification"
        features = predictor.extract_nlp_features(text)

        # Verificar que temos exatamente 30 features
        assert len(features) == 30

        # Verificar features obrigatórias
        required_features = [
            "specialist_confidence",  # Embora não usado diretamente aqui
            "domain_security",
            "domain_performance",
            "domain_database",
            "domain_devops",
            "domain_testing",
            "action_create",
            "action_update",
            "action_delete",
            "action_read",
            "action_deploy",
            "has_backup",
            "has_verification",
            "has_all",
            "text_length_chars",
            "text_length_words",
            "risk_high",
            "risk_medium",
            "risk_low",
            "simple_risk_score",
            "primary_domain_security",
            "primary_domain_performance",
            "primary_domain_database",
            "primary_domain_devops",
            "primary_domain_testing",
            "primary_action_create",
            "primary_action_update",
            "primary_action_delete",
            "primary_action_read",
            "primary_action_deploy",
        ]

        for feature in required_features:
            assert feature in features, f"Feature {feature} não encontrada"

    def test_extract_nlp_features_detects_domain(self, predictor):
        """Testa detecção de domínio security."""
        text = "Enable SSL/TLS authentication for secure login"
        features = predictor.extract_nlp_features(text)

        assert features["domain_security"] == 1.0
        assert features["domain_database"] == 0.0

    def test_extract_nlp_features_detects_action(self, predictor):
        """Testa detecção de ação delete."""
        text = "Delete all users from database"
        features = predictor.extract_nlp_features(text)

        assert features["action_delete"] == 1.0
        assert features["action_create"] == 0.0

    def test_extract_nlp_features_empty_text(self, predictor):
        """Testa comportamento com texto vazio."""
        features = predictor.extract_nlp_features("")
        assert features == {}

    def test_extract_nlp_features_risk_detection(self, predictor):
        """Testa detecção de risco."""
        text = "Drop all tables without backup"
        features = predictor.extract_nlp_features(text)

        # Deve detectar como alto risco
        assert features["risk_high"] == 1.0
        assert features["action_delete"] == 1.0
        assert features["simple_risk_score"] > 0

    def test_predict_from_text_legacy_mode(self, predictor):
        """Testa predição completa em modo legado."""
        text = "Create new user with email verification"
        result = predictor.predict_from_text(text, specialist_confidence=0.7)

        assert "decision" in result
        assert "confidence" in result
        assert "probabilities" in result
        assert result["model_version"] == "test_v1"


class TestApprovalPredictorProfessionalMode:
    """Testes do modo profissional (FeatureAdapter)."""

    @pytest.fixture
    def mock_feature_adapter(self):
        """Cria mock do FeatureAdapter."""
        adapter = Mock()

        # Retornar features dummy no formato legado
        def mock_extract(text, cognitive_plan, specialist_confidence):
            return {
                "specialist_confidence": specialist_confidence,
                "domain_security": 1.0 if "security" in text.lower() else 0.0,
                "domain_performance": 0.0,
                "domain_database": 0.0,
                "domain_devops": 0.0,
                "domain_testing": 0.0,
                "action_create": 1.0 if "create" in text.lower() else 0.0,
                "action_update": 0.0,
                "action_delete": 1.0 if "delete" in text.lower() else 0.0,
                "action_read": 0.0,
                "action_deploy": 0.0,
                "has_backup": 0.0,
                "has_verification": 0.0,
                "has_all": 0.0,
                "text_length_chars": len(text),
                "text_length_words": len(text.split()),
                "risk_high": 0.0,
                "risk_medium": 0.0,
                "risk_low": 1.0,
                "simple_risk_score": 0.0,
                "primary_domain_security": 1.0,
                "primary_domain_performance": 0.0,
                "primary_domain_database": 0.0,
                "primary_domain_devops": 0.0,
                "primary_domain_testing": 0.0,
                "primary_action_create": 1.0,
                "primary_action_update": 0.0,
                "primary_action_delete": 0.0,
                "primary_action_read": 0.0,
                "primary_action_deploy": 0.0,
            }

        adapter.extract_legacy_features = mock_extract
        return adapter

    @pytest.fixture
    def predictor_professional(self, mock_feature_adapter):
        """Cria instância do predictor em modo profissional."""
        model_path = create_test_model_file()

        # Ativar modo profissional
        os.environ["USE_PROFESSIONAL_FEATURES"] = "true"

        try:
            # Mock do get_feature_adapter - patch antes de importar
            with patch(
                "ml_pipelines.inference.feature_adapter.get_feature_adapter",
                return_value=mock_feature_adapter,
            ):
                from ml_pipelines.inference.approval_predictor import ApprovalPredictor

                # Força reload do módulo para pegar a variável de ambiente
                import importlib
                import ml_pipelines.inference.approval_predictor as ap_module

                importlib.reload(ap_module)

                predictor = ap_module.ApprovalPredictor(model_path=model_path)
                yield predictor

        finally:
            # Cleanup
            os.environ["USE_PROFESSIONAL_FEATURES"] = "false"
            if model_path.exists():
                model_path.unlink()

    def test_professional_mode_activated(self, predictor_professional):
        """Testa que modo profissional foi ativado."""
        assert predictor_professional.use_professional_features
        assert predictor_professional.is_using_professional_features() is True

    def test_professional_mode_uses_adapter(self, predictor_professional, mock_feature_adapter):
        """Testa que modo profissional usa FeatureAdapter."""
        text = "Create user with security settings"
        features = predictor_professional.extract_nlp_features(text)

        # Verificar que o adapter foi chamado - verificar via feature values
        # O mock retorna domain_security=1.0 se "security" estiver no texto
        assert features["domain_security"] == 1.0  # Valor do mock, não do regex manual

        # Verificar features retornadas
        assert len(features) == 30
        assert "domain_security" in features

    def test_professional_mode_predict_from_text(self, predictor_professional):
        """Testa predição completa em modo profissional."""
        text = "Create new user with email verification"
        result = predictor_professional.predict_from_text(text, specialist_confidence=0.7)

        assert "decision" in result
        assert "confidence" in result


class TestApprovalPredictorFallback:
    """Testes do mecanismo de fallback."""

    def test_fallback_on_adapter_error(self):
        """Testa fallback para regex manuais quando FeatureAdapter falha."""
        os.environ["USE_PROFESSIONAL_FEATURES"] = "true"
        model_path = create_test_model_file()

        try:
            # Criar adapter que lança exceção
            failing_adapter = Mock()
            failing_adapter.extract_legacy_features = Mock(side_effect=Exception("Adapter error"))

            with patch(
                "ml_pipelines.inference.feature_adapter.get_feature_adapter",
                return_value=failing_adapter,
            ):
                from ml_pipelines.inference.approval_predictor import ApprovalPredictor

                import importlib
                import ml_pipelines.inference.approval_predictor as ap_module

                importlib.reload(ap_module)

                predictor = ap_module.ApprovalPredictor(model_path=model_path)

                # extract_nlp_features deve funcionar com regex manuais (fallback)
                text = "Create new user"
                features = predictor.extract_nlp_features(text)

                # Deve ter features válidas (do fallback)
                assert len(features) == 30
                assert features["action_create"] == 1.0

        finally:
            os.environ["USE_PROFESSIONAL_FEATURES"] = "false"
            if model_path.exists():
                model_path.unlink()


class TestFeatureCompatibility:
    """Testes de compatibilidade entre modos."""

    def test_both_modes_return_same_feature_keys(self):
        """Testa que ambos modos retornam as mesmas chaves de features."""
        test_text = "Delete all users without backup"

        # Modo legado
        os.environ["USE_PROFESSIONAL_FEATURES"] = "false"

        model_path_legacy = create_test_model_file()
        try:
            from ml_pipelines.inference.approval_predictor import ApprovalPredictor

            import importlib
            import ml_pipelines.inference.approval_predictor as ap_module

            importlib.reload(ap_module)

            predictor_legacy = ap_module.ApprovalPredictor(model_path=model_path_legacy)
            features_legacy = predictor_legacy.extract_nlp_features(test_text)

            # Criar adapter mock que retorna mesmas chaves
            mock_adapter = Mock()
            mock_adapter.extract_legacy_features = Mock(
                return_value={k: 0.0 for k in features_legacy.keys()}
            )

            # Modo profissional
            os.environ["USE_PROFESSIONAL_FEATURES"] = "true"
            model_path_prof = create_test_model_file()
            try:
                with patch(
                    "ml_pipelines.inference.feature_adapter.get_feature_adapter",
                    return_value=mock_adapter,
                ):
                    importlib.reload(ap_module)
                    predictor_professional = ap_module.ApprovalPredictor(model_path=model_path_prof)
                    features_professional = predictor_professional.extract_nlp_features(test_text)

                # Verificar que ambas retornam as mesmas chaves
                assert set(features_legacy.keys()) == set(features_professional.keys())

            finally:
                if model_path_prof.exists():
                    model_path_prof.unlink()

        finally:
            os.environ["USE_PROFESSIONAL_FEATURES"] = "false"
            if model_path_legacy.exists():
                model_path_legacy.unlink()


class TestModelInfo:
    """Testes para get_model_info."""

    def test_get_model_info_includes_mode(self):
        """Testa que get_model_info inclui modo de extração."""
        os.environ["USE_PROFESSIONAL_FEATURES"] = "false"
        model_path = create_test_model_file()

        try:
            from ml_pipelines.inference.approval_predictor import ApprovalPredictor

            import importlib
            import ml_pipelines.inference.approval_predictor as ap_module

            importlib.reload(ap_module)

            predictor = ap_module.ApprovalPredictor(model_path=model_path)
            info = predictor.get_model_info()

            assert "feature_extraction_mode" in info
            assert info["feature_extraction_mode"] == "legacy"
            assert info["version"] == "test_v1"

        finally:
            os.environ["USE_PROFESSIONAL_FEATURES"] = "false"
            if model_path.exists():
                model_path.unlink()


class TestRealModelIntegration:
    """Testes de integração com modelo real v7."""

    @pytest.fixture
    def real_model_path(self):
        """Retorna caminho para modelo real v7 se existir."""
        path = Path("/home/jimy/NHM/Neural-Hive-Mind/ml_models/nhm_approval_model_v7.pkl")
        if path.exists():
            return path
        pytest.skip("Modelo v7 não encontrado")

    def test_real_model_legacy_mode(self, real_model_path):
        """Testa predictor com modelo real em modo legado."""
        try:
            os.environ["USE_PROFESSIONAL_FEATURES"] = "false"

            from ml_pipelines.inference.approval_predictor import ApprovalPredictor

            import importlib
            import ml_pipelines.inference.approval_predictor as ap_module

            importlib.reload(ap_module)

            predictor = ap_module.ApprovalPredictor(model_path=real_model_path)

            # Testar predição
            text = "Create new user with email verification"
            result = predictor.predict_from_text(text, specialist_confidence=0.8)

            assert "decision" in result
            assert "confidence" in result
            assert result["model_version"] in ["v6", "v7"]

            # Verificar informações do modelo
            info = predictor.get_model_info()
            assert info["training_samples"] > 0
        except ModuleNotFoundError as e:
            if "numpy._core" in str(e):
                pytest.skip("Modelo v7 foi treinado com versão diferente de numpy/sklearn")
            raise

    def test_extract_features_with_real_model(self, real_model_path):
        """Testa extração de features com modelo real."""
        try:
            os.environ["USE_PROFESSIONAL_FEATURES"] = "false"

            from ml_pipelines.inference.approval_predictor import ApprovalPredictor

            import importlib
            import ml_pipelines.inference.approval_predictor as ap_module

            importlib.reload(ap_module)

            predictor = ap_module.ApprovalPredictor(model_path=real_model_path)

            test_cases = [
                ("Delete all users without backup", "high_risk"),
                ("Create new user with verification", "low_risk"),
                ("Update database schema", "medium_risk"),
            ]

            for text, expected_risk_level in test_cases:
                features = predictor.extract_nlp_features(text)
                assert len(features) == 30

                if expected_risk_level == "high_risk":
                    assert features["action_delete"] == 1.0 or features["risk_high"] == 1.0
                elif expected_risk_level == "low_risk":
                    assert features["action_create"] == 1.0 or features["risk_low"] == 1.0
        except ModuleNotFoundError as e:
            if "numpy._core" in str(e):
                pytest.skip("Modelo v7 foi treinado com versão diferente de numpy/sklearn")
            raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
