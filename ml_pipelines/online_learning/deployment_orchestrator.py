"""
Deployment Orchestrator para Online Learning.

Coordena o pipeline completo de online learning incluindo coleta de feedback,
atualização incremental, validação shadow, e deployment gradual.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
import structlog
import numpy as np
from pymongo import MongoClient, DESCENDING
from prometheus_client import Counter, Histogram, Gauge

from .config import OnlineLearningConfig
from .incremental_learner import IncrementalLearner
from .shadow_validator import ShadowValidator, ShadowValidationResult
from .model_ensemble import ModelEnsemble
from .rollback_manager import RollbackManager
from .online_monitor import OnlinePerformanceMonitor

logger = structlog.get_logger(__name__)

# Métricas Prometheus
deployment_cycles_total = Counter(
    'neural_hive_deployment_cycles_total',
    'Total de ciclos de deployment',
    ['specialist_type', 'result']
)
deployment_duration = Histogram(
    'neural_hive_deployment_duration_seconds',
    'Duração de ciclos de deployment',
    ['specialist_type', 'stage']
)
current_rollout_percentage = Gauge(
    'neural_hive_current_rollout_percentage',
    'Percentual atual de rollout',
    ['specialist_type']
)
deployment_cooldown_active = Gauge(
    'neural_hive_deployment_cooldown_active',
    'Indicador de cooldown ativo (1=ativo)',
    ['specialist_type']
)


class DeploymentError(Exception):
    """Exceção para erros de deployment."""
    pass


class DeploymentStage:
    """Representa um estágio de deployment."""

    COLLECT = 'collect'
    UPDATE = 'update'
    VALIDATE = 'validate'
    APPROVE = 'approve'
    DEPLOY = 'deploy'
    MONITOR = 'monitor'
    ROLLBACK = 'rollback'


class OnlineDeploymentOrchestrator:
    """
    Orquestra o pipeline completo de online learning.

    Pipeline:
    1. COLLECT: Buscar feedback recente
    2. UPDATE: Executar partial_fit no modelo online
    3. VALIDATE: Shadow validation com baseline
    4. APPROVE: Verificar thresholds de qualidade
    5. DEPLOY: Gradual rollout (10% → 50% → 100%)
    6. MONITOR: Observar métricas por período
    7. ROLLBACK: Reverter se degradação detectada

    Features:
    - Integração com RetrainingTrigger para coordenar batch + online
    - Cooldown period entre updates
    - Feature flags por specialist
    - Logs estruturados para auditoria
    """

    def __init__(
        self,
        config: OnlineLearningConfig,
        specialist_type: str,
        batch_model: Any,
        feedback_collector: Optional[Any] = None,
        feature_extractor: Optional[Callable] = None
    ):
        """
        Inicializa OnlineDeploymentOrchestrator.

        Args:
            config: Configuração de online learning
            specialist_type: Tipo do especialista
            batch_model: Modelo batch (baseline)
            feedback_collector: Coletor de feedback (opcional)
            feature_extractor: Função para extrair features de feedback
        """
        self.config = config
        self.specialist_type = specialist_type
        self.batch_model = batch_model
        self.feedback_collector = feedback_collector
        self.feature_extractor = feature_extractor

        # Inicializar componentes
        self.learner = IncrementalLearner(config, specialist_type)
        self.rollback_manager = RollbackManager(config, specialist_type)
        self.monitor = OnlinePerformanceMonitor(config, specialist_type, self.learner)

        # Ensemble e validator serão criados após primeiro update
        self.ensemble: Optional[ModelEnsemble] = None
        self.validator: Optional[ShadowValidator] = None

        # MongoDB para histórico
        self._client = MongoClient(config.mongodb_uri)
        self._db = self._client[config.mongodb_database]
        self._deployments_collection = self._db['online_deployments']

        # Estado
        self._last_deployment_time: Optional[datetime] = None
        self._current_rollout_percentage = 0
        self._current_deployment_id: Optional[str] = None
        self._is_running = False

        logger.info(
            "deployment_orchestrator_initialized",
            specialist_type=specialist_type,
            update_frequency_minutes=config.update_frequency_minutes,
            rollout_stages=config.rollout_stages
        )

    def _check_cooldown(self) -> bool:
        """
        Verifica se está em período de cooldown.

        Returns:
            True se em cooldown, False caso contrário
        """
        if self._last_deployment_time is None:
            return False

        cooldown_end = self._last_deployment_time + timedelta(
            minutes=self.config.deployment_cooldown_minutes
        )

        in_cooldown = datetime.utcnow() < cooldown_end

        deployment_cooldown_active.labels(
            specialist_type=self.specialist_type
        ).set(1 if in_cooldown else 0)

        return in_cooldown

    async def _collect_feedback(self, min_samples: int = 100) -> List[Dict[str, Any]]:
        """
        Coleta feedback recente.

        Args:
            min_samples: Número mínimo de amostras

        Returns:
            Lista de feedbacks
        """
        start_time = time.time()

        if self.feedback_collector is None:
            logger.warning(
                "no_feedback_collector",
                specialist_type=self.specialist_type
            )
            return []

        try:
            # Buscar feedbacks recentes não processados
            feedbacks = self.feedback_collector.get_feedback_by_specialist(
                specialist_type=self.specialist_type,
                window_days=7
            )

            duration = time.time() - start_time
            deployment_duration.labels(
                specialist_type=self.specialist_type,
                stage=DeploymentStage.COLLECT
            ).observe(duration)

            logger.info(
                "feedback_collected",
                specialist_type=self.specialist_type,
                count=len(feedbacks),
                duration_seconds=duration
            )

            return [f.model_dump() if hasattr(f, 'model_dump') else f for f in feedbacks]

        except Exception as e:
            logger.error(
                "feedback_collection_failed",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            return []

    def _prepare_training_data(
        self,
        feedbacks: List[Dict[str, Any]]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Prepara dados de treinamento a partir de feedbacks.

        Args:
            feedbacks: Lista de feedbacks

        Returns:
            Tuple (X, y) para treinamento
        """
        if not feedbacks:
            raise ValueError("Nenhum feedback disponível")

        if self.feature_extractor is None:
            raise ValueError("Feature extractor não configurado")

        X_list = []
        y_list = []

        for feedback in feedbacks:
            try:
                # Extrair features
                features = self.feature_extractor(feedback)
                X_list.append(features)

                # Label é a recomendação humana
                y_list.append(feedback.get('human_recommendation', 'review_required'))

            except Exception as e:
                logger.warning(
                    "feature_extraction_failed",
                    feedback_id=feedback.get('feedback_id'),
                    error=str(e)
                )
                continue

        if not X_list:
            raise ValueError("Nenhum feedback válido após extração de features")

        return np.array(X_list), np.array(y_list)

    async def _update_model(
        self,
        feedbacks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Executa atualização incremental do modelo.

        Args:
            feedbacks: Feedbacks para treinamento

        Returns:
            Métricas de atualização
        """
        start_time = time.time()

        try:
            # Preparar dados
            X, y = self._prepare_training_data(feedbacks)

            # Dividir em mini-batches
            batch_size = self.config.mini_batch_size
            n_samples = len(X)
            n_batches = max(1, n_samples // batch_size)

            total_loss = 0.0
            updates_executed = 0

            for i in range(n_batches):
                start_idx = i * batch_size
                end_idx = min((i + 1) * batch_size, n_samples)

                X_batch = X[start_idx:end_idx]
                y_batch = y[start_idx:end_idx]

                # Executar partial_fit
                result = self.learner.partial_fit(X_batch, y_batch)
                total_loss += result['loss_after']
                updates_executed += 1

                # Registrar no monitor
                self.monitor.record_update(
                    loss=result['loss_after'],
                    duration_ms=result['duration_ms'],
                    samples_count=len(y_batch)
                )

            avg_loss = total_loss / updates_executed if updates_executed > 0 else 0.0

            duration = time.time() - start_time
            deployment_duration.labels(
                specialist_type=self.specialist_type,
                stage=DeploymentStage.UPDATE
            ).observe(duration)

            metrics = {
                'samples_processed': n_samples,
                'batches_executed': n_batches,
                'avg_loss': avg_loss,
                'duration_seconds': duration,
                'model_version': self.learner.model_version
            }

            logger.info(
                "model_updated",
                specialist_type=self.specialist_type,
                **metrics
            )

            return metrics

        except Exception as e:
            logger.error(
                "model_update_failed",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            raise DeploymentError(f"Falha na atualização: {str(e)}") from e

    async def _validate(self, X_validation: np.ndarray, y_validation: Optional[np.ndarray] = None) -> ShadowValidationResult:
        """
        Executa shadow validation.

        Args:
            X_validation: Features para validação
            y_validation: Labels para validação (opcional)

        Returns:
            Resultado da validação
        """
        start_time = time.time()

        # Criar validator se não existir
        if self.validator is None:
            self.validator = ShadowValidator(
                config=self.config,
                specialist_type=self.specialist_type,
                batch_model=self.batch_model,
                online_learner=self.learner
            )

        result = self.validator.validate(X_validation, y_validation)

        duration = time.time() - start_time
        deployment_duration.labels(
            specialist_type=self.specialist_type,
            stage=DeploymentStage.VALIDATE
        ).observe(duration)

        logger.info(
            "validation_completed",
            specialist_type=self.specialist_type,
            passed=result.passed,
            validation_id=result.validation_id,
            duration_seconds=duration
        )

        return result

    async def _gradual_rollout(self) -> bool:
        """
        Executa rollout gradual do modelo online.

        Returns:
            True se rollout completo com sucesso
        """
        # Criar ensemble se não existir
        if self.ensemble is None:
            self.ensemble = ModelEnsemble(
                config=self.config,
                specialist_type=self.specialist_type,
                batch_model=self.batch_model,
                online_learner=self.learner
            )
        else:
            self.ensemble.set_online_learner(self.learner)

        for stage_percentage in self.config.rollout_stages:
            self._current_rollout_percentage = stage_percentage
            current_rollout_percentage.labels(
                specialist_type=self.specialist_type
            ).set(stage_percentage)

            logger.info(
                "rollout_stage_started",
                specialist_type=self.specialist_type,
                percentage=stage_percentage
            )

            # Atualizar peso do modelo online baseado no estágio
            online_weight = (stage_percentage / 100.0) * self.config.online_model_weight
            batch_weight = 1.0 - online_weight
            self.ensemble._online_weight = online_weight
            self.ensemble._batch_weight = batch_weight

            # Monitorar por período do estágio
            stage_duration = self.config.rollout_stage_duration_minutes * 60
            stage_start = time.time()

            while time.time() - stage_start < stage_duration:
                # Verificar saúde
                status = self.monitor.get_status()

                if status['health'] == 'unhealthy':
                    logger.error(
                        "rollout_aborted_unhealthy",
                        specialist_type=self.specialist_type,
                        stage=stage_percentage,
                        alerts=status['active_alerts']
                    )
                    return False

                await asyncio.sleep(60)  # Check a cada minuto

            logger.info(
                "rollout_stage_completed",
                specialist_type=self.specialist_type,
                percentage=stage_percentage
            )

        return True

    async def run_deployment_cycle(
        self,
        force: bool = False,
        validation_data: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """
        Executa um ciclo completo de deployment.

        Args:
            force: Ignorar cooldown
            validation_data: Dados de validação (X, y) opcionais

        Returns:
            Resultado do deployment
        """
        if self._is_running:
            raise DeploymentError("Deployment já em execução")

        if not force and self._check_cooldown():
            remaining = (
                self._last_deployment_time +
                timedelta(minutes=self.config.deployment_cooldown_minutes) -
                datetime.utcnow()
            ).seconds
            raise DeploymentError(f"Em cooldown. Aguarde {remaining} segundos.")

        self._is_running = True
        self._current_deployment_id = f"deploy-{uuid.uuid4().hex[:12]}"
        cycle_start = time.time()

        deployment_record = {
            'deployment_id': self._current_deployment_id,
            'specialist_type': self.specialist_type,
            'started_at': datetime.utcnow(),
            'stages': [],
            'status': 'running'
        }

        try:
            # Stage 1: Collect
            feedbacks = await self._collect_feedback()
            if len(feedbacks) < self.config.mini_batch_size:
                deployment_record['status'] = 'skipped'
                deployment_record['reason'] = 'insufficient_feedback'
                self._persist_deployment(deployment_record)
                return {'status': 'skipped', 'reason': 'Feedback insuficiente'}

            deployment_record['stages'].append({
                'stage': DeploymentStage.COLLECT,
                'feedback_count': len(feedbacks)
            })

            # Stage 2: Update
            update_metrics = await self._update_model(feedbacks)
            deployment_record['stages'].append({
                'stage': DeploymentStage.UPDATE,
                'metrics': update_metrics
            })

            # Stage 3: Validate
            if validation_data:
                X_val, y_val = validation_data
            else:
                # Usar parte do feedback para validação
                X_val, y_val = self._prepare_training_data(
                    feedbacks[-self.config.shadow_sample_size:]
                )

            validation_result = await self._validate(X_val, y_val)
            deployment_record['stages'].append({
                'stage': DeploymentStage.VALIDATE,
                'passed': validation_result.passed,
                'metrics': validation_result.metrics
            })

            # Stage 4: Approve
            if not validation_result.passed:
                deployment_record['status'] = 'rejected'
                deployment_record['reason'] = 'validation_failed'
                deployment_record['failures'] = validation_result.failures
                self._persist_deployment(deployment_record)

                deployment_cycles_total.labels(
                    specialist_type=self.specialist_type,
                    result='rejected'
                ).inc()

                return {
                    'status': 'rejected',
                    'reason': 'Validação falhou',
                    'failures': validation_result.failures
                }

            deployment_record['stages'].append({
                'stage': DeploymentStage.APPROVE,
                'approved': True
            })

            # Stage 5: Deploy (gradual rollout)
            if self.config.gradual_rollout_enabled:
                rollout_success = await self._gradual_rollout()

                if not rollout_success:
                    # Executar rollback
                    await self._execute_rollback("Rollout falhou durante monitoramento")
                    deployment_record['status'] = 'rolled_back'
                    self._persist_deployment(deployment_record)

                    deployment_cycles_total.labels(
                        specialist_type=self.specialist_type,
                        result='rolled_back'
                    ).inc()

                    return {'status': 'rolled_back', 'reason': 'Rollout falhou'}

            deployment_record['stages'].append({
                'stage': DeploymentStage.DEPLOY,
                'final_percentage': 100
            })

            # Registrar versão como estável
            checkpoint_path = self.learner.save_checkpoint()
            self.rollback_manager.register_version(
                version_id=self.learner.model_version,
                checkpoint_path=checkpoint_path,
                metrics={
                    'loss': update_metrics['avg_loss'],
                    'validation_kl': validation_result.metrics.get('kl_divergence', 0)
                },
                mark_stable=True
            )

            # Finalizar
            deployment_record['status'] = 'completed'
            deployment_record['completed_at'] = datetime.utcnow()
            deployment_record['duration_seconds'] = time.time() - cycle_start

            self._persist_deployment(deployment_record)
            self._last_deployment_time = datetime.utcnow()

            deployment_cycles_total.labels(
                specialist_type=self.specialist_type,
                result='success'
            ).inc()

            logger.info(
                "deployment_cycle_completed",
                deployment_id=self._current_deployment_id,
                specialist_type=self.specialist_type,
                duration_seconds=deployment_record['duration_seconds']
            )

            return {
                'status': 'completed',
                'deployment_id': self._current_deployment_id,
                'model_version': self.learner.model_version,
                'duration_seconds': deployment_record['duration_seconds']
            }

        except Exception as e:
            deployment_record['status'] = 'failed'
            deployment_record['error'] = str(e)
            self._persist_deployment(deployment_record)

            deployment_cycles_total.labels(
                specialist_type=self.specialist_type,
                result='failed'
            ).inc()

            logger.error(
                "deployment_cycle_failed",
                deployment_id=self._current_deployment_id,
                specialist_type=self.specialist_type,
                error=str(e)
            )

            raise

        finally:
            self._is_running = False

    async def _execute_rollback(self, reason: str):
        """Executa rollback para versão estável."""
        try:
            result = self.rollback_manager.execute_rollback(reason)

            # Restaurar modelo
            stable = self.rollback_manager.get_stable_version()
            if stable:
                checkpoint = self.rollback_manager.load_checkpoint(stable)
                self.learner.load_checkpoint(stable.checkpoint_path)

            # Resetar rollout
            self._current_rollout_percentage = 0
            current_rollout_percentage.labels(
                specialist_type=self.specialist_type
            ).set(0)

            if self.ensemble:
                self.ensemble._online_weight = 0
                self.ensemble._batch_weight = 1.0

            logger.info(
                "rollback_executed",
                specialist_type=self.specialist_type,
                reason=reason,
                **result
            )

        except Exception as e:
            logger.error(
                "rollback_failed",
                specialist_type=self.specialist_type,
                error=str(e)
            )
            raise

    def _persist_deployment(self, record: Dict[str, Any]):
        """Persiste registro de deployment no MongoDB."""
        try:
            self._deployments_collection.insert_one(record)
        except Exception as e:
            logger.warning("failed_to_persist_deployment", error=str(e))

    def get_deployment_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna histórico de deployments."""
        docs = self._deployments_collection.find({
            'specialist_type': self.specialist_type
        }).sort('started_at', DESCENDING).limit(limit)

        history = []
        for doc in docs:
            doc.pop('_id', None)
            if 'started_at' in doc:
                doc['started_at'] = doc['started_at'].isoformat()
            if 'completed_at' in doc:
                doc['completed_at'] = doc['completed_at'].isoformat()
            history.append(doc)

        return history

    def get_status(self) -> Dict[str, Any]:
        """Retorna status atual do orchestrator."""
        return {
            'specialist_type': self.specialist_type,
            'is_running': self._is_running,
            'current_deployment_id': self._current_deployment_id,
            'current_rollout_percentage': self._current_rollout_percentage,
            'in_cooldown': self._check_cooldown(),
            'model_version': self.learner.model_version if self.learner.is_fitted else None,
            'learner_state': self.learner.get_model_state(),
            'monitor_status': self.monitor.get_status()
        }

    def close(self):
        """Fecha conexões."""
        self.rollback_manager.close()
        self.monitor.close()
        if self._client:
            self._client.close()


async def main():
    """Ponto de entrada para execução via CLI."""
    import argparse

    parser = argparse.ArgumentParser(description='Online Learning Deployment Orchestrator')
    parser.add_argument('--specialist-type', required=True, help='Tipo do especialista')
    parser.add_argument('--dry-run', action='store_true', help='Modo simulação')
    parser.add_argument('--force', action='store_true', help='Ignorar cooldown')

    args = parser.parse_args()

    config = OnlineLearningConfig()

    logger.info(
        "starting_deployment_orchestrator",
        specialist_type=args.specialist_type,
        dry_run=args.dry_run
    )

    # Nota: Em produção, batch_model seria carregado do MLflow
    # Aqui apenas demonstramos a estrutura
    print(f"Orchestrator para {args.specialist_type} iniciado.")
    print("Em produção, executaria ciclo de deployment.")


if __name__ == '__main__':
    asyncio.run(main())
