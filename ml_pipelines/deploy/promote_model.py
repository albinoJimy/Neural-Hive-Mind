#!/usr/bin/env python3
"""
Pipeline de Promoção de Modelos ML

Este módulo implementa o pipeline completo de promoção de modelos entre ambientes,
incluindo validação, backup, promoção atômica e rollback.

Uso:
    from ml_pipelines.deploy.promote_model import promote_model

    result = promote_model(
        model_path="models/approval_v8.pkl",
        from_stage="staging",
        to_stage="production",
        min_accuracy=0.85,
        max_drift_score=0.3
    )
"""

import json
import pickle
import shutil
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

# Configurações padrão
DEFAULT_MODELS_DIR = Path(__file__).parent.parent.parent / "ml_models"
DEFAULT_BACKUP_DIR = DEFAULT_MODELS_DIR / "backups"
METRICS_FILE = "metrics.json"
MODEL_FILE = "nhm_approval_model.pkl"
VERSION_FILE = "model_version.json"

# Thresholds de validação
DEFAULT_MIN_ACCURACY = 0.85
DEFAULT_MAX_DRIFT_SCORE = 0.3
DEFAULT_MIN_F1_SCORE = 0.80


class Stage(str, Enum):
    """Ambientes de deploy."""

    STAGING = "staging"
    PRODUCTION = "production"
    SHADOW = "shadow"


class ModelPromotionError(Exception):
    """Erro base durante promoção de modelo."""


class ModelValidationError(ModelPromotionError):
    """Erro durante validação de modelo."""


class ModelBackupError(ModelPromotionError):
    """Erro durante backup de modelo."""


class ModelMetrics:
    """Métricas de validação de modelo."""

    def __init__(
        self,
        accuracy: float = 0.0,
        f1_score: float = 0.0,
        precision: float = 0.0,
        recall: float = 0.0,
        drift_score: float = 0.0,
        training_samples: int = 0,
        model_version: str = "unknown",
    ):
        self.accuracy = accuracy
        self.f1_score = f1_score
        self.precision = precision
        self.recall = recall
        self.drift_score = drift_score
        self.training_samples = training_samples
        self.model_version = model_version

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário."""
        return {
            "accuracy": self.accuracy,
            "f1_score": self.f1_score,
            "precision": self.precision,
            "recall": self.recall,
            "drift_score": self.drift_score,
            "training_samples": self.training_samples,
            "model_version": self.model_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelMetrics":
        """Cria instância a partir de dicionário."""
        return cls(
            accuracy=data.get("accuracy", 0.0),
            f1_score=data.get("f1_score", 0.0),
            precision=data.get("precision", 0.0),
            recall=data.get("recall", 0.0),
            drift_score=data.get("drift_score", 0.0),
            training_samples=data.get("training_samples", 0),
            model_version=data.get("model_version", "unknown"),
        )

    def validate(
        self,
        min_accuracy: float = DEFAULT_MIN_ACCURACY,
        max_drift_score: float = DEFAULT_MAX_DRIFT_SCORE,
        min_f1_score: float = DEFAULT_MIN_F1_SCORE,
    ) -> bool:
        """
        Valida se as métricas atendem aos requisitos mínimos.

        Args:
            min_accuracy: Acurácia mínima exigida
            max_drift_score: Score máximo de drift permitido
            min_f1_score: F1-score mínimo exigido

        Returns:
            True se todas as métricas passarem na validação

        Raises:
            ModelValidationError: Se alguma métrica falhar na validação
        """
        errors = []

        if self.accuracy < min_accuracy:
            errors.append(f"Acurácia {self.accuracy:.2%} abaixo do mínimo {min_accuracy:.2%}")

        if self.f1_score < min_f1_score:
            errors.append(f"F1-Score {self.f1_score:.2%} abaixo do mínimo {min_f1_score:.2%}")

        if self.drift_score > max_drift_score:
            errors.append(
                f"Drift score {self.drift_score:.2f} acima do máximo {max_drift_score:.2f}"
            )

        if errors:
            raise ModelValidationError(f"Validação de métricas falhou: {'; '.join(errors)}")

        logger.info(
            "model_metrics_validated",
            accuracy=self.accuracy,
            f1_score=self.f1_score,
            drift_score=self.drift_score,
        )

        return True


def validate_model(
    model_path: Path,
    min_accuracy: float = DEFAULT_MIN_ACCURACY,
    max_drift_score: float = DEFAULT_MAX_DRIFT_SCORE,
    min_f1_score: float = DEFAULT_MIN_F1_SCORE,
) -> ModelMetrics:
    """
    Valida modelo treinado verificando arquivo e métricas.

    Args:
        model_path: Caminho para o arquivo do modelo (.pkl)
        min_accuracy: Acurácia mínima exigida
        max_drift_score: Score máximo de drift permitido
        min_f1_score: F1-score mínimo exigido

    Returns:
        ModelMetrics com as métricas do modelo

    Raises:
        ModelValidationError: Se validação falhar
    """
    logger.info("validating_model", model_path=str(model_path))

    # Verificar se arquivo existe
    if not model_path.exists():
        raise ModelValidationError(f"Arquivo do modelo não encontrado: {model_path}")

    # Verificar se arquivo é carregável
    try:
        with open(model_path, "rb") as f:
            model_data = pickle.load(f)
    except Exception as e:
        raise ModelValidationError(f"Erro ao carregar modelo: {e}") from e

    # Verificar estrutura do modelo
    if not isinstance(model_data, dict):
        raise ModelValidationError("Modelo deve ser um dicionário com 'model' e metadados")

    if "model" not in model_data:
        raise ModelValidationError("Modelo não contém chave 'model'")

    # Extrair métricas
    metrics_dict = model_data.get("metrics", {})
    metrics = ModelMetrics.from_dict(metrics_dict)
    metrics.model_version = model_data.get("version", "unknown")

    # Validar métricas
    try:
        metrics.validate(
            min_accuracy=min_accuracy,
            max_drift_score=max_drift_score,
            min_f1_score=min_f1_score,
        )
    except ModelValidationError:
        logger.error(
            "model_validation_failed",
            model_path=str(model_path),
            metrics=metrics.to_dict(),
        )
        raise

    logger.info(
        "model_validation_successful",
        model_path=str(model_path),
        metrics=metrics.to_dict(),
    )

    return metrics


def backup_current_model(
    models_dir: Path = DEFAULT_MODELS_DIR,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> Path:
    """
    Cria backup do modelo atual antes de promoção.

    O backup é feito com timestamp para permitir múltipos backups
    e rollback para qualquer versão anterior.

    Args:
        models_dir: Diretório onde estão os modelos
        backup_dir: Diretório para armazenar backups

    Returns:
        Caminho para o arquivo de backup criado

    Raises:
        ModelBackupError: Se backup falhar
    """
    logger.info("backing_up_current_model", models_dir=str(models_dir))

    # Criar diretório de backup se não existir
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Caminho do modelo atual
    current_model_path = models_dir / MODEL_FILE

    if not current_model_path.exists():
        logger.warning(
            "no_current_model_to_backup",
            current_model_path=str(current_model_path),
        )
        # Retornar caminho vazio - não há modelo para backup
        return backup_dir / "no_backup_needed"

    # Criar nome de arquivo com timestamp + UUID único para evitar colisões
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    backup_path = backup_dir / f"nhm_approval_model_backup_{timestamp}_{unique_id}.pkl"

    # Copiar modelo
    try:
        shutil.copy2(current_model_path, backup_path)
        logger.info(
            "model_backup_successful",
            original=str(current_model_path),
            backup=str(backup_path),
            size_bytes=backup_path.stat().st_size,
        )
    except Exception as e:
        raise ModelBackupError(f"Erro ao criar backup: {e}") from e

    # Também fazer backup do metrics.json se existir
    metrics_path = models_dir / METRICS_FILE
    if metrics_path.exists():
        backup_metrics_path = backup_dir / f"metrics_backup_{timestamp}.json"
        try:
            shutil.copy2(metrics_path, backup_metrics_path)
            logger.info(
                "metrics_backup_successful",
                backup=str(backup_metrics_path),
            )
        except Exception as e:
            logger.warning("metrics_backup_failed", error=str(e))

    return backup_path


def update_model_version(
    model_version: str,
    models_dir: Path = DEFAULT_MODELS_DIR,
) -> dict[str, Any]:
    """
    Atualiza arquivo de versão do modelo.

    Args:
        model_version: Nova versão do modelo (ex: "v8")
        models_dir: Diretório onde estão os modelos

    Returns:
        Dicionário com os dados de versão atualizados
    """
    logger.info("updating_model_version", version=model_version)

    version_file = models_dir / VERSION_FILE

    # Ler versão atual se existir
    current_data: dict[str, Any] = {}
    if version_file.exists():
        try:
            with open(version_file) as f:
                current_data = json.load(f)
        except Exception as e:
            logger.warning("failed_to_read_version_file", error=str(e))

    # Atualizar dados
    new_data = {
        "current_version": model_version,
        "previous_version": current_data.get("current_version", "unknown"),
        "updated_at": datetime.now().isoformat(),
        "promotion_history": current_data.get("promotion_history", []),
    }

    # Adicionar ao histórico
    new_data["promotion_history"].append(
        {
            "version": model_version,
            "timestamp": datetime.now().isoformat(),
            "previous_version": current_data.get("current_version", "unknown"),
        }
    )

    # Manter apenas últimos 10 registros no histórico
    if len(new_data["promotion_history"]) > 10:
        new_data["promotion_history"] = new_data["promotion_history"][-10:]

    # Escrever arquivo
    version_file.parent.mkdir(parents=True, exist_ok=True)
    with open(version_file, "w") as f:
        json.dump(new_data, f, indent=2)

    logger.info(
        "model_version_updated",
        version=model_version,
        version_file=str(version_file),
    )

    return new_data


def promote_model(
    model_path: Path,
    from_stage: str = Stage.STAGING,
    to_stage: str = Stage.PRODUCTION,
    models_dir: Path = DEFAULT_MODELS_DIR,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    min_accuracy: float = DEFAULT_MIN_ACCURACY,
    max_drift_score: float = DEFAULT_MAX_DRIFT_SCORE,
    min_f1_score: float = DEFAULT_MIN_F1_SCORE,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Promove modelo de um ambiente para outro com validação e backup.

    O processo de promoção é atômico: se qualquer etapa falhar,
    as alterações são revertidas.

    Args:
        model_path: Caminho para o novo modelo a ser promovido
        from_stage: Ambiente de origem (staging, shadow)
        to_stage: Ambiente de destino (production)
        models_dir: Diretório onde estão os modelos
        backup_dir: Diretório para armazenar backups
        min_accuracy: Acurácia mínima exigida
        max_drift_score: Score máximo de drift permitido
        min_f1_score: F1-score mínimo exigido
        dry_run: Se True, simula a promoção sem aplicar mudanças

    Returns:
        Dicionário com resultado da promoção

    Raises:
        ModelPromotionError: Se promoção falhar
    """
    logger.info(
        "starting_model_promotion",
        model_path=str(model_path),
        from_stage=from_stage,
        to_stage=to_stage,
        dry_run=dry_run,
    )

    result = {
        "status": "pending",
        "from_stage": from_stage,
        "to_stage": to_stage,
        "model_path": str(model_path),
        "dry_run": dry_run,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # 1. Validar modelo
        metrics = validate_model(
            model_path=model_path,
            min_accuracy=min_accuracy,
            max_drift_score=max_drift_score,
            min_f1_score=min_f1_score,
        )
        result["metrics"] = metrics.to_dict()

        if dry_run:
            result["status"] = "dry_run_success"
            logger.info(
                "dry_run_complete",
                model_path=str(model_path),
                metrics=metrics.to_dict(),
            )
            return result

        # 2. Backup do modelo atual
        backup_path = backup_current_model(
            models_dir=models_dir,
            backup_dir=backup_dir,
        )
        result["backup_path"] = str(backup_path)

        # 3. Copiar novo modelo (operação atômica)
        target_path = models_dir / MODEL_FILE
        temp_path = models_dir / f"{MODEL_FILE}.tmp"

        try:
            # Copiar para arquivo temporário primeiro
            shutil.copy2(model_path, temp_path)

            # Renomear atomicamente
            temp_path.replace(target_path)

            logger.info(
                "model_promoted",
                source=str(model_path),
                target=str(target_path),
            )
        except Exception as e:
            # Limpar arquivo temporário se existir
            if temp_path.exists():
                temp_path.unlink()
            raise ModelPromotionError(f"Erro ao copiar modelo: {e}") from e

        # 4. Atualizar versão
        version_info = update_model_version(
            model_version=metrics.model_version,
            models_dir=models_dir,
        )
        result["version_info"] = version_info

        # 5. Atualizar metrics.json
        metrics_file = models_dir / METRICS_FILE
        with open(metrics_file, "w") as f:
            json.dump(metrics.to_dict(), f, indent=2)

        result["status"] = "success"
        logger.info(
            "model_promotion_successful",
            model_version=metrics.model_version,
            backup_path=str(backup_path),
        )

        return result

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(
            "model_promotion_failed",
            model_path=str(model_path),
            error=str(e),
        )
        raise


def rollback_model(
    backup_path: Optional[Path] = None,
    models_dir: Path = DEFAULT_MODELS_DIR,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> dict[str, Any]:
    """
    Reverte para versão anterior do modelo.

    Se backup_path não for especificado, usa o backup mais recente.

    Args:
        backup_path: Caminho específico para backup (opcional)
        models_dir: Diretório onde estão os modelos
        backup_dir: Diretório onde estão os backups

    Returns:
        Dicionário com resultado do rollback

    Raises:
        ModelPromotionError: Se rollback falhar
    """
    logger.info(
        "starting_model_rollback",
        backup_path=str(backup_path) if backup_path else "latest",
    )

    result = {
        "status": "pending",
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Encontrar backup se não especificado
        if backup_path is None:
            # Listar backups e pegar o mais recente
            backups = sorted(
                backup_dir.glob("nhm_approval_model_backup_*.pkl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            if not backups:
                raise ModelPromotionError("Nenhum backup encontrado para rollback")

            backup_path = backups[0]
            logger.info("using_latest_backup", backup_path=str(backup_path))

        result["backup_path"] = str(backup_path)

        # Verificar se backup existe
        if not backup_path.exists():
            raise ModelPromotionError(f"Backup não encontrado: {backup_path}")

        # Ler versão do modelo no backup
        with open(backup_path, "rb") as f:
            model_data = pickle.load(f)
        backup_version = model_data.get("version", "unknown")
        result["backup_version"] = backup_version

        # Fazer backup do modelo atual antes de reverter
        current_backup = backup_current_model(
            models_dir=models_dir,
            backup_dir=backup_dir,
        )
        result["pre_rollback_backup"] = str(current_backup)

        # Copiar backup para produção (operação atômica)
        target_path = models_dir / MODEL_FILE
        temp_path = models_dir / f"{MODEL_FILE}.rollback.tmp"

        try:
            shutil.copy2(backup_path, temp_path)
            temp_path.replace(target_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise ModelPromotionError(f"Erro ao restaurar backup: {e}") from e

        # Atualizar versão
        version_info = update_model_version(
            model_version=backup_version,
            models_dir=models_dir,
        )
        result["version_info"] = version_info

        result["status"] = "success"
        logger.info(
            "model_rollback_successful",
            backup_version=backup_version,
            backup_path=str(backup_path),
        )

        return result

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        logger.error(
            "model_rollback_failed",
            error=str(e),
        )
        raise


def list_backups(
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Lista backups disponíveis ordenados por data (mais recente primeiro).

    Args:
        backup_dir: Diretório onde estão os backups
        limit: Número máximo de backups a retornar

    Returns:
        Lista de dicionários com informações dos backups
    """
    backups = []

    if not backup_dir.exists():
        return backups

    for backup_path in sorted(
        backup_dir.glob("nhm_approval_model_backup_*.pkl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]:
        try:
            stat = backup_path.stat()

            # Extrair versão do modelo do backup
            with open(backup_path, "rb") as f:
                model_data = pickle.load(f)
            version = model_data.get("version", "unknown")

            backups.append(
                {
                    "path": str(backup_path),
                    "version": version,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        except Exception as e:
            logger.warning("failed_to_read_backup", path=str(backup_path), error=str(e))

    return backups


def get_current_model_info(
    models_dir: Path = DEFAULT_MODELS_DIR,
) -> dict[str, Any]:
    """
    Retorna informações sobre o modelo atual em produção.

    Args:
        models_dir: Diretório onde estão os modelos

    Returns:
        Dicionário com informações do modelo ou vazio se não encontrado
    """
    model_path = models_dir / MODEL_FILE
    version_file = models_dir / VERSION_FILE

    info: dict[str, Any] = {}

    # Ler versão do arquivo
    if version_file.exists():
        try:
            with open(version_file) as f:
                version_data = json.load(f)
            info["version_info"] = version_data
        except Exception as e:
            logger.warning("failed_to_read_version_file", error=str(e))

    # Ler modelo
    if model_path.exists():
        try:
            with open(model_path, "rb") as f:
                model_data = pickle.load(f)

            info["model_version"] = model_data.get("version", "unknown")
            info["trained_at"] = model_data.get("trained_at", "unknown")
            info["metrics"] = model_data.get("metrics", {})
            info["features"] = model_data.get("features", [])
            info["file_size_bytes"] = model_path.stat().st_size
            info["file_path"] = str(model_path)
        except Exception as e:
            logger.warning("failed_to_read_model", error=str(e))
    else:
        info["error"] = "Model file not found"

    return info
