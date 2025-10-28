"""
DriftDetector: Orquestra detecção de drift e dispara alertas.

Executa verificações periódicas de drift e persiste resultados no MongoDB.
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

from .evidently_monitor import EvidentlyMonitor
from .drift_alerts import DriftAlerter

logger = structlog.get_logger(__name__)


class DriftDetector:
    """Detector de drift com verificação periódica."""

    def __init__(
        self,
        config: Dict[str, Any],
        evidently_monitor: EvidentlyMonitor,
        drift_alerter: DriftAlerter,
        ledger_client: Any
    ):
        """
        Inicializa detector de drift.

        Args:
            config: Configuração (window_hours, threshold_psi)
            evidently_monitor: Monitor Evidently
            drift_alerter: Alerter de drift
            ledger_client: Cliente do ledger para persistência
        """
        self.config = config
        self.evidently_monitor = evidently_monitor
        self.drift_alerter = drift_alerter
        self.ledger_client = ledger_client

        self.window_hours = config.get('drift_detection_window_hours', 24)
        self.threshold_psi = config.get('drift_threshold_psi', 0.2)
        self.check_interval_minutes = config.get('drift_check_interval_minutes', 60)

        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(
            "DriftDetector initialized",
            window_hours=self.window_hours,
            threshold_psi=self.threshold_psi
        )

    async def start_monitoring(self):
        """Inicia monitoramento periódico de drift."""
        if self._running:
            logger.warning("Drift monitoring already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("Drift monitoring started")

    async def stop_monitoring(self):
        """Para monitoramento de drift."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Drift monitoring stopped")

    async def _monitoring_loop(self):
        """Loop de monitoramento periódico."""
        while self._running:
            try:
                await self.check_drift()
                await asyncio.sleep(self.check_interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in drift monitoring loop",
                    error=str(e),
                    exc_info=True
                )
                await asyncio.sleep(60)  # Retry após 1 minuto

    async def check_drift(self) -> Dict[str, Any]:
        """
        Executa verificação de drift.

        Returns:
            Resultado da detecção de drift
        """
        logger.info("Starting drift check")

        try:
            # Detectar drift
            drift_result = self.evidently_monitor.detect_drift()

            # Persistir resultado
            await self._persist_drift_result(drift_result)

            # Verificar se drift excede threshold
            if drift_result['drift_detected']:
                drift_score = drift_result['drift_score']

                if drift_score > self.threshold_psi:
                    logger.warning(
                        "Drift threshold exceeded",
                        drift_score=drift_score,
                        threshold=self.threshold_psi,
                        drifted_features=drift_result['drifted_features']
                    )

                    # Disparar alerta
                    await self.drift_alerter.send_alert(
                        drift_score=drift_score,
                        drifted_features=drift_result['drifted_features'],
                        report=drift_result['report']
                    )

            # Limpar dados atuais após verificação
            self.evidently_monitor.clear_current_data()

            return drift_result

        except Exception as e:
            logger.error("Drift check failed", error=str(e), exc_info=True)
            return {
                'drift_detected': False,
                'drift_score': 0.0,
                'error': str(e)
            }

    async def _persist_drift_result(self, drift_result: Dict[str, Any]):
        """Persiste resultado de drift no ledger."""
        try:
            document = {
                'type': 'drift_detection',
                'timestamp': datetime.utcnow(),
                'drift_detected': drift_result['drift_detected'],
                'drift_score': drift_result['drift_score'],
                'drifted_features': drift_result['drifted_features'],
                'threshold_psi': self.threshold_psi,
                'window_hours': self.window_hours,
                'report_summary': {
                    'num_drifted_features': len(drift_result['drifted_features']),
                    'timestamp': drift_result.get('timestamp')
                }
            }

            # Salvar no MongoDB
            collection = self.ledger_client.db['drift_monitoring']
            await collection.insert_one(document)

            logger.debug("Drift result persisted", drift_detected=drift_result['drift_detected'])

        except Exception as e:
            logger.error("Failed to persist drift result", error=str(e))

    def log_evaluation_features(self, features: Dict[str, Any]):
        """
        Registra features de uma avaliação para monitoramento.

        Args:
            features: Features extraídas da avaliação
        """
        self.evidently_monitor.log_features(features)
