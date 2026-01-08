"""
Validador Contínuo para Modelos ML.

Compara predições com outcomes reais em tempo real,
calcula métricas de acurácia com janela deslizante,
e dispara alertas quando acurácia cai abaixo do threshold.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from collections import deque
from dataclasses import dataclass, field
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ValidationWindow:
    """Janela de validação com métricas agregadas."""
    window_name: str
    window_hours: int
    predictions: deque = field(default_factory=lambda: deque(maxlen=10000))
    actuals: deque = field(default_factory=lambda: deque(maxlen=10000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=10000))

    def add_pair(
        self,
        prediction: float,
        actual: float,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Adiciona par predição/actual à janela."""
        ts = timestamp or datetime.utcnow()
        self.predictions.append(prediction)
        self.actuals.append(actual)
        self.timestamps.append(ts)

    def get_valid_pairs(self) -> Tuple[np.ndarray, np.ndarray]:
        """Retorna pares válidos dentro da janela de tempo."""
        cutoff = datetime.utcnow() - timedelta(hours=self.window_hours)

        valid_preds = []
        valid_actuals = []

        for pred, actual, ts in zip(self.predictions, self.actuals, self.timestamps):
            if ts >= cutoff:
                valid_preds.append(pred)
                valid_actuals.append(actual)

        return np.array(valid_preds), np.array(valid_actuals)

    def compute_metrics(self) -> Dict[str, float]:
        """Calcula métricas para a janela."""
        preds, actuals = self.get_valid_pairs()

        if len(preds) < 10:
            return {
                'mae': None,
                'mape': None,
                'rmse': None,
                'sample_count': len(preds),
                'sufficient_data': False
            }

        errors = np.abs(preds - actuals)
        mae = np.mean(errors)

        # MAPE com proteção contra divisão por zero
        non_zero_mask = actuals > 0
        if non_zero_mask.sum() > 0:
            mape = np.mean(errors[non_zero_mask] / actuals[non_zero_mask]) * 100
        else:
            mape = None

        rmse = np.sqrt(np.mean(errors ** 2))

        # MAE percentual relativo à média
        mean_actual = np.mean(actuals)
        mae_pct = (mae / mean_actual * 100) if mean_actual > 0 else None

        return {
            'mae': float(mae),
            'mae_pct': mae_pct,
            'mape': float(mape) if mape is not None else None,
            'rmse': float(rmse),
            'mean_actual': float(mean_actual),
            'mean_prediction': float(np.mean(preds)),
            'sample_count': len(preds),
            'sufficient_data': True
        }


@dataclass
class ValidationAlert:
    """Alerta de validação."""
    alert_type: str
    severity: str
    message: str
    metrics: Dict[str, Any]
    window: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'alert_type': self.alert_type,
            'severity': self.severity,
            'message': self.message,
            'metrics': self.metrics,
            'window': self.window,
            'timestamp': self.timestamp.isoformat()
        }


class ContinuousValidator:
    """
    Validador contínuo para modelos ML.

    Funcionalidades:
    - Validação online: compara predições com outcomes reais
    - Métricas com janela deslizante (24h, 7d)
    - Alertas quando acurácia cai abaixo do threshold
    - Armazenamento de resultados para análise
    """

    def __init__(
        self,
        config,
        mongodb_client=None,
        clickhouse_client=None,
        metrics=None,
        alert_handlers: Optional[List] = None
    ):
        """
        Args:
            config: Configuração do orchestrator
            mongodb_client: Cliente MongoDB (opcional)
            clickhouse_client: Cliente ClickHouse (opcional)
            metrics: OrchestratorMetrics (opcional)
            alert_handlers: Handlers de alerta (opcional)
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.clickhouse_client = clickhouse_client
        self.metrics = metrics
        self.alert_handlers = alert_handlers or []
        self.logger = logger.bind(component="continuous_validator")

        # Thresholds de configuração
        self.mae_threshold_pct = getattr(config, 'ml_validation_mae_threshold', 0.15) * 100
        self.alert_cooldown_minutes = getattr(config, 'ml_alert_cooldown_minutes', 30)

        # Janelas de validação
        self.windows: Dict[str, ValidationWindow] = {
            '24h': ValidationWindow(window_name='24h', window_hours=24),
            '7d': ValidationWindow(window_name='7d', window_hours=168)
        }

        # Buffer de predições pendentes (aguardando outcome)
        self._pending_predictions: Dict[str, Dict[str, Any]] = {}
        self._pending_ttl_hours = 24

        # Cache de alertas para cooldown
        self._alert_cache: Dict[str, datetime] = {}

        # Task de validação
        self._validation_task: Optional[asyncio.Task] = None
        self._stop_validation = False

        # Histórico de métricas
        self._metrics_history: deque = deque(maxlen=1000)

    def record_prediction(
        self,
        ticket_id: str,
        predicted_duration_ms: float,
        model_version: str = 'unknown',
        features: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Registra uma predição para validação posterior.

        Args:
            ticket_id: ID do ticket
            predicted_duration_ms: Duração predita em ms
            model_version: Versão do modelo
            features: Features usadas (opcional)
        """
        self._pending_predictions[ticket_id] = {
            'predicted_duration_ms': predicted_duration_ms,
            'model_version': model_version,
            'features': features,
            'timestamp': datetime.utcnow()
        }

        # Limpar predições antigas
        self._cleanup_pending_predictions()

    def record_actual(
        self,
        ticket_id: str,
        actual_duration_ms: float
    ) -> Optional[Dict[str, Any]]:
        """
        Registra outcome real e calcula erro.

        Args:
            ticket_id: ID do ticket
            actual_duration_ms: Duração real em ms

        Returns:
            Resultado da validação ou None se não houver predição
        """
        if ticket_id not in self._pending_predictions:
            return None

        prediction_data = self._pending_predictions.pop(ticket_id)
        predicted = prediction_data['predicted_duration_ms']

        # Adicionar às janelas
        for window in self.windows.values():
            window.add_pair(predicted, actual_duration_ms)

        # Calcular erro
        error = abs(predicted - actual_duration_ms)
        error_pct = (error / actual_duration_ms * 100) if actual_duration_ms > 0 else 0

        result = {
            'ticket_id': ticket_id,
            'predicted_duration_ms': predicted,
            'actual_duration_ms': actual_duration_ms,
            'error_ms': error,
            'error_pct': error_pct,
            'model_version': prediction_data['model_version'],
            'prediction_timestamp': prediction_data['timestamp'].isoformat(),
            'validation_timestamp': datetime.utcnow().isoformat()
        }

        # Registrar métricas
        if self.metrics:
            self.metrics.record_prediction_error(
                model_name='duration-predictor',
                error_ms=error,
                error_pct=error_pct
            )

        return result

    async def start_continuous_validation(
        self,
        check_interval_seconds: int = 300
    ) -> None:
        """
        Inicia validação contínua em background.

        Args:
            check_interval_seconds: Intervalo entre checks (default: 5 min)
        """
        if self._validation_task and not self._validation_task.done():
            self.logger.warning("validation_already_running")
            return

        self._stop_validation = False
        self._validation_task = asyncio.create_task(
            self._validation_loop(check_interval_seconds)
        )

        self.logger.info(
            "continuous_validation_started",
            interval_seconds=check_interval_seconds
        )

    async def stop_continuous_validation(self) -> None:
        """Para a validação contínua."""
        self._stop_validation = True

        if self._validation_task:
            self._validation_task.cancel()
            try:
                await self._validation_task
            except asyncio.CancelledError:
                pass

        self.logger.info("continuous_validation_stopped")

    async def _validation_loop(self, interval_seconds: int) -> None:
        """Loop principal de validação."""
        while not self._stop_validation:
            try:
                # Computar métricas para todas as janelas
                results = await self.compute_all_metrics()

                # Verificar thresholds e gerar alertas
                await self._check_thresholds(results)

                # Armazenar resultados
                await self._store_validation_results(results)

                # Atualizar métricas Prometheus
                self._update_prometheus_metrics(results)

            except Exception as e:
                self.logger.error("validation_loop_error", error=str(e))

            await asyncio.sleep(interval_seconds)

    async def compute_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Computa métricas para todas as janelas.

        Returns:
            Dict com métricas por janela
        """
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'model_name': 'duration-predictor',
            'windows': {}
        }

        for window_name, window in self.windows.items():
            metrics = window.compute_metrics()
            results['windows'][window_name] = metrics

        # Adicionar ao histórico
        self._metrics_history.append(results)

        return results

    async def _check_thresholds(self, results: Dict[str, Any]) -> None:
        """Verifica thresholds e gera alertas se necessário."""
        for window_name, metrics in results.get('windows', {}).items():
            if not metrics.get('sufficient_data'):
                continue

            mae_pct = metrics.get('mae_pct')
            if mae_pct is None:
                continue

            # Verificar threshold
            if mae_pct > self.mae_threshold_pct:
                await self._generate_alert(
                    alert_type='accuracy_degradation',
                    severity='warning' if mae_pct < self.mae_threshold_pct * 1.5 else 'critical',
                    message=f"MAE ({mae_pct:.1f}%) excede threshold ({self.mae_threshold_pct:.1f}%) na janela {window_name}",
                    metrics=metrics,
                    window=window_name
                )

    async def _generate_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        metrics: Dict[str, Any],
        window: str
    ) -> None:
        """Gera e envia alerta de validação."""
        # Verificar cooldown
        alert_key = f"{alert_type}_{window}"
        if alert_key in self._alert_cache:
            last_alert = self._alert_cache[alert_key]
            cooldown = timedelta(minutes=self.alert_cooldown_minutes)
            if datetime.utcnow() - last_alert < cooldown:
                return

        alert = ValidationAlert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            metrics=metrics,
            window=window
        )

        # Atualizar cache
        self._alert_cache[alert_key] = datetime.utcnow()

        # Enviar para handlers
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

        # Armazenar alerta
        await self._store_alert(alert)

        self.logger.warning(
            "validation_alert_generated",
            alert_type=alert_type,
            severity=severity,
            window=window,
            message=message
        )

    async def _store_validation_results(self, results: Dict[str, Any]) -> None:
        """Armazena resultados de validação."""
        # MongoDB
        if self.mongodb_client:
            try:
                await self.mongodb_client.db['ml_validation_results'].insert_one(results)
            except Exception as e:
                self.logger.warning("mongodb_store_failed", error=str(e))

        # ClickHouse (para análise de longo prazo)
        if self.clickhouse_client:
            try:
                await self._store_to_clickhouse(results)
            except Exception as e:
                self.logger.warning("clickhouse_store_failed", error=str(e))

    async def _store_to_clickhouse(self, results: Dict[str, Any]) -> None:
        """Armazena resultados no ClickHouse."""
        if not self.clickhouse_client:
            return

        timestamp = results.get('timestamp', datetime.utcnow().isoformat())
        model_name = results.get('model_name', 'duration-predictor')

        rows = []
        for window_name, metrics in results.get('windows', {}).items():
            if not metrics.get('sufficient_data'):
                continue

            rows.append({
                'timestamp': timestamp,
                'model_name': model_name,
                'window': window_name,
                'mae': metrics.get('mae'),
                'mae_pct': metrics.get('mae_pct'),
                'mape': metrics.get('mape'),
                'rmse': metrics.get('rmse'),
                'sample_count': metrics.get('sample_count', 0)
            })

        if rows:
            # Insert via ClickHouse client
            pass  # Implementação depende do schema ClickHouse

    async def _store_alert(self, alert: ValidationAlert) -> None:
        """Armazena alerta no MongoDB."""
        if not self.mongodb_client:
            return

        try:
            await self.mongodb_client.db['ml_validation_alerts'].insert_one(
                alert.to_dict()
            )
        except Exception as e:
            self.logger.warning("alert_store_failed", error=str(e))

    def _update_prometheus_metrics(self, results: Dict[str, Any]) -> None:
        """Atualiza métricas Prometheus."""
        if not self.metrics:
            return

        try:
            for window_name, window_metrics in results.get('windows', {}).items():
                if not window_metrics.get('sufficient_data'):
                    continue

                mae = window_metrics.get('mae')
                if mae is not None:
                    self.metrics.record_validation_metric(
                        metric_name='mae',
                        value=mae,
                        window=window_name,
                        model_name='duration-predictor'
                    )

                mae_pct = window_metrics.get('mae_pct')
                if mae_pct is not None:
                    self.metrics.record_validation_metric(
                        metric_name='mae_pct',
                        value=mae_pct,
                        window=window_name,
                        model_name='duration-predictor'
                    )

        except Exception as e:
            self.logger.warning("prometheus_update_failed", error=str(e))

    def _cleanup_pending_predictions(self) -> None:
        """Remove predições pendentes antigas."""
        cutoff = datetime.utcnow() - timedelta(hours=self._pending_ttl_hours)

        expired = [
            ticket_id
            for ticket_id, data in self._pending_predictions.items()
            if data['timestamp'] < cutoff
        ]

        for ticket_id in expired:
            del self._pending_predictions[ticket_id]

    def get_current_metrics(self) -> Dict[str, Any]:
        """Retorna métricas atuais de todas as janelas."""
        return {
            window_name: window.compute_metrics()
            for window_name, window in self.windows.items()
        }

    def get_validation_status(self) -> Dict[str, Any]:
        """Retorna status do validador."""
        return {
            'running': self._validation_task is not None and not self._validation_task.done(),
            'pending_predictions': len(self._pending_predictions),
            'windows': {
                name: {
                    'samples_in_window': len(window.predictions),
                    'metrics': window.compute_metrics()
                }
                for name, window in self.windows.items()
            },
            'alerts_in_cooldown': len(self._alert_cache),
            'handlers_registered': len(self.alert_handlers)
        }

    async def get_metrics_history(
        self,
        hours: int = 24,
        window: str = '24h'
    ) -> List[Dict[str, Any]]:
        """
        Recupera histórico de métricas.

        Args:
            hours: Janela de tempo em horas
            window: Nome da janela ('24h' ou '7d')

        Returns:
            Lista de métricas históricas
        """
        if not self.mongodb_client:
            # Retornar do cache local
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            return [
                entry
                for entry in self._metrics_history
                if datetime.fromisoformat(entry['timestamp']) >= cutoff
            ]

        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)

            results = await self.mongodb_client.db['ml_validation_results'].find({
                'timestamp': {'$gte': cutoff.isoformat()},
                f'windows.{window}.sufficient_data': True
            }).sort('timestamp', -1).to_list(1000)

            return results

        except Exception as e:
            self.logger.error("get_metrics_history_failed", error=str(e))
            return []

    def register_alert_handler(self, handler) -> None:
        """Registra handler de alerta."""
        self.alert_handlers.append(handler)
