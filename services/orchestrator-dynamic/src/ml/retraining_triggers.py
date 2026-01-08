"""
Sistema de triggers para re-treinamento automático de modelos ML.

Implementa múltiplos gatilhos:
- Scheduled: Re-treinamento periódico baseado em intervalo configurado
- Drift-based: Re-treinamento quando drift detectado (PSI > threshold)
- Performance-based: Re-treinamento quando acurácia degrada
- Data-based: Re-treinamento quando volume de novos dados atinge threshold
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class TriggerType(str, Enum):
    """Tipos de gatilhos de re-treinamento."""
    SCHEDULED = "scheduled"
    DRIFT = "drift"
    PERFORMANCE = "performance"
    DATA_VOLUME = "data_volume"
    MANUAL = "manual"


class TriggerPriority(int, Enum):
    """Prioridade de gatilhos."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class RetrainingTrigger:
    """Representa um gatilho de re-treinamento."""

    def __init__(
        self,
        trigger_type: TriggerType,
        priority: TriggerPriority,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.trigger_type = trigger_type
        self.priority = priority
        self.reason = reason
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'trigger_type': self.trigger_type.value,
            'priority': self.priority.value,
            'reason': self.reason,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat()
        }


class RetrainingTriggerSystem:
    """
    Sistema de gerenciamento de triggers de re-treinamento.

    Avalia condições para re-treinamento e gera triggers com priorização.
    """

    def __init__(
        self,
        config,
        mongodb_client,
        drift_detector=None,
        metrics=None
    ):
        """
        Args:
            config: Configuração do orchestrator
            mongodb_client: Cliente MongoDB
            drift_detector: DriftDetector para verificação de drift
            metrics: OrchestratorMetrics
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.drift_detector = drift_detector
        self.metrics = metrics
        self.logger = logger.bind(component="retraining_triggers")

        # Configurações de threshold
        self.drift_threshold = getattr(config, 'ml_drift_trigger_threshold', 0.25)
        self.performance_threshold = getattr(config, 'ml_performance_trigger_threshold', 1.5)
        self.data_volume_threshold = getattr(config, 'ml_data_volume_trigger_threshold', 10000)

        # Último re-treinamento por modelo
        self._last_training: Dict[str, datetime] = {}

        # Callbacks para triggers
        self._callbacks: List[Callable] = []

        # Lock para evitar re-treinamentos concorrentes
        self._training_lock = asyncio.Lock()

    def register_callback(self, callback: Callable):
        """Registra callback para quando trigger é ativado."""
        self._callbacks.append(callback)

    async def evaluate_triggers(
        self,
        model_name: str = 'duration-predictor'
    ) -> List[RetrainingTrigger]:
        """
        Avalia todas as condições de re-treinamento.

        Args:
            model_name: Nome do modelo a avaliar

        Returns:
            Lista de triggers ativos, ordenados por prioridade
        """
        triggers = []

        # Verificar se triggers estão habilitados
        if not getattr(self.config, 'ml_retraining_triggers_enabled', True):
            return triggers

        try:
            # 1. Avaliar trigger de schedule
            schedule_trigger = await self._evaluate_schedule_trigger(model_name)
            if schedule_trigger:
                triggers.append(schedule_trigger)

            # 2. Avaliar trigger de drift
            if self.drift_detector:
                drift_trigger = await self._evaluate_drift_trigger(model_name)
                if drift_trigger:
                    triggers.append(drift_trigger)

            # 3. Avaliar trigger de performance
            performance_trigger = await self._evaluate_performance_trigger(model_name)
            if performance_trigger:
                triggers.append(performance_trigger)

            # 4. Avaliar trigger de volume de dados
            data_trigger = await self._evaluate_data_volume_trigger(model_name)
            if data_trigger:
                triggers.append(data_trigger)

            # Ordenar por prioridade (maior primeiro)
            triggers.sort(key=lambda t: t.priority.value, reverse=True)

            if triggers:
                self.logger.info(
                    "retraining_triggers_evaluated",
                    model_name=model_name,
                    active_triggers=len(triggers),
                    highest_priority=triggers[0].trigger_type.value if triggers else None
                )

            return triggers

        except Exception as e:
            self.logger.error(
                "trigger_evaluation_failed",
                model_name=model_name,
                error=str(e)
            )
            return []

    async def _evaluate_schedule_trigger(
        self,
        model_name: str
    ) -> Optional[RetrainingTrigger]:
        """Avalia se re-treinamento scheduled deve ser acionado."""
        interval_hours = getattr(self.config, 'ml_training_interval_hours', 24)

        last_training = self._last_training.get(model_name)

        if last_training is None:
            # Verificar último treinamento no MongoDB
            last_training_doc = await self.mongodb_client.db['ml_training_history'].find_one(
                {'model_name': model_name},
                sort=[('timestamp', -1)]
            )

            if last_training_doc:
                last_training = last_training_doc.get('timestamp')
                self._last_training[model_name] = last_training
            else:
                # Nunca treinado, trigger imediato
                return RetrainingTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    priority=TriggerPriority.HIGH,
                    reason=f"Modelo {model_name} nunca foi treinado",
                    metadata={'first_training': True}
                )

        if last_training:
            elapsed_hours = (datetime.utcnow() - last_training).total_seconds() / 3600

            if elapsed_hours >= interval_hours:
                return RetrainingTrigger(
                    trigger_type=TriggerType.SCHEDULED,
                    priority=TriggerPriority.MEDIUM,
                    reason=f"Intervalo de {interval_hours}h desde último treinamento excedido",
                    metadata={
                        'last_training': last_training.isoformat(),
                        'elapsed_hours': round(elapsed_hours, 2),
                        'interval_hours': interval_hours
                    }
                )

        return None

    async def _evaluate_drift_trigger(
        self,
        model_name: str
    ) -> Optional[RetrainingTrigger]:
        """Avalia se drift detectado deve acionar re-treinamento."""
        if not self.drift_detector:
            return None

        try:
            drift_report = self.drift_detector.run_drift_check()

            overall_status = drift_report.get('overall_status', 'ok')

            if overall_status == 'critical':
                # Drift crítico - trigger imediato
                feature_drift = drift_report.get('feature_drift', {})
                prediction_drift = drift_report.get('prediction_drift', {})

                drifted_features = [
                    f for f, psi in feature_drift.items()
                    if psi > self.drift_threshold
                ]

                return RetrainingTrigger(
                    trigger_type=TriggerType.DRIFT,
                    priority=TriggerPriority.CRITICAL,
                    reason=f"Drift crítico detectado: {len(drifted_features)} features afetadas",
                    metadata={
                        'overall_status': overall_status,
                        'drifted_features': drifted_features,
                        'prediction_drift_ratio': prediction_drift.get('drift_ratio'),
                        'recommendations': drift_report.get('recommendations', [])
                    }
                )

            elif overall_status == 'warning':
                # Drift moderado - trigger com prioridade média
                return RetrainingTrigger(
                    trigger_type=TriggerType.DRIFT,
                    priority=TriggerPriority.MEDIUM,
                    reason="Drift moderado detectado em features ou predições",
                    metadata={
                        'overall_status': overall_status,
                        'feature_drift': drift_report.get('feature_drift', {}),
                        'prediction_drift': drift_report.get('prediction_drift', {})
                    }
                )

        except Exception as e:
            self.logger.warning("drift_trigger_evaluation_failed", error=str(e))

        return None

    async def _evaluate_performance_trigger(
        self,
        model_name: str
    ) -> Optional[RetrainingTrigger]:
        """Avalia se degradação de performance deve acionar re-treinamento."""
        try:
            # Buscar MAE recente vs MAE de baseline
            recent_metrics = await self.mongodb_client.db['ml_prediction_metrics'].find({
                'model_name': model_name,
                'timestamp': {'$gte': datetime.utcnow() - timedelta(days=7)}
            }).to_list(100)

            if not recent_metrics:
                return None

            # Calcular MAE médio recente
            recent_mae = sum(m.get('mae_ms', 0) for m in recent_metrics) / len(recent_metrics)

            # Buscar baseline MAE
            baseline = await self.mongodb_client.db['ml_feature_baselines'].find_one(
                {'model_name': model_name},
                sort=[('timestamp', -1)]
            )

            if not baseline:
                return None

            training_mae = baseline.get('training_mae', 0)

            if training_mae > 0:
                performance_ratio = recent_mae / training_mae

                if performance_ratio > self.performance_threshold:
                    degradation_pct = (performance_ratio - 1) * 100

                    return RetrainingTrigger(
                        trigger_type=TriggerType.PERFORMANCE,
                        priority=TriggerPriority.HIGH,
                        reason=f"Degradação de {degradation_pct:.1f}% na acurácia",
                        metadata={
                            'recent_mae': recent_mae,
                            'training_mae': training_mae,
                            'performance_ratio': performance_ratio,
                            'degradation_pct': degradation_pct,
                            'threshold': self.performance_threshold
                        }
                    )

        except Exception as e:
            self.logger.warning("performance_trigger_evaluation_failed", error=str(e))

        return None

    async def _evaluate_data_volume_trigger(
        self,
        model_name: str
    ) -> Optional[RetrainingTrigger]:
        """Avalia se volume de novos dados deve acionar re-treinamento."""
        try:
            # Buscar timestamp do último treinamento
            last_training = await self.mongodb_client.db['ml_training_history'].find_one(
                {'model_name': model_name},
                sort=[('timestamp', -1)]
            )

            if not last_training:
                return None

            last_training_date = last_training.get('timestamp')
            if not last_training_date:
                return None

            # Contar novos tickets desde último treinamento
            new_tickets_count = await self.mongodb_client.db['execution_tickets'].count_documents({
                'completed_at': {'$gte': last_training_date}
            })

            if new_tickets_count >= self.data_volume_threshold:
                return RetrainingTrigger(
                    trigger_type=TriggerType.DATA_VOLUME,
                    priority=TriggerPriority.MEDIUM,
                    reason=f"{new_tickets_count} novos tickets desde último treinamento",
                    metadata={
                        'new_tickets_count': new_tickets_count,
                        'threshold': self.data_volume_threshold,
                        'last_training': last_training_date.isoformat()
                    }
                )

        except Exception as e:
            self.logger.warning("data_volume_trigger_evaluation_failed", error=str(e))

        return None

    async def should_retrain(self, model_name: str = 'duration-predictor') -> bool:
        """
        Verifica se modelo deve ser re-treinado.

        Args:
            model_name: Nome do modelo

        Returns:
            True se há triggers ativos
        """
        triggers = await self.evaluate_triggers(model_name)
        return len(triggers) > 0

    async def trigger_retraining(
        self,
        model_name: str,
        trigger: RetrainingTrigger
    ) -> Dict[str, Any]:
        """
        Executa re-treinamento baseado em trigger.

        Args:
            model_name: Nome do modelo
            trigger: Trigger que acionou o re-treinamento

        Returns:
            Dict com resultado do re-treinamento
        """
        async with self._training_lock:
            try:
                self.logger.info(
                    "retraining_triggered",
                    model_name=model_name,
                    trigger_type=trigger.trigger_type.value,
                    priority=trigger.priority.value,
                    reason=trigger.reason
                )

                # Registrar trigger no histórico
                await self._record_trigger(model_name, trigger)

                # Executar callbacks registrados
                for callback in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(model_name, trigger)
                        else:
                            callback(model_name, trigger)
                    except Exception as e:
                        self.logger.warning(
                            "trigger_callback_failed",
                            error=str(e)
                        )

                # Atualizar timestamp de último treinamento
                self._last_training[model_name] = datetime.utcnow()

                return {
                    'status': 'triggered',
                    'model_name': model_name,
                    'trigger': trigger.to_dict()
                }

            except Exception as e:
                self.logger.error(
                    "trigger_retraining_failed",
                    model_name=model_name,
                    error=str(e)
                )
                return {
                    'status': 'failed',
                    'error': str(e)
                }

    async def _record_trigger(
        self,
        model_name: str,
        trigger: RetrainingTrigger
    ) -> None:
        """Registra trigger no histórico MongoDB."""
        try:
            await self.mongodb_client.db['ml_retraining_triggers'].insert_one({
                'model_name': model_name,
                'trigger_type': trigger.trigger_type.value,
                'priority': trigger.priority.value,
                'reason': trigger.reason,
                'metadata': trigger.metadata,
                'timestamp': trigger.timestamp
            })
        except Exception as e:
            self.logger.warning("failed_to_record_trigger", error=str(e))

    def create_manual_trigger(self, reason: str = "Manual trigger") -> RetrainingTrigger:
        """Cria trigger manual para re-treinamento forçado."""
        return RetrainingTrigger(
            trigger_type=TriggerType.MANUAL,
            priority=TriggerPriority.HIGH,
            reason=reason,
            metadata={'initiated_by': 'manual'}
        )

    async def get_trigger_history(
        self,
        model_name: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Recupera histórico de triggers para um modelo.

        Args:
            model_name: Nome do modelo
            limit: Limite de registros

        Returns:
            Lista de triggers históricos
        """
        try:
            triggers = await self.mongodb_client.db['ml_retraining_triggers'].find({
                'model_name': model_name
            }).sort('timestamp', -1).limit(limit).to_list(limit)

            return triggers

        except Exception as e:
            self.logger.error("failed_to_get_trigger_history", error=str(e))
            return []

    async def get_trigger_stats(
        self,
        model_name: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Obtém estatísticas de triggers para um modelo.

        Args:
            model_name: Nome do modelo
            days: Janela de tempo em dias

        Returns:
            Dict com estatísticas
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)

            pipeline = [
                {'$match': {
                    'model_name': model_name,
                    'timestamp': {'$gte': cutoff}
                }},
                {'$group': {
                    '_id': '$trigger_type',
                    'count': {'$sum': 1},
                    'last_triggered': {'$max': '$timestamp'}
                }}
            ]

            results = await self.mongodb_client.db['ml_retraining_triggers'].aggregate(
                pipeline
            ).to_list(None)

            stats = {
                'model_name': model_name,
                'period_days': days,
                'triggers_by_type': {r['_id']: r['count'] for r in results},
                'total_triggers': sum(r['count'] for r in results),
                'last_triggered': max(
                    (r['last_triggered'] for r in results),
                    default=None
                )
            }

            return stats

        except Exception as e:
            self.logger.error("failed_to_get_trigger_stats", error=str(e))
            return {}
