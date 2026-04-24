#!/usr/bin/env python3
"""
Testes E2E para Pipeline de Promoção de Modelos

Testa o fluxo completo:
1. Treinar shadow model
2. Validar performance
3. Promover para production
4. Verificar capability de rollback
"""

import json
import pickle
from datetime import datetime
from pathlib import Path

import pytest
from sklearn.datasets import make_classification
from sklearn.ensemble import RandomForestClassifier

from ml_pipelines.deploy.promote_model import (
    ModelMetrics,
    ModelValidationError,
    Stage,
    backup_current_model,
    get_current_model_info,
    list_backups,
    promote_model,
    rollback_model,
    update_model_version,
    validate_model,
)


class TestModelPromotionE2E:
    """
    Testes E2E para pipeline completo de promoção de modelos.

    Fluxo completo:
    1. Criar e treinar shadow model
    2. Validar performance metrics
    3. Promover para production
    4. Verificar rollback capability
    """

    @pytest.fixture()
    def temp_dirs(self, tmp_path: Path):
        """Cria diretórios temporários para testes."""
        models_dir = tmp_path / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        staging_dir = tmp_path / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        return {
            "models_dir": models_dir,
            "backup_dir": backup_dir,
            "staging_dir": staging_dir,
        }

    @pytest.fixture()
    def valid_model(self, temp_dirs: dict[str, Path], tmp_path: Path) -> Path:
        """
        Cria um modelo válido em staging para teste.

        Simula um modelo treinado com métricas aceitáveis.
        """
        staging_dir = temp_dirs.get("staging_dir", tmp_path / "staging")
        staging_dir.mkdir(parents=True, exist_ok=True)

        model_path = staging_dir / "approval_v8.pkl"

        # Criar modelo dummy
        X, y = make_classification(
            n_samples=100,
            n_features=30,
            n_informative=10,
            n_classes=3,
            random_state=42,
        )
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        # Criar estrutura de dados do modelo NHM
        model_data = {
            "model": model,
            "version": "v8",
            "trained_at": datetime.now().isoformat(),
            "features": [f"feature_{i}" for i in range(30)],
            "metrics": {
                "accuracy": 0.90,
                "f1_score": 0.88,
                "precision": 0.89,
                "recall": 0.87,
                "drift_score": 0.15,
                "training_samples": 100,
            },
            "training_samples": 100,
        }

        with open(model_path, "wb") as f:
            pickle.dump(model_data, f)

        return model_path

    @pytest.fixture()
    def invalid_model(self, temp_dirs: dict[str, Path], tmp_path: Path) -> Path:
        """
        Cria um modelo inválido com métricas abaixo do threshold.
        """
        staging_dir = temp_dirs.get("staging_dir", tmp_path / "staging")
        staging_dir.mkdir(parents=True, exist_ok=True)

        model_path = staging_dir / "approval_invalid.pkl"

        X, y = make_classification(
            n_samples=100,
            n_features=30,
            n_informative=5,
            n_classes=3,
            random_state=42,
        )
        model = RandomForestClassifier(n_estimators=5, random_state=42)
        model.fit(X, y)

        model_data = {
            "model": model,
            "version": "v9_invalid",
            "trained_at": datetime.now().isoformat(),
            "features": [f"feature_{i}" for i in range(30)],
            "metrics": {
                "accuracy": 0.70,  # Abaixo do threshold de 0.85
                "f1_score": 0.65,
                "precision": 0.68,
                "recall": 0.62,
                "drift_score": 0.50,  # Acima do threshold de 0.3
                "training_samples": 100,
            },
            "training_samples": 100,
        }

        with open(model_path, "wb") as f:
            pickle.dump(model_data, f)

        return model_path

    @pytest.fixture()
    def production_model(self, temp_dirs: dict[str, Path]) -> Path:
        """Cria um modelo em production para teste de rollback."""
        models_dir = temp_dirs["models_dir"]
        model_path = models_dir / "nhm_approval_model.pkl"

        X, y = make_classification(
            n_samples=100,
            n_features=30,
            n_informative=10,
            n_classes=3,
            random_state=42,
        )
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)

        model_data = {
            "model": model,
            "version": "v7",
            "trained_at": "2024-03-01T10:00:00",
            "features": [f"feature_{i}" for i in range(30)],
            "metrics": {
                "accuracy": 0.87,
                "f1_score": 0.85,
                "precision": 0.86,
                "recall": 0.84,
                "drift_score": 0.20,
                "training_samples": 75,
            },
            "training_samples": 75,
        }

        with open(model_path, "wb") as f:
            pickle.dump(model_data, f)

        # Criar version file
        version_file = models_dir / "model_version.json"
        with open(version_file, "w") as f:
            json.dump({
                "current_version": "v7",
                "updated_at": "2024-03-01T10:00:00",
            }, f)

        return model_path

    def test_e2e_full_promotion_flow(
        self, temp_dirs: dict[str, Path], valid_model: Path, production_model: Path
    ):
        """
        Testa fluxo E2E completo: treinar shadow → validar → promover → rollback.

        Steps:
        1. Shadow model já treinado (valid_model fixture)
        2. Validar performance do shadow model
        3. Promover shadow → production
        4. Verificar modelo atualizado
        5. Fazer rollback
        6. Verificar versão anterior restaurada
        """
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]
        staging_dir = temp_dirs["staging_dir"]

        # STEP 1: Validar shadow model
        metrics = validate_model(
            model_path=valid_model,
            min_accuracy=0.85,
            max_drift_score=0.3,
            min_f1_score=0.80,
        )

        assert metrics.accuracy == 0.90
        assert metrics.f1_score == 0.88
        assert metrics.drift_score == 0.15
        assert metrics.model_version == "v8"

        # STEP 2: Promover para production
        result = promote_model(
            model_path=valid_model,
            from_stage=Stage.STAGING,
            to_stage=Stage.PRODUCTION,
            models_dir=models_dir,
            backup_dir=backup_dir,
            min_accuracy=0.85,
            max_drift_score=0.3,
            min_f1_score=0.80,
        )

        assert result["status"] == "success"
        assert result["from_stage"] == Stage.STAGING
        assert result["to_stage"] == Stage.PRODUCTION
        assert "backup_path" in result
        assert "metrics" in result
        assert result["metrics"]["model_version"] == "v8"

        # STEP 3: Verificar modelo atualizado
        current_info = get_current_model_info(models_dir=models_dir)
        assert current_info["model_version"] == "v8"
        assert current_info["metrics"]["accuracy"] == 0.90

        # STEP 4: Verificar backup criado
        backup_path = Path(result["backup_path"])
        assert backup_path.exists()

        # STEP 5: Fazer rollback
        rollback_result = rollback_model(
            backup_path=backup_path,
            models_dir=models_dir,
            backup_dir=backup_dir,
        )

        assert rollback_result["status"] == "success"
        assert rollback_result["backup_version"] == "v7"

        # STEP 6: Verificar versão anterior restaurada
        current_info = get_current_model_info(models_dir=models_dir)
        assert current_info["model_version"] == "v7"

    def test_promotion_rejects_invalid_model(
        self, temp_dirs: dict[str, Path], invalid_model: Path, production_model: Path
    ):
        """
        Testa que promoção rejeita modelo com métricas abaixo do threshold.
        """
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]

        with pytest.raises(ModelValidationError) as exc_info:
            promote_model(
                model_path=invalid_model,
                from_stage=Stage.STAGING,
                to_stage=Stage.PRODUCTION,
                models_dir=models_dir,
                backup_dir=backup_dir,
                min_accuracy=0.85,
                max_drift_score=0.3,
                min_f1_score=0.80,
            )

        assert "acurácia" in str(exc_info.value).lower() or "drift" in str(exc_info.value).lower()

        # Verificar que modelo original não foi modificado
        current_info = get_current_model_info(models_dir=models_dir)
        assert current_info["model_version"] == "v7"

    def test_promotion_creates_backup_before_promoting(
        self, temp_dirs: dict[str, Path], valid_model: Path, production_model: Path
    ):
        """
        Testa que backup é criado antes de promover modelo.
        """
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]

        promote_model(
            model_path=valid_model,
            from_stage=Stage.STAGING,
            to_stage=Stage.PRODUCTION,
            models_dir=models_dir,
            backup_dir=backup_dir,
        )

        # Listar backups
        backups = list_backups(backup_dir=backup_dir)
        assert len(backups) >= 1

        # Verificar que backup contém versão anterior
        assert backups[0]["version"] == "v7"

    def test_rollback_to_specific_backup(
        self, temp_dirs: dict[str, Path], valid_model: Path, production_model: Path
    ):
        """
        Testa rollback para backup específico.
        """
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]

        # Primeira promoção
        promote_model(
            model_path=valid_model,
            from_stage=Stage.STAGING,
            to_stage=Stage.PRODUCTION,
            models_dir=models_dir,
            backup_dir=backup_dir,
        )

        assert get_current_model_info(models_dir)["model_version"] == "v8"

        # Listar backups
        backups = list_backups(backup_dir=backup_dir)
        original_backup = Path(backups[0]["path"])

        # Rollback para backup específico
        rollback_result = rollback_model(
            backup_path=original_backup,
            models_dir=models_dir,
            backup_dir=backup_dir,
        )

        assert rollback_result["status"] == "success"
        assert rollback_result["backup_version"] == "v7"

    def test_dry_run_promotion(
        self, temp_dirs: dict[str, Path], valid_model: Path, production_model: Path
    ):
        """
        Testa modo dry-run (simulação sem aplicar mudanças).
        """
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]

        result = promote_model(
            model_path=valid_model,
            from_stage=Stage.STAGING,
            to_stage=Stage.PRODUCTION,
            models_dir=models_dir,
            backup_dir=backup_dir,
            dry_run=True,
        )

        assert result["status"] == "dry_run_success"
        assert result["dry_run"] is True

        # Verificar que modelo não foi modificado
        current_info = get_current_model_info(models_dir=models_dir)
        assert current_info["model_version"] == "v7"

        # Verificar que nenhum backup foi criado
        backups = list_backups(backup_dir=backup_dir)
        assert len(backups) == 0

    def test_list_backups_sorted_by_date(
        self, temp_dirs: dict[str, Path], valid_model: Path, production_model: Path
    ):
        """
        Testa que backups são listados em ordem decrescente de data.
        """
        import time
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]

        # Criar múltiplas promoções para gerar múltiplos backups
        for i in range(3):
            # Criar modelo com versão diferente
            model_data = None
            with open(valid_model, "rb") as f:
                model_data = pickle.load(f)
            model_data["version"] = f"v{i+8}"

            temp_model = temp_dirs["staging_dir"] / f"model_v{i+8}.pkl"
            with open(temp_model, "wb") as f:
                pickle.dump(model_data, f)

            promote_model(
                model_path=temp_model,
                models_dir=models_dir,
                backup_dir=backup_dir,
            )

            # Pequeno delay para garantir timestamps únicos
            time.sleep(0.01)

        backups = list_backups(backup_dir=backup_dir)

        assert len(backups) >= 3

        # Verificar ordem decrescente de data (mais recente primeiro)
        dates = [b["created_at"] for b in backups]
        assert dates == sorted(dates, reverse=True)

    def test_update_model_version(
        self, temp_dirs: dict[str, Path]
    ):
        """Testa atualização de versão do modelo."""
        models_dir = temp_dirs["models_dir"]

        # Primeira atualização
        info_v1 = update_model_version("v8", models_dir=models_dir)
        assert info_v1["current_version"] == "v8"
        assert info_v1["previous_version"] == "unknown"
        assert len(info_v1["promotion_history"]) == 1

        # Segunda atualização
        info_v2 = update_model_version("v9", models_dir=models_dir)
        assert info_v2["current_version"] == "v9"
        assert info_v2["previous_version"] == "v8"
        assert len(info_v2["promotion_history"]) == 2

        # Verificar histórico
        assert info_v2["promotion_history"][0]["version"] == "v8"
        assert info_v2["promotion_history"][1]["version"] == "v9"

    def test_validate_model_with_missing_file(
        self, temp_dirs: dict[str, Path]
    ):
        """Testa validação com arquivo inexistente."""
        with pytest.raises(ModelValidationError) as exc_info:
            validate_model(
                model_path=temp_dirs["staging_dir"] / "nonexistent.pkl",
            )

        assert "não encontrado" in str(exc_info.value).lower()

    def test_validate_model_with_corrupted_file(
        self, temp_dirs: dict[str, Path]
    ):
        """Testa validação com arquivo corrompido."""
        corrupted_path = temp_dirs["staging_dir"] / "corrupted.pkl"

        with open(corrupted_path, "wb") as f:
            f.write(b"not a valid pickle file")

        with pytest.raises(ModelValidationError) as exc_info:
            validate_model(model_path=corrupted_path)

        assert "erro ao carregar" in str(exc_info.value).lower()

    def test_get_current_model_info_when_no_model(
        self, temp_dirs: dict[str, Path]
    ):
        """Testa get_current_model_info quando não há modelo."""
        models_dir = temp_dirs["models_dir"]

        info = get_current_model_info(models_dir=models_dir)

        assert "error" in info
        assert info["error"] == "Model file not found"

    def test_backup_when_no_current_model(
        self, temp_dirs: dict[str, Path]
    ):
        """Testa backup quando não há modelo atual."""
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]

        backup_path = backup_current_model(
            models_dir=models_dir,
            backup_dir=backup_dir,
        )

        # Quando não há modelo, backup não deve ser criado
        assert "no_backup_needed" in str(backup_path)

    def test_promotion_validates_custom_thresholds(
        self, temp_dirs: dict[str, Path], valid_model: Path
    ):
        """
        Testa que promoção usa thresholds customizados.
        """
        models_dir = temp_dirs["models_dir"]
        backup_dir = temp_dirs["backup_dir"]

        # Criar modelo com métricas intermediárias
        with open(valid_model, "rb") as f:
            model_data = pickle.load(f)

        model_data["metrics"]["accuracy"] = 0.83  # Entre default e custom

        temp_model = temp_dirs["staging_dir"] / "model_custom.pkl"
        with open(temp_model, "wb") as f:
            pickle.dump(model_data, f)

        # Com threshold default (0.85) deve falhar
        with pytest.raises(ModelValidationError):
            validate_model(
                model_path=temp_model,
                min_accuracy=0.85,
            )

        # Com threshold customizado (0.80) deve passar
        metrics = validate_model(
            model_path=temp_model,
            min_accuracy=0.80,
        )
        assert metrics.accuracy == 0.83

    def test_model_metrics_validation(
        self, temp_dirs: dict[str, Path]
    ):
        """Testa classe ModelMetrics."""
        # Métricas válidas
        metrics = ModelMetrics(
            accuracy=0.90,
            f1_score=0.88,
            drift_score=0.15,
        )

        assert metrics.validate() is True

        # Acurácia abaixo do threshold
        low_accuracy = ModelMetrics(
            accuracy=0.70,
            f1_score=0.88,
            drift_score=0.15,
        )

        with pytest.raises(ModelValidationError) as exc_info:
            low_accuracy.validate(min_accuracy=0.85)

        assert "acurácia" in str(exc_info.value).lower()

        # Drift acima do threshold
        high_drift = ModelMetrics(
            accuracy=0.90,
            f1_score=0.88,
            drift_score=0.50,
        )

        with pytest.raises(ModelValidationError) as exc_info:
            high_drift.validate(max_drift_score=0.3)

        assert "drift" in str(exc_info.value).lower()

    def test_model_metrics_to_dict(self):
        """Testa conversão de ModelMetrics para dicionário."""
        metrics = ModelMetrics(
            accuracy=0.90,
            f1_score=0.88,
            precision=0.89,
            recall=0.87,
            drift_score=0.15,
            training_samples=100,
            model_version="v8",
        )

        data = metrics.to_dict()

        assert data["accuracy"] == 0.90
        assert data["f1_score"] == 0.88
        assert data["precision"] == 0.89
        assert data["recall"] == 0.87
        assert data["drift_score"] == 0.15
        assert data["training_samples"] == 100
        assert data["model_version"] == "v8"

    def test_model_metrics_from_dict(self):
        """Testa criação de ModelMetrics a partir de dicionário."""
        data = {
            "accuracy": 0.90,
            "f1_score": 0.88,
            "precision": 0.89,
            "recall": 0.87,
            "drift_score": 0.15,
            "training_samples": 100,
            "model_version": "v8",
        }

        metrics = ModelMetrics.from_dict(data)

        assert metrics.accuracy == 0.90
        assert metrics.f1_score == 0.88
        assert metrics.precision == 0.89
        assert metrics.recall == 0.87
        assert metrics.drift_score == 0.15
        assert metrics.training_samples == 100
        assert metrics.model_version == "v8"

        # Valores default quando não especificados
        partial_data = {"accuracy": 0.80}
        partial_metrics = ModelMetrics.from_dict(partial_data)

        assert partial_metrics.accuracy == 0.80
        assert partial_metrics.f1_score == 0.0
        assert partial_metrics.model_version == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
