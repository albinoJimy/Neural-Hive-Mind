"""
Job de detecção de drift standalone para execução via CronJob Kubernetes.

Este script é executado independentemente da aplicação FastAPI principal
para monitorar drift de modelos ML de forma periódica.
"""

import sys
import structlog
from datetime import datetime
from typing import Dict, Any

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from src.config.settings import get_settings
from src.clients.mongodb_client import MongoDBClient
from src.ml.drift_detector import DriftDetector
from src.observability.metrics import OrchestratorMetrics, get_metrics


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


def push_drift_metrics_to_gateway(
    drift_report: Dict[str, Any],
    pushgateway_url: str,
    job_name: str = "ml_drift_detection"
) -> None:
    """
    Publica métricas de drift no Prometheus Pushgateway.

    Args:
        drift_report: Relatório de drift
        pushgateway_url: URL do Pushgateway
        job_name: Nome do job para label
    """
    try:
        registry = CollectorRegistry()

        # Status geral de drift
        drift_status_metric = Gauge(
            'orchestration_ml_drift_overall_status',
            'Status geral de drift (0=ok, 1=warning, 2=critical)',
            registry=registry
        )
        status_value = {'ok': 0, 'warning': 1, 'critical': 2}.get(
            drift_report.get('overall_status', 'ok'), 0
        )
        drift_status_metric.set(status_value)

        # Feature drift - PSI máximo
        if drift_report.get('feature_drift'):
            max_psi = max(drift_report['feature_drift'].values(), default=0)
            feature_drift_metric = Gauge(
                'orchestration_ml_drift_feature_max_psi',
                'PSI máximo entre todas as features',
                registry=registry
            )
            feature_drift_metric.set(max_psi)

        # Prediction drift - ratio MAE
        if drift_report.get('prediction_drift'):
            mae_ratio = drift_report['prediction_drift'].get('drift_ratio', 0)
            prediction_drift_metric = Gauge(
                'orchestration_ml_drift_prediction_ratio',
                'Ratio MAE atual / MAE treino',
                registry=registry
            )
            prediction_drift_metric.set(mae_ratio)

        # Target drift - p-value K-S
        if drift_report.get('target_drift'):
            p_value = drift_report['target_drift'].get('p_value', 1.0)
            target_drift_metric = Gauge(
                'orchestration_ml_drift_target_pvalue',
                'P-value do K-S test',
                registry=registry
            )
            target_drift_metric.set(p_value)

        # Timestamp do check
        drift_timestamp = Gauge(
            'orchestration_ml_drift_check_timestamp',
            'Timestamp do último drift check',
            registry=registry
        )
        drift_timestamp.set(datetime.utcnow().timestamp())

        # Push para gateway
        push_to_gateway(
            pushgateway_url,
            job=job_name,
            registry=registry
        )

        logger.info("drift_metrics_pushed_to_gateway", url=pushgateway_url, job=job_name)

    except Exception as e:
        logger.error("failed_to_push_drift_metrics", error=str(e), exc_info=True)


def main() -> int:
    """
    Função principal do job de drift detection.

    Returns:
        Código de saída (0=sucesso, 1=erro)
    """
    config = get_settings()

    logger.info(
        "ml_drift_job_started",
        check_window_days=config.ml_drift_check_window_days,
        psi_threshold=config.ml_drift_psi_threshold,
        mae_ratio_threshold=config.ml_drift_mae_ratio_threshold
    )

    mongodb_client = None
    metrics = None
    drift_report = None

    try:
        # Inicializar MongoDB
        logger.info("initializing_mongodb_client")
        mongodb_client = MongoDBClient(config)

        # Inicializar métricas (usar singleton get_metrics) - EARLY
        metrics = get_metrics()

        # Inicializar Drift Detector
        logger.info("initializing_drift_detector")
        drift_detector = DriftDetector(
            config=config,
            mongodb_client=mongodb_client,
            metrics=metrics
        )

        # Executar drift check
        logger.info("running_drift_check")
        drift_report = drift_detector.run_drift_check()

        # Registrar scores de drift individuais via métricas padrão
        # Feature drift - PSI scores
        if drift_report.get('feature_drift'):
            for feature, psi_score in drift_report['feature_drift'].items():
                metrics.record_drift_score(
                    drift_type='feature',
                    score=psi_score,
                    feature=feature,
                    model_name='duration-predictor'
                )

        # Prediction drift - MAE ratio
        if drift_report.get('prediction_drift'):
            mae_ratio = drift_report['prediction_drift'].get('drift_ratio', 0)
            if mae_ratio > 0:
                metrics.record_drift_score(
                    drift_type='prediction',
                    score=mae_ratio,
                    feature='',
                    model_name='duration-predictor'
                )

        # Target drift - K-S test statistic
        if drift_report.get('target_drift'):
            ks_statistic = drift_report['target_drift'].get('ks_statistic', 0.0)
            if ks_statistic > 0:
                metrics.record_drift_score(
                    drift_type='target',
                    score=ks_statistic,
                    feature='',
                    model_name='duration-predictor'
                )

        # Registrar status geral do drift nas métricas
        overall_status = drift_report.get('overall_status', 'ok')

        # Update drift status for each type based on report
        if drift_report.get('feature_drift'):
            metrics.update_drift_status(
                model_name='duration-predictor',
                drift_type='feature',
                status=overall_status
            )

        if drift_report.get('prediction_drift'):
            metrics.update_drift_status(
                model_name='duration-predictor',
                drift_type='prediction',
                status=overall_status
            )

        if drift_report.get('target_drift'):
            metrics.update_drift_status(
                model_name='duration-predictor',
                drift_type='target',
                status=overall_status
            )

        # Update overall drift status
        metrics.update_drift_status(
            model_name='duration-predictor',
            drift_type='overall',
            status=overall_status
        )

        # Determinar job status baseado em overall_status
        # 'critical' drift é warning (alerta), não é falha de execução
        job_status = 'success' if overall_status != 'critical' else 'warning'

        # Registrar execução do job nas métricas padrão
        metrics.record_training_job(
            status=job_status,
            trigger='scheduled'
        )

        # Log relatório em JSON
        logger.info(
            "drift_check_completed",
            overall_status=drift_report.get('overall_status'),
            window_days=drift_report.get('window_days'),
            feature_drift_count=len(drift_report.get('feature_drift', {})),
            prediction_drift_ratio=drift_report.get('prediction_drift', {}).get('drift_ratio'),
            target_drift_pvalue=drift_report.get('target_drift', {}).get('p_value'),
            recommendations_count=len(drift_report.get('recommendations', []))
        )

        # Log recomendações
        for rec in drift_report.get('recommendations', []):
            logger.info("drift_recommendation", message=rec)

        # Publicar métricas no Pushgateway
        if hasattr(config, 'prometheus_pushgateway_url'):
            push_drift_metrics_to_gateway(
                drift_report,
                config.prometheus_pushgateway_url
            )

        # Determinar código de saída baseado em status
        if overall_status == 'critical':
            logger.warning("critical_drift_detected")
            # Retornar 0 mesmo em drift crítico (não é erro de execução)
            # Alertas Prometheus devem ser configurados para notificar

        logger.info("ml_drift_job_completed_successfully")
        return 0

    except Exception as e:
        logger.error(
            "ml_drift_job_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )

        # Registrar falha do job nas métricas padrão (mesmo em exceção)
        try:
            if metrics is None:
                metrics = get_metrics()
            metrics.record_training_job(
                status='failure',
                trigger='scheduled'
            )
        except Exception as metrics_error:
            logger.warning("failed_to_record_failure_metrics", error=str(metrics_error))

        # Publicar métrica de falha no Pushgateway
        if hasattr(config, 'prometheus_pushgateway_url'):
            try:
                push_drift_metrics_to_gateway(
                    {'overall_status': 'error', 'error': str(e)},
                    config.prometheus_pushgateway_url
                )
            except Exception as push_error:
                logger.warning("failed_to_push_failure_metrics", error=str(push_error))

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
