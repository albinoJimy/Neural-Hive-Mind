"""
Training Pipeline para treinamento incremental de modelos ML.

Orquestra ciclo completo de treinamento: query de dados históricos,
delegação de treinamento para modelos especializados, e retreinamento periódico.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


class TrainingPipeline:
    """
    Pipeline de treinamento incremental para modelos ML.

    Responsável por:
    - Query de dados históricos do MongoDB
    - Delegação de treinamento para DurationPredictor e AnomalyDetector
      (cada predictor gerencia sua própria preparação de features)
    - Agendamento de retreinamento periódico
    """

    def __init__(
        self,
        config,
        mongodb_client,
        model_registry,
        duration_predictor,
        anomaly_detector,
        metrics,
        drift_detector=None
    ):
        """
        Inicializa Training Pipeline.

        Args:
            config: Configuração do orchestrator
            mongodb_client: Cliente MongoDB
            model_registry: ModelRegistry
            duration_predictor: DurationPredictor instance
            anomaly_detector: AnomalyDetector instance
            metrics: OrchestratorMetrics
            drift_detector: DriftDetector instance (opcional)
        """
        self.config = config
        self.mongodb_client = mongodb_client
        self.model_registry = model_registry
        self.duration_predictor = duration_predictor
        self.anomaly_detector = anomaly_detector
        self.metrics = metrics
        self.drift_detector = drift_detector
        self.logger = logger.bind(component="training_pipeline")

        # Task de treinamento periódico
        self._training_task: Optional[asyncio.Task] = None
        self._stop_training = False

    def run_training_cycle_sync(
        self,
        window_days: Optional[int] = None,
        backfill_errors: bool = False
    ) -> Dict[str, Any]:
        """
        Wrapper síncrono para run_training_cycle (para uso em contextos síncronos).

        IMPORTANTE: Use este método apenas em scripts standalone ou contextos
        que não tenham um event loop rodando. Para uso dentro de aplicações
        async (FastAPI, Temporal), use diretamente run_training_cycle com await.

        Args:
            window_days: Janela de dados em dias (default: config value)
            backfill_errors: Se True, calcula erros históricos e registra em batch

        Returns:
            Dict com métricas de ambos os modelos
        """
        return asyncio.run(self.run_training_cycle(window_days, backfill_errors))

    async def run_training_cycle(
        self,
        window_days: Optional[int] = None,
        backfill_errors: bool = False
    ) -> Dict[str, Any]:
        """
        Executa ciclo completo de treinamento (versão assíncrona).

        Steps:
        1. Query dados históricos do MongoDB para validar volume mínimo
        2. Treina DurationPredictor (feature engineering interno)
        3. Treina AnomalyDetector (feature engineering interno)
        4. Consolida métricas de ambos os modelos
        5. (Opcional) Backfill de erros de predição históricos

        Args:
            window_days: Janela de dados em dias (default: config value)
            backfill_errors: Se True, calcula erros históricos e registra em batch

        Returns:
            Dict com métricas de ambos os modelos
        """
        import time

        start_time = time.time()

        try:
            window_days = window_days or self.config.ml_training_window_days

            self.logger.info(
                "training_cycle_started",
                window_days=window_days,
                backfill_errors=backfill_errors
            )

            # Query dados de treino
            df = await self._query_training_data(window_days)

            if len(df) < self.config.ml_min_training_samples:
                self.logger.warning(
                    "insufficient_training_data",
                    samples=len(df),
                    required=self.config.ml_min_training_samples
                )
                return {
                    'status': 'skipped',
                    'reason': 'insufficient_data',
                    'samples': len(df)
                }

            # Backfill de erros ML históricos (opcional)
            backfill_stats = None
            if backfill_errors:
                backfill_stats = await self._backfill_prediction_errors(df)

            # Treina modelos em paralelo
            duration_metrics, anomaly_metrics = await asyncio.gather(
                self.duration_predictor.train_model(window_days),
                self.anomaly_detector.train_model(window_days),
                return_exceptions=True
            )

            # Handle exceptions
            if isinstance(duration_metrics, Exception):
                self.logger.error("duration_training_failed", error=str(duration_metrics))
                duration_metrics = {}

            if isinstance(anomaly_metrics, Exception):
                self.logger.error("anomaly_training_failed", error=str(anomaly_metrics))
                anomaly_metrics = {}

            # Salvar baseline de features para drift detection
            if self.drift_detector and getattr(self.config, 'ml_drift_baseline_enabled', True):
                try:
                    await self._save_feature_baseline(df, duration_metrics)
                except Exception as e:
                    self.logger.error("failed_to_save_feature_baseline", error=str(e))

            # Consolida métricas
            training_duration = time.time() - start_time

            results = {
                'status': 'completed',
                'training_duration_seconds': training_duration,
                'samples_used': len(df),
                'window_days': window_days,
                'timestamp': datetime.utcnow().isoformat(),
                'duration_predictor': duration_metrics,
                'anomaly_detector': anomaly_metrics,
                'backfill_stats': backfill_stats,
                'models_promoted': []
            }

            # Verificar modelos promovidos
            if duration_metrics.get('promoted'):
                results['models_promoted'].append('duration-predictor')
            if anomaly_metrics.get('promoted'):
                results['models_promoted'].append('anomaly-detector')

            # Log sumário
            self.logger.info(
                "training_cycle_completed",
                duration_seconds=training_duration,
                samples=len(df),
                duration_mae_pct=duration_metrics.get('mae_percentage'),
                anomaly_precision=anomaly_metrics.get('precision'),
                backfill_errors=backfill_stats.get('processed') if backfill_stats else 0,
                models_promoted=results['models_promoted']
            )

            return results

        except Exception as e:
            self.logger.error("training_cycle_failed", error=str(e))
            return {
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _query_training_data(self, window_days: int) -> pd.DataFrame:
        """
        Query dados de treino do MongoDB e converte para DataFrame.

        Campos buscados:
        - ticket_id, task_type, risk_band, qos, sla
        - required_capabilities, parameters
        - estimated_duration_ms, actual_duration_ms
        - created_at, started_at, completed_at
        - status, retry_count

        Args:
            window_days: Janela de dados em dias

        Returns:
            DataFrame com dados de tickets
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=window_days)

            # Query MongoDB
            tickets = await self.mongodb_client.db['execution_tickets'].find({
                'completed_at': {'$gte': cutoff_date}
            }).to_list(None)

            self.logger.info(
                "training_data_queried",
                tickets=len(tickets),
                window_days=window_days
            )

            # Converte para DataFrame
            if not tickets:
                return pd.DataFrame()

            df = pd.DataFrame(tickets)

            # Garante colunas necessárias
            required_columns = [
                'ticket_id', 'task_type', 'risk_band', 'qos', 'sla',
                'required_capabilities', 'parameters',
                'estimated_duration_ms', 'actual_duration_ms',
                'created_at', 'completed_at', 'status'
            ]

            # Adiciona colunas faltantes com None
            for col in required_columns:
                if col not in df.columns:
                    df[col] = None

            return df

        except Exception as e:
            self.logger.error("query_training_data_failed", error=str(e))
            return pd.DataFrame()

    async def schedule_periodic_training(self, interval_hours: Optional[int] = None):
        """
        Agenda treinamento periódico em background.

        Args:
            interval_hours: Intervalo de retreinamento (default: config value)
        """
        interval_hours = interval_hours or self.config.ml_training_interval_hours

        self.logger.info(
            "periodic_training_scheduled",
            interval_hours=interval_hours
        )

        self._training_task = asyncio.create_task(
            self._training_loop(interval_hours)
        )

    async def _training_loop(self, interval_hours: int):
        """
        Loop de treinamento periódico.

        Args:
            interval_hours: Intervalo entre treinamentos
        """
        interval_seconds = interval_hours * 3600

        while not self._stop_training:
            try:
                # Aguarda intervalo
                await asyncio.sleep(interval_seconds)

                if self._stop_training:
                    break

                # Executa ciclo de treinamento
                self.logger.info("periodic_training_triggered")

                results = await self.run_training_cycle()

                if results.get('status') == 'completed':
                    self.logger.info(
                        "periodic_training_completed",
                        duration_mae=results.get('duration_predictor', {}).get('mae_percentage'),
                        anomaly_precision=results.get('anomaly_detector', {}).get('precision')
                    )
                else:
                    self.logger.warning(
                        "periodic_training_incomplete",
                        status=results.get('status'),
                        reason=results.get('reason')
                    )

            except asyncio.CancelledError:
                self.logger.info("training_loop_cancelled")
                break
            except Exception as e:
                self.logger.error("training_loop_error", error=str(e))
                # Continua loop mesmo com erro

    async def stop_periodic_training(self):
        """
        Para loop de treinamento periódico.
        """
        self._stop_training = True

        if self._training_task:
            self._training_task.cancel()
            try:
                await self._training_task
            except asyncio.CancelledError:
                pass

        self.logger.info("periodic_training_stopped")

    async def _save_feature_baseline(
        self,
        df: pd.DataFrame,
        duration_metrics: Dict[str, Any]
    ) -> None:
        """
        Salva baseline de features para detecção de drift.

        Args:
            df: DataFrame com tickets de treino
            duration_metrics: Métricas do modelo de duração
        """
        try:
            from src.ml.feature_engineering import extract_ticket_features

            # Extrair features de todos os tickets
            features_data = []
            target_values = []

            for idx, row in df.iterrows():
                ticket_dict = row.to_dict()
                features = extract_ticket_features(ticket_dict)

                if features:
                    features_data.append(features)

                    # Coletar target values
                    actual_duration = row.get('actual_duration_ms')
                    if actual_duration and actual_duration > 0:
                        target_values.append(float(actual_duration))

            if not features_data or not target_values:
                self.logger.warning("No features or targets to save baseline")
                return

            # Obter MAE do treinamento
            training_mae = duration_metrics.get('mae', 0)

            # Salvar baseline usando drift detector
            self.drift_detector.save_feature_baseline(
                features_data=features_data,
                target_values=target_values,
                training_mae=training_mae,
                model_name="duration-predictor",
                version=duration_metrics.get('version', 'latest')
            )

            self.logger.info(
                "feature_baseline_saved",
                features_count=len(features_data),
                target_count=len(target_values),
                training_mae=training_mae
            )

        except Exception as e:
            self.logger.error("failed_to_save_feature_baseline", error=str(e))
            raise

    async def _backfill_prediction_errors(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Backfill de erros de predição para tickets históricos.

        Calcula erros (actual - predicted) para tickets que têm ambos os campos
        e registra no Prometheus em batch para alimentar dashboards e alertas.

        Args:
            df: DataFrame com tickets históricos

        Returns:
            Dict com estatísticas de backfill incluindo erros extremos
        """
        try:
            self.logger.info(
                "ml_error_backfill_started",
                total_tickets=len(df)
            )

            processed = 0
            skipped_no_actual = 0
            skipped_no_predicted = 0
            skipped_invalid = 0
            errors_recorded = []
            extreme_errors = []

            for idx, row in df.iterrows():
                try:
                    # Obter actual_duration_ms
                    actual_duration_ms = row.get('actual_duration_ms')

                    # Fallback para calcular de timestamps
                    if pd.isna(actual_duration_ms) or actual_duration_ms is None:
                        started_at = row.get('started_at')
                        completed_at = row.get('completed_at')
                        if started_at and completed_at:
                            actual_duration_ms = completed_at - started_at
                        else:
                            skipped_no_actual += 1
                            continue

                    # Validar actual > 0
                    if actual_duration_ms <= 0:
                        skipped_invalid += 1
                        continue

                    # Obter predicted_duration_ms
                    allocation_metadata = row.get('allocation_metadata', {})
                    if isinstance(allocation_metadata, dict):
                        predicted_duration_ms = allocation_metadata.get('predicted_duration_ms')
                    else:
                        predicted_duration_ms = None

                    # Fallback para predictions field
                    if predicted_duration_ms is None:
                        predictions = row.get('predictions', {})
                        if isinstance(predictions, dict):
                            predicted_duration_ms = predictions.get('duration_ms')

                    # Fallback para estimated
                    if predicted_duration_ms is None:
                        predicted_duration_ms = row.get('estimated_duration_ms')

                    # Validar predicted > 0
                    if predicted_duration_ms is None or predicted_duration_ms <= 0:
                        skipped_no_predicted += 1
                        continue

                    # Calcular erro
                    error_ms = actual_duration_ms - predicted_duration_ms
                    abs_error = abs(error_ms)

                    # Registrar no Prometheus
                    self.metrics.record_ml_prediction_error_with_logging(
                        model_type='duration',
                        error_ms=error_ms,
                        ticket_id=row.get('ticket_id', f'backfill_{idx}'),
                        predicted_ms=predicted_duration_ms,
                        actual_ms=actual_duration_ms
                    )

                    errors_recorded.append(abs_error)

                    # Detectar erros extremos (>3x predição)
                    if abs_error > (3 * predicted_duration_ms):
                        extreme_errors.append({
                            'ticket_id': row.get('ticket_id'),
                            'predicted_ms': predicted_duration_ms,
                            'actual_ms': actual_duration_ms,
                            'error_ms': error_ms,
                            'error_ratio': abs_error / predicted_duration_ms
                        })

                    processed += 1

                except Exception as e:
                    self.logger.warning(
                        "ml_error_backfill_ticket_failed",
                        ticket_id=row.get('ticket_id'),
                        error=str(e)
                    )
                    continue

            # Calcular estatísticas incluindo percentis
            errors_series = pd.Series(errors_recorded) if errors_recorded else pd.Series([])

            stats = {
                'processed': processed,
                'skipped_no_actual': skipped_no_actual,
                'skipped_no_predicted': skipped_no_predicted,
                'skipped_invalid': skipped_invalid,
                'total_tickets': len(df),
                'mean_error_ms': float(errors_series.mean()) if len(errors_series) > 0 else 0.0,
                'median_error_ms': float(errors_series.median()) if len(errors_series) > 0 else 0.0,
                'p50_error_ms': float(errors_series.quantile(0.50)) if len(errors_series) > 0 else 0.0,
                'p95_error_ms': float(errors_series.quantile(0.95)) if len(errors_series) > 0 else 0.0,
                'p99_error_ms': float(errors_series.quantile(0.99)) if len(errors_series) > 0 else 0.0,
                'extreme_errors_count': len(extreme_errors),
                'extreme_errors': extreme_errors[:10]  # Limitar para não sobrecarregar logs
            }

            # Salvar histórico de backfill no MongoDB
            if processed > 0:
                retention_days = getattr(self.config, 'ml_backfill_history_retention_days', 90)
                try:
                    backfill_record = {
                        'timestamp': datetime.utcnow(),
                        'stats': stats,
                        'retention_until': datetime.utcnow() + timedelta(days=retention_days)
                    }
                    await self.mongodb_client.db['ml_backfill_history'].insert_one(backfill_record)
                except Exception as e:
                    self.logger.warning("failed_to_save_backfill_history", error=str(e))

            self.logger.info(
                "ml_error_backfill_completed",
                **{k: v for k, v in stats.items() if k != 'extreme_errors'}
            )

            return stats

        except Exception as e:
            self.logger.error("ml_error_backfill_failed", error=str(e))
            return {
                'processed': 0,
                'error': str(e)
            }
