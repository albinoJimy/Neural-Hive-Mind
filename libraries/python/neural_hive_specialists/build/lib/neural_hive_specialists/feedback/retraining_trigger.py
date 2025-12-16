"""
Trigger de re-treinamento automático baseado em threshold de feedback.

Este módulo monitora a quantidade de feedback humano e dispara pipeline
MLflow de re-treinamento quando threshold é atingido.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import structlog
from pydantic import BaseModel, Field, ConfigDict
from pymongo import MongoClient, DESCENDING
import mlflow

from ..config import SpecialistConfig
from .feedback_collector import FeedbackCollector
from ..mlflow_client import MLflowClient

logger = structlog.get_logger()


class RetrainingTriggerRecord(BaseModel):
    """
    Schema Pydantic para registro de trigger de re-treinamento.

    Armazena histórico de triggers disparados e seus resultados.
    """

    trigger_id: str = Field(
        default_factory=lambda: f"trigger-{uuid.uuid4().hex[:12]}",
        description="ID único do trigger"
    )
    specialist_type: str = Field(
        ...,
        description="Tipo do especialista"
    )
    triggered_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp do trigger"
    )
    feedback_count: int = Field(
        ...,
        description="Quantidade de feedbacks que disparou trigger"
    )
    feedback_window_days: int = Field(
        ...,
        description="Janela de tempo considerada (dias)"
    )
    mlflow_run_id: Optional[str] = Field(
        default=None,
        description="ID do run MLflow iniciado"
    )
    mlflow_experiment_id: Optional[str] = Field(
        default=None,
        description="ID do experimento MLflow"
    )
    status: str = Field(
        default='pending',
        description="Status do trigger (pending, running, completed, failed)"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Mensagem de erro se falhou"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp de conclusão"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadados (model_version, dataset_size, etc.)"
    )

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class RetrainingTrigger:
    """
    Gerencia trigger automático de re-treinamento baseado em feedback.

    Responsável por:
    - Verificar threshold de feedback periodicamente
    - Disparar pipeline MLflow quando threshold atingido
    - Persistir histórico de triggers no MongoDB
    - Prevenir triggers duplicados (cooldown period)
    """

    def __init__(
        self,
        config: SpecialistConfig,
        feedback_collector: FeedbackCollector,
        mlflow_client: Optional[MLflowClient] = None,
        metrics: 'SpecialistMetrics' = None
    ):
        """
        Inicializa RetrainingTrigger.

        Args:
            config: Configuração do especialista
            feedback_collector: Coletor de feedback
            mlflow_client: Cliente MLflow (opcional, será criado se não fornecido)
            metrics: Instância de SpecialistMetrics (opcional)
        """
        self.config = config
        self.feedback_collector = feedback_collector
        self.mlflow_client = mlflow_client or MLflowClient(config)
        self.metrics = metrics

        # Conectar ao MongoDB para triggers
        self._client = MongoClient(config.mongodb_uri)
        self._db = self._client[config.mongodb_database]
        self._triggers_collection = self._db['retraining_triggers']

        # Criar índices
        self._create_indexes()

        # Emitir threshold configurado
        if self.metrics:
            self.metrics.set_retraining_threshold(config.retraining_feedback_threshold)

        logger.info(
            "RetrainingTrigger initialized",
            threshold=config.retraining_feedback_threshold,
            window_days=config.retraining_feedback_window_days,
            enabled=config.enable_retraining_trigger
        )

    def _create_indexes(self):
        """Cria índices para queries de triggers."""
        try:
            # Índice composto para verificar cooldown
            self._triggers_collection.create_index([
                ('specialist_type', 1),
                ('triggered_at', -1)
            ])

            # Índice para trigger_id único
            self._triggers_collection.create_index([('trigger_id', 1)], unique=True)

            logger.debug("Retraining trigger indexes created")
        except Exception as e:
            logger.warning("Failed to create trigger indexes", error=str(e))

    def _check_cooldown(self, specialist_type: str, cooldown_hours: int = 24) -> bool:
        """
        Verifica se há trigger recente (cooldown period).

        Args:
            specialist_type: Tipo do especialista
            cooldown_hours: Período de cooldown em horas

        Returns:
            True se cooldown ativo (não deve disparar), False caso contrário
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=cooldown_hours)

            # Buscar último trigger bem-sucedido
            last_trigger = self._triggers_collection.find_one(
                {
                    'specialist_type': specialist_type,
                    'status': {'$in': ['completed', 'running']},
                    'triggered_at': {'$gte': cutoff_time}
                },
                sort=[('triggered_at', DESCENDING)]
            )

            if last_trigger:
                time_since_trigger = (datetime.utcnow() - last_trigger['triggered_at']).total_seconds() / 3600
                logger.info(
                    "Cooldown active - recent trigger found",
                    specialist_type=specialist_type,
                    last_trigger_id=last_trigger['trigger_id'],
                    hours_ago=round(time_since_trigger, 1),
                    cooldown_hours=cooldown_hours
                )
                return True

            return False

        except Exception as e:
            logger.error(
                "Error checking cooldown",
                specialist_type=specialist_type,
                error=str(e)
            )
            # Em caso de erro, assumir que cooldown está ativo (seguro)
            return True

    def _should_trigger(self, specialist_type: str) -> Tuple[bool, int]:
        """
        Verifica se deve disparar re-treinamento.

        Args:
            specialist_type: Tipo do especialista

        Returns:
            Tupla (should_trigger, feedback_count)
        """
        # Contar feedbacks recentes
        feedback_count = self.feedback_collector.count_recent_feedback(
            specialist_type=specialist_type,
            window_days=self.config.retraining_feedback_window_days
        )

        # Verificar threshold
        should_trigger = feedback_count >= self.config.retraining_feedback_threshold

        # Emitir métrica de contagem atual
        if self.metrics:
            self.metrics.set_feedback_count_current(feedback_count)

        logger.info(
            "Checked retraining trigger condition",
            specialist_type=specialist_type,
            feedback_count=feedback_count,
            threshold=self.config.retraining_feedback_threshold,
            window_days=self.config.retraining_feedback_window_days,
            should_trigger=should_trigger
        )

        return should_trigger, feedback_count

    def _start_mlflow_run(
        self,
        specialist_type: str,
        feedback_count: int
    ) -> Tuple[str, str]:
        """
        Inicia run MLflow via mlflow.projects.run().

        Args:
            specialist_type: Tipo do especialista
            feedback_count: Quantidade de feedbacks

        Returns:
            Tupla (run_id, experiment_id)
        """
        try:
            # Configurar tracking URI
            mlflow.set_tracking_uri(self.config.mlflow_tracking_uri)

            # Configurar experimento
            experiment_name = f"specialist-retraining-{specialist_type}"
            mlflow.set_experiment(experiment_name)

            # Obter experiment_id após configurar
            experiment = mlflow.get_experiment_by_name(experiment_name)
            experiment_id = experiment.experiment_id

            # Parâmetros para o pipeline
            parameters = {
                'specialist_type': specialist_type,
                'feedback_count': str(feedback_count),
                'window_days': str(self.config.retraining_feedback_window_days),
                'min_feedback_quality': str(self.config.retraining_min_feedback_quality),
                'model_type': self.config.training_model_types[0],  # Usar primeiro tipo
                'hyperparameter_tuning': 'true' if self.config.training_hyperparameter_tuning else 'false',
                'promote_if_better': 'true'
            }

            logger.info(
                "Starting MLflow training run",
                experiment_name=experiment_name,
                experiment_id=experiment_id,
                parameters=parameters
            )

            # Disparar pipeline MLflow
            # Nota: mlflow.projects.run() não aceita experiment_id
            # O experimento já foi configurado via mlflow.set_experiment()
            run = mlflow.projects.run(
                uri=self.config.retraining_mlflow_project_uri,
                parameters=parameters,
                synchronous=False  # Executar em background
            )

            run_id = run.run_id

            logger.info(
                "MLflow training run started successfully",
                run_id=run_id,
                experiment_id=experiment_id,
                specialist_type=specialist_type
            )

            return run_id, experiment_id

        except Exception as e:
            logger.error(
                "Failed to start MLflow run",
                specialist_type=specialist_type,
                error=str(e)
            )
            raise

    def trigger_retraining(
        self,
        specialist_type: str,
        feedback_count: int
    ) -> str:
        """
        Dispara re-treinamento e persiste registro.

        Args:
            specialist_type: Tipo do especialista
            feedback_count: Quantidade de feedbacks

        Returns:
            trigger_id: ID do trigger criado
        """
        # Criar registro de trigger
        trigger_record = RetrainingTriggerRecord(
            specialist_type=specialist_type,
            feedback_count=feedback_count,
            feedback_window_days=self.config.retraining_feedback_window_days,
            status='pending'
        )

        # Persistir registro inicial
        try:
            self._triggers_collection.insert_one(trigger_record.model_dump())
            logger.info(
                "Trigger record created",
                trigger_id=trigger_record.trigger_id,
                specialist_type=specialist_type
            )
        except Exception as e:
            logger.error(
                "Failed to persist trigger record",
                trigger_id=trigger_record.trigger_id,
                error=str(e)
            )
            raise

        # Iniciar run MLflow
        try:
            run_id, experiment_id = self._start_mlflow_run(
                specialist_type=specialist_type,
                feedback_count=feedback_count
            )

            # Atualizar registro com run_id
            self.update_trigger_status(
                trigger_id=trigger_record.trigger_id,
                status='running',
                metadata={
                    'mlflow_run_id': run_id,
                    'mlflow_experiment_id': experiment_id,
                    'started_at': datetime.utcnow().isoformat()
                }
            )

            # Emitir métricas de trigger bem-sucedido
            if self.metrics:
                import time
                self.metrics.increment_retraining_trigger('success')
                self.metrics.set_retraining_last_trigger_timestamp(time.time())

            logger.info(
                "Retraining triggered successfully",
                trigger_id=trigger_record.trigger_id,
                run_id=run_id,
                specialist_type=specialist_type,
                feedback_count=feedback_count
            )

            return trigger_record.trigger_id

        except Exception as e:
            # Atualizar registro com erro
            self.update_trigger_status(
                trigger_id=trigger_record.trigger_id,
                status='failed',
                metadata={
                    'error_message': str(e),
                    'failed_at': datetime.utcnow().isoformat()
                }
            )
            # Emitir métrica de trigger falhado
            if self.metrics:
                self.metrics.increment_retraining_trigger('failed')
            raise

    def update_trigger_status(
        self,
        trigger_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Atualiza status de um trigger.

        Args:
            trigger_id: ID do trigger
            status: Novo status
            metadata: Metadados adicionais
        """
        try:
            update_doc = {
                '$set': {
                    'status': status
                }
            }

            if metadata:
                update_doc['$set']['metadata'] = metadata

            if status in ['completed', 'failed']:
                update_doc['$set']['completed_at'] = datetime.utcnow()

            self._triggers_collection.update_one(
                {'trigger_id': trigger_id},
                update_doc
            )

            logger.info(
                "Trigger status updated",
                trigger_id=trigger_id,
                status=status,
                metadata=metadata
            )

        except Exception as e:
            logger.error(
                "Failed to update trigger status",
                trigger_id=trigger_id,
                error=str(e)
            )

    def get_recent_triggers(
        self,
        specialist_type: str,
        limit: int = 10
    ) -> list:
        """
        Consulta triggers recentes.

        Args:
            specialist_type: Tipo do especialista
            limit: Quantidade máxima de registros

        Returns:
            Lista de triggers recentes
        """
        try:
            results = self._triggers_collection.find(
                {'specialist_type': specialist_type}
            ).sort('triggered_at', DESCENDING).limit(limit)

            triggers = []
            for doc in results:
                doc.pop('_id', None)
                triggers.append(RetrainingTriggerRecord(**doc))

            return triggers

        except Exception as e:
            logger.error(
                "Error retrieving recent triggers",
                specialist_type=specialist_type,
                error=str(e)
            )
            return []

    def check_and_trigger(
        self,
        specialist_type: str,
        force: bool = False
    ) -> Optional[str]:
        """
        Verifica threshold e dispara re-treinamento se necessário.

        Args:
            specialist_type: Tipo do especialista
            force: Ignorar cooldown e disparar forçadamente

        Returns:
            trigger_id se disparado, None caso contrário
        """
        logger.info(
            "Checking retraining trigger",
            specialist_type=specialist_type,
            force=force
        )

        # Verificar se está habilitado
        if not self.config.enable_retraining_trigger:
            logger.info("Retraining trigger disabled")
            return None

        # Verificar threshold
        should_trigger, feedback_count = self._should_trigger(specialist_type)

        if not should_trigger:
            logger.info(
                "Threshold not met - no trigger",
                specialist_type=specialist_type,
                feedback_count=feedback_count,
                threshold=self.config.retraining_feedback_threshold
            )
            return None

        # Verificar cooldown (a menos que force=True)
        if not force and self._check_cooldown(specialist_type):
            logger.info(
                "Cooldown active - skipping trigger",
                specialist_type=specialist_type
            )
            return None

        # Disparar re-treinamento
        try:
            trigger_id = self.trigger_retraining(
                specialist_type=specialist_type,
                feedback_count=feedback_count
            )

            logger.info(
                "Retraining triggered",
                trigger_id=trigger_id,
                specialist_type=specialist_type,
                feedback_count=feedback_count
            )

            return trigger_id

        except Exception as e:
            logger.error(
                "Failed to trigger retraining",
                specialist_type=specialist_type,
                error=str(e)
            )
            return None

    def monitor_run_status(self, trigger_id: str) -> Optional[str]:
        """
        Monitora status de um run MLflow e atualiza trigger se necessário.

        Args:
            trigger_id: ID do trigger a monitorar

        Returns:
            Novo status do trigger se atualizado, None caso contrário
        """
        try:
            # Buscar trigger
            trigger = self._triggers_collection.find_one({'trigger_id': trigger_id})
            if not trigger:
                logger.warning("Trigger not found", trigger_id=trigger_id)
                return None

            if trigger['status'] != 'running':
                logger.debug("Trigger not in running state", trigger_id=trigger_id, status=trigger['status'])
                return None

            mlflow_run_id = trigger.get('metadata', {}).get('mlflow_run_id')
            if not mlflow_run_id:
                logger.warning("Trigger without MLflow run ID", trigger_id=trigger_id)
                return None

            # Verificar status no MLflow
            from mlflow.tracking import MlflowClient
            client = MlflowClient(tracking_uri=self.config.mlflow_tracking_uri)
            run = client.get_run(mlflow_run_id)
            run_status = run.info.status

            new_status = None

            if run_status == 'FINISHED':
                # Run completado
                end_time = datetime.fromtimestamp(run.info.end_time / 1000)
                start_time = datetime.fromtimestamp(run.info.start_time / 1000)
                duration = (end_time - start_time).total_seconds()

                metadata = {
                    'duration_seconds': duration,
                    'mlflow_status': run_status,
                    'completed_at': datetime.utcnow().isoformat()
                }

                # Extrair métricas se disponíveis
                metrics = run.data.metrics
                if 'precision' in metrics:
                    metadata['model_precision'] = metrics['precision']
                if 'recall' in metrics:
                    metadata['model_recall'] = metrics['recall']
                if 'f1' in metrics:
                    metadata['model_f1'] = metrics['f1']

                self.update_trigger_status(trigger_id, 'completed', metadata)
                new_status = 'completed'

                # Emitir métricas
                if self.metrics:
                    self.metrics.observe_retraining_run_duration(duration)
                    if 'precision' in metrics:
                        self.metrics.set_retraining_model_performance('precision', metrics['precision'])
                    if 'recall' in metrics:
                        self.metrics.set_retraining_model_performance('recall', metrics['recall'])
                    if 'f1' in metrics:
                        self.metrics.set_retraining_model_performance('f1', metrics['f1'])

                logger.info(
                    "Retraining run completed",
                    trigger_id=trigger_id,
                    mlflow_run_id=mlflow_run_id,
                    duration_seconds=duration
                )

            elif run_status in ['FAILED', 'KILLED']:
                # Run falhou ou foi cancelado
                metadata = {
                    'mlflow_status': run_status,
                    'error_message': f'Run MLflow terminou com status: {run_status}'
                }
                self.update_trigger_status(trigger_id, 'failed', metadata)
                new_status = 'failed'

                logger.error(
                    "Retraining run failed",
                    trigger_id=trigger_id,
                    mlflow_run_id=mlflow_run_id,
                    status=run_status
                )

            return new_status

        except Exception as e:
            logger.error(
                "Error monitoring run status",
                trigger_id=trigger_id,
                error=str(e)
            )
            return None

    def close(self):
        """Fecha conexão com MongoDB."""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed for retraining trigger")
