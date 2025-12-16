#!/usr/bin/env python3
"""
Script para verificar threshold de feedback e disparar re-treinamento de modelos.

Este script deve ser executado periodicamente (via CronJob) para monitorar
feedback humano e disparar pipeline MLflow quando threshold atingido.

Uso:
    python run_retraining_trigger.py
    python run_retraining_trigger.py --dry-run
    python run_retraining_trigger.py --specialist-type technical
    python run_retraining_trigger.py --force
    python run_retraining_trigger.py --pushgateway-url http://localhost:9091
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()


def load_config() -> Dict[str, Any]:
    """
    Carrega configuração de variáveis de ambiente.

    Returns:
        Dict com configuração
    """
    try:
        config = {
            # MongoDB
            'mongodb_uri': os.getenv('MONGODB_URI'),
            'mongodb_database': os.getenv('MONGODB_DATABASE', 'neural_hive'),
            'mongodb_opinions_collection': os.getenv('MONGODB_OPINIONS_COLLECTION', 'cognitive_ledger'),
            'feedback_mongodb_collection': os.getenv('FEEDBACK_MONGODB_COLLECTION', 'specialist_feedback'),

            # Feedback & Retraining
            'enable_feedback_collection': os.getenv('ENABLE_FEEDBACK_COLLECTION', 'true').lower() == 'true',
            'enable_retraining_trigger': os.getenv('ENABLE_RETRAINING_TRIGGER', 'true').lower() == 'true',
            'retraining_feedback_threshold': int(os.getenv('RETRAINING_FEEDBACK_THRESHOLD', '100')),
            'retraining_feedback_window_days': int(os.getenv('RETRAINING_FEEDBACK_WINDOW_DAYS', '7')),
            'retraining_mlflow_project_uri': os.getenv('RETRAINING_MLFLOW_PROJECT_URI', './ml_pipelines/training'),
            'retraining_min_feedback_quality': float(os.getenv('RETRAINING_MIN_FEEDBACK_QUALITY', '0.5')),

            # MLflow
            'mlflow_tracking_uri': os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow:5000'),

            # Prometheus Pushgateway (opcional)
            'pushgateway_url': os.getenv('PUSHGATEWAY_URL')
        }

        # Validar campos obrigatórios
        if not config['mongodb_uri']:
            raise ValueError("MONGODB_URI é obrigatório")

        return config

    except Exception as e:
        print(f"❌ ERRO ao carregar configuração: {e}", file=sys.stderr)
        print("\n📋 Variáveis de ambiente necessárias:", file=sys.stderr)
        print("  ✅ MONGODB_URI - URI do MongoDB", file=sys.stderr)
        print("  ⚙️  ENABLE_RETRAINING_TRIGGER - Habilitar trigger (default: true)", file=sys.stderr)
        print("  ⚙️  RETRAINING_FEEDBACK_THRESHOLD - Threshold de feedbacks (default: 100)", file=sys.stderr)
        print("  ⚙️  MLFLOW_TRACKING_URI - URI do MLflow (default: http://mlflow:5000)", file=sys.stderr)
        sys.exit(1)


def initialize_components(config: Dict[str, Any], specialist_type: str):
    """
    Inicializa componentes de feedback e retraining trigger.

    Args:
        config: Configuração
        specialist_type: Tipo do especialista

    Returns:
        Tupla (feedback_collector, retraining_trigger)
    """
    from neural_hive_specialists.config import SpecialistConfig
    from neural_hive_specialists.feedback import FeedbackCollector, RetrainingTrigger
    from neural_hive_specialists.mlflow_client import MLflowClient

    # Criar SpecialistConfig temporário
    temp_config = SpecialistConfig(
        specialist_type=specialist_type,
        mongodb_uri=config['mongodb_uri'],
        mongodb_database=config['mongodb_database'],
        mongodb_opinions_collection=config['mongodb_opinions_collection'],
        feedback_mongodb_collection=config['feedback_mongodb_collection'],
        enable_feedback_collection=config['enable_feedback_collection'],
        enable_retraining_trigger=config['enable_retraining_trigger'],
        retraining_feedback_threshold=config['retraining_feedback_threshold'],
        retraining_feedback_window_days=config['retraining_feedback_window_days'],
        retraining_mlflow_project_uri=config['retraining_mlflow_project_uri'],
        retraining_min_feedback_quality=config['retraining_min_feedback_quality'],
        mlflow_tracking_uri=config['mlflow_tracking_uri']
    )

    # Inicializar componentes
    feedback_collector = FeedbackCollector(temp_config, audit_logger=None)
    mlflow_client = MLflowClient(temp_config)
    retraining_trigger = RetrainingTrigger(temp_config, feedback_collector, mlflow_client)

    logger.info(
        "Components initialized",
        specialist_type=specialist_type,
        threshold=temp_config.retraining_feedback_threshold
    )

    return feedback_collector, retraining_trigger


def check_and_trigger_retraining(
    specialist_type: str,
    config: Dict[str, Any],
    dry_run: bool = False,
    force: bool = False
) -> Optional[str]:
    """
    Verifica threshold e dispara re-treinamento se necessário.

    Args:
        specialist_type: Tipo do especialista
        config: Configuração
        dry_run: Modo de simulação
        force: Forçar trigger ignorando cooldown

    Returns:
        trigger_id se disparado, None caso contrário
    """
    try:
        # Inicializar componentes
        feedback_collector, retraining_trigger = initialize_components(config, specialist_type)

        # Verificar e disparar
        if dry_run:
            # Apenas verificar sem disparar
            should_trigger, feedback_count = retraining_trigger._should_trigger(specialist_type)

            logger.info(
                "Dry-run mode",
                specialist_type=specialist_type,
                feedback_count=feedback_count,
                threshold=config['retraining_feedback_threshold'],
                would_trigger=should_trigger
            )

            if should_trigger:
                print(f"✅ [DRY-RUN] Would trigger retraining for {specialist_type}")
                print(f"   Feedback count: {feedback_count} >= {config['retraining_feedback_threshold']}")
            else:
                print(f"ℹ️  [DRY-RUN] Threshold not met for {specialist_type}")
                print(f"   Feedback count: {feedback_count} < {config['retraining_feedback_threshold']}")

            return None

        else:
            # Disparar efetivamente
            trigger_id = retraining_trigger.check_and_trigger(
                specialist_type=specialist_type,
                force=force
            )

            if trigger_id:
                logger.info(
                    "Retraining triggered",
                    specialist_type=specialist_type,
                    trigger_id=trigger_id
                )
                print(f"✅ Retraining triggered for {specialist_type}")
                print(f"   Trigger ID: {trigger_id}")
                return trigger_id
            else:
                logger.info(
                    "No trigger needed",
                    specialist_type=specialist_type
                )
                print(f"ℹ️  No trigger needed for {specialist_type}")
                return None

    except Exception as e:
        logger.error(
            "Error checking retraining trigger",
            specialist_type=specialist_type,
            error=str(e)
        )
        print(f"❌ Error for {specialist_type}: {e}", file=sys.stderr)
        return None

    finally:
        # Fechar conexões
        if 'feedback_collector' in locals():
            feedback_collector.close()
        if 'retraining_trigger' in locals():
            retraining_trigger.close()


def push_metrics_to_pushgateway(config: Dict[str, Any], specialist_types: list):
    """
    Envia métricas para Prometheus Pushgateway.

    Args:
        config: Configuração
        specialist_types: Lista de tipos de especialistas processados
    """
    if not config['pushgateway_url']:
        return

    try:
        from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
        import socket

        registry = CollectorRegistry()

        # Métrica de última execução
        last_run = Gauge(
            'neural_hive_retraining_trigger_last_run_timestamp',
            'Timestamp da última execução do trigger checker',
            ['specialist_type'],
            registry=registry
        )

        timestamp = time.time()
        for specialist_type in specialist_types:
            last_run.labels(specialist_type=specialist_type).set(timestamp)

        # Push para gateway
        push_to_gateway(
            config['pushgateway_url'],
            job='retraining_trigger_checker',
            registry=registry,
            grouping_key={'instance': socket.gethostname()}
        )

        logger.info(
            "Metrics pushed to Pushgateway",
            url=config['pushgateway_url'],
            specialist_types=specialist_types
        )

    except Exception as e:
        logger.warning(
            "Failed to push metrics to Pushgateway",
            error=str(e)
        )


def main():
    """Ponto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Verificar threshold de feedback e disparar re-treinamento"
    )
    parser.add_argument(
        '--specialist-type',
        type=str,
        help="Executar apenas para especialista específico (default: todos)"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Simular execução sem disparar re-treinamento"
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help="Ignorar cooldown e disparar forçadamente"
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help="Logging detalhado"
    )
    parser.add_argument(
        '--pushgateway-url',
        type=str,
        help="URL do Prometheus Pushgateway (override de variável de ambiente)"
    )

    args = parser.parse_args()

    # Configurar logging
    if args.verbose:
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
        )

    print("🔄 Neural Hive - Retraining Trigger Checker")
    print(f"⏰ Execution time: {datetime.utcnow().isoformat()}")
    print()

    # Carregar configuração
    config = load_config()

    # Override pushgateway URL se fornecido
    if args.pushgateway_url:
        config['pushgateway_url'] = args.pushgateway_url

    # Verificar se está habilitado
    if not config['enable_retraining_trigger']:
        print("ℹ️  Retraining trigger disabled (ENABLE_RETRAINING_TRIGGER=false)")
        sys.exit(0)

    # Determinar especialistas a processar
    if args.specialist_type:
        specialist_types = [args.specialist_type]
    else:
        specialist_types = ['technical', 'business', 'behavior', 'evolution', 'architecture']

    print(f"📊 Processing {len(specialist_types)} specialist(s)")
    if args.dry_run:
        print("🔍 DRY-RUN MODE - No actual triggers will be executed")
    if args.force:
        print("⚠️  FORCE MODE - Cooldown will be ignored")
    print()

    # Processar cada especialista
    triggered_count = 0
    for specialist_type in specialist_types:
        print(f"--- {specialist_type.upper()} ---")

        trigger_id = check_and_trigger_retraining(
            specialist_type=specialist_type,
            config=config,
            dry_run=args.dry_run,
            force=args.force
        )

        if trigger_id:
            triggered_count += 1

        print()

    # Push métricas para Pushgateway
    if config['pushgateway_url']:
        push_metrics_to_pushgateway(config, specialist_types)

    # Resumo final
    print("=" * 50)
    print(f"✅ Execution completed")
    print(f"   Triggers executed: {triggered_count}/{len(specialist_types)}")
    print()

    sys.exit(0)


if __name__ == '__main__':
    main()
