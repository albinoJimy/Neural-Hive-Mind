#!/usr/bin/env python3
"""
Script para migrar SBOMs existentes de file:// para S3.

Uso:
    python migrate_sboms_to_s3.py --dry-run  # Apenas mostra o que seria feito
    python migrate_sboms_to_s3.py            # Executa a migração
"""
import asyncio
import argparse
import os
import sys
import structlog

# Adicionar path do projeto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.clients.s3_artifact_client import S3ArtifactClient
from src.clients.mongodb_client import MongoDBClient
from src.config import get_settings

logger = structlog.get_logger()


async def migrate_sboms(dry_run: bool = True):
    """
    Migra SBOMs de file:// para S3.

    Args:
        dry_run: Se True, apenas mostra o que seria feito
    """
    settings = get_settings()

    if not settings.ARTIFACTS_S3_BUCKET:
        logger.error('ARTIFACTS_S3_BUCKET não configurado')
        return

    # Inicializar clientes
    mongodb_client = MongoDBClient(settings.MONGODB_URL, 'code_forge')
    await mongodb_client.start()

    s3_client = S3ArtifactClient(
        bucket=settings.ARTIFACTS_S3_BUCKET,
        region=settings.ARTIFACTS_S3_REGION,
        endpoint=settings.ARTIFACTS_S3_ENDPOINT or None
    )

    try:
        # Buscar artefatos com SBOM local
        collection = mongodb_client.db.artifacts
        cursor = collection.find({
            'sbom_uri': {'$regex': '^file://'}
        })

        migrated = 0
        failed = 0
        skipped = 0

        async for artifact in cursor:
            artifact_id = artifact.get('artifact_id')
            ticket_id = artifact.get('ticket_id', 'unknown')
            sbom_uri = artifact.get('sbom_uri')

            if not sbom_uri or not sbom_uri.startswith('file://'):
                continue

            local_path = sbom_uri.replace('file://', '')

            if not os.path.exists(local_path):
                logger.warning(
                    'sbom_file_not_found',
                    artifact_id=artifact_id,
                    local_path=local_path
                )
                skipped += 1
                continue

            if dry_run:
                logger.info(
                    'would_migrate',
                    artifact_id=artifact_id,
                    ticket_id=ticket_id,
                    local_path=local_path
                )
                migrated += 1
                continue

            try:
                # Upload para S3
                new_uri = await s3_client.upload_sbom(
                    local_path=local_path,
                    artifact_id=artifact_id,
                    ticket_id=ticket_id
                )

                # Atualizar MongoDB
                await collection.update_one(
                    {'artifact_id': artifact_id},
                    {'$set': {'sbom_uri': new_uri, 'sbom_storage': 's3'}}
                )

                # Deletar arquivo local
                os.unlink(local_path)

                logger.info(
                    'sbom_migrated',
                    artifact_id=artifact_id,
                    old_uri=sbom_uri,
                    new_uri=new_uri
                )
                migrated += 1

            except Exception as e:
                logger.error(
                    'migration_failed',
                    artifact_id=artifact_id,
                    error=str(e)
                )
                failed += 1

        logger.info(
            'migration_completed',
            dry_run=dry_run,
            migrated=migrated,
            failed=failed,
            skipped=skipped
        )

    finally:
        await mongodb_client.stop()


def main():
    parser = argparse.ArgumentParser(
        description='Migra SBOMs de file:// para S3'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Apenas mostra o que seria feito'
    )

    args = parser.parse_args()

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(20),
        processors=[
            structlog.dev.ConsoleRenderer()
        ]
    )

    asyncio.run(migrate_sboms(dry_run=args.dry_run))


if __name__ == '__main__':
    main()
