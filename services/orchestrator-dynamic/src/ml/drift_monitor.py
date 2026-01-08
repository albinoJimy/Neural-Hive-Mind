"""
Monitor de Drift Contínuo para modelos ML.

Coleta predições e targets em tempo real, executa análise de drift
com janela deslizante, e dispara alertas quando drift detectado.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
from collections import deque
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class DriftSeverity(str, Enum):
    """Níveis de severidade de drift."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DriftAlert:
    """Representa um alerta de drift."""

    def __init__(
        self,
        drift_type: str,
        severity: DriftSeverity,
        message: str,
        metrics: Dict[str, Any],
        model_name: str = 'duration-predictor'
    ):
        self.drift_type = drift_type
        self.severity = severity
        self.message = message
        self.metrics = metrics
        self.model_name = model_name
        self.timestamp = datetime.utcnow()
        self.alert_id = f"drift_{drift_type}_{self.timestamp.strftime('%Y%m%d%H%M%S')}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'alert_id': self.alert_id,
            'drift_type': self.drift_type,
            'severity': self.severity.value,
            'message': self.message,
            'metrics': self.metrics,
            'model_name': self.model_name,
            'timestamp': self.timestamp.isoformat()
        }


class DriftMonitor:
    """
    Monitor contínuo de drift para modelos ML.

    Funcionalidades:
    - Coleta de predições e targets em tempo real
    - Análise de drift com janela deslizante (7 dias, 30 dias)
    - Detecção de drift por PSI, K-S test, e degradação de MAE
    - Geração de alertas com deduplicação
    - Integração com sistema de re-treinamento
    """

    def __init__(
        self,
        config,
        mongodb_client,
        drift_detector,
        metrics=None,
        alert_handlers=None
    ):
        """
        Args:
            config: Configuração do orchestrator
            mongodb_client: Cliente MongoDB
            drift_detector: DriftDetector instance
            metrics: OrchestratorMetrics
            alert_handlers: Lista de handlers de alerta
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.drift_detector = drift_detector
        self.metrics = metrics
        self.alert_handlers = alert_handlers or []
        self.logger = logger.bind(component="drift_monitor")

        # Configurações de threshold
        self.psi_threshold = getattr(config, 'ml_drift_psi_threshold', 0.25)
        self.mae_ratio_threshold = getattr(config, 'ml_drift_mae_ratio_threshold', 1.5)

        # Buffers para coleta em tempo real
        self._prediction_buffer: deque = deque(maxlen=10000)
        self._target_buffer: deque = deque(maxlen=10000)

        # Cache de alertas para deduplicação (TTL: 6 horas)
        self._alert_cache: Dict[str, datetime] = {}
        self._alert_ttl = timedelta(hours=6)

        # Task de monitoramento
        self._monitor_task: Optional[asyncio.Task] = None
        self._stop_monitor = False

        # Último check
        self._last_check_time: Optional[datetime] = None

    def record_prediction(
        self,
        ticket_id: str,
        predicted_duration_ms: float,
        confidence: float,
        features: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Registra uma predição para monitoramento de drift.

        Args:
            ticket_id: ID do ticket
            predicted_duration_ms: Duração predita em ms
            confidence: Score de confiança
            features: Features usadas (opcional)
        """
        self._prediction_buffer.append({
            'ticket_id': ticket_id,
            'predicted_duration_ms': predicted_duration_ms,
            'confidence': confidence,
            'features': features,
            'timestamp': datetime.utcnow()
        })

    def record_target(
        self,
        ticket_id: str,
        actual_duration_ms: float
    ) -> None:
        """
        Registra um target (duração real) para monitoramento.

        Args:
            ticket_id: ID do ticket
            actual_duration_ms: Duração real em ms
        """
        self._target_buffer.append({
            'ticket_id': ticket_id,
            'actual_duration_ms': actual_duration_ms,
            'timestamp': datetime.utcnow()
        })

    async def start_monitoring(
        self,
        check_interval_seconds: int = 3600
    ) -> None:
        """
        Inicia monitoramento contínuo de drift.

        Args:
            check_interval_seconds: Intervalo entre checks (default: 1 hora)
        """
        if self._monitor_task and not self._monitor_task.done():
            self.logger.warning("monitoring_already_running")
            return

        self._stop_monitor = False
        self._monitor_task = asyncio.create_task(
            self._monitoring_loop(check_interval_seconds)
        )

        self.logger.info(
            "drift_monitoring_started",
            interval_seconds=check_interval_seconds
        )

    async def stop_monitoring(self) -> None:
        """Para o monitoramento de drift."""
        self._stop_monitor = True

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        self.logger.info("drift_monitoring_stopped")

    async def _monitoring_loop(self, interval_seconds: int) -> None:
        """Loop principal de monitoramento."""
        while not self._stop_monitor:
            try:
                # Executar check de drift
                report = await self.run_drift_analysis()

                # Processar alertas
                await self._process_drift_report(report)

                # Atualizar métricas
                self._update_monitoring_metrics(report)

                self._last_check_time = datetime.utcnow()

            except Exception as e:
                self.logger.error("monitoring_loop_error", error=str(e))

            # Aguardar próximo ciclo
            await asyncio.sleep(interval_seconds)

    async def run_drift_analysis(
        self,
        window_7d: bool = True,
        window_30d: bool = True
    ) -> Dict[str, Any]:
        """
        Executa análise completa de drift.

        Args:
            window_7d: Analisar janela de 7 dias
            window_30d: Analisar janela de 30 dias

        Returns:
            Relatório consolidado de drift
        """
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'model_name': 'duration-predictor',
            'windows': {}
        }

        # Janela de 7 dias
        if window_7d:
            report['windows']['7d'] = self.drift_detector.run_drift_check()
            report['windows']['7d']['window_days'] = 7

        # Janela de 30 dias (drift mais lento)
        if window_30d:
            try:
                feature_drift_30d = self.drift_detector.detect_feature_drift(30)
                prediction_drift_30d = self.drift_detector.detect_prediction_drift(30)
                target_drift_30d = self.drift_detector.detect_target_drift(30)

                overall_status_30d = self.drift_detector._determine_overall_status(
                    feature_drift_30d,
                    prediction_drift_30d,
                    target_drift_30d
                )

                report['windows']['30d'] = {
                    'window_days': 30,
                    'feature_drift': feature_drift_30d,
                    'prediction_drift': prediction_drift_30d,
                    'target_drift': target_drift_30d,
                    'overall_status': overall_status_30d
                }

            except Exception as e:
                self.logger.warning("30d_drift_analysis_failed", error=str(e))

        # Determinar status consolidado
        report['consolidated_status'] = self._determine_consolidated_status(report)
        report['severity'] = self._determine_severity(report)

        # Armazenar relatório
        await self._store_drift_report(report)

        self.logger.info(
            "drift_analysis_completed",
            consolidated_status=report['consolidated_status'],
            severity=report['severity']
        )

        return report

    def _determine_consolidated_status(self, report: Dict[str, Any]) -> str:
        """Determina status consolidado de todas as janelas."""
        statuses = []

        for window, data in report.get('windows', {}).items():
            status = data.get('overall_status', 'ok')
            statuses.append(status)

        # Usar pior status
        if 'critical' in statuses:
            return 'critical'
        elif 'warning' in statuses:
            return 'warning'
        return 'ok'

    def _determine_severity(self, report: Dict[str, Any]) -> str:
        """Determina severidade baseada no relatório."""
        consolidated = report.get('consolidated_status', 'ok')

        if consolidated == 'critical':
            return DriftSeverity.CRITICAL.value
        elif consolidated == 'warning':
            # Verificar se há drift em múltiplas janelas
            windows_with_warning = sum(
                1 for w in report.get('windows', {}).values()
                if w.get('overall_status') in ['warning', 'critical']
            )
            if windows_with_warning > 1:
                return DriftSeverity.HIGH.value
            return DriftSeverity.MEDIUM.value

        return DriftSeverity.LOW.value

    async def _process_drift_report(self, report: Dict[str, Any]) -> None:
        """Processa relatório de drift e gera alertas se necessário."""
        severity = DriftSeverity(report.get('severity', 'low'))

        if severity == DriftSeverity.LOW:
            return

        # Determinar tipo de drift principal
        drift_types = []
        for window_name, window_data in report.get('windows', {}).items():
            # Feature drift
            feature_drift = window_data.get('feature_drift', {})
            drifted_features = [
                f for f, psi in feature_drift.items()
                if psi > self.psi_threshold
            ]
            if drifted_features:
                drift_types.append(('feature', drifted_features, window_name))

            # Prediction drift
            prediction_drift = window_data.get('prediction_drift', {})
            drift_ratio = prediction_drift.get('drift_ratio', 0)
            if drift_ratio > self.mae_ratio_threshold:
                drift_types.append(('prediction', drift_ratio, window_name))

            # Target drift
            target_drift = window_data.get('target_drift', {})
            p_value = target_drift.get('p_value')
            if p_value is not None and p_value < 0.05:
                drift_types.append(('target', p_value, window_name))

        # Gerar alertas
        for drift_type, drift_data, window in drift_types:
            await self._generate_alert(
                drift_type=drift_type,
                severity=severity,
                drift_data=drift_data,
                window=window,
                report=report
            )

    async def _generate_alert(
        self,
        drift_type: str,
        severity: DriftSeverity,
        drift_data: Any,
        window: str,
        report: Dict[str, Any]
    ) -> None:
        """Gera e envia alerta de drift."""
        # Deduplicação
        alert_key = f"{drift_type}_{window}"
        if alert_key in self._alert_cache:
            cached_time = self._alert_cache[alert_key]
            if datetime.utcnow() - cached_time < self._alert_ttl:
                self.logger.debug(
                    "alert_deduplicated",
                    alert_key=alert_key
                )
                return

        # Construir mensagem
        if drift_type == 'feature':
            message = f"Feature drift detectado em {len(drift_data)} features ({window})"
            metrics = {'drifted_features': drift_data}
        elif drift_type == 'prediction':
            message = f"Degradação de acurácia de {(drift_data - 1) * 100:.1f}% ({window})"
            metrics = {'drift_ratio': drift_data}
        else:
            message = f"Target drift detectado (p-value: {drift_data:.4f}) ({window})"
            metrics = {'p_value': drift_data}

        alert = DriftAlert(
            drift_type=drift_type,
            severity=severity,
            message=message,
            metrics=metrics
        )

        # Atualizar cache
        self._alert_cache[alert_key] = datetime.utcnow()

        # Enviar para handlers
        await self._send_alert(alert)

        # Armazenar no MongoDB
        await self._store_alert(alert)

        self.logger.warning(
            "drift_alert_generated",
            alert_id=alert.alert_id,
            drift_type=drift_type,
            severity=severity.value,
            message=message
        )

    async def _send_alert(self, alert: DriftAlert) -> None:
        """Envia alerta para handlers registrados."""
        for handler in self.alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                self.logger.error(
                    "alert_handler_failed",
                    handler=str(handler),
                    error=str(e)
                )

    async def _store_alert(self, alert: DriftAlert) -> None:
        """Armazena alerta no MongoDB."""
        try:
            await self.mongodb_client.db['ml_drift_alerts'].insert_one(
                alert.to_dict()
            )
        except Exception as e:
            self.logger.warning("failed_to_store_alert", error=str(e))

    async def _store_drift_report(self, report: Dict[str, Any]) -> None:
        """Armazena relatório de drift no MongoDB."""
        try:
            await self.mongodb_client.db['ml_drift_reports'].insert_one(report)
        except Exception as e:
            self.logger.warning("failed_to_store_drift_report", error=str(e))

    def _update_monitoring_metrics(self, report: Dict[str, Any]) -> None:
        """Atualiza métricas Prometheus."""
        if not self.metrics:
            return

        try:
            # Status geral
            status_map = {'ok': 0, 'warning': 1, 'critical': 2}
            status_value = status_map.get(report.get('consolidated_status', 'ok'), 0)

            self.metrics.update_drift_status(
                model_name='duration-predictor',
                drift_type='consolidated',
                status=report.get('consolidated_status', 'ok')
            )

            # Drift scores por janela
            for window_name, window_data in report.get('windows', {}).items():
                # MAE drift ratio
                drift_ratio = window_data.get('prediction_drift', {}).get('drift_ratio')
                if drift_ratio is not None:
                    self.metrics.record_drift_score(
                        drift_type='prediction',
                        score=drift_ratio,
                        model_name='duration-predictor'
                    )

                # Feature drift (média)
                feature_drift = window_data.get('feature_drift', {})
                if feature_drift:
                    avg_psi = np.mean(list(feature_drift.values()))
                    self.metrics.record_drift_score(
                        drift_type='feature_avg',
                        score=avg_psi,
                        model_name='duration-predictor'
                    )

        except Exception as e:
            self.logger.warning("metrics_update_failed", error=str(e))

    async def get_drift_history(
        self,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Recupera histórico de drift.

        Args:
            days: Janela de tempo
            limit: Limite de registros

        Returns:
            Lista de relatórios de drift
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)

            reports = await self.mongodb_client.db['ml_drift_reports'].find({
                'timestamp': {'$gte': cutoff.isoformat()}
            }).sort('timestamp', -1).limit(limit).to_list(limit)

            return reports

        except Exception as e:
            self.logger.error("failed_to_get_drift_history", error=str(e))
            return []

    async def get_alert_history(
        self,
        days: int = 7,
        severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Recupera histórico de alertas.

        Args:
            days: Janela de tempo
            severity: Filtrar por severidade (opcional)

        Returns:
            Lista de alertas
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)

            query = {'timestamp': {'$gte': cutoff.isoformat()}}
            if severity:
                query['severity'] = severity

            alerts = await self.mongodb_client.db['ml_drift_alerts'].find(
                query
            ).sort('timestamp', -1).to_list(100)

            return alerts

        except Exception as e:
            self.logger.error("failed_to_get_alert_history", error=str(e))
            return []

    def register_alert_handler(self, handler) -> None:
        """Registra handler de alerta."""
        self.alert_handlers.append(handler)

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Retorna status atual do monitoramento."""
        return {
            'running': self._monitor_task is not None and not self._monitor_task.done(),
            'last_check': self._last_check_time.isoformat() if self._last_check_time else None,
            'predictions_buffered': len(self._prediction_buffer),
            'targets_buffered': len(self._target_buffer),
            'alerts_cached': len(self._alert_cache),
            'handlers_registered': len(self.alert_handlers)
        }
