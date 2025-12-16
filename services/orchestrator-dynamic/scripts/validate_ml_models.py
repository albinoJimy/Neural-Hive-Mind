#!/usr/bin/env python3
"""
Script de validação de modelos ML em produção.
Verifica se modelos estão carregados, faz predições de teste, valida métricas.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mlflow.tracking import MlflowClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.settings import get_settings
from clients.mongodb_client import MongoDBClient
from ml.anomaly_detector import AnomalyDetector
from ml.drift_detector import DriftDetector
from ml.duration_predictor import DurationPredictor
from ml.load_predictor import LoadPredictor
from ml.model_registry import ModelRegistry
from observability.metrics import OrchestratorMetrics


class MLModelValidator:
    """Valida disponibilidade e funcionamento dos modelos em produção."""

    def __init__(self) -> None:
        self.config = get_settings()
        self.metrics = OrchestratorMetrics()
        self.mongo_client: Optional[MongoDBClient] = None
        self.model_registry: Optional[ModelRegistry] = None
        self.duration_predictor: Optional[DurationPredictor] = None
        self.anomaly_detector: Optional[AnomalyDetector] = None
        self.load_predictor: Optional[LoadPredictor] = None
        self.drift_detector: Optional[DriftDetector] = None
        self.logger = logging.getLogger("ml_model_validator")

    async def setup(self) -> None:
        """Inicializa dependências necessárias para validação."""
        self.mongo_client = MongoDBClient(self.config)
        await self.mongo_client.initialize()

        # Adiciona coleção de baseline se não existir na instância
        if not hasattr(self.mongo_client, "ml_feature_baselines"):
            self.mongo_client.ml_feature_baselines = self.mongo_client.db["ml_feature_baselines"]

        self.model_registry = ModelRegistry(self.config)
        await self.model_registry.initialize()

        self.duration_predictor = DurationPredictor(
            self.config,
            self.mongo_client,
            self.model_registry,
            self.metrics
        )
        self.anomaly_detector = AnomalyDetector(
            self.config,
            self.mongo_client,
            self.model_registry,
            self.metrics
        )
        self.load_predictor = LoadPredictor(
            self.config,
            self.mongo_client,
            None,
            self.metrics
        )
        self.drift_detector = DriftDetector(
            self.config,
            self.mongo_client,
            self.metrics
        )

        await asyncio.gather(
            self.duration_predictor.initialize(),
            self.anomaly_detector.initialize()
        )

    async def check_mlflow_connection(self) -> Dict[str, Any]:
        """Valida conectividade com o MLflow."""
        try:
            client = MlflowClient(tracking_uri=self.config.mlflow_tracking_uri)
            client.list_experiments()
            return {"status": "ok", "tracking_uri": self.config.mlflow_tracking_uri}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def check_models_in_production(self) -> Dict[str, Any]:
        """Lista modelos em stage Production."""
        if not self.model_registry:
            return {"status": "error", "error": "model_registry_not_initialized"}

        try:
            models = await self.model_registry.list_models()
            in_production = [
                m for m in models
                if m.get("current_stage") and m.get("current_stage").lower() == "production"
            ]
            return {
                "status": "ok" if in_production else "warning",
                "production_models": in_production,
                "total_registered": len(models)
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def validate_duration_predictor(self) -> Dict[str, Any]:
        """Executa predição de teste e mede latência do DurationPredictor."""
        if not self.duration_predictor:
            return {"status": "error", "error": "duration_predictor_not_initialized"}

        ticket = {
            "ticket_id": "validation-duration",
            "task_type": "standard_task",
            "risk_band": "medium",
            "qos": {"delivery": "at_least_once"},
            "estimated_duration_ms": 60000,
            "required_capabilities": ["compute", "storage"],
            "parameters": {"payload_size": 1024},
            "sla": {"timeout_ms": 180000}
        }

        start = time.time()
        try:
            prediction = await self.duration_predictor.predict_duration(ticket)
            latency_ms = (time.time() - start) * 1000
            return {
                "status": "ok" if latency_ms < 200 else "warning",
                "prediction_ms": prediction.get("duration_ms"),
                "confidence": prediction.get("confidence"),
                "latency_ms": latency_ms
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def validate_anomaly_detector(self) -> Dict[str, Any]:
        """Executa detecção de anomalia de teste."""
        if not self.anomaly_detector:
            return {"status": "error", "error": "anomaly_detector_not_initialized"}

        ticket = {
            "ticket_id": "validation-anomaly",
            "task_type": "standard_task",
            "risk_band": "low",
            "qos": {"delivery": "exactly_once"},
            "estimated_duration_ms": 45000,
            "required_capabilities": ["compute", "network"],
            "parameters": {"payload_size": 512},
            "sla": {"timeout_ms": 120000}
        }

        try:
            result = await self.anomaly_detector.detect_anomaly(ticket)
            return {
                "status": "ok",
                "is_anomaly": result.get("is_anomaly"),
                "anomaly_type": result.get("anomaly_type"),
                "anomaly_score": result.get("anomaly_score")
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def validate_load_predictor(self) -> Dict[str, Any]:
        """Executa predições de carga e fila para validar funcionamento básico."""
        if not self.load_predictor:
            return {"status": "error", "error": "load_predictor_not_initialized"}

        ticket = {
            "ticket_id": "validation-load",
            "task_type": "standard_task",
            "estimated_duration_ms": 30000,
            "required_capabilities": ["compute"]
        }

        try:
            queue_ms = await self.load_predictor.predict_queue_time("validator-worker", ticket)
            load_pct = await self.load_predictor.predict_worker_load("validator-worker")
            return {
                "status": "ok",
                "queue_prediction_ms": queue_ms,
                "load_prediction": load_pct
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def check_feature_baseline(self) -> Dict[str, Any]:
        """Verifica existência do baseline de features no MongoDB."""
        if not self.mongo_client:
            return {"status": "error", "error": "mongo_not_initialized"}

        try:
            collection = self.mongo_client.db["ml_feature_baselines"]
            baseline = await collection.find_one(sort=[("timestamp", -1)])
            if not baseline:
                return {"status": "warning", "baseline_found": False}

            return {
                "status": "ok",
                "baseline_found": True,
                "model_name": baseline.get("model_name"),
                "timestamp": baseline.get("timestamp")
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def run_drift_check(self) -> Dict[str, Any]:
        """Executa drift detection usando baseline existente."""
        if not self.drift_detector:
            return {"status": "error", "error": "drift_detector_not_initialized"}

        try:
            report = self.drift_detector.run_drift_check()
            return {"status": "ok", "report": report}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def generate_report(self, results: Dict[str, Any]) -> Path:
        """Salva relatório JSON consolidado no /tmp."""
        report_path = Path("/tmp") / f"ml_validation_report_{int(time.time())}.json"
        report_path.write_text(json.dumps(results, indent=2, default=str))
        self.logger.info("validation_report_written", extra={"path": str(report_path)})
        return report_path

    async def cleanup(self) -> None:
        """Fecha conexões."""
        if self.mongo_client and self.mongo_client.client:
            self.mongo_client.client.close()
        if self.model_registry:
            await self.model_registry.close()

    async def run(self) -> int:
        """Fluxo principal de validação."""
        try:
            await self.setup()

            mlflow_status = await self.check_mlflow_connection()
            models_status = await self.check_models_in_production()
            duration_status = await self.validate_duration_predictor()
            anomaly_status = await self.validate_anomaly_detector()
            load_status = await self.validate_load_predictor()
            baseline_status = await self.check_feature_baseline()
            drift_status = self.run_drift_check()

            results = {
                "timestamp": time.time(),
                "mlflow": mlflow_status,
                "models": models_status,
                "duration_predictor": duration_status,
                "anomaly_detector": anomaly_status,
                "load_predictor": load_status,
                "feature_baseline": baseline_status,
                "drift_detection": drift_status
            }

            self.generate_report(results)

            statuses = [
                mlflow_status.get("status"),
                models_status.get("status"),
                duration_status.get("status"),
                anomaly_status.get("status"),
                load_status.get("status")
            ]

            critical_error = any(status == "error" for status in statuses)
            return 1 if critical_error else 0

        finally:
            await self.cleanup()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )


def main() -> None:
    configure_logging()
    validator = MLModelValidator()
    exit_code = asyncio.run(validator.run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
