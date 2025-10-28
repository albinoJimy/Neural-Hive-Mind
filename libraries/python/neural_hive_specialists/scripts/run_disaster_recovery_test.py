#!/usr/bin/env python3
"""
Script CLI para teste de recovery de backups de disaster recovery.

Uso:
    # Testar recovery do backup mais recente
    python run_disaster_recovery_test.py --specialist-type business

    # Testar backup específico
    python run_disaster_recovery_test.py --specialist-type business --backup-id specialist-business-backup-20250211-143000

    # Testar com alertas em caso de falha
    python run_disaster_recovery_test.py --specialist-type business --alert-on-failure

    # Enviar métricas para Pushgateway
    python run_disaster_recovery_test.py --specialist-type business --pushgateway-url http://localhost:9091
"""

import argparse
import sys
import os
import json
from datetime import datetime
import structlog

# Adicionar path do library ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from neural_hive_specialists.config import SpecialistConfig
from neural_hive_specialists.disaster_recovery.disaster_recovery_manager import DisasterRecoveryManager
from neural_hive_specialists.disaster_recovery.storage_client import (
    S3StorageClient,
    GCSStorageClient,
    LocalStorageClient
)

logger = structlog.get_logger()


def create_storage_client(config: SpecialistConfig):
    """
    Cria cliente de storage baseado na configuração.

    Args:
        config: Configuração do especialista

    Returns:
        Instância de StorageClient
    """
    provider = config.backup_storage_provider

    if provider == 's3':
        return S3StorageClient(
            bucket=config.backup_s3_bucket,
            region=config.backup_s3_region,
            prefix=config.backup_prefix or '',
            aws_access_key=config.aws_access_key_id,
            aws_secret_key=config.aws_secret_access_key
        )
    elif provider == 'gcs':
        if not config.backup_gcs_bucket or not config.backup_gcs_project:
            raise ValueError("backup_gcs_bucket e backup_gcs_project são obrigatórios quando provider=gcs")
        return GCSStorageClient(
            bucket=config.backup_gcs_bucket,
            project=config.backup_gcs_project,
            prefix=config.backup_prefix or '',
            credentials_path=config.gcp_credentials_path
        )
    elif provider == 'local':
        return LocalStorageClient(
            base_path=config.backup_local_path or '/tmp/backups'
        )
    else:
        raise ValueError(f"Storage provider não suportado: {provider}")


def push_metrics_to_gateway(pushgateway_url: str, metrics: dict, job_name: str):
    """
    Envia métricas para Prometheus Pushgateway.

    Args:
        pushgateway_url: URL do Pushgateway
        metrics: Dicionário de métricas
        job_name: Nome do job
    """
    try:
        from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

        registry = CollectorRegistry()

        # Criar gauge para status do teste
        test_status = Gauge(
            'dr_recovery_test_status',
            'Status do teste de recovery (1=success, 0=failed)',
            ['specialist_type'],
            registry=registry
        )

        # Criar gauge para duração
        test_duration = Gauge(
            'dr_recovery_test_duration_seconds',
            'Duração do teste de recovery',
            ['specialist_type'],
            registry=registry
        )

        # Definir valores
        status_value = 1 if metrics.get('status') == 'success' else 0
        test_status.labels(specialist_type=metrics.get('specialist_type', 'unknown')).set(status_value)
        test_duration.labels(specialist_type=metrics.get('specialist_type', 'unknown')).set(
            metrics.get('duration_seconds', 0)
        )

        # Enviar para pushgateway
        push_to_gateway(pushgateway_url, job=job_name, registry=registry)

        logger.info(
            "Métricas enviadas para Pushgateway",
            url=pushgateway_url,
            job=job_name
        )

    except ImportError:
        logger.warning("prometheus_client não instalado, métricas não enviadas")
    except Exception as e:
        logger.error("Erro ao enviar métricas", error=str(e))


def send_alert(message: str):
    """
    Envia alerta em caso de falha.

    Args:
        message: Mensagem de alerta
    """
    # TODO: Implementar integração com sistema de alertas (PagerDuty, Slack, etc.)
    logger.error("ALERTA DE DISASTER RECOVERY", message=message)
    print()
    print("=" * 80)
    print("ALERTA: Teste de Recovery Falhou")
    print("=" * 80)
    print(message)
    print("=" * 80)
    print()


def print_test_results(result: dict, verbose: bool = False):
    """
    Imprime resultados do teste de forma formatada.

    Args:
        result: Resultado do teste
        verbose: Modo verbose
    """
    print()
    print("=" * 80)
    print("Resultado do Teste de Recovery")
    print("=" * 80)
    print()
    print(f"Status: {result['status'].upper()}")
    print(f"Backup: {result.get('backup_id', 'N/A')}")
    print(f"Duração: {result.get('duration_seconds', 0):.2f}s")
    print()

    if result['status'] == 'success':
        print("✓ Teste concluído com sucesso!")
        print()

        test_results = result.get('test_results', {})

        print("Etapas validadas:")
        for step, data in test_results.items():
            status_icon = "✓" if data.get('status') == 'success' else ("⚠" if data.get('status') == 'skipped' else "✗")
            print(f"  {status_icon} {step}: {data.get('status', 'unknown')}")

            if verbose and 'error' in data:
                print(f"      Erro: {data['error']}")

        print()

    else:
        print(f"✗ Teste falhou: {result.get('error', 'Erro desconhecido')}")
        print()

        if verbose:
            print("Detalhes:")
            print(json.dumps(result.get('test_results', {}), indent=2))
            print()

    print("=" * 80)
    print()


def main():
    """Função principal do script."""
    parser = argparse.ArgumentParser(
        description='Teste de recovery de backups de disaster recovery',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Parâmetros obrigatórios
    parser.add_argument(
        '--specialist-type',
        type=str,
        required=True,
        choices=['business', 'technical', 'behavior', 'evolution', 'architecture'],
        help='Tipo de especialista'
    )

    # Parâmetros opcionais
    parser.add_argument(
        '--backup-id',
        type=str,
        help='ID ou nome do arquivo de backup específico (usa mais recente se não especificado)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Modo verbose (log detalhado)'
    )

    parser.add_argument(
        '--alert-on-failure',
        action='store_true',
        help='Enviar alerta em caso de falha'
    )

    parser.add_argument(
        '--pushgateway-url',
        type=str,
        help='URL do Prometheus Pushgateway para enviar métricas'
    )

    args = parser.parse_args()

    # Configurar logging
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG)
        )

    try:
        # Carregar configuração
        config = SpecialistConfig(specialist_type=args.specialist_type)

        # Criar storage client
        storage_client = create_storage_client(config)

        # Criar mock specialist (apenas para DR)
        class MockSpecialist:
            def __init__(self, config):
                self.config = config
                self.mlflow_client = None
                self.metrics = None

        specialist = MockSpecialist(config)

        # Criar DR manager
        dr_manager = DisasterRecoveryManager(
            config=config,
            specialist=specialist,
            storage_client=storage_client
        )

        # Executar teste de recovery
        print()
        print("Iniciando teste de recovery...")
        print()

        if args.backup_id:
            print(f"Backup selecionado: {args.backup_id}")
        else:
            print("Usando backup mais recente...")

        result = dr_manager.test_recovery(backup_id=args.backup_id)

        # Adicionar specialist_type ao resultado para métricas
        result['specialist_type'] = args.specialist_type

        # Exibir resultado
        print_test_results(result, verbose=args.verbose)

        # Enviar métricas para Pushgateway
        if args.pushgateway_url:
            push_metrics_to_gateway(
                pushgateway_url=args.pushgateway_url,
                metrics=result,
                job_name=f'dr_test_{args.specialist_type}'
            )

        # Enviar alerta em caso de falha
        if result['status'] != 'success' and args.alert_on_failure:
            alert_message = (
                f"Teste de recovery falhou para specialist-{args.specialist_type}\n"
                f"Backup: {result.get('backup_id', 'N/A')}\n"
                f"Erro: {result.get('error', 'Desconhecido')}\n"
                f"Timestamp: {datetime.utcnow().isoformat()}"
            )
            send_alert(alert_message)

        # Código de saída
        return 0 if result['status'] == 'success' else 1

    except Exception as e:
        print(f"ERRO: {str(e)}", file=sys.stderr)
        logger.exception("Erro fatal no script de teste")

        # Enviar alerta em caso de exceção
        if args.alert_on_failure:
            send_alert(f"Erro fatal no teste de recovery: {str(e)}")

        return 1


if __name__ == '__main__':
    sys.exit(main())
