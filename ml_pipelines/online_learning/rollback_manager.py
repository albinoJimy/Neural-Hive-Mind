"""
Rollback Manager para Online Learning.

Gerencia versões de modelos online e executa rollback automático
quando degradação de performance é detectada.
"""

import os
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple
import structlog
import joblib
from pymongo import MongoClient, DESCENDING
from prometheus_client import Counter, Histogram, Gauge
import requests

from .config import OnlineLearningConfig

logger = structlog.get_logger(__name__)

# Métricas Prometheus - lazy initialization
_rollback_metrics_initialized = False
rollback_total = None
rollback_duration = None
model_versions_count = None
degradation_detected_total = None


def _init_rollback_prometheus_metrics():
    """Inicializa métricas Prometheus de forma lazy."""
    global _rollback_metrics_initialized, rollback_total, rollback_duration
    global model_versions_count, degradation_detected_total

    if _rollback_metrics_initialized:
        return

    rollback_total = Counter(
        "neural_hive_rollback_total", "Total de rollbacks executados", ["specialist_type", "reason"]
    )
    rollback_duration = Histogram(
        "neural_hive_rollback_duration_seconds", "Duração de rollbacks", ["specialist_type"]
    )
    model_versions_count = Gauge(
        "neural_hive_model_versions_count",
        "Número de versões de modelo armazenadas",
        ["specialist_type"],
    )
    degradation_detected_total = Counter(
        "neural_hive_degradation_detected_total",
        "Total de degradações detectadas",
        ["specialist_type", "metric"],
    )
    _rollback_metrics_initialized = True


class RollbackError(Exception):
    """Exceção para erros de rollback."""

    pass


class ModelVersion:
    """Representa uma versão de modelo."""

    def __init__(
        self,
        version_id: str,
        specialist_type: str,
        checkpoint_path: str,
        created_at: datetime,
        metrics: Dict[str, float],
        is_stable: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.version_id = version_id
        self.specialist_type = specialist_type
        self.checkpoint_path = checkpoint_path
        self.created_at = created_at
        self.metrics = metrics
        self.is_stable = is_stable
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "specialist_type": self.specialist_type,
            "checkpoint_path": self.checkpoint_path,
            "created_at": self.created_at.isoformat(),
            "metrics": self.metrics,
            "is_stable": self.is_stable,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelVersion":
        return cls(
            version_id=data["version_id"],
            specialist_type=data["specialist_type"],
            checkpoint_path=data["checkpoint_path"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metrics=data.get("metrics", {}),
            is_stable=data.get("is_stable", False),
            metadata=data.get("metadata", {}),
        )


class RollbackManager:
    """
    Gerencia versões de modelos e executa rollbacks automáticos.

    Funcionalidades:
    - Armazena histórico de versões de modelo
    - Detecta degradação de performance
    - Executa rollback automático para versão estável
    - Notifica equipe via Slack/Email
    - Integra com MLflow Model Registry
    """

    def __init__(self, config: OnlineLearningConfig, specialist_type: str):
        """
        Inicializa RollbackManager.

        Args:
            config: Configuração de online learning
            specialist_type: Tipo do especialista
        """
        # Inicializa métricas Prometheus (lazy)
        _init_rollback_prometheus_metrics()

        self.config = config
        self.specialist_type = specialist_type

        # MongoDB para persistência
        self._client = MongoClient(config.mongodb_uri)
        self._db = self._client[config.mongodb_database]
        self._versions_collection = self._db["model_versions"]
        self._rollbacks_collection = self._db["rollback_history"]

        # Criar índices
        self._create_indexes()

        # Estado
        self._current_version: Optional[ModelVersion] = None
        self._stable_version: Optional[ModelVersion] = None
        self._last_rollback_time: Optional[datetime] = None
        self._baseline_metrics: Optional[Dict[str, float]] = None

        # Carregar versões existentes
        self._load_versions()

        logger.info(
            "rollback_manager_initialized",
            specialist_type=specialist_type,
            max_versions=config.max_model_versions,
            f1_threshold=config.rollback_f1_drop_threshold,
            latency_threshold=config.rollback_latency_increase_threshold,
        )

    def _create_indexes(self):
        """Cria índices no MongoDB."""
        try:
            self._versions_collection.create_index([("specialist_type", 1), ("created_at", -1)])
            self._versions_collection.create_index([("specialist_type", 1), ("is_stable", 1)])
            self._rollbacks_collection.create_index([("specialist_type", 1), ("timestamp", -1)])
        except Exception as e:
            logger.warning("failed_to_create_indexes", error=str(e))

    def _load_versions(self):
        """Carrega versões existentes do MongoDB."""
        try:
            # Buscar versão estável atual
            stable_doc = self._versions_collection.find_one(
                {"specialist_type": self.specialist_type, "is_stable": True}
            )
            if stable_doc:
                stable_doc.pop("_id", None)
                self._stable_version = ModelVersion.from_dict(stable_doc)
                self._current_version = self._stable_version
                self._baseline_metrics = self._stable_version.metrics

            # Contar versões
            count = self._versions_collection.count_documents(
                {"specialist_type": self.specialist_type}
            )
            model_versions_count.labels(specialist_type=self.specialist_type).set(count)

            logger.info(
                "versions_loaded",
                specialist_type=self.specialist_type,
                has_stable=self._stable_version is not None,
                total_versions=count,
            )

        except Exception as e:
            logger.error("failed_to_load_versions", error=str(e))

    def register_version(
        self,
        version_id: str,
        checkpoint_path: str,
        metrics: Dict[str, float],
        mark_stable: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ModelVersion:
        """
        Registra nova versão de modelo.

        Args:
            version_id: ID da versão
            checkpoint_path: Caminho do checkpoint
            metrics: Métricas da versão (f1, precision, recall, latency_ms)
            mark_stable: Se deve marcar como versão estável
            metadata: Metadados adicionais

        Returns:
            ModelVersion registrada
        """
        version = ModelVersion(
            version_id=version_id,
            specialist_type=self.specialist_type,
            checkpoint_path=checkpoint_path,
            created_at=datetime.now(timezone.utc),
            metrics=metrics,
            is_stable=mark_stable,
            metadata=metadata,
        )

        try:
            # Se marcando como estável, desmarcar anterior
            if mark_stable:
                self._versions_collection.update_many(
                    {"specialist_type": self.specialist_type, "is_stable": True},
                    {"$set": {"is_stable": False}},
                )
                self._stable_version = version
                self._baseline_metrics = metrics

            # Inserir nova versão
            self._versions_collection.insert_one(version.to_dict())
            self._current_version = version

            # Limpar versões antigas
            self._cleanup_old_versions()

            # Atualizar métrica
            count = self._versions_collection.count_documents(
                {"specialist_type": self.specialist_type}
            )
            model_versions_count.labels(specialist_type=self.specialist_type).set(count)

            logger.info(
                "version_registered",
                version_id=version_id,
                specialist_type=self.specialist_type,
                is_stable=mark_stable,
                metrics=metrics,
            )

            return version

        except Exception as e:
            logger.error("failed_to_register_version", version_id=version_id, error=str(e))
            raise RollbackError(f"Falha ao registrar versão: {str(e)}") from e

    def _cleanup_old_versions(self):
        """Remove versões antigas mantendo max_model_versions."""
        try:
            # Buscar todas versões ordenadas por data
            versions = list(
                self._versions_collection.find({"specialist_type": self.specialist_type}).sort(
                    "created_at", DESCENDING
                )
            )

            if len(versions) <= self.config.max_model_versions:
                return

            # Identificar versões para remover (manter estáveis)
            to_remove = []
            kept_count = 0

            for v in versions:
                if v.get("is_stable"):
                    continue
                if kept_count >= self.config.max_model_versions:
                    to_remove.append(v)
                else:
                    kept_count += 1

            # Remover versões
            for v in to_remove:
                # Remover checkpoint se existir
                if v.get("checkpoint_path") and os.path.exists(v["checkpoint_path"]):
                    try:
                        os.remove(v["checkpoint_path"])
                    except Exception:
                        pass

                self._versions_collection.delete_one({"version_id": v["version_id"]})

            if to_remove:
                logger.info(
                    "old_versions_cleaned",
                    specialist_type=self.specialist_type,
                    removed_count=len(to_remove),
                )

        except Exception as e:
            logger.warning("cleanup_failed", error=str(e))

    def detect_degradation(self, current_metrics: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        Detecta degradação de performance.

        Args:
            current_metrics: Métricas atuais (f1, precision, recall, latency_ms)

        Returns:
            Tuple (is_degraded, list of reasons)
        """
        if self._baseline_metrics is None:
            logger.warning("no_baseline_metrics", specialist_type=self.specialist_type)
            return False, []

        reasons = []

        # Verificar F1 drop
        if "f1" in current_metrics and "f1" in self._baseline_metrics:
            baseline_f1 = self._baseline_metrics["f1"]
            current_f1 = current_metrics["f1"]
            f1_drop = baseline_f1 - current_f1

            if f1_drop > self.config.rollback_f1_drop_threshold:
                reasons.append(
                    f"F1 drop: {f1_drop:.3f} (baseline: {baseline_f1:.3f}, "
                    f"current: {current_f1:.3f}, threshold: {self.config.rollback_f1_drop_threshold})"
                )
                degradation_detected_total.labels(
                    specialist_type=self.specialist_type, metric="f1"
                ).inc()

        # Verificar latency increase
        if "latency_ms" in current_metrics and "latency_ms" in self._baseline_metrics:
            baseline_latency = self._baseline_metrics["latency_ms"]
            current_latency = current_metrics["latency_ms"]

            if baseline_latency > 0:
                latency_increase = (current_latency - baseline_latency) / baseline_latency

                if latency_increase > self.config.rollback_latency_increase_threshold:
                    reasons.append(
                        f"Latency increase: {latency_increase:.1%} "
                        f"(baseline: {baseline_latency:.1f}ms, current: {current_latency:.1f}ms, "
                        f"threshold: {self.config.rollback_latency_increase_threshold:.0%})"
                    )
                    degradation_detected_total.labels(
                        specialist_type=self.specialist_type, metric="latency"
                    ).inc()

        # Verificar precision drop
        if "precision" in current_metrics and "precision" in self._baseline_metrics:
            baseline_prec = self._baseline_metrics["precision"]
            current_prec = current_metrics["precision"]
            prec_drop = baseline_prec - current_prec

            if prec_drop > self.config.rollback_f1_drop_threshold:
                reasons.append(f"Precision drop: {prec_drop:.3f}")
                degradation_detected_total.labels(
                    specialist_type=self.specialist_type, metric="precision"
                ).inc()

        is_degraded = len(reasons) > 0

        if is_degraded:
            logger.warning(
                "degradation_detected",
                specialist_type=self.specialist_type,
                reasons=reasons,
                current_metrics=current_metrics,
                baseline_metrics=self._baseline_metrics,
            )

        return is_degraded, reasons

    def execute_rollback(self, reason: str, target_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Executa rollback para versão estável.

        Args:
            reason: Razão do rollback
            target_version: Versão alvo (usa estável se não especificado)

        Returns:
            Dict com detalhes do rollback
        """
        start_time = time.time()

        # Verificar cooldown
        if self._last_rollback_time:
            cooldown_end = self._last_rollback_time + timedelta(
                minutes=self.config.rollback_cooldown_minutes
            )
            if datetime.now(timezone.utc) < cooldown_end:
                remaining = (cooldown_end - datetime.now(timezone.utc)).seconds
                raise RollbackError(f"Rollback em cooldown. Aguarde {remaining} segundos.")

        # Determinar versão alvo
        if target_version:
            target_doc = self._versions_collection.find_one(
                {"specialist_type": self.specialist_type, "version_id": target_version}
            )
            if not target_doc:
                raise RollbackError(f"Versão {target_version} não encontrada")
            target_doc.pop("_id", None)
            target = ModelVersion.from_dict(target_doc)
        elif self._stable_version:
            target = self._stable_version
        else:
            raise RollbackError("Nenhuma versão estável disponível para rollback")

        rollback_id = f"rollback-{uuid.uuid4().hex[:12]}"

        try:
            # Verificar se checkpoint existe
            if not os.path.exists(target.checkpoint_path):
                raise RollbackError(f"Checkpoint não encontrado: {target.checkpoint_path}")

            # Registrar rollback
            rollback_record = {
                "rollback_id": rollback_id,
                "specialist_type": self.specialist_type,
                "from_version": self._current_version.version_id if self._current_version else None,
                "to_version": target.version_id,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc),
                "status": "completed",
                "duration_seconds": 0,
            }

            # Atualizar versão atual
            previous_version = self._current_version
            self._current_version = target
            self._last_rollback_time = datetime.now(timezone.utc)

            # Calcular duração
            duration = time.time() - start_time
            rollback_record["duration_seconds"] = duration

            # Persistir registro
            self._rollbacks_collection.insert_one(rollback_record)

            # Emitir métricas
            rollback_total.labels(
                specialist_type=self.specialist_type,
                reason=reason.split(":")[0] if ":" in reason else reason[:20],
            ).inc()
            rollback_duration.labels(specialist_type=self.specialist_type).observe(duration)

            # Enviar notificação
            self._send_notification(rollback_id, reason, target, previous_version)

            logger.info(
                "rollback_completed",
                rollback_id=rollback_id,
                specialist_type=self.specialist_type,
                from_version=previous_version.version_id if previous_version else None,
                to_version=target.version_id,
                reason=reason,
                duration_seconds=duration,
            )

            return {
                "rollback_id": rollback_id,
                "from_version": previous_version.version_id if previous_version else None,
                "to_version": target.version_id,
                "reason": reason,
                "duration_seconds": duration,
                "status": "completed",
            }

        except Exception as e:
            # Registrar falha
            rollback_record = {
                "rollback_id": rollback_id,
                "specialist_type": self.specialist_type,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc),
                "status": "failed",
                "error": str(e),
            }
            self._rollbacks_collection.insert_one(rollback_record)

            logger.error(
                "rollback_failed",
                rollback_id=rollback_id,
                specialist_type=self.specialist_type,
                error=str(e),
            )
            raise RollbackError(f"Falha no rollback: {str(e)}") from e

    def _send_notification(
        self, rollback_id: str, reason: str, target: ModelVersion, previous: Optional[ModelVersion]
    ):
        """Envia notificação de rollback."""
        if not self.config.notification_channels:
            return

        message = (
            f"🔄 *Rollback Executado*\n"
            f"• Specialist: {self.specialist_type}\n"
            f"• ID: {rollback_id}\n"
            f"• De: {previous.version_id if previous else 'N/A'}\n"
            f"• Para: {target.version_id}\n"
            f"• Razão: {reason}\n"
            f"• Timestamp: {datetime.now(timezone.utc).isoformat()}"
        )

        if "slack" in self.config.notification_channels and self.config.slack_webhook_url:
            try:
                requests.post(self.config.slack_webhook_url, json={"text": message}, timeout=10)
            except Exception as e:
                logger.warning("slack_notification_failed", error=str(e))

    def get_current_version(self) -> Optional[ModelVersion]:
        """Retorna versão atual."""
        return self._current_version

    def get_stable_version(self) -> Optional[ModelVersion]:
        """Retorna versão estável."""
        return self._stable_version

    def list_versions(self, limit: int = 10) -> List[ModelVersion]:
        """
        Lista versões recentes.

        Args:
            limit: Número máximo de versões

        Returns:
            Lista de ModelVersion
        """
        docs = (
            self._versions_collection.find({"specialist_type": self.specialist_type})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )

        versions = []
        for doc in docs:
            doc.pop("_id", None)
            versions.append(ModelVersion.from_dict(doc))

        return versions

    def get_rollback_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retorna histórico de rollbacks.

        Args:
            limit: Número máximo de registros

        Returns:
            Lista de registros de rollback
        """
        docs = (
            self._rollbacks_collection.find({"specialist_type": self.specialist_type})
            .sort("timestamp", DESCENDING)
            .limit(limit)
        )

        history = []
        for doc in docs:
            doc.pop("_id", None)
            if "timestamp" in doc:
                doc["timestamp"] = doc["timestamp"].isoformat()
            history.append(doc)

        return history

    def set_baseline_metrics(self, metrics: Dict[str, float]):
        """Define métricas baseline para comparação."""
        self._baseline_metrics = metrics
        logger.info("baseline_metrics_set", specialist_type=self.specialist_type, metrics=metrics)

    def load_checkpoint(self, version: ModelVersion) -> Any:
        """
        Carrega checkpoint de uma versão.

        Args:
            version: Versão do modelo

        Returns:
            Checkpoint carregado
        """
        if not os.path.exists(version.checkpoint_path):
            raise RollbackError(f"Checkpoint não encontrado: {version.checkpoint_path}")

        return joblib.load(version.checkpoint_path)

    def close(self):
        """Fecha conexão com MongoDB."""
        if self._client:
            self._client.close()
