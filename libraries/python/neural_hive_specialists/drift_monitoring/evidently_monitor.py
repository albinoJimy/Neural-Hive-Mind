"""
EvidentlyMonitor: Integração com Evidently AI para detecção de drift.

Monitora distribuição de features ao longo do tempo e detecta desvios
significativos em relação ao dataset de referência.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger(__name__)


class EvidentlyMonitor:
    """Monitor de drift usando Evidently AI."""

    def __init__(self, config: Dict[str, Any]):
        """
        Inicializa monitor de drift.

        Args:
            config: Configuração com reference_dataset_path, threshold_psi, etc.
        """
        self.config = config
        self.reference_data: Optional[pd.DataFrame] = None
        self.current_data: List[Dict[str, Any]] = []
        self._load_reference_data()

        logger.info("EvidentlyMonitor initialized", config=config)

    def _load_reference_data(self):
        """Carrega dataset de referência."""
        reference_path = self.config.get('drift_reference_dataset_path')

        if reference_path:
            try:
                self.reference_data = pd.read_parquet(reference_path)
                logger.info(
                    "Reference dataset loaded",
                    path=reference_path,
                    shape=self.reference_data.shape
                )
            except Exception as e:
                logger.error(
                    "Failed to load reference dataset",
                    path=reference_path,
                    error=str(e)
                )
                self.reference_data = None
        else:
            logger.warning("No reference dataset configured")

    def log_features(self, features: Dict[str, Any], timestamp: Optional[datetime] = None):
        """
        Registra features de uma avaliação.

        Args:
            features: Dicionário de features extraídas
            timestamp: Timestamp da avaliação (usa now() se None)
        """
        record = {
            'timestamp': timestamp or datetime.utcnow(),
            **features
        }
        self.current_data.append(record)

        logger.debug("Features logged", num_features=len(features))

    def detect_drift(self) -> Dict[str, Any]:
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
                'drift_detected': False,
                'drift_score': 0.0,
                'drifted_features': [],
                'report': {'error': 'No reference data'}
            }

        if not self.current_data:
            logger.warning("No current data to compare")
            return {
                'drift_detected': False,
                'drift_score': 0.0,
                'drifted_features': [],
                'report': {'error': 'No current data'}
            }

        try:
            # Converter current_data para DataFrame
            current_df = pd.DataFrame(self.current_data)

            # Usar Evidently para detectar drift
            from evidently.report import Report
            from evidently.metric_preset import DataDriftPreset

            report = Report(metrics=[
                DataDriftPreset()
            ])

            report.run(
                reference_data=self.reference_data,
                current_data=current_df,
                column_mapping=None
            )

            # Extrair resultados
            report_dict = report.as_dict()
            metrics = report_dict.get('metrics', [])

            drift_detected = False
            drift_score = 0.0
            drifted_features = []

            for metric in metrics:
                if metric.get('metric') == 'DatasetDriftMetric':
                    result = metric.get('result', {})
                    drift_detected = result.get('dataset_drift', False)
                    drift_score = result.get('drift_share', 0.0)

                    # Identificar features com drift
                    drift_by_columns = result.get('drift_by_columns', {})
                    for col, col_result in drift_by_columns.items():
                        if col_result.get('drift_detected', False):
                            drifted_features.append(col)

            logger.info(
                "Drift detection completed",
                drift_detected=drift_detected,
                drift_score=drift_score,
                num_drifted_features=len(drifted_features)
            )

            return {
                'drift_detected': drift_detected,
                'drift_score': drift_score,
                'drifted_features': drifted_features,
                'report': report_dict,
                'timestamp': datetime.utcnow().isoformat()
            }

        except ImportError:
            logger.error("Evidently not installed. Install with: pip install evidently")
            return {
                'drift_detected': False,
                'drift_score': 0.0,
                'drifted_features': [],
                'report': {'error': 'Evidently not installed'}
            }
        except Exception as e:
            logger.error("Drift detection failed", error=str(e), exc_info=True)
            return {
                'drift_detected': False,
                'drift_score': 0.0,
                'drifted_features': [],
                'report': {'error': str(e)}
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
            from evidently.report import Report
            from evidently.metric_preset import DataDriftPreset, DataQualityPreset

            current_df = pd.DataFrame(self.current_data)

            report = Report(metrics=[
                DataDriftPreset(),
                DataQualityPreset()
            ])

            report.run(
                reference_data=self.reference_data,
                current_data=current_df
            )

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
        logger.info(
            "Reference data updated",
            shape=new_reference.shape
        )
