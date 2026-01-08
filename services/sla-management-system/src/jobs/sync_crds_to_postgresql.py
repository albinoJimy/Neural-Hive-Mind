#!/usr/bin/env python3
"""
Job para sincronizar SLODefinition CRDs do Kubernetes para PostgreSQL.

Complementa o operator com reconciliacao periodica para:
- Recuperacao de drift entre CRDs e banco de dados
- Consistencia apos falhas do operator
- Sincronizacao inicial em novos deployments

Uso:
    python sync_crds_to_postgresql.py [--namespace NAMESPACE] [--dry-run]
"""

import asyncio
import argparse
import sys
import structlog

from ..config.settings import get_settings
from ..clients.postgresql_client import PostgreSQLClient
from ..clients.prometheus_client import PrometheusClient
from ..clients.kubernetes_client import KubernetesClient
from ..services.slo_manager import SLOManager

logger = structlog.get_logger()


async def main(namespace: str | None = None, dry_run: bool = False) -> int:
    """
    Executa sincronizacao de CRDs para PostgreSQL.

    Args:
        namespace: Namespace especifico ou None para todos.
        dry_run: Se True, simula sem persistir.

    Returns:
        Exit code (0 sucesso, 1 falha).
    """
    settings = get_settings()

    logger.info(
        "crd_sync_job.starting",
        namespace=namespace or "all",
        dry_run=dry_run,
        environment=settings.environment
    )

    # Inicializar clientes
    postgresql_client = PostgreSQLClient(settings.postgresql)
    prometheus_client = PrometheusClient(settings.prometheus)
    kubernetes_client = KubernetesClient(
        in_cluster=True,
        namespace=settings.kubernetes.namespace
    )

    try:
        # Conectar aos clientes
        await postgresql_client.connect()
        logger.info("crd_sync_job.postgresql_connected")

        await kubernetes_client.connect()
        logger.info("crd_sync_job.kubernetes_connected")

        if dry_run:
            # Em dry-run, listar CRDs sem sincronizar
            crds = await kubernetes_client.list_slo_definitions(namespace)
            logger.info(
                "crd_sync_job.dry_run_complete",
                crd_count=len(crds),
                message="Nenhuma alteracao foi feita (dry-run)"
            )
            for crd in crds:
                crd_name = crd.get("metadata", {}).get("name", "unknown")
                crd_namespace = crd.get("metadata", {}).get("namespace", "unknown")
                spec_name = crd.get("spec", {}).get("name", "unknown")
                logger.info(
                    "crd_sync_job.dry_run_crd",
                    crd_name=crd_name,
                    crd_namespace=crd_namespace,
                    spec_name=spec_name
                )
            return 0

        # Criar SLOManager e executar sincronizacao
        slo_manager = SLOManager(
            postgresql_client=postgresql_client,
            prometheus_client=prometheus_client,
            kubernetes_client=kubernetes_client
        )

        synced_ids = await slo_manager.sync_from_crds(namespace)

        logger.info(
            "crd_sync_job.completed",
            synced_count=len(synced_ids),
            synced_ids=synced_ids
        )

        return 0

    except Exception as e:
        logger.error(
            "crd_sync_job.failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return 1

    finally:
        # Cleanup
        await postgresql_client.disconnect()
        logger.info("crd_sync_job.cleanup_complete")


def parse_args() -> argparse.Namespace:
    """Parse argumentos da linha de comando."""
    parser = argparse.ArgumentParser(
        description="Sincroniza SLODefinition CRDs do Kubernetes para PostgreSQL"
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=None,
        help="Namespace especifico para sincronizar (default: todos)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simular sem persistir alteracoes"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    exit_code = asyncio.run(main(namespace=args.namespace, dry_run=args.dry_run))
    sys.exit(exit_code)
