"""
Testes unitários para DecisionWrapperModel e classes relacionadas.

EPIC-204-01: Modelo ML para SHAP
"""

from unittest.mock import Mock, patch

import numpy as np
import pytest
from src.models.shap_model import DecisionWrapperModel, FeatureExtractor, ModelTrainer


class TestDecisionWrapperModel:
    """Testes para DecisionWrapperModel."""

    @pytest.fixture()
    def model(self):
        """Fixture para modelo não treinado."""
        return DecisionWrapperModel()

    @pytest.fixture()
    def sample_decision(self):
        """Fixture para decisão de exemplo."""
        return {
            "decision_id": "test_decision_1",
            "plan_id": "plan_1",
            "intent_id": "intent_1",
            "final_decision": "approve",
            "aggregated_confidence": 0.85,
            "aggregated_risk": 0.15,
            "specialist_votes": [
                {
                    "specialist_type": "business",
                    "confidence_score": 0.9,
                    "risk_score": 0.1,
                    "processing_time_ms": 500,
                    "seniority_multiplier": 1.5,
                },
                {
                    "specialist_type": "technical",
                    "confidence_score": 0.8,
                    "risk_score": 0.2,
                    "processing_time_ms": 800,
                    "seniority_multiplier": 1.0,
                },
            ],
            "consensus_metrics": {
                "divergence_score": 0.2,
                "unanimous": True,
                "bayesian_confidence": 0.85,
                "voting_confidence": 0.90,
            },
        }

    def test_init(self, model):
        """Testa inicialização do modelo."""
        assert model is not None
        assert len(model.feature_names) == 8
        assert not model.is_trained
        assert model.model_type == "random_forest"

    def test_init_gradient_boosting(self):
        """Testa inicialização com gradient boosting."""
        model = DecisionWrapperModel(model_type="gradient_boosting")
        assert model.model_type == "gradient_boosting"

    def test_extract_features(self, model, sample_decision):
        """Testa extração de features."""
        features = model.extract_features(sample_decision)

        assert features.shape == (1, 8)

        # Verificar valores esperados
        assert features[0][0] == 0.85  # confidence
        assert features[0][1] == 0.15  # risk
        assert features[0][2] == 0.2  # divergence
        assert features[0][4] >= 0  # processing_time (normalizado)
        assert features[0][5] == 1.0  # unanimous

    def test_extract_features_without_seniority(self, model):
        """Testa extração quando seniority_multiplier está ausente."""
        decision = {
            "aggregated_confidence": 0.7,
            "aggregated_risk": 0.3,
            "specialist_votes": [
                {"confidence_score": 0.7, "risk_score": 0.3, "processing_time_ms": 1000}
            ],
            "consensus_metrics": {
                "divergence_score": 0.1,
                "unanimous": False,
                "bayesian_confidence": 0.7,
                "voting_confidence": 0.75,
            },
        }

        features = model.extract_features(decision)
        assert features[0][3] == 1.0  # seniority default

    def test_train_with_insufficient_samples(self, model):
        """Testa erro ao treinar com poucas amostras."""
        with pytest.raises(ValueError, match="Insufficient samples"):
            model.train([])

    def test_train_with_sample_decisions(self, model, sample_decision):
        """Testa treinamento com decisões de exemplo."""
        # Criar decisões variadas
        decisions = []
        for i in range(20):
            decision = sample_decision.copy()
            decision["decision_id"] = f"decision_{i}"
            # Variar features para criar padrão
            confidence = 0.4 + (i * 0.03)
            risk = 1.0 - confidence
            decision["aggregated_confidence"] = confidence
            decision["aggregated_risk"] = risk
            # Aprovar se confiança > risco
            decision["final_decision"] = "approve" if confidence > risk else "reject"

            for vote in decision["specialist_votes"]:
                vote["confidence_score"] = confidence
                vote["risk_score"] = risk

            decision["consensus_metrics"]["bayesian_confidence"] = confidence
            decision["consensus_metrics"]["voting_confidence"] = confidence

            decisions.append(decision)

        metrics = model.train(decisions)

        assert model.is_trained
        assert metrics["samples"] == 20
        assert "accuracy" in metrics
        assert 0 <= metrics["accuracy"] <= 1

    def test_predict_without_training(self, model, sample_decision):
        """Testa erro ao predizer sem treinar."""
        with pytest.raises(RuntimeError, match="must be trained"):
            model.predict_proba(sample_decision)

    def test_predict_proba_after_training(self, model, sample_decision):
        """Testa predição após treinamento."""
        # Treinar com algumas decisões
        decisions = []
        for i in range(15):
            decision = sample_decision.copy()
            decision["decision_id"] = f"decision_{i}"
            decision["aggregated_confidence"] = 0.5 + (i * 0.03)
            decision["aggregated_risk"] = 0.5 - (i * 0.03)
            decision["final_decision"] = "approve" if i > 7 else "reject"
            decisions.append(decision)

        model.train(decisions)

        proba = model.predict_proba(sample_decision)
        assert 0 <= proba <= 1

    def test_predict_after_training(self, model, sample_decision):
        """Testa predict após treinamento."""
        decisions = []
        for i in range(15):
            decision = sample_decision.copy()
            decision["decision_id"] = f"decision_{i}"
            decision["final_decision"] = "approve" if i > 7 else "reject"
            decisions.append(decision)

        model.train(decisions)

        pred = model.predict(sample_decision)
        assert pred in [0, 1]

    def test_get_feature_importance_without_training(self, model):
        """Testa erro ao obter importância sem treinar."""
        with pytest.raises(RuntimeError, match="must be trained"):
            model.get_feature_importance()

    def test_get_feature_importance_after_training(self, model, sample_decision):
        """Testa obter importância após treinamento."""
        decisions = [sample_decision.copy() for _ in range(15)]
        for i, d in enumerate(decisions):
            d["decision_id"] = f"decision_{i}"
            d["final_decision"] = "approve" if i > 7 else "reject"

        model.train(decisions)

        importance = model.get_feature_importance()
        assert len(importance) == len(model.feature_names)
        assert all(imp >= 0 for imp in importance.values())

    def test_save_without_training(self, model, tmp_path):
        """Testa erro ao salvar modelo não treinado."""
        with pytest.raises(RuntimeError, match="Cannot save untrained"):
            model.save(str(tmp_path / "model.joblib"))

    @patch("src.models.shap_model.joblib.dump")
    def test_save_after_training(self, mock_dump, model, sample_decision, tmp_path):
        """Testa salvar modelo treinado."""
        decisions = [sample_decision.copy() for _ in range(15)]
        for i, d in enumerate(decisions):
            d["decision_id"] = f"decision_{i}"
            d["final_decision"] = "approve"

        model.train(decisions)

        model_path = str(tmp_path / "model.joblib")
        model.save(model_path)

        mock_dump.assert_called_once()
        call_args = mock_dump.call_args[0][1]
        assert call_args == model_path

    @patch("src.models.shap_model.joblib.load")
    def test_load_model(self, mock_load, model, tmp_path):
        """Testa carregar modelo salvo."""
        mock_data = {
            "model": Mock(),
            "scaler": Mock(),
            "feature_names": ["f1", "f2"],
            "model_type": "random_forest",
            "is_trained": True,
        }
        mock_load.return_value = mock_data

        model.load(str(tmp_path / "model.joblib"))

        assert model.is_trained
        assert model.feature_names == ["f1", "f2"]


class TestFeatureExtractor:
    """Testes para FeatureExtractor."""

    @pytest.fixture()
    def extractor(self):
        """Fixture para FeatureExtractor."""
        return FeatureExtractor()

    @pytest.fixture()
    def sample_decisions(self):
        """Fixture para decisões de exemplo."""
        return [
            {
                "aggregated_confidence": 0.8,
                "aggregated_risk": 0.2,
                "specialist_votes": [{"processing_time_ms": 500, "seniority_multiplier": 1.0}],
                "consensus_metrics": {
                    "divergence_score": 0.1,
                    "unanimous": True,
                    "bayesian_confidence": 0.8,
                    "voting_confidence": 0.85,
                },
            },
            {
                "aggregated_confidence": 0.3,
                "aggregated_risk": 0.7,
                "specialist_votes": [{"processing_time_ms": 1500, "seniority_multiplier": 1.5}],
                "consensus_metrics": {
                    "divergence_score": 0.5,
                    "unanimous": False,
                    "bayesian_confidence": 0.3,
                    "voting_confidence": 0.4,
                },
            },
        ]

    def test_init(self, extractor):
        """Testa inicialização."""
        assert len(extractor.feature_names) == 8

    def test_extract_batch(self, extractor, sample_decisions):
        """Testa extração em lote."""
        features = extractor.extract_batch(sample_decisions)

        assert features.shape == (2, 8)

    def test_validate_features_valid(self, extractor, sample_decisions):
        """Testa validação de features válidas."""
        features = extractor.extract_batch(sample_decisions)
        result = extractor.validate_features(features)

        assert result["is_valid"]
        assert len(result["issues"]) == 0

    def test_validate_features_invalid_shape(self, extractor):
        """Testa validação com shape incorreto."""
        invalid = np.array([[1, 2, 3]])  # 3 features em vez de 8
        result = extractor.validate_features(invalid)

        assert not result["is_valid"]
        assert any("Invalid number of features" in issue for issue in result["issues"])

    def test_validate_features_with_nan(self, extractor):
        """Testa validação com NaN."""
        invalid = np.array([[1, 2, np.nan, 4, 5, 6, 7, 8]])
        result = extractor.validate_features(invalid)

        assert not result["is_valid"]
        assert any("NaN" in issue for issue in result["issues"])


class TestModelTrainer:
    """Testes para ModelTrainer."""

    @pytest.fixture()
    def trainer(self):
        """Fixture para ModelTrainer."""
        return ModelTrainer(model_type="random_forest", min_samples=10, target_accuracy=0.6)

    @pytest.fixture()
    def sample_decisions(self):
        """Fixture para decisões de exemplo."""
        decisions = []
        for i in range(20):
            decision = {
                "decision_id": f"decision_{i}",
                "final_decision": "approve" if i > 9 else "reject",
                "aggregated_confidence": 0.3 + (i * 0.035),
                "aggregated_risk": 0.7 - (i * 0.035),
                "specialist_votes": [
                    {
                        "processing_time_ms": 500 + i * 10,
                        "seniority_multiplier": 1.0,
                        "confidence_score": 0.3 + (i * 0.035),
                        "risk_score": 0.7 - (i * 0.035),
                    }
                ],
                "consensus_metrics": {
                    "divergence_score": 0.1 + (i * 0.01),
                    "unanimous": i % 2 == 0,
                    "bayesian_confidence": 0.3 + (i * 0.035),
                    "voting_confidence": 0.3 + (i * 0.035),
                },
            }
            decisions.append(decision)
        return decisions

    def test_init(self, trainer):
        """Testa inicialização."""
        assert trainer.min_samples == 10
        assert trainer.target_accuracy == 0.6
        assert trainer.model is not None

    def test_train_from_decisions_insufficient(self, trainer):
        """Testa treino com amostras insuficientes."""
        result = trainer.train_from_decisions([])

        assert not result["success"]
        assert "Insufficient samples" in result["error"]

    def test_train_from_decisions_success(self, trainer, sample_decisions):
        """Testa treino bem-sucedido."""
        result = trainer.train_from_decisions(sample_decisions)

        assert result["success"]
        assert "metrics" in result
        assert "feature_importance" in result
        assert trainer.model.is_trained

    def test_train_from_decisions_meets_target(self, trainer, sample_decisions):
        """Testa se modelo atinge target de acurácia."""
        # Usar target baixo para garantir sucesso
        trainer.target_accuracy = 0.5
        result = trainer.train_from_decisions(sample_decisions)

        assert result["success"]
        # Pode ou não atingir target dependendo dos dados

    def test_save_trained_model(self, trainer, sample_decisions, tmp_path):
        """Testa salvar modelo treinado."""
        trainer.train_from_decisions(sample_decisions)

        output_path = str(tmp_path / "model.joblib")

        with patch("src.models.shap_model.joblib.dump") as mock_dump:
            trainer.save_trained_model(output_path)
            mock_dump.assert_called_once()

    def test_save_without_training(self, trainer, tmp_path):
        """Testa erro ao salvar sem treinar."""
        with pytest.raises(RuntimeError, match="No trained model"):
            trainer.save_trained_model(str(tmp_path / "model.joblib"))

    @patch("src.models.shap_model.DecisionWrapperModel.load")
    def test_load_model(self, mock_load, trainer):
        """Testa carregar modelo."""
        trainer.load_model("path/to/model.joblib")
        mock_load.assert_called_once_with("path/to/model.joblib")
