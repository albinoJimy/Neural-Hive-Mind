#!/usr/bin/env python3
"""
Script de treinamento de modelos ML para orchestrator-dynamic.
Treina DurationPredictor, AnomalyDetector e LoadPredictor com dados reais.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: F401 - mantido para compatibilidade com planilha

# Adicionar path das bibliotecas
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config.settings import get_settings
from ml.anomaly_detector import AnomalyDetector
from ml.drift_detector import DriftDetector
from ml.duration_predictor import DurationPredictor
from ml.feature_engineering import extract_ticket_features
from ml.load_predictor import LoadPredictor
from ml.model_registry import ModelRegistry
from ml.training_pipeline import TrainingPipeline
from observability.metrics import OrchestratorMetrics
from clients.mongodb_client import MongoDBClient


class ProductionModelTrainer:
    """Orquestra o treinamento dos modelos ML em ambiente de produção."""

    def __init__(
        self,
        window_days: int,
        min_samples: int,
        backfill_errors: bool = False,
        dry_run: bool = False
    ) -> None:
        self.window_days = window_days
        self.min_samples = min_samples
        self.backfill_errors = backfill_errors
        self.dry_run = dry_run

        self.config = get_settings()
        self.metrics = OrchestratorMetrics()

        self.mongo_client: Optional[MongoDBClient] = None
        self.model_registry: Optional[ModelRegistry] = None
        self.duration_predictor: Optional[DurationPredictor] = None
        self.anomaly_detector: Optional[AnomalyDetector] = None
        self.load_predictor: Optional[LoadPredictor] = None
        self.drift_detector: Optional[DriftDetector] = None
        self.training_pipeline: Optional[TrainingPipeline] = None

        self.training_results: Dict[str, Any] = {}

        self.logger = logging.getLogger("production_model_trainer")

    async def setup(self) -> None:
        """Inicializa conexões e dependências necessárias."""
        self.logger.info("setup_started")

        self.mongo_client = MongoDBClient(self.config)
        await self.mongo_client.initialize()

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

        self.training_pipeline = TrainingPipeline(
            self.config,
            self.mongo_client,
            self.model_registry,
            self.duration_predictor,
            self.anomaly_detector,
            self.metrics,
            drift_detector=self.drift_detector
        )

        await asyncio.gather(
            self.duration_predictor.initialize(),
            self.anomaly_detector.initialize()
        )

        if self.dry_run:
            self._apply_dry_run_mode()

        self.logger.info("setup_completed")

    def _apply_dry_run_mode(self) -> None:
        """Ativa modo dry-run substituindo operações de gravação."""
        if not self.model_registry:
            return

        async def _noop_save_model(*args, **kwargs):
            self.logger.info(
                "dry_run_skip_save_model",
                extra={"model_name": kwargs.get("model_name") or (args[2] if len(args) > 2 else "unknown")}
            )
            return "dry-run"

        async def _noop_promote_model(*args, **kwargs):
            self.logger.info(
                "dry_run_skip_promote_model",
                extra={"model_name": kwargs.get("model_name")}
            )
            return None

        self.model_registry.save_model = _noop_save_model  # type: ignore[assignment]
        self.model_registry.promote_model = _noop_promote_model  # type: ignore[assignment]

    async def count_training_samples(self) -> int:
        """Conta amostras elegíveis para treinamento na janela configurada."""
        if not self.mongo_client:
            return 0

        cutoff_date = datetime.utcnow() - timedelta(days=self.window_days)
        tickets_collection = self.mongo_client.db[self.config.mongodb_collection_tickets]

        query = {
            "status": "COMPLETED",
            "actual_duration_ms": {"$exists": True, "$gt": 0},
            "completed_at": {"$gte": cutoff_date}
        }

        return await tickets_collection.count_documents(query)

    async def _fetch_training_data(self) -> pd.DataFrame:
        """Busca tickets para baseline de features."""
        if not self.mongo_client:
            return pd.DataFrame()

        cutoff_date = datetime.utcnow() - timedelta(days=self.window_days)
        tickets_collection = self.mongo_client.db[self.config.mongodb_collection_tickets]

        tickets = await tickets_collection.find({
            "status": "COMPLETED",
            "actual_duration_ms": {"$exists": True, "$gt": 0},
            "completed_at": {"$gte": cutoff_date}
        }).to_list(None)

        if not tickets:
            return pd.DataFrame()

        return pd.DataFrame(tickets)

    async def train_all_models(self) -> Dict[str, Any]:
        """Executa ciclo completo de treinamento."""
        if not self.training_pipeline:
            raise RuntimeError("Training pipeline not initialized")

        self.logger.info(
            "training_started",
            extra={
                "window_days": self.window_days,
                "backfill_errors": self.backfill_errors
            }
        )

        results = await self.training_pipeline.run_training_cycle(
            window_days=self.window_days,
            backfill_errors=self.backfill_errors
        )

        self.training_results = results
        self.logger.info("training_finished", extra={"status": results.get("status")})
        return results

    def validate_models(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Valida métricas contra critérios mínimos."""
        duration_metrics = results.get("duration_predictor", {}) or {}
        anomaly_metrics = results.get("anomaly_detector", {}) or {}

        duration_mae_pct = duration_metrics.get("mae_percentage")
        anomaly_precision = anomaly_metrics.get("precision")

        validation = {
            "duration_predictor": {
                "mae_percentage": duration_mae_pct,
                "threshold": 15.0,
                "passed": duration_mae_pct is not None and duration_mae_pct < 15.0
            },
            "anomaly_detector": {
                "precision": anomaly_precision,
                "threshold": 0.75,
                "passed": anomaly_precision is not None and anomaly_precision > 0.75
            },
            "load_predictor": {
                "status": "heuristic",
                "passed": True
            }
        }

        validation["overall_passed"] = validation["duration_predictor"]["passed"] and validation["anomaly_detector"]["passed"]
        return validation

    async def save_feature_baseline(self) -> Dict[str, Any]:
        """Extrai features e salva baseline para detecção de drift."""
        if not self.drift_detector or self.dry_run:
            return {"saved": False, "reason": "drift_detector_disabled_or_dry_run"}

        df = await self._fetch_training_data()
        if df.empty:
            return {"saved": False, "reason": "no_training_data"}

        features_data = []
        target_values = []

        for row in df.to_dict(orient="records"):
            try:
                features = extract_ticket_features(row)
                if not features:
                    continue

                features_data.append(features)

                actual_duration = row.get("actual_duration_ms")
                if actual_duration and actual_duration > 0:
                    target_values.append(float(actual_duration))
            except Exception as err:
                self.logger.warning("feature_extraction_failed_for_baseline", extra={"error": str(err)})
                continue

        if not features_data or not target_values:
            return {"saved": False, "reason": "no_features_or_targets"}

        training_mae = self.training_results.get("duration_predictor", {}).get("mae", 0.0)

        self.drift_detector.save_feature_baseline(
            features_data=features_data,
            target_values=target_values,
            training_mae=training_mae,
            model_name="duration-predictor",
            version=self.training_results.get("duration_predictor", {}).get("version", "latest")
        )

        return {
            "saved": True,
            "features_count": len(features_data),
            "target_count": len(target_values),
            "training_mae": training_mae
        }

    def generate_report(
        self,
        results: Dict[str, Any],
        validation: Dict[str, Any],
        baseline_info: Dict[str, Any],
        samples_available: int
    ) -> Path:
        """Gera relatório JSON no /tmp com métricas e status."""
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        report_path = Path("/tmp") / f"ml_training_report_{timestamp}.json"

        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "window_days": self.window_days,
            "min_samples": self.min_samples,
            "backfill_errors": self.backfill_errors,
            "dry_run": self.dry_run,
            "samples_available": samples_available,
            "results": results,
            "validation": validation,
            "baseline": baseline_info,
            "models_promoted": results.get("models_promoted", []),
            "extreme_errors": (results.get("backfill_stats") or {}).get("extreme_errors", []),
        }

        report_path.write_text(json.dumps(report, indent=2, default=str))
        self.logger.info("training_report_written", extra={"path": str(report_path)})

        return report_path

    async def cleanup(self) -> None:
        """Fecha conexões com MongoDB/MLflow."""
        if self.mongo_client and self.mongo_client.client:
            self.mongo_client.client.close()

        if self.model_registry:
            await self.model_registry.close()

        self.logger.info("cleanup_completed")

    async def run(self) -> int:
        """Executa fluxo completo de treinamento."""
        try:
            await self.setup()
            samples_available = await self.count_training_samples()

            if samples_available < self.min_samples:
                warning_report = self.generate_report(
                    results={"status": "skipped", "reason": "insufficient_data"},
                    validation={"overall_passed": False},
                    baseline_info={"saved": False, "reason": "insufficient_data"},
                    samples_available=samples_available
                )
                self.logger.warning(
                    "insufficient_training_data",
                    extra={
                        "samples": samples_available,
                        "required": self.min_samples,
                        "report": str(warning_report)
                    }
                )
                return 1

            results = await self.train_all_models()
            validation = self.validate_models(results)
            baseline_info = await self.save_feature_baseline()

            report_path = self.generate_report(results, validation, baseline_info, samples_available)

            if validation.get("overall_passed"):
                self.logger.info("training_successful", extra={"report": str(report_path)})
                return 0

            self.logger.warning("training_completed_with_validation_issues", extra={"report": str(report_path)})
            return 1

        except Exception as exc:  # pragma: no cover - proteção de execução
            self.logger.exception("training_script_failed", extra={"error": str(exc)})

            failure_report = {
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(exc),
                "window_days": self.window_days,
                "backfill_errors": self.backfill_errors,
                "dry_run": self.dry_run
            }
            report_path = Path("/tmp") / f"ml_training_report_error_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
            report_path.write_text(json.dumps(failure_report, indent=2, default=str))

            return 1

        finally:
            await self.cleanup()


def parse_args() -> argparse.Namespace:
    """Parsers de argumentos CLI."""
    parser = argparse.ArgumentParser(description="Treinamento de modelos ML para orchestrator-dynamic")
    parser.add_argument("--window-days", type=int, default=540, help="Janela de dados em dias (default: 540)")
    parser.add_argument("--min-samples", type=int, default=100, help="Mínimo de amostras para treinamento (default: 100)")
    parser.add_argument("--backfill-errors", action="store_true", help="Habilitar backfill de erros históricos")
    parser.add_argument("--dry-run", action="store_true", help="Executa fluxo sem salvar/promover modelos")
    return parser.parse_args()


def configure_logging() -> None:
    """Configura logging básico para execução standalone."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )


def main() -> None:
    configure_logging()
    args = parse_args()

    trainer = ProductionModelTrainer(
        window_days=args.window_days,
        min_samples=args.min_samples,
        backfill_errors=args.backfill_errors,
        dry_run=args.dry_run
    )

    exit_code = asyncio.run(trainer.run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
