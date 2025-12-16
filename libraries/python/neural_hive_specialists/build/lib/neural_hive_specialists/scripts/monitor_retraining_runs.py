#!/usr/bin/env python3
"""
Script para monitorar runs MLflow de re-treinamento e atualizar status dos triggers.

Este script deve ser executado periodicamente (ex: via CronJob a cada 5 minutos)
para verificar o status de runs assíncronos e atualizar os registros de trigger.
"""

import sys
import time
import argparse
from datetime import datetime, timedelta
import structlog
from pymongo import MongoClient
from mlflow.tracking import MlflowClient

logger = structlog.get_logger()


def monitor_running_triggers(
    mongodb_uri: str,
    mongodb_database: str,
    mlflow_tracking_uri: str,
    max_run_age_hours: int = 24
) -> dict:
    """
    Monitora triggers em execução e atualiza seus status.

    Args:
        mongodb_uri: URI de conexão MongoDB
        mongodb_database: Nome do database
        mlflow_tracking_uri: URI do MLflow tracking server
        max_run_age_hours: Idade máxima de run antes de considerar timeout

    Returns:
        Dict com estatísticas de processamento
    """
    stats = {
        'checked': 0,
        'completed': 0,
        'failed': 0,
        'timed_out': 0,
        'still_running': 0,
        'errors': 0
    }

    try:
        # Conectar ao MongoDB
        mongo_client = MongoClient(mongodb_uri)
        db = mongo_client[mongodb_database]
        triggers_collection = db['retraining_triggers']

        # Conectar ao MLflow
        mlflow_client = MlflowClient(tracking_uri=mlflow_tracking_uri)

        # Buscar triggers em execução
        running_triggers = list(triggers_collection.find({
            'status': 'running'
        }))

        stats['checked'] = len(running_triggers)

        logger.info(
            "Starting monitoring of retraining runs",
            total_running=stats['checked']
        )

        for trigger in running_triggers:
            trigger_id = trigger.get('trigger_id')
            mlflow_run_id = trigger.get('metadata', {}).get('mlflow_run_id')
            triggered_at = trigger.get('triggered_at')
            specialist_type = trigger.get('specialist_type')

            if not mlflow_run_id:
                logger.warning(
                    "Trigger without MLflow run ID",
                    trigger_id=trigger_id
                )
                continue

            try:
                # Verificar idade do run
                run_age = datetime.utcnow() - triggered_at
                if run_age > timedelta(hours=max_run_age_hours):
                    logger.warning(
                        "Run exceeded max age - marking as failed",
                        trigger_id=trigger_id,
                        mlflow_run_id=mlflow_run_id,
                        age_hours=run_age.total_seconds() / 3600
                    )

                    triggers_collection.update_one(
                        {'trigger_id': trigger_id},
                        {
                            '$set': {
                                'status': 'failed',
                                'completed_at': datetime.utcnow(),
                                'metadata.error_message': f'Run timeout após {max_run_age_hours} horas',
                                'metadata.timed_out': True
                            }
                        }
                    )
                    stats['timed_out'] += 1
                    continue

                # Verificar status do run no MLflow
                run = mlflow_client.get_run(mlflow_run_id)
                run_status = run.info.status

                logger.debug(
                    "Checked MLflow run status",
                    trigger_id=trigger_id,
                    mlflow_run_id=mlflow_run_id,
                    status=run_status
                )

                if run_status == 'FINISHED':
                    # Run concluído com sucesso
                    end_time = datetime.fromtimestamp(run.info.end_time / 1000)
                    start_time = datetime.fromtimestamp(run.info.start_time / 1000)
                    duration = (end_time - start_time).total_seconds()

                    # Extrair métricas do run
                    metrics = run.data.metrics

                    update_data = {
                        'status': 'completed',
                        'completed_at': datetime.utcnow(),
                        'metadata.duration_seconds': duration,
                        'metadata.mlflow_status': run_status
                    }

                    # Adicionar métricas relevantes
                    if 'precision' in metrics:
                        update_data['metadata.model_precision'] = metrics['precision']
                    if 'recall' in metrics:
                        update_data['metadata.model_recall'] = metrics['recall']
                    if 'f1' in metrics:
                        update_data['metadata.model_f1'] = metrics['f1']

                    triggers_collection.update_one(
                        {'trigger_id': trigger_id},
                        {'$set': update_data}
                    )

                    logger.info(
                        "Run completed successfully",
                        trigger_id=trigger_id,
                        mlflow_run_id=mlflow_run_id,
                        duration_seconds=duration,
                        specialist_type=specialist_type
                    )
                    stats['completed'] += 1

                elif run_status == 'FAILED':
                    # Run falhou
                    triggers_collection.update_one(
                        {'trigger_id': trigger_id},
                        {
                            '$set': {
                                'status': 'failed',
                                'completed_at': datetime.utcnow(),
                                'metadata.mlflow_status': run_status,
                                'metadata.error_message': 'Run MLflow falhou'
                            }
                        }
                    )

                    logger.error(
                        "Run failed",
                        trigger_id=trigger_id,
                        mlflow_run_id=mlflow_run_id,
                        specialist_type=specialist_type
                    )
                    stats['failed'] += 1

                elif run_status == 'KILLED':
                    # Run foi cancelado
                    triggers_collection.update_one(
                        {'trigger_id': trigger_id},
                        {
                            '$set': {
                                'status': 'failed',
                                'completed_at': datetime.utcnow(),
                                'metadata.mlflow_status': run_status,
                                'metadata.error_message': 'Run MLflow foi cancelado'
                            }
                        }
                    )

                    logger.warning(
                        "Run was killed",
                        trigger_id=trigger_id,
                        mlflow_run_id=mlflow_run_id,
                        specialist_type=specialist_type
                    )
                    stats['failed'] += 1

                else:
                    # Ainda em execução (RUNNING, SCHEDULED)
                    stats['still_running'] += 1
                    logger.debug(
                        "Run still in progress",
                        trigger_id=trigger_id,
                        mlflow_run_id=mlflow_run_id,
                        status=run_status,
                        specialist_type=specialist_type
                    )

            except Exception as e:
                logger.error(
                    "Error monitoring trigger",
                    trigger_id=trigger_id,
                    mlflow_run_id=mlflow_run_id,
                    error=str(e)
                )
                stats['errors'] += 1

        logger.info(
            "Monitoring completed",
            **stats
        )

        mongo_client.close()
        return stats

    except Exception as e:
        logger.error(
            "Fatal error in monitoring",
            error=str(e)
        )
        stats['errors'] += 1
        return stats


def main():
    """Função principal do script."""
    parser = argparse.ArgumentParser(
        description='Monitora runs MLflow de re-treinamento'
    )
    parser.add_argument(
        '--mongodb-uri',
        default='mongodb://localhost:27017',
        help='URI de conexão MongoDB'
    )
    parser.add_argument(
        '--mongodb-database',
        default='neural_hive',
        help='Nome do database MongoDB'
    )
    parser.add_argument(
        '--mlflow-tracking-uri',
        default='http://localhost:5000',
        help='URI do MLflow tracking server'
    )
    parser.add_argument(
        '--max-run-age-hours',
        type=int,
        default=24,
        help='Idade máxima de run em horas antes de timeout'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Executa em modo dry-run (sem atualizar database)'
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("Running in DRY-RUN mode - no database updates")

    # Executar monitoramento
    stats = monitor_running_triggers(
        mongodb_uri=args.mongodb_uri,
        mongodb_database=args.mongodb_database,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        max_run_age_hours=args.max_run_age_hours
    )

    # Imprimir resumo
    print("\n=== Resumo do Monitoramento ===")
    print(f"Triggers verificados: {stats['checked']}")
    print(f"Completados: {stats['completed']}")
    print(f"Falhados: {stats['failed']}")
    print(f"Timeout: {stats['timed_out']}")
    print(f"Ainda em execução: {stats['still_running']}")
    print(f"Erros: {stats['errors']}")
    print()

    # Exit code baseado em erros
    if stats['errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
