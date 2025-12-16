#!/usr/bin/env python3
"""
Script CLI para restore de backups de disaster recovery.

Uso:
    # Listar backups disponíveis
    python run_disaster_recovery_restore.py --list --specialist-type business

    # Restaurar backup mais recente
    python run_disaster_recovery_restore.py --latest --specialist-type business

    # Restaurar backup específico por ID/timestamp
    python run_disaster_recovery_restore.py --backup-id specialist-business-backup-20250211-143000 --specialist-type business

    # Restore com validação desabilitada (não recomendado)
    python run_disaster_recovery_restore.py --latest --specialist-type business --skip-validation

    # Restore forçado sem confirmação
    python run_disaster_recovery_restore.py --backup-id abc123 --specialist-type business --force
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


def list_backups(dr_manager: DisasterRecoveryManager) -> int:
    """
    Lista backups disponíveis.

    Args:
        dr_manager: Gerenciador de disaster recovery

    Returns:
        Código de saída (0=sucesso)
    """
    print("Listando backups disponíveis...")
    print()

    backups = dr_manager.list_available_backups()

    # Filtrar apenas .tar.gz
    backup_files = [b for b in backups if b['key'].endswith('.tar.gz')]

    if not backup_files:
        print("Nenhum backup encontrado.")
        return 0

    print(f"Total de backups: {len(backup_files)}")
    print()
    print(f"{'#':<4} {'Backup File':<60} {'Size (MB)':<12} {'Timestamp':<20}")
    print("-" * 100)

    for i, backup in enumerate(backup_files, 1):
        size_mb = backup.get('size', 0) / (1024 * 1024)
        timestamp = backup.get('timestamp', 'unknown')

        if isinstance(timestamp, datetime):
            timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        else:
            timestamp_str = str(timestamp)

        print(f"{i:<4} {backup['key']:<60} {size_mb:>10.2f}  {timestamp_str:<20}")

    print()
    return 0


def confirm_restore(backup_id: str) -> bool:
    """
    Solicita confirmação do usuário.

    Args:
        backup_id: ID do backup a restaurar

    Returns:
        True se confirmado, False caso contrário
    """
    print()
    print("=" * 80)
    print("ATENÇÃO: Operação de Restore")
    print("=" * 80)
    print(f"Backup: {backup_id}")
    print()
    print("Esta operação irá:")
    print("  1. Baixar o backup do storage")
    print("  2. Validar checksums")
    print("  3. Restaurar componentes")
    print("  4. Executar smoke tests")
    print()
    print("Tem certeza que deseja continuar? (yes/no): ", end='')

    response = input().strip().lower()
    return response in ['yes', 'y', 'sim', 's']


def main():
    """Função principal do script."""
    parser = argparse.ArgumentParser(
        description='Restore de backups de disaster recovery',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Ações
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        '--list',
        action='store_true',
        help='Listar backups disponíveis'
    )
    action_group.add_argument(
        '--latest',
        action='store_true',
        help='Restaurar backup mais recente'
    )
    action_group.add_argument(
        '--backup-id',
        type=str,
        help='ID ou nome do arquivo de backup específico'
    )
    action_group.add_argument(
        '--timestamp',
        type=str,
        help='Timestamp do backup (formato: YYYYMMDD-HHMMSS)'
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
        '--tenant-id',
        type=str,
        help='ID do tenant (para multi-tenancy)'
    )

    parser.add_argument(
        '--target-dir',
        type=str,
        help='Diretório de destino para restore (opcional)'
    )

    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Pular validação de checksums (não recomendado)'
    )

    parser.add_argument(
        '--skip-smoke-tests',
        action='store_true',
        help='Pular smoke tests após restore'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Não solicitar confirmação'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Modo verbose (log detalhado)'
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

        # Executar ação
        if args.list:
            return list_backups(dr_manager)

        # Determinar backup_id
        backup_id = None

        if args.latest:
            # Pegar mais recente
            backups = dr_manager.list_available_backups()
            backup_files = [b for b in backups if b['key'].endswith('.tar.gz')]

            if not backup_files:
                print("ERRO: Nenhum backup disponível", file=sys.stderr)
                return 1

            backup_id = backup_files[0]['key']
            print(f"Backup mais recente: {backup_id}")

        elif args.backup_id:
            backup_id = args.backup_id

        elif args.timestamp:
            # Procurar por timestamp
            backups = dr_manager.list_available_backups()

            for b in backups:
                if args.timestamp in b['key']:
                    backup_id = b['key']
                    break

            if not backup_id:
                print(f"ERRO: Backup com timestamp {args.timestamp} não encontrado", file=sys.stderr)
                return 1

        if not backup_id:
            print("ERRO: Backup não especificado", file=sys.stderr)
            return 1

        # Solicitar confirmação
        if not args.force:
            if not confirm_restore(backup_id):
                print("Operação cancelada pelo usuário.")
                return 0

        # Executar restore
        print()
        print("Iniciando restore...")
        print()

        result = dr_manager.restore_specialist_state(
            backup_id=backup_id,
            target_dir=args.target_dir,
            skip_validation=args.skip_validation,
            skip_smoke_tests=args.skip_smoke_tests
        )

        # Exibir resultado
        print()
        print("=" * 80)
        print("Resultado do Restore")
        print("=" * 80)
        print(json.dumps(result, indent=2, default=str))
        print()

        if result['status'] == 'success':
            print("✓ Restore concluído com sucesso!")
            return 0
        else:
            print(f"✗ Restore falhou: {result.get('error', 'Erro desconhecido')}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"ERRO: {str(e)}", file=sys.stderr)
        logger.exception("Erro fatal no script de restore")
        return 1


if __name__ == '__main__':
    sys.exit(main())
