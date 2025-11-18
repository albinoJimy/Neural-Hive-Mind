"""
Job de treinamento standalone para execução via CronJob Kubernetes.

Este script é executado independentemente da aplicação FastAPI principal
e do worker Temporal, permitindo treinamento confiável e isolado.
"""

import sys
import logging
import asyncio
import structlog
from datetime import datetime
from typing import Dict, Any

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from src.config.settings import get_settings
from src.clients.mongodb_client import MongoDBClient
from src.ml.model_registry import ModelRegistry
from src.ml.duration_predictor import DurationPredictor
from src.ml.anomaly_detector import AnomalyDetector
from src.ml.training_pipeline import TrainingPipeline
from src.observability.metrics import get_metrics


# Configurar logging estruturado
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


def push_metrics_to_gateway(
    metrics: Dict[str, Any],
    pushgateway_url: str,
    job_name: str = "ml_training"
) -> None:
    """
    Publica métricas de treinamento no Prometheus Pushgateway.

    Args:
        metrics: Métricas do treinamento
        pushgateway_url: URL do Pushgateway
        job_name: Nome do job para label
    """
    try:
        registry = CollectorRegistry()

        # Métricas de sucesso/falha
        training_status = Gauge(
            'orchestration_ml_training_status',
            'Status do último treinamento (1=success, 0=failure)',
            registry=registry
        )
        training_status.set(1 if metrics.get('status') == 'completed' else 0)

        # Métricas de performance do modelo de duração
        if 'duration_predictor' in metrics:
            duration_mae = Gauge(
                'orchestration_ml_duration_model_mae',
                'MAE do modelo de predição de duração',
                registry=registry
            )
            duration_mae.set(metrics['duration_predictor'].get('mae', 0))

            duration_samples = Gauge(
                'orchestration_ml_training_samples_duration',
                'Número de amostras usadas no treinamento de duração',
                registry=registry
            )
            duration_samples.set(metrics['duration_predictor'].get('samples', 0))

        # Métricas de performance do detector de anomalias
        if 'anomaly_detector' in metrics:
            anomaly_precision = Gauge(
                'orchestration_ml_anomaly_model_precision',
                'Precisão do detector de anomalias',
                registry=registry
            )
            anomaly_precision.set(metrics['anomaly_detector'].get('precision', 0))

            anomaly_samples = Gauge(
                'orchestration_ml_training_samples_anomaly',
                'Número de amostras usadas no treinamento de anomalias',
                registry=registry
            )
            anomaly_samples.set(metrics['anomaly_detector'].get('samples', 0))

        # Timestamp do treinamento
        training_timestamp = Gauge(
            'orchestration_ml_training_timestamp',
            'Timestamp do último treinamento',
            registry=registry
        )
        training_timestamp.set(datetime.utcnow().timestamp())

        # Push para gateway
        push_to_gateway(
            pushgateway_url,
            job=job_name,
            registry=registry
        )

        logger.info("metrics_pushed_to_gateway", url=pushgateway_url, job=job_name)

    except Exception as e:
        logger.error("failed_to_push_metrics", error=str(e), exc_info=True)


def main() -> int:
    """
    Função principal do job de treinamento.

    Returns:
        Código de saída (0=sucesso, 1=erro)
    """
    config = get_settings()

    logger.info(
        "ml_training_job_started",
        window_days=config.ml_training_window_days,
        min_samples=config.ml_min_training_samples,
        mlflow_uri=config.mlflow_tracking_uri
    )

    mongodb_client = None

    try:
        # Inicializar MongoDB
        logger.info("initializing_mongodb_client")
        mongodb_client = MongoDBClient(config)

        # Inicializar Model Registry
        logger.info("initializing_model_registry")
        model_registry = ModelRegistry(config)

        # Inicializar preditores
        logger.info("initializing_predictors")
        duration_predictor = DurationPredictor(
            config=config,
            mongodb_client=mongodb_client
        )

        anomaly_detector = AnomalyDetector(
            config=config,
            mongodb_client=mongodb_client
        )

        # Obter instância de métricas
        metrics = get_metrics()

        # Criar pipeline de treinamento
        logger.info("creating_training_pipeline")
        training_pipeline = TrainingPipeline(
            config=config,
            mongodb_client=mongodb_client,
            model_registry=model_registry,
            duration_predictor=duration_predictor,
            anomaly_detector=anomaly_detector,
            metrics=metrics
        )

        # Executar ciclo de treinamento
        logger.info("starting_training_cycle")
        start_time = datetime.utcnow()

        result = asyncio.run(training_pipeline.run_training_cycle(
            window_days=config.ml_training_window_days,
            backfill_errors=config.ml_backfill_errors if hasattr(config, 'ml_backfill_errors') else False
        ))

        end_time = datetime.utcnow()
        duration_seconds = (end_time - start_time).total_seconds()

        logger.info(
            "training_cycle_completed",
            status=result.get('status'),
            duration_seconds=duration_seconds,
            duration_predictor_mae=result.get('duration_predictor', {}).get('mae'),
            duration_predictor_samples=result.get('duration_predictor', {}).get('samples'),
            anomaly_detector_precision=result.get('anomaly_detector', {}).get('precision'),
            anomaly_detector_samples=result.get('anomaly_detector', {}).get('samples'),
            models_promoted=result.get('models_promoted', [])
        )

        # Publicar métricas no Pushgateway
        if hasattr(config, 'prometheus_pushgateway_url'):
            push_metrics_to_gateway(
                result,
                config.prometheus_pushgateway_url
            )

        # Registrar execução do job nas métricas padrão
        job_status = 'success' if result.get('status') == 'completed' else 'failure'
        if result.get('status') == 'skipped':
            job_status = 'success'  # Dados insuficientes não é falha

        metrics.record_training_job(
            status=job_status,
            trigger='scheduled'
        )

        # Registrar volume de amostras utilizadas
        if result.get('samples_used'):
            metrics.record_training_samples(
                model_name='duration-predictor',
                samples=result.get('samples_used'),
                data_source='mongodb'
            )

        # Verificar se treinamento foi bem-sucedido
        if result.get('status') == 'skipped':
            logger.warning(
                "training_skipped",
                reason=result.get('reason'),
                message=result.get('message')
            )
            # Retornar sucesso mesmo quando skipado (dados insuficientes não é erro)
            return 0

        if result.get('status') != 'completed':
            logger.error(
                "training_failed",
                status=result.get('status'),
                error=result.get('error')
            )
            # Registrar falha nas métricas
            metrics.record_training_job(
                status='failure',
                trigger='scheduled'
            )
            return 1

        # Verificar qualidade dos modelos
        duration_mae_pct = result.get('duration_predictor', {}).get('mae_percentage', 100)
        anomaly_precision = result.get('anomaly_detector', {}).get('precision', 0)

        if duration_mae_pct > 50:
            logger.warning(
                "duration_model_poor_quality",
                mae_percentage=duration_mae_pct,
                threshold=50
            )

        if anomaly_precision < 0.5:
            logger.warning(
                "anomaly_model_poor_quality",
                precision=anomaly_precision,
                threshold=0.5
            )

        # Log de tickets com erros extremos (se backfill habilitado)
        if 'backfill_stats' in result:
            backfill = result['backfill_stats']
            if backfill.get('extreme_errors', []):
                logger.warning(
                    "extreme_prediction_errors_detected",
                    count=len(backfill['extreme_errors']),
                    tickets=backfill['extreme_errors'][:5]  # Log apenas os 5 primeiros
                )

        logger.info("ml_training_job_completed_successfully")
        return 0

    except Exception as e:
        logger.error(
            "ml_training_job_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )

        # Registrar falha nas métricas padrão
        try:
            metrics = get_metrics()
            metrics.record_training_job(
                status='failure',
                trigger='scheduled'
            )
        except:
            pass  # Não falhar se registro de métricas falhar

        # Publicar métrica de falha
        if hasattr(config, 'prometheus_pushgateway_url'):
            try:
                push_metrics_to_gateway(
                    {'status': 'failed', 'error': str(e)},
                    config.prometheus_pushgateway_url
                )
            except:
                pass  # Não falhar se push de métricas falhar

        return 1

    finally:
        # Cleanup
        if mongodb_client:
            try:
                mongodb_client.close()
                logger.info("mongodb_client_closed")
            except Exception as e:
                logger.error("failed_to_close_mongodb", error=str(e))


if __name__ == "__main__":
    sys.exit(main())
