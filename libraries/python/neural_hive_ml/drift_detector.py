"""DriftDetector - Detecção de Model Drift para Approval Models."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class DriftDetector:
    """
    Detector de drift para modelos de aprovação.

    Monitora métricas de produção e detecta degradation
    de performance comparando baseline com current.
    """

    def __init__(
        self,
        mongo_client: AsyncIOMotorDatabase,
        kafka_producer: Any,
        confidence_threshold: float = 0.10,
        approve_rate_threshold: float = 0.15,
        baseline_window_hours: int = 168,  # 7 dias
    ):
        """
        Inicializa o detector de drift.

        Args:
            mongo_client: Cliente MongoDB
            kafka_producer: Producer Kafka para alertas
            confidence_threshold: Threshold para alerta de confidence drop
            approve_rate_threshold: Threshold para alerta de approve rate change
            baseline_window_hours: Janela para cálculo de baseline
        """
        self.mongo_client = mongo_client
        self.kafka_producer = kafka_producer
        self.confidence_threshold = confidence_threshold
        self.approve_rate_threshold = approve_rate_threshold
        self.baseline_window_hours = baseline_window_hours
        logger.info("DriftDetector inicializado")

    @property
    def db(self):
        """Propriedade para compatibilidade com código existente."""
        return self.mongo_client

    async def calculate_baseline(self, window_hours: int = 168) -> Dict[str, Any]:
        """
        Calcula baseline de métricas (últimos N dias).

        Args:
            window_hours: Horas de dados para considerar

        Returns:
            Dicionário com métricas baseline
        """
        try:
            pipeline = self._build_aggregation_pipeline(window_hours)

            # Aggregate retorna cursor diretamente
            cursor = self.db.plan_approvals.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if results and results[0]:
                return {
                    "approve_rate": results[0].get("approve_rate", 0.0),
                    "avg_confidence": results[0].get("avg_confidence", 0.0),
                    "sample_count": results[0].get("count", 0),
                }

            # Valores padrão se não houver dados
            return {"approve_rate": 0.65, "avg_confidence": 0.72, "sample_count": 0}

        except Exception as e:
            logger.error(f"Erro ao calcular baseline: {e}")
            raise

    async def calculate_current(self, window_hours: int = 24) -> Dict[str, Any]:
        """
        Calcula métricas atuais (últimas N horas).

        Args:
            window_hours: Horas de dados para considerar

        Returns:
            Dicionário com métricas atuais
        """
        try:
            pipeline = self._build_aggregation_pipeline(window_hours)

            cursor = self.db.plan_approvals.aggregate(pipeline)
            results = await cursor.to_list(length=1)

            if results and results[0]:
                return {
                    "approve_rate": results[0].get("approve_rate", 0.0),
                    "avg_confidence": results[0].get("avg_confidence", 0.0),
                    "sample_count": results[0].get("count", 0),
                }

            return {"approve_rate": 0.0, "avg_confidence": 0.0, "sample_count": 0}

        except Exception as e:
            logger.error(f"Erro ao calcular métricas atuais: {e}")
            raise

    def _build_aggregation_pipeline(self, window_hours: int) -> list:
        """Constrói pipeline de agregação MongoDB."""
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

        return [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": None,
                    "approve_rate": {
                        "$avg": {"$cond": [{"$eq": ["$approval_decision", "approve"]}, 1, 0]}
                    },
                    "avg_confidence": {"$avg": "$ml_confidence"},
                    "count": {"$sum": 1},
                }
            },
        ]

    async def detect_drift(self, window_hours: int = 168) -> Dict[str, Any]:
        """
        Detecta drift comparando baseline com current.

        Args:
            window_hours: Janela para comparação

        Returns:
            Dicionário com resultado da detecção
        """
        try:
            # Calcula baseline (7 dias atrás até 7 dias atrás)
            baseline = await self.calculate_baseline(self.baseline_window_hours)

            # Calcula current (últimas 24h)
            current = await self.calculate_current(24)

            # Calcula mudanças
            confidence_change = current["avg_confidence"] - baseline["avg_confidence"]
            approve_rate_change = current["approve_rate"] - baseline["approve_rate"]

            # Detecta drift
            alerts = []
            drift_detected = False

            if abs(confidence_change) >= self.confidence_threshold:
                alerts.append(
                    {
                        "metric": "avg_confidence",
                        "change": round(confidence_change, 3),
                        "threshold": self.confidence_threshold,
                        "severity": "warning"
                        if abs(confidence_change) < self.confidence_threshold * 1.5
                        else "critical",
                    }
                )
                drift_detected = True

            if abs(approve_rate_change) >= self.approve_rate_threshold:
                alerts.append(
                    {
                        "metric": "approve_rate",
                        "change": round(approve_rate_change, 3),
                        "threshold": self.approve_rate_threshold,
                        "severity": "warning",
                    }
                )
                drift_detected = True

            result = {
                "model_version": await self._get_active_model_version(),
                "window_hours": window_hours,
                "baseline": baseline,
                "current": current,
                "drift_detected": drift_detected,
                "alerts": alerts,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            # Publica alerta se drift detectado
            if drift_detected:
                await self.publish_drift_alert(result)

            return result

        except Exception as e:
            logger.error(f"Erro ao detectar drift: {e}")
            return {
                "drift_detected": False,
                "error": str(e),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    async def _get_active_model_version(self) -> str:
        """
        Obtém versão do modelo ativo.

        Busca na coleção model_versions do MongoDB
        pelo modelo com stage='production' e is_active=True.
        """
        try:
            doc = await self.db.model_versions.find_one(
                {"stage": "production", "is_active": True}, sort=[("created_at", -1)]
            )

            if doc and "version" in doc:
                return doc["version"]

            # Fallback se não encontrar modelo ativo
            logger.warning("Nenhum modelo ativo encontrado em model_versions")
            return "unknown"

        except Exception as e:
            logger.error(f"Erro ao buscar versão do modelo ativo: {e}")
            return "unknown"

    async def publish_drift_alert(self, drift_data: Dict[str, Any]) -> bool:
        """
        Publica alerta de drift no Kafka.

        Args:
            drift_data: Dados do drift detectado

        Returns:
            True se publicou com sucesso
        """
        try:
            if not self.kafka_producer:
                return False

            event = {
                "event_type": "model_drift_detected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model_version": drift_data.get("model_version"),
                "drift_detected": drift_data.get("drift_detected"),
                "alerts": drift_data.get("alerts", []),
                "confidence_change": drift_data.get("current", {}).get("avg_confidence", 0)
                - drift_data.get("baseline", {}).get("avg_confidence", 0),
            }

            await self.kafka_producer.produce_and_wait(
                topic="ml.model_drift_detected",
                key="drift_alert",
                value=json.dumps(event),
            )

            logger.info(f"Alerta de drift publicado para modelo {event['model_version']}")
            return True

        except Exception as e:
            logger.error(f"Erro ao publicar alerta: {e}")
            return False

    async def get_drift_metrics(self, window_hours: int = 168) -> Dict[str, Any]:
        """
        Obtém métricas de drift para API endpoint.

        Args:
            window_hours: Janela para análise

        Returns:
            Dicionário com métricas formatadas
        """
        drift_data = await self.detect_drift(window_hours)

        # Adiciona recomendação
        if drift_data.get("drift_detected"):
            drift_data["recommendation"] = "Consider retraining with latest 100+ samples"

        return drift_data


class CanaryDeployer:
    """
    Gerencia deploy canary de novos modelos.

    Testa novo modelo com % do tráfego antes de promover 100%.
    """

    # Armazenamento em memória para canaries ativos
    # Em produção, usar Redis ou similar
    _active_canaries: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        model_repo: Any,
        kafka_producer: Any,
        canary_duration_minutes: int = 60,
        canary_traffic_percentage: int = 10,
    ):
        """
        Inicializa o canary deployer.

        Args:
            model_repo: Repositório de versões
            kafka_producer: Producer Kafka para eventos
            canary_duration_minutes: Duração do teste canary
            canary_traffic_percentage: Percentual de tráfego para canary
        """
        self.model_repo = model_repo
        self.kafka_producer = kafka_producer
        self.canary_duration_minutes = canary_duration_minutes
        self.canary_traffic_percentage = canary_traffic_percentage

    async def start_canary(self, version: str, target_version: str) -> Dict[str, Any]:
        """
        Inicia deploy canary.

        Args:
            version: Versão do modelo novo
            target_version: Versão do modelo atual

        Returns:
            Status do canary
        """
        # Valida existência das versões
        new_model = await self.model_repo.get_model_version(version)
        if not new_model:
            return {"status": "failed", "error": f"Version {version} not found"}

        canary_id = f"canary-{version}-{target_version}"
        started_at = datetime.now(timezone.utc)

        # Armazena estado do canary
        self._active_canaries[canary_id] = {
            "canary_id": canary_id,
            "version": version,
            "target_version": target_version,
            "status": "running",
            "started_at": started_at,
            "traffic_percentage": self.canary_traffic_percentage,
            "duration_minutes": self.canary_duration_minutes,
            "metrics": [],
        }

        # Publica evento Kafka
        await self._publish_canary_event("canary_started", canary_id, version, target_version)

        return {
            "canary_id": canary_id,
            "status": "running",
            "started_at": started_at.isoformat(),
            "canary_traffic_percentage": self.canary_traffic_percentage,
            "duration_minutes": self.canary_duration_minutes,
        }

    async def collect_canary_metrics(self, canary_id: str) -> Dict[str, Any]:
        """
        Coleta métricas durante o período canary.

        Args:
            canary_id: ID do canary

        Returns:
            Métricas coletadas
        """
        canary = self._active_canaries.get(canary_id)
        if not canary:
            return {"canary_id": canary_id, "error": "Canary not found"}

        # Coleta métricas simuladas
        # Em produção, buscar do Prometheus/monitoring
        baseline_f1 = canary.get("baseline_f1", 0.73)
        canary_f1 = baseline_f1 + 0.02  # Simula leve melhoria

        metrics = {
            "baseline": {
                "version": canary["target_version"],
                "f1_score": baseline_f1,
                "accuracy": 0.80,
                "sample_count": 1000,
            },
            "canary": {
                "version": canary["version"],
                "f1_score": canary_f1,
                "accuracy": 0.81,
                "sample_count": 100,  # 10% do tráfego
            },
            "comparison": {"f1_delta": canary_f1 - baseline_f1, "accuracy_delta": 0.01},
        }

        return {
            "canary_id": canary_id,
            "metrics": metrics,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def validate_canary(self, canary_id: str) -> Dict[str, Any]:
        """
        Valida se canary deve ser promovido.

        Args:
            canary_id: ID do canary

        Returns:
            Dict com should_promote e reasons
        """
        canary = self._active_canaries.get(canary_id)
        if not canary:
            return {"should_promote": False, "reasons": ["Canary not found"]}

        metrics_result = await self.collect_canary_metrics(canary_id)
        metrics = metrics_result.get("metrics", {})
        comparison = metrics.get("comparison", {})

        f1_delta = comparison.get("f1_delta", 0)
        canary_samples = metrics.get("canary", {}).get("sample_count", 0)

        reasons = []
        should_promote = True

        # Valida número mínimo de samples
        min_samples = 50
        if canary_samples < min_samples:
            should_promote = False
            reasons.append(f"Insufficient samples: {canary_samples} < {min_samples}")

        # Valida melhoria de métricas
        if f1_delta < 0:
            should_promote = False
            reasons.append(f"F1 score degraded: {f1_delta:.3f}")
        elif f1_delta < 0.01:
            reasons.append(f"F1 improvement marginal: {f1_delta:.3f}")
        else:
            reasons.append(f"F1 score improved: {f1_delta:.3f}")

        return {
            "should_promote": should_promote,
            "reasons": reasons,
            "metrics_summary": {"f1_delta": f1_delta, "sample_count": canary_samples},
        }

    async def promote_or_rollback(self, canary_id: str, should_promote: bool) -> Dict[str, Any]:
        """
        Promove ou faz rollback baseado em validação.

        Args:
            canary_id: ID do canary
            should_promote: Se deve promover

        Returns:
            Resultado da operação
        """
        if should_promote:
            return await self._promote(canary_id)
        else:
            return await self._rollback(canary_id)

    async def _promote(self, canary_id: str) -> Dict[str, Any]:
        """Promove novo modelo para 100% do tráfego."""
        canary = self._active_canaries.get(canary_id)
        if not canary:
            return {"status": "failed", "error": "Canary not found"}

        version = canary["version"]

        # Promove no repositório
        success = await self.model_repo.promote_model(
            version=version, stage="production", promoted_by="canary"
        )

        if not success:
            return {"status": "failed", "error": "Promotion failed"}

        # Atualiza estado
        canary["status"] = "promoted"
        canary["completed_at"] = datetime.now(timezone.utc).isoformat()

        # Publica evento
        await self._publish_canary_event(
            "canary_promoted", canary_id, version, canary["target_version"]
        )

        return {
            "status": "promoted",
            "canary_id": canary_id,
            "version": version,
            "previous_version": canary["target_version"],
        }

    async def _rollback(self, canary_id: str) -> Dict[str, Any]:
        """Rollback para modelo anterior."""
        canary = self._active_canaries.get(canary_id)
        if not canary:
            return {"status": "failed", "error": "Canary not found"}

        # Atualiza estado
        canary["status"] = "rolled_back"
        canary["completed_at"] = datetime.now(timezone.utc).isoformat()

        # Publica evento
        await self._publish_canary_event(
            "canary_rolled_back", canary_id, canary["version"], canary["target_version"]
        )

        return {
            "status": "rolled_back",
            "canary_id": canary_id,
            "remained_version": canary["target_version"],
        }

    async def _calculate_traffic_split(
        self, canary_version: str, baseline_version: str
    ) -> Dict[str, Any]:
        """
        Calcula split de tráfego para canary.

        Args:
            canary_version: Versão canary
            baseline_version: Versão baseline

        Returns:
            Dict com percentuais de split
        """
        canary_pct = self.canary_traffic_percentage
        baseline_pct = 100 - canary_pct

        return {
            "canary_version": canary_version,
            "baseline_version": baseline_version,
            "canary_percentage": canary_pct,
            "baseline_percentage": baseline_pct,
        }

    async def _publish_canary_event(
        self, event_type: str, canary_id: str, version: str, target_version: str
    ) -> None:
        """Publica evento Kafka sobre canary."""
        if not self.kafka_producer:
            return

        event = {
            "event_type": f"ml.{event_type}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "canary_id": canary_id,
            "version": version,
            "target_version": target_version,
        }

        try:
            await self.kafka_producer.produce_and_wait(
                topic=f"ml.{event_type}", key=canary_id, value=json.dumps(event)
            )
        except Exception as e:
            logger.error(f"Erro ao publicar evento canary: {e}")
