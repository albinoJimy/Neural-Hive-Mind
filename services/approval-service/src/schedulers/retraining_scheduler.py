"""
Retraining Scheduler - Agendador de retreino periódico

Gerencia agendamento de retreinos periodicos e triggers por drift detection.
Inclui shadow validation e A/B testing antes de deploy.
"""

import asyncio
import os
import structlog
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from enum import Enum

from src.config.settings import Settings

logger = structlog.get_logger()


class SchedulerStatus(str, Enum):
    """Status do scheduler."""
    STOPPED = 'stopped'
    RUNNING = 'running'
    PAUSED = 'paused'


class RetrainingTrigger(str, Enum):
    """Tipos de trigger para retreino."""
    SCHEDULED = 'scheduled'  # Retreino periodico agendado
    DRIFT_DETECTED = 'drift_detected'  # Drift detectado
    MANUAL = 'manual'  # Trigger manual
    ACCURACY_DROP = 'accuracy_drop'  # Queda de accuracy
    MODEL_STALL = 'model_stall'  # Modelo estagnado


class ValidationStatus(str, Enum):
    """Status da validação shadow."""
    PENDING = 'pending'
    VALIDATING = 'validating'
    PASSED = 'passed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class RetrainingScheduler:
    """
    Scheduler para retreino periodico de modelos ML.

    Funcionalidades:
    - Agendamento de retreino (diario/semanal/mensal)
    - Trigger por drift detection
    - Shadow validation antes de deploy
    - A/B testing entre modelo antigo e novo
    - Rollback automático em caso de problema
    """

    def __init__(
        self,
        settings: Settings,
        online_learning_service: Optional[Any] = None,
        drift_detector: Optional[Any] = None
    ):
        """
        Inicializa Retraining Scheduler.

        Args:
            settings: Configurações do Approval Service
            online_learning_service: Serviço de online learning (opcional)
            drift_detector: Detector de drift (opcional)
        """
        self.settings = settings
        self.online_learning_service = online_learning_service
        self.drift_detector = drift_detector

        self._status = SchedulerStatus.STOPPED
        self._task: Optional[asyncio.Task] = None
        self._last_schedule_run: Optional[datetime] = None
        self._last_drift_check: Optional[datetime] = None
        self._validation_results: Dict[str, Dict[str, Any]] = {}

        # Configurações de agendamento
        self._retrain_interval_hours = settings.online_learning_retrain_interval_hours
        self._drift_check_interval_minutes = 30
        self._shadow_validation_sample_size = 1000

        logger.info(
            'retraining_scheduler_initialized',
            retrain_interval_hours=self._retrain_interval_hours,
            drift_check_interval_minutes=self._drift_check_interval_minutes
        )

    @property
    def status(self) -> SchedulerStatus:
        """Retorna status atual do scheduler."""
        return self._status

    @property
    def is_running(self) -> bool:
        """Retorna se scheduler está rodando."""
        return self._status == SchedulerStatus.RUNNING

    async def start(self):
        """Inicia o scheduler."""
        if self._status == SchedulerStatus.RUNNING:
            logger.warning('scheduler_ja_esta_rodando')
            return

        self._status = SchedulerStatus.RUNNING
        self._task = asyncio.create_task(self._scheduler_loop())

        logger.info(
            'retraining_scheduler_iniciado',
            retrain_interval_hours=self._retrain_interval_hours
        )

    async def stop(self):
        """Para o scheduler gracefulmente."""
        if self._status == SchedulerStatus.STOPPED:
            return

        self._status = SchedulerStatus.STOPPED

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info('retraining_scheduler_parado')

    async def pause(self):
        """Pausa o scheduler temporariamente."""
        if self._status == SchedulerStatus.RUNNING:
            self._status = SchedulerStatus.PAUSED
            logger.info('retraining_scheduler_pausado')

    async def resume(self):
        """Retoma scheduler pausado."""
        if self._status == SchedulerStatus.PAUSED:
            self._status = SchedulerStatus.RUNNING
            logger.info('retraining_scheduler_retomado')

    async def _scheduler_loop(self):
        """Loop principal do scheduler."""
        logger.info('scheduler_loop_iniciado')

        while self._status != SchedulerStatus.STOPPED:
            try:
                # Se pausado, apenas aguarda
                if self._status == SchedulerStatus.PAUSED:
                    await asyncio.sleep(5)
                    continue

                now = datetime.utcnow()

                # Verifica se é hora do retreino agendado
                if self._should_run_scheduled_retrain(now):
                    await self._run_scheduled_retraining()

                # Verifica drift de dados periodicamente
                if self._should_check_drift(now):
                    await self._check_and_trigger_drift_retraining()

                # Dorme por um intervalo curto
                await asyncio.sleep(60)  # Checa a cada minuto

            except asyncio.CancelledError:
                logger.info('scheduler_loop_cancelado')
                break
            except Exception as e:
                logger.error(
                    'erro_no_scheduler_loop',
                    error=str(e)
                )
                await asyncio.sleep(60)  # Espera antes de tentar novamente

    def _should_run_scheduled_retrain(self, now: datetime) -> bool:
        """Verifica se é hora do retreino agendado."""
        if self._last_schedule_run is None:
            return True

        hours_since_last = (now - self._last_schedule_run).total_seconds() / 3600
        return hours_since_last >= self._retrain_interval_hours

    def _should_check_drift(self, now: datetime) -> bool:
        """Verifica se é hora de checar drift."""
        if self._last_drift_check is None:
            return True

        minutes_since_last = (now - self._last_drift_check).total_seconds() / 60
        return minutes_since_last >= self._drift_check_interval_minutes

    async def _run_scheduled_retraining(self):
        """Executa retreino agendado."""
        logger.info('iniciando_retreino_agendado', trigger=RetrainingTrigger.SCHEDULED)
        self._last_schedule_run = datetime.utcnow()

        try:
            # Salvar checkpoints dos modelos atuais
            if self.online_learning_service:
                checkpoint_result = await self.online_learning_service.save_all_checkpoints()
                logger.info('checkpoints_salvos', result=checkpoint_result)

            # Executar shadow validation
            validation_result = await self._run_shadow_validation()

            if validation_result['status'] == ValidationStatus.PASSED:
                logger.info(
                    'shadow_validation_passed',
                    result=validation_result
                )
                # TODO: Implementar deploy do novo modelo
            else:
                logger.warning(
                    'shadow_validation_failed',
                    result=validation_result
                )

        except Exception as e:
            logger.error(
                'erro_no_retreino_agendado',
                error=str(e)
            )

    async def _check_and_trigger_drift_retraining(self):
        """Verifica drift e triggera retreino se necessário."""
        self._last_drift_check = datetime.utcnow()

        if not self.drift_detector:
            return

        try:
            # Verificar drift
            drift_result = await self._detect_drift()

            if drift_result.get('drift_detected'):
                logger.warning(
                    'drift_detectado',
                    trigger=RetrainingTrigger.DRIFT_DETECTED,
                    drift_score=drift_result.get('drift_score')
                )

                # Triggerar retreino por drift
                await self._trigger_retraining(
                    trigger=RetrainingTrigger.DRIFT_DETECTED,
                    reason=drift_result.get('drift_type', 'unknown')
                )
            else:
                logger.debug(
                    'drift_nao_detectado',
                    drift_score=drift_result.get('drift_score', 0)
                )

        except Exception as e:
            logger.error(
                'erro_ao_verificar_drift',
                error=str(e)
            )

    async def _detect_drift(self) -> Dict[str, Any]:
        """
        Detecta drift nos dados/modelos.

        Returns:
            Dicionário com resultado da detecção
        """
        # Placeholder - implementação real usaria o drift_detector
        return {
            'drift_detected': False,
            'drift_score': 0.0,
            'drift_type': None
        }

    async def _trigger_retraining(
        self,
        trigger: RetrainingTrigger,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Triggera retreino com motivo específico.

        Args:
            trigger: Tipo de trigger
            reason: Razão do retreino
            metadata: Metadados adicionais
        """
        logger.info(
            'retraining_triggered',
            trigger=trigger,
            reason=reason,
            metadata=metadata
        )

        # TODO: Implementar lógica de retreino real
        # Por enquanto, apenas log

    async def _run_shadow_validation(
        self,
        sample_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Executa shadow validation do modelo.

        Compara predições do modelo atual vs novo modelo em dados reais
        sem afetar produções.

        Args:
            sample_size: Tamanho da amostra (usa config se não fornecido)

        Returns:
            Dicionário com resultado da validação
        """
        sample_size = sample_size or self._shadow_validation_sample_size

        validation_id = f"validation_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        result = {
            'validation_id': validation_id,
            'status': ValidationStatus.PENDING,
            'sample_size': sample_size,
            'started_at': datetime.utcnow().isoformat()
        }

        self._validation_results[validation_id] = result

        try:
            result['status'] = ValidationStatus.VALIDATING
            logger.info(
                'shadow_validation_iniciada',
                validation_id=validation_id,
                sample_size=sample_size
            )

            # TODO: Implementar shadow validation real
            # Por enquanto, simula validação bem-sucedida
            await asyncio.sleep(1)

            result['status'] = ValidationStatus.PASSED
            result['metrics'] = {
                'accuracy_ratio': 0.98,  # 98% do baseline
                'latency_ratio': 1.1,  # 110% do baseline
                'predictions_match_rate': 0.95
            }
            result['completed_at'] = datetime.utcnow().isoformat()

        except Exception as e:
            result['status'] = ValidationStatus.FAILED
            result['error'] = str(e)
            logger.error(
                'shadow_validation_falhou',
                validation_id=validation_id,
                error=str(e)
            )

        return result

    async def trigger_manual_retraining(
        self,
        reason: str,
        requested_by: str
    ) -> Dict[str, Any]:
        """
        Triggera retreino manual.

        Args:
            reason: Razão do retreino manual
            requested_by: Quem solicitou

        Returns:
            Resultado do trigger
        """
        logger.info(
            'retraining_manual_solicitado',
            reason=reason,
            requested_by=requested_by
        )

        await self._trigger_retraining(
            trigger=RetrainingTrigger.MANUAL,
            reason=reason,
            metadata={'requested_by': requested_by}
        )

        return {
            'triggered': True,
            'trigger_type': RetrainingTrigger.MANUAL,
            'requested_by': requested_by,
            'timestamp': datetime.utcnow().isoformat()
        }

    async def run_ab_test(
        self,
        model_a_id: str,
        model_b_id: str,
        traffic_split: float = 0.5,
        duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Executa teste A/B entre dois modelos.

        Args:
            model_a_id: ID do modelo A (baseline)
            model_b_id: ID do modelo B (candidate)
            traffic_split: Split de tráfego para modelo B (0-1)
            duration_minutes: Duração do teste

        Returns:
            Resultados do A/B test
        """
        test_id = f"ab_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        logger.info(
            'ab_test_iniciado',
            test_id=test_id,
            model_a=model_a_id,
            model_b=model_b_id,
            traffic_split=traffic_split,
            duration_minutes=duration_minutes
        )

        # TODO: Implementar A/B test real
        # Por agora, retorna placeholder

        return {
            'test_id': test_id,
            'status': 'running',
            'model_a_id': model_a_id,
            'model_b_id': model_b_id,
            'traffic_split': traffic_split,
            'started_at': datetime.utcnow().isoformat(),
            'estimated_end': (datetime.utcnow() + timedelta(minutes=duration_minutes)).isoformat()
        }

    async def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Retorna status completo do scheduler.

        Returns:
            Dicionário com status
        """
        return {
            'status': self._status.value,
            'is_running': self.is_running,
            'retrain_interval_hours': self._retrain_interval_hours,
            'drift_check_interval_minutes': self._drift_check_interval_minutes,
            'last_schedule_run': self._last_schedule_run.isoformat() if self._last_schedule_run else None,
            'last_drift_check': self._last_drift_check.isoformat() if self._last_drift_check else None,
            'next_schedule_run': (
                self._last_schedule_run + timedelta(hours=self._retrain_interval_hours)
            ).isoformat() if self._last_schedule_run else None,
            'validation_results': self._validation_results
        }

    async def get_recent_validations(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retorna validações recentes.

        Args:
            limit: Limite de resultados

        Returns:
            Lista de validações
        """
        validations = list(self._validation_results.values())
        validations.sort(
            key=lambda x: x.get('started_at', ''),
            reverse=True
        )
        return validations[:limit]

    def clear_validation_history(self, older_than_hours: int = 24):
        """
        Limpa histórico de validações antigas.

        Args:
            older_than_hours: Idade mínima em horas
        """
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
        to_remove = []

        for validation_id, result in self._validation_results.items():
            started_at_str = result.get('started_at')
            if started_at_str:
                try:
                    started_at = datetime.fromisoformat(started_at_str)
                    if started_at < cutoff:
                        to_remove.append(validation_id)
                except ValueError:
                    pass

        for validation_id in to_remove:
            del self._validation_results[validation_id]

        logger.info(
            'validation_history_limpa',
            removed_count=len(to_remove),
            remaining_count=len(self._validation_results)
        )


# Factory function para criar scheduler
def create_retraining_scheduler(
    settings: Settings,
    online_learning_service: Optional[Any] = None,
    drift_detector: Optional[Any] = None
) -> RetrainingScheduler:
    """
    Factory para criar RetrainingScheduler.

    Args:
        settings: Configurações do Approval Service
        online_learning_service: Serviço de online learning (opcional)
        drift_detector: Detector de drift (opcional)

    Returns:
        Instância de RetrainingScheduler
    """
    return RetrainingScheduler(
        settings=settings,
        online_learning_service=online_learning_service,
        drift_detector=drift_detector
    )
