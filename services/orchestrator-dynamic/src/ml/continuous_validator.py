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
from sklearn.metrics import r2_score
from motor.motor_asyncio import AsyncIOMotorClient

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
                'r2': None,
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

        # R² (coeficiente de determinação)
        try:
            r2 = r2_score(actuals, preds)
        except Exception:
            r2 = None

        # MAE percentual relativo à média
        mean_actual = np.mean(actuals)
        mae_pct = (mae / mean_actual * 100) if mean_actual > 0 else None

        return {
            'mae': float(mae),
            'mae_pct': mae_pct,
            'mape': float(mape) if mape is not None else None,
            'rmse': float(rmse),
            'r2': float(r2) if r2 is not None else None,
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


@dataclass
class LatencyWindow:
    """Janela de latência com percentiles."""
    window_name: str
    window_hours: int
    latencies: deque = field(default_factory=lambda: deque(maxlen=10000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=10000))
    errors: deque = field(default_factory=lambda: deque(maxlen=10000))

    def add_latency(
        self,
        latency_ms: float,
        had_error: bool = False,
        timestamp: Optional[datetime] = None
    ) -> None:
        """Adiciona latência à janela."""
        ts = timestamp or datetime.utcnow()
        self.latencies.append(latency_ms)
        self.errors.append(int(had_error))
        self.timestamps.append(ts)

    def get_valid_latencies(self) -> Tuple[np.ndarray, np.ndarray]:
        """Retorna latências válidas dentro da janela de tempo."""
        cutoff = datetime.utcnow() - timedelta(hours=self.window_hours)

        valid_latencies = []
        valid_errors = []

        for latency, error, ts in zip(self.latencies, self.errors, self.timestamps):
            if ts >= cutoff:
                valid_latencies.append(latency)
                valid_errors.append(error)

        return np.array(valid_latencies), np.array(valid_errors)

    def compute_metrics(self) -> Dict[str, float]:
        """Calcula métricas de latência."""
        latencies, errors = self.get_valid_latencies()

        if len(latencies) < 10:
            return {
                'p50': None,
                'p95': None,
                'p99': None,
                'mean': None,
                'error_rate': None,
                'sample_count': len(latencies),
                'sufficient_data': False
            }

        p50 = float(np.percentile(latencies, 50))
        p95 = float(np.percentile(latencies, 95))
        p99 = float(np.percentile(latencies, 99))
        mean = float(np.mean(latencies))
        error_rate = float(np.mean(errors))

        return {
            'p50': p50,
            'p95': p95,
            'p99': p99,
            'mean': mean,
            'error_rate': error_rate,
            'sample_count': len(latencies),
            'sufficient_data': True
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
        mongodb_client: Optional[AsyncIOMotorClient] = None,
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
        self.alert_cooldown_minutes = getattr(config, 'ml_validation_alert_cooldown_minutes', 30)
        self.use_mongodb = getattr(config, 'ml_validation_use_mongodb', True)
        self.mongodb_collection = getattr(config, 'ml_validation_mongodb_collection', 'model_predictions')

        # Janelas de validação configuráveis
        window_configs = getattr(config, 'ml_validation_windows', ['1h', '24h', '7d'])
        window_hours_map = {'1h': 1, '24h': 24, '7d': 168}

        self.windows: Dict[str, ValidationWindow] = {
            name: ValidationWindow(window_name=name, window_hours=window_hours_map.get(name, 24))
            for name in window_configs
        }

        # Janelas de latência (se habilitado)
        self.latency_enabled = getattr(config, 'ml_validation_latency_enabled', True)
        self.latency_windows: Dict[str, LatencyWindow] = {}
        if self.latency_enabled:
            self.latency_windows = {
                name: LatencyWindow(window_name=name, window_hours=window_hours_map.get(name, 24))
                for name in window_configs
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

        # Cache de baseline de treinamento
        self._training_baseline: Optional[Dict[str, Any]] = None
        self._baseline_cache_ttl_hours = 24
        self._baseline_last_fetched: Optional[datetime] = None

    def record_prediction(
        self,
        ticket_id: str,
        predicted_duration_ms: float,
        model_version: str = 'unknown',
        features: Optional[Dict[str, float]] = None,
        prediction_latency_ms: Optional[float] = None
    ) -> None:
        """
        Registra uma predição para validação posterior.

        Args:
            ticket_id: ID do ticket
            predicted_duration_ms: Duração predita em ms
            model_version: Versão do modelo
            features: Features usadas (opcional)
            prediction_latency_ms: Latência da predição em ms (opcional)
        """
        self._pending_predictions[ticket_id] = {
            'predicted_duration_ms': predicted_duration_ms,
            'model_version': model_version,
            'features': features,
            'prediction_latency_ms': prediction_latency_ms,
            'timestamp': datetime.utcnow()
        }

        # Limpar predições antigas
        self._cleanup_pending_predictions()

    async def record_actual(
        self,
        ticket_id: str,
        actual_duration_ms: float,
        had_error: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Registra outcome real e calcula erro.

        Args:
            ticket_id: ID do ticket
            actual_duration_ms: Duração real em ms
            had_error: Se houve erro na execução

        Returns:
            Resultado da validação ou None se não houver predição
        """
        if ticket_id not in self._pending_predictions:
            return None

        prediction_data = self._pending_predictions.pop(ticket_id)
        predicted = prediction_data['predicted_duration_ms']
        latency_ms = prediction_data.get('prediction_latency_ms')

        # Adicionar às janelas
        timestamp = datetime.utcnow()
        for window in self.windows.values():
            window.add_pair(predicted, actual_duration_ms, timestamp)

        # Adicionar latência se disponível
        if self.latency_enabled and latency_ms is not None:
            for latency_window in self.latency_windows.values():
                latency_window.add_latency(latency_ms, had_error, timestamp)

        # Calcular erro
        error = abs(predicted - actual_duration_ms)
        error_pct = (error / actual_duration_ms * 100) if actual_duration_ms > 0 else 0

        result = {
            'ticket_id': ticket_id,
            'model_name': 'duration-predictor',
            'predicted': predicted,
            'actual': actual_duration_ms,
            'error_ms': error,
            'error_pct': error_pct,
            'latency_ms': latency_ms,
            'had_error': had_error,
            'model_version': prediction_data['model_version'],
            'prediction_timestamp': prediction_data['timestamp'],
            'validation_timestamp': timestamp,
            'timestamp': timestamp
        }

        # Persistir no MongoDB
        if self.mongodb_client and self.use_mongodb:
            try:
                await self.mongodb_client.db[self.mongodb_collection].insert_one(result.copy())
            except Exception as e:
                self.logger.warning("mongodb_insert_failed", error=str(e))

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

        # Popular janelas do MongoDB antes de iniciar
        if self.use_mongodb and self.mongodb_client:
            await self.populate_windows_from_mongodb()

        self._stop_validation = False
        self._validation_task = asyncio.create_task(
            self._validation_loop(check_interval_seconds)
        )

        self.logger.info(
            "continuous_validation_started",
            interval_seconds=check_interval_seconds,
            use_mongodb=self.use_mongodb
        )

    async def _fetch_predictions_from_mongodb(
        self,
        model_name: str,
        window_hours: int
    ) -> List[Dict[str, Any]]:
        """
        Busca predições e actuals do MongoDB.

        Args:
            model_name: Nome do modelo
            window_hours: Janela de tempo em horas

        Returns:
            Lista de documentos com predicted, actual, latency_ms, had_error
        """
        if not self.mongodb_client or not self.use_mongodb:
            return []

        try:
            cutoff = datetime.utcnow() - timedelta(hours=window_hours)

            cursor = self.mongodb_client.db[self.mongodb_collection].find({
                'model_name': model_name,
                'timestamp': {'$gte': cutoff},
                'actual': {'$exists': True}  # Apenas predições com outcome conhecido
            }).sort('timestamp', -1).limit(10000)

            results = await cursor.to_list(length=10000)

            self.logger.debug(
                "mongodb_predictions_fetched",
                model_name=model_name,
                window_hours=window_hours,
                count=len(results)
            )

            return results

        except Exception as e:
            self.logger.warning(
                "mongodb_fetch_failed",
                model_name=model_name,
                error=str(e)
            )
            return []

    async def populate_windows_from_mongodb(
        self,
        model_name: str = 'duration-predictor'
    ) -> None:
        """
        Popula janelas de validação com dados do MongoDB.

        Args:
            model_name: Nome do modelo
        """
        if not self.use_mongodb or not self.mongodb_client:
            self.logger.info("mongodb_disabled_using_in_memory")
            return

        for window_name, window in self.windows.items():
            predictions = await self._fetch_predictions_from_mongodb(
                model_name=model_name,
                window_hours=window.window_hours
            )

            for pred_doc in predictions:
                try:
                    predicted = pred_doc.get('predicted')
                    actual = pred_doc.get('actual')
                    timestamp = pred_doc.get('timestamp')

                    if predicted is not None and actual is not None:
                        window.add_pair(predicted, actual, timestamp)

                    # Adicionar latência se disponível
                    if self.latency_enabled and window_name in self.latency_windows:
                        latency_ms = pred_doc.get('latency_ms')
                        had_error = pred_doc.get('had_error', False)

                        if latency_ms is not None:
                            self.latency_windows[window_name].add_latency(
                                latency_ms, had_error, timestamp
                            )

                except Exception as e:
                    self.logger.warning(
                        "populate_window_error",
                        window=window_name,
                        error=str(e)
                    )

            self.logger.info(
                "window_populated",
                window=window_name,
                samples=len(window.predictions)
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
            'windows': {},
            'latency_windows': {}
        }

        # Métricas de predição
        for window_name, window in self.windows.items():
            metrics = window.compute_metrics()
            results['windows'][window_name] = metrics

        # Métricas de latência
        if self.latency_enabled:
            for window_name, latency_window in self.latency_windows.items():
                latency_metrics = latency_window.compute_metrics()
                results['latency_windows'][window_name] = latency_metrics

        # Adicionar ao histórico
        self._metrics_history.append(results)

        return results

    async def _fetch_training_baseline(
        self,
        model_name: str = 'duration-predictor'
    ) -> Optional[Dict[str, Any]]:
        """
        Busca baseline de treinamento do MongoDB.

        Args:
            model_name: Nome do modelo

        Returns:
            Dict com métricas baseline (mae, rmse, mae_pct, r2) ou None
        """
        # Verificar cache
        if (
            self._training_baseline is not None and
            self._baseline_last_fetched is not None and
            datetime.utcnow() - self._baseline_last_fetched < timedelta(hours=self._baseline_cache_ttl_hours)
        ):
            return self._training_baseline

        if not self.mongodb_client or not self.use_mongodb:
            return None

        try:
            # Buscar baseline mais recente da coleção de histórico de treinamento
            baseline_doc = await self.mongodb_client.db['ml_training_history'].find_one(
                {
                    'model_name': model_name,
                    'status': 'completed',
                    'metrics': {'$exists': True}
                },
                sort=[('trained_at', -1)]
            )

            if baseline_doc and baseline_doc.get('metrics'):
                metrics = baseline_doc['metrics']
                self._training_baseline = {
                    'mae': metrics.get('mae'),
                    'rmse': metrics.get('rmse'),
                    'mae_pct': metrics.get('mae_pct'),
                    'r2': metrics.get('r2'),
                    'trained_at': baseline_doc.get('trained_at'),
                    'model_version': baseline_doc.get('model_version')
                }
                self._baseline_last_fetched = datetime.utcnow()

                self.logger.info(
                    "training_baseline_fetched",
                    model_name=model_name,
                    baseline_mae=self._training_baseline.get('mae'),
                    baseline_mae_pct=self._training_baseline.get('mae_pct'),
                    trained_at=str(self._training_baseline.get('trained_at'))
                )

                return self._training_baseline

            self.logger.warning(
                "training_baseline_not_found",
                model_name=model_name
            )
            return None

        except Exception as e:
            self.logger.warning(
                "training_baseline_fetch_failed",
                model_name=model_name,
                error=str(e)
            )
            return None

    async def _check_thresholds(self, results: Dict[str, Any]) -> None:
        """
        Verifica thresholds e gera alertas se necessário.

        Primeiro compara métricas atuais com baseline de treinamento.
        Usa threshold fixo como fallback se baseline não disponível.
        """
        # Buscar baseline de treinamento
        baseline = await self._fetch_training_baseline()

        for window_name, metrics in results.get('windows', {}).items():
            if not metrics.get('sufficient_data'):
                continue

            mae_pct = metrics.get('mae_pct')
            mae = metrics.get('mae')
            rmse = metrics.get('rmse')

            if mae_pct is None:
                continue

            # Comparar com baseline se disponível
            if baseline is not None:
                baseline_mae_pct = baseline.get('mae_pct')
                baseline_mae = baseline.get('mae')
                baseline_rmse = baseline.get('rmse')

                # Calcular degradação relativa ao baseline
                degradation_detected = False
                degradation_details = []

                # Verificar MAE percentual (principal métrica)
                if baseline_mae_pct is not None and baseline_mae_pct > 0:
                    mae_pct_ratio = mae_pct / baseline_mae_pct
                    # Alerta se MAE atual for 50% maior que baseline
                    if mae_pct_ratio > 1.5:
                        degradation_detected = True
                        degradation_details.append(
                            f"MAE% {mae_pct:.1f}% vs baseline {baseline_mae_pct:.1f}% (ratio: {mae_pct_ratio:.2f}x)"
                        )

                # Verificar MAE absoluto
                if baseline_mae is not None and mae is not None and baseline_mae > 0:
                    mae_ratio = mae / baseline_mae
                    if mae_ratio > 1.5:
                        degradation_detected = True
                        degradation_details.append(
                            f"MAE {mae:.2f}ms vs baseline {baseline_mae:.2f}ms (ratio: {mae_ratio:.2f}x)"
                        )

                # Verificar RMSE
                if baseline_rmse is not None and rmse is not None and baseline_rmse > 0:
                    rmse_ratio = rmse / baseline_rmse
                    if rmse_ratio > 1.5:
                        degradation_detected = True
                        degradation_details.append(
                            f"RMSE {rmse:.2f}ms vs baseline {baseline_rmse:.2f}ms (ratio: {rmse_ratio:.2f}x)"
                        )

                if degradation_detected:
                    # Determinar severidade com base no maior ratio
                    max_ratio = max([
                        (mae_pct / baseline_mae_pct) if baseline_mae_pct and baseline_mae_pct > 0 else 0,
                        (mae / baseline_mae) if baseline_mae and mae and baseline_mae > 0 else 0,
                        (rmse / baseline_rmse) if baseline_rmse and rmse and baseline_rmse > 0 else 0
                    ])
                    severity = 'critical' if max_ratio > 2.0 else 'warning'

                    await self._generate_alert(
                        alert_type='accuracy_degradation_vs_baseline',
                        severity=severity,
                        message=f"Degradação detectada vs baseline de treinamento na janela {window_name}: {'; '.join(degradation_details)}",
                        metrics={
                            **metrics,
                            'baseline_mae_pct': baseline_mae_pct,
                            'baseline_mae': baseline_mae,
                            'baseline_rmse': baseline_rmse,
                            'baseline_trained_at': str(baseline.get('trained_at')),
                            'degradation_details': degradation_details
                        },
                        window=window_name
                    )
                    continue  # Não verificar threshold fixo se baseline detectou problema

            # Fallback: verificar threshold fixo se baseline não disponível ou não detectou degradação
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
            # Métricas de predição
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

                r2 = window_metrics.get('r2')
                if r2 is not None:
                    self.metrics.record_validation_metric(
                        metric_name='r2',
                        value=r2,
                        window=window_name,
                        model_name='duration-predictor'
                    )

            # Métricas de latência
            if self.latency_enabled:
                for window_name, latency_metrics in results.get('latency_windows', {}).items():
                    if not latency_metrics.get('sufficient_data'):
                        continue

                    for metric_name in ['p50', 'p95', 'p99', 'error_rate']:
                        value = latency_metrics.get(metric_name)
                        if value is not None:
                            self.metrics.record_validation_metric(
                                metric_name=f'latency_{metric_name}',
                                value=value,
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

    async def get_current_metrics(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Retorna métricas atuais de todas as janelas.

        Se ml_validation_use_mongodb estiver ativo, recarrega dados do MongoDB
        para garantir que métricas reflitam o estado atual de model_predictions.

        Args:
            force_reload: Forçar recarga do MongoDB mesmo se não habilitado

        Returns:
            Dict com métricas de predição e latência por janela
        """
        # Recarregar do MongoDB se habilitado
        if (self.use_mongodb and self.mongodb_client) or force_reload:
            await self._reload_windows_from_mongodb()

        metrics = {
            'prediction_metrics': {
                window_name: window.compute_metrics()
                for window_name, window in self.windows.items()
            }
        }

        if self.latency_enabled:
            metrics['latency_metrics'] = {
                window_name: latency_window.compute_metrics()
                for window_name, latency_window in self.latency_windows.items()
            }

        return metrics

    async def _reload_windows_from_mongodb(
        self,
        model_name: str = 'duration-predictor'
    ) -> None:
        """
        Recarrega dados do MongoDB para todas as janelas.

        Limpa janelas antes de repopular para evitar duplicidades
        e garante que métricas reflitam model_predictions no momento da consulta.

        Args:
            model_name: Nome do modelo
        """
        if not self.mongodb_client or not self.use_mongodb:
            return

        # Limpar todas as janelas antes de repopular
        for window in self.windows.values():
            window.predictions.clear()
            window.actuals.clear()
            window.timestamps.clear()

        if self.latency_enabled:
            for latency_window in self.latency_windows.values():
                latency_window.latencies.clear()
                latency_window.errors.clear()
                latency_window.timestamps.clear()

        self.logger.debug(
            "windows_cleared_for_reload",
            model_name=model_name
        )

        # Repopular janelas do MongoDB
        await self.populate_windows_from_mongodb(model_name)

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
