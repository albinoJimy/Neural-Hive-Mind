"""
Testes unitários para Model Promotion Pipeline.

Testa:
- Validação de modelo antes da promoção
- Promoção entre estágios (staging → production)
- Backup e rollback de modelos
- Histórico de promoções

FASE 0 - IA/ML Integration (TICKET 3.4)
"""

import pickle
from pathlib import Path

import pytest
from ml_pipelines.deployment.model_promotion import (
    ModelPromotion,
    get_model_promotion,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def temp_models_dir(tmp_path):
    """Diretório temporário para modelos."""
    models_dir = tmp_path / "ml_models"
    models_dir.mkdir()
    backup_dir = models_dir / "backups"
    backup_dir.mkdir()
    return models_dir


@pytest.fixture()
def sample_model_data():
    """Dados de modelo de exemplo."""
    # Criar um modelo pickle-able simples
    import sklearn.linear_model
    simple_model = sklearn.linear_model.LogisticRegression()
    simple_model.fit([[0], [1]], [0, 1])  # Treinar minimalmente

    return {
        "version": "v8",
        "model": simple_model,
        "trained_at": "2026-04-24T10:00:00Z",
        "training_samples": 100,
        "metrics": {
            "accuracy": 0.90,
            "f1_score": 0.88,
            "precision": 0.85,
            "recall": 0.91,
        },
        "drift_score": 0.1,
        "features": ["feature1", "feature2"],
    }


@pytest.fixture()
def good_model_file(temp_models_dir, sample_model_data):
    """Arquivo de modelo bom (passa validação)."""
    model_path = temp_models_dir / "nhm_approval_model_staging.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(sample_model_data, f)
    return model_path


@pytest.fixture()
def bad_model_file(temp_models_dir):
    """Arquivo de modelo ruim (falha validação)."""
    import sklearn.linear_model
    simple_model = sklearn.linear_model.LogisticRegression()
    simple_model.fit([[0], [1]], [0, 1])

    bad_data = {
        "version": "v9",
        "model": simple_model,
        "trained_at": "2026-04-24T10:00:00Z",
        "training_samples": 20,  # Abaixo do mínimo
        "metrics": {
            "accuracy": 0.70,  # Abaixo do threshold
            "f1_score": 0.65,  # Abaixo do threshold
            "precision": 0.60,
            "recall": 0.70,
        },
        "drift_score": 0.5,  # Acima do threshold
        "features": ["feature1", "feature2"],
    }
    model_path = temp_models_dir / "bad_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(bad_data, f)
    return model_path


@pytest.fixture()
def current_production_model(temp_models_dir):
    """Modelo de produção atual."""
    import sklearn.linear_model
    simple_model = sklearn.linear_model.LogisticRegression()
    simple_model.fit([[0], [1]], [0, 1])

    data = {
        "version": "v7",
        "model": simple_model,
        "trained_at": "2026-04-01T10:00:00Z",
        "training_samples": 75,
        "metrics": {
            "accuracy": 0.85,
            "f1_score": 0.82,
            "precision": 0.80,
            "recall": 0.85,
        },
        "drift_score": 0.2,
        "features": ["feature1", "feature2"],
    }
    model_path = temp_models_dir / "nhm_approval_model_production.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(data, f)
    return model_path


@pytest.fixture()
def model_promotion(temp_models_dir):
    """Instância de ModelPromotion para testes."""
    return ModelPromotion(models_dir=temp_models_dir)


# =============================================================================
# Testes de Validação
# =============================================================================


class TestModelValidation:
    """Testa validação de modelos para promoção."""

    def test_validate_good_model(self, model_promotion, sample_model_data):
        """Modelo bom deve passar validação."""
        validation = model_promotion.validate_model_for_promotion(sample_model_data)

        assert validation.passed is True
        assert len(validation.reasons) == 0
        assert validation.accuracy == 0.90
        assert validation.f1_score == 0.88
        assert validation.drift_score == 0.1

    def test_validate_bad_model_accuracy(self, model_promotion):
        """Modelo com accuracy baixo deve falhar."""
        bad_data = {
            "metrics": {"accuracy": 0.70, "f1_score": 0.90, "precision": 0.85, "recall": 0.90},
            "training_samples": 100,
            "drift_score": 0.1,
        }
        validation = model_promotion.validate_model_for_promotion(bad_data)

        assert validation.passed is False
        assert any("accuracy" in r.lower() for r in validation.reasons)

    def test_validate_bad_model_f1_score(self, model_promotion):
        """Modelo com F1 baixo deve falhar."""
        bad_data = {
            "metrics": {"accuracy": 0.90, "f1_score": 0.70, "precision": 0.85, "recall": 0.90},
            "training_samples": 100,
            "drift_score": 0.1,
        }
        validation = model_promotion.validate_model_for_promotion(bad_data)

        assert validation.passed is False
        assert any("f1" in r.lower() for r in validation.reasons)

    def test_validate_bad_model_drift(self, model_promotion):
        """Modelo com drift alto deve falhar."""
        bad_data = {
            "metrics": {"accuracy": 0.90, "f1_score": 0.90, "precision": 0.85, "recall": 0.90},
            "training_samples": 100,
            "drift_score": 0.5,
        }
        validation = model_promotion.validate_model_for_promotion(bad_data)

        assert validation.passed is False
        assert any("drift" in r.lower() for r in validation.reasons)

    def test_validate_bad_model_sample_count(self, model_promotion):
        """Modelo com poucas amostras deve falhar."""
        bad_data = {
            "metrics": {"accuracy": 0.90, "f1_score": 0.90, "precision": 0.85, "recall": 0.90},
            "training_samples": 20,  # Abaixo do mínimo
            "drift_score": 0.1,
        }
        validation = model_promotion.validate_model_for_promotion(bad_data)

        assert validation.passed is False
        assert any("sample" in r.lower() for r in validation.reasons)

    def test_validate_multiple_failures(self, model_promotion):
        """Modelo com múltiplas falhas deve listar todas."""
        bad_data = {
            "metrics": {"accuracy": 0.70, "f1_score": 0.65, "precision": 0.60, "recall": 0.70},
            "training_samples": 20,
            "drift_score": 0.5,
        }
        validation = model_promotion.validate_model_for_promotion(bad_data)

        assert validation.passed is False
        assert len(validation.reasons) >= 3  # Accuracy, F1, drift, sample count


# =============================================================================
# Testes de Promoção
# =============================================================================


class TestModelPromotion:
    """Testa promoção de modelos entre estágios."""

    def test_promote_staging_to_production_success(
        self, model_promotion, good_model_file, current_production_model
    ):
        """Promoção bem-sucedida de staging para production."""
        result = model_promotion.promote_model(
            model_path=good_model_file,
            from_stage="staging",
            to_stage="production",
            validate=True,
            backup=True,
        )

        assert result.success is True
        assert result.model_version == "v8"
        assert result.previous_version == "v7"
        assert result.rollback_performed is False
        assert result.backup_path is not None
        assert result.promoted_at is not None

    def test_promote_without_validation(self, model_promotion, good_model_file):
        """Promoção sem validação deve sempre sucesso."""
        result = model_promotion.promote_model(
            model_path=good_model_file,
            from_stage="staging",
            to_stage="production",
            validate=False,
            backup=False,
        )

        assert result.success is True
        assert result.validation_results == {}

    def test_promote_with_validation_failure(self, model_promotion, bad_model_file):
        """Promoção com validação que falha."""
        result = model_promotion.promote_model(
            model_path=bad_model_file,
            from_stage="staging",
            to_stage="production",
            validate=True,
            backup=True,
        )

        assert result.success is False
        assert result.validation_results["passed"] is False
        assert len(result.validation_results["reasons"]) > 0
        assert result.error_message is not None

    def test_promote_creates_backup(self, model_promotion, good_model_file, current_production_model):
        """Promoção deve criar backup do modelo anterior."""
        result = model_promotion.promote_model(
            model_path=good_model_file,
            from_stage="staging",
            to_stage="production",
            validate=True,
            backup=True,
        )

        assert result.success is True
        backup_path = Path(result.backup_path)
        assert backup_path.exists()
        assert "v7" in backup_path.name

    def test_promote_without_backup(self, model_promotion, good_model_file):
        """Promoção sem backup não deve criar arquivo de backup."""
        result = model_promotion.promote_model(
            model_path=good_model_file,
            from_stage="staging",
            to_stage="production",
            validate=True,
            backup=False,
        )

        assert result.success is True
        assert result.backup_path is None


# =============================================================================
# Testes de Rollback
# =============================================================================


class TestModelRollback:
    """Testa rollback de modelos."""

    def test_rollback_to_previous_version(
        self, model_promotion, good_model_file, current_production_model
    ):
        """Rollback para versão anterior."""
        # Primeiro promover
        promotion_result = model_promotion.promote_model(
            model_path=good_model_file,
            from_stage="staging",
            to_stage="production",
            validate=True,
            backup=True,
        )
        assert promotion_result.success is True

        # Depois fazer rollback
        rollback_result = model_promotion.rollback_model(
            to_version="v7",
            from_stage="production",
        )

        assert rollback_result.success is True
        assert rollback_result.rollback_performed is True
        assert rollback_result.model_version == "v7"

    def test_rollback_nonexistent_version(self, model_promotion):
        """Rollback para versão inexistente deve falhar."""
        result = model_promotion.rollback_model(to_version="v999", from_stage="production")

        assert result.success is False
        assert "not found" in result.error_message.lower()

    def test_rollback_creates_backup_of_current(self, model_promotion, good_model_file, current_production_model):
        """Rollback deve fazer backup do modelo atual antes de reverter."""
        # Promover primeiro
        model_promotion.promote_model(
            model_path=good_model_file,
            from_stage="staging",
            to_stage="production",
            validate=True,
            backup=True,
        )

        # Rollback
        rollback_result = model_promotion.rollback_model(
            to_version="v7",
            from_stage="production",
        )

        assert rollback_result.success is True
        # Verificar que v8 foi feito backup
        backup_files = list((model_promotion.backup_dir).glob("pre_rollback_v8*"))
        assert len(backup_files) > 0


# =============================================================================
# Testes de Histórico
# =============================================================================


class TestPromotionHistory:
    """Testa histórico de promoções."""

    def test_promotion_saves_metadata(self, model_promotion, good_model_file, current_production_model):
        """Promoção deve salvar metadata."""
        model_promotion.promote_model(
            model_path=good_model_file,
            from_stage="staging",
            to_stage="production",
            validate=True,
            backup=True,
        )

        history = model_promotion.get_promotion_history()
        assert len(history) >= 1

        last_promotion = history[-1]
        assert last_promotion["model_version"] == "v8"
        assert last_promotion["from_stage"] == "staging"
        assert last_promotion["to_stage"] == "production"
        assert last_promotion["previous_version"] == "v7"

    def test_promotion_history_limit(self, model_promotion, good_model_file, current_production_model):
        """Limite de histórico deve funcionar."""
        # Criar múltiplas promoções
        for _ in range(5):
            model_promotion.promote_model(
                model_path=good_model_file,
                from_stage="staging",
                to_stage="production",
                validate=False,  # Skip validação para速度
                backup=True,
            )

        history = model_promotion.get_promotion_history(limit=3)
        assert len(history) == 3


# =============================================================================
# Testes de Singleton
# =============================================================================


class TestSingleton:
    """Testa padrão singleton."""

    def test_get_model_promotion_singleton(self):
        """get_model_promotion deve retornar singleton."""
        promotion1 = get_model_promotion()
        promotion2 = get_model_promotion()
        assert promotion1 is promotion2
