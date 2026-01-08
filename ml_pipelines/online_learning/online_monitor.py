"""
Online Performance Monitor para Online Learning.

Monitoramento específico de modelos online incluindo convergência,
estabilidade de predições, uso de memória e alertas proativos.
"""

import os
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import structlog
import numpy as np
from prometheus_client import Counter, Histogram, Gauge, Info
from pymongo import MongoClient, DESCENDING

from .config import OnlineLearningConfig
from .incremental_learner import IncrementalLearner

logger = structlog.get_logger(__name__)

# Métricas Prometheus
online_convergence_stall = Gauge(
    'neural_hive_online_convergence_stall',
    'Indicador de convergence stall (1=stall detectado)',
    ['specialist_type']
)
online_memory_usage_mb = Gauge(
    'neural_hive_online_memory_usage_mb',
    'Uso de memória do processo em MB',
    ['specialist_type']
)
online_model_size_mb = Gauge(
    'neural_hive_online_model_size_mb',
    'Tamanho do modelo online em MB',
    ['specialist_type']
)
online_prediction_variance = Gauge(
    'neural_hive_online_prediction_variance',
    'Variância de predições entre updates',
    ['specialist_type']
)
online_update_frequency = Gauge(
    'neural_hive_online_update_frequency_per_hour',
    'Frequência de updates por hora',
    ['specialist_type']
)
online_alert_triggered = Counter(
    'neural_hive_online_alert_triggered_total',
    'Total de alertas disparados',
    ['specialist_type', 'alert_type']
)


class Alert:
    """Representa um alerta gerado pelo monitor."""

    def __init__(
        self,
        alert_type: str,
        severity: str,
        message: str,
        specialist_type: str,
        metrics: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ):
        self.alert_type = alert_type
        self.severity = severity  # info, warning, critical
        self.message = message
        self.specialist_type = specialist_type
        self.metrics = metrics
        self.timestamp = timestamp or datetime.utcnow()
        self.acknowledged = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'alert_type': self.alert_type,
            'severity': self.severity,
            'message': self.message,
            'specialist_type': self.specialist_type,
            'metrics': self.metrics,
            'timestamp': self.timestamp.isoformat(),
            'acknowledged': self.acknowledged
        }


class OnlinePerformanceMonitor:
    """
    Monitora performance de modelos online.

    Métricas monitoradas:
    - Update frequency (updates/hora)
    - Convergence rate (redução de loss por update)
    - Prediction stability (variância entre updates)
    - Memory usage (crescimento de tamanho do modelo)

    Alertas:
    - Convergence stall: sem redução de loss por período
    - Memory leak: crescimento anormal de memória
    - Accuracy drop: queda de accuracy detectada
    - High latency: latência acima do threshold
    """

    ALERT_TYPES = [
        'convergence_stall',
        'memory_leak',
        'accuracy_drop',
        'high_latency',
        'prediction_instability',
        'update_frequency_low'
    ]

    def __init__(
        self,
        config: OnlineLearningConfig,
        specialist_type: str,
        learner: Optional[IncrementalLearner] = None
    ):
        """
        Inicializa OnlinePerformanceMonitor.

        Args:
            config: Configuração de online learning
            specialist_type: Tipo do especialista
            learner: IncrementalLearner a monitorar (opcional)
        """
        self.config = config
        self.specialist_type = specialist_type
        self.learner = learner

        # MongoDB para histórico
        self._client = MongoClient(config.mongodb_uri)
        self._db = self._client[config.mongodb_database]
        self._metrics_collection = self._db['online_learning_metrics']
        self._alerts_collection = self._db['online_learning_alerts']

        # Criar índices
        self._create_indexes()

        # Estado interno
        self._update_timestamps: List[datetime] = []
        self._loss_history: List[Tuple[datetime, float]] = []
        self._memory_history: List[Tuple[datetime, float]] = []
        self._prediction_samples: List[np.ndarray] = []
        self._active_alerts: List[Alert] = []
        self._initial_memory_mb: Optional[float] = None

        # Métricas baseline
        self._baseline_latency_ms: Optional[float] = None
        self._baseline_accuracy: Optional[float] = None

        logger.info(
            "online_monitor_initialized",
            specialist_type=specialist_type,
            convergence_stall_hours=config.convergence_stall_threshold_hours,
            memory_leak_threshold_mb=config.memory_leak_threshold_mb
        )

    def _create_indexes(self):
        """Cria índices no MongoDB."""
        try:
            self._metrics_collection.create_index([
                ('specialist_type', 1),
                ('timestamp', -1)
            ])
            self._alerts_collection.create_index([
                ('specialist_type', 1),
                ('timestamp', -1)
            ])
        except Exception as e:
            logger.warning("failed_to_create_indexes", error=str(e))

    def set_learner(self, learner: IncrementalLearner):
        """Define o learner a ser monitorado."""
        self.learner = learner

    def set_baseline(
        self,
        latency_ms: Optional[float] = None,
        accuracy: Optional[float] = None
    ):
        """Define métricas baseline para comparação."""
        if latency_ms is not None:
            self._baseline_latency_ms = latency_ms
        if accuracy is not None:
            self._baseline_accuracy = accuracy

        logger.info(
            "baseline_metrics_set",
            specialist_type=self.specialist_type,
            latency_ms=self._baseline_latency_ms,
            accuracy=self._baseline_accuracy
        )

    def record_update(
        self,
        loss: float,
        duration_ms: float,
        samples_count: int
    ):
        """
        Registra uma atualização de modelo.

        Args:
            loss: Loss após update
            duration_ms: Duração do update em ms
            samples_count: Número de amostras no batch
        """
        now = datetime.utcnow()

        # Atualizar históricos
        self._update_timestamps.append(now)
        self._loss_history.append((now, loss))

        # Limitar tamanho dos históricos
        max_history = 1000
        if len(self._update_timestamps) > max_history:
            self._update_timestamps = self._update_timestamps[-max_history:]
        if len(self._loss_history) > max_history:
            self._loss_history = self._loss_history[-max_history:]

        # Registrar uso de memória
        memory_mb = self._get_memory_usage_mb()
        self._memory_history.append((now, memory_mb))
        if len(self._memory_history) > max_history:
            self._memory_history = self._memory_history[-max_history:]

        if self._initial_memory_mb is None:
            self._initial_memory_mb = memory_mb

        # Persistir métricas
        metric_doc = {
            'specialist_type': self.specialist_type,
            'timestamp': now,
            'loss': loss,
            'duration_ms': duration_ms,
            'samples_count': samples_count,
            'memory_mb': memory_mb,
            'update_count': len(self._update_timestamps)
        }

        try:
            self._metrics_collection.insert_one(metric_doc)
        except Exception as e:
            logger.warning("failed_to_persist_metric", error=str(e))

        # Atualizar métricas Prometheus
        self._update_prometheus_metrics()

        # Verificar alertas
        self._check_alerts()

    def record_prediction(self, probas: np.ndarray):
        """
        Registra predições para análise de estabilidade.

        Args:
            probas: Probabilidades preditas
        """
        self._prediction_samples.append(probas.copy())

        # Limitar amostras
        if len(self._prediction_samples) > 100:
            self._prediction_samples = self._prediction_samples[-100:]

    def _get_memory_usage_mb(self) -> float:
        """Retorna uso de memória do processo em MB."""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    def _get_model_size_mb(self) -> float:
        """Estima tamanho do modelo em MB."""
        if self.learner is None or not self.learner.is_fitted:
            return 0.0

        try:
            import pickle
            model_bytes = len(pickle.dumps(self.learner.model))
            scaler_bytes = len(pickle.dumps(self.learner._scaler))
            return (model_bytes + scaler_bytes) / (1024 * 1024)
        except Exception:
            return 0.0

    def _calculate_update_frequency(self) -> float:
        """Calcula frequência de updates por hora."""
        if len(self._update_timestamps) < 2:
            return 0.0

        # Considerar última hora
        cutoff = datetime.utcnow() - timedelta(hours=1)
        recent = [t for t in self._update_timestamps if t > cutoff]

        return float(len(recent))

    def _calculate_convergence_rate(self) -> float:
        """
        Calcula taxa de convergência (redução de loss por update).

        Returns:
            Taxa de redução de loss (negativo = convergindo)
        """
        if len(self._loss_history) < 10:
            return 0.0

        recent_losses = [l[1] for l in self._loss_history[-100:]]

        # Calcular tendência linear
        x = np.arange(len(recent_losses))
        coeffs = np.polyfit(x, recent_losses, 1)

        return float(coeffs[0])  # Slope

    def _calculate_prediction_variance(self) -> float:
        """
        Calcula variância entre predições consecutivas.

        Returns:
            Variância média das predições
        """
        if len(self._prediction_samples) < 2:
            return 0.0

        # Calcular variância entre últimas predições
        recent = self._prediction_samples[-10:]
        variances = []

        for i in range(1, len(recent)):
            if recent[i].shape == recent[i-1].shape:
                var = np.mean(np.abs(recent[i] - recent[i-1]))
                variances.append(var)

        return float(np.mean(variances)) if variances else 0.0

    def _update_prometheus_metrics(self):
        """Atualiza métricas Prometheus."""
        # Update frequency
        freq = self._calculate_update_frequency()
        online_update_frequency.labels(
            specialist_type=self.specialist_type
        ).set(freq)

        # Memory usage
        memory_mb = self._get_memory_usage_mb()
        online_memory_usage_mb.labels(
            specialist_type=self.specialist_type
        ).set(memory_mb)

        # Model size
        model_size = self._get_model_size_mb()
        online_model_size_mb.labels(
            specialist_type=self.specialist_type
        ).set(model_size)

        # Prediction variance
        variance = self._calculate_prediction_variance()
        online_prediction_variance.labels(
            specialist_type=self.specialist_type
        ).set(variance)

    def _check_alerts(self):
        """Verifica condições de alerta."""
        alerts_to_add = []

        # Check convergence stall
        stall_alert = self._check_convergence_stall()
        if stall_alert:
            alerts_to_add.append(stall_alert)

        # Check memory leak
        leak_alert = self._check_memory_leak()
        if leak_alert:
            alerts_to_add.append(leak_alert)

        # Check prediction instability
        instability_alert = self._check_prediction_instability()
        if instability_alert:
            alerts_to_add.append(instability_alert)

        # Check update frequency
        freq_alert = self._check_update_frequency()
        if freq_alert:
            alerts_to_add.append(freq_alert)

        # Adicionar novos alertas
        for alert in alerts_to_add:
            self._add_alert(alert)

    def _check_convergence_stall(self) -> Optional[Alert]:
        """Verifica se convergência está parada."""
        if len(self._loss_history) < 10:
            return None

        # Verificar última janela
        cutoff = datetime.utcnow() - timedelta(
            hours=self.config.convergence_stall_threshold_hours
        )
        recent = [(t, l) for t, l in self._loss_history if t > cutoff]

        if len(recent) < 5:
            return None

        losses = [l for _, l in recent]
        loss_reduction = losses[0] - losses[-1]

        # Stall se não houve redução significativa
        if loss_reduction < 0.001:
            online_convergence_stall.labels(
                specialist_type=self.specialist_type
            ).set(1)

            # Verificar se já existe alerta ativo
            for alert in self._active_alerts:
                if alert.alert_type == 'convergence_stall' and not alert.acknowledged:
                    return None

            return Alert(
                alert_type='convergence_stall',
                severity='warning',
                message=f"Convergência parada há {self.config.convergence_stall_threshold_hours}h. "
                        f"Loss inicial: {losses[0]:.4f}, final: {losses[-1]:.4f}",
                specialist_type=self.specialist_type,
                metrics={
                    'initial_loss': losses[0],
                    'final_loss': losses[-1],
                    'loss_reduction': loss_reduction,
                    'window_hours': self.config.convergence_stall_threshold_hours
                }
            )
        else:
            online_convergence_stall.labels(
                specialist_type=self.specialist_type
            ).set(0)

        return None

    def _check_memory_leak(self) -> Optional[Alert]:
        """Verifica se há memory leak."""
        if self._initial_memory_mb is None or len(self._memory_history) < 10:
            return None

        current_memory = self._memory_history[-1][1]
        memory_growth = current_memory - self._initial_memory_mb

        if memory_growth > self.config.memory_leak_threshold_mb:
            # Verificar se já existe alerta ativo
            for alert in self._active_alerts:
                if alert.alert_type == 'memory_leak' and not alert.acknowledged:
                    return None

            return Alert(
                alert_type='memory_leak',
                severity='critical',
                message=f"Possível memory leak detectado. "
                        f"Crescimento: {memory_growth:.1f}MB "
                        f"(threshold: {self.config.memory_leak_threshold_mb}MB)",
                specialist_type=self.specialist_type,
                metrics={
                    'initial_memory_mb': self._initial_memory_mb,
                    'current_memory_mb': current_memory,
                    'growth_mb': memory_growth,
                    'threshold_mb': self.config.memory_leak_threshold_mb
                }
            )

        return None

    def _check_prediction_instability(self) -> Optional[Alert]:
        """Verifica instabilidade de predições."""
        variance = self._calculate_prediction_variance()

        if variance > self.config.prediction_stability_variance_threshold:
            # Verificar se já existe alerta ativo
            for alert in self._active_alerts:
                if alert.alert_type == 'prediction_instability' and not alert.acknowledged:
                    return None

            return Alert(
                alert_type='prediction_instability',
                severity='warning',
                message=f"Alta variância em predições: {variance:.4f} "
                        f"(threshold: {self.config.prediction_stability_variance_threshold})",
                specialist_type=self.specialist_type,
                metrics={
                    'variance': variance,
                    'threshold': self.config.prediction_stability_variance_threshold
                }
            )

        return None

    def _check_update_frequency(self) -> Optional[Alert]:
        """Verifica frequência de updates."""
        freq = self._calculate_update_frequency()

        # Alerta se frequência muito baixa (menos de 1 update por hora)
        expected_freq = 60 / self.config.update_frequency_minutes
        if freq < expected_freq * 0.5 and len(self._update_timestamps) > 5:
            # Verificar se já existe alerta ativo
            for alert in self._active_alerts:
                if alert.alert_type == 'update_frequency_low' and not alert.acknowledged:
                    return None

            return Alert(
                alert_type='update_frequency_low',
                severity='info',
                message=f"Frequência de updates baixa: {freq:.1f}/hora "
                        f"(esperado: ~{expected_freq:.1f}/hora)",
                specialist_type=self.specialist_type,
                metrics={
                    'current_frequency': freq,
                    'expected_frequency': expected_freq
                }
            )

        return None

    def _add_alert(self, alert: Alert):
        """Adiciona novo alerta."""
        self._active_alerts.append(alert)

        # Persistir alerta
        try:
            self._alerts_collection.insert_one(alert.to_dict())
        except Exception as e:
            logger.warning("failed_to_persist_alert", error=str(e))

        # Emitir métrica
        online_alert_triggered.labels(
            specialist_type=self.specialist_type,
            alert_type=alert.alert_type
        ).inc()

        # Logar alerta
        log_fn = logger.warning if alert.severity in ['warning', 'critical'] else logger.info
        log_fn(
            "alert_triggered",
            specialist_type=self.specialist_type,
            alert_type=alert.alert_type,
            severity=alert.severity,
            message=alert.message,
            metrics=alert.metrics
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Retorna status completo do monitoramento.

        Returns:
            Dict com status e métricas
        """
        convergence = self._calculate_convergence_rate()
        variance = self._calculate_prediction_variance()
        freq = self._calculate_update_frequency()
        memory = self._get_memory_usage_mb()
        model_size = self._get_model_size_mb()

        return {
            'specialist_type': self.specialist_type,
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': {
                'update_frequency_per_hour': freq,
                'convergence_rate': convergence,
                'is_converging': convergence < 0,
                'prediction_variance': variance,
                'memory_usage_mb': memory,
                'model_size_mb': model_size,
                'memory_growth_mb': memory - self._initial_memory_mb if self._initial_memory_mb else 0,
                'total_updates': len(self._update_timestamps),
                'current_loss': self._loss_history[-1][1] if self._loss_history else None
            },
            'active_alerts': [a.to_dict() for a in self._active_alerts if not a.acknowledged],
            'health': self._assess_health()
        }

    def _assess_health(self) -> str:
        """
        Avalia saúde geral do modelo online.

        Returns:
            'healthy', 'degraded', ou 'unhealthy'
        """
        critical_alerts = [a for a in self._active_alerts
                          if a.severity == 'critical' and not a.acknowledged]
        warning_alerts = [a for a in self._active_alerts
                         if a.severity == 'warning' and not a.acknowledged]

        if critical_alerts:
            return 'unhealthy'
        elif warning_alerts:
            return 'degraded'
        else:
            return 'healthy'

    def acknowledge_alert(self, alert_type: str):
        """Marca alertas de um tipo como reconhecidos."""
        for alert in self._active_alerts:
            if alert.alert_type == alert_type:
                alert.acknowledged = True

        logger.info(
            "alert_acknowledged",
            specialist_type=self.specialist_type,
            alert_type=alert_type
        )

    def get_metrics_history(
        self,
        hours: int = 24,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Retorna histórico de métricas.

        Args:
            hours: Janela de tempo em horas
            limit: Número máximo de registros

        Returns:
            Lista de registros de métricas
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        docs = self._metrics_collection.find({
            'specialist_type': self.specialist_type,
            'timestamp': {'$gte': cutoff}
        }).sort('timestamp', DESCENDING).limit(limit)

        metrics = []
        for doc in docs:
            doc.pop('_id', None)
            if 'timestamp' in doc:
                doc['timestamp'] = doc['timestamp'].isoformat()
            metrics.append(doc)

        return metrics

    def close(self):
        """Fecha conexão com MongoDB."""
        if self._client:
            self._client.close()
