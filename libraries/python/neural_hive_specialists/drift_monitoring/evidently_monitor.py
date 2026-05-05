"""
EvidentlyMonitor: Integração com Evidently AI para detecção de drift.

Monitora distribuição de features ao longo do tempo e detecta desvios
significativos em relação ao dataset de referência.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class EvidentlyMonitor:
    """Monitor de drift usando Evidently AI."""

    def __init__(self, config: dict[str, Any]):
        """
        Inicializa monitor de drift.

        Args:
            config: Configuração com reference_dataset_path, threshold_psi, etc.
        """
        self.config = config
        self.enabled = config.get("evidently_enabled", True)
        self.project_id = config.get("evidently_project_id", "default")
        self.reference_data: Optional[pd.DataFrame] = None
        self.current_data: list[dict[str, Any]] = []
        self._load_reference_data()

        logger.info("EvidentlyMonitor initialized", config=config)

    def _load_reference_data(self):
        """Carrega dataset de referência."""
        reference_path = self.config.get("drift_reference_dataset_path")

        if reference_path:
            try:
                self.reference_data = pd.read_parquet(reference_path)
                logger.info(
                    "Reference dataset loaded",
                    path=reference_path,
                    shape=self.reference_data.shape,
                )
            except Exception as e:
                logger.error(
                    "Failed to load reference dataset",
                    path=reference_path,
                    error=str(e),
                )
                self.reference_data = None
        else:
            logger.warning("No reference dataset configured")

    def log_features(self, features: dict[str, Any], timestamp: Optional[datetime] = None):
        """
        Registra features de uma avaliação.

        Args:
            features: Dicionário de features extraídas
            timestamp: Timestamp da avaliação (usa now() se None)
        """
        record = {"timestamp": timestamp or datetime.now(timezone.utc), **features}
        self.current_data.append(record)

        logger.debug("Features logged", num_features=len(features))

    def detect_drift(self) -> dict[str, Any]:
        """
        Detecta drift comparando dados atuais com referência.

        Returns:
            Dicionário com resultados de drift:
            - drift_detected: bool
            - drift_score: float (PSI)
            - drifted_features: List[str]
            - report: Dict com detalhes
        """
        if self.reference_data is None:
            logger.warning("No reference data available for drift detection")
            return {
                "drift_detected": False,
                "drift_score": 0.0,
                "drifted_features": [],
                "report": {"error": "No reference data"},
            }

        if not self.current_data:
            logger.warning("No current data to compare")
            return {
                "drift_detected": False,
                "drift_score": 0.0,
                "drifted_features": [],
                "report": {"error": "No current data"},
            }

        try:
            # Converter current_data para DataFrame
            current_df = pd.DataFrame(self.current_data)

            # Usar Evidently para detectar drift
            from evidently.metric_preset import DataDriftPreset
            from evidently.report import Report

            report = Report(metrics=[DataDriftPreset()])

            report.run(
                reference_data=self.reference_data,
                current_data=current_df,
                column_mapping=None,
            )

            # Extrair resultados
            report_dict = report.as_dict()
            metrics = report_dict.get("metrics", [])

            drift_detected = False
            drift_score = 0.0
            drifted_features = []

            for metric in metrics:
                if metric.get("metric") == "DatasetDriftMetric":
                    result = metric.get("result", {})
                    drift_detected = result.get("dataset_drift", False)
                    drift_score = result.get("drift_share", 0.0)

                    # Identificar features com drift
                    drift_by_columns = result.get("drift_by_columns", {})
                    for col, col_result in drift_by_columns.items():
                        if col_result.get("drift_detected", False):
                            drifted_features.append(col)

            logger.info(
                "Drift detection completed",
                drift_detected=drift_detected,
                drift_score=drift_score,
                num_drifted_features=len(drifted_features),
            )

            return {
                "drift_detected": drift_detected,
                "drift_score": drift_score,
                "drifted_features": drifted_features,
                "report": report_dict,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except ImportError:
            logger.error("Evidently not installed. Install with: pip install evidently")
            return {
                "drift_detected": False,
                "drift_score": 0.0,
                "drifted_features": [],
                "report": {"error": "Evidently not installed"},
            }
        except Exception as e:
            logger.error("Drift detection failed", error=str(e), exc_info=True)
            return {
                "drift_detected": False,
                "drift_score": 0.0,
                "drifted_features": [],
                "report": {"error": str(e)},
            }

    def generate_html_report(self, output_path: str):
        """
        Gera relatório HTML de drift.

        Args:
            output_path: Caminho para salvar relatório HTML
        """
        if self.reference_data is None or not self.current_data:
            logger.warning("Cannot generate report without data")
            return

        try:
            from evidently.metric_preset import DataDriftPreset, DataQualityPreset
            from evidently.report import Report

            current_df = pd.DataFrame(self.current_data)

            report = Report(metrics=[DataDriftPreset(), DataQualityPreset()])

            report.run(reference_data=self.reference_data, current_data=current_df)

            report.save_html(output_path)
            logger.info("HTML report generated", path=output_path)

        except Exception as e:
            logger.error("Failed to generate HTML report", error=str(e))

    def clear_current_data(self):
        """Limpa dados atuais após detecção de drift."""
        self.current_data = []
        logger.debug("Current data cleared")

    def update_reference_data(self, new_reference: pd.DataFrame):
        """
        Atualiza dataset de referência.

        Args:
            new_reference: Novo DataFrame de referência
        """
        self.reference_data = new_reference
        logger.info("Reference data updated", shape=new_reference.shape)

    def get_drift_score(self, reference_data: list[float], current_data: list[float]) -> float:
        """
        Calcula PSI (Population Stability Index) entre duas distribuições.

        Args:
            reference_data: Dados de referência
            current_data: Dados atuais

        Returns:
            Score de drift entre 0 e 1 (0 = sem drift, 1 = drift máximo)
        """
        if not reference_data or not current_data:
            return 0.0

        try:
            # Converter para arrays numpy
            ref = np.array(reference_data)
            curr = np.array(current_data)

            # Criar bins baseados nos dados de referência
            # Usar Sturges rule para número de bins
            n_bins = max(5, int(np.log2(len(ref)) + 1))

            # Calcular histogramas
            ref_hist, ref_edges = np.histogram(ref, bins=n_bins, density=True)
            curr_hist, _ = np.histogram(curr, bins=ref_edges, density=True)

            # Evitar divisão por zero
            ref_hist = np.where(ref_hist == 0, 1e-10, ref_hist)
            curr_hist = np.where(curr_hist == 0, 1e-10, curr_hist)

            # Calcular PSI
            psi = np.sum((ref_hist - curr_hist) * np.log(ref_hist / curr_hist))

            # Normalizar para 0-1 (PSI > 1 é considerado drift severo)
            drift_score = min(psi / 2.0, 1.0)

            logger.debug(
                "Drift score calculated",
                psi=psi,
                drift_score=drift_score,
                n_bins=n_bins,
            )

            return drift_score

        except Exception as e:
            logger.error("Failed to calculate drift score", error=str(e))
            return 0.0
