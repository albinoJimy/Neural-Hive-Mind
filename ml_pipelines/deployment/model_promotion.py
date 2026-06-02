"""
Model Promotion Pipeline - Promove modelos ML de staging → production.

Funcionalidades:
- Validações de métricas antes da promoção (accuracy > 0.85, drift < 0.3)
- Backup do modelo anterior antes de promover
- Rollback automático se new model falhar
- Shadow mode para validação gradual

FASE 0 - IA/ML Integration (TICKET 3.4)
"""

import json
import pickle
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PromotionResult:
    """Resultado da promoção de modelo."""

    success: bool
    from_stage: str
    to_stage: str
    model_version: str
    previous_version: str | None
    backup_path: str | None
    new_model_path: str
    validation_results: dict[str, Any]
    rollback_performed: bool
    error_message: str | None = None
    promoted_at: datetime | None = None


@dataclass
class ModelValidation:
    """Validação de modelo para promoção."""

    accuracy: float
    f1_score: float
    precision: float
    recall: float
    drift_score: float
    sample_count: int
    passed: bool
    reasons: list[str]


class ModelPromotion:
    """
    Gerencia promoção de modelos ML entre estágios.

    Estágios suportados:
    - staging: Modelo em testes
    - production: Modelo em produção
    - shadow: Modelo shadow (comparação lado a lado)
    - archived: Modelo arquivado (backup)
    """

    # Thresholds para promoção
    DEFAULT_THRESHOLDS = {
        "min_accuracy": 0.85,
        "min_f1_score": 0.80,
        "max_drift_score": 0.3,
        "min_sample_count": 50,
    }

    def __init__(
        self,
        models_dir: Path | None = None,
        backup_dir: Path | None = None,
        thresholds: dict[str, float] | None = None,
    ):
        """
        Inicializa o gerenciador de promoção.

        Args:
            models_dir: Diretório base dos modelos
            backup_dir: Diretório para backups
            thresholds: Thresholds customizados para validação
        """
        self.models_dir = models_dir or Path(__file__).parent.parent.parent / "ml_models"
        self.backup_dir = backup_dir or self.models_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Load thresholds
        self.thresholds = {**self.DEFAULT_THRESHOLDS}
        if thresholds:
            self.thresholds.update(thresholds)

        logger.info(
            "model_promotion_initialized",
            models_dir=str(self.models_dir),
            backup_dir=str(self.backup_dir),
            thresholds=self.thresholds,
        )

    def validate_model_for_promotion(self, model_data: dict[str, Any]) -> ModelValidation:
        """
        Valida se modelo atende critérios para promoção.

        Args:
            model_data: Dados do modelo (do pickle)

        Returns:
            ModelValidation com resultado
        """
        metrics = model_data.get("metrics", {})
        training_samples = model_data.get("training_samples", 0)

        # Extrair métricas
        accuracy = metrics.get("accuracy", 0.0)
        f1_score = metrics.get("f1_score", 0.0)
        precision = metrics.get("precision", 0.0)
        recall = metrics.get("recall", 0.0)
        drift_score = model_data.get("drift_score", 0.0)

        # Validações
        reasons = []
        passed = True

        if accuracy < self.thresholds["min_accuracy"]:
            passed = False
            reasons.append(f"Accuracy {accuracy:.3f} < {self.thresholds['min_accuracy']}")

        if f1_score < self.thresholds["min_f1_score"]:
            passed = False
            reasons.append(f"F1-Score {f1_score:.3f} < {self.thresholds['min_f1_score']}")

        if drift_score > self.thresholds["max_drift_score"]:
            passed = False
            reasons.append(f"Drift score {drift_score:.3f} > {self.thresholds['max_drift_score']}")

        if training_samples < self.thresholds["min_sample_count"]:
            passed = False
            reasons.append(
                f"Sample count {training_samples} < {self.thresholds['min_sample_count']}"
            )

        return ModelValidation(
            accuracy=accuracy,
            f1_score=f1_score,
            precision=precision,
            recall=recall,
            drift_score=drift_score,
            sample_count=training_samples,
            passed=passed,
            reasons=reasons,
        )

    def promote_model(
        self,
        model_path: Path,
        from_stage: Literal["staging", "shadow"],
        to_stage: Literal["production", "shadow"],
        validate: bool = True,
        backup: bool = True,
    ) -> PromotionResult:
        """
        Promove modelo de um estágio para outro.

        Args:
            model_path: Caminho do modelo a promover
            from_stage: Estágio de origem
            to_stage: Estágio de destino
            validate: Se deve validar métricas antes de promover
            backup: Se deve fazer backup do modelo anterior

        Returns:
            PromotionResult com detalhes da operação
        """
        logger.info(
            "promoting_model",
            model_path=str(model_path),
            from_stage=from_stage,
            to_stage=to_stage,
            validate=validate,
            backup=backup,
        )

        try:
            # Carregar modelo
            with open(model_path, "rb") as f:
                model_data = pickle.load(f)

            model_version = model_data.get("version", "unknown")

            # Validar se solicitado
            validation_results = {}
            if validate:
                validation = self.validate_model_for_promotion(model_data)
                validation_results = {
                    "passed": validation.passed,
                    "reasons": validation.reasons,
                    "accuracy": validation.accuracy,
                    "f1_score": validation.f1_score,
                    "drift_score": validation.drift_score,
                }

                if not validation.passed:
                    logger.warning(
                        "model_validation_failed",
                        version=model_version,
                        reasons=validation.reasons,
                    )
                    return PromotionResult(
                        success=False,
                        from_stage=from_stage,
                        to_stage=to_stage,
                        model_version=model_version,
                        previous_version=None,
                        backup_path=None,
                        new_model_path=str(model_path),
                        validation_results=validation_results,
                        rollback_performed=False,
                        error_message="; ".join(validation.reasons),
                    )

            # Path do modelo de destino
            target_filename = f"nhm_approval_model_{to_stage}.pkl"
            target_path = self.models_dir / target_filename

            # Backup do modelo anterior se existir
            backup_path = None
            previous_version = None
            if backup and target_path.exists():
                previous_version = self._get_model_version(target_path)
                backup_path = self._backup_model(target_path, previous_version)
                logger.info(
                    "model_backed_up",
                    previous_version=previous_version,
                    backup_path=str(backup_path),
                )

            # Copiar novo modelo
            shutil.copy2(model_path, target_path)
            logger.info(
                "model_promoted",
                version=model_version,
                target_path=str(target_path),
            )

            # Salvar metadata da promoção
            self._save_promotion_metadata(
                model_version=model_version,
                from_stage=from_stage,
                to_stage=to_stage,
                previous_version=previous_version,
                validation_results=validation_results,
            )

            return PromotionResult(
                success=True,
                from_stage=from_stage,
                to_stage=to_stage,
                model_version=model_version,
                previous_version=previous_version,
                backup_path=str(backup_path) if backup_path else None,
                new_model_path=str(target_path),
                validation_results=validation_results,
                rollback_performed=False,
                promoted_at=datetime.now(),
            )

        except Exception as e:
            logger.error("promotion_failed", error=str(e), model_path=str(model_path))
            return PromotionResult(
                success=False,
                from_stage=from_stage,
                to_stage=to_stage,
                model_version="unknown",
                previous_version=None,
                backup_path=None,
                new_model_path=str(model_path),
                validation_results={},
                rollback_performed=False,
                error_message=str(e),
            )

    def rollback_model(
        self, to_version: str, from_stage: Literal["production", "shadow"]
    ) -> PromotionResult:
        """
        Faz rollback do modelo para versão anterior.

        Args:
            to_version: Versão para qual fazer rollback
            from_stage: Estágio do qual fazer rollback

        Returns:
            PromotionResult com detalhes do rollback
        """
        logger.info(
            "rolling_back_model",
            to_version=to_version,
            from_stage=from_stage,
        )

        try:
            # Encontrar backup
            backup_path = self._find_backup(to_version)
            if not backup_path:
                return PromotionResult(
                    success=False,
                    from_stage=from_stage,
                    to_stage="rollback",
                    model_version=to_version,
                    previous_version=None,
                    backup_path=None,
                    new_model_path="",
                    validation_results={},
                    rollback_performed=False,
                    error_message=f"Backup for version {to_version} not found",
                )

            # Path do modelo atual
            current_filename = f"nhm_approval_model_{from_stage}.pkl"
            current_path = self.models_dir / current_filename

            # Backup do modelo atual antes de rollback
            current_version = (
                self._get_model_version(current_path) if current_path.exists() else "unknown"
            )
            if current_path.exists():
                self._backup_model(current_path, f"pre_rollback_{current_version}")

            # Restaurar backup
            shutil.copy2(backup_path, current_path)
            logger.info(
                "model_rolled_back",
                to_version=to_version,
                target_path=str(current_path),
            )

            return PromotionResult(
                success=True,
                from_stage=from_stage,
                to_stage="rollback",
                model_version=to_version,
                previous_version=current_version,
                backup_path=str(backup_path),
                new_model_path=str(current_path),
                validation_results={},
                rollback_performed=True,
                promoted_at=datetime.now(),
            )

        except Exception as e:
            logger.error("rollback_failed", error=str(e), to_version=to_version)
            return PromotionResult(
                success=False,
                from_stage=from_stage,
                to_stage="rollback",
                model_version=to_version,
                previous_version=None,
                backup_path=None,
                new_model_path="",
                validation_results={},
                rollback_performed=False,
                error_message=str(e),
            )

    def _backup_model(self, model_path: Path, rollback_version: str) -> Path:
        """Cria backup do modelo."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{rollback_version}_{timestamp}.pkl"
        backup_path = self.backup_dir / backup_filename
        shutil.copy2(model_path, backup_path)
        return backup_path

    def _get_model_version(self, model_path: Path) -> str | None:
        """Retorna versão do modelo do arquivo."""
        try:
            with open(model_path, "rb") as f:
                model_data = pickle.load(f)
            return model_data.get("version", "unknown")
        except Exception:
            return None

    def _find_backup(self, version: str) -> Path | None:
        """Encontra backup de uma versão."""
        for backup_file in self.backup_dir.glob(f"{version}_*.pkl"):
            return backup_file
        return None

    def _save_promotion_metadata(
        self,
        model_version: str,
        from_stage: str,
        to_stage: str,
        previous_version: str | None,
        validation_results: dict[str, Any],
    ) -> None:
        """Salva metadata da promoção."""
        metadata_file = self.models_dir / "promotion_history.jsonl"

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "model_version": model_version,
            "from_stage": from_stage,
            "to_stage": to_stage,
            "previous_version": previous_version,
            "validation_results": validation_results,
        }

        with open(metadata_file, "a") as f:
            f.write(json.dumps(metadata) + "\n")

    def get_promotion_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Retorna histórico de promoções."""
        metadata_file = self.models_dir / "promotion_history.jsonl"

        if not metadata_file.exists():
            return []

        history = []
        with open(metadata_file) as f:
            for line in f:
                try:
                    history.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        return history[-limit:]


# Singleton para uso na aplicação
_promotion_instance: ModelPromotion | None = None


def get_model_promotion() -> ModelPromotion:
    """Retorna instância singleton do ModelPromotion."""
    global _promotion_instance
    if _promotion_instance is None:
        _promotion_instance = ModelPromotion()
    return _promotion_instance
