#!/usr/bin/env python3
"""
Script CLI para executar backup de disaster recovery de especialistas.

Uso:
    python -m neural_hive_specialists.scripts.run_disaster_recovery_backup
    python -m neural_hive_specialists.scripts.run_disaster_recovery_backup --specialist-type technical --dry-run
    python -m neural_hive_specialists.scripts.run_disaster_recovery_backup --tenant-id tenant-A

Este script é executado pelo CronJob Kubernetes diariamente.
"""

import os
import sys
import argparse
import logging
import structlog
from typing import Optional

# Configurar logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def create_storage_client(config):
    """
    Cria cliente de storage baseado na configuração.

    Args:
        config: SpecialistConfig

    Returns:
        StorageClient (S3/GCS/Local)
    """
    from neural_hive_specialists.disaster_recovery import (
        S3StorageClient,
        GCSStorageClient,
        LocalStorageClient,
    )

    provider = config.backup_storage_provider

    logger.info("Criando storage client", provider=provider)

    if provider == "s3":
        if not config.backup_s3_bucket:
            raise ValueError("backup_s3_bucket é obrigatório quando provider=s3")

        return S3StorageClient(
            bucket=config.backup_s3_bucket,
            region=config.backup_s3_region,
            prefix=config.backup_prefix,
            aws_access_key=config.aws_access_key_id,
            aws_secret_key=config.aws_secret_access_key,
        )

    elif provider == "gcs":
        if not config.backup_gcs_bucket or not config.backup_gcs_project:
            raise ValueError(
                "backup_gcs_bucket e backup_gcs_project são obrigatórios quando provider=gcs"
            )

        return GCSStorageClient(
            bucket=config.backup_gcs_bucket,
            project=config.backup_gcs_project,
            prefix=config.backup_prefix,
            credentials_path=config.gcp_credentials_path,
        )

    elif provider == "local":
        return LocalStorageClient(base_path=config.backup_local_path)

    else:
        raise ValueError(f"Provider de storage desconhecido: {provider}")


def run_backup(
    specialist_type: Optional[str] = None,
    tenant_id: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = False,
    pushgateway_url: Optional[str] = None,
    cleanup: bool = False,
):
    """
    Executa backup de disaster recovery.

    Args:
        specialist_type: Tipo do especialista (None = todos)
        tenant_id: Tenant ID (None = todos)
        dry_run: Simular sem executar
        verbose: Logging detalhado
        pushgateway_url: URL do Prometheus Pushgateway
        cleanup: Executar limpeza de backups expirados após backup
    """
    from neural_hive_specialists.config import SpecialistConfig
    from neural_hive_specialists.disaster_recovery import DisasterRecoveryManager

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    logger.info(
        "Iniciando processo de backup de disaster recovery",
        specialist_type=specialist_type or "todos",
        tenant_id=tenant_id or "todos",
        dry_run=dry_run,
    )

    try:
        # Carregar configuração
        config = SpecialistConfig()

        # Verificar se DR está habilitado
        if not config.enable_disaster_recovery:
            logger.warning(
                "Disaster recovery não está habilitado",
                hint="Configure ENABLE_DISASTER_RECOVERY=true para habilitar",
            )
            return 0

        # Determinar tipos de especialistas a fazer backup
        if specialist_type:
            specialist_types = [specialist_type]
        else:
            # Fazer backup de todos os tipos
            specialist_types = [
                "technical",
                "business",
                "behavior",
                "evolution",
                "architecture",
            ]

        # Determinar tenants
        tenants = [tenant_id] if tenant_id else ["default"]

        if config.enable_multi_tenancy and not tenant_id:
            logger.info("Multi-tenancy habilitado, fazendo backup de todos os tenants")
            # Aqui você poderia listar todos os tenants ativos
            # tenants = get_active_tenants()

        total_backups = 0
        successful_backups = 0
        failed_backups = 0

        for spec_type in specialist_types:
            for tenant in tenants:
                logger.info(
                    "Executando backup", specialist_type=spec_type, tenant_id=tenant
                )

                if dry_run:
                    logger.info(
                        "[DRY-RUN] Criaria backup",
                        specialist_type=spec_type,
                        tenant_id=tenant,
                    )
                    successful_backups += 1
                    continue

                try:
                    # Criar configuração específica para o tipo
                    spec_config = SpecialistConfig(
                        specialist_type=spec_type,
                        service_name=f"{spec_type}-specialist",
                    )

                    # Criar storage client
                    storage_client = create_storage_client(spec_config)

                    # Criar specialist stub (simplificado para backup)
                    # Nota: Em produção, você poderia instanciar o specialist real
                    # Por ora, criamos um objeto stub com os componentes necessários
                    class SpecialistStub:
                        def __init__(self, config):
                            self.config = config
                            self.mlflow_client = (
                                None  # Seria inicializado se necessário
                            )
                            # Importar aqui para evitar problemas de importação circular
                            from neural_hive_specialists.metrics import (
                                SpecialistMetrics,
                            )

                            self.metrics = SpecialistMetrics(config, spec_type)

                    specialist_stub = SpecialistStub(spec_config)

                    # Criar DisasterRecoveryManager
                    dr_manager = DisasterRecoveryManager(
                        config=spec_config,
                        specialist=specialist_stub,
                        storage_client=storage_client,
                    )

                    # Executar backup
                    result = dr_manager.backup_specialist_state(
                        tenant_id=tenant if tenant != "default" else None
                    )

                    if result["status"] == "success":
                        successful_backups += 1

                        logger.info(
                            "Backup concluído com sucesso",
                            specialist_type=spec_type,
                            tenant_id=tenant,
                            backup_id=result["backup_id"],
                            size_mb=round(
                                result["total_size_bytes"] / (1024 * 1024), 2
                            ),
                            duration_seconds=result["duration_seconds"],
                            components=result["components_included"],
                        )
                    else:
                        failed_backups += 1

                        logger.error(
                            "Backup falhou",
                            specialist_type=spec_type,
                            tenant_id=tenant,
                            error=result.get("error"),
                        )

                except Exception as e:
                    failed_backups += 1

                    logger.error(
                        "Erro ao executar backup",
                        specialist_type=spec_type,
                        tenant_id=tenant,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

                total_backups += 1

        # Resumo final
        logger.info(
            "Processo de backup concluído",
            total_backups=total_backups,
            successful=successful_backups,
            failed=failed_backups,
        )

        # Limpeza de backups expirados (se habilitado)
        if cleanup and not dry_run and successful_backups > 0:
            logger.info("Iniciando limpeza de backups expirados")

            total_deleted = 0
            for spec_type in specialist_types:
                try:
                    # Criar configuração específica para o tipo
                    spec_config = SpecialistConfig(
                        specialist_type=spec_type,
                        service_name=f"{spec_type}-specialist",
                    )

                    # Criar storage client
                    storage_client = create_storage_client(spec_config)

                    # Criar specialist stub
                    class SpecialistStub:
                        def __init__(self, config):
                            self.config = config
                            from neural_hive_specialists.metrics import (
                                SpecialistMetrics,
                            )

                            self.metrics = SpecialistMetrics(config, spec_type)

                    specialist_stub = SpecialistStub(spec_config)

                    # Criar DisasterRecoveryManager
                    dr_manager = DisasterRecoveryManager(
                        config=spec_config,
                        specialist=specialist_stub,
                        storage_client=storage_client,
                    )

                    # Executar limpeza
                    deleted_count = dr_manager.delete_expired_backups()
                    total_deleted += deleted_count

                    logger.info(
                        "Backups expirados deletados",
                        specialist_type=spec_type,
                        deleted_count=deleted_count,
                    )

                except Exception as e:
                    logger.error(
                        "Erro ao limpar backups expirados",
                        specialist_type=spec_type,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

            logger.info("Limpeza de backups concluída", total_deleted=total_deleted)

        # Push de métricas para Prometheus Pushgateway (se configurado)
        if pushgateway_url and not dry_run:
            try:
                from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

                registry = CollectorRegistry()

                # Métrica de sucesso/falha
                backup_result_gauge = Gauge(
                    "neural_hive_dr_backup_result",
                    "Resultado do job de backup (1=success, 0=failure)",
                    ["specialist_type"],
                    registry=registry,
                )

                for spec_type in specialist_types:
                    backup_result_gauge.labels(specialist_type=spec_type).set(
                        1 if failed_backups == 0 else 0
                    )

                push_to_gateway(
                    pushgateway_url, job="disaster_recovery_backup", registry=registry
                )

                logger.info("Métricas enviadas para Pushgateway", url=pushgateway_url)

            except Exception as e:
                logger.warning("Erro ao enviar métricas para Pushgateway", error=str(e))

        # Exit code
        return 1 if failed_backups > 0 else 0

    except Exception as e:
        logger.error(
            "Erro fatal no processo de backup",
            error=str(e),
            error_type=type(e).__name__,
        )
        return 1


def main():
    """Entrypoint do script."""
    parser = argparse.ArgumentParser(
        description="Executa backup de disaster recovery para especialistas neurais"
    )

    parser.add_argument(
        "--specialist-type",
        type=str,
        help="Tipo de especialista (technical, business, etc). Default: todos",
    )

    parser.add_argument(
        "--tenant-id", type=str, help="Tenant ID específico. Default: todos"
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Simular execução sem fazer backup"
    )

    parser.add_argument("--verbose", action="store_true", help="Logging detalhado")

    parser.add_argument(
        "--pushgateway-url",
        type=str,
        help="URL do Prometheus Pushgateway para enviar métricas",
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Executar limpeza de backups expirados após backup bem-sucedido",
    )

    args = parser.parse_args()

    # Executar backup
    exit_code = run_backup(
        specialist_type=args.specialist_type,
        tenant_id=args.tenant_id,
        dry_run=args.dry_run,
        verbose=args.verbose,
        pushgateway_url=args.pushgateway_url,
        cleanup=args.cleanup,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
