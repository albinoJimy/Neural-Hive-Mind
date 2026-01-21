"""
Script para executar validação contínua via CronJob.

Popula janelas do MongoDB, computa métricas, verifica thresholds
e publica métricas no Prometheus Pushgateway.
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime
import structlog
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

from src.config.settings import get_settings
from src.ml.continuous_validator import ContinuousValidator
from motor.motor_asyncio import AsyncIOMotorClient

logger = structlog.get_logger(__name__)


async def run_validation(
    populate_from_mongodb: bool = True,
    compute_metrics: bool = True,
    check_thresholds: bool = True,
    verbose: bool = False
):
    """
    Executa validação contínua.

    Args:
        populate_from_mongodb: Popular janelas do MongoDB
        compute_metrics: Computar métricas
        check_thresholds: Verificar thresholds e gerar alertas
        verbose: Logging verboso
    """
    settings = get_settings()

    if verbose:
        logger.info(
            "continuous_validation_started",
            mongodb_uri=settings.mongodb_uri[:20] + "...",  # Truncar por segurança
            use_mongodb=getattr(settings, 'ml_validation_use_mongodb', True),
            windows=getattr(settings, 'ml_validation_windows', ['1h', '24h', '7d'])
        )

    # Conectar MongoDB
    mongodb_uri = settings.mongodb_uri
    mongodb_client = AsyncIOMotorClient(mongodb_uri)
    mongodb_client.db = mongodb_client[settings.mongodb_database]

    try:
        # Criar validador
        validator = ContinuousValidator(
            config=settings,
            mongodb_client=mongodb_client,
            clickhouse_client=None,
            metrics=None,  # Usaremos Pushgateway
            alert_handlers=[]
        )

        # Popular do MongoDB
        if populate_from_mongodb:
            logger.info("populating_windows_from_mongodb")
            await validator.populate_windows_from_mongodb()

        # Computar métricas
        if compute_metrics:
            logger.info("computing_metrics")
            results = await validator.compute_all_metrics()

            # Publicar no Pushgateway
            await publish_to_pushgateway(results, settings)

            # Verificar thresholds
            if check_thresholds:
                logger.info("checking_thresholds")
                await validator._check_thresholds(results)

            logger.info(
                "validation_completed",
                windows=list(results.get('windows', {}).keys()),
                latency_windows=list(results.get('latency_windows', {}).keys())
            )

            # Log de métricas para debug
            if verbose:
                for window_name, metrics in results.get('windows', {}).items():
                    logger.info(
                        "window_metrics",
                        window=window_name,
                        mae=metrics.get('mae'),
                        mae_pct=metrics.get('mae_pct'),
                        r2=metrics.get('r2'),
                        sample_count=metrics.get('sample_count')
                    )

    except Exception as e:
        logger.error("validation_failed", error=str(e))
        raise

    finally:
        mongodb_client.close()


async def publish_to_pushgateway(results: dict, settings):
    """Publica métricas no Prometheus Pushgateway."""
    pushgateway_url = getattr(
        settings,
        'prometheus_pushgateway_url',
        os.environ.get('PROMETHEUS_PUSHGATEWAY_URL', 'localhost:9091')
    )

    # Remover protocolo se presente
    pushgateway_host = pushgateway_url.replace('http://', '').replace('https://', '')

    registry = CollectorRegistry()

    # Métricas de predição
    for window_name, metrics in results.get('windows', {}).items():
        if not metrics.get('sufficient_data'):
            continue

        for metric_name in ['mae', 'mae_pct', 'rmse', 'r2']:
            value = metrics.get(metric_name)
            if value is not None:
                gauge = Gauge(
                    f'neural_hive_validation_{metric_name}',
                    f'Validation {metric_name}',
                    ['window', 'model'],
                    registry=registry
                )
                gauge.labels(window=window_name, model='duration-predictor').set(value)

        # Sample count
        sample_count = metrics.get('sample_count')
        if sample_count is not None:
            gauge = Gauge(
                'neural_hive_validation_sample_count',
                'Validation sample count',
                ['window', 'model'],
                registry=registry
            )
            gauge.labels(window=window_name, model='duration-predictor').set(sample_count)

    # Métricas de latência
    for window_name, metrics in results.get('latency_windows', {}).items():
        if not metrics.get('sufficient_data'):
            continue

        for metric_name in ['p50', 'p95', 'p99', 'mean', 'error_rate']:
            value = metrics.get(metric_name)
            if value is not None:
                gauge = Gauge(
                    f'neural_hive_validation_latency_{metric_name}',
                    f'Validation latency {metric_name}',
                    ['window', 'model'],
                    registry=registry
                )
                gauge.labels(window=window_name, model='duration-predictor').set(value)

    # Push para gateway
    try:
        push_to_gateway(
            pushgateway_host,
            job='continuous-validation',
            registry=registry
        )
        logger.info("metrics_pushed_to_gateway", gateway=pushgateway_host)
    except Exception as e:
        logger.warning("pushgateway_failed", error=str(e), gateway=pushgateway_host)


def main():
    parser = argparse.ArgumentParser(description='Continuous Validation CronJob')
    parser.add_argument(
        '--populate-from-mongodb',
        action='store_true',
        help='Popular janelas do MongoDB'
    )
    parser.add_argument(
        '--compute-metrics',
        action='store_true',
        help='Computar métricas'
    )
    parser.add_argument(
        '--check-thresholds',
        action='store_true',
        help='Verificar thresholds'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Logging verboso'
    )

    args = parser.parse_args()

    # Se nenhuma flag foi passada, executar tudo
    if not any([args.populate_from_mongodb, args.compute_metrics, args.check_thresholds]):
        args.populate_from_mongodb = True
        args.compute_metrics = True
        args.check_thresholds = True

    try:
        asyncio.run(run_validation(
            populate_from_mongodb=args.populate_from_mongodb,
            compute_metrics=args.compute_metrics,
            check_thresholds=args.check_thresholds,
            verbose=args.verbose
        ))
        logger.info("script_completed_successfully")
        sys.exit(0)
    except Exception as e:
        logger.error("script_failed", error=str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
